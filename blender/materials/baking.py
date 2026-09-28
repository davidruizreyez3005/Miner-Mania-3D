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
from utilities import tangents

from .nodes import AO_NODE, EDGE_NODE

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


def _emission_link(mat):
    """Route the material's emitted radiance (colour x strength, clamped to
    the 0..1 texture range) into an Emission shader for the bake."""
    nt = mat.node_tree
    bsdf = _principled(mat)
    out = _output(mat)
    em = nt.nodes.new("ShaderNodeEmission")
    strength = float(bsdf.inputs["Emission Strength"].default_value)
    em.inputs["Strength"].default_value = min(1.0, max(0.0, strength))
    src = bsdf.inputs["Emission Color"]
    if src.is_linked:
        nt.links.new(src.links[0].from_socket, em.inputs["Color"])
    else:
        v = src.default_value
        em.inputs["Color"].default_value = (v[0], v[1], v[2], 1.0)
    nt.links.new(em.outputs["Emission"], out.inputs["Surface"])
    return em


def _emits(mat):
    bsdf = _principled(mat)
    strength = bsdf.inputs["Emission Strength"]
    colour = bsdf.inputs["Emission Color"]
    if strength.is_linked or colour.is_linked:
        return True
    return strength.default_value > 0.0 and max(colour.default_value[:3]) > 0.0


def _restore_bsdf(mat, em):
    nt = mat.node_tree
    nt.links.new(_principled(mat).outputs["BSDF"], _output(mat).inputs["Surface"])
    nt.nodes.remove(em)


def _edge_material(ao_distance):
    """Emits 1 - dot(bevelled normal, true normal), remapped: bright on convex
    and concave edges within the bevel radius (scaled with the asset)."""
    mat = bpy.data.materials.new("__edge_mask__")
    mat.use_nodes = True
    nt = mat.node_tree
    nt.nodes.clear()
    out = nt.nodes.new("ShaderNodeOutputMaterial")
    bev = nt.nodes.new("ShaderNodeBevel")
    bev.samples = 8
    bev.inputs["Radius"].default_value = max(0.004, min(0.02, ao_distance * 0.03))
    geo = nt.nodes.new("ShaderNodeNewGeometry")
    dot = nt.nodes.new("ShaderNodeVectorMath")
    dot.operation = "DOT_PRODUCT"
    nt.links.new(bev.outputs["Normal"], dot.inputs[0])
    nt.links.new(geo.outputs["Normal"], dot.inputs[1])
    rng = nt.nodes.new("ShaderNodeMapRange")
    rng.inputs["From Min"].default_value = 0.995
    rng.inputs["From Max"].default_value = 0.82
    nt.links.new(dot.outputs["Value"], rng.inputs["Value"])
    em = nt.nodes.new("ShaderNodeEmission")
    nt.links.new(rng.outputs["Result"], em.inputs["Color"])
    nt.links.new(em.outputs["Emission"], out.inputs["Surface"])
    return mat


BAKE_TIMINGS = {}


def _bake(kind, margin, samples, clear=True, **kw):
    import time
    scene = bpy.context.scene
    scene.cycles.samples = samples
    t = time.time()
    r = bpy.ops.object.bake(type=kind, margin=margin, margin_type="EXTEND", use_clear=clear,
                            target="IMAGE_TEXTURES", use_selected_to_active=False, **kw)
    BAKE_TIMINGS[kind] = round(BAKE_TIMINGS.get(kind, 0.0) + time.time() - t, 2)
    if "FINISHED" not in r:
        raise PipelineError(f"Cycles bake pass {kind} failed: {r}")


NORMAL_KW = dict(normal_space="TANGENT", normal_r="POS_X", normal_g="POS_Y", normal_b="POS_Z")


def _extend_margin(rgb, filled, passes):
    """Grow baked texels into their empty surroundings like Blender's EXTEND
    bake margin (imbuf ``IMB_filter_extend``): each pass, an empty texel with
    a filled 4-neighbour takes the weighted mean of its filled 8-neighbours
    (orthogonal weight 2, diagonal 1); coordinates clamp at the image border."""
    rgb = rgb.astype(np.float64)
    filled = filled.copy()
    h, w = filled.shape
    for _ in range(passes):
        pr = np.pad(rgb, ((1, 1), (1, 1), (0, 0)), mode="edge")
        pf = np.pad(filled, 1, mode="edge")
        acc = np.zeros_like(rgb)
        wsum = np.zeros((h, w))
        orth = np.zeros((h, w), dtype=bool)
        for dy in (-1, 0, 1):
            for dx in (-1, 0, 1):
                if dy == 0 and dx == 0:
                    continue
                f = pf[1 + dy:1 + dy + h, 1 + dx:1 + dx + w]
                wt = 2.0 if dy == 0 or dx == 0 else 1.0
                acc += pr[1 + dy:1 + dy + h, 1 + dx:1 + dx + w] * (f * wt)[..., None]
                wsum += f * wt
                if dy == 0 or dx == 0:
                    orth |= f
        grow = ~filled & orth
        if not grow.any():
            break
        rgb[grow] = acc[grow] / wsum[grow][:, None]
        filled |= grow
    return rgb


def _bake_normal(proxy, mats, img, margin):
    """Tangent-space normal pass.

    Cycles' MikkTSpace tangents are not reproducible on meshes above
    ``tangents.CHUNK_TRIS`` (see utilities/tangents.py), so a larger proxy is
    baked as chunk objects of whole components, which gives exactly the
    single-threaded tangents. The chunks bake together, without margin and
    without clearing, into an RGBA image pre-filled with a flat normal at
    alpha 0, so alpha marks the texels the bake wrote (Blender's own clear
    leaves alpha alone for single-object bakes); the margin is then grown the
    way Blender's EXTEND margin grows it.
    """
    chunks = tangents.face_chunks(proxy.data)
    if len(chunks) <= 1:
        _set_target(mats, img)
        _bake("NORMAL", margin, 1, **NORMAL_KW)
        return
    size = img.size[0]
    tmp = bpy.data.images.new(f"{img.name}_chunks", size, size, alpha=True, float_buffer=False)
    tmp.colorspace_settings.name = "Non-Color"
    tmp.pixels.foreach_set(np.tile(np.array([0.5, 0.5, 1.0, 0.0], dtype=np.float32), size * size))
    parts = []
    hidden = proxy.hide_render
    try:
        for i, faces in enumerate(chunks):
            me, _ = tangents.chunk_mesh(proxy.data, faces, f"__bake_chunk_{i}")
            o = bpy.data.objects.new(me.name, me)
            o.matrix_world = proxy.matrix_world.copy()
            scn.link(o)
            parts.append(o)
        proxy.hide_render = True
        scn.select_only(parts, parts[0])
        _set_target(mats, tmp)
        _bake("NORMAL", 0, 1, clear=False, **NORMAL_KW)
        px = _pixels(tmp)
        out = np.ones_like(px)
        out[..., :3] = _extend_margin(px[..., :3], px[..., 3] > 0.5, margin)
        img.pixels.foreach_set(out.ravel())
    finally:
        proxy.hide_render = hidden
        for o in parts:
            me = o.data
            bpy.data.objects.remove(o, do_unlink=True)
            bpy.data.meshes.remove(me)
        bpy.data.images.remove(tmp)
        scn.select_only([proxy], proxy)


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


def build_final_material(name, base_path, orm_path, normal_path, emissive_path=None):
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
    if emissive_path:
        emi = tex(emissive_path, False)
        links.new(emi.outputs["Color"], bsdf.inputs["Emission Color"])
        bsdf.inputs["Emission Strength"].default_value = 1.0
    mat["mm_key"] = name
    mat["mm_kind"] = "baked"
    mat["mm_baked"] = False
    return mat


def _joined_proxy(objs):
    """Temporary single-object copy of all parts sharing the atlas.

    Cycles bakes every selected object as a separate full-image pass, so a
    21-part character took ~8 s per pass; one joined proxy takes ~0.4 s.
    Modifiers are dropped (rest pose) and transforms baked in.
    """
    dups = []
    for o in objs:
        d = o.copy()
        d.data = o.data.copy()
        d.modifiers.clear()
        d.parent = None
        d.matrix_world = o.matrix_world.copy()
        scn.link(d)
        dups.append(d)
    if len(dups) > 1:
        scn.select_only(dups, dups[0])
        r = bpy.ops.object.join()
        if "FINISHED" not in r:
            raise PipelineError(f"could not join bake proxy: {r}")
    proxy = dups[0]
    proxy.name = "__bake_proxy__"
    return proxy


def bake_asset(objs, size, stem, work_dir, cfg, ao_distance):
    """Bake all baked-library materials on ``objs`` and return texture info."""
    tcfg = cfg["textures"]
    margin = int(tcfg["bake_margin_px"].get(str(size), max(4, size // 128)))
    mats = _materials(objs)
    if not mats:
        raise PipelineError(f"{stem}: no bakeable materials on {[o.name for o in objs]}")
    proxy = _joined_proxy(objs)
    # The originals must not be renderable while the coincident proxy bakes,
    # otherwise AO rays start inside duplicate surfaces (black, slow AO).
    hidden = [(o, o.hide_render) for o in objs]
    for o, _ in hidden:
        o.hide_render = True
    try:
        return _bake_passes(proxy, mats, size, stem, work_dir, tcfg, margin, ao_distance)
    finally:
        for o, state in hidden:
            o.hide_render = state
        mesh = proxy.data
        bpy.data.objects.remove(proxy, do_unlink=True)
        if mesh.users == 0:
            bpy.data.meshes.remove(mesh)


def _bake_passes(proxy, mats, size, stem, work_dir, tcfg, margin, ao_distance):
    scn.select_only([proxy], proxy)
    scene = bpy.context.scene
    scene.world.light_settings.distance = ao_distance

    img_ao = _new_image(f"{stem}_ao", size, True)
    img_nrm = _new_image(f"{stem}_normal", size, True)
    img_col = _new_image(f"{stem}_basecolor", size, False)
    img_rgh = _new_image(f"{stem}_rough", size, True)
    img_met = _new_image(f"{stem}_metal", size, True)

    # AO only needs geometry: bake it with one flat material on the proxy so the
    # procedural bump networks are not evaluated for every AO sample (~6x faster).
    flat = bpy.data.materials.new("__ao_flat__")
    flat.use_nodes = True
    _set_target([flat], img_ao)
    saved = list(proxy.data.materials)
    for i in range(len(saved)):
        proxy.data.materials[i] = flat
    try:
        _bake("AO", margin, int(tcfg["ao_samples"]))
    finally:
        for i, m in enumerate(saved):
            proxy.data.materials[i] = m
        bpy.data.materials.remove(flat)
    for m in mats:
        n = m.node_tree.nodes.get(AO_NODE)
        if n is not None:
            n.image = img_ao
    # Convex-edge mask (bevel-normal deviation) baked once on the proxy and
    # fed back like AO: edge wear that does not depend on vertex density.
    img_edge = _new_image(f"{stem}_edge", size, True)
    edge_mat = _edge_material(ao_distance)
    _set_target([edge_mat], img_edge)
    for i in range(len(saved)):
        proxy.data.materials[i] = edge_mat
    try:
        _bake("EMIT", margin, 1)
    finally:
        for i, m in enumerate(saved):
            proxy.data.materials[i] = m
        bpy.data.materials.remove(edge_mat)
    for m in mats:
        n = m.node_tree.nodes.get(EDGE_NODE)
        if n is not None:
            n.image = img_edge

    _bake_normal(proxy, mats, img_nrm, margin)

    for img, sock in ((img_col, "Base Color"), (img_rgh, "Roughness"), (img_met, "Metallic")):
        _set_target(mats, img)
        emitters = [(m, _emit_link(m, sock)) for m in mats]
        try:
            _bake("EMIT", margin, 1)
        finally:
            for m, em in emitters:
                _restore_bsdf(m, em)
    # Emissive map only for assets with lamps/indicators (keeps others at 3 textures).
    img_emi = None
    if any(_emits(m) for m in mats):
        img_emi = _new_image(f"{stem}_emissive", size, False)
        _set_target(mats, img_emi)
        emitters = [(m, _emission_link(m)) for m in mats]
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
    outputs = [("base_color", img_col, tcfg["base_color_format"]), ("orm", img_orm, tcfg["orm_format"]),
               ("normal", img_nrm, tcfg["normal_format"])]
    if img_emi is not None:
        outputs.append(("emissive", img_emi, tcfg["base_color_format"]))
    for key, img, fmt in outputs:
        p = os.path.join(work_dir, f"{stem}_{key}{ext[fmt]}")
        _save(img, p, fmt, q)
        paths[key] = p
    stats = {
        "ao_mean": float(ao[..., 0].mean()),
        "metallic_mean": float(mt[..., 0].mean()),
        "roughness_mean": float(rg[..., 0].mean()),
    }
    for img in (img_ao, img_edge, img_nrm, img_col, img_rgh, img_met, img_orm, img_emi):
        if img is not None:
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
