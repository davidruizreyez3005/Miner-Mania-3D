"""Carry clips: Pick_Up, Put_Down, Carry, Carry_Walk, Load, Unload.

The carried prop hangs from ``carry_attachment`` (box bottom centre, item up
= socket Y); both hands hold its side hand-holds at the ``carry_box`` grip
offsets, so any prop built to the standard carry size (prop_crate_carry_01)
sits between the palms. Pick_Up starts with the socket on the ground at the
``pickup_point``; Load leaves it on the ``load_surface``. Put_Down and Unload
are the exact time reversals of Pick_Up and Load, so their grip windows
mirror each other.
"""

import math

from mathutils import Matrix, Vector

from core import config

from .clipkit import STAND, add, carry_frame, ease_in, ease_out, keys, offset_frame, stand_feet, wave
from .locomotion import idle_hand_frames, idle_pose, walk_pose
from .mining import spine, track

CARRY_POS = Vector((0.0, -0.32, 0.84))      # box bottom centre while carried


def _points():
    return config.animation_spec()["interaction_points"]


_FINGERS_DOWN = Matrix.Rotation(math.radians(90.0), 4, "X")


def box_hands(box):
    """Hand sockets on the hand-holds: palms in, thumbs forward, fingers down
    along the sides (wrists above the holds)."""
    offs = config.animation_spec()["grips"]["carry_box"]["offsets"]
    return {"L": offset_frame(box, offs[0]) @ _FINGERS_DOWN, "R": offset_frame(box, offs[1]) @ _FINGERS_DOWN}


def _released(box, out=0.07, back=0.04):
    """Hands just off the hand-holds (moved outward and back)."""
    h = box_hands(box)
    shift = {"L": box.to_3x3() @ Vector((out, 0.0, -back)), "R": box.to_3x3() @ Vector((-out, 0.0, -back))}
    for s in h:
        h[s].translation += shift[s]
    return h


def carry(t):
    T = 2.0
    base = idle_pose(t, T, breath=1.2)
    br = wave(t, T / 2.0, 1.0)
    box = carry_frame(CARRY_POS + Vector((0.0, 0.0, 0.004 * br)))
    base["fk"] = add(base["fk"], spine(-5.0, 0.0, 0.0))
    base["carry"] = box
    base["hands"] = box_hands(box)
    base["fingers"] = {"L": "carry", "R": "carry"}
    base["look"] = (3.0 * wave(t, T, 1.0, 0.3), 2.0 + 1.0 * br)
    return base


def carry_walk(t):
    T = 1.1
    spec = walk_pose(t, T, _speed("Carry_Walk"), lean=-3.0, carry=True)
    px, _, pz = spec["pelvis"]["loc"]
    box = carry_frame(CARRY_POS + Vector((px * 0.6, 0.0, pz + 0.045)))
    spec["carry"] = box
    spec["hands"] = box_hands(box)
    spec["fingers"] = {"L": "carry", "R": "carry"}
    return spec


def _speed(name):
    return config.animation_spec()["clips"][name]["root_motion"]["speed_mps"]


# ------------------------------------------------------------------ Pick_Up / Put_Down

PICK_BODY = [
    (0.0, dict(ploc=(0.0, 0.0, -0.012), prot=(0.0, 0.0, 0.0), spine=(0.0, 0.0, 0.0), look=(0.0, 6.0))),
    (0.45, dict(ploc=(0.0, 0.15, -0.54), prot=(16.0, 0.0, 0.0), spine=(44.0, 0.0, 0.0), look=(0.0, 16.0))),
    (0.62, dict(ploc=(0.0, 0.15, -0.55), prot=(16.0, 0.0, 0.0), spine=(45.0, 0.0, 0.0), look=(0.0, 16.0))),
    (1.1, dict(ploc=(0.0, 0.08, -0.26), prot=(9.0, 0.0, 0.0), spine=(22.0, 0.0, 0.0), look=(0.0, 14.0))),
    (1.6, dict(ploc=(0.0, 0.0, -0.02), prot=(0.0, 0.0, 0.0), spine=(-5.0, 0.0, 0.0), look=(0.0, 3.0))),
]


def pick_up(t):
    ground = carry_frame(Vector(_points()["pickup_point"]))
    b = track(t, PICK_BODY)
    box = keys(t, [(0.0, ground), (0.55, ground), (1.1, carry_frame((0.0, -0.4, 0.5))),
                   (1.6, carry_frame(CARRY_POS), ease_out)])
    idle = idle_hand_frames()
    rel = _released(ground, out=0.08, back=0.02)
    grab = box_hands(box)
    hands = {s: (keys(t, [(0.0, idle[s]), (0.1, idle[s]), (0.47, rel[s]), (0.55, grab[s])]) if t < 0.55 else grab[s])
             for s in ("L", "R")}
    fk = add(STAND, spine(*b["spine"]))
    w = min(1.0, max(0.0, (t - 0.35) / 0.2))
    return {
        "pelvis": {"loc": b["ploc"], "rot": b["prot"]},
        "fk": fk,
        "feet": stand_feet(width=0.03, yaw_out=12.0),
        "hands": hands,
        "carry": box,
        "fingers": {s: _blend("relaxed", "carry", w) for s in ("L", "R")},
        "look": b["look"],
    }


def put_down(t):
    return pick_up(1.6 - t)


def _blend(a, b, w):
    from .solver import blend_fingers
    return blend_fingers(a, b, w)


# ------------------------------------------------------------------ Load / Unload

LOAD_BODY = [
    (0.0, dict(ploc=(0.0, 0.0, -0.02), prot=(0.0, 0.0, 0.0), spine=(-5.0, 0.0, 0.0), look=(0.0, 3.0))),
    (0.5, dict(ploc=(0.0, -0.02, -0.03), prot=(2.0, 0.0, 0.0), spine=(6.0, 0.0, 0.0), look=(0.0, 10.0))),
    (1.0, dict(ploc=(0.0, -0.03, -0.045), prot=(4.0, 0.0, 0.0), spine=(14.0, 0.0, 0.0), look=(0.0, 16.0))),
    (1.25, dict(ploc=(0.0, -0.01, -0.035), prot=(2.0, 0.0, 0.0), spine=(8.0, 0.0, 0.0), look=(0.0, 12.0))),
    (1.8, dict(ploc=(0.0, 0.0, -0.012), prot=(0.0, 0.0, 0.0), spine=(0.0, 0.0, 0.0), look=(0.0, 4.0))),
]


def load(t):
    surface = carry_frame(Vector(_points()["load_surface"]))
    b = track(t, LOAD_BODY)
    box = keys(t, [(0.0, carry_frame(CARRY_POS)), (0.5, carry_frame((0.0, -0.4, 1.0))), (1.0, surface)])
    grab = box_hands(box)
    rel = _released(surface)
    idle = idle_hand_frames()
    hands = {s: (grab[s] if t <= 1.0 else keys(t, [(1.0, grab[s]), (1.25, rel[s]), (1.8, idle[s])]))
             for s in ("L", "R")}
    w = 1.0 - min(1.0, max(0.0, (t - 1.0) / 0.3))
    return {
        "pelvis": {"loc": b["ploc"], "rot": b["prot"]},
        "fk": add(STAND, spine(*b["spine"])),
        "feet": stand_feet(),
        "hands": hands,
        "carry": box,
        "fingers": {s: _blend("relaxed", "carry", w) for s in ("L", "R")},
        "look": b["look"],
    }


def unload(t):
    return load(1.8 - t)


CLIPS = {
    "Pick_Up": pick_up,
    "Put_Down": put_down,
    "Carry": carry,
    "Carry_Walk": carry_walk,
    "Load": load,
    "Unload": unload,
}
