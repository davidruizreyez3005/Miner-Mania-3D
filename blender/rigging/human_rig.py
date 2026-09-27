"""Shared humanoid skeleton ``humanoid_worker_v1``.

Every worker variant uses exactly this skeleton (identical bone names,
hierarchy, rest positions and bone frames), so one baked animation library
drives all of them. Body variation (slim/stocky/heavy, masculine/feminine) is
expressed in the meshes, never in the joints.

Conventions (Blender space; the worker faces -Y, +X is the worker's left):

* A-pose rest: arms 45 degrees down in the frontal plane, straight elbows.
* Trunk and limb bones: local Y along the bone, local Z points forward
  (-Y world) so ``+X rotation`` swings a bone forward (flexion).
* Hands and fingers: local Z points toward the palm so ``+X rotation`` curls.
* Feet/toes: local Z points up so ``+X rotation`` lifts the toes.
* Sockets (non-deforming): local Y is the attached item's "up", local Z its
  "front". Items authored with +Z up / -Y front attach at identity once
  exported (glTF +Y up / +Z front).
"""

from mathutils import Vector

from core.context import BoneSpec

NAME = "humanoid_worker_v1"

FWD = Vector((0.0, -1.0, 0.0))
UP = Vector((0.0, 0.0, 1.0))

FINGERS = ("thumb", "index", "middle", "ring", "pinky")
SOCKETS = ("hand_tool.L", "hand_tool.R", "back_equipment", "helmet_attachment", "waist_equipment", "carry_attachment")

# Finger layout on the left hand: (spread offset along thumb axis T, back offset along D, lengths)
_FINGER_LAYOUT = {
    "index": (0.029, -0.004, (0.042, 0.026, 0.021)),
    "middle": (0.009, 0.0, (0.046, 0.029, 0.022)),
    "ring": (-0.011, -0.004, (0.043, 0.027, 0.021)),
    "pinky": (-0.029, -0.014, (0.034, 0.021, 0.018)),
}
_SPREAD = {"index": 0.07, "middle": 0.0, "ring": -0.06, "pinky": -0.14}


def _v(x, y, z):
    return Vector((x, y, z))


class Skeleton:
    """Rest-pose joint positions and bone specs for the standard worker."""

    def __init__(self):
        j = {}
        j["root"] = _v(0, 0, 0)
        j["pelvis"] = _v(0, 0.004, 0.955)
        j["spine_01"] = _v(0, 0.008, 1.005)
        j["spine_02"] = _v(0, 0.014, 1.13)
        j["spine_03"] = _v(0, 0.01, 1.255)
        j["neck"] = _v(0, 0.012, 1.47)
        j["head"] = _v(0, 0.012, 1.575)
        j["head_top"] = _v(0, 0.012, 1.775)
        self.arm_dir = {}
        for side, s in (("L", 1.0), ("R", -1.0)):
            j[f"clavicle.{side}"] = _v(0.022 * s, -0.018, 1.428)
            j[f"shoulder.{side}"] = _v(0.195 * s, 0.006, 1.435)
            d = Vector((0.7071 * s, 0.0, -0.7071))
            self.arm_dir[side] = d
            j[f"elbow.{side}"] = j[f"shoulder.{side}"] + d * 0.29
            j[f"wrist.{side}"] = j[f"elbow.{side}"] + d * 0.26
            j[f"knuckle.{side}"] = j[f"wrist.{side}"] + d * 0.09
            j[f"hip.{side}"] = _v(0.098 * s, 0.0, 0.905)
            j[f"knee.{side}"] = _v(0.1 * s, -0.012, 0.49)
            j[f"ankle.{side}"] = _v(0.1 * s, 0.022, 0.085)
            j[f"ball.{side}"] = _v(0.1 * s, -0.1, 0.025)
            j[f"toe_tip.{side}"] = _v(0.1 * s, -0.185, 0.022)
            j[f"eye.{side}"] = _v(0.0345 * s, -0.068, 1.651)
        self.joints = j
        self._build_hands()
        self.specs = self._build_specs()
        self.by_name = {b.name: b for b in self.specs}

    # -- hand frames ----------------------------------------------------------
    def hand_frame(self, side):
        """(D distal, T thumb-ward, P palm normal) in rest pose."""
        d = self.arm_dir[side].copy()
        t = FWD.copy()
        p = d.cross(t) if side == "L" else t.cross(d)
        return d.normalized(), t.normalized(), p.normalized()

    def _build_hands(self):
        j = self.joints
        self.finger_chains = {}
        for side in ("L", "R"):
            d, t, p = self.hand_frame(side)
            k = j[f"knuckle.{side}"]
            for f, (spread, back, lengths) in _FINGER_LAYOUT.items():
                base = k + t * spread + d * back
                dirn = (d + t * _SPREAD[f]).normalized()
                pts = [base]
                for ln in lengths:
                    pts.append(pts[-1] + dirn * ln)
                self.finger_chains[(f, side)] = (pts, p.copy())
            w = j[f"wrist.{side}"]
            base = w + d * 0.022 + t * 0.021 + p * 0.012
            tdir = (t * 0.62 + d * 0.72 + p * 0.3).normalized()
            pts = [base]
            for ln in (0.042, 0.031, 0.025):
                pts.append(pts[-1] + tdir * ln)
            curl_axis = (p * 0.8 - t * 0.6).normalized()
            self.finger_chains[("thumb", side)] = (pts, curl_axis)

    def grip_point(self, side):
        d, t, p = self.hand_frame(side)
        return self.joints[f"knuckle.{side}"] + d * 0.004 + p * 0.03

    # -- specs --------------------------------------------------------------------
    def _build_specs(self):
        j = self.joints
        S = []

        def add(name, head, tail, parent, z, deform=True):
            S.append(BoneSpec(name, tuple(head), tuple(tail), parent, tuple(z), deform))

        add("root", j["root"], j["root"] + _v(0, 0, 0.3), None, FWD, False)
        add("pelvis", j["pelvis"], j["spine_01"], "root", FWD)
        add("spine_01", j["spine_01"], j["spine_02"], "pelvis", FWD)
        add("spine_02", j["spine_02"], j["spine_03"], "spine_01", FWD)
        add("spine_03", j["spine_03"], j["neck"], "spine_02", FWD)
        add("neck", j["neck"], j["head"], "spine_03", FWD)
        add("head", j["head"], j["head_top"], "neck", FWD)
        for side in ("L", "R"):
            add(f"eye.{side}", j[f"eye.{side}"], j[f"eye.{side}"] + FWD * 0.02, "head", UP)
        for side in ("L", "R"):
            add(f"clavicle.{side}", j[f"clavicle.{side}"], j[f"shoulder.{side}"], "spine_03", FWD)
            add(f"upper_arm.{side}", j[f"shoulder.{side}"], j[f"elbow.{side}"], f"clavicle.{side}", FWD)
            add(f"forearm.{side}", j[f"elbow.{side}"], j[f"wrist.{side}"], f"upper_arm.{side}", FWD)
            d, t, p = self.hand_frame(side)
            add(f"hand.{side}", j[f"wrist.{side}"], j[f"knuckle.{side}"], f"forearm.{side}", p)
            for f in FINGERS:
                pts, curl = self.finger_chains[(f, side)]
                parent = f"hand.{side}"
                for i in range(3):
                    name = f"{f}_{i + 1:02d}.{side}"
                    add(name, pts[i], pts[i + 1], parent, curl)
                    parent = name
        for side in ("L", "R"):
            add(f"thigh.{side}", j[f"hip.{side}"], j[f"knee.{side}"], "pelvis", FWD)
            add(f"calf.{side}", j[f"knee.{side}"], j[f"ankle.{side}"], f"thigh.{side}", FWD)
            add(f"foot.{side}", j[f"ankle.{side}"], j[f"ball.{side}"], f"calf.{side}", UP)
            add(f"toe.{side}", j[f"ball.{side}"], j[f"toe_tip.{side}"], f"foot.{side}", UP)
        # Attachment sockets (non-deforming).
        for side in ("L", "R"):
            d, t, p = self.hand_frame(side)
            g = self.grip_point(side)
            add(f"hand_tool.{side}", g, g + t * 0.08, f"hand.{side}", d, deform=False)
        add("back_equipment", _v(0, 0.135, 1.33), _v(0, 0.135, 1.43), "spine_03", FWD, deform=False)
        add("helmet_attachment", _v(0, 0.004, 1.69), _v(0, 0.004, 1.79), "head", FWD, deform=False)
        add("waist_equipment", _v(-0.165, 0.035, 1.0), _v(-0.165, 0.035, 1.1), "pelvis", FWD, deform=False)
        add("carry_attachment", _v(0, -0.34, 0.9), _v(0, -0.34, 1.0), "root", FWD, deform=False)
        return S

    # -- queries --------------------------------------------------------------------
    @property
    def bone_names(self):
        return [b.name for b in self.specs]

    @property
    def deform_bones(self):
        return [b.name for b in self.specs if b.deform]

    def parent_map(self):
        return {b.name: b.parent for b in self.specs}

    @staticmethod
    def mirror_name(name):
        if name.endswith(".L"):
            return name[:-2] + ".R"
        if name.endswith(".R"):
            return name[:-2] + ".L"
        return name

    def describe(self):
        return {
            "name": NAME,
            "bones": [{"name": b.name, "parent": b.parent, "head": [round(x, 4) for x in b.head],
                       "tail": [round(x, 4) for x in b.tail], "deform": b.deform} for b in self.specs],
            "sockets": list(SOCKETS),
        }


_SINGLETON = None


def skeleton():
    global _SINGLETON
    if _SINGLETON is None:
        _SINGLETON = Skeleton()
    return _SINGLETON
