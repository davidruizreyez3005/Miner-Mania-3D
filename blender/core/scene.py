"""Scene lifecycle and context helpers that are safe in ``--background`` mode."""

import contextlib

import bpy
from mathutils import Matrix, Vector

from .errors import PipelineError

ASSET_COLLECTION = "ASSET"


def reset_scene(cfg, seed=0):
    """Start every asset from factory settings so no state leaks between assets."""
    result = bpy.ops.wm.read_factory_settings(use_empty=True)
    if "FINISHED" not in result:
        raise PipelineError(f"could not reset Blender scene: {result}")
    scene = bpy.context.scene
    scene.name = "Scene"
    us = scene.unit_settings
    us.system = "METRIC"
    us.scale_length = cfg["world"]["unit_scale"]
    us.length_unit = "METERS"
    scene.render.fps = cfg["world"]["fps"]
    scene.render.fps_base = 1.0
    scene.frame_start = 0
    scene.frame_end = 0
    scene.frame_current = 0
    scene.render.engine = "CYCLES"
    cy = scene.cycles
    cy.device = "CPU"
    cy.samples = 1
    cy.use_denoising = False
    cy.seed = int(seed) & 0x7FFFFFFF
    cy.use_animated_seed = False
    cy.max_bounces = 2
    scene.render.bake.margin_type = "EXTEND"
    scene.view_settings.view_transform = "Standard"
    scene.view_settings.look = "None"
    scene.display_settings.display_device = "sRGB"
    world = bpy.data.worlds.new("World")
    world.use_nodes = True
    scene.world = world
    coll = bpy.data.collections.new(ASSET_COLLECTION)
    scene.collection.children.link(coll)
    return scene


def asset_collection():
    coll = bpy.data.collections.get(ASSET_COLLECTION)
    if coll is None:
        raise PipelineError("ASSET collection missing; reset_scene() was not called")
    return coll


def link(obj, collection=None):
    (collection or asset_collection()).objects.link(obj)
    return obj


def object_mode():
    obj = bpy.context.view_layer.objects.active
    if obj is not None and obj.mode != "OBJECT":
        bpy.ops.object.mode_set(mode="OBJECT")


def select_only(objs, active=None):
    object_mode()
    for o in bpy.context.view_layer.objects:
        o.select_set(False)
    for o in objs:
        o.select_set(True)
    bpy.context.view_layer.objects.active = active or (objs[0] if objs else None)


@contextlib.contextmanager
def edit_mode(objs):
    """Multi-object edit mode on ``objs`` with everything selected."""
    objs = [o for o in objs if o.type == "MESH"]
    if not objs:
        raise PipelineError("edit_mode() called without mesh objects")
    select_only(objs, objs[0])
    bpy.ops.object.mode_set(mode="EDIT")
    try:
        bpy.ops.mesh.select_all(action="SELECT")
        yield
    finally:
        bpy.ops.object.mode_set(mode="OBJECT")


def new_empty(name, matrix=None, collection=None, display="PLAIN_AXES", size=0.1):
    obj = bpy.data.objects.new(name, None)
    obj.empty_display_type = display
    obj.empty_display_size = size
    if matrix is not None:
        obj.matrix_world = matrix
    link(obj, collection)
    return obj


def mesh_objects(collection=None, kind=None):
    coll = collection or asset_collection()
    out = []
    for o in coll.all_objects:
        if o.type != "MESH":
            continue
        if kind is not None and o.get("mm_kind", "render") != kind:
            continue
        out.append(o)
    return sorted(out, key=lambda o: o.name)


def triangle_count(obj):
    me = obj.data
    return sum(len(p.vertices) - 2 for p in me.polygons)


def world_bounds(objs):
    lo = Vector((1e18, 1e18, 1e18))
    hi = Vector((-1e18, -1e18, -1e18))
    found = False
    for o in objs:
        if o.type != "MESH":
            continue
        mw = o.matrix_world
        for v in o.data.vertices:
            p = mw @ v.co
            lo.x, lo.y, lo.z = min(lo.x, p.x), min(lo.y, p.y), min(lo.z, p.z)
            hi.x, hi.y, hi.z = max(hi.x, p.x), max(hi.y, p.y), max(hi.z, p.z)
            found = True
    if not found:
        raise PipelineError("world_bounds() found no vertices")
    return lo, hi


def apply_object_transform(obj):
    """Bake the object's world transform into its mesh and reset it to identity."""
    if obj.type != "MESH":
        return
    mw = obj.matrix_world.copy()
    obj.data.transform(mw)
    if mw.determinant() < 0:
        obj.data.flip_normals()
    obj.parent = None
    obj.matrix_world = Matrix.Identity(4)
    obj.data.update()


def remove_object(obj):
    data = obj.data
    bpy.data.objects.remove(obj, do_unlink=True)
    if data is not None and getattr(data, "users", 1) == 0:
        if isinstance(data, bpy.types.Mesh):
            bpy.data.meshes.remove(data)
