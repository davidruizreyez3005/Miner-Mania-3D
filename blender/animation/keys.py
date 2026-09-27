"""Fast keyframe writing through the layered/slotted Action API (Blender 4.4+).

Every frame is keyed, so interpolation mode does not matter: the glTF exporter
samples each frame exactly.
"""

import bpy
import numpy as np

from core.errors import PipelineError


def new_action(name, arm_obj):
    if bpy.data.actions.get(name) is not None:
        raise PipelineError(f"action '{name}' already exists")
    act = bpy.data.actions.new(name)
    slot = act.slots.new(id_type="OBJECT", name=arm_obj.name)
    layer = act.layers.new("Layer")
    strip = layer.strips.new(type="KEYFRAME")
    bag = strip.channelbag(slot, ensure=True)
    act.use_fake_user = True
    return act, slot, bag


def _curve(bag, path, index, group):
    fc = bag.fcurves.new(path, index=index)
    grp = bag.groups.get(group) or bag.groups.new(group)
    fc.group = grp
    return fc


def write_channel(bag, path, frames, values, group):
    """values: (N, C) array; writes C F-curves keyed at every frame."""
    values = np.asarray(values, dtype=np.float64)
    frames = np.asarray(frames, dtype=np.float64)
    if not np.all(np.isfinite(values)):
        raise PipelineError(f"non-finite animation values for {path}")
    n = len(frames)
    for c in range(values.shape[1]):
        fc = _curve(bag, path, c, group)
        fc.keyframe_points.add(n)
        co = np.empty(2 * n, dtype=np.float64)
        co[0::2] = frames
        co[1::2] = values[:, c]
        fc.keyframe_points.foreach_set("co", co)
        fc.update()


def continuous_quats(quats):
    """Flip quaternion signs so consecutive keys take the short path."""
    q = np.array(quats, dtype=np.float64)
    for i in range(1, len(q)):
        if np.dot(q[i - 1], q[i]) < 0.0:
            q[i] = -q[i]
    return q


def write_bone(bag, bone, frames, locs=None, quats=None, scales=None):
    if locs is not None:
        write_channel(bag, f'pose.bones["{bone}"].location', frames, locs, bone)
    if quats is not None:
        write_channel(bag, f'pose.bones["{bone}"].rotation_quaternion', frames, continuous_quats(quats), bone)
    if scales is not None:
        write_channel(bag, f'pose.bones["{bone}"].scale', frames, scales, bone)


def finalize_action(act, frame_end):
    act.use_frame_range = True
    act.frame_start = 0
    act.frame_end = frame_end
    act.use_cyclic = False
