"""Test mannequin: rigid segments on the shared humanoid skeleton.

Two uses:

* ``chr_mannequin_test_01`` -- the automated test character. It carries the
  whole worker animation library and is what the pipeline and the Godot
  validation play to exercise idle/walk/run/mine/carry/operate/repair.
* the proxy body of the ``anim_worker_*`` animation GLBs, so every clip file
  imports into Godot with the same Skeleton3D (and track paths) as the
  workers and can be previewed on its own.

Every segment is weighted 100 % to one bone, so what you see is exactly the
skeleton motion: no skinning artefacts can hide a bad pose. Left limbs are
blue and right limbs orange so mirroring mistakes are obvious.
"""

import math

from mathutils import Matrix

from animation.rig_model import model
from rigging import human_rig
from utilities.meshkit import Geo

from .skinned import SkinnedGeo

TRUNK = "plastic:plastic_white"
JOINT = "plastic:plastic_black"
LEFT = "paint_clean:machine_blue"
RIGHT = "paint_clean:safety_orange"
FINGERS = ("thumb", "index", "middle", "ring", "pinky")
_ALONG_Y = Matrix.Rotation(math.radians(-90.0), 4, "X")     # primitive local Z -> bone Y


def _along(y):
    return Matrix.Translation((0.0, y, 0.0)) @ _ALONG_Y


def _limb(g, length, r0, r1, key, joint_r=None):
    if joint_r:
        g.sphere(joint_r, segments=12, rings=6, mat=JOINT)
    g.cylinder(r0, length * 0.92, segments=12, matrix=_along(length * 0.5), mat=key, radius_top=r1, bevel=0.006)


def _segments(m):
    """(bone, builder) pairs; builders draw in bone-local space (Y along the bone)."""
    out = []

    def add(bone, fn):
        out.append((bone, fn))

    add("pelvis", lambda g: g.box((0.3, 0.17, 0.19), center=(0.0, -0.035, 0.0), mat=TRUNK, bevel=0.045, segments=2))
    add("spine_01", lambda g: g.sphere(1.0, segments=14, rings=8, scale=(0.135, 0.085, 0.1),
                                       matrix=Matrix.Translation((0.0, 0.06, 0.0)), mat=TRUNK))
    add("spine_02", lambda g: g.sphere(1.0, segments=14, rings=8, scale=(0.15, 0.09, 0.105),
                                       matrix=Matrix.Translation((0.0, 0.065, 0.005)), mat=TRUNK))
    add("spine_03", lambda g: g.sphere(1.0, segments=16, rings=8, scale=(0.17, 0.135, 0.115),
                                       matrix=Matrix.Translation((0.0, 0.1, 0.0)), mat=TRUNK))
    add("neck", lambda g: g.cylinder(0.045, 0.11, segments=10, matrix=_along(0.05), mat=JOINT))

    def head(g):
        g.sphere(1.0, segments=16, rings=10, scale=(0.095, 0.115, 0.11), matrix=Matrix.Translation((0.0, 0.08, -0.005)),
                 mat=TRUNK)
        g.box((0.13, 0.035, 0.03), center=(0.0, 0.09, 0.1), mat=JOINT, bevel=0.01, segments=1)     # visor = facing
    add("head", head)
    for side, key in (("L", LEFT), ("R", RIGHT)):
        add(f"clavicle.{side}", lambda g, k=key: g.cylinder(0.03, m.length[f"clavicle.{side}"] * 0.8, segments=8,
                                                            matrix=_along(m.length[f"clavicle.{side}"] * 0.5), mat=TRUNK))
        add(f"upper_arm.{side}", lambda g, k=key, s=side: _limb(g, m.length[f"upper_arm.{s}"], 0.048, 0.04, k, 0.056))
        add(f"forearm.{side}", lambda g, k=key, s=side: _limb(g, m.length[f"forearm.{s}"], 0.04, 0.03, k, 0.043))
        add(f"hand.{side}", lambda g, k=key: g.box((0.08, 0.09, 0.028), center=(0.0, 0.045, 0.0), mat=k, bevel=0.01,
                                                   segments=1))
        for f in FINGERS:
            for i in range(3):
                b = f"{f}_{i + 1:02d}.{side}"
                r = 0.0095 if f == "thumb" else 0.0082
                add(b, lambda g, bb=b, rr=r, k=key: g.cylinder(rr, m.length[bb] * 0.9, segments=6,
                                                             matrix=_along(m.length[bb] * 0.5), mat=k))
        add(f"thigh.{side}", lambda g, k=key, s=side: _limb(g, m.length[f"thigh.{s}"], 0.075, 0.056, k, 0.078))
        add(f"calf.{side}", lambda g, k=key, s=side: _limb(g, m.length[f"calf.{s}"], 0.054, 0.04, k, 0.058))
        add(f"foot.{side}", lambda g, k=key: g.box((0.09, 0.2, 0.06), center=(0.0, 0.04, -0.022), mat=k, bevel=0.015,
                                                   segments=1))
        add(f"toe.{side}", lambda g, k=key: g.box((0.085, 0.08, 0.03), center=(0.0, 0.04, -0.006), mat=k, bevel=0.01,
                                                  segments=1))
    return out


def build_body(ctx):
    m = model()
    body = SkinnedGeo("body")
    for bone, fn in _segments(m):
        g = Geo(f"seg_{bone}")
        fn(g)
        body.append_rigid(g, bone, matrix=m.rest[bone])
    obj = body.to_object(ctx.lib, subdivide=0)
    obj["mm_part"] = "body"
    obj["mm_uv_scale"] = 1.0
    ctx.objects.append(obj)
    return obj


def build(ctx):
    build_body(ctx)
    ctx.character = {"skeleton": human_rig.NAME, "animate": ctx.param("animate", True)}
    if ctx.defn.collision != "none":
        cap = ctx.cfg["collision"]["character_capsule"]
        ctx.col_capsule(cap["radius"], cap["height"])
        ctx.metadata["capsule"] = cap
    ctx.metadata["character"] = {"role": "test_mannequin", "skeleton": human_rig.NAME, "tools": {}, "equipment": []}
