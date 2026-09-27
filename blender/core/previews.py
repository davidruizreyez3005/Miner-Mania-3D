"""Review thumbnails rendered with Cycles (CPU, headless) from the exported GLBs.

Previews are a QA aid for reviewers; they are never a substitute for the GLB
assets themselves. Each GLB is re-imported into an empty scene, so the
thumbnail shows exactly what the exporter wrote.
"""

import math
import os

import bpy
from mathutils import Vector

from . import log, paths
from . import scene as scn

SIZE = 320


def _setup(cfg):
    scn.reset_scene(cfg, 7)
    sc = bpy.context.scene
    sc.render.resolution_x = SIZE
    sc.render.resolution_y = SIZE
    sc.render.film_transparent = False
    sc.cycles.samples = 24
    sc.cycles.use_denoising = True
    sc.view_settings.view_transform = "AgX"
    w = sc.world
    nt = w.node_tree
    bg = nt.nodes.get("Background")
    bg.inputs["Color"].default_value = (0.42, 0.45, 0.5, 1.0)
    bg.inputs["Strength"].default_value = 0.9
    sun = bpy.data.objects.new("Sun", bpy.data.lights.new("Sun", "SUN"))
    sun.data.energy = 3.2
    sun.data.angle = math.radians(8)
    sun.rotation_euler = (math.radians(50), math.radians(8), math.radians(-35))
    sc.collection.objects.link(sun)
    fill = bpy.data.objects.new("Fill", bpy.data.lights.new("Fill", "SUN"))
    fill.data.energy = 0.8
    fill.rotation_euler = (math.radians(65), 0, math.radians(150))
    sc.collection.objects.link(fill)
    return sc


def render_glb(glb_path, out_path, cfg, frame_action=None, frame=0):
    sc = _setup(cfg)
    before = set(bpy.data.objects)
    r = bpy.ops.import_scene.gltf(filepath=glb_path)
    if "FINISHED" not in r:
        raise RuntimeError(f"preview import failed for {glb_path}")
    objs = [o for o in bpy.data.objects if o not in before]
    arm = next((o for o in objs if o.type == "ARMATURE"), None)
    if arm is not None and frame_action and bpy.data.actions.get(frame_action):
        arm.animation_data_create()
        arm.animation_data.action = bpy.data.actions[frame_action]
        sc.frame_set(frame)
    meshes = [o for o in objs if o.type == "MESH" and not o.name.endswith("-convcolonly")]
    deps = bpy.context.evaluated_depsgraph_get()
    lo = Vector((1e9, 1e9, 1e9))
    hi = Vector((-1e9, -1e9, -1e9))
    for o in meshes:
        ev = o.evaluated_get(deps)
        for c in ev.bound_box:
            p = ev.matrix_world @ Vector(c)
            lo = Vector(map(min, lo, p))
            hi = Vector(map(max, hi, p))
    center = (lo + hi) / 2
    radius = max((hi - lo).length / 2, 0.05)
    ground = bpy.data.objects.new("Ground", bpy.data.meshes.new("Ground"))
    s = radius * 8
    ground.data.from_pydata([(-s, -s, lo.z), (s, -s, lo.z), (s, s, lo.z), (-s, s, lo.z)], [], [(0, 1, 2, 3)])
    gm = bpy.data.materials.new("GroundMat")
    gm.use_nodes = True
    gm.node_tree.nodes["Principled BSDF"].inputs["Base Color"].default_value = (0.32, 0.3, 0.28, 1)
    gm.node_tree.nodes["Principled BSDF"].inputs["Roughness"].default_value = 0.9
    ground.data.materials.append(gm)
    sc.collection.objects.link(ground)
    cam = bpy.data.objects.new("Cam", bpy.data.cameras.new("Cam"))
    cam.data.lens = 50
    sc.collection.objects.link(cam)
    sc.camera = cam
    d = radius / math.tan(cam.data.angle / 2) * 1.12
    direction = Vector((0.62, -1.0, 0.55)).normalized()
    cam.location = center + direction * d
    cam.rotation_euler = (center - cam.location).to_track_quat("-Z", "Y").to_euler()
    cam.data.clip_start = max(0.01, d * 0.01)
    cam.data.clip_end = d * 20
    sc.render.filepath = out_path
    bpy.ops.render.render(write_still=True)


def render_all(results, cfg):
    paths.ensure_dir(paths.PREVIEW_DIR)
    made = []
    for r in results:
        for o in r.outputs:
            src = os.path.join(paths.REPO_ROOT, o.model)
            dst = os.path.join(paths.PREVIEW_DIR, f"{o.name}.png")
            try:
                act = "Walk" if "Walk" in o.animations else (o.animations[0] if o.animations else None)
                render_glb(src, dst, cfg, act, 8 if act == "Walk" else 0)
                made.append(dst)
            except Exception as exc:  # previews are advisory; report but never mask asset failures
                log.warn(f"preview failed for {o.name}: {exc}")
    contact_sheet(made)
    log.info(f"previews: {len(made)} thumbnails in {paths.rel(paths.PREVIEW_DIR)}")


def contact_sheet(files, cols=8):
    import numpy as np
    if not files:
        return
    imgs = []
    for f in files:
        img = bpy.data.images.load(f, check_existing=False)
        px = np.empty(img.size[0] * img.size[1] * 4, dtype=np.float32)
        img.pixels.foreach_get(px)
        imgs.append(px.reshape(img.size[1], img.size[0], 4))
        bpy.data.images.remove(img)
    rows = (len(imgs) + cols - 1) // cols
    sheet = np.ones((rows * SIZE, cols * SIZE, 4), dtype=np.float32) * 0.15
    sheet[..., 3] = 1.0
    for i, im in enumerate(imgs):
        r, c = divmod(i, cols)
        y0 = (rows - 1 - r) * SIZE
        sheet[y0:y0 + im.shape[0], c * SIZE:c * SIZE + im.shape[1]] = im[:SIZE, :SIZE]
    out = bpy.data.images.new("contact_sheet", cols * SIZE, rows * SIZE)
    out.pixels.foreach_set(sheet.ravel())
    out.filepath_raw = os.path.join(paths.PREVIEW_DIR, "contact_sheet.png")
    out.file_format = "PNG"
    out.save()
