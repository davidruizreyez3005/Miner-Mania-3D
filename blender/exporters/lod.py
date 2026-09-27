"""LOD generation.

LOD n keeps the parts whose ``mm_max_lod`` >= n (small greebles such as bolts
disappear first), then collapse-decimates to the target triangle count. UVs,
material assignments, skin weights and scale are preserved; silhouette
preservation is measured as a two-sided surface deviation against LOD0.
"""

import math
import os

import bpy
from mathutils.bvhtree import BVHTree

from core import scene as scn
from core.errors import PipelineError
from materials import baking
from utilities.meshkit import apply_modifiers

from . import assembly


def _tris(objs):
    return sum(scn.triangle_count(o) for o in objs if o.type == "MESH")


def decimate(obj, ratio, min_edge=1e-5):
    if ratio >= 0.999:
        return
    # Armature modifiers are removed first so only the decimation is applied
    # (vertex groups survive and are interpolated by the collapse).
    arm_mods = [(m.name, m.object) for m in obj.modifiers if m.type == "ARMATURE"]
    for name, _ in arm_mods:
        obj.modifiers.remove(obj.modifiers[name])
    mod = obj.modifiers.new("Decimate", "DECIMATE")
    mod.decimate_type = "COLLAPSE"
    mod.ratio = max(0.02, ratio)
    mod.use_collapse_triangulate = True
    apply_modifiers(obj)
    _remove_degenerate(obj, min_edge)
    for name, target in arm_mods:
        m = obj.modifiers.new(name, "ARMATURE")
        m.object = target
        m.use_vertex_groups = True
        m.use_bone_envelopes = False


def _remove_degenerate(obj, min_edge=1e-5):
    """Aggressive collapses leave zero-area triangles (the glTF exporter
    silently drops them) and long slivers whose UVs collapse to a line (zero
    tangents). Collapsing edges below ``min_edge`` removes both."""
    import bmesh
    bm = bmesh.new()
    bm.from_mesh(obj.data)
    bmesh.ops.dissolve_degenerate(bm, dist=min_edge, edges=list(bm.edges))
    bad = {f for f in bm.faces if f.calc_area() < 1e-12}
    # Collapses can fold a strip into faces over the same three vertices:
    # back-to-back pairs enclose nothing (drop both), same-winding copies keep one.
    groups = {}
    for f in bm.faces:
        if f not in bad:
            # Keyed by (rounded) positions: the exporter welds coincident
            # vertices, so overlapping faces on different vertices also collapse.
            key = frozenset(tuple(round(c, 5) for c in v.co) for v in f.verts)
            groups.setdefault(key, []).append(f)
    for faces in groups.values():
        if len(faces) < 2:
            continue
        n0 = faces[0].normal
        if all(f.normal.dot(n0) > 0.0 for f in faces[1:]):
            bad.update(faces[1:])
        else:
            bad.update(faces)
    if bad:
        bmesh.ops.delete(bm, geom=list(bad), context="FACES")
    loose = [v for v in bm.verts if not v.link_faces]
    if loose:
        bmesh.ops.delete(bm, geom=loose, context="VERTS")
    ngons = [f for f in bm.faces if len(f.verts) > 3]
    if ngons:
        bmesh.ops.triangulate(bm, faces=ngons, quad_method="BEAUTY", ngon_method="BEAUTY")
    bm.to_mesh(obj.data)
    bm.free()
    obj.data.update()


def _reshade(obj, angle_deg=35.0):
    """Hard-surface LODs: collapses interpolate custom split normals until a
    corner can end up nearly perpendicular to its face (zero MikkTSpace
    tangent). Re-derive smooth/sharp shading from the decimated geometry."""
    me = obj.data
    if "custom_normal" in me.attributes:
        me.attributes.remove(me.attributes["custom_normal"])
    me.shade_smooth()
    me.set_sharp_from_angle(angle=math.radians(angle_deg))


def _bvh(objs):
    import bmesh
    bm = bmesh.new()
    for o in objs:
        tmp = o.data.copy()
        tmp.transform(o.matrix_world)
        bm.from_mesh(tmp)
        bpy.data.meshes.remove(tmp)
    tree = BVHTree.FromBMesh(bm)
    verts = [v.co.copy() for v in bm.verts]
    bm.free()
    return tree, verts


def deviation(ref_objs, lod_objs, max_samples=6000):
    """Symmetric max surface deviation (meters) between two object sets."""
    t_ref, v_ref = _bvh(ref_objs)
    t_lod, v_lod = _bvh(lod_objs)
    worst = 0.0
    for verts, tree in ((v_lod, t_ref), (v_ref, t_lod)):
        step = max(1, len(verts) // max_samples)
        for v in verts[::step]:
            hit = tree.find_nearest(v)
            if hit[0] is not None:
                worst = max(worst, hit[3])
    return worst


def largest_island(obj):
    """Diagonal of the biggest connected piece of ``obj`` (world space)."""
    import bmesh
    bm = bmesh.new()
    bm.from_mesh(obj.data)
    bm.transform(obj.matrix_world)
    seen = set()
    best = 0.0
    for v in bm.verts:
        if v in seen:
            continue
        stack = [v]
        seen.add(v)
        lo = [1e9] * 3
        hi = [-1e9] * 3
        while stack:
            x = stack.pop()
            for i in range(3):
                lo[i] = min(lo[i], x.co[i])
                hi[i] = max(hi[i], x.co[i])
            for e in x.link_edges:
                o = e.other_vert(x)
                if o not in seen:
                    seen.add(o)
                    stack.append(o)
        best = max(best, sum((hi[i] - lo[i]) ** 2 for i in range(3)) ** 0.5)
    bm.free()
    return best


def lod_material(ctx, level, scale):
    """Downscaled copy of the baked texture set for LOD ``level``."""
    size = max(64, int(ctx.texture_size * scale))
    out = {}
    for key, path in ctx.texture_paths.items():
        img = bpy.data.images.load(path, check_existing=False)
        img.scale(size, size)
        root, ext = os.path.splitext(path)
        p = f"{root}_lod{level}{ext}"
        img.file_format = "JPEG" if ext == ".jpg" else "PNG"
        img.save(filepath=p, quality=int(ctx.cfg["textures"]["jpeg_quality"]))
        bpy.data.images.remove(img)
        out[key] = p
    return baking.build_final_material(f"M_{ctx.name}_lod{level}", out["base_color"], out["orm"], out["normal"],
                                       out.get("emissive")), size


def _large_islands(obj, min_size):
    """(copy of ``obj`` holding only islands whose world bounding-box diagonal
    is at least ``min_size`` or None, largest removed island size). Detail
    parts past their max LOD lose their small islands; big pieces never
    disappear."""
    import bmesh
    bm = bmesh.new()
    bm.from_mesh(obj.data)
    bm.verts.ensure_lookup_table()
    mw = obj.matrix_world
    seen = set()
    small_faces = []
    kept = 0
    removed = 0.0
    for v0 in bm.verts:
        if v0 in seen or not v0.link_faces:
            continue
        stack, island = [v0], []
        seen.add(v0)
        while stack:
            x = stack.pop()
            island.append(x)
            for e in x.link_edges:
                o = e.other_vert(x)
                if o not in seen:
                    seen.add(o)
                    stack.append(o)
        pts = [mw @ v.co for v in island]
        lo = [min(p[i] for p in pts) for i in range(3)]
        hi = [max(p[i] for p in pts) for i in range(3)]
        size = sum((hi[i] - lo[i]) ** 2 for i in range(3)) ** 0.5
        if size < min_size:
            small_faces.extend({f for v in island for f in v.link_faces})
            removed = max(removed, size)
        else:
            kept += 1
    if not kept:
        bm.free()
        return None, removed
    dup = obj.copy()
    dup.data = obj.data.copy()
    scn.link(dup)
    if small_faces:
        bmesh.ops.delete(bm, geom=list(set(small_faces)), context="FACES")
        loose = [v for v in bm.verts if not v.link_faces]
        if loose:
            bmesh.ops.delete(bm, geom=loose, context="VERTS")
    bm.to_mesh(dup.data)
    bm.free()
    dup["mm_max_lod"] = 99
    return dup, removed


def build(ctx, parts, final_objs):
    """Create LOD objects for every configured level; returns list of dicts."""
    ratios = ctx.lod_ratios
    if not ratios:
        return []
    lcfg = ctx.cfg["lod"]
    lod0_tris = _tris(final_objs)
    lo, hi = scn.world_bounds(final_objs)
    diag = (hi - lo).length
    results = []
    min_keep = lcfg["max_dropped_part_ratio"] * diag
    for level, ratio in enumerate(ratios, start=1):
        keep, temps, removed = [], [], []
        for p in parts:
            if int(p.get("mm_max_lod", 99)) >= level:
                keep.append(p)
            else:
                big, gone = _large_islands(p, min_keep)
                removed.append((gone, p.get("mm_part", p.name)))
                if big is not None:
                    keep.append(big)
                    temps.append(big)
        if not keep:
            raise PipelineError(f"LOD{level}: every part was dropped")
        dups = assembly.duplicate(keep, f"__lod{level}")
        root, meshes, attachments = assembly.assemble(ctx, dups, suffix=f"_lod{level}")
        objs = meshes + attachments
        target = max(lcfg["min_triangles"], int(lod0_tris * ratio))
        current = _tris(objs)
        if current > target:
            r = target / float(current)
            for o in objs:
                decimate(o, r, min_edge=lcfg.get("min_edge_ratio", 0.0015) * diag)
                if ctx.character is None:
                    _reshade(o)
                if ctx.armature is not None and o.vertex_groups:
                    # Collapses interpolate weights: re-limit influences.
                    from rigging.worker_rig import clean_weights
                    dcfg = ctx.cfg["deformation"]
                    clean_weights(o, dcfg["max_influences"], dcfg["min_weight"])
        tris = _tris(objs)
        if tris > target * 1.25:
            ctx.warn("LOD_TRIANGLE_TARGET_MISSED", f"LOD{level} has {tris} tris (target {target})")
        scale = lcfg["texture_scale"][min(level - 1, len(lcfg["texture_scale"]) - 1)]
        mat, tex = lod_material(ctx, level, scale)
        for o in objs:
            for i, slot in enumerate(o.material_slots):
                if slot.material is not None and slot.material.get("mm_kind") == "baked":
                    o.data.materials[i] = mat
        # Decimation error is measured against the parts kept at this level;
        # dropped parts must be small details (checked below).
        dev = deviation(keep, objs)
        dropped = [p for p in parts if int(p.get("mm_max_lod", 99)) < level]
        biggest, biggest_part = max(removed) if removed else (0.0, "")
        for t in temps:
            me = t.data
            bpy.data.objects.remove(t, do_unlink=True)
            if me.users == 0:
                bpy.data.meshes.remove(me)
        max_ratio = lcfg["max_deviation_ratio"][min(level - 1, len(lcfg["max_deviation_ratio"]) - 1)]
        results.append({"level": level, "objects": objs, "root": root, "triangles": tris, "target": target,
                        "deviation_m": round(dev, 4), "deviation_ratio": round(dev / max(diag, 1e-6), 5),
                        "max_deviation_ratio": max_ratio, "texture": tex,
                        "dropped_parts": len(dropped), "largest_dropped_ratio": round(biggest / max(diag, 1e-6), 4),
                        "largest_dropped_part": biggest_part})
    return results
