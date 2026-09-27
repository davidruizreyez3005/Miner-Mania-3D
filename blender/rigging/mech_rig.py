"""Rigid skeletons for machinery and vehicles.

Each moving part is weighted 100% to one bone; after assembly the whole
machine is a single skinned mesh (one draw call per material on mobile) that
Godot drives with a Skeleton3D + AnimationPlayer. Bone pivots sit on the real
mechanical axes (wheel hubs, hinge pins, piston mounts) so gameplay code can
also rotate them procedurally.
"""

from core.context import BoneSpec
from core.errors import PipelineError

from . import armature_utils


def build(ctx):
    specs = [BoneSpec("root", (0.0, 0.0, 0.0), (0.0, 0.0, 0.35), None, (0.0, -1.0, 0.0), True)]
    names = {"root"}
    for b in ctx.bones:
        if b.name in names:
            raise PipelineError(f"duplicate mechanical bone '{b.name}'")
        if b.parent and b.parent not in names:
            raise PipelineError(f"bone '{b.name}' declared before its parent '{b.parent}'")
        specs.append(b)
        names.add(b.name)
    arm = armature_utils.create_armature(ctx.name, specs, display="STICK")
    ctx.armature = arm
    for o in ctx.objects:
        if o.type != "MESH" or o.get("mm_attach_bone"):
            continue
        bone = o.get("mm_bone", "root")
        if bone not in names:
            raise PipelineError(f"part {o.name} references unknown bone '{bone}'")
        armature_utils.bind_rigid(o, arm, bone)
    ctx.metadata["bones"] = [s.name for s in specs]
