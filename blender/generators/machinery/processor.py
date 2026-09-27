"""Agitated leach / flotation tank (ore processing).

Mechanics: slurry enters through the feed pipe; a gear-motor on the top
bridge turns the agitator shaft and impeller; clean overflow runs off the
rim launder; a control valve on the discharge line and a pressure gauge are
worked from the operator console. Bones:

* ``agitator``     shaft + impeller + coupling, spins about +Z
* ``valve``        discharge valve handwheel, turns about the valve stem
* ``needle``       gauge needle

Clips: ``Idle`` (slow stir) and ``Work`` (full-speed agitation, valve
throttling, gauge responding). Origin: base centre.
"""

import math

from mathutils import Quaternion, Vector

from animation.machine_anim import loop_spin
from utilities.meshkit import trs

from .. import kit
from . import common

TANK = "paint_worn:cream_paint"
FRAME = "paint_worn:machine_blue"


def build(ctx):
    R, H = 1.4, 2.3
    plinth_h = 0.25
    base = ctx.geo("tank")
    det = ctx.geo("tank_detail", max_lod=1)
    base.cylinder(R + 0.25, plinth_h, segments=40, matrix=trs((0.0, 0.0, plinth_h / 2)), mat="concrete:concrete", bevel=0.02)
    z0, z1 = plinth_h, plinth_h + H
    base.lathe([(0.0, z0), (R, z0), (R, z1), (R - 0.06, z1), (R - 0.06, z0 + 0.1), (0.0, z0 + 0.1)], segments=40,
               mat=TANK)
    for k in range(4):                                           # hoops
        base.torus(R + 0.012, 0.022, seg_major=40, seg_minor=6, matrix=trs((0.0, 0.0, z0 + 0.3 + (H - 0.5) * k / 3)),
                   mat=kit.DARK)
    base.cylinder(R - 0.07, 0.02, segments=40, matrix=trs((0.0, 0.0, z1 - 0.18)), mat="paint:machine_green")   # slurry
    # Overflow launder around the rim.
    base.lathe([(R + 0.02, z1 - 0.2), (R + 0.22, z1 - 0.16), (R + 0.24, z1 + 0.05), (R + 0.2, z1 + 0.05),
                (R + 0.19, z1 - 0.12), (R + 0.02, z1 - 0.15)], segments=40, mat=TANK, caps=False, closed_loop=True)
    kit.pipe_run(base, [(R + 0.24, 0.3, z1 - 0.1), (R + 0.6, 0.3, z1 - 0.1), (R + 0.6, 0.3, 0.6), (R + 1.1, 0.3, 0.6)], 0.09,
                 "paint_worn:machine_green")
    # Bridge across the top with the drive.
    for s in (-1, 1):
        kit.beam(base, (-R - 0.15, s * 0.25, z1 + 0.12), (R + 0.15, s * 0.25, z1 + 0.12), 0.14, 0.2, FRAME, profile="I")
    kit.deck(base, (0.0, 0.0, z1 + 0.25), (2 * R + 0.3, 0.7), thickness=0.04)
    kit.railing(base, [(-R - 0.1, 0.36, z1 + 0.25), (R + 0.1, 0.36, z1 + 0.25)], mat="paint_worn:industrial_yellow")
    kit.railing(base, [(-R - 0.1, -0.36, z1 + 0.25), (R + 0.1, -0.36, z1 + 0.25)], mat="paint_worn:industrial_yellow")
    gb = Vector((0.0, 0.0, z1 + 0.5))
    base.box((0.5, 0.5, 0.45), matrix=trs(gb), mat=FRAME, bevel=0.03)
    kit.motor(base, gb + Vector((0.0, 0.0, 0.55)), (0, 0, 1), 0.2, 0.5, mat=FRAME, shaft=False)
    kit.ladder(base, (R + 0.2, -0.55, 0.0), z1 + 0.25, mat="paint_worn:industrial_yellow", facing=(1, 0, 0))
    # Agitator (rotates): coupling, shaft, impeller blades near the bottom.
    ctx.bone("agitator", (0.0, 0.0, z1 + 0.25), (0.0, 0.0, z1 + 0.55))
    ag = ctx.geo("agitator", bone="agitator")
    ag.cylinder(0.09, 0.16, segments=16, matrix=trs((0.0, 0.0, z1 + 0.2)), mat=kit.DARK, bevel=0.01)
    for k in range(4):
        a = k * math.pi / 2
        ag.box((0.04, 0.05, 0.12), matrix=trs((math.cos(a) * 0.09, math.sin(a) * 0.09, z1 + 0.2), (0, 0, math.degrees(a))),
               mat=kit.BOLT, bevel=0.004)
    ag.cylinder(0.05, H - 0.2, segments=10, matrix=trs((0.0, 0.0, z0 + 0.15 + (H - 0.2) / 2)), mat=kit.STEEL)
    for k in range(3):
        a = 2 * math.pi * k / 3
        ag.box((0.55, 0.12, 0.02), matrix=trs((math.cos(a) * 0.32, math.sin(a) * 0.32, z0 + 0.45), (35, 0, math.degrees(a))),
               mat=kit.STEEL, bevel=0.004)
    ag.cylinder(0.1, 0.12, segments=12, matrix=trs((0.0, 0.0, z0 + 0.45)), mat=kit.DARK, bevel=0.01)
    # Discharge line with control valve (handwheel turns) and gauge.
    dz = 0.55
    kit.pipe_run(base, [(0.0, -R, dz), (0.0, -R - 0.9, dz), (0.9, -R - 0.9, dz), (0.9, -R - 0.9, 0.08)], 0.08,
                 "paint_worn:signal_red")
    vb = Vector((0.0, -R - 0.5, dz))
    base.box((0.26, 0.26, 0.26), matrix=trs(vb), mat=kit.DARK, bevel=0.02)
    kit.beam(base, vb, vb + Vector((0.0, 0.0, 0.35)), 0.04, 0.04, kit.STEEL, profile="tube")
    hw = vb + Vector((0.0, 0.0, 0.36))
    ctx.bone("valve", tuple(hw), tuple(hw + Vector((0.0, 0.0, 0.2))))
    kit.valve_wheel(ctx.geo("valve", bone="valve"), hw, (0, 0, 1), 0.17)
    gz = Vector((0.45, -R - 0.9, dz + 0.28))
    kit.beam(base, (0.45, -R - 0.9, dz + 0.06), gz, 0.03, 0.03, kit.STEEL, profile="tube")
    base.cylinder(0.08, 0.05, segments=20, matrix=trs(gz, (90, 0, 0)), mat=kit.CHROME, bevel=0.008)
    base.cylinder(0.07, 0.052, segments=20, matrix=trs(gz + Vector((0.0, -0.002, 0.0)), (90, 0, 0)), mat="plastic:plastic_white")
    ctx.bone("needle", tuple(gz + Vector((0.0, -0.03, 0.0))), tuple(gz + Vector((0.0, -0.03, 0.05))), z_axis=(0, -1, 0))
    ctx.geo("needle", bone="needle").box((0.007, 0.004, 0.05), matrix=trs(gz + Vector((0.0, -0.03, 0.02))),
                                         mat="paint:signal_red", bevel=0.0)
    # Feed pipe in over the rim.
    kit.pipe_run(base, [(-R - 1.0, 0.0, 0.5), (-R - 0.4, 0.0, 0.5), (-R - 0.4, 0.0, z1 + 0.35), (-R + 0.4, 0.0, z1 + 0.35),
                        (-R + 0.4, 0.0, z1 - 0.1)], 0.07, "paint_worn:machine_green")
    kit.beacon(det, (0.3, 0.3, z1 + 0.27))
    kit.warning_sign(det, (0.0, -R - 0.02, z1 - 0.4), facing=(0, -1, 0))
    # Stations: lever console on the discharge side, pump-box service bolt.
    common.operate_facing(ctx, base, (-1.0, -R - 1.25, 0.0), (0.0, 1.0, 0.0))
    pb = Vector((-R - 0.75, 0.0, 0.5))
    base.box((0.3, 0.4, 0.5), matrix=trs(pb), mat=kit.DARK, bevel=0.02)
    common.repair_at(ctx, det, pb + Vector((0.0, 0.2, 0.0)), (0.0, 1.0, 0.0))
    ctx.socket("input", (-R - 1.0, 0.0, 0.5))
    ctx.socket("output", (0.9, -R - 0.9, 0.08))
    ctx.col_cylinder((0.0, 0.0, (z0 + z1) / 2), R + 0.25, z1 - z0 + 0.1)
    ctx.col_box((0.0, 0.0, z1 + 0.6), (2 * R + 0.4, 0.8, 0.8))
    ctx.col_box((0.45, -R - 0.7, dz), (1.3, 0.8, 0.9))

    def idle(t):
        return {"agitator": (None, loop_spin((0, 0, 1), 1, t, 4.0)),
                "needle": (None, Quaternion((0, -1, 0), math.radians(-30)))}

    def work(t):
        T = 4.0
        throttle = 0.5 - 0.5 * math.cos(2 * math.pi * t / T)
        return {"agitator": (None, loop_spin((0, 0, 1), 6, t, T)),
                "valve": (None, Quaternion((0, 0, 1), math.radians(-240 * throttle))),
                "needle": (None, Quaternion((0, -1, 0), math.radians(20 + 50 * throttle)))}

    ctx.clip("Idle", 4.0, True, idle, "Slow stir, valve closed")
    ctx.clip("Work", 4.0, True, work, "Full agitation at 1.5 rev/s; operator throttles the discharge valve, gauge follows")
    ctx.metadata["interaction"] = {"operate": "socket_operate", "repair": "socket_repair", "input": "socket_input",
                                   "output": "socket_output"}
