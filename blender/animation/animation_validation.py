"""Pre-export animation checks on the Blender actions.

The authoritative checks (loops, foot sliding, grips, skeleton references)
run again on the exported GLB in validators/glb_inspector.py; these catch
problems before export and verify the actions match the clip contract.
"""

import math

import bpy
import numpy as np

from core import config
from core.errors import ValidationIssue

from .library import library


def validate_actions(ctx):
    spec = config.animation_spec()
    acfg = ctx.cfg["animation"]
    fps = spec["fps"]
    issues = []
    have = {a.name: a for a in bpy.data.actions}
    for name, clip in spec["clips"].items():
        act = have.get(name)
        if act is None:
            if not clip.get("optional"):
                issues.append(ValidationIssue("error", "ANIM_MISSING", f"required clip {name} missing"))
            continue
        start, end = act.frame_range
        frames = int(round(end - start))
        want = int(round(clip["duration"] * fps))
        if start != 0 or frames != want:
            issues.append(ValidationIssue("error", "ANIM_FRAME_RANGE",
                                          f"{name}: frames {start}-{end}, expected 0-{want}"))
        dur = frames / fps
        if not (acfg["min_duration_s"] <= dur <= acfg["max_duration_s"]):
            issues.append(ValidationIssue("error", "ANIM_DURATION", f"{name}: {dur:.2f}s out of range"))
    lib = library()
    worst = max(v["reach_error"] for v in lib.values())
    for name, data in lib.items():
        for b, arr in data["rot"].items():
            if not np.all(np.isfinite(arr)):
                issues.append(ValidationIssue("error", "ANIM_NAN", f"{name}: non-finite rotation on {b}"))
                break
            norms = np.linalg.norm(arr, axis=1)
            if np.abs(norms - 1.0).max() > acfg["quaternion_norm_tolerance"]:
                issues.append(ValidationIssue("error", "ANIM_QUAT", f"{name}: non-unit quaternion on {b}"))
                break
        if spec["clips"][name]["loop"]:
            for b, arr in data["rot"].items():
                d = abs(float(np.dot(arr[0], arr[-1])))
                ang = math.degrees(2 * math.acos(min(1.0, d)))
                if ang > acfg["loop_rotation_tolerance_deg"]:
                    issues.append(ValidationIssue("error", "ANIM_LOOP", f"{name}: {b} jumps {ang:.1f} deg at the loop"))
                    break
        if data["reach_error"] > 0.02:
            issues.append(ValidationIssue("error", "ANIM_IK_REACH",
                                          f"{name}: IK targets out of reach by {data['reach_error'] * 100:.1f} cm"))
    ctx.metadata["ik_worst_reach_error_m"] = round(worst, 4)
    return issues
