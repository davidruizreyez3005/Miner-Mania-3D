"""GLB export with Godot-oriented settings. Export failure is always fatal:
partial files are removed and an exception is raised."""

import os
import types

import bpy

from core import log
from core import scene as scn
from core.errors import PipelineError, ToolchainError
from utilities import tangents
from validators.glb_inspector import GLB, GLBError

INTERNAL_PREFIX = "mm_"


class _TangentLoops:
    """Stands in for ``Mesh.loops`` in the exporter's tangent readers, which
    only call ``len()`` and ``foreach_get('tangent' / 'bitangent_sign')``."""

    def __init__(self, tangent, sign):
        self._data = {"tangent": tangent, "bitangent_sign": sign}

    def __len__(self):
        return len(self._data["bitangent_sign"])

    def foreach_get(self, prop, out):
        out[:] = self._data[prop].ravel()


def install_tangent_hook():
    """Make the glTF exporter write reproducible tangents.

    The exporter calls ``Mesh.calc_tangents()``, which is not reproducible
    above ~10k triangles (see utilities/tangents.py), then reads the loop
    tangents in two private methods; those now read
    ``tangents.loop_tangents`` instead. Rounding, axis conversion and vertex
    deduplication stay the exporter's own. The exporter version is pinned and
    checked by ``core.cli.verify_toolchain``; a changed exporter fails here.
    """
    from io_scene_gltf2.blender.exp import primitive_extract
    cls = primitive_extract.PrimitiveCreator
    if getattr(cls, "_mm_tangent_hook", False):
        return
    names = ("prepare_data", "_PrimitiveCreator__get_tangents", "_PrimitiveCreator__get_bitangent_signs")
    if not all(callable(getattr(cls, n, None)) for n in names):
        raise ToolchainError("glTF exporter internals changed: update install_tangent_hook in exporters/gltf_export.py")
    prepare, get_tangents, get_signs = (getattr(cls, n) for n in names)

    def prepare_data(self):
        prepare(self)
        self._mm_tangents = None
        if self.use_tangents:
            mesh = self.blender_mesh
            self._mm_tangents = _TangentLoops(*tangents.loop_tangents(mesh, mesh.uv_layers.active.name))

    def reading(fn):
        def run(self):
            loops = getattr(self, "_mm_tangents", None)
            if loops is None:
                return fn(self)
            mesh = self.blender_mesh
            self.blender_mesh = types.SimpleNamespace(loops=loops)
            try:
                return fn(self)
            finally:
                self.blender_mesh = mesh
        return run

    cls.prepare_data = prepare_data
    cls._PrimitiveCreator__get_tangents = reading(get_tangents)
    cls._PrimitiveCreator__get_bitangent_signs = reading(get_signs)
    cls._mm_tangent_hook = True


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
    install_tangent_hook()
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
