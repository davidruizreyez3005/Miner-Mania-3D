"""Expressive clips: Celebrate, React, Rest, Sit, Death_or_Fall.

Non-looping gestures start and end in the Idle(0) pose so the game can blend
in and out without pops; Rest and Sit are seamless loops.
"""

import math

from mathutils import Vector

from core import config

from .clipkit import (STAND, add, blend, ease_in, ease_out, foot_frame, foot_from_ball, hand_frame, keys, planted,
                      rest_ball, smooth, stand_feet, wave)
from .locomotion import idle_pose
from .mining import spine, track

GUARD = {
    "upper_arm.L": (58.0, -10.0, -22.0), "upper_arm.R": (58.0, -10.0, -22.0),
    "forearm.L": (118.0, 30.0, 0.0), "forearm.R": (118.0, 30.0, 0.0),
    "hand.L": (-10.0, 0.0, 0.0), "hand.R": (-10.0, 0.0, 0.0),
    "clavicle.L": (6.0, 0.0, 6.0), "clavicle.R": (6.0, 0.0, 6.0),
}


def fk_hands(spec):
    """hand_tool frames the spec's FK arms produce (for FK -> IK blends)."""
    from .solver import solve, world_pose
    s = dict(spec)
    s.pop("hands", None)
    s.pop("grip", None)
    w = world_pose(solve(s))
    return {side: w[f"hand_tool.{side}"].copy() for side in ("L", "R")}


def _arms(base, pose, w):
    """Blend the arm bones of ``base`` toward ``pose`` by ``w``."""
    out = dict(base)
    for b, v in pose.items():
        a = base.get(b, (0.0, 0.0, 0.0))
        out[b] = tuple(x + (y - x) * w for x, y in zip(a, v))
    return out


# ------------------------------------------------------------------ Celebrate

CELEBRATE = [
    (0.0, dict(ploc=(0.0, 0.0, -0.012), prot=(0.0, 0.0, 0.0), spine=(0.0, 0.0, 0.0), air=0.0, look=(0.0, 1.0))),
    (0.28, dict(ploc=(0.0, 0.02, -0.11), prot=(6.0, 0.0, 0.0), spine=(12.0, 0.0, 0.0), air=0.0, look=(0.0, 8.0))),
    (0.48, dict(ploc=(0.0, 0.0, 0.1), prot=(-2.0, 0.0, 0.0), spine=(-8.0, 0.0, 0.0), air=1.0, look=(0.0, -14.0)),
     ease_out),
    (0.66, dict(ploc=(0.0, 0.01, -0.08), prot=(4.0, 0.0, 0.0), spine=(6.0, 0.0, 0.0), air=0.0, look=(0.0, -6.0)),
     ease_in),
    (0.85, dict(ploc=(0.0, 0.0, -0.025), prot=(0.0, 0.0, 0.0), spine=(-4.0, 0.0, 0.0), air=0.0, look=(0.0, -8.0))),
    (1.05, dict(ploc=(0.0, 0.0, -0.035), prot=(1.0, 0.0, 0.0), spine=(3.0, -6.0, 0.0), air=0.0, look=(-4.0, 0.0)),
     ease_out),
    (1.22, dict(ploc=(0.0, 0.0, -0.02), prot=(0.0, 0.0, 0.0), spine=(-2.0, -2.0, 0.0), air=0.0, look=(-2.0, -6.0))),
    (1.4, dict(ploc=(0.0, 0.0, -0.035), prot=(1.0, 0.0, 0.0), spine=(3.0, -6.0, 0.0), air=0.0, look=(-4.0, 0.0)),
     ease_out),
    (2.0, dict(ploc=(0.0, 0.0, -0.012), prot=(0.0, 0.0, 0.0), spine=(0.0, 0.0, 0.0), air=0.0, look=(0.0, 1.0))),
]


def _fist_up(side, pos):
    sx = 1.0 if side == "L" else -1.0
    return hand_frame(side, pos, (-0.35 * sx, -0.9, 0.0), (0.15 * sx, 0.0, 1.0))


def _pump(pos):
    return hand_frame("R", pos, (0.35, 0.9, 0.1), (0.0, -0.2, 1.0))


def celebrate(t):
    k = track(t, CELEBRATE)
    base = idle_pose(0.0)
    fk = add(base["fk"], spine(*k["spine"]))
    air = k["air"]
    feet = {}
    for s, yaw in (("L", 5.0), ("R", -5.0)):
        ball = rest_ball(s) + Vector((0.0, 0.0, 0.13 * air))
        feet[s] = foot_from_ball(s, ball, 28.0 * air, yaw)
    spec = {
        "pelvis": {"loc": k["ploc"], "rot": k["prot"]},
        "fk": fk,
        "feet": feet,
        "toes": {"L": 20.0 * air, "R": 20.0 * air},
        "look": k["look"],
    }
    rest = fk_hands({**spec, "fk": add(idle_pose(0.0)["fk"], spine(*k["spine"]))})
    dz = k["ploc"][2] + 0.012
    up = {s: _fist_up(s, (0.27 * (1 if s == "L" else -1), -0.12, 2.02 + dz)) for s in ("L", "R")}
    pump_lo = _pump((-0.24, -0.3, 1.42 + dz))
    pump_hi = _fist_up("R", (-0.3, -0.14, 1.98 + dz))
    low = {s: m.copy() for s, m in rest.items()}
    for m in low.values():
        m.translation += Vector((0.0, 0.04, 0.05))
    lk = [(0.0, rest["L"]), (0.28, low["L"]), (0.48, up["L"], ease_out), (0.85, up["L"]), (1.1, rest["L"]),
          (2.0, rest["L"])]
    rk = [(0.0, rest["R"]), (0.28, low["R"]), (0.48, up["R"], ease_out), (0.85, up["R"]), (1.05, pump_lo, ease_out),
          (1.22, pump_hi), (1.4, pump_lo, ease_out), (2.0, rest["R"])]
    spec["hands"] = {"L": keys(t, lk), "R": keys(t, rk)}
    fist_l = keys(t, [(0.0, 0.0), (0.4, 1.0), (0.85, 1.0), (1.2, 0.0)])
    fist_r = keys(t, [(0.0, 0.0), (0.4, 1.0), (1.5, 1.0), (1.9, 0.0)])
    from .solver import blend_fingers
    spec["fingers"] = {"L": blend_fingers("relaxed", "fist", fist_l), "R": blend_fingers("grip", "fist", fist_r)}
    return spec


# ------------------------------------------------------------------ React

REACT = [
    (0.0, dict(ploc=(0.0, 0.0, -0.012), prot=(0.0, 0.0, 0.0), spine=(0.0, 0.0, 0.0), guard=0.0, look=(0.0, 1.0))),
    (0.12, dict(ploc=(0.0, 0.04, -0.04), prot=(-4.0, 6.0, 0.0), spine=(-10.0, 8.0, 0.0), guard=1.0,
                look=(18.0, -8.0)), ease_out),
    (0.32, dict(ploc=(0.0, 0.09, -0.06), prot=(-2.0, 8.0, 0.0), spine=(-6.0, 10.0, 0.0), guard=1.0,
                look=(22.0, -4.0))),
    (0.6, dict(ploc=(0.0, 0.08, -0.05), prot=(0.0, 6.0, 0.0), spine=(-2.0, 6.0, 0.0), guard=0.8, look=(10.0, 0.0))),
    (0.9, dict(ploc=(0.0, 0.02, -0.02), prot=(0.0, 1.0, 0.0), spine=(0.0, 1.0, 0.0), guard=0.1, look=(2.0, 1.0))),
    (1.1, dict(ploc=(0.0, 0.0, -0.012), prot=(0.0, 0.0, 0.0), spine=(0.0, 0.0, 0.0), guard=0.0, look=(0.0, 1.0))),
]


def _step(side, t, t0, t1, frm, to, yaw, h=0.07):
    """Foot stepping from ball offset ``frm`` to ``to`` between t0 and t1."""
    u = min(1.0, max(0.0, (t - t0) / (t1 - t0)))
    s = smooth(u)
    off = Vector(frm).lerp(Vector(to), s)
    ball = rest_ball(side) + off + Vector((0.0, 0.0, h * math.sin(math.pi * u)))
    return foot_from_ball(side, ball, 18.0 * math.sin(math.pi * u), yaw)


def react(t):
    k = track(t, REACT)
    base = idle_pose(0.0)
    fk = add(base["fk"], spine(*k["spine"]))
    fk = _arms(fk, add(STAND, GUARD), k["guard"])
    back = (0.0, 0.2, 0.0)
    if t < 0.5:
        foot_r = _step("R", t, 0.08, 0.3, (0.0, 0.0, 0.0), back, -12.0)
    else:
        foot_r = _step("R", t, 0.72, 0.95, back, (0.0, 0.0, 0.0), -5.0)
    from .solver import blend_fingers
    return {
        "pelvis": {"loc": k["ploc"], "rot": k["prot"]},
        "fk": fk,
        "feet": {"L": planted("L", yaw=5.0), "R": foot_r},
        "fingers": {"L": blend_fingers("relaxed", "spread", k["guard"]), "R": blend_fingers("grip", "spread", k["guard"])},
        "look": k["look"],
    }


# ------------------------------------------------------------------ Rest

def _knees(spec):
    from .solver import solve, world_pose
    s = dict(spec)
    s.pop("hands", None)
    w = world_pose(solve(s))
    return {side: w[f"calf.{side}"].translation.copy() for side in ("L", "R")}


def rest(t):
    """Catching breath: bent over with the hands on the knees."""
    T = 3.0
    br = wave(t, T / 3.0, 1.0)
    look = keys(t, [(0.0, (0.0, -24.0)), (1.5, (6.0, -20.0))], loop=T)
    spec = {
        "pelvis": {"loc": (0.0, 0.1, -0.15 + 0.004 * br), "rot": (22.0 + 1.0 * br, 0.0, 0.0)},
        "fk": add(STAND, spine(30.0 + 2.5 * br, 0.0, 0.0),
                  {"clavicle.L": (0.0, 0.0, 3.0 * br), "clavicle.R": (0.0, 0.0, 3.0 * br)}),
        "feet": stand_feet(width=0.04, yaw_out=12.0),
        "fingers": {"L": "relaxed", "R": "relaxed"},
        "look": look,
    }
    knees = _knees(spec)
    spec["hands"] = {
        "L": hand_frame("L", knees["L"] + Vector((0.01, -0.035, 0.1)), (0.0, 0.45, -0.9), (-0.35, -0.85, -0.4)),
        "R": hand_frame("R", knees["R"] + Vector((-0.01, -0.035, 0.1)), (0.0, 0.45, -0.9), (0.35, -0.85, -0.4)),
    }
    return spec


# ------------------------------------------------------------------ Sit

def sit(t):
    """Seated on a bench/box of seat_height, hands on the thighs, breathing."""
    T = 3.0
    ip = config.animation_spec()["interaction_points"]
    seat = Vector(ip["seat_point"])
    br = wave(t, T / 2.0, 1.0)
    look = keys(t, [(0.0, (0.0, 4.0)), (1.1, (18.0, 8.0)), (2.1, (-10.0, 2.0))], loop=T)
    hip_h = seat.z + 0.075
    drop = hip_h - 0.905
    spec = {
        "pelvis": {"loc": (0.0, seat.y, drop + 0.003 * br), "rot": (-8.0, 0.0, 0.0)},
        "fk": add(STAND, spine(10.0 + 1.2 * br, 0.0, 0.0)),
        "feet": {"L": planted("L", 0.04, -0.3, 8.0), "R": planted("R", -0.04, -0.3, -8.0)},
        "fingers": {"L": "relaxed", "R": "relaxed"},
        "look": look,
    }
    spec["hands"] = {
        "L": hand_frame("L", (0.13, -0.2, 0.6 + 0.002 * br), (0.0, 0.1, -1.0), (-0.2, -1.0, -0.1)),
        "R": hand_frame("R", (-0.13, -0.2, 0.6 + 0.002 * br), (0.0, 0.1, -1.0), (0.2, -1.0, -0.1)),
    }
    return spec


# ------------------------------------------------------------------ Death_or_Fall

FALL = [
    (0.0, dict(ploc=(0.0, 0.0, -0.012), prot=(0.0, 0.0, 0.0), spine=(0.0, 0.0, 0.0), arms=0.0, brace=0.0,
               look=(0.0, 1.0), kneel=0.0, prone=0.0)),
    (0.3, dict(ploc=(0.0, 0.03, -0.1), prot=(-6.0, 8.0, 4.0), spine=(-8.0, 10.0, 0.0), arms=1.0, brace=0.0,
               look=(20.0, -16.0), kneel=0.0, prone=0.0)),
    (0.65, dict(ploc=(0.0, 0.03, -0.44), prot=(8.0, 4.0, 0.0), spine=(18.0, 4.0, 0.0), arms=1.0, brace=0.2,
                look=(10.0, 10.0), kneel=1.0, prone=0.0), ease_in),
    (1.1, dict(ploc=(0.0, -0.36, -0.79), prot=(74.0, 0.0, -6.0), spine=(12.0, 0.0, 0.0), arms=0.0, brace=1.0,
               look=(55.0, -30.0), kneel=1.0, prone=1.0), ease_in),
    (1.25, dict(ploc=(0.0, -0.37, -0.765), prot=(72.0, 0.0, -6.0), spine=(11.0, 0.0, 0.0), arms=0.0, brace=0.6,
                look=(55.0, -28.0), kneel=1.0, prone=1.0), ease_out),
    (1.8, dict(ploc=(0.0, -0.37, -0.8), prot=(80.0, 0.0, -6.0), spine=(9.0, 0.0, 0.0), arms=0.0, brace=0.0,
               look=(62.0, -32.0), kneel=1.0, prone=1.0)),
]
LOOSE = {"upper_arm.L": (10.0, 0.0, -20.0), "upper_arm.R": (-5.0, 0.0, -10.0),
         "forearm.L": (30.0, 20.0, 0.0), "forearm.R": (20.0, 20.0, 0.0)}



def _fall_feet(k):
    feet = {}
    stand = stand_feet()
    y0 = k["ploc"][1]
    for s in ("L", "R"):
        sx = 1.0 if s == "L" else -1.0
        tuck = foot_frame(s, (0.1 * sx, 0.46 + y0, 0.085), yaw=4.0 * sx, pitch=-100.0)
        lie = foot_frame(s, (0.14 * sx, 0.8 + y0, 0.075), yaw=8.0 * sx, pitch=-105.0)
        f = stand[s] if k["kneel"] <= 0.0 else _mix(stand[s], tuck, k["kneel"])
        if k["prone"] > 0.0:
            f = _mix(tuck, lie, k["prone"])
        feet[s] = f
    return feet


def _mix(a, b, w):
    from .clipkit import flerp
    return flerp(a, b, w)


GROUND_HAND_Z = -0.015      # socket height that rests a palm-down hand on the ground


def _ground_hand(side, x, y, fingers=(0.0, -1.0, 0.0)):
    return hand_frame(side, (x, y, GROUND_HAND_Z), (0.0, 0.0, -1.0), fingers)


def death_or_fall(t):
    k = track(t, FALL)
    base = idle_pose(0.0)
    fk = add(base["fk"], spine(*k["spine"]))
    fk = _arms(fk, add(STAND, LOOSE), k["arms"])
    knee = {s: Vector((0.1 if s == "L" else -0.1, -2.0, -0.6)) for s in ("L", "R")}
    spec = {
        "pelvis": {"loc": k["ploc"], "rot": k["prot"]},
        "fk": fk,
        "feet": _fall_feet(k),
        "toes": {"L": -20.0 * k["kneel"], "R": -20.0 * k["kneel"]},
        "knee": knee,
        "fingers": {"L": "relaxed", "R": "relaxed"},
        "look": k["look"],
    }
    if t > 0.3:
        loose = fk_hands(spec)
        brace = {"L": _ground_hand("L", 0.26, -0.93, (-0.2, -1.0, 0.0)),
                 "R": _ground_hand("R", -0.26, -0.93, (0.2, -1.0, 0.0))}
        limp = {"L": _ground_hand("L", 0.36, -1.08, (0.1, -1.0, 0.0)),
                "R": _ground_hand("R", -0.3, -0.42, (0.0, 1.0, 0.0))}
        w = 0.2 * smooth((t - 0.3) / 0.35) + 0.8 * k["prone"]
        hands = {}
        for s in ("L", "R"):
            reach = keys(t, [(1.1, brace[s]), (1.8, limp[s])]) if t > 1.1 else brace[s]
            hands[s] = loose[s] if w <= 0.0 else _mix(loose[s], reach, w)
        spec["hands"] = hands
        # Reaching for the floor while falling may over-extend; from landing on
        # the hands are real ground contacts again (reach is validated).
        spec["soft_hands"] = t < 1.05
    return spec


CLIPS = {
    "Celebrate": celebrate,
    "React": react,
    "Rest": rest,
    "Sit": sit,
    "Death_or_Fall": death_or_fall,
}
