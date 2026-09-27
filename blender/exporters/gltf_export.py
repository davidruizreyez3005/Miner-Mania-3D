"""GLB export with Godot-oriented settings. Export failure is always fatal:
partial files are removed and an exception is raised."""

import os

import bpy

from core import log
from core import scene as scn
from core.errors import PipelineError
from validators.glb_inspector import GLB, GLBError

INTERNAL_PREFIX = "mm_"


def strip_internal_props(objs):
    """Remove pipeline bookkeeping properties so they do not leak into glTF extras."""
    seen = set()
    for o in objs:
        for key in [k for k in o.keys() if k.startswith(INTERNAL_PREFIX) or k.startswith("_")]:
            del o[key]
        datas = [o.data] if o.data is not None else []
        for d in datas:
            if id(d) in seen:
                continue
            seen.add(id(d))
            for key in [k for k in d.keys() if k.startswith(INTERNAL_PREFIX)]:
                del d[key]
            for m in getattr(d, "materials", []) or []:
                if m is None or id(m) in seen:
                    continue
                seen.add(id(m))
                for key in [k for k in m.keys() if k.startswith(INTERNAL_PREFIX)]:
                    del m[key]


def sanitize_names(objs):
    """Give every exported datablock a clean, deterministic name (no '.001')."""
    for o in objs:
        if o.data is None:
            continue
        want = o.name
        if o.data.name == want:
            continue
        clash = None
        coll = bpy.data.meshes if o.type == "MESH" else bpy.data.armatures if o.type == "ARMATURE" else None
        if coll is not None:
            clash = coll.get(want)
        if clash is not None and clash is not o.data:
            clash.name = want + "__renamed"
        o.data.name = want


def export_glb(path, objects, cfg, animations=False):
    objects = [o for o in objects if o is not None]
    if not objects:
        raise PipelineError(f"nothing to export for {path}")
    os.makedirs(os.path.dirname(path), exist_ok=True)
    if os.path.exists(path):
        os.remove(path)
    sanitize_names(objects)
    scn.select_only(objects, objects[0])
    q = int(cfg["export"]["jpeg_quality"])
    kwargs = dict(
        filepath=path,
        export_format="GLB",
        use_selection=True,
        use_visible=False,
        use_renderable=False,
        use_active_collection=False,
        export_yup=True,
        export_apply=False,
        export_texcoords=True,
        export_normals=True,
        export_tangents=True,
        export_materials="EXPORT",
        export_image_format="AUTO",
        export_jpeg_quality=q,
        export_image_quality=q,
        export_cameras=False,
        export_lights=False,
        export_extras=True,
        export_skins=True,
        export_influence_nb=int(cfg["export"]["influences"]),
        export_all_influences=False,
        export_def_bones=False,
        export_leaf_bone=False,
        export_hierarchy_flatten_bones=False,
        export_rest_position_armature=True,
        export_morph=False,
        export_attributes=False,
        export_vertex_color="NONE",
        export_draco_mesh_compression_enable=bool(cfg["export"]["draco"]),
        export_copyright=cfg["pipeline"]["copyright"],
        export_animations=animations,
    )
    if animations:
        kwargs.update(
            export_animation_mode="ACTIONS",
            export_anim_single_armature=True,
            export_force_sampling=True,
            export_frame_step=1,
            export_optimize_animation_size=True,
            export_optimize_animation_keep_anim_armature=True,
            export_reset_pose_bones=True,
            export_bake_animation=False,
            export_anim_slide_to_zero=True,
            export_negative_frame="SLIDE",
            export_merge_animation="ACTION",
        )
    try:
        result = bpy.ops.export_scene.gltf(**kwargs)
    except Exception as exc:  # the exporter raises plain Exceptions
        if os.path.exists(path):
            os.remove(path)
        raise PipelineError(f"glTF exporter raised for {os.path.basename(path)}: {exc}") from exc
    if "FINISHED" not in result:
        if os.path.exists(path):
            os.remove(path)
        raise PipelineError(f"glTF export of {os.path.basename(path)} returned {result}")
    if not os.path.isfile(path) or os.path.getsize(path) < 64:
        if os.path.exists(path):
            os.remove(path)
        raise PipelineError(f"glTF export produced no/empty file: {path}")
    try:
        GLB.load(path)
    except GLBError as exc:
        os.remove(path)
        raise PipelineError(f"exported file is not a valid GLB: {exc}") from exc
    log.info(f"exported {os.path.relpath(path)} ({os.path.getsize(path) / 1024:.0f} KiB)")
    return path
