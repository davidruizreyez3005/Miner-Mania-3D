"""Per-asset stage pipeline.

    generate -> rig -> animate -> optimize (clean, UV, bake) -> collision -> LOD
             -> validate (pre-export) -> export -> post-export GLB validation

Any failure raises; the asset is marked failed, its partial outputs are
deleted and the build exits non-zero. Warnings pass only when their code is
listed in pipeline_config.json ``validation.allowed_warning_codes``.
"""

import glob
import hashlib
import os
import time
import traceback

import bpy

from . import log, paths
from . import scene as scn
from .context import BuildContext
from .errors import AssetBuildError, PipelineError, ValidationFailed, ValidationIssue


class AssetResult:
    def __init__(self, defn):
        self.defn = defn
        self.id = defn.id
        self.category = defn.category
        self.status = "pending"
        self.error = None
        self.failed_stage = None
        self.outputs = []
        self.warnings = []
        self.timings = {}
        self.metadata = {}

    def as_dict(self):
        return {"id": self.id, "category": self.category, "status": self.status, "error": self.error,
                "failed_stage": self.failed_stage, "warnings": self.warnings, "timings": self.timings,
                "outputs": [o.__dict__ for o in self.outputs]}


def _gate(ctx, stage, issues):
    allowed = set(ctx.cfg["validation"]["allowed_warning_codes"])
    blocking = []
    for i in issues:
        i.asset_id = ctx.name
        i.check = stage
        if i.severity == "error" or i.code not in allowed:
            if i.severity == "warning":
                i.message += " (warning not allowed by pipeline_config.json)"
            blocking.append(i)
            log.error(f"{stage}: {i.code}: {i.message}")
        else:
            log.warn(f"{stage}: {i.code}: {i.message}")
            ctx.warnings.append({"code": i.code, "message": i.message, "stage": stage, "state": ctx.state})
    if blocking:
        raise ValidationFailed(ctx.name, stage, blocking)
    ctx.record.checks[stage] = "passed"


def _sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


# ---------------------------------------------------------------- stages

def stage_generate(ctx, gen):
    gen(ctx)
    ctx.finalize_geos()
    render = [o for o in ctx.objects if o.type == "MESH"]
    if not render:
        raise PipelineError("generator produced no render meshes")
    for o in render:
        if len(o.data.polygons) == 0:
            raise PipelineError(f"generator produced empty mesh {o.name}")


def stage_rig(ctx):
    if ctx.character is not None:
        from rigging import worker_rig
        worker_rig.finalize(ctx)
    elif ctx.bones:
        from rigging import mech_rig
        mech_rig.build(ctx)


def stage_animate(ctx):
    if ctx.character is not None and ctx.character.get("animate", True):
        from animation import library
        library.apply_worker_library(ctx)
    elif ctx.clips:
        from animation import machine_anim
        machine_anim.bake_clips(ctx)


def _clean_parts(parts):
    import bmesh
    from utilities.meshkit import apply_modifiers
    for o in parts:
        non_arm = [m for m in o.modifiers if m.type != "ARMATURE"]
        if non_arm:
            apply_modifiers(o, only_types={m.type for m in non_arm})
        bm = bmesh.new()
        bm.from_mesh(o.data)
        loose = [v for v in bm.verts if not v.link_faces]
        if loose:
            bmesh.ops.delete(bm, geom=loose, context="VERTS")
        loose_e = [e for e in bm.edges if not e.link_faces]
        if loose_e:
            bmesh.ops.delete(bm, geom=loose_e, context="EDGES")
        bmesh.ops.dissolve_degenerate(bm, dist=1e-7, edges=list(bm.edges))
        tiny = [f for f in bm.faces if f.calc_area() < 1e-10]
        if tiny:
            bmesh.ops.delete(bm, geom=tiny, context="FACES")
            loose = [v for v in bm.verts if not v.link_faces]
            if loose:
                bmesh.ops.delete(bm, geom=loose, context="VERTS")
        bm.to_mesh(o.data)
        bm.free()
        o.data.update()


def _split_non_baked(parts):
    """Faces using factor-only materials (glass, emissive) move to their own
    objects so they do not consume atlas space."""
    import bmesh
    out = []
    for o in parts:
        me = o.data
        flags = [bool(s.material is not None and s.material.get("mm_baked", True)) for s in o.material_slots]
        if all(flags) or not any(flags):
            out.append(o)
            continue
        twin = o.copy()
        twin.data = me.copy()
        twin.name = o.name + "__fx"
        scn.link(twin)
        for obj, keep_baked in ((o, True), (twin, False)):
            bm = bmesh.new()
            bm.from_mesh(obj.data)
            kill = [f for f in bm.faces if flags[f.material_index] != keep_baked]
            bmesh.ops.delete(bm, geom=kill, context="FACES")
            bm.to_mesh(obj.data)
            bm.free()
            obj.data.update()
        out.extend([o, twin])
    return out


def stage_optimize(ctx):
    from materials import baking, uv
    t0 = time.time()
    parts = [o for o in ctx.objects if o.type == "MESH"]
    _clean_parts(parts)
    parts = _split_non_baked(parts)
    t_clean = time.time() - t0
    baked = [o for o in parts if any(s.material is not None and s.material.get("mm_baked", True)
                                      for s in o.material_slots)]
    if not baked:
        raise PipelineError("asset has no bakeable (textured) surfaces")
    angle = 60.0 if ctx.character is not None else 52.0
    pad_px = int(ctx.cfg["textures"]["bake_margin_px"].get(str(ctx.texture_size), 8))
    # Island gap of ~half the bake padding: bleeding stays inside each island's
    # own dilation while small detail islands waste less atlas space.
    margin = max(ctx.cfg["uv"]["island_margin"], 0.5 * pad_px / float(ctx.texture_size))
    t1 = time.time()
    uv.unwrap_atlas(baked, margin=margin, angle_limit_deg=angle)
    t_uv = time.time() - t1
    ctx.uv_stats = uv.uv_stats(baked, ctx.texture_size)
    t_stats = time.time() - t1 - t_uv
    lo, hi = scn.world_bounds(parts)
    size = max(hi[i] - lo[i] for i in range(3))
    ao_dist = max(0.06, min(1.2, 0.12 * size)) if ctx.character is None else 0.2
    t2 = time.time()
    baking.BAKE_TIMINGS.clear()
    tex_paths, stats = baking.bake_asset(baked, ctx.texture_size, ctx.name, ctx.work_dir, ctx.cfg, ao_dist)
    log.info(f"optimize timings: clean {t_clean:.1f}s uv {t_uv:.1f}s uv_stats {t_stats:.1f}s "
             f"bake {time.time() - t2:.1f}s {dict(baking.BAKE_TIMINGS)}")
    ctx.texture_paths = tex_paths
    mat = baking.build_final_material(f"M_{ctx.name}", tex_paths["base_color"], tex_paths["orm"], tex_paths["normal"])
    baking.replace_with_baked(baked, mat)
    ctx.metadata["bake"] = {k: round(v, 4) for k, v in stats.items()}
    ctx.parts = parts
    ctx.render_bounds = (lo, hi)


def stage_collision(ctx):
    from exporters import collision
    ctx.collision_objects = collision.build(ctx) if ctx.defn.collision != "none" else []
    lo, hi = ctx.render_bounds
    _gate(ctx, "collision", collision.validate(ctx, ctx.collision_objects, lo, hi))


def stage_lod(ctx):
    from exporters import assembly, lod
    ctx.lod_results = lod.build(ctx, ctx.parts, ctx.parts)
    root, meshes, attachments = assembly.assemble(ctx, ctx.parts)
    ctx.root = root
    ctx.final_meshes = meshes
    ctx.attachments = attachments
    ctx.socket_objects = assembly.add_sockets(ctx, root)


def stage_validate(ctx):
    from validators import mesh_validation as mv
    issues = []
    finals = ctx.final_meshes + ctx.attachments
    issues += mv.validate_meshes(ctx, finals)
    issues += mv.validate_uv(ctx)
    issues += mv.validate_transforms(ctx, finals + ([ctx.armature] if ctx.armature else []))
    lo, hi = scn.world_bounds(finals)
    sc_issues, dims = mv.validate_scale(ctx, lo, hi)
    issues += sc_issues
    tris = sum(scn.triangle_count(o) for o in finals)
    b = ctx.budget
    hard = int(b["triangles"][1] * (1.0 + ctx.cfg["budget_policy"]["max_overshoot_ratio"]))
    if tris > hard:
        issues.append(ValidationIssue("error", "TRIANGLE_BUDGET", f"{tris} tris > hard limit {hard} ({ctx.defn.budget})"))
    elif tris > b["triangles"][1]:
        issues.append(ValidationIssue("warning", "BUDGET_OVER_TARGET", f"{tris} tris above target {b['triangles'][1]}"))
    if tris < b["triangles"][0]:
        issues.append(ValidationIssue("warning", "BUDGET_BELOW_MIN", f"{tris} tris below {b['triangles'][0]}"))
    for r in ctx.lod_results:
        if r["triangles"] >= tris:
            issues.append(ValidationIssue("error", "LOD_NOT_REDUCED", f"LOD{r['level']} ({r['triangles']}) >= LOD0 ({tris})"))
        if r["largest_dropped_ratio"] > ctx.cfg["lod"]["max_dropped_part_ratio"]:
            issues.append(ValidationIssue("error", "LOD_DROPPED_LARGE_PART",
                                          f"LOD{r['level']} dropped a part spanning {r['largest_dropped_ratio']:.2f} of the "
                                          f"asset diagonal (only small details may be removed)"))
        if r["deviation_ratio"] > r["max_deviation_ratio"]:
            issues.append(ValidationIssue("error", "LOD_SILHOUETTE",
                                          f"LOD{r['level']} deviates {r['deviation_m'] * 100:.1f} cm "
                                          f"({r['deviation_ratio']:.4f} of diagonal > {r['max_deviation_ratio']})"))
    if ctx.armature is not None:
        from rigging import rig_validation
        issues += rig_validation.validate(ctx)
    if ctx.character is not None and ctx.character.get("animate", True):
        from animation import animation_validation
        issues += animation_validation.validate_actions(ctx)
    ctx.record.triangles = tris
    ctx.record.dimensions = [round(d, 4) for d in dims]
    ctx.record.uv = dict(ctx.uv_stats)
    _gate(ctx, "validate", issues)


def _out_dir(ctx):
    return paths.generated(ctx.category_cfg["output_dir"])


def stage_export(ctx):
    from exporters.gltf_export import export_glb, strip_internal_props
    cfg = ctx.cfg
    animated = bool(bpy.data.actions)
    main_objs = ([ctx.armature] if ctx.armature else []) + ctx.final_meshes + ctx.attachments + ctx.socket_objects
    lod_sets = [([ctx.armature] if ctx.armature else []) + r["objects"] for r in ctx.lod_results]
    everything = main_objs + [o for s in lod_sets for o in s] + ctx.collision_objects
    strip_internal_props(everything)
    root = ctx.root
    root["asset_id"] = ctx.name
    root["asset_category"] = ctx.defn.category
    root["pipeline_version"] = cfg["pipeline"]["version"]
    root["lod_count"] = len(ctx.lod_results)
    main_path = os.path.join(_out_dir(ctx), f"{ctx.name}.glb")
    export_glb(main_path, main_objs, cfg, animations=animated)
    ctx.record.model = paths.rel(main_path)
    ctx.record.lods = []
    ctx.record.lod_triangles = []
    lod_anim = animated and ctx.character is None
    for r, objs in zip(ctx.lod_results, lod_sets):
        p = paths.generated("lod", f"{ctx.name}_lod{r['level']}.glb")
        export_glb(p, objs, cfg, animations=lod_anim)
        ctx.record.lods.append({"level": r["level"], "model": paths.rel(p), "triangles": r["triangles"],
                                "deviation_m": r["deviation_m"], "texture": r["texture"]})
        ctx.record.lod_triangles.append(r["triangles"])
    if ctx.collision_objects:
        p = paths.generated("collisions", f"{ctx.name}_collision.glb")
        export_glb(p, ctx.collision_objects, cfg, animations=False)
        ctx.record.collision = paths.rel(p)
        ctx.record.collision_shapes = len(ctx.collision_objects)
    ctx.record.sockets = [s.name for s in ctx.sockets]
    ctx.record.texture_resolution = ctx.texture_size


def expectations(ctx, kind="main"):
    """Build GLB inspector expectations for this asset."""
    from core import config
    cfg = ctx.cfg
    b = ctx.budget
    exp = {
        "anim_cfg": cfg["animation"],
        "dims_min": ctx.category_cfg["dimensions_m"]["min"],
        "dims_max": ctx.category_cfg["dimensions_m"]["max"],
        "max_texture": ctx.texture_size,
        "max_materials": 4,
        "forbidden_node_patterns": [r"(?i)camera", r"(?i)^light", r"(?i)^ctrl[_.]", r"(?i)^mch[_.-]",
                                    r"(?i)debug", r"(?i)^ik[_.]", r"-colonly$", r"-convcolonly$"],
    }
    from validators.mesh_validation import origin_policy
    exp["origin"] = origin_policy(ctx)
    if ctx.defn.category == "tool":
        exp["dims_min"] = None
    if ctx.armature is not None:
        exp["kind"] = "skinned"
        bones = [bn.name for bn in ctx.armature.data.bones]
        exp["skeleton"] = bones
        exp["skeleton_parents"] = {bn.name: (bn.parent.name if bn.parent else ctx.name)
                                   for bn in ctx.armature.data.bones}
    if kind == "main":
        exp["triangles"] = [b["triangles"][0], int(b["triangles"][1] * (1 + cfg["budget_policy"]["max_overshoot_ratio"]))]
        exp["triangles_soft_max"] = b["triangles"][1]
        exp["max_file_mb"] = b["file_size_mb"]
        exp["required_nodes"] = [ctx.name] + [f"socket_{s.name}" for s in ctx.sockets]
        if ctx.character is not None and ctx.character.get("animate", True):
            spec = config.animation_spec()
            exp["animations"] = config.required_clip_names()
            exp["clips"] = spec["clips"]
            exp["grips"] = spec["grips"]
        elif ctx.clips:
            exp["animations"] = [c.name for c in ctx.clips]
            exp["clips"] = {c.name: {"loop": c.loop, "duration": c.duration, "feet": "none",
                                     "root_motion": {"type": "none"}} for c in ctx.clips}
        else:
            exp["no_animations"] = True
    elif kind == "lod":
        exp["max_file_mb"] = b["file_size_mb"]
        if not ctx.clips:
            exp["no_animations"] = True
    elif kind == "collision":
        exp = {"collision": True, "no_animations": True, "origin": "any", "allow_no_material": True}
    return exp


def stage_post_validate(ctx):
    from validators import glb_inspector
    issues = []
    rep = glb_inspector.inspect(os.path.join(paths.REPO_ROOT, ctx.record.model), expectations(ctx, "main"))
    for e in rep.errors:
        issues.append(ValidationIssue("error", e["code"], f"{os.path.basename(ctx.record.model)}: {e['message']}"))
    for w in rep.warnings:
        issues.append(ValidationIssue("warning", w["code"], f"{os.path.basename(ctx.record.model)}: {w['message']}"))
    st = rep.stats
    ctx.record.triangles = st.get("triangles", ctx.record.triangles)
    ctx.record.materials = st.get("materials", 0)
    ctx.record.textures = st.get("textures", 0)
    ctx.record.bones = st.get("bones", 0)
    ctx.record.skeleton = bool(st.get("bones"))
    ctx.record.animations = st.get("animations", [])
    ctx.record.animation_details = st.get("animation_details", {})
    ctx.record.dimensions = st.get("dimensions", ctx.record.dimensions)
    ctx.record.bounds_min = st.get("bounds_min", [])
    ctx.record.bounds_max = st.get("bounds_max", [])
    full = os.path.join(paths.REPO_ROOT, ctx.record.model)
    ctx.record.file_size = os.path.getsize(full)
    ctx.record.sha256 = _sha256(full)
    for lod in ctx.record.lods:
        r = glb_inspector.inspect(os.path.join(paths.REPO_ROOT, lod["model"]), expectations(ctx, "lod"))
        for e in r.errors:
            issues.append(ValidationIssue("error", e["code"], f"{os.path.basename(lod['model'])}: {e['message']}"))
        lod["sha256"] = _sha256(os.path.join(paths.REPO_ROOT, lod["model"]))
        if r.stats.get("triangles") != lod["triangles"]:
            issues.append(ValidationIssue("error", "LOD_TRIANGLE_MISMATCH",
                                          f"LOD{lod['level']} GLB has {r.stats.get('triangles')} tris, expected {lod['triangles']}"))
    if ctx.record.collision:
        r = glb_inspector.inspect(os.path.join(paths.REPO_ROOT, ctx.record.collision), expectations(ctx, "collision"))
        for e in r.errors:
            issues.append(ValidationIssue("error", e["code"], f"{os.path.basename(ctx.record.collision)}: {e['message']}"))
        names = r.stats.get("node_names", [])
        if not names or not all(n.endswith("-convcolonly") for n in names):
            issues.append(ValidationIssue("error", "COLLISION_NAMING", f"collision nodes must end with -convcolonly: {names}"))
    elif ctx.defn.collision != "none":
        issues.append(ValidationIssue("error", "COLLISION_MISSING", "collision file missing"))
    _gate(ctx, "post_validate", issues)
    ctx.record.validated = True


STAGE_ORDER = ("generate", "rig", "animate", "optimize", "collision", "lod", "validate", "export", "post_validate")


def remove_outputs(name):
    for sub in paths.GENERATED_SUBDIRS:
        for p in glob.glob(os.path.join(paths.GENERATED_DIR, sub, f"{name}.glb")) + \
                glob.glob(os.path.join(paths.GENERATED_DIR, sub, f"{name}_lod*.glb")) + \
                glob.glob(os.path.join(paths.GENERATED_DIR, sub, f"{name}_collision.glb")):
            os.remove(p)


def build_asset(defn, cfg, options):
    from generators import resolve
    from materials.library import MaterialLibrary
    result = AssetResult(defn)
    ctx = BuildContext(defn, cfg, MaterialLibrary, options)
    log.set_asset(defn.id)
    t0 = time.time()
    stage = "resolve"
    try:
        gen = resolve(defn.generator_name)
        for state in defn.states:
            stage = "reset"
            scn.reset_scene(cfg, defn.seed)
            ctx.begin_state(state)
            log.info(f"state '{state}' -> {ctx.name}")
            for stage in STAGE_ORDER:
                t = time.time()
                if stage == "generate":
                    stage_generate(ctx, gen)
                else:
                    globals()[f"stage_{stage}"](ctx)
                result.timings[stage] = round(result.timings.get(stage, 0.0) + time.time() - t, 3)
            result.outputs.append(ctx.record)
            log.info(f"OK {ctx.name}: {ctx.record.triangles} tris, {len(ctx.record.animations)} clips, "
                     f"{ctx.record.file_size / 1024:.0f} KiB")
        result.status = "ok"
    except ValidationFailed as exc:
        result.status = "failed"
        result.failed_stage = exc.stage
        result.error = str(exc)
    except PipelineError as exc:
        result.status = "failed"
        result.failed_stage = stage
        result.error = f"[{ctx.name if ctx.state else defn.id}] stage={stage}: {exc}"
    except Exception as exc:  # unexpected bug: still a hard failure with traceback
        result.status = "failed"
        result.failed_stage = stage
        result.error = f"[{defn.id}] stage={stage}: unexpected {type(exc).__name__}: {exc}"
        traceback.print_exc()
    finally:
        log.set_asset(None)
    result.warnings = list(ctx.warnings)
    result.metadata = dict(getattr(ctx, "metadata", {}) or {})
    result.timings["total"] = round(time.time() - t0, 3)
    if result.status != "ok":
        log.error(f"ERROR: {result.error}")
        for st in defn.states:
            remove_outputs(defn.output_name(st))
        result.outputs = []
    return result
