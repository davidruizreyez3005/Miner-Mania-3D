"""Machine interaction clips: Operate, Interact, Pull_Lever, Inspect, Push, Pull.

Hands target the standard interaction points in animation_clips.json, so a
machine that places its controls (socket_operate, socket_button, ...) at those
offsets from the worker's standing spot lines up with the animation. Push and
Pull keep both hands on a bar fixed relative to the root (cart_bar/pull_bar
grips) while the feet walk in place at the clip's root-motion speed.
"""

import math

from mathutils import Matrix, Vector

from core import config

from .clipkit import STAND, Gait, add, ease_in, ease_out, hand_frame, keys, smooth, stand_feet, tool_frame, wave
from .locomotion import idle_hand_frames, idle_pose
from .mining import spine, track
from .rig_model import mirrored, model
from .solver import FINGER_PRESETS, blend_fingers


def _points():
    return config.animation_spec()["interaction_points"]


# ------------------------------------------------------------------ Operate

def _lever(side, angle):
    """Hand socket on an operating lever knob; ``angle`` > 0 pushes forward."""
    ip = _points()
    knob = Vector(ip["operate_levers"][0 if side == "L" else 1])
    pivot = Vector((knob.x, knob.y, ip["operate_lever_pivot_height"]))
    length = knob.z - pivot.z
    a = math.radians(angle)
    up = Vector((0.0, -math.sin(a), math.cos(a)))
    fwd = Vector((0.0, -math.cos(a), -math.sin(a)))
    return tool_frame(pivot + up * length, up, fwd)


def operate(t):
    T = 2.4
    base = idle_pose(t, T, breath=0.8)
    a_l = keys(t, [(0.0, 0.0), (0.45, 18.0), (0.85, 18.0), (1.2, 0.0)], loop=T)
    a_r = keys(t, [(0.0, 0.0), (1.2, 0.0), (1.65, -16.0), (2.05, -16.0)], loop=T)
    lean = keys(t, [(0.0, 0.0), (0.45, 1.0), (0.85, 1.0), (1.2, 0.0), (1.65, -0.6), (2.05, -0.6)], loop=T)
    base["fk"] = add(base["fk"], spine(8.0 + 3.0 * lean, 3.0 * lean, 0.0))
    base["pelvis"]["loc"] = (base["pelvis"]["loc"][0], -0.01 * lean, -0.03)
    base["hands"] = {"L": _lever("L", a_l), "R": _lever("R", a_r)}
    base["fingers"] = {"L": "grip", "R": "grip"}
    base["look"] = (keys(t, [(0.0, 6.0), (0.9, 6.0), (1.3, -8.0), (2.1, -8.0)], loop=T), 14.0)
    return base


# ------------------------------------------------------------------ Interact

_TIP = None


def _index_tip():
    """Index fingertip of the 'point' preset in hand_tool.R socket space."""
    global _TIP
    if _TIP is None:
        m = model()
        rot = {}
        for f, vals in FINGER_PRESETS["point"].items():
            for i, ang in enumerate(vals):
                b = f"{f}_{i + 1:02d}.R"
                rot[b] = mirrored(b, ang, 0.0, 0.0)
        w = m.fk(rot)
        tip = w["index_03.R"] @ Vector((0.0, m.length["index_03.R"], 0.0))
        _TIP = w["hand_tool.R"].inverted() @ tip
    return _TIP.copy()


def _press_frame(point, back=0.0):
    orient = hand_frame("R", (0.0, 0.0, 0.0), (0.0, 0.25, -0.97), (0.0, -1.0, -0.1))
    rot = orient.to_3x3()
    m = orient.copy()
    m.translation = Vector(point) - rot @ _index_tip() + Vector((0.0, back, 0.0))
    return m


def interact(t):
    base = idle_pose(0.0)
    idle = idle_hand_frames()
    button = _points()["button"]
    near = _press_frame(button, back=0.06)
    press = _press_frame(button)
    sock = keys(t, [(0.0, idle["R"]), (0.38, near), (0.5, press, ease_in), (0.66, press), (0.8, near, ease_out),
                    (1.2, idle["R"])])
    w = keys(t, [(0.0, 0.0), (0.3, 1.0), (0.85, 1.0), (1.15, 0.0)])
    lean = keys(t, [(0.0, 0.0), (0.45, 1.0), (0.7, 1.0), (1.1, 0.0)])
    base["fk"] = add(base["fk"], spine(5.0 * lean, 5.0 * lean, 0.0))
    base["hands"] = {"R": sock}
    base["fingers"] = {"L": "relaxed", "R": blend_fingers("relaxed", "point", w)}
    base["look"] = (-6.0 * lean, 4.0 + 16.0 * lean)
    return base


# ------------------------------------------------------------------ Pull_Lever

def _lever_handle(angle):
    ip = _points()
    pivot = Vector(ip["lever_pivot"])
    top = Vector(ip["lever_handle_top"])
    length = (top - pivot).length
    a = math.radians(angle)
    r = Vector((0.0, math.sin(a), math.cos(a)))
    tangent = Vector((0.0, math.cos(a), -math.sin(a)))
    return hand_frame("R", pivot + r * length, -r, -tangent)


def pull_lever(t):
    base = idle_pose(0.0)
    idle = idle_hand_frames()
    a0 = math.degrees(math.atan2(*(Vector(_points()["lever_handle_top"]) - Vector(_points()["lever_pivot"])).yz))
    reach = _lever_handle(a0)
    near = reach.copy()
    near.translation += Vector((0.0, 0.05, -0.04))
    ang = keys(t, [(0.0, a0), (0.45, a0), (1.0, 110.0, ease_in), (1.6, 110.0)])
    on = _lever_handle(ang)
    off = on.copy()
    off.translation += Vector((0.0, 0.06, -0.03))
    sock = keys(t, [(0.0, idle["R"]), (0.32, near), (0.45, reach)]) if t < 0.45 else (
        on if t <= 1.05 else keys(t, [(1.05, on), (1.2, off), (1.6, idle["R"])]))
    w = keys(t, [(0.0, 0.0), (0.35, 1.0), (1.05, 1.0), (1.25, 0.0)])
    pull = keys(t, [(0.0, 0.0), (0.45, 0.0), (1.0, 1.0), (1.2, 1.0), (1.6, 0.0)])
    reach_up = keys(t, [(0.0, 0.0), (0.4, 1.0), (0.6, 1.0), (1.0, 0.0)])
    base["fk"] = add(base["fk"], spine(-4.0 * reach_up + 10.0 * pull, 6.0 * pull, 0.0),
                     {"clavicle.R": (0.0, 0.0, 10.0 * reach_up)})
    base["pelvis"]["loc"] = (0.0, 0.02 * pull, -0.012 - 0.04 * pull)
    base["hands"] = {"R": sock}
    base["fingers"] = {"L": "relaxed", "R": blend_fingers("relaxed", "grip", w)}
    base["look"] = (-8.0, -14.0 * reach_up + 10.0 * pull)
    return base


# ------------------------------------------------------------------ Inspect

def inspect(t):
    """Hands on hips, leaning in and looking the machine over."""
    T = 3.2
    base = idle_pose(t, T, breath=0.9)
    lean = keys(t, [(0.0, 0.2), (0.8, 1.0), (1.6, 0.6), (2.4, 1.0)], loop=T)
    base["fk"] = add(base["fk"], spine(10.0 * lean, 0.0, 0.0))
    base["hands"] = {
        "L": hand_frame("L", (0.155, 0.0, 1.0), (-1.0, 0.0, -0.25), (0.0, -0.55, -0.85)),
        "R": hand_frame("R", (-0.155, 0.0, 1.0), (1.0, 0.0, -0.25), (0.0, -0.55, -0.85)),
    }
    base["fingers"] = {"L": "relaxed", "R": "relaxed"}
    base["look"] = keys(t, [(0.0, (0.0, 10.0)), (0.8, (24.0, 18.0)), (1.6, (0.0, 24.0)), (2.4, (-24.0, 16.0))],
                        loop=T)
    return base


# ------------------------------------------------------------------ Push / Pull

def _bar_hands(grip):
    offs = config.animation_spec()["grips"][grip]["offsets"]
    return {s: hand_frame(s, o, (0.0, 0.25, -0.97), (0.0, -0.97, -0.25)) for s, o in zip(("L", "R"), offs)}


def _bar_walk(t, T, v, grip, lean, pelvis_y, pelvis_z, stance, step):
    g = Gait(T, v, stance=stance, step_height=step, heel_strike=8.0, toe_off=16.0)
    feet, toes = {}, {}
    for s in ("L", "R"):
        f, toe, _ = g.foot(s, t)
        feet[s] = f
        toes[s] = toe
    ph = (t / T) % 1.0
    c2 = math.cos(4.0 * math.pi * ph)
    bob = -0.012 * (0.5 + 0.5 * c2)
    sway = -0.01 * math.sin(2.0 * math.pi * ph)
    yaw = 3.0 * math.cos(2.0 * math.pi * ph)
    fk = add(STAND, spine(lean, -0.6 * yaw, 0.0), {"neck": (-lean * 0.3, 0.0, 0.0), "head": (-lean * 0.4, 0.0, 0.0)})
    return {
        "pelvis": {"loc": (sway, pelvis_y, pelvis_z + bob), "rot": (lean * 0.4, yaw, 0.0)},
        "fk": fk,
        "feet": feet,
        "toes": toes,
        "hands": _bar_hands(grip),
        "fingers": {"L": "grip", "R": "grip"},
    }


def _speed(name):
    return config.animation_spec()["clips"][name]["root_motion"]["speed_mps"]


def push(t):
    return _bar_walk(t, 1.2, _speed("Push"), "cart_bar", lean=14.0, pelvis_y=-0.02, pelvis_z=-0.07,
                     stance=0.65, step=0.05)


def pull(t):
    return _bar_walk(t, 1.4, _speed("Pull"), "pull_bar", lean=2.0, pelvis_y=0.03, pelvis_z=-0.08,
                     stance=0.65, step=0.045)


CLIPS = {
    "Operate": operate,
    "Interact": interact,
    "Pull_Lever": pull_lever,
    "Inspect": inspect,
    "Push": push,
    "Pull": pull,
}
