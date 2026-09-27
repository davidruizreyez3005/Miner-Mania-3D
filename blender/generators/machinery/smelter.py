"""Tilting crucible smelter.

Mechanics: a refractory-lined crucible furnace sits on trunnions between two
pedestals; hydraulic cylinders tilt it forward to pour molten metal through
the spout into ingot moulds on a casting table; a fume hood and stack draw
off the gases. Bones:

* ``furnace``        crucible body, tilts about +X on the trunnion axis
* ``tilt_barrel.L/R``, ``tilt_rod.L/R``  cylinder barrels and rods (follow the furnace lug; recomputed per frame)

Clips: ``Idle`` (upright, molten glow) and ``Work`` (tilt 38 degrees, pour,
return). Origin: base centre; pouring side -Y.
"""

import math

from mathutils import Matrix, Quaternion, Vector

from utilities.meshkit import trs

from .. import kit
from . import common

SHELL = "paint_worn:gunmetal"
REFRACTORY = "concrete:concrete_dark"
MOLTEN = "emit:emissive_molten"


def build(ctx):
    plinth = ctx.geo("plinth")
    det = ctx.geo("plinth_detail", max_lod=1)
    plinth.box((3.4, 3.6, 0.3), matrix=trs((0.0, 0.2, 0.15)), mat="concrete:concrete", bevel=0.03)
    axis = Vector((0.0, 0.0, 1.55))                           # trunnion axis (along X)
    for x in (-1.25, 1.25):
        plinth.box((0.4, 0.8, 1.4), matrix=trs((x, 0.0, 0.3 + 0.7)), mat=SHELL, bevel=0.03)
        plinth.cylinder(0.2, 0.3, segments=20, matrix=trs((x, 0.0, axis.z), (0, 90, 0)), mat=kit.DARK, bevel=0.02)
        kit.bolt_grid(det, (x, -0.402, 0.9), (1, 0, 0), (0, 0, 1), 2, 3, 0.22, 0.3, (0, -1, 0))
    # Crucible furnace (tilts).
    ctx.bone("furnace", tuple(axis), tuple(axis + Vector((0.4, 0.0, 0.0))), z_axis=(0, 0, 1))
    fur = ctx.geo("furnace", bone="furnace")
    fdet = ctx.geo("furnace_detail", bone="furnace", max_lod=1)
    fc = axis + Vector((0.0, 0.0, -0.25))
    prof = [(0.0, -0.55), (0.72, -0.55), (0.9, -0.3), (0.95, 0.6), (0.88, 0.8), (0.7, 0.85), (0.62, 0.7), (0.62, -0.35),
            (0.0, -0.35)]
    fur.lathe(prof, segments=32, matrix=trs(fc), mat=SHELL)
    fur.lathe([(0.62, 0.7), (0.62, -0.35), (0.0, -0.35), (0.0, 0.55), (0.6, 0.55)], segments=32, matrix=trs(fc),
              mat=REFRACTORY, caps=False)
    fur.cylinder(0.6, 0.02, segments=32, matrix=trs(fc + Vector((0.0, 0.0, 0.55))), mat=MOLTEN)     # melt surface
    for z in (-0.2, 0.25, 0.6):                                                                     # bands
        fur.torus(0.96, 0.03, seg_major=32, seg_minor=6, matrix=trs(fc + Vector((0.0, 0.0, z))), mat=kit.DARK)
    for x in (-1.0, 1.0):                                                                           # trunnion pins
        fur.cylinder(0.12, 0.35, segments=16, matrix=trs(axis + Vector((x, 0.0, 0.0)), (0, 90, 0)), mat=kit.STEEL)
    spout = fc + Vector((0.0, -0.9, 0.75))
    fur.box((0.28, 0.45, 0.14), matrix=trs(spout, (-12, 0, 0)), mat=REFRACTORY, bevel=0.03)
    fur.box((0.14, 0.4, 0.02), matrix=trs(spout + Vector((0.0, 0.0, 0.06)), (-12, 0, 0)), mat=MOLTEN)
    lug = fc + Vector((0.0, 0.85, -0.35))
    for x in (-0.45, 0.45):
        fur.box((0.12, 0.25, 0.2), matrix=trs(lug + Vector((x, 0.0, 0.0))), mat=kit.DARK, bevel=0.02)
    kit.bolt_circle(fdet, fc + Vector((0.0, 0.0, 0.86)), (0, 0, 1), 0.8, 16)
    # Tilt cylinders: barrels pivot on the plinth, rods to the furnace lugs
    # (rod bones get their pose from the furnace angle each frame).
    base_pts = {s: Vector((x, 1.2, 0.35)) for s, x in (("L", 0.45), ("R", -0.45))}
    lug_pts = {s: lug + Vector((x, 0.0, 0.0)) for s, x in (("L", 0.45), ("R", -0.45))}
    cyl = ctx.geo("tilt_cylinders")
    for s in ("L", "R"):
        b, tip = base_pts[s], lug_pts[s]
        ctx.bone(f"tilt_barrel.{s}", tuple(b), tuple(b + (tip - b).normalized() * 0.3))
        ctx.bone(f"tilt_rod.{s}", tuple(tip), tuple(tip + (tip - b).normalized() * 0.3), parent=f"tilt_barrel.{s}")
        kit.hydraulic(ctx.geo(f"tilt_barrel.{s}", bone=f"tilt_barrel.{s}"), ctx.geo(f"tilt_rod.{s}", bone=f"tilt_rod.{s}"),
                      b, tip, 0.09, body_ratio=0.55, body_mat=SHELL)
        cyl.box((0.16, 0.2, 0.12), matrix=trs(b + Vector((0.0, 0.0, -0.08))), mat=kit.DARK, bevel=0.01)
    # Fume hood + stack (fixed).
    hood = ctx.geo("hood")
    hz = 3.3
    kit.hopper(hood, (0.0, 0.0), (1.7, 1.7), (0.5, 0.5), hz, hz + 0.9, wall=0.03, mat=SHELL, rim=0.0)
    kit.pipe_run(hood, [(0.0, 0.0, hz + 0.85), (0.0, 0.0, hz + 1.6), (0.0, 0.9, hz + 2.2), (0.0, 0.9, hz + 3.6)], 0.25, SHELL,
                 bend=0.4, flanges=False)
    for x in (-0.85, 0.85):
        kit.beam(hood, (x, 0.8, 0.3), (x, 0.8, hz + 0.1), 0.14, 0.14, kit.FRAME, profile="I", up=(0, 1, 0))
        kit.beam(hood, (x, 0.8, hz + 0.1), (x * 0.3, 0.3, hz + 0.1), 0.1, 0.1, kit.FRAME)
    kit.lamp(hood, (0.9, 0.7, hz - 0.2), (-0.4, -0.6, -0.7), emit="emit:emissive_warm")
    # Casting table with ingot moulds in front.
    tab = ctx.geo("casting_table")
    tab.box((1.6, 0.9, 0.7), matrix=trs((0.0, -2.1, 0.35)), mat=kit.FRAME, bevel=0.02)
    for k in range(4):
        x = -0.54 + 0.36 * k
        tab.box((0.3, 0.6, 0.12), matrix=trs((x, -2.1, 0.76)), mat=kit.DARK, bevel=0.02)
        tab.box((0.22, 0.5, 0.02), matrix=trs((x, -2.1, 0.81)), mat="iron_metal", bevel=0.004)
    kit.warning_sign(det, (1.25, -0.42, 1.2), facing=(0, -1, 0))
    # Stations: lever console on the right, service bolt on the hydraulic unit.
    common.operate_facing(ctx, plinth, (2.1, -1.2, 0.0), (-1.0, 0.0, 0.0))
    hpu = Vector((-1.6, 1.3, 0.55))
    plinth.box((0.5, 0.6, 0.5), matrix=trs(hpu), mat=kit.DARK, bevel=0.02)
    common.repair_at(ctx, det, hpu + Vector((-0.25, 0.0, 0.0)), (-1.0, 0.0, 0.0))
    ctx.socket("output", (0.0, -2.1, 0.82))
    ctx.socket("input", (0.0, 0.0, 2.6))
    ctx.col_box((0.0, 0.2, 0.15), (3.4, 3.6, 0.3))
    ctx.col_cylinder(tuple(fc + Vector((0.0, 0.0, 0.15))), 0.98, 1.45)
    for x in (-1.25, 1.25):
        ctx.col_box((x, 0.0, 1.0), (0.4, 0.8, 1.4))
    ctx.col_box((0.0, -2.1, 0.42), (1.6, 0.9, 0.84))
    ctx.col_box((0.0, 0.45, hz + 1.5), (1.8, 2.0, 3.2))

    def pose(tilt_deg):
        q = Quaternion((1, 0, 0), math.radians(tilt_deg))
        out = {"furnace": (None, q)}
        rot = Matrix.Translation(axis) @ q.to_matrix().to_4x4() @ Matrix.Translation(-axis)
        for s in ("L", "R"):
            b, tip0 = base_pts[s], lug_pts[s]
            tip = rot @ tip0
            d0, d1 = (tip0 - b).normalized(), (tip - b).normalized()
            qb = d0.rotation_difference(d1)
            ext = (tip - b).length - (tip0 - b).length
            out[f"tilt_barrel.{s}"] = (None, qb)
            # Rod: extension along the rotated cylinder axis (child of the barrel).
            out[f"tilt_rod.{s}"] = (d0 * ext, None)
        return out

    def work(t):
        T = 6.0
        u = t / T
        if u < 0.3:
            a = 38.0 * (0.5 - 0.5 * math.cos(math.pi * u / 0.3))
        elif u < 0.6:
            a = 38.0 + 2.0 * math.sin(2 * math.pi * (u - 0.3) / 0.3)
        else:
            a = 38.0 * (0.5 + 0.5 * math.cos(math.pi * (u - 0.6) / 0.4))
        return pose(-a)

    ctx.clip("Idle", 2.0, True, lambda t: pose(0.0), "Upright, melt glowing")
    ctx.clip("Work", 6.0, True, work, "Tilts 38 degrees to pour into the ingot moulds, holds, returns")
    ctx.metadata["interaction"] = {"operate": "socket_operate", "repair": "socket_repair", "input": "socket_input",
                                   "output": "socket_output"}
