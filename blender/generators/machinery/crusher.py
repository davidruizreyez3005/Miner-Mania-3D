"""Jaw crusher on a steel frame.

Mechanics: an electric motor drives the flywheels through V-belts; the
flywheels sit on the eccentric shaft that swings the moving jaw against the
fixed jaw, crushing ore fed from the hopper. Bones:

* ``flywheel``   eccentric shaft + both flywheels, spins about +X
* ``jaw``        swing jaw, pivots about the eccentric shaft (+X)
* ``motor_pulley`` motor sheave, spins about +X
* ``body``       crusher housing (vibration while crushing)

Clips: ``Idle`` (coasting) and ``Work`` (crushing: 2 rev/s, jaw stroke,
housing vibration). Origin: base centre. Feed from the top, discharge at -Y.
"""

import math

from mathutils import Quaternion, Vector

from animation.machine_anim import loop_spin
from utilities.meshkit import trs

from .. import kit
from . import common

BODY = "paint_worn:machine_blue"


def build(ctx):
    L, W = 3.2, 2.2
    frame_h = 0.45
    body_c = Vector((0.0, 0.1, frame_h))
    shaft = Vector((0.0, 0.55, frame_h + 1.45))
    base = ctx.geo("frame")
    det = ctx.geo("frame_detail", max_lod=1)
    for x in (-W / 2 + 0.12, W / 2 - 0.12):
        kit.beam(base, (x, -L / 2, frame_h / 2), (x, L / 2, frame_h / 2), 0.2, frame_h, kit.FRAME, profile="I")
    for y in (-L / 2 + 0.15, -0.4, 0.6, L / 2 - 0.15):
        kit.beam(base, (-W / 2 + 0.2, y, frame_h - 0.1), (W / 2 - 0.2, y, frame_h - 0.1), 0.14, 0.18, kit.FRAME, profile="I")
    # Housing: cheek plates + front/back walls (on the vibrating body bone).
    ctx.bone("body", tuple(body_c), tuple(body_c + Vector((0, 0, 0.4))))
    housing = ctx.geo("housing", bone="body")
    hdet = ctx.geo("housing_detail", bone="body", max_lod=1)
    for x in (-0.62, 0.62):
        housing.box((0.16, 1.9, 1.6), matrix=trs((x, body_c.y, frame_h + 0.8)), mat=BODY, bevel=0.03, segments=2)
        kit.bolt_grid(hdet, (x * 1.13, body_c.y, frame_h + 0.8), (0, 1, 0), (0, 0, 1), 5, 4, 0.36, 0.35,
                      (1 if x > 0 else -1, 0, 0))
        for k in range(3):                                   # stiffening ribs
            housing.box((0.05, 0.08, 1.5), matrix=trs((x * 1.1, body_c.y - 0.6 + 0.6 * k, frame_h + 0.8)), mat=BODY,
                        bevel=0.01)
    housing.box((1.4, 0.25, 1.1), matrix=trs((0.0, body_c.y + 0.85, frame_h + 1.05)), mat=BODY, bevel=0.03)
    # Fixed jaw (inclined liner at the front) and the discharge throat.
    housing.box((1.08, 0.18, 1.5), matrix=trs((0.0, body_c.y - 0.62, frame_h + 0.85), (-12, 0, 0)), mat=kit.DARK,
                bevel=0.02)
    for k in range(7):                                       # manganese liner teeth
        hdet.box((1.02, 0.05, 0.06), matrix=trs((0.0, body_c.y - 0.52 + 0.022 * k, frame_h + 0.3 + 0.2 * k), (-12, 0, 0)),
                 mat="steel", bevel=0.01)
    # Hopper above the jaw cavity.
    kit.hopper(housing, (0.0, body_c.y - 0.1), (2.0, 1.8), (1.1, 0.8), frame_h + 2.35, frame_h + 1.6, wall=0.04,
               mat="paint_worn:industrial_yellow", rim=0.06, rim_mat=kit.HAZARD)
    # Moving jaw on the eccentric shaft.
    ctx.bone("jaw", tuple(shaft), tuple(shaft + Vector((0.4, 0, 0))), parent="body", z_axis=(0, 0, 1))
    jaw = ctx.geo("swing_jaw", bone="jaw")
    jaw.box((1.02, 0.34, 1.45), matrix=trs(shaft + Vector((0.0, -0.3, -0.7)), (8, 0, 0)), mat=kit.DARK, bevel=0.03)
    for k in range(7):
        jaw.box((0.98, 0.05, 0.06), matrix=trs(shaft + Vector((0.0, -0.49 - 0.012 * k, -1.3 + 0.2 * k)), (8, 0, 0)),
                mat="steel", bevel=0.01)
    jaw.cylinder(0.18, 1.12, segments=20, matrix=trs(shaft, (0, 90, 0)), mat=kit.STEEL, bevel=0.01)
    # Flywheels on the shaft (spin with it).
    ctx.bone("flywheel", tuple(shaft + Vector((0.0, 0.0, 0.0))), tuple(shaft + Vector((0.5, 0, 0))), parent="body",
             z_axis=(0, 0, 1))
    fly = ctx.geo("flywheels", bone="flywheel")
    for x in (-0.95, 0.95):
        c = shaft + Vector((x, 0.0, 0.0))
        fly.tube(0.78, 0.66, 0.2, segments=40, matrix=trs(c, (0, 90, 0)), mat="paint_worn:signal_red", bevel=0.01)
        fly.cylinder(0.17, 0.26, segments=16, matrix=trs(c, (0, 90, 0)), mat=kit.DARK, bevel=0.01)
        for k in range(6):
            a = 2 * math.pi * k / 6
            d = Vector((0.0, math.cos(a), math.sin(a)))
            kit.beam(fly, c + d * 0.15, c + d * 0.67, 0.08, 0.05, "paint_worn:signal_red", up=(1, 0, 0))
        if x > 0:
            for k in range(3):                               # V-belt grooves on the drive flywheel
                fly.torus(0.78, 0.012, seg_major=40, seg_minor=5, matrix=trs(c + Vector((0.05 * (k - 1), 0, 0)), (0, 90, 0)),
                          mat=kit.DARK)
    # Bearings on the cheek plates.
    for x in (-0.72, 0.72):
        housing.box((0.24, 0.42, 0.34), matrix=trs(shaft + Vector((x, 0.0, -0.05))), mat=kit.DARK, bevel=0.03)
    # Motor on a slide rail beside the frame, V-belts to the drive flywheel.
    mc = Vector((0.95, 1.2, frame_h + 0.35))
    kit.beam(base, (0.7, 1.2, frame_h), (1.3, 1.2, frame_h), 0.14, 0.1, kit.FRAME)
    kit.motor(base, mc, (1, 0, 0), 0.26, 0.6, mat=BODY, shaft=False)
    ctx.bone("motor_pulley", tuple(mc + Vector((0.42, 0, 0))), tuple(mc + Vector((0.8, 0, 0))), z_axis=(0, 0, 1))
    mp = ctx.geo("motor_pulley", bone="motor_pulley")
    kit.pulley(mp, mc + Vector((0.42, 0, 0)), (1, 0, 0), 0.2, 0.16, grooves=3)
    kit.belt(base, mc + Vector((0.46, 0, 0)), 0.2, shaft + Vector((0.95 + 0.05, 0, 0)), 0.78, (1, 0, 0), width=0.14,
             thick=0.018)
    base.box((0.06, 1.6, 0.9), matrix=trs((1.3, 0.85, frame_h + 1.0), (32, 0, 0)), mat=kit.HAZARD, bevel=0.01)
    # Discharge chute toward -Y.
    kit.chute(base, (0.0, -0.75, frame_h + 0.25), (0.0, -L / 2 - 0.2, 0.3), 0.9, depth=0.18, mat=kit.DARK)
    # Walkway on the right with ladder, railing, operator console.
    wk = ctx.geo("walkway")
    wx = -W / 2 - 0.5
    kit.deck(wk, (wx, 0.2, frame_h + 1.3), (0.9, 2.2), thickness=0.05)
    for y in (-0.8, 1.2):
        kit.beam(wk, (wx - 0.4, y, 0.0), (wx - 0.4, y, frame_h + 1.3), 0.08, 0.08, kit.FRAME)
        kit.beam(wk, (wx + 0.4, y, 0.0), (wx + 0.4, y, frame_h + 1.3), 0.08, 0.08, kit.FRAME)
    kit.railing(wk, [(wx - 0.42, -0.85, frame_h + 1.3), (wx - 0.42, 1.25, frame_h + 1.3), (wx + 0.42, 1.25, frame_h + 1.3)],
                mat="paint_worn:industrial_yellow")
    kit.ladder(wk, (wx + 0.1, -0.9, 0.0), frame_h + 1.3, mat="paint_worn:industrial_yellow", facing=(0, -1, 0))
    common.operate_station(ctx, wk, (wx - 0.1, 0.55, frame_h + 1.3), 90.0)
    kit.lamp(wk, (wx - 0.4, 1.2, frame_h + 2.5), (0.3, -0.3, -0.8))
    kit.beam(wk, (wx - 0.4, 1.2, frame_h + 1.3), (wx - 0.4, 1.2, frame_h + 2.45), 0.05, 0.05, kit.FRAME, profile="tube")
    kit.warning_sign(hdet, (0.0, body_c.y + 1.0, frame_h + 1.3), facing=(0, 1, 0))
    # Service point for the Repair clip: motor terminal cover on the outside.
    tb = Vector((mc.x + 0.39, mc.y, 0.5))
    base.box((0.18, 0.2, 0.52), matrix=trs(tb), mat=kit.DARK, bevel=0.01)
    common.repair_at(ctx, det, tb + Vector((0.09, 0.0, 0.0)), (1.0, 0.0, 0.0))
    ctx.socket("input", (0.0, body_c.y - 0.1, frame_h + 2.4))
    ctx.socket("output", (0.0, -L / 2 - 0.2, 0.3))
    ctx.col_box((0.0, 0.0, frame_h / 2), (W, L, frame_h))
    ctx.col_box((0.0, body_c.y, frame_h + 0.8), (1.5, 2.0, 1.6))
    ctx.col_hull([(x, body_c.y - 0.1 + y, frame_h + z) for x in (-1.0, 1.0) for y in (-0.9, 0.9) for z in (2.35,)] +
                 [(x, body_c.y - 0.1 + y, frame_h + 1.6) for x in (-0.55, 0.55) for y in (-0.4, 0.4)])
    ctx.col_cylinder(tuple(shaft), 0.8, 2.1, rot=(0, 90, 0))
    ctx.col_box((wx, 0.2, (frame_h + 1.3) / 2 + 0.5), (0.9, 2.2, frame_h + 2.3))

    def idle(t):
        return {"flywheel": (None, loop_spin((1, 0, 0), 1, t, 3.0)),
                "motor_pulley": (None, loop_spin((1, 0, 0), 4, t, 3.0))}

    def work(t):
        T = 2.0
        turns = 4
        ang = 2 * math.pi * turns * t / T
        swing = math.radians(3.5) * math.sin(ang)
        buzz = 0.003 * math.sin(2 * ang)
        return {
            "flywheel": (None, loop_spin((1, 0, 0), turns, t, T)),
            "motor_pulley": (None, loop_spin((1, 0, 0), turns * 4, t, T)),
            "jaw": (Vector((0.0, 0.012 * math.cos(ang), 0.01 * math.sin(ang))), Quaternion((1, 0, 0), swing)),
            "body": (Vector((buzz, 0.0, buzz * 0.5)), None),
        }

    ctx.clip("Idle", 3.0, True, idle, "Flywheels coasting")
    ctx.clip("Work", 2.0, True, work, "Crushing: eccentric shaft at 2 rev/s swings the jaw; housing vibrates")
    ctx.metadata["interaction"] = {"operate": "socket_operate", "repair": "socket_repair", "input": "socket_input",
                                   "output": "socket_output"}
