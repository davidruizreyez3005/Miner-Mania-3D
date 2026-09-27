"""Locomotion and idle clips: Idle, Idle_Variant, Walk, Run, Turn_Left, Turn_Right.

Walk/Run are in-place with planted feet: stance feet travel backward at the
clip's ``root_motion.speed_mps`` so gameplay can move the character at that
speed (or scale playback by actual_speed / clip_speed) without foot sliding.
Turns rotate the ``root`` bone by +-90 degrees (intentional root motion) while
each foot steps once to its rotated position.
"""

import math

from mathutils import Quaternion, Vector

from .clipkit import STAND, Gait, add, foot_from_ball, keys, planted, rest_ball, smooth, stand_feet, wave
from .rig_model import model


def _arm_swing(amount_l, amount_r, elbow_gain=12.0):
    """Deltas added to STAND: shoulder flexion swing, extra elbow bend when forward."""
    return {
        "upper_arm.L": (amount_l, 0.0, 0.0),
        "upper_arm.R": (amount_r, 0.0, 0.0),
        "forearm.L": (elbow_gain * max(0.0, amount_l) / 20.0, 0.0, 0.0),
        "forearm.R": (elbow_gain * max(0.0, amount_r) / 20.0, 0.0, 0.0),
    }


def idle_pose(t, T=3.0, breath=1.0):
    br = wave(t, T / 2.0, 1.0)
    shift = wave(t, T, 1.0)
    fk = add(STAND, {
        "spine_02": (0.9 * br * breath, 0.0, 0.0),
        "spine_03": (0.6 * br * breath, 0.0, 0.0),
        "clavicle.L": (0.0, 0.0, 0.6 * br * breath), "clavicle.R": (0.0, 0.0, 0.6 * br * breath),
        "upper_arm.L": (1.5 * shift, 0.0, 0.0), "upper_arm.R": (-1.5 * shift, 0.0, 0.0),
        "spine_01": (0.0, 0.0, 1.2 * shift),
    })
    return {
        "pelvis": {"loc": (0.009 * shift, 0.0, -0.012 - 0.002 * br), "rot": (0.0, 1.5 * shift, -1.2 * shift)},
        "fk": fk,
        "feet": stand_feet(),
        "look": (4.0 * wave(t, T, 1.0, 0.2), 1.0 * br),
        "fingers": {"L": "relaxed", "R": "grip"},
    }


def idle(t):
    return idle_pose(t, 3.0)


_IDLE_HANDS = None


def idle_hand_frames():
    """hand_tool socket frames of Idle(0); non-looping interaction clips start
    and end there so they blend cleanly with Idle."""
    global _IDLE_HANDS
    if _IDLE_HANDS is None:
        from .solver import solve, world_pose
        w = world_pose(solve(idle_pose(0.0)))
        _IDLE_HANDS = {s: w[f"hand_tool.{s}"].copy() for s in ("L", "R")}
    return {s: m.copy() for s, m in _IDLE_HANDS.items()}


def idle_variant(t):
    """Look around, roll the shoulders and stretch the back; starts/ends at Idle(0)."""
    base = idle_pose(t % 3.0, 3.0)
    w = keys(t, [(0.0, 0.0), (0.5, 1.0), (3.4, 1.0), (4.0, 0.0)])
    look_y = keys(t, [(0.0, 0.0), (0.7, 35.0), (1.6, 35.0), (2.3, -30.0), (3.1, -30.0), (3.7, 0.0)])
    look_p = keys(t, [(0.0, 0.0), (0.7, -6.0), (1.6, 4.0), (2.3, -4.0), (3.7, 0.0)])
    stretch = keys(t, [(0.0, 0.0), (2.4, 0.0), (2.9, 1.0), (3.3, 1.0), (3.8, 0.0)])
    roll = keys(t, [(0.0, 0.0), (1.0, 0.0), (1.4, 1.0), (1.8, 0.0)])
    fk = add(base["fk"], {
        "spine_03": (-8.0 * stretch, 6.0 * w * math.copysign(1, look_y) if look_y else 0.0, 0.0),
        "spine_02": (-4.0 * stretch, 0.0, 0.0),
        "clavicle.L": (-6.0 * roll, 0.0, 8.0 * roll + 4.0 * stretch),
        "clavicle.R": (-6.0 * roll, 0.0, 8.0 * roll + 4.0 * stretch),
        "upper_arm.L": (-10.0 * stretch, 0.0, 12.0 * stretch),
        "upper_arm.R": (-10.0 * stretch, 0.0, 12.0 * stretch),
        "forearm.L": (20.0 * stretch, 0.0, 0.0), "forearm.R": (20.0 * stretch, 0.0, 0.0),
    })
    base["fk"] = fk
    base["look"] = (look_y, look_p)
    return base


def walk_pose(t, T, v, lean=4.0, arm=18.0, carry=False, stance=0.6, step=0.06):
    g = Gait(T, v, stance=stance, step_height=step, heel_strike=12.0, toe_off=18.0)
    feet, toes = {}, {}
    for s in ("L", "R"):
        f, toe, _ = g.foot(s, t)
        feet[s] = f
        toes[s] = toe
    ph = (t / T) % 1.0
    c2 = math.cos(4.0 * math.pi * ph)
    bob = -0.02 * (0.5 + 0.5 * c2)
    sway = -0.013 * math.sin(2.0 * math.pi * ph)
    yaw = 5.0 * math.cos(2.0 * math.pi * ph) * (1 if v >= 0 else -1)
    roll = 2.5 * math.sin(2.0 * math.pi * ph)
    fk = add(STAND, {
        "spine_01": (lean * 0.5, -0.3 * yaw, -0.5 * roll),
        "spine_02": (lean * 0.3 + 1.0 * c2, -0.4 * yaw, 0.0),
        "spine_03": (lean * 0.2, -0.5 * yaw, 0.0),
        "neck": (0.0, 0.4 * yaw, 0.0), "head": (-lean * 0.6 - 1.0 * c2, 0.4 * yaw, 0.0),
    })
    if not carry:
        swing = arm * math.cos(2.0 * math.pi * ph) * (1 if v >= 0 else -1)
        fk = add(fk, _arm_swing(swing, -swing))
    return {
        "pelvis": {"loc": (sway, 0.0, -0.045 + bob), "rot": (lean * 0.3, yaw, roll)},
        "fk": fk,
        "feet": feet,
        "toes": toes,
        "fingers": {"L": "relaxed", "R": "grip"},
    }


def walk(t):
    return walk_pose(t, 1.0, _speed("Walk"))


def _speed(name):
    from core import config
    return config.animation_spec()["clips"][name]["root_motion"]["speed_mps"]


def run(t):
    T, v = 0.7, _speed("Run")
    g = Gait(T, v, stance=0.33, step_height=0.15, heel_strike=6.0, toe_off=26.0, center=0.0)
    feet, toes = {}, {}
    for s in ("L", "R"):
        f, toe, _ = g.foot(s, t)
        feet[s] = f
        toes[s] = toe
    ph = (t / T) % 1.0
    c2 = math.cos(4.0 * math.pi * ph)
    bob = 0.028 * (0.5 - 0.5 * c2) - 0.01
    yaw = 8.0 * math.cos(2.0 * math.pi * ph)
    swing = 34.0 * math.cos(2.0 * math.pi * ph)
    # Deltas on STAND: forward lean, counter-rotating chest, pumping arms with
    # ~80 degree elbows held slightly away from the body.
    fk = add(STAND, {
        "spine_01": (7.0, -0.3 * yaw, 0.0), "spine_02": (5.0, -0.4 * yaw, 0.0), "spine_03": (2.0, -0.6 * yaw, 0.0),
        "neck": (-2.0, 0.4 * yaw, 0.0), "head": (-8.0, 0.4 * yaw, 0.0),
        "upper_arm.L": (swing - 6.0, -6.0, 8.0), "upper_arm.R": (-swing - 6.0, -6.0, 8.0),
        "forearm.L": (64.0 + 10.0 * max(0.0, swing) / 34.0, 12.0, 0.0),
        "forearm.R": (64.0 + 10.0 * max(0.0, -swing) / 34.0, 12.0, 0.0),
    })
    return {
        "pelvis": {"loc": (0.0, 0.0, -0.075 + bob), "rot": (8.0, yaw, 0.0)},
        "fk": fk, "feet": feet, "toes": toes,
        "fingers": {"L": "fist", "R": "grip"},
    }


def _turn(t, sign):
    """90 degree turn in place: root yaws while each foot steps once."""
    yaw = 90.0 * sign * smooth((t - 0.1) / 0.8)
    q_end = Quaternion(Vector((0, 0, 1)), math.radians(90.0 * sign))
    lead, trail = ("L", "R") if sign > 0 else ("R", "L")
    feet = {}
    toes = {}
    for side, (t0, t1) in ((lead, (0.12, 0.52)), (trail, (0.42, 0.86))):
        start_ball = rest_ball(side)
        end_ball = q_end @ rest_ball(side)
        u = smooth((t - t0) / (t1 - t0))
        pos = start_ball.lerp(end_ball, u)
        pos.z += 0.06 * math.sin(math.pi * max(0.0, min(1.0, (t - t0) / (t1 - t0))))
        yaw_f = 90.0 * sign * u + (5.0 if side == "L" else -5.0)
        lift = 18.0 * math.sin(math.pi * max(0.0, min(1.0, (t - t0) / (t1 - t0))))
        feet[side] = foot_from_ball(side, pos, lift, yaw_f)
        toes[side] = lift * 0.6
    # Foot targets are in armature space; the root bone carries the rotation,
    # so express them relative to the (rotating) root.
    q_root = Quaternion(Vector((0, 0, 1)), math.radians(yaw))
    inv = q_root.inverted().to_matrix().to_4x4()
    feet = {s: inv @ f for s, f in feet.items()}
    base = idle_pose(0.0)
    lean = 3.0 * math.sin(math.pi * max(0.0, min(1.0, t)))
    base["fk"] = add(base["fk"], {"spine_01": (lean, 4.0 * sign * math.sin(math.pi * t), 0.0),
                                   "neck": (0.0, 10.0 * sign * math.sin(math.pi * min(1.0, t * 1.4)), 0.0)})
    base["root"] = {"yaw": yaw}
    base["feet"] = feet
    base["toes"] = toes
    base["look"] = None
    return base


def turn_left(t):
    return _turn(t, 1.0)


def turn_right(t):
    return _turn(t, -1.0)


CLIPS = {
    "Idle": idle,
    "Idle_Variant": idle_variant,
    "Walk": walk,
    "Run": run,
    "Turn_Left": turn_left,
    "Turn_Right": turn_right,
}
