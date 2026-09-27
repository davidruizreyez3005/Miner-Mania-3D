"""Containerised diesel generator set.

Mechanics: the engine turns the alternator and the radiator fan; exhaust
pulses lift the stack's rain cap. Bones:

* ``fan``       radiator fan, spins about +Y
* ``rain_cap``  exhaust flap, hinged about +X at the stack rim
* ``body``      enclosure on its isolation mounts (vibration)

Clips: ``Idle`` (low idle) and ``Work`` (full load). Origin: base centre;
radiator end at +Y, control panel at -Y.
"""

import math

from mathutils import Quaternion, Vector

from animation.machine_anim import loop_spin
from utilities.meshkit import trs

from .. import kit
from . import common

BODY = "paint_worn:industrial_yellow"


def build(ctx):
    L, W, H = 3.4, 1.4, 1.7
    base_h = 0.3
    base = ctx.geo("base_tank")
    base.box((W + 0.1, L + 0.1, base_h), matrix=trs((0.0, 0.0, base_h / 2)), mat=kit.FRAME, bevel=0.02, segments=1)
    for y in (-L / 2 + 0.3, L / 2 - 0.3):                       # fork pockets
        for x in (-0.35, 0.35):
            base.box((0.26, 0.12, 0.12), matrix=trs((x, y, 0.1)), mat=kit.DARK, bevel=0.004)
    ctx.bone("body", (0.0, 0.0, base_h), (0.0, 0.0, base_h + 0.5))
    enc = ctx.geo("enclosure", bone="body")
    edet = ctx.geo("enclosure_detail", bone="body", max_lod=1)
    c = Vector((0.0, 0.0, base_h + H / 2))
    enc.box((W, L, H), matrix=trs(c), mat=BODY, bevel=0.03, segments=2)
    enc.box((W + 0.04, L + 0.04, 0.06), matrix=trs(c + Vector((0.0, 0.0, H / 2))), mat=kit.DARK, bevel=0.01)
    # Side doors with louvres and hinges.
    for side in (-1, 1):
        for d in range(3):
            y0 = -L / 2 + 0.3 + d * 1.0
            enc.box((0.02, 0.92, H - 0.25), matrix=trs((side * (W / 2 + 0.005), y0 + 0.46, c.z)), mat=BODY, bevel=0.006)
            for k in range(5):
                enc.box((0.03, 0.7, 0.03), matrix=trs((side * (W / 2 + 0.018), y0 + 0.46, c.z - 0.3 + 0.13 * k), (side * 25, 0, 0)),
                        mat=kit.DARK, bevel=0.004)
            edet.box((0.03, 0.04, 0.16), matrix=trs((side * (W / 2 + 0.02), y0 + 0.9, c.z + 0.2)), mat=kit.CHROME, bevel=0.005)
    # Radiator grille (+Y) and fan behind it.
    rg = Vector((0.0, L / 2 + 0.02, c.z))
    enc.box((W - 0.2, 0.04, H - 0.3), matrix=trs(rg), mat=kit.DARK, bevel=0.01)
    for k in range(10):
        enc.box((W - 0.26, 0.02, 0.02), matrix=trs(rg + Vector((0.0, 0.025, -0.6 + 0.133 * k))), mat=kit.STEEL, bevel=0.003)
    fc = rg + Vector((0.0, -0.12, 0.0))
    ctx.bone("fan", tuple(fc), tuple(fc + Vector((0.0, -0.3, 0.0))), parent="body")
    fan = ctx.geo("fan", bone="fan")
    fan.cylinder(0.08, 0.1, segments=12, matrix=trs(fc, (90, 0, 0)), mat=kit.DARK)
    for k in range(7):
        a = 2 * math.pi * k / 7
        fan.box((0.09, 0.012, 0.44), matrix=trs(fc, (90, 0, 0)) @ trs((math.cos(a) * 0.26, math.sin(a) * 0.26, 0.0),
                                                                      (0, 0, math.degrees(a) + 90)) @ trs(rot=(0, 22, 0)),
                mat=kit.DARK, bevel=0.004)
    # Control panel door (-Y) with indicators and emergency stop.
    kit.control_panel(enc, (0.25, -L / 2 - 0.09, c.z + 0.2), facing=(0, -1, 0), size=(0.6, 0.16, 0.5))
    enc.cylinder(0.05, 0.04, segments=16, matrix=trs((-0.3, -L / 2 - 0.02, c.z + 0.35), (90, 0, 0)), mat="plastic:signal_red")
    enc.box((0.3, 0.12, 0.3), matrix=trs((-0.35, -L / 2 - 0.06, base_h + 0.35)), mat=kit.DARK, bevel=0.01)   # cable box
    for k in range(3):
        kit.pipe_run(edet, [(-0.45 + 0.1 * k, -L / 2 - 0.12, base_h + 0.3), (-0.45 + 0.1 * k, -L / 2 - 0.4, base_h + 0.25),
                            (-0.45 + 0.1 * k, -L / 2 - 0.55, 0.03)], 0.02, kit.RUBBER, flanges=False)
    # Exhaust stack with a hinged rain cap; lifting eyes.
    ex = Vector((0.4, 0.8, base_h + H))
    kit.pipe_run(enc, [ex, ex + Vector((0.0, 0.0, 0.7))], 0.075, kit.DARK, flanges=False)
    enc.cylinder(0.11, 0.35, segments=16, matrix=trs(ex + Vector((0.0, 0.0, 0.25))), mat=kit.DARK, bevel=0.01)   # silencer
    hinge = ex + Vector((0.0, 0.08, 0.72))
    ctx.bone("rain_cap", tuple(hinge), tuple(hinge + Vector((0.3, 0.0, 0.0))), parent="body", z_axis=(0, 0, 1))
    cap = ctx.geo("rain_cap", bone="rain_cap")
    cap.cylinder(0.09, 0.012, segments=16, matrix=trs(hinge + Vector((0.0, -0.08, 0.004))), mat=kit.DARK)
    cap.cylinder(0.012, 0.06, segments=8, matrix=trs(hinge, (0, 90, 0)), mat=kit.STEEL)
    for x in (-0.5, 0.5):
        for y in (-1.3, 1.3):
            edet.torus(0.05, 0.014, seg_major=12, seg_minor=5, matrix=trs((x, y, base_h + H + 0.07), (90, 0, 0)), mat=kit.DARK)
    kit.beacon(edet, (-0.4, -1.2, base_h + H + 0.03))
    kit.warning_sign(edet, (W / 2 + 0.03, -1.0, c.z + 0.55), facing=(1, 0, 0), size=0.24)
    # Stations: start button below the control panel (Interact clip), service
    # bolt on the right-hand filter housing (Repair clip).
    common.interact_at(ctx, enc, (0.25, -L / 2 - 0.01, 1.12), (0.0, -1.0, 0.0))
    ctx.socket("power_out", (-0.45, -L / 2 - 0.55, 0.03))
    fh = Vector((W / 2 + 0.07, 0.8, 0.66))
    base.box((0.14, 0.34, 0.36), matrix=trs(fh), mat=kit.DARK, bevel=0.01)
    common.repair_at(ctx, edet, fh + Vector((0.07, 0.0, 0.0)), (1.0, 0.0, 0.0))
    ctx.col_box((0.0, 0.0, base_h / 2), (W + 0.1, L + 0.1, base_h))
    ctx.col_box(tuple(c), (W + 0.05, L + 0.06, H))
    ctx.col_cylinder(tuple(ex + Vector((0.0, 0.0, 0.4))), 0.12, 0.8)

    def idle(t):
        T = 2.0
        flap = math.radians(6 + 3 * math.sin(2 * math.pi * 4 * t / T))
        return {"fan": (None, loop_spin((0, 1, 0), 6, t, T)),
                "rain_cap": (None, Quaternion((1, 0, 0), -flap)),
                "body": (Vector((0.0005 * math.sin(2 * math.pi * 12 * t / T), 0.0, 0.0)), None)}

    def work(t):
        T = 2.0
        flap = math.radians(22 + 10 * abs(math.sin(2 * math.pi * 6 * t / T)))
        buzz = 0.0015 * math.sin(2 * math.pi * 24 * t / T)
        return {"fan": (None, loop_spin((0, 1, 0), 24, t, T)),
                "rain_cap": (None, Quaternion((1, 0, 0), -flap)),
                "body": (Vector((buzz, 0.0, 0.5 * buzz)), None)}

    ctx.clip("Idle", 2.0, True, idle, "Low idle: slow fan, rain cap barely lifting")
    ctx.clip("Work", 2.0, True, work, "Full load: fan at speed, exhaust lifting the rain cap, enclosure vibration")
    ctx.metadata["interaction"] = {"interact": "socket_interact", "repair": "socket_repair", "output": "socket_power_out"}
