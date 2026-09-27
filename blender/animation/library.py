"""Shared worker animation library.

Clip functions (locomotion, mining, carrying, operating, repairing, gestures)
are evaluated once per build against the pure-math rig model and cached; every
worker variant (and the standalone animation library GLB) receives the same
keys because all of them share the humanoid_worker_v1 skeleton.
"""

import math

import numpy as np
from mathutils import Quaternion, Vector

from core import config, log
from core.errors import PipelineError

from . import keys
from .rig_model import model
from .solver import solve

_CACHE = {}
LOCATION_BONES = ("root", "pelvis", "carry_attachment")


def clip_functions():
    from . import carrying, gestures, locomotion, mining, operating, repairing
    out = {}
    for mod in (locomotion, mining, carrying, operating, repairing, gestures):
        for name, fn in mod.CLIPS.items():
            if name in out:
                raise PipelineError(f"clip {name} defined twice")
            out[name] = fn
    return out


def evaluate(name, fn, duration, loop, fps):
    n = int(round(duration * fps))
    if n < 2:
        raise PipelineError(f"clip {name}: duration {duration}s too short")
    m = model()
    rot = {b: [] for b in m.names}
    loc = {b: [] for b in LOCATION_BONES}
    worst_reach = 0.0
    for f in range(n + 1):
        t = (f % n) / fps if loop else f / fps
        spec = fn(t)
        s = solve(spec)
        worst_reach = max(worst_reach, s.reach_error)
        for b in m.names:
            q = s.rot.get(b, Quaternion())
            rot[b].append((q.w, q.x, q.y, q.z))
        for b in LOCATION_BONES:
            v = s.loc.get(b, Vector())
            loc[b].append((v.x, v.y, v.z))
    return {"frames": n, "rot": {b: np.array(v) for b, v in rot.items()},
            "loc": {b: np.array(v) for b, v in loc.items()}, "reach_error": worst_reach}


def library():
    """Evaluate (or reuse) every clip in the animation contract."""
    spec = config.animation_spec()
    fps = spec["fps"]
    fns = clip_functions()
    missing = [c for c in spec["clips"] if c not in fns]
    if missing:
        raise PipelineError(f"animation contract clips without implementation: {missing}")
    for name, c in spec["clips"].items():
        if name not in _CACHE:
            _CACHE[name] = evaluate(name, fns[name], c["duration"], c["loop"], fps)
            if _CACHE[name]["reach_error"] > 0.01:
                log.warn(f"clip {name}: IK target out of reach by {_CACHE[name]['reach_error'] * 100:.1f} cm")
    return _CACHE


def verify_rest(arm):
    m = model()
    worst = 0.0
    for b in arm.data.bones:
        if b.name not in m.rest:
            raise PipelineError(f"armature bone {b.name} unknown to the rig model")
        d = np.abs(np.array(b.matrix_local) - np.array(m.rest[b.name])).max()
        worst = max(worst, float(d))
    if worst > 1e-4:
        raise PipelineError(f"rig model rest frames differ from the armature (max {worst:.2e})")


def apply_worker_library(ctx):
    arm = ctx.armature
    if arm is None:
        raise PipelineError("worker animation requires the armature (rig stage)")
    verify_rest(arm)
    lib = library()
    spec = config.animation_spec()
    arm.animation_data_create()
    for name, c in spec["clips"].items():
        data = lib[name]
        act, slot, bag = keys.new_action(name, arm)
        frames = np.arange(data["frames"] + 1, dtype=np.float64)
        for b in arm.data.bones:
            n = b.name
            locs = data["loc"][n] if n in LOCATION_BONES else None
            keys.write_bone(bag, n, frames, locs=locs, quats=data["rot"][n])
        keys.finalize_action(act, data["frames"])
        act["mm_loop"] = bool(c["loop"])
    # Leave no action assigned and the pose at rest: the glTF exporter
    # (ACTIONS mode, single armature) exports every bone-keyed action of an
    # armature that has animation_data, and the rest-pose checks stay valid.
    arm.animation_data.action = None
    for pb in arm.pose.bones:
        pb.matrix_basis.identity()
    ctx.metadata["clips"] = [{"name": n, "loop": c["loop"], "duration": c["duration"],
                              "frames": lib[n]["frames"]} for n, c in spec["clips"].items()]
    ctx.metadata["ik_reach_error_m"] = {n: round(lib[n]["reach_error"], 4) for n in spec["clips"]}
