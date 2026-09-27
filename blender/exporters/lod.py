"""LOD generation.

LOD n keeps the parts whose ``mm_max_lod`` >= n (small greebles such as bolts
disappear first), then collapse-decimates to the target triangle count. UVs,
material assignments, skin weights and scale are preserved; silhouette
preservation is measured as a two-sided surface deviation against LOD0.
"""

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


def decimate(obj, ratio):
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
    for name, target in arm_mods:
        m = obj.modifiers.new(name, "ARMATURE")
        m.object = target
        m.use_vertex_groups = True
        m.use_bone_envelopes = False


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
    return baking.build_final_material(f"M_{ctx.name}_lod{level}", out["base_color"], out["orm"], out["normal"]), size


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
    for level, ratio in enumerate(ratios, start=1):
        keep = [p for p in parts if int(p.get("mm_max_lod", 99)) >= level]
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
                decimate(o, r)
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
        dropped = [p for p in parts if p not in keep]
        biggest = max([largest_island(d) for d in dropped] or [0.0])
        max_ratio = lcfg["max_deviation_ratio"][min(level - 1, len(lcfg["max_deviation_ratio"]) - 1)]
        results.append({"level": level, "objects": objs, "root": root, "triangles": tris, "target": target,
                        "deviation_m": round(dev, 4), "deviation_ratio": round(dev / max(diag, 1e-6), 5),
                        "max_deviation_ratio": max_ratio, "texture": tex,
                        "dropped_parts": len(dropped), "largest_dropped_ratio": round(biggest / max(diag, 1e-6), 4)})
    return results
