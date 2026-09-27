"""Side-tipping rail mine cart (600 mm gauge).

Construction: steel chassis on two axles with flanged rail wheels, buffers
and link couplings at both ends; a V-shaped tub on a pivot rail tips to the
side to unload and is held by a latch lever. Bones:

* ``wheel_front`` / ``wheel_rear``   axles with both wheels, spin about +X
* ``tub``                            tub, tips about the longitudinal pivot (+Y)
* ``latch``                          latch lever, rotates about +X

Clips: ``Idle``, ``Roll`` (2 m/s in place) and ``Tip`` (unlatch, tip 45 degrees,
return). Origin: rail level at the cart centre; front -Y; runs on
env_rail_straight_01 track.
"""

import math

from mathutils import Quaternion, Vector

from utilities.meshkit import trs

from .. import kit

GAUGE = 0.6
TUB = "paint_worn:rust"


def build(ctx):
    r = 0.18
    length, width = 1.7, 0.95
    frame_z = r + 0.12
    ch = ctx.geo("chassis")
    det = ctx.geo("chassis_detail", max_lod=1)
    for x in (-0.3, 0.3):
        kit.beam(ch, (x, -length / 2, frame_z), (x, length / 2, frame_z), 0.08, 0.14, kit.FRAME, profile="C")
    for y in (-length / 2 + 0.05, length / 2 - 0.05):
        kit.beam(ch, (-0.4, y, frame_z), (0.4, y, frame_z), 0.1, 0.16, kit.FRAME)
        ch.box((0.5, 0.1, 0.12), matrix=trs((0.0, y + (0.08 if y > 0 else -0.08), frame_z)), mat=kit.DARK, bevel=0.02)  # buffer
        for x in (-0.12, 0.12):
            det.torus(0.04, 0.012, seg_major=10, seg_minor=5,
                      matrix=trs((x, y + (0.2 if y > 0 else -0.2), frame_z), (0, 90, 0)), mat=kit.DARK)
    wheels = {}
    for name, y in (("wheel_front", -0.45), ("wheel_rear", 0.45)):
        c = Vector((0.0, y, r))
        ctx.bone(name, tuple(c), tuple(c + Vector((0.3, 0.0, 0.0))), z_axis=(0, 0, 1))
        wg = ctx.geo(name, bone=name)
        wg.cylinder(0.035, GAUGE + 0.16, segments=10, matrix=trs(c, (0, 90, 0)), mat=kit.STEEL)
        for s in (-1, 1):
            x = s * GAUGE / 2
            prof = [(0.03, -0.035), (r, -0.035), (r, 0.02), (r + 0.025, 0.02), (r + 0.025, 0.035), (0.03, 0.035)]
            wg.lathe(prof, segments=20, matrix=trs((x, y, r), (0, 90 * s, 0)), mat=kit.DARK)
        wheels[name] = c
        ch.box((GAUGE + 0.1, 0.12, 0.08), matrix=trs((0.0, y, frame_z - 0.08)), mat=kit.DARK, bevel=0.01)     # axle box
    # Tub on the pivot rail (tips toward +X).
    pivot = Vector((0.35, 0.0, frame_z + 0.1))
    ctx.bone("tub", tuple(pivot), tuple(pivot + Vector((0.0, 0.3, 0.0))), z_axis=(0, 0, 1))
    tub = ctx.geo("tub", bone="tub")
    tdet = ctx.geo("tub_detail", bone="tub", max_lod=1)
    z0 = frame_z + 0.12
    sec = [(-width / 2, z0 + 0.62), (-width / 2 + 0.1, z0 + 0.12), (0.0, z0), (width / 2 - 0.1, z0 + 0.12), (width / 2, z0 + 0.62)]
    ln = length - 0.1
    outer = [(x, y, z) for y in (-ln / 2, ln / 2) for x, z in sec]
    faces = []
    n = len(sec)
    for i in range(n - 1):
        faces.append((i, i + 1, n + i + 1, n + i))          # V-shaped hull
    faces.append(tuple(range(n))[::-1])                      # front end plate
    faces.append(tuple(range(n, 2 * n)))                     # rear end plate
    tub.mesh(outer, faces, mat=TUB, recalc=True)
    inner = [(x * 0.94, y * 0.96, z + 0.03) for x, y, z in outer]
    tub.mesh(inner, [f[::-1] for f in faces], mat=TUB, recalc=True)
    for x in (-width / 2, width / 2):
        tub.box((0.05, ln + 0.04, 0.05), matrix=trs((x, 0.0, z0 + 0.63)), mat=kit.DARK, bevel=0.01)     # rim bars
    for y in (-ln / 2, ln / 2):
        tdet.box((width * 0.9, 0.04, 0.05), matrix=trs((0.0, y * 1.01, z0 + 0.4)), mat=kit.DARK, bevel=0.008)
    tub.box((0.12, ln, 0.06), matrix=trs((0.3, 0.0, z0 - 0.02)), mat=kit.DARK, bevel=0.01)               # pivot rail
    # Latch lever at the front.
    lp = Vector((-0.42, -length / 2 + 0.1, frame_z + 0.1))
    ctx.bone("latch", tuple(lp), tuple(lp + Vector((0.0, 0.0, 0.3))), z_axis=(0, -1, 0))
    latch = ctx.geo("latch", bone="latch")
    kit.beam(latch, lp, lp + Vector((0.0, 0.0, 0.45)), 0.03, 0.03, kit.DARK, profile="tube")
    latch.sphere(0.04, segments=10, rings=6, matrix=trs(lp + Vector((0.0, 0.0, 0.47))), mat="plastic:signal_red")
    ctx.socket("load", (0.0, 0.0, z0 + 0.9))
    ctx.socket("coupling_front", (0.0, -length / 2 - 0.25, frame_z))
    ctx.socket("coupling_rear", (0.0, length / 2 + 0.25, frame_z))
    ctx.socket("push", (0.0, length / 2 + 0.45, 0.0), (0.0, 0.0, 0.0))
    ctx.col_box((0.0, 0.0, frame_z - 0.05), (0.9, length + 0.2, 0.3))
    ctx.col_hull([(x, y, z) for y in (-ln / 2, ln / 2) for x, z in sec])

    speed = 2.0
    T_roll = 2 * math.pi * r * 3 / speed

    def roll(t):
        q = Quaternion((1, 0, 0), speed * t / r)
        return {"wheel_front": (None, q), "wheel_rear": (None, q)}

    def tip(t):
        T = 4.0
        u = t / T
        latch = min(1.0, u / 0.12) if u < 0.8 else max(0.0, 1.0 - (u - 0.8) / 0.12)
        k = 0.0 if u < 0.12 else (min(1.0, (u - 0.12) / 0.3) if u < 0.55 else max(0.0, 1.0 - (u - 0.55) / 0.25))
        return {"tub": (None, Quaternion((0, 1, 0), math.radians(45) * (0.5 - 0.5 * math.cos(math.pi * k)))),
                "latch": (None, Quaternion((1, 0, 0), math.radians(40) * latch))}

    ctx.clip("Idle", 1.0, True, lambda t: {}, "Standing")
    ctx.clip("Roll", T_roll, True, roll, f"Rolling at {speed} m/s (in place)")
    ctx.clip("Tip", 4.0, False, tip, "Latch released, tub tips 45 degrees to the side, rights itself, latch closes")
    ctx.metadata["speeds"] = {"roll_mps": speed, "wheel_radius_m": r, "track_gauge_m": GAUGE}
    ctx.metadata["interaction"] = {"load": "socket_load", "push": "socket_push"}
