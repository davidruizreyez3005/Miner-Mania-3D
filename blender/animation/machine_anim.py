"""Bake procedural machine clips (ClipSpec) into actions on the rigid rig.

Clip functions return, for time ``t`` in seconds, a mapping of bone name to
``(location, rotation)`` expressed in the bone's *rest* frame offsets:
location is a translation in armature space applied to the rest head, and
rotation is a Quaternion in armature space about the bone head. This keeps
machine authoring in intuitive world axes while writing correct pose-space
keys for any bone roll.
"""

import numpy as np
from mathutils import Matrix, Quaternion, Vector

from core.errors import PipelineError

from . import keys


def _pose_basis(rest, loc, rot):
    """Convert an armature-space offset (translation + rotation about head)
    into the bone's local pose basis."""
    r3 = rest.to_3x3()
    q_rest = r3.to_quaternion()
    q = rot if rot is not None else Quaternion()
    q_local = q_rest.inverted() @ q @ q_rest
    t = Vector(loc) if loc is not None else Vector()
    t_local = r3.inverted() @ t
    return t_local, q_local


def bake_clips(ctx):
    arm = ctx.armature
    if arm is None:
        raise PipelineError("machine clips require a rig (declare bones with ctx.bone)")
    fps = ctx.cfg["world"]["fps"]
    bones = arm.data.bones
    arm.animation_data_create()
    first = None
    for clip in ctx.clips:
        n = int(round(clip.duration * fps))
        if n < 2:
            raise PipelineError(f"clip {clip.name} is too short")
        frames = np.arange(n + 1, dtype=np.float64)
        samples = [clip.fn(f / fps if not clip.loop else (f % n) / fps) for f in range(n + 1)]
        animated = sorted({b for s in samples for b in s})
        for b in animated:
            if b not in bones:
                raise PipelineError(f"clip {clip.name} animates unknown bone '{b}'")
        act, slot, bag = keys.new_action(clip.name, arm)
        for b in animated:
            rest = bones[b].matrix_local
            locs, quats = [], []
            for s in samples:
                loc, rot = s.get(b, (None, None))
                t_local, q_local = _pose_basis(rest, loc, rot)
                locs.append(tuple(t_local))
                quats.append((q_local.w, q_local.x, q_local.y, q_local.z))
            keys.write_bone(bag, b, frames, locs=np.array(locs), quats=np.array(quats))
        keys.finalize_action(act, n)
        if first is None:
            first = (act, slot)
    arm.animation_data.action = first[0]
    arm.animation_data.action_slot = first[1]
    ctx.metadata["clips"] = [{"name": c.name, "duration": c.duration, "loop": c.loop, "description": c.description}
                             for c in ctx.clips]


def spin(axis, turns_per_second, t, phase=0.0):
    """Rotation of ``turns_per_second`` about a world axis at time t."""
    return Quaternion(Vector(axis).normalized(), 2.0 * np.pi * (turns_per_second * t + phase))


def loop_spin(axis, turns, t, duration):
    """Integer number of turns over the clip so the loop is seamless."""
    return Quaternion(Vector(axis).normalized(), 2.0 * np.pi * turns * (t / duration))


def osc(amplitude, cycles, t, duration, phase=0.0):
    return amplitude * np.sin(2.0 * np.pi * (cycles * t / duration + phase))
