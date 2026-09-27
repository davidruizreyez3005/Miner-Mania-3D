"""Skid-mounted rotary drill rig.

Mechanics: a diesel power pack (radiator fan) drives a hydraulic system; two
feed cylinders on the mast push the rotary head down the mast guides while
the head's motor spins the drill string. Bones sit on the real axes:

* ``fan``      radiator fan hub, spins about +Y
* ``feed``     rotary head carriage, translates along the mast (+Z)
* ``spindle``  drill string, child of ``feed``, spins about +Z

Clips: ``Idle`` (fan idling, head parked at the top) and ``Work`` (head
feeds down while the string spins, then retracts; seamless loop).
Origin: base centre on the ground. Front (-Y) carries the mast.
"""

import math

from mathutils import Quaternion, Vector

from animation.machine_anim import loop_spin
from utilities.meshkit import trs

from .. import kit
from . import common

YELLOW = "paint_worn:industrial_yellow"


def build(ctx):
    sx, sy = 2.2, 3.4
    deck_z = 0.34
    mast_y = -1.25
    mast_top = 5.4
    head_top, head_travel = 4.35, 2.6
    body = ctx.geo("skid")
    det = ctx.geo("skid_detail", max_lod=1)
    # --- skid: two I-beam runners, cross members, chequer deck, hazard ends
    for x in (-sx / 2 + 0.12, sx / 2 - 0.12):
        kit.beam(body, (x, -sy / 2, 0.12), (x, sy / 2, 0.12), 0.16, 0.24, kit.FRAME, profile="I")
    for y in (-sy / 2 + 0.2, -0.6, 0.4, sy / 2 - 0.2):
        kit.beam(body, (-sx / 2 + 0.2, y, 0.14), (sx / 2 - 0.2, y, 0.14), 0.12, 0.2, kit.FRAME, profile="C")
    kit.deck(body, (0.0, 0.0, deck_z), (sx, sy), mat="metal:galvanized", thickness=0.06)
    for y in (-sy / 2 - 0.03, sy / 2 + 0.03):
        body.box((sx, 0.06, 0.26), matrix=trs((0.0, y, 0.15)), mat=kit.HAZARD, bevel=0.01)
    for x in (-sx / 2 + 0.12, sx / 2 - 0.12):
        for y in (-sy / 2 + 0.1, sy / 2 - 0.1):
            det.torus(0.05, 0.012, seg_major=12, seg_minor=5, matrix=trs((x, y, 0.3), (90, 0, 90)), mat=kit.DARK)
    # --- power pack at the rear
    pp = ctx.geo("power_pack")
    ppd = ctx.geo("power_pack_detail", max_lod=1)
    pc = Vector((0.0, 0.85, deck_z))
    pp.box((1.7, 1.4, 1.35), matrix=trs(pc + Vector((0.0, 0.0, 0.7))), mat=YELLOW, bevel=0.04, segments=2)
    pp.box((1.74, 1.44, 0.1), matrix=trs(pc + Vector((0.0, 0.0, 1.42))), mat=kit.DARK, bevel=0.02, segments=1)
    for side in (-1, 1):                                    # louvred side doors
        for k in range(6):
            pp.box((0.02, 0.9, 0.035), matrix=trs(pc + Vector((side * 0.862, -0.05, 0.4 + 0.12 * k)), (18 * side, 0, 0)),
                    mat=kit.DARK, bevel=0.004)
        kit.bolt_grid(ppd, pc + Vector((side * 0.855, 0.0, 0.7)), (0, 1, 0), (0, 0, 1), 2, 2, 1.2, 1.1, (side, 0, 0))
    # Radiator grille at the back with the fan behind it.
    rad = pc + Vector((0.0, 0.71, 0.72))
    pp.box((1.3, 0.04, 1.0), matrix=trs(rad), mat=kit.DARK, bevel=0.01)
    for k in range(9):
        pp.box((1.24, 0.02, 0.018), matrix=trs(rad + Vector((0.0, 0.025, -0.42 + 0.105 * k))), mat=kit.STEEL, bevel=0.003)
    ctx.bone("fan", tuple(rad + Vector((0.0, -0.1, 0.0))), tuple(rad + Vector((0.0, -0.35, 0.0))))
    fan = ctx.geo("fan", bone="fan")
    fc = rad + Vector((0.0, -0.1, 0.0))
    fan.cylinder(0.07, 0.08, segments=12, matrix=kit.axis_frame(fc, (0, 1, 0)), mat=kit.DARK)
    for k in range(6):
        a = 2 * math.pi * k / 6
        fan.box((0.07, 0.012, 0.38), matrix=kit.axis_frame(fc, (0, 1, 0)) @ trs((math.cos(a) * 0.22, math.sin(a) * 0.22, 0.0),
                                                                                (0, 0, math.degrees(a) + 90)) @ trs(rot=(0, 25, 0)),
                mat=kit.DARK, bevel=0.004)
    # Exhaust stack + air filter.
    ex = pc + Vector((0.55, 0.3, 1.47))
    kit.pipe_run(pp, [ex, ex + Vector((0, 0, 0.55)), ex + Vector((0, 0.12, 0.7))], 0.06, kit.DARK, flanges=False)
    ppd.cylinder(0.14, 0.36, segments=16, matrix=trs(pc + Vector((-0.5, 0.2, 1.65))), mat=kit.DARK, bevel=0.02)
    # --- mast: two guide columns with lattice bracing
    mast = ctx.geo("mast")
    mdet = ctx.geo("mast_detail", max_lod=1)
    for x in (-0.24, 0.24):
        kit.beam(mast, (x, mast_y, deck_z), (x, mast_y, mast_top), 0.12, 0.16, YELLOW, up=(0, 1, 0))
        kit.beam(mast, (x, mast_y + 0.1, deck_z), (x, mast_y + 0.1, mast_top), 0.05, 0.05, kit.STEEL, profile="tube",
                 up=(0, 1, 0))
    n = 8
    for k in range(n):
        z0 = deck_z + 0.3 + (mast_top - deck_z - 0.6) * k / n
        z1 = deck_z + 0.3 + (mast_top - deck_z - 0.6) * (k + 1) / n
        kit.beam(mdet, (-0.24, mast_y + 0.08, z0), (0.24, mast_y + 0.08, z1), 0.04, 0.04, YELLOW, profile="tube")
        kit.beam(mast, (-0.24, mast_y + 0.08, z1), (0.24, mast_y + 0.08, z1), 0.05, 0.05, YELLOW)
    mast.box((0.8, 0.5, 0.2), matrix=trs((0.0, mast_y + 0.05, mast_top + 0.1)), mat=kit.DARK, bevel=0.02)
    mast.box((0.8, 0.6, 0.35), matrix=trs((0.0, mast_y + 0.05, deck_z + 0.18)), mat=kit.HAZARD, bevel=0.02)
    for x in (-0.3, 0.3):                                   # crown sheaves
        mdet.cylinder(0.12, 0.05, segments=16, matrix=trs((x, mast_y + 0.05, mast_top + 0.28), (0, 90, 0)), mat=kit.STEEL)
    kit.lamp(mdet, (-0.42, mast_y - 0.05, mast_top - 0.2), (0.0, -0.8, -0.6))
    kit.lamp(mdet, (0.42, mast_y - 0.05, mast_top - 0.2), (0.0, -0.8, -0.6))
    kit.beacon(mdet, (0.0, mast_y + 0.05, mast_top + 0.2))
    # Feed cylinders: barrels on the mast, rods ride the head carriage.
    ctx.bone("feed", (0.0, mast_y - 0.12, head_top), (0.0, mast_y - 0.12, head_top + 0.3))
    ctx.bone("spindle", (0.0, mast_y - 0.32, head_top - 0.25), (0.0, mast_y - 0.32, head_top - 0.55), parent="feed",
             z_axis=(0.0, -1.0, 0.0))
    cyl = ctx.geo("feed_cylinders")
    rods = ctx.geo("feed_rods", bone="feed")
    for x in (-0.42, 0.42):
        base = Vector((x, mast_y - 0.02, deck_z + 0.5))
        tip = Vector((x, mast_y - 0.02, head_top - 0.05))
        kit.hydraulic(cyl, rods, base, tip, 0.055, body_ratio=0.5, body_mat=YELLOW)
        kit.beam(rods, tip, (x * 0.5, mast_y - 0.12, head_top - 0.05), 0.06, 0.06, kit.DARK)
        kit.pipe_run(cyl, [base + Vector((0.07 * (1 if x > 0 else -1), 0.06, 0.1)),
                            base + Vector((0.07 * (1 if x > 0 else -1), 0.3, 0.1)),
                            Vector((x * 1.4, 0.2, deck_z + 0.9))], 0.018, kit.RUBBER, flanges=False)
    # Rotary head carriage (moves with feed): gearbox + motor + guide shoes.
    head = ctx.geo("rotary_head", bone="feed")
    hc = Vector((0.0, mast_y - 0.3, head_top))
    head.box((0.66, 0.46, 0.5), matrix=trs(hc), mat=YELLOW, bevel=0.03, segments=2)
    for x in (-0.24, 0.24):
        head.box((0.14, 0.2, 0.36), matrix=trs((x, mast_y + 0.02, head_top)), mat=kit.DARK, bevel=0.01)
    kit.motor(head, hc + Vector((0.0, 0.0, 0.42)), (0, 0, 1), 0.16, 0.34, mat="paint:machine_blue")
    kit.bolt_grid(head, hc + Vector((0.0, -0.232, 0.0)), (1, 0, 0), (0, 0, 1), 4, 3, 0.16, 0.14, (0, -1, 0))
    # Drill string (spins): kelly bar, stabiliser, tri-cone bit near the ground.
    rod = ctx.geo("drill_string", bone="spindle")
    top = Vector((0.0, mast_y - 0.32, head_top - 0.25))
    bottom_z = 0.22
    rod.cylinder(0.055, top.z - bottom_z, segments=6, matrix=trs((top.x, top.y, (top.z + bottom_z) / 2)), mat=kit.STEEL)
    rod.cylinder(0.08, 0.12, segments=16, matrix=trs((top.x, top.y, top.z - 0.08)), mat=kit.DARK, bevel=0.01)
    for k in range(3):
        a = 2 * math.pi * k / 3
        rod.box((0.03, 0.16, 0.3), matrix=trs((top.x + math.cos(a) * 0.07, top.y + math.sin(a) * 0.07, 1.1),
                                              (0, 0, math.degrees(a) + 90)), mat=kit.DARK, bevel=0.006)
        rod.sphere(0.07, segments=10, rings=6, matrix=trs((top.x + math.cos(a) * 0.05, top.y + math.sin(a) * 0.05, 0.12)),
                   mat="steel", scale=(1.0, 1.0, 1.3))
    rod.cylinder(0.1, 0.12, segments=16, matrix=trs((top.x, top.y, 0.26)), mat=kit.DARK, bevel=0.01)
    # Rod rack beside the mast.
    rack = ctx.geo("rod_rack")
    for k in range(5):                                      # spare rods lying along Y on two cradles
        x = 0.56 + 0.1 * (k % 3) + 0.05 * (k // 3)
        rack.cylinder(0.04, 1.6, segments=8, matrix=trs((x, mast_y + 0.8, deck_z + 0.25 + 0.075 * (k // 3)), (90, 0, 0)),
                      mat=kit.STEEL)
    for y in (mast_y + 0.25, mast_y + 1.35):
        for x in (0.48, 0.86):
            kit.beam(rack, (x, y, deck_z), (x, y, deck_z + 0.42), 0.05, 0.05, kit.FRAME)
        kit.beam(rack, (0.48, y, deck_z + 0.18), (0.86, y, deck_z + 0.18), 0.05, 0.05, kit.FRAME)
    # --- operator platform on the left side with console and railing
    plat = ctx.geo("platform")
    px = -sx / 2 - 0.45
    kit.deck(plat, (px, -0.4, deck_z + 0.05), (0.9, 1.6), thickness=0.05)
    for y in (-1.15, 0.35):
        kit.beam(plat, (px + 0.4, y, deck_z), (-sx / 2 + 0.05, y, deck_z), 0.08, 0.08, kit.FRAME)
    kit.railing(plat, [(px - 0.42, 0.35, deck_z + 0.05), (px - 0.42, -1.15, deck_z + 0.05), (px + 0.4, -1.15, deck_z + 0.05)],
                mat=YELLOW)
    kit.ladder(plat, (px - 0.1, 0.42, 0.0), deck_z + 0.05, width=0.42, mat=YELLOW, facing=(0, 1, 0))
    # Operator faces the mast (+X) across the lever console.
    common.operate_station(ctx, plat, (px - 0.05, -0.55, deck_z + 0.05), 90.0)
    # Hydraulic manifold on the front of the skid: the kneeling mechanic's
    # service bolt sits on its face, clear of the skid for the worker's feet.
    man = Vector((0.62, -sy / 2 - 0.08, 0.72))
    body.box((0.42, 0.16, 0.6), matrix=trs(man), mat=kit.DARK, bevel=0.015, segments=1)
    for dx in (-0.12, 0.0, 0.12):
        kit.pipe_run(body, [man + Vector((dx, 0.05, 0.3)), man + Vector((dx, 0.05, 0.45)), man + Vector((dx * 0.5, 0.6, 0.45))],
                     0.016, kit.RUBBER, flanges=False)
    common.repair_at(ctx, det, (man.x, man.y - 0.08, man.z), (0.0, -1.0, 0.0))
    ctx.socket("output", (0.0, mast_y - 0.32, 0.0))
    # Collision: skid + power pack + mast.
    ctx.col_box((0.0, 0.0, deck_z / 2), (sx, sy, deck_z))
    ctx.col_box(tuple(pc + Vector((0.0, 0.0, 0.72))), (1.74, 1.44, 1.44))
    ctx.col_box((0.0, mast_y - 0.05, (deck_z + mast_top) / 2 + 0.1), (0.9, 0.7, mast_top - deck_z + 0.2))
    ctx.col_box((px, -0.4, deck_z / 2 + 0.55), (0.9, 1.6, deck_z + 1.1))

    def idle(t):
        return {"fan": (None, loop_spin((0, 1, 0), 3, t, 2.0))}

    def drill(t):
        T = 4.0
        u = t / T
        # Feed down over 75 % of the cycle, retract quickly; string spins 12 turns.
        if u < 0.75:
            depth = head_travel * (0.5 - 0.5 * math.cos(math.pi * u / 0.75))
        else:
            depth = head_travel * (0.5 + 0.5 * math.cos(math.pi * (u - 0.75) / 0.25))
        buzz = 0.004 * math.sin(2 * math.pi * 16 * u)
        return {
            "feed": (Vector((buzz, 0.0, -depth)), None),
            "spindle": (None, loop_spin((0, 0, 1), 12, t, T)),
            "fan": (None, loop_spin((0, 1, 0), 18, t, T)),
        }

    ctx.clip("Idle", 2.0, True, idle, "Engine idling, head parked at the top of the mast")
    ctx.clip("Work", 4.0, True, drill, "Drilling: rotary head feeds down 2.6 m while the drill string spins, then retracts")
    ctx.metadata["interaction"] = {"operate": "socket_operate", "repair": "socket_repair", "output": "socket_output"}
