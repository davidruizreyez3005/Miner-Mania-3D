"""Repair: kneel on the right knee and turn a bolt with a wrench (ratchet loop).

The wrench jaw stays on the ``repair_bolt`` interaction point while the handle
sweeps 60 degrees clockwise (as seen by the worker), comes off the bolt, swings
back and re-engages. Tool grip space (tools.py): jaw 0.19 m up the handle and
0.035 m toward the working face; the flat of the wrench is the socket X axis,
which for the right hand is the palm normal.
"""

import math

from mathutils import Vector

from core import config

from .clipkit import STAND, add, foot_from_ball, hand_frame, keys, planted, rest_ball, tool_frame, wave
from .mining import spine, track

JAW_UP = 0.19
JAW_FACE = 0.035


def _wrench(bolt, angle, off):
    a = math.radians(angle)
    handle = Vector((math.cos(a), 0.0, math.sin(a)))      # hand -> jaw, in the machine face plane
    palm = Vector((0.0, -1.0, 0.0))                        # toward the machine: wrench flat on the bolt
    face = palm.cross(handle)
    grip = Vector(bolt) - handle * JAW_UP - face * JAW_FACE + Vector((0.0, off, 0.0))
    return tool_frame(grip, handle, face)


def _kneel_feet():
    ball_r = rest_ball("R") + Vector((0.0, 0.46, 0.0))
    return ({"L": planted("L", 0.02, -0.38, 8.0), "R": foot_from_ball("R", ball_r, 68.0, -4.0)},
            {"R": 62.0})


def repair(t):
    T = 2.0
    bolt = config.animation_spec()["interaction_points"]["repair_bolt"]
    angle = keys(t, [(0.0, -30.0), (0.9, 30.0), (1.1, 30.0), (1.7, -30.0)], loop=T)
    off = keys(t, [(0.0, 0.0), (0.85, 0.0), (1.05, 0.045), (1.65, 0.045), (1.85, 0.0)], loop=T)
    effort = keys(t, [(0.0, 0.0), (0.45, 1.0), (0.9, 0.3), (1.2, 0.0)], loop=T)
    br = wave(t, T, 1.0)
    feet, toes = _kneel_feet()
    fk = add(STAND, spine(19.0 + 3.0 * effort, 6.0 + 2.0 * effort, 0.0))
    return {
        "pelvis": {"loc": (0.0, 0.07, -0.43 + 0.004 * br), "rot": (6.0, -4.0, 0.0)},
        "fk": fk,
        "feet": feet,
        "toes": toes,
        "hands": {"R": _wrench(bolt, angle, off),
                  "L": hand_frame("L", (0.13, -0.3, 0.53), (0.0, 0.3, -0.95), (-0.25, -0.95, -0.3))},
        "fingers": {"L": "relaxed", "R": "grip"},
        "look": (4.0, 18.0 + 2.0 * effort),
    }


CLIPS = {"Repair": repair}
