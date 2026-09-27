"""Pose solver: clip pose specs -> local bone rotations/locations.

A pose spec is a dict produced by a clip function for one instant:

    root:    {"yaw": deg}                     root-motion rotation (turn clips)
    pelvis:  {"loc": (x, y, z), "rot": (flex, twist, side)}
    fk:      {bone: (flex, twist, side)}      semantic local rotations (degrees)
    feet:    {"L": ankle_frame, "R": ...}     armature-space targets (foot IK)
    toes:    {"L": deg, "R": deg}
    knee:    {"L": pole, ...}                 optional pole points
    hands:   {"R": socket_frame, ...}          hand_tool socket targets (arm IK)
    elbow:   {"L": pole, ...}
    grip:    "pickaxe" | ...                  left hand derived from the right socket
    fingers: {"L": preset | dict, "R": ...}
    carry:   frame                            carry_attachment target
    look:    (yaw, pitch)                     distributed over neck/head
    soft_hands: bool                          hand targets are reach directions, not contacts

Targets are in character (armature) space: the worker faces -Y at the origin.
Arms without IK targets use their FK values; legs without targets stay FK.
"""

import math

from mathutils import Euler, Matrix, Quaternion, Vector

from core import config

from .rig_model import mirrored, model

FINGERS = ("thumb", "index", "middle", "ring", "pinky")

FINGER_PRESETS = {
    "relaxed": {"thumb": (8, 12, 8), "index": (12, 16, 10), "middle": (14, 18, 12), "ring": (16, 20, 12),
                "pinky": (18, 22, 14)},
    "grip": {"thumb": (18, 38, 30), "index": (62, 78, 38), "middle": (66, 80, 40), "ring": (68, 80, 42),
             "pinky": (70, 76, 42)},
    "fist": {"thumb": (22, 45, 40), "index": (85, 95, 55), "middle": (88, 98, 58), "ring": (88, 98, 58),
             "pinky": (88, 95, 55)},
    "flat": {"thumb": (0, 4, 2), "index": (2, 3, 2), "middle": (2, 3, 2), "ring": (3, 3, 2), "pinky": (4, 4, 2)},
    "carry": {"thumb": (6, 10, 8), "index": (28, 24, 12), "middle": (30, 26, 12), "ring": (32, 26, 12),
              "pinky": (34, 26, 12)},
    "point": {"thumb": (22, 40, 35), "index": (4, 4, 3), "middle": (85, 95, 55), "ring": (88, 98, 58),
              "pinky": (88, 95, 55)},
    "spread": {"thumb": (-6, 0, 0), "index": (-4, 0, 0), "middle": (-4, 0, 0), "ring": (-4, 0, 0),
               "pinky": (-4, 0, 0)},
}


def blend_fingers(a, b, t):
    pa = FINGER_PRESETS[a] if isinstance(a, str) else a
    pb = FINGER_PRESETS[b] if isinstance(b, str) else b
    return {f: tuple(x + (y - x) * t for x, y in zip(pa[f], pb[f])) for f in FINGERS}


class Solved:
    __slots__ = ("rot", "loc", "reach_error", "reach_detail")

    def __init__(self):
        self.rot = {}
        self.loc = {}
        self.reach_error = 0.0
        self.reach_detail = {}


def _grip_matrix(name):
    g = config.animation_spec()["grips"][name]
    rx, ry, rz = (math.radians(a) for a in g.get("rotation_deg", (0, 0, 0)))
    r = Euler((rx, ry, rz), "XYZ").to_matrix().to_4x4()
    return Matrix.Translation(Vector(g["offset"])) @ r


def solve(spec):
    m = model()
    out = Solved()
    rot, loc = out.rot, out.loc
    # Root (turns) and pelvis.
    yaw = spec.get("root", {}).get("yaw", 0.0)
    if yaw:
        rot["root"] = Quaternion((0.0, 1.0, 0.0), math.radians(yaw))
    pel = spec.get("pelvis", {})
    if "loc" in pel:
        off = Vector(pel["loc"])
        loc["pelvis"] = m.rest["pelvis"].to_3x3().inverted() @ off
    if "rot" in pel:
        rot["pelvis"] = mirrored("pelvis", *pel["rot"])
    for bone, vals in spec.get("fk", {}).items():
        rot[bone] = mirrored(bone, *vals)
    look = spec.get("look")
    if look:
        ly, lp = look
        for bone, share in (("neck", 0.4), ("head", 0.6)):
            q = mirrored(bone, lp * share, ly * share, 0.0)
            rot[bone] = (rot.get(bone) or Quaternion()) @ q
    cache = {}

    def world(name):
        return m.world_of(name, rot, loc, cache)

    def invalidate(names):
        for n in list(cache):
            if n in names or any(_is_descendant(m, n, x) for x in names):
                del cache[n]

    # Legs (IK to ankle frames).
    for side, ankle in (spec.get("feet") or {}).items():
        th, cf, ft = f"thigh.{side}", f"calf.{side}", f"foot.{side}"
        pw = world("pelvis")
        knee_pole = (spec.get("knee") or {}).get(side)
        if knee_pole is None:
            hip = (pw @ m.rest_rel[th]).translation
            knee_pole = hip.lerp(ankle.translation, 0.5) + ankle.to_3x3().col[1] * 0.0 + Vector((0, -0.6, 0))
            fwd = ankle.to_3x3().col[1]
            fwd = Vector((fwd.x, fwd.y, 0.0))
            if fwd.length > 1e-6:
                knee_pole = hip.lerp(ankle.translation, 0.5) + fwd.normalized() * 0.6
        qt, qc, err = m.two_bone(th, cf, ankle.translation, knee_pole, pw, rot, loc)
        out.reach_error = max(out.reach_error, err)
        out.reach_detail[f"leg.{side}"] = err
        rot[th], rot[cf] = qt, qc
        invalidate({th})
        cw = world(cf)
        rot[ft] = m.basis_for_world(ft, ankle, cw)
        invalidate({ft})
        toe = (spec.get("toes") or {}).get(side)
        if toe is not None:
            rot[f"toe.{side}"] = mirrored(f"toe.{side}", toe, 0, 0)
    # Arms: right first, then left (possibly derived from the right socket).
    hands = dict(spec.get("hands") or {})
    order = [s for s in ("R", "L") if s in hands or (s == "L" and spec.get("grip"))]
    for side in order:
        if side == "L" and "L" not in hands and spec.get("grip"):
            sr = world("hand_tool.R")
            hands["L"] = sr @ _grip_matrix(spec["grip"])
        sock = hands[side]
        ua, fa, hd, cl = f"upper_arm.{side}", f"forearm.{side}", f"hand.{side}", f"clavicle.{side}"
        hand_w = m.socket_to_hand(side, sock)
        cw = world(cl)
        elbow = (spec.get("elbow") or {}).get(side)
        if elbow is None:
            sh = (cw @ m.rest_rel[ua]).translation
            sx = 1.0 if side == "L" else -1.0
            elbow = sh.lerp(hand_w.translation, 0.5) + Vector((0.35 * sx, 0.25, -0.25))
        qu, qf, err = m.two_bone(ua, fa, hand_w.translation, elbow, cw, rot, loc)
        if spec.get("soft_hands"):
            err = 0.0          # free gesture: the arm extends toward the target, no contact implied
        out.reach_error = max(out.reach_error, err)
        out.reach_detail[f"arm.{side}"] = err
        rot[ua], rot[fa] = qu, qf
        invalidate({ua})
        fw = world(fa)
        rot[hd] = m.basis_for_world(hd, hand_w, fw)
        invalidate({hd})
    # Fingers.
    for side, preset in (spec.get("fingers") or {}).items():
        vals = FINGER_PRESETS[preset] if isinstance(preset, str) else preset
        for f in FINGERS:
            a, b, c = vals[f]
            for i, ang in enumerate((a, b, c)):
                bone = f"{f}_{i + 1:02d}.{side}"
                rot[bone] = mirrored(bone, ang, 0.0, 0.0)
    # Carry prop socket.
    carry = spec.get("carry")
    if carry is not None:
        base = world("root") @ m.rest_rel["carry_attachment"]
        b = base.inverted() @ carry
        loc["carry_attachment"] = b.translation.copy()
        q = b.to_quaternion()
        q.normalize()
        rot["carry_attachment"] = q
    return out


def _is_descendant(m, name, ancestor):
    p = m.parent[name]
    while p is not None:
        if p == ancestor:
            return True
        p = m.parent[p]
    return False


def world_pose(solved):
    """Armature-space matrices for a solved pose (validation / derived targets)."""
    return model().fk(solved.rot, solved.loc)
