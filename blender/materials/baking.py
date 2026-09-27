"""Bake the procedural library materials of an asset into one compact PBR
texture set (baseColor, ORM, normal) and replace them with a single
glTF-friendly material.

Pass order matters:
1. AO (multi-sample, ray traced) -> also fed back into material graphs as the
   grime/cavity mask so the remaining passes converge at one sample.
2. NORMAL (tangent space, OpenGL/+Y as glTF and Godot expect).
3. EMIT tricks for base color, roughness and metallic (a diffuse-color bake
   would return black for metals).
"""

import os

import bpy
import numpy as np

from core import scene as scn
from core.errors import PipelineError

from .nodes import AO_NODE

TARGET_NODE = "mm_bake_target"


def _new_image(name, size, non_color):
    img = bpy.data.images.new(name, size, size, alpha=False, float_buffer=False)
    img.colorspace_settings.name = "Non-Color" if non_color else "sRGB"
    img.generated_color = (0.5, 0.5, 1.0, 1.0) if name.endswith("_normal") else (0.0, 0.0, 0.0, 1.0)
    return img


def _materials(objs):
    seen = []
    for o in objs:
        for slot in o.material_slots:
            m = slot.material
            if m is not None and m.get("mm_baked", True) and m not in seen:
                seen.append(m)
    return seen


def _principled(mat):
    for n in mat.node_tree.nodes:
        if n.type == "BSDF_PRINCIPLED":
            return n
    raise PipelineError(f"material {mat.name} has no Principled BSDF")


def _output(mat):
    for n in mat.node_tree.nodes:
        if n.type == "OUTPUT_MATERIAL" and n.is_active_output:
            return n
    for n in mat.node_tree.nodes:
        if n.type == "OUTPUT_MATERIAL":
            return n
    raise PipelineError(f"material {mat.name} has no output node")


def _set_target(mats, img):
    for m in mats:
        nt = m.node_tree
        node = nt.nodes.get(TARGET_NODE)
        if node is None:
            node = nt.nodes.new("ShaderNodeTexImage")
            node.name = TARGET_NODE
            node.label = TARGET_NODE
        node.image = img
        for n in nt.nodes:
            n.select = False
        node.select = True
        nt.nodes.active = node


def _emit_link(mat, socket_name):
    nt = mat.node_tree
    bsdf = _principled(mat)
    out = _output(mat)
    em = nt.nodes.new("ShaderNodeEmission")
    em.inputs["Strength"].default_value = 1.0
    src = bsdf.inputs[socket_name]
    if src.is_linked:
        nt.links.new(src.links[0].from_socket, em.inputs["Color"])
    else:
        v = src.default_value
        if hasattr(v, "__len__"):
            em.inputs["Color"].default_value = (v[0], v[1], v[2], 1.0)
        else:
            em.inputs["Color"].default_value = (v, v, v, 1.0)
    nt.links.new(em.outputs["Emission"], out.inputs["Surface"])
    return em


def _restore_bsdf(mat, em):
    nt = mat.node_tree
    nt.links.new(_principled(mat).outputs["BSDF"], _output(mat).inputs["Surface"])
    nt.nodes.remove(em)


def _bake(kind, margin, samples, **kw):
    scene = bpy.context.scene
    scene.cycles.samples = samples
    r = bpy.ops.object.bake(type=kind, margin=margin, margin_type="EXTEND", use_clear=True,
                            target="IMAGE_TEXTURES", use_selected_to_active=False, **kw)
    if "FINISHED" not in r:
        raise PipelineError(f"Cycles bake pass {kind} failed: {r}")


def _pixels(img):
    arr = np.empty(img.size[0] * img.size[1] * 4, dtype=np.float32)
    img.pixels.foreach_get(arr)
    return arr.reshape(img.size[1], img.size[0], 4)


def _save(img, path, fmt, quality):
    img.file_format = fmt
    img.filepath_raw = path
    img.save(filepath=path, quality=quality)
    if not os.path.isfile(path) or os.path.getsize(path) == 0:
        raise PipelineError(f"failed to write texture {path}")


def gltf_output_group():
    from io_scene_gltf2.blender.com.material_helpers import create_settings_group, get_gltf_node_name
    name = get_gltf_node_name()
    grp = bpy.data.node_groups.get(name)
    if grp is None:
        grp = create_settings_group(name)
    return grp


def build_final_material(name, base_path, orm_path, normal_path):
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    mat.use_backface_culling = True  # closed game meshes: export doubleSided=false
    nt = mat.node_tree
    nodes, links = nt.nodes, nt.links
    nodes.clear()
    out = nodes.new("ShaderNodeOutputMaterial")
    bsdf = nodes.new("ShaderNodeBsdfPrincipled")
    links.new(bsdf.outputs["BSDF"], out.inputs["Surface"])

    def tex(path, non_color):
        img = bpy.data.images.load(path, check_existing=False)
        img.colorspace_settings.name = "Non-Color" if non_color else "sRGB"
        n = nodes.new("ShaderNodeTexImage")
        n.image = img
        n.interpolation = "Linear"
        return n

    base = tex(base_path, False)
    links.new(base.outputs["Color"], bsdf.inputs["Base Color"])
    orm = tex(orm_path, True)
    sep = nodes.new("ShaderNodeSeparateColor")
    links.new(orm.outputs["Color"], sep.inputs["Color"])
    links.new(sep.outputs["Green"], bsdf.inputs["Roughness"])
    links.new(sep.outputs["Blue"], bsdf.inputs["Metallic"])
    grp = nodes.new("ShaderNodeGroup")
    grp.node_tree = gltf_output_group()
    links.new(sep.outputs["Red"], grp.inputs["Occlusion"])
    nrm = tex(normal_path, True)
    nmap = nodes.new("ShaderNodeNormalMap")
    links.new(nrm.outputs["Color"], nmap.inputs["Color"])
    links.new(nmap.outputs["Normal"], bsdf.inputs["Normal"])
    bsdf.inputs["Specular IOR Level"].default_value = 0.5
    mat["mm_key"] = name
    mat["mm_kind"] = "baked"
    mat["mm_baked"] = False
    return mat


def bake_asset(objs, size, stem, work_dir, cfg, ao_distance):
    """Bake all baked-library materials on ``objs`` and return texture info."""
    tcfg = cfg["textures"]
    margin = int(tcfg["bake_margin_px"].get(str(size), max(4, size // 128)))
    mats = _materials(objs)
    if not mats:
        raise PipelineError(f"{stem}: no bakeable materials on {[o.name for o in objs]}")
    scn.select_only(objs, objs[0])
    scene = bpy.context.scene
    scene.world.light_settings.distance = ao_distance

    img_ao = _new_image(f"{stem}_ao", size, True)
    img_nrm = _new_image(f"{stem}_normal", size, True)
    img_col = _new_image(f"{stem}_basecolor", size, False)
    img_rgh = _new_image(f"{stem}_rough", size, True)
    img_met = _new_image(f"{stem}_metal", size, True)

    _set_target(mats, img_ao)
    _bake("AO", margin, int(tcfg["ao_samples"]))
    for m in mats:
        n = m.node_tree.nodes.get(AO_NODE)
        if n is not None:
            n.image = img_ao

    _set_target(mats, img_nrm)
    _bake("NORMAL", margin, 1, normal_space="TANGENT", normal_r="POS_X", normal_g="POS_Y", normal_b="POS_Z")

    for img, sock in ((img_col, "Base Color"), (img_rgh, "Roughness"), (img_met, "Metallic")):
        _set_target(mats, img)
        emitters = [(m, _emit_link(m, sock)) for m in mats]
        try:
            _bake("EMIT", margin, 1)
        finally:
            for m, em in emitters:
                _restore_bsdf(m, em)

    os.makedirs(work_dir, exist_ok=True)
    ao = _pixels(img_ao)
    rg = _pixels(img_rgh)
    mt = _pixels(img_met)
    orm = np.ones_like(ao)
    orm[..., 0] = ao[..., 0]
    orm[..., 1] = np.clip(rg[..., 0], 0.03, 1.0)
    orm[..., 2] = mt[..., 0]
    img_orm = _new_image(f"{stem}_orm", size, True)
    img_orm.pixels.foreach_set(orm.ravel())

    q = int(tcfg["jpeg_quality"])
    ext = {"JPEG": ".jpg", "PNG": ".png"}
    paths = {}
    for key, img, fmt in (("base_color", img_col, tcfg["base_color_format"]),
                          ("orm", img_orm, tcfg["orm_format"]),
                          ("normal", img_nrm, tcfg["normal_format"])):
        p = os.path.join(work_dir, f"{stem}_{key}{ext[fmt]}")
        _save(img, p, fmt, q)
        paths[key] = p
    stats = {
        "ao_mean": float(ao[..., 0].mean()),
        "metallic_mean": float(mt[..., 0].mean()),
        "roughness_mean": float(rg[..., 0].mean()),
    }
    for img in (img_ao, img_nrm, img_col, img_rgh, img_met, img_orm):
        bpy.data.images.remove(img)
    return paths, stats


def replace_with_baked(objs, final_mat):
    """Swap every baked-library slot for the single baked material."""
    for o in objs:
        me = o.data
        for i, slot in enumerate(o.material_slots):
            m = slot.material
            if m is not None and m.get("mm_kind") != "baked" and m.get("mm_baked", True):
                me.materials[i] = final_mat
        _merge_duplicate_slots(o)


def _merge_duplicate_slots(obj):
    me = obj.data
    mats = list(me.materials)
    uniq = []
    remap = {}
    for i, m in enumerate(mats):
        if m not in uniq:
            uniq.append(m)
        remap[i] = uniq.index(m)
    if len(uniq) == len(mats):
        return
    idx = np.empty(len(me.polygons), dtype=np.int32)
    me.polygons.foreach_get("material_index", idx)
    lut = np.array([remap[i] for i in range(len(mats))], dtype=np.int32)
    idx = lut[idx]
    me.materials.clear()
    for m in uniq:
        me.materials.append(m)
    me.polygons.foreach_set("material_index", idx)
    me.update()
