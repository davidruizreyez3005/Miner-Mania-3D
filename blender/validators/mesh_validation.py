"""Blender-side (pre-export) validation of final render meshes."""

import numpy as np

from core.errors import ValidationIssue

MAX_MATERIALS = 4


def validate_meshes(ctx, meshes):
    issues = []
    mats = set()
    for o in meshes:
        me = o.data
        n = len(me.vertices)
        co = np.empty(n * 3, dtype=np.float64)
        me.vertices.foreach_get("co", co)
        if not np.all(np.isfinite(co)):
            issues.append(ValidationIssue("error", "MESH_NAN", f"{o.name}: non-finite vertex coordinates"))
        used = np.zeros(n, dtype=bool)
        loops = np.empty(len(me.loops), dtype=np.int64)
        me.loops.foreach_get("vertex_index", loops)
        used[loops] = True
        loose = int((~used).sum())
        if loose:
            issues.append(ValidationIssue("error", "MESH_LOOSE_VERTS", f"{o.name}: {loose} loose vertices"))
        face_edges = set()
        for p in me.polygons:
            face_edges.update(p.edge_keys)
        loose_edges = sum(1 for e in me.edges if e.key not in face_edges)
        if loose_edges:
            issues.append(ValidationIssue("error", "MESH_LOOSE_EDGES", f"{o.name}: {loose_edges} loose edges"))
        areas = np.empty(len(me.polygons), dtype=np.float64)
        me.polygons.foreach_get("area", areas)
        degenerate = int((areas < 1e-10).sum())
        if degenerate:
            issues.append(ValidationIssue("error", "MESH_DEGENERATE_FACES", f"{o.name}: {degenerate} zero-area faces"))
        if not len(me.polygons):
            issues.append(ValidationIssue("error", "MESH_EMPTY", f"{o.name}: no faces"))
        for i, slot in enumerate(o.material_slots):
            if slot.material is None:
                issues.append(ValidationIssue("error", "MATERIAL_SLOT_EMPTY", f"{o.name}: slot {i} has no material"))
            else:
                mats.add(slot.material.name)
        idx = np.empty(len(me.polygons), dtype=np.int64)
        me.polygons.foreach_get("material_index", idx)
        if len(idx) and int(idx.max()) >= max(1, len(o.material_slots)):
            issues.append(ValidationIssue("error", "MATERIAL_INDEX", f"{o.name}: face references missing material slot"))
        for m in o.material_slots:
            mat = m.material
            if mat is not None and mat.get("mm_kind") not in ("baked", "glass", "emit"):
                issues.append(ValidationIssue("error", "MATERIAL_NOT_FINAL",
                                              f"{o.name}: material {mat.name} was not baked/finalized"))
    if len(mats) > MAX_MATERIALS:
        issues.append(ValidationIssue("error", "MATERIAL_COUNT", f"{len(mats)} materials > {MAX_MATERIALS}: {sorted(mats)}"))
    return issues


def validate_uv(ctx):
    ucfg = ctx.cfg["uv"]
    s = ctx.uv_stats
    issues = []
    if not s:
        return [ValidationIssue("error", "UV_MISSING", "no UV statistics recorded (asset not unwrapped)")]
    if s["out_of_range_uvs"]:
        issues.append(ValidationIssue("error", "UV_OUT_OF_RANGE", f"{s['out_of_range_uvs']} UVs outside 0..1"))
    if s["overlap_ratio"] > ucfg["max_overlap_ratio"]:
        issues.append(ValidationIssue("error", "UV_OVERLAP", f"overlap ratio {s['overlap_ratio']} > {ucfg['max_overlap_ratio']}"))
    # Coverage = exact summed UV triangle area (islands never overlap: checked
    # above). The 256-cell raster ratio undercounts thin islands (beams, rods)
    # and is reported only as a diagnostic.
    coverage = min(1.0, s["uv_area"])
    # Hard-surface categories pack many small islands (fasteners, rails), each
    # with a constant bake-padding gap, so their floor is lower; texel density
    # is still enforced below.
    floor = ucfg.get("min_used_area_by_category", {}).get(ctx.defn.category, ucfg["min_used_area"])
    # Explicit per-asset override (registry params) for shapes that unwrap as
    # one long island, e.g. a silo shell; recorded in the asset manifest.
    floor = float(ctx.param("uv_min_coverage", floor))
    if coverage < floor:
        issues.append(ValidationIssue("warning", "UV_LOW_COVERAGE",
                                      f"atlas coverage {coverage:.3f} (raster estimate {s['used_ratio']})"))
    dens = ctx.cfg["textures"]["min_texel_density_px_per_m"]
    want = dens.get(ctx.defn.category, dens["default"])
    if s["texel_density_median"] < want:
        issues.append(ValidationIssue("warning", "TEXEL_DENSITY_LOW",
                                      f"median texel density {s['texel_density_median']} px/m < {want}"))
    return issues


def origin_policy(ctx):
    pol = ctx.param("origin")
    if pol:
        return pol
    return {"tool": "grip", "equipment": "any"}.get(ctx.defn.category, "base")


def validate_scale(ctx, lo, hi):
    issues = []
    dims = [hi[i] - lo[i] for i in range(3)]
    lim = ctx.category_cfg["dimensions_m"]
    for axis, d, mn, mx in zip("XYZ", dims, lim["min"], lim["max"]):
        if d < mn - 1e-6 and not (axis != "Z" and ctx.defn.category in ("tool",)):
            issues.append(ValidationIssue("error", "SCALE_TOO_SMALL", f"{axis} size {d:.3f} m < {mn} m for {ctx.defn.category}"))
        if d > mx + 1e-6:
            issues.append(ValidationIssue("error", "SCALE_TOO_LARGE", f"{axis} size {d:.3f} m > {mx} m for {ctx.defn.category}"))
    exp = ctx.param("expected_dims")
    if exp:
        for axis, d, (mn, mx) in zip("XYZ", dims, exp):
            if not (mn <= d <= mx):
                issues.append(ValidationIssue("error", "SCALE_UNEXPECTED", f"{axis} size {d:.3f} m outside expected [{mn}, {mx}]"))
    pol = origin_policy(ctx)
    size = max(dims)
    if pol in ("base", "embedded"):
        if not (lo[0] - 0.05 * size <= 0 <= hi[0] + 0.05 * size and lo[1] - 0.05 * size <= 0 <= hi[1] + 0.05 * size):
            issues.append(ValidationIssue("error", "ORIGIN_OFF_FOOTPRINT", "origin is outside the asset footprint"))
        if pol == "base" and abs(lo[2]) > max(0.02, 0.02 * dims[2]):
            issues.append(ValidationIssue("error", "ORIGIN_NOT_ON_GROUND", f"lowest point z={lo[2]:.3f}; origin must be at the base"))
        if pol == "embedded" and not (-0.4 * dims[2] <= lo[2] <= 0.01):
            issues.append(ValidationIssue("error", "ORIGIN_EMBED", f"embedded base z={lo[2]:.3f} out of range"))
    elif pol == "grip":
        if not all(lo[i] <= 0.02 and hi[i] >= -0.02 for i in range(3)):
            issues.append(ValidationIssue("error", "ORIGIN_GRIP", "tool origin (grip) lies outside the tool"))
    return issues, dims


def validate_transforms(ctx, objs):
    from mathutils import Matrix
    issues = []
    for o in objs:
        if o.type == "ARMATURE":
            if o.matrix_world != Matrix.Identity(4):
                issues.append(ValidationIssue("error", "ARMATURE_TRANSFORM", f"{o.name}: armature must sit at the origin with unit scale"))
        elif o.type == "MESH" and o.parent_type != "BONE":
            m = o.matrix_world
            if any(abs(m[i][j] - (1.0 if i == j else 0.0)) > 1e-5 for i in range(4) for j in range(4)):
                issues.append(ValidationIssue("error", "MESH_TRANSFORM", f"{o.name}: transform not applied (non-identity)"))
    return issues
