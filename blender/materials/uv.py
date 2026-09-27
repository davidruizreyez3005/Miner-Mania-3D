"""UV generation: every textured asset gets one non-overlapping atlas layout
shared by all its render objects (they are baked into one texture set)."""

import math

import bmesh
import bpy

from core import scene as scn
from core.errors import PipelineError

UV_NAME = "UVMap"


def ensure_uv_layer(obj):
    me = obj.data
    if UV_NAME not in me.uv_layers:
        for layer in list(me.uv_layers):
            me.uv_layers.remove(layer)
        me.uv_layers.new(name=UV_NAME)
    me.uv_layers.active = me.uv_layers[UV_NAME]
    me.uv_layers[UV_NAME].active_render = True


def _scale_object_uvs(obj, factor):
    import numpy as np
    uvl = obj.data.uv_layers[UV_NAME].data
    n = len(uvl)
    if not n or abs(factor - 1.0) < 1e-6:
        return
    arr = np.empty(n * 2, dtype=np.float64)
    uvl.foreach_get("uv", arr)
    arr = arr.reshape(n, 2)
    c = arr.mean(axis=0)
    arr = c + (arr - c) * factor
    uvl.foreach_set("uv", arr.ravel())


def unwrap_atlas(objs, margin=0.004, angle_limit_deg=52.0, shape_method="CONCAVE"):
    """Smart-project + average scale + priority scaling + pack into one 0..1 atlas.

    Objects may carry ``mm_uv_scale`` (e.g. 1.8 for faces) to receive more
    texel density than the uniform average. Note: the FRACTION margin method
    runs an iterative scale search that is orders of magnitude slower (37 s vs
    2 s on a barrel); ADD is used with a margin derived from the bake padding.
    """
    objs = [o for o in objs if o.type == "MESH" and len(o.data.polygons)]
    if not objs:
        raise PipelineError("unwrap_atlas: nothing to unwrap")
    for o in objs:
        ensure_uv_layer(o)
    with scn.edit_mode(objs):
        r = bpy.ops.uv.smart_project(angle_limit=math.radians(angle_limit_deg), margin_method="SCALED",
                                     rotate_method="AXIS_ALIGNED_Y", island_margin=margin, area_weight=0.0,
                                     correct_aspect=True, scale_to_bounds=False)
        if "FINISHED" not in r:
            raise PipelineError(f"smart_project failed: {r}")
        bpy.ops.uv.select_all(action="SELECT")
        bpy.ops.uv.average_islands_scale()
    for o in objs:
        _scale_object_uvs(o, float(o.get("mm_uv_scale", 1.0)))
    with scn.edit_mode(objs):
        bpy.ops.uv.select_all(action="SELECT")
        # ADD keeps a constant UV-space gap between islands; SCALED shrinks the
        # gap for small islands, which lets neighbouring islands bleed into each
        # other under texture filtering.
        r = bpy.ops.uv.pack_islands(rotate=True, rotate_method="ANY", scale=True, margin_method="ADD",
                                    margin=margin, shape_method=shape_method)
        if "FINISHED" not in r:
            raise PipelineError(f"pack_islands failed: {r}")


def uv_stats(objs, texture_size, baked_only=True):
    """Coverage, overlap and texel density of the atlas (for validation/reporting)."""
    import numpy as np

    res = 256
    cover = np.zeros((res, res), dtype=np.uint16)
    densities = []
    total_uv_area = 0.0
    out_of_range = 0
    for o in objs:
        me = o.data
        if UV_NAME not in me.uv_layers:
            raise PipelineError(f"{o.name}: missing UV layer '{UV_NAME}'")
        uvl = me.uv_layers[UV_NAME].data
        mw = o.matrix_world
        me.calc_loop_triangles()
        for tri in me.loop_triangles:
            mat = me.materials[tri.material_index] if me.materials else None
            if baked_only and mat is not None and not mat.get("mm_baked", True):
                continue
            uvs = [uvl[li].uv for li in tri.loops]
            ps = [mw @ me.vertices[vi].co for vi in tri.vertices]
            a3 = ((ps[1] - ps[0]).cross(ps[2] - ps[0])).length * 0.5
            a2 = abs((uvs[1].x - uvs[0].x) * (uvs[2].y - uvs[0].y) - (uvs[2].x - uvs[0].x) * (uvs[1].y - uvs[0].y)) * 0.5
            total_uv_area += a2
            for uv in uvs:
                if uv.x < -1e-4 or uv.x > 1.0001 or uv.y < -1e-4 or uv.y > 1.0001:
                    out_of_range += 1
            if a3 > 1e-10:
                densities.append((math.sqrt(a2 / a3) * texture_size, a3))
            # Rasterize the triangle coarsely for overlap estimation (centroid samples of cells).
            xs = [min(max(uv.x, 0.0), 1.0) * res for uv in uvs]
            ys = [min(max(uv.y, 0.0), 1.0) * res for uv in uvs]
            x0, x1 = int(math.floor(min(xs))), int(math.ceil(max(xs)))
            y0, y1 = int(math.floor(min(ys))), int(math.ceil(max(ys)))
            if x1 <= x0 or y1 <= y0:
                continue
            gx, gy = np.meshgrid(np.arange(x0, x1) + 0.5, np.arange(y0, y1) + 0.5)
            (ax, bx, cx), (ay, by, cy) = xs, ys
            den = (by - cy) * (ax - cx) + (cx - bx) * (ay - cy)
            if abs(den) < 1e-12:
                continue
            l1 = ((by - cy) * (gx - cx) + (cx - bx) * (gy - cy)) / den
            l2 = ((cy - ay) * (gx - cx) + (ax - cx) * (gy - cy)) / den
            l3 = 1.0 - l1 - l2
            inside = (l1 >= 0) & (l2 >= 0) & (l3 >= 0)
            sub = cover[y0:y1, x0:x1]
            sub[inside] += 1
    overlap_cells = int((cover > 1).sum())
    used_cells = int((cover > 0).sum())
    if densities:
        ws = sorted(densities)
        tot = sum(w for _, w in ws)
        acc = 0.0
        median = ws[-1][0]
        for d, w in ws:
            acc += w
            if acc >= tot / 2:
                median = d
                break
        dmin = ws[0][0]
        dmax = ws[-1][0]
    else:
        median = dmin = dmax = 0.0
    return {
        "uv_area": round(total_uv_area, 4),
        "used_ratio": round(used_cells / float(res * res), 4),
        "overlap_ratio": round(overlap_cells / float(max(used_cells, 1)), 5),
        "out_of_range_uvs": out_of_range,
        "texel_density_median": round(median, 1),
        "texel_density_min": round(dmin, 1),
        "texel_density_max": round(dmax, 1),
    }
