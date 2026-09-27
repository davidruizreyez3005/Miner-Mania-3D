"""Tool clips: Mine, Mine_Heavy, Dig, Drill, Hammer.

Tool motion is authored as hand_tool.R socket keyframes (grip point, handle
direction, working-face direction). Two-handed tools derive the left hand from
the grip contract in animation_clips.json, so both hands stay on the handle
(re-checked on the exported GLB). Impact keys coincide with the contract's
``events`` times and land the working face on the standard interaction points.
"""

import math

from mathutils import Quaternion, Vector

from .clipkit import STAND, add, ease_in, ease_out, hand_frame, keys, linear, planted, tool_frame, wave


def track(t, frames, loop=None):
    """Interpolate [(time, {field: value}[, ease]), ...] keyframes field-wise."""
    out = {}
    for f in frames[0][1]:
        pts = [(k[0], k[1][f]) + ((k[2],) if len(k) > 2 else ()) for k in frames]
        out[f] = keys(t, pts, loop=loop)
    return out


def spine(flex, twist, side=0.0):
    """Distribute a trunk rotation over the three spine bones."""
    return {"spine_01": (flex * 0.4, twist * 0.35, side * 0.4),
            "spine_02": (flex * 0.35, twist * 0.35, side * 0.35),
            "spine_03": (flex * 0.25, twist * 0.3, side * 0.25)}


def _n(*v):
    return Vector(v).normalized()


def _feet(l=(0.03, -0.13, 14.0), r=(-0.05, 0.11, -26.0)):
    return {"L": planted("L", *l), "R": planted("R", *r)}


def _upper(k):
    fk = add(STAND, spine(*k["spine"]),
             {"clavicle.L": (0.0, 0.0, k["clav"]), "clavicle.R": (0.0, 0.0, k["clav"])})
    return fk


# ------------------------------------------------------------------ Mine

def _pick(grip, handle, face):
    return tool_frame(grip, _n(*handle), _n(*face))


MINE_KEYS = [
    (0.0, dict(sock=_pick((-0.14, 0.04, 1.72), (0, 0.75, 0.66), (0, -0.66, 0.75)),
               ploc=(0.0, 0.03, -0.06), prot=(-3.0, -10.0, 0.0), spine=(-6.0, -14.0, 0.0), look=(4.0, 8.0), clav=6.0)),
    (0.3, dict(sock=_pick((-0.13, 0.08, 1.76), (0, 0.85, 0.52), (0, -0.52, 0.85)),
               ploc=(0.0, 0.04, -0.055), prot=(-4.0, -12.0, 0.0), spine=(-8.0, -16.0, 0.0), look=(4.0, 6.0), clav=8.0)),
    (0.62, dict(sock=_pick((-0.1, -0.28, 1.52), (0, -0.35, 0.94), (0, -0.94, -0.35)),
                ploc=(0.0, 0.0, -0.08), prot=(3.0, -2.0, 0.0), spine=(10.0, -4.0, 0.0), look=(2.0, 16.0), clav=4.0),
     ease_in),
    (0.8, dict(sock=_pick((-0.05, -0.46, 0.88), (0, -0.99, 0.12), (0, -0.12, -0.99)),
               ploc=(0.0, -0.03, -0.12), prot=(8.0, 4.0, 0.0), spine=(26.0, 4.0, 0.0), look=(0.0, 25.0), clav=0.0),
     linear),
    (0.95, dict(sock=_pick((-0.05, -0.44, 0.92), (0, -0.93, 0.36), (0, -0.36, -0.93)),
                ploc=(0.0, -0.025, -0.115), prot=(7.0, 3.0, 0.0), spine=(24.0, 3.0, 0.0), look=(0.0, 22.0), clav=0.0),
     ease_out),
    (1.25, dict(sock=_pick((-0.1, -0.22, 1.32), (0, -0.3, 0.95), (0, -0.95, -0.3)),
                ploc=(0.0, 0.0, -0.08), prot=(2.0, -4.0, 0.0), spine=(8.0, -6.0, 0.0), look=(2.0, 14.0), clav=3.0)),
]

HEAVY_KEYS = [
    (0.0, dict(sock=_pick((-0.07, -0.42, 0.9), (0, -0.85, 0.52), (0, -0.52, -0.85)),
               ploc=(0.0, -0.02, -0.12), prot=(6.0, 0.0, 0.0), spine=(18.0, 0.0, 0.0), look=(0.0, 20.0), clav=0.0)),
    (0.45, dict(sock=_pick((-0.14, -0.12, 1.45), (0, 0.2, 0.98), (0, -0.98, 0.2)),
                ploc=(0.0, 0.02, -0.08), prot=(0.0, -10.0, 0.0), spine=(2.0, -14.0, 0.0), look=(3.0, 10.0), clav=5.0)),
    (0.8, dict(sock=_pick((-0.15, 0.1, 1.8), (0, 0.6, 0.8), (0, -0.8, 0.6)),
               ploc=(0.0, 0.05, -0.06), prot=(-4.0, -16.0, 0.0), spine=(-10.0, -20.0, 0.0), look=(4.0, 6.0), clav=10.0)),
    (0.95, dict(sock=_pick((-0.15, 0.12, 1.82), (0, 0.66, 0.75), (0, -0.75, 0.66)),
                ploc=(0.0, 0.055, -0.06), prot=(-5.0, -17.0, 0.0), spine=(-11.0, -21.0, 0.0), look=(4.0, 8.0), clav=10.0)),
    (1.08, dict(sock=_pick((-0.1, -0.3, 1.5), (0, -0.4, 0.92), (0, -0.92, -0.4)),
                ploc=(0.0, 0.0, -0.1), prot=(4.0, -3.0, 0.0), spine=(14.0, -5.0, 0.0), look=(1.0, 20.0), clav=4.0),
     ease_in),
    (1.2, dict(sock=_pick((-0.04, -0.48, 0.7), (0, -0.97, -0.23), (0, 0.23, -0.97)),
               ploc=(0.0, -0.04, -0.2), prot=(10.0, 6.0, 0.0), spine=(36.0, 6.0, 0.0), look=(0.0, 30.0), clav=0.0),
     linear),
    (1.36, dict(sock=_pick((-0.05, -0.46, 0.75), (0, -0.96, 0.05), (0, -0.05, -0.96)),
                ploc=(0.0, -0.035, -0.19), prot=(9.0, 5.0, 0.0), spine=(34.0, 5.0, 0.0), look=(0.0, 28.0), clav=0.0),
     ease_out),
    (1.75, dict(sock=_pick((-0.06, -0.44, 0.84), (0, -0.9, 0.4), (0, -0.4, -0.9)),
                ploc=(0.0, -0.025, -0.14), prot=(7.0, 1.0, 0.0), spine=(22.0, 1.0, 0.0), look=(0.0, 22.0), clav=0.0)),
]


def _swing(t, frames, period, feet):
    k = track(t, frames, loop=period)
    return {
        "pelvis": {"loc": k["ploc"], "rot": k["prot"]},
        "fk": _upper(k),
        "feet": feet,
        "hands": {"R": k["sock"]},
        "grip": "pickaxe",
        "fingers": {"L": "grip", "R": "grip"},
        "look": k["look"],
    }


def mine(t):
    return _swing(t, MINE_KEYS, 1.6, _feet())


def mine_heavy(t):
    return _swing(t, HEAVY_KEYS, 2.2, _feet(l=(0.05, -0.15, 16.0), r=(-0.07, 0.12, -28.0)))


# ------------------------------------------------------------------ Dig

SHOVEL_TIP = 0.93      # grip-space distance from the main grip to the blade tip


def _shovel(grip, handle, roll=0.0):
    """Socket frame for the shovel: main grip at ``grip``, shaft toward the
    blade along ``handle``. The right hand holds underhand (fingers across the
    shaft, palm and blade scoop facing up), which makes the left hand overhand
    through the shared grip contract; ``roll`` turns the scoop about the shaft
    (tossing). The shaft crosses the body so the top (left) hand stays in
    front of the belly."""
    h = _n(*handle)
    up = Vector((0.0, 0.0, 1.0))
    fingers = up.cross(h).normalized()
    if roll:
        fingers = Quaternion(h, math.radians(roll)) @ fingers
    return tool_frame(Vector(grip), h, fingers)


DIG_KEYS = [
    (0.0, dict(sock=_shovel((-0.16, -0.31, 0.77), (-0.1, -0.62, -0.78)),
               ploc=(0.0, 0.045, -0.14), prot=(9.0, -2.0, 0.0), spine=(21.0, -3.0, 0.0), look=(-6.0, 26.0), clav=0.0)),
    (0.55, dict(sock=_shovel((-0.165, -0.361, 0.701), (-0.1, -0.62, -0.78)),
                ploc=(0.0, 0.05, -0.17), prot=(11.0, -2.0, 0.0), spine=(25.0, -3.0, 0.0), look=(-6.0, 28.0), clav=0.0),
     ease_in),
    (0.85, dict(sock=_shovel((-0.165, -0.335, 0.84), (-0.1, -0.78, -0.6)),
                ploc=(0.0, 0.045, -0.12), prot=(8.0, -2.0, 0.0), spine=(19.0, -3.0, 0.0), look=(-6.0, 24.0), clav=0.0)),
    (1.15, dict(sock=_shovel((-0.17, -0.4, 0.95), (-0.3, -0.9, -0.3)),
                ploc=(0.0, 0.05, -0.09), prot=(6.0, -3.0, 0.0), spine=(16.0, -4.0, 0.0), look=(-10.0, 16.0), clav=2.0)),
    (1.45, dict(sock=_shovel((-0.22, -0.36, 0.98), (-0.8, -0.5, -0.2), roll=-100.0),
                ploc=(0.0, 0.02, -0.07), prot=(2.0, -8.0, 0.0), spine=(6.0, -12.0, 0.0), look=(-24.0, 14.0), clav=2.0),
     ease_out),
    (1.75, dict(sock=_shovel((-0.17, -0.36, 0.83), (-0.3, -0.72, -0.62), roll=-25.0),
                ploc=(0.0, 0.035, -0.1), prot=(6.0, -3.0, 0.0), spine=(13.0, -5.0, 0.0), look=(-8.0, 22.0), clav=0.0)),
]


def dig(t):
    k = track(t, DIG_KEYS, loop=2.0)
    return {
        "pelvis": {"loc": k["ploc"], "rot": k["prot"]},
        "fk": _upper(k),
        "feet": _feet(l=(0.04, -0.14, 12.0), r=(-0.06, 0.1, -24.0)),
        "hands": {"R": k["sock"]},
        "grip": "shovel",
        "fingers": {"L": "grip", "R": "grip"},
        "look": k["look"],
    }


# ------------------------------------------------------------------ Drill

def drill(t):
    """Jackhammer held on both T-bar handles, bit on the ground, vibrating."""
    T = 1.2
    buzz = wave(t, T / 5.0, 1.0)
    buzz2 = wave(t, T / 5.0, 1.0, 0.25)
    sway = wave(t, T, 1.0)
    grip = Vector((-0.18 + 0.004 * sway, -0.36, 0.905 + 0.007 * buzz))
    handle = _n(1.0, 0.0, 0.02 * buzz2)
    sock = tool_frame(grip, handle, (0.0, -1.0, 0.0))
    fk = add(STAND, spine(14.0 + 0.8 * buzz, 1.5 * sway, 0.0),
             {"clavicle.L": (0.0, 0.0, -1.0 + 0.6 * buzz), "clavicle.R": (0.0, 0.0, -1.0 + 0.6 * buzz)})
    return {
        "pelvis": {"loc": (0.004 * sway, 0.02, -0.08 + 0.003 * buzz), "rot": (4.0, 0.0, 0.0)},
        "fk": fk,
        "feet": _feet(l=(0.05, -0.06, 12.0), r=(-0.05, 0.06, -12.0)),
        "hands": {"R": sock},
        "grip": "jackhammer",
        "fingers": {"L": "grip", "R": "grip"},
        "look": (2.0 * sway, 22.0 + 1.0 * buzz),
    }


# ------------------------------------------------------------------ Hammer

HAMMER_HEAD = 0.245     # grip-space height of the hammer head
HAMMER_FACE = 0.0525    # striking face offset toward the working face


def _hammer(face_point, handle, face):
    h, f = _n(*handle), _n(*face)
    grip = Vector(face_point) - h * HAMMER_HEAD - f * HAMMER_FACE
    return tool_frame(grip, h, f)


def _surface():
    from core import config
    return Vector(config.animation_spec()["interaction_points"]["hammer_surface"])


HAMMER_KEYS = None


def _hammer_keys():
    global HAMMER_KEYS
    if HAMMER_KEYS is None:
        s = _surface()
        rest = tool_frame(s + Vector((0.0, 0.245 - 0.0, 0.065)), _n(0, -0.97, 0.24), _n(0, -0.24, -0.97))
        HAMMER_KEYS = [
            (0.0, dict(sock=rest, spine=(10.0, 4.0, 0.0), ploc=(0.0, 0.0, -0.05), look=(-4.0, 24.0), clav=0.0)),
            (0.25, dict(sock=tool_frame(s + Vector((-0.03, 0.38, 0.39)), _n(0, 0.26, 0.97), _n(0, -0.97, 0.26)),
                        spine=(6.0, 0.0, 0.0), ploc=(0.0, 0.0, -0.045), look=(-4.0, 22.0), clav=4.0)),
            (0.45, dict(sock=_hammer(s, (0, -1, 0), (0, 0, -1)), spine=(12.0, 5.0, 0.0), ploc=(0.0, -0.005, -0.055),
                        look=(-4.0, 26.0), clav=0.0), ease_in),
            (0.55, dict(sock=tool_frame(s + Vector((0.0, 0.25, 0.08)), _n(0, -0.95, 0.31), _n(0, -0.31, -0.95)),
                        spine=(11.0, 4.5, 0.0), ploc=(0.0, 0.0, -0.052), look=(-4.0, 25.0), clav=0.0), ease_out),
            (0.8, dict(sock=rest, spine=(10.0, 4.0, 0.0), ploc=(0.0, 0.0, -0.05), look=(-4.0, 24.0), clav=0.0)),
        ]
    return HAMMER_KEYS


def hammer(t):
    k = track(t, _hammer_keys(), loop=1.0)
    s = _surface()
    hold = hand_frame("L", s + Vector((0.16, 0.1, -0.02)), (0.0, 0.0, -1.0), (-0.35, -0.94, 0.0))
    return {
        "pelvis": {"loc": k["ploc"], "rot": (4.0, 2.0, 0.0)},
        "fk": _upper(k),
        "feet": _feet(l=(0.03, -0.08, 10.0), r=(-0.04, 0.06, -16.0)),
        "hands": {"R": k["sock"], "L": hold},
        "fingers": {"L": "flat", "R": "grip"},
        "look": k["look"],
    }


CLIPS = {
    "Mine": mine,
    "Mine_Heavy": mine_heavy,
    "Dig": dig,
    "Drill": drill,
    "Hammer": hammer,
}
