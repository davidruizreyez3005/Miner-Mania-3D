"""Skid-mounted triplex plunger pump (mine dewatering).

Mechanics: the motor drives the crankshaft sheave through V-belts; the
crankshaft (inside the crankcase) strokes three plungers 120 degrees apart
into the fluid end, which draws from the suction manifold and pushes into the
discharge manifold; a gauge reads the discharge pressure. Bones:

* ``sheave``            crankshaft + sheave, spins about +X
* ``motor_pulley``      spins about +X
* ``plunger_1..3``      reciprocate along -Y
* ``needle``            pressure gauge needle, turns about the dial axis

Clips: ``Idle`` (coasting, needle at rest) and ``Work`` (pumping).
Origin: base centre; fluid end at -Y.
"""

import math

from mathutils import Quaternion, Vector

from animation.machine_anim import loop_spin
from utilities.meshkit import trs

from .. import kit
from . import common

BODY = "paint_worn:machine_green"


def build(ctx):
    L, W, sk = 2.6, 1.5, 0.22
    base = ctx.geo("skid")
    det = ctx.geo("skid_detail", max_lod=1)
    for x in (-W / 2 + 0.08, W / 2 - 0.08):
        kit.beam(base, (x, -L / 2, sk / 2), (x, L / 2, sk / 2), 0.14, sk, kit.FRAME, profile="C")
    kit.deck(base, (0.0, 0.0, sk), (W, L), mat=kit.FRAME, edge_mat=kit.HAZARD, thickness=0.03)
    # Crankcase with the crankshaft along X.
    cc = Vector((0.0, 0.1, sk + 0.4))
    base.box((0.9, 0.7, 0.62), matrix=trs(cc), mat=BODY, bevel=0.04, segments=2)
    base.box((0.96, 0.18, 0.66), matrix=trs(cc + Vector((0.0, -0.4, 0.0))), mat=BODY, bevel=0.02)
    kit.bolt_grid(det, cc + Vector((0.0, 0.352, 0.0)), (1, 0, 0), (0, 0, 1), 4, 3, 0.2, 0.17, (0, 1, 0))
    for x in (-0.47, 0.47):
        base.cylinder(0.14, 0.08, segments=20, matrix=trs(cc + Vector((x, 0.0, 0.0)), (0, 90, 0)), mat=kit.DARK, bevel=0.01)
    # Fluid end block, manifolds, valves, gauge.
    fe = Vector((0.0, -0.78, sk + 0.4))
    base.box((0.95, 0.42, 0.5), matrix=trs(fe), mat=kit.DARK, bevel=0.03)
    for k in range(3):
        x = -0.3 + 0.3 * k
        det.cylinder(0.07, 0.06, segments=12, matrix=trs(fe + Vector((x, -0.2, 0.12)), (90, 0, 0)), mat=kit.STEEL)
        kit.bolt_circle(det, fe + Vector((x, -0.24, 0.12)), (0, -1, 0), 0.055, 6)
    suc = fe + Vector((0.0, 0.0, -0.3))
    kit.pipe_run(base, [suc + Vector((-0.75, 0.0, 0.0)), suc + Vector((0.6, 0.0, 0.0)), suc + Vector((0.6, 0.0, -0.1))], 0.09,
                 "paint_worn:safety_orange")
    dis = fe + Vector((0.0, 0.0, 0.34))
    kit.pipe_run(base, [dis + Vector((-0.5, 0.0, 0.0)), dis + Vector((0.55, 0.0, 0.0)), dis + Vector((0.55, 0.0, 0.5)),
                        dis + Vector((0.55, -0.6, 0.5))], 0.07, "paint_worn:signal_red")
    kit.valve_wheel(base, dis + Vector((-0.2, -0.1, 0.12)), (0, -1, 0.4), 0.12)
    # Pressure gauge on a riser.
    gz = dis + Vector((0.2, -0.05, 0.3))
    kit.beam(base, dis + Vector((0.2, 0.0, 0.05)), gz, 0.03, 0.03, kit.STEEL, profile="tube")
    base.cylinder(0.09, 0.05, segments=20, matrix=trs(gz, (90, 0, 0)), mat=kit.CHROME, bevel=0.008)
    base.cylinder(0.078, 0.052, segments=20, matrix=trs(gz + Vector((0.0, -0.002, 0.0)), (90, 0, 0)), mat="plastic:plastic_white")
    ctx.bone("needle", tuple(gz + Vector((0.0, -0.03, 0.0))), tuple(gz + Vector((0.0, -0.03, 0.06))), z_axis=(0, -1, 0))
    nd = ctx.geo("needle", bone="needle")
    nd.box((0.008, 0.004, 0.06), matrix=trs(gz + Vector((0.0, -0.03, 0.022))), mat="paint:signal_red", bevel=0.0)
    # Plungers (reciprocate between crankcase and fluid end).
    for k in range(3):
        x = -0.3 + 0.3 * k
        head = Vector((x, -0.45, sk + 0.4))
        name = f"plunger_{k + 1}"
        ctx.bone(name, tuple(head), tuple(head + Vector((0.0, -0.2, 0.0))))
        pg = ctx.geo(name, bone=name)
        pg.cylinder(0.045, 0.3, segments=12, matrix=trs(head + Vector((0.0, -0.08, 0.0)), (90, 0, 0)), mat=kit.CHROME)
        pg.cylinder(0.07, 0.08, segments=12, matrix=trs(head + Vector((0.0, 0.05, 0.0)), (90, 0, 0)), mat=kit.DARK, bevel=0.008)
    # Sheave on the crankshaft (+X side) and the motor with belts.
    sh = cc + Vector((0.62, 0.0, 0.0))
    ctx.bone("sheave", tuple(sh), tuple(sh + Vector((0.3, 0.0, 0.0))), z_axis=(0, 0, 1))
    sg = ctx.geo("sheave", bone="sheave")
    kit.pulley(sg, sh, (1, 0, 0), 0.34, 0.14, grooves=3)
    for k in range(5):
        a = 2 * math.pi * k / 5
        d = Vector((0.0, math.cos(a), math.sin(a)))
        kit.beam(sg, sh + d * 0.08, sh + d * 0.3, 0.05, 0.03, kit.DARK, up=(1, 0, 0))
    mc = Vector((0.45, 0.95, sk + 0.3))
    kit.motor(base, mc, (1, 0, 0), 0.22, 0.55, mat=BODY, shaft=False)
    mp = mc + Vector((0.4, 0.0, 0.0))
    ctx.bone("motor_pulley", tuple(mp), tuple(mp + Vector((0.3, 0.0, 0.0))), z_axis=(0, 0, 1))
    kit.pulley(ctx.geo("motor_pulley", bone="motor_pulley"), mp, (1, 0, 0), 0.12, 0.14, grooves=3)
    kit.belt(base, mp + Vector((0.0, 0.0, 0.0)), 0.12, sh + Vector((0.0, 0.0, 0.0)) + Vector((mp.x - sh.x, 0.0, 0.0)), 0.34,
             (1, 0, 0), width=0.12, thick=0.016)
    base.box((0.05, 1.3, 0.8), matrix=trs((mp.x + 0.14, (mp.y + sh.y) / 2, (mp.z + sh.z) / 2 + 0.05)), mat=kit.HAZARD,
             bevel=0.01)
    # Stations: lever console at the rear-left, service bolt on the motor terminal box.
    common.operate_facing(ctx, base, (-0.45, L / 2 + 0.52, 0.0), (0.0, -1.0, 0.0))
    # Motor junction box hanging past the skid end (clear ground for the kneeling mechanic).
    jb = Vector((0.45, L / 2 + 0.07, 0.62))
    base.box((0.3, 0.14, 0.36), matrix=trs(jb), mat=kit.DARK, bevel=0.01)
    kit.beam(base, (0.45, mc.y + 0.2, sk + 0.1), jb + Vector((0.0, 0.0, -0.1)), 0.05, 0.05, kit.FRAME)
    common.repair_at(ctx, det, jb + Vector((0.0, 0.07, 0.0)), (0.0, 1.0, 0.0))
    ctx.socket("input", tuple(suc + Vector((-0.75, 0.0, 0.0))))
    ctx.socket("output", tuple(dis + Vector((0.55, -0.6, 0.5))))
    ctx.col_box((0.0, 0.0, sk / 2), (W, L, sk))
    ctx.col_box(tuple(cc + Vector((0.0, -0.3, 0.0))), (1.0, 1.4, 0.7))
    ctx.col_box((0.25, 0.9, sk + 0.3), (1.2, 0.6, 0.6))
    ctx.col_box((0.2, -1.0, sk + 0.75), (1.4, 0.6, 1.0))

    def idle(t):
        return {"sheave": (None, loop_spin((1, 0, 0), 1, t, 4.0)),
                "motor_pulley": (None, loop_spin((1, 0, 0), 3, t, 4.0)),
                "needle": (None, Quaternion((0, -1, 0), math.radians(-100)))}

    def work(t):
        T, turns = 1.5, 3
        ang = 2 * math.pi * turns * t / T
        out = {"sheave": (None, loop_spin((1, 0, 0), turns, t, T)),
               "motor_pulley": (None, loop_spin((1, 0, 0), turns * 3, t, T)),
               "needle": (None, Quaternion((0, -1, 0), math.radians(40 + 4 * math.sin(2 * ang))))}
        for k in range(3):
            stroke = 0.04 * (1 - math.cos(ang + 2 * math.pi * k / 3))
            out[f"plunger_{k + 1}"] = (Vector((0.0, -stroke, 0.0)), None)
        return out

    ctx.clip("Idle", 4.0, True, idle, "Coasting; gauge at rest")
    ctx.clip("Work", 1.5, True, work, "Pumping at 2 rev/s: plungers 120 degrees apart, gauge at working pressure")
    ctx.metadata["interaction"] = {"operate": "socket_operate", "repair": "socket_repair", "input": "socket_input",
                                   "output": "socket_output"}
