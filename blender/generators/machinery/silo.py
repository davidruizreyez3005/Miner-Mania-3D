"""Ore storage silo with conical discharge hopper.

Mechanics: a welded bin on four braced legs; a rack-and-pinion slide gate at
the cone outlet meters ore onto whatever is parked underneath; a float-level
indicator on the side shows the fill. Bones:

* ``gate``       slide gate, translates along +X to open
* ``handwheel``  gate handwheel, spins about +Y while the gate moves
* ``level``      level indicator pointer, travels along the gauge

Clips: ``Idle`` (closed) and ``Work`` (gate opens, level drops, gate closes).
Origin: base centre between the legs.
"""

import math

from mathutils import Quaternion, Vector

from utilities.meshkit import trs

from .. import kit
from . import common

SHELL = "metal:galvanized"
FRAME = "paint_worn:machine_blue"


def build(ctx):
    R = ctx.param("radius", 1.5)
    h_cyl = ctx.param("height", 4.0)
    cone_bot = 1.9
    cone_top = cone_bot + 1.3
    top = cone_top + h_cyl
    shell = ctx.geo("shell")
    det = ctx.geo("shell_detail", max_lod=1)
    prof = [(0.25, cone_bot), (R, cone_top), (R, top), (R * 0.9, top + 0.35), (0.35, top + 0.5), (0.0, top + 0.5)]
    shell.lathe([(0.0, cone_bot)] + prof, segments=40, mat=SHELL)
    for k in range(5):                                          # weld seams / stiffener rings
        z = cone_top + h_cyl * k / 4
        shell.torus(R + 0.015, 0.025, seg_major=40, seg_minor=6, matrix=trs((0.0, 0.0, z)), mat=kit.DARK)
    shell.cylinder(0.3, 0.2, segments=20, matrix=trs((0.0, 0.0, top + 0.55)), mat=kit.DARK, bevel=0.02)   # roof vent
    shell.cylinder(0.25, 0.4, segments=16, matrix=trs((0.0, 0.0, cone_bot - 0.15)), mat=kit.DARK, bevel=0.01)
    # Legs with bracing.
    legs = []
    for k in range(4):
        a = math.pi / 4 + k * math.pi / 2
        p = Vector((math.cos(a) * R * 0.92, math.sin(a) * R * 0.92, 0.0))
        legs.append(p)
        kit.beam(shell, p, p + Vector((0.0, 0.0, cone_top + 0.4)), 0.2, 0.2, FRAME, profile="I", up=(math.cos(a), math.sin(a), 0))
        shell.box((0.4, 0.4, 0.04), matrix=trs(p + Vector((0.0, 0.0, 0.02))), mat=kit.DARK, bevel=0.006)
    for i in range(4):
        a, b = legs[i], legs[(i + 1) % 4]
        kit.beam(shell, a + Vector((0.0, 0.0, 0.5)), b + Vector((0.0, 0.0, cone_top - 0.3)), 0.07, 0.07, FRAME, profile="tube")
        kit.beam(shell, b + Vector((0.0, 0.0, 0.5)), a + Vector((0.0, 0.0, cone_top - 0.3)), 0.07, 0.07, FRAME, profile="tube")
        kit.beam(shell, a + Vector((0.0, 0.0, cone_top - 0.3)), b + Vector((0.0, 0.0, cone_top - 0.3)), 0.12, 0.12, FRAME)
    # Roof railing and caged ladder.
    ring = [Vector((math.cos(2 * math.pi * k / 16) * (R - 0.1), math.sin(2 * math.pi * k / 16) * (R - 0.1), top + 0.02))
            for k in range(17)]
    kit.railing(shell, ring, height=1.0, mat="paint_worn:industrial_yellow", post_spacing=1.2, toe=False)
    kit.ladder(shell, (0.0, -R - 0.18, cone_top - 0.2), h_cyl + 0.25, mat="paint_worn:industrial_yellow", facing=(0, -1, 0),
               cage=True)
    kit.ladder(shell, (0.0, -R * 0.92 - 0.35, 0.0), cone_top - 0.2, mat="paint_worn:industrial_yellow", facing=(0, -1, 0))
    # Slide gate (moves) + handwheel.
    gz = cone_bot - 0.4
    shell.box((0.9, 0.5, 0.12), matrix=trs((0.25, 0.0, gz)), mat=kit.DARK, bevel=0.01)
    ctx.bone("gate", (0.0, 0.0, gz - 0.02), (0.3, 0.0, gz - 0.02))
    gate = ctx.geo("gate", bone="gate")
    gate.box((0.55, 0.46, 0.03), matrix=trs((0.0, 0.0, gz - 0.02)), mat=kit.STEEL, bevel=0.004)
    gate.box((0.04, 0.5, 0.08), matrix=trs((0.3, 0.0, gz - 0.02)), mat=kit.DARK, bevel=0.004)
    hw = Vector((0.75, -0.3, gz))
    ctx.bone("handwheel", tuple(hw), tuple(hw + Vector((0.0, -0.25, 0.0))), z_axis=(0, 0, 1))
    kit.valve_wheel(ctx.geo("handwheel", bone="handwheel"), hw, (0, -1, 0), 0.16)
    # Level indicator: gauge board with a travelling pointer.
    gb = Vector((R + 0.06, 0.0, cone_top + h_cyl * 0.5))
    shell.box((0.04, 0.12, h_cyl * 0.8), matrix=trs(gb), mat="paint_clean:sign_white", bevel=0.006)
    for k in range(9):
        det.box((0.02, 0.06, 0.012), matrix=trs(gb + Vector((0.025, 0.0, -h_cyl * 0.38 + h_cyl * 0.095 * k))), mat=kit.DARK)
    top_lvl = gb + Vector((0.05, 0.0, h_cyl * 0.35))
    ctx.bone("level", tuple(top_lvl), tuple(top_lvl + Vector((0.2, 0.0, 0.0))), z_axis=(0, 0, 1))
    lv = ctx.geo("level_pointer", bone="level")
    lv.box((0.06, 0.18, 0.05), matrix=trs(top_lvl), mat="paint:signal_red", bevel=0.01)
    # Stations: Interact button box on a leg; service bolt on the gate gearbox.
    common.interact_at(ctx, shell, legs[3] + Vector((0.0, -0.11, 0.0)), (0.0, -1.0, 0.0))
    gbx = Vector((0.75, 0.3, 0.72))
    kit.beam(shell, (0.75, 0.3, 0.0), (0.75, 0.3, 0.5), 0.08, 0.08, FRAME)
    shell.box((0.26, 0.26, 0.36), matrix=trs(gbx), mat=kit.DARK, bevel=0.01)
    common.repair_at(ctx, det, gbx + Vector((0.13, 0.0, 0.0)), (1.0, 0.0, 0.0))
    ctx.socket("output", (0.0, 0.0, gz - 0.1))
    ctx.socket("input", (0.0, 0.0, top + 0.5))
    ctx.col_cylinder((0.0, 0.0, (cone_top + top) / 2), R + 0.03, h_cyl + 0.05)
    ctx.col_hull([(math.cos(a) * R, math.sin(a) * R, cone_top) for a in [k * math.pi / 6 for k in range(12)]] +
                 [(math.cos(a) * 0.3, math.sin(a) * 0.3, cone_bot) for a in [k * math.pi / 6 for k in range(12)]])
    for p in legs:
        ctx.col_box(tuple(p + Vector((0.0, 0.0, (cone_top + 0.4) / 2))), (0.22, 0.22, cone_top + 0.4))

    def work(t):
        T = 5.0
        u = t / T
        # Gate opens over the first 20 %, stays open to 60 %, closes by 80 %.
        if u < 0.2:
            k = u / 0.2
        elif u < 0.6:
            k = 1.0
        elif u < 0.8:
            k = 1.0 - (u - 0.6) / 0.2
        else:
            k = 0.0
        opening = 0.5 - 0.5 * math.cos(math.pi * k)
        drop = 0.4 * h_cyl * 0.35 * math.sin(math.pi * u)      # level falls while discharging, refills
        return {"gate": (Vector((0.42 * opening, 0.0, 0.0)), None),
                "handwheel": (None, Quaternion((0, -1, 0), 6.0 * math.pi * k)),     # three turns to open
                "level": (Vector((0.0, 0.0, -drop)), None)}

    ctx.clip("Idle", 2.0, True, lambda t: {}, "Gate closed")
    ctx.clip("Work", 5.0, True, work, "Slide gate opens, ore discharges (level drops), gate closes")
    ctx.metadata["interaction"] = {"interact": "socket_interact", "repair": "socket_repair", "input": "socket_input",
                                   "output": "socket_output"}
