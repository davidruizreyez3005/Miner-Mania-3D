"""Armature construction and mesh binding shared by characters and machines."""

import bpy
from mathutils import Vector

from core import scene as scn
from core.errors import PipelineError


def create_armature(name, specs, display="OCTAHEDRAL"):
    """Create an armature from BoneSpec-like objects (name, head, tail, parent, z_axis, deform).

    Specs must be ordered parents-first. Bone rolls are set by aligning the
    local Z axis to ``z_axis`` so every rig uses deterministic bone frames.
    """
    arm = bpy.data.armatures.new(name)
    obj = bpy.data.objects.new(name, arm)
    scn.link(obj)
    scn.select_only([obj], obj)
    bpy.ops.object.mode_set(mode="EDIT")
    try:
        ebs = {}
        for s in specs:
            if s.name in ebs:
                raise PipelineError(f"duplicate bone '{s.name}'")
            eb = arm.edit_bones.new(s.name)
            eb.head = Vector(s.head)
            eb.tail = Vector(s.tail)
            if (eb.tail - eb.head).length < 1e-4:
                raise PipelineError(f"bone '{s.name}' has zero length")
            if s.z_axis is not None:
                eb.align_roll(Vector(s.z_axis))
            eb.use_deform = bool(s.deform)
            eb.use_connect = False
            ebs[s.name] = eb
        for s in specs:
            if s.parent:
                if s.parent not in ebs:
                    raise PipelineError(f"bone '{s.name}' parent '{s.parent}' does not exist")
                ebs[s.name].parent = ebs[s.parent]
    finally:
        bpy.ops.object.mode_set(mode="OBJECT")
    arm.display_type = display
    arm.pose_position = "POSE"
    for pb in obj.pose.bones:
        pb.rotation_mode = "QUATERNION"
    return obj


def bind(obj, arm_obj):
    """Add an Armature modifier and parent (keeping world transform)."""
    for m in list(obj.modifiers):
        if m.type == "ARMATURE":
            obj.modifiers.remove(m)
    mod = obj.modifiers.new("Armature", "ARMATURE")
    mod.object = arm_obj
    mod.use_vertex_groups = True
    mod.use_bone_envelopes = False
    mw = obj.matrix_world.copy()
    obj.parent = arm_obj
    obj.parent_type = "OBJECT"
    obj.matrix_world = mw
    return mod


def bind_rigid(obj, arm_obj, bone):
    """Weight every vertex 100% to ``bone`` (mechanical parts)."""
    for vg in list(obj.vertex_groups):
        obj.vertex_groups.remove(vg)
    vg = obj.vertex_groups.new(name=bone)
    vg.add(list(range(len(obj.data.vertices))), 1.0, "REPLACE")
    bind(obj, arm_obj)


def attach_to_bone(obj, arm_obj, bone):
    """Rigidly parent an object to a bone (exported as a child node of the joint;
    Godot turns it into a BoneAttachment3D)."""
    if bone not in arm_obj.data.bones:
        raise PipelineError(f"attachment bone '{bone}' missing on {arm_obj.name}")
    mw = obj.matrix_world.copy()
    for m in list(obj.modifiers):
        if m.type == "ARMATURE":
            obj.modifiers.remove(m)
    for vg in list(obj.vertex_groups):
        obj.vertex_groups.remove(vg)
    obj.parent = arm_obj
    obj.parent_type = "BONE"
    obj.parent_bone = bone
    obj.matrix_world = mw


def rest_matrix(arm_obj, bone):
    return arm_obj.matrix_world @ arm_obj.data.bones[bone].matrix_local
