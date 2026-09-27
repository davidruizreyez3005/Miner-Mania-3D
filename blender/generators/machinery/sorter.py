"""Double-deck vibrating screen (ore sorter).

Mechanics: an exciter with unbalanced shafts on top of the screen box drives
a linear stroke along the throw angle; the box rides coil springs on the
frame. Coarse ore leaves over the top deck lip, mid-size over the lower
deck, fines drop into the pan. Bones:

* ``deck``      screen box + decks on the springs (linear throw)
* ``exciter``   unbalanced shaft pair, spins about +X

Clips: ``Idle`` (stopped) and ``Work`` (screening: 8 Hz stroke).
Origin: base centre; feed at +Y, discharge at -Y.
"""

import math

from mathutils import Vector

from animation.machine_anim import loop_spin
from utilities.meshkit import trs

from .. import kit
from . import common

BOX = "paint_worn:safety_orange"
FRAME = "paint_worn:dark_steel"


def build(ctx):
    L, W = 3.0, 1.5
    deck_tilt = 15.0
    frame = ctx.geo("frame")
    det = ctx.geo("frame_detail", max_lod=1)
    posts = [(-W / 2 - 0.1, -L / 2 + 0.3), (W / 2 + 0.1, -L / 2 + 0.3), (-W / 2 - 0.1, L / 2 - 0.3), (W / 2 + 0.1, L / 2 - 0.3)]
    heights = {}
    for x, y in posts:
        h = 0.9 + 0.8 * (y + L / 2) / L                       # feed end higher
        heights[(x, y)] = h
        kit.beam(frame, (x, y, 0.0), (x, y, h), 0.16, 0.16, FRAME, profile="I", up=(1, 0, 0))
        frame.box((0.3, 0.3, 0.02), matrix=trs((x, y, 0.01)), mat=kit.DARK, bevel=0.004)
        # Spring seat + coil spring.
        frame.box((0.26, 0.26, 0.04), matrix=trs((x, y, h + 0.02)), mat=kit.DARK, bevel=0.006)
        coil = [Vector((x + 0.07 * math.cos(2 * math.pi * k / 10), y + 0.07 * math.sin(2 * math.pi * k / 10), h + 0.05 + 0.02 * k))
                for k in range(61)]
        frame.sweep(coil, radius=0.012, segments=6, mat="paint:signal_red")
    for (xa, ya), (xb, yb) in ((posts[0], posts[2]), (posts[1], posts[3])):
        kit.beam(frame, (xa, ya, 0.35), (xb, yb, 0.35), 0.1, 0.12, FRAME, profile="C")
    # Screen box (vibrates as one rigid body).
    ctx.bone("deck", (0.0, 0.0, 1.6), (0.0, 0.0, 1.9))
    box = ctx.geo("screen_box", bone="deck")
    bdet = ctx.geo("screen_box_detail", bone="deck", max_lod=1)
    rot = (-deck_tilt, 0.0, 0.0)
    for side in (-1, 1):
        box.box((0.04, L + 0.1, 0.62), matrix=trs((side * (W / 2 + 0.02), 0.0, 1.62), rot), mat=BOX, bevel=0.01)
        for k in range(4):
            bdet.box((0.05, 0.06, 0.6), matrix=trs((side * (W / 2 + 0.05), -L / 2 + 0.5 + 0.7 * k, 1.62), rot), mat=BOX, bevel=0.006)
        kit.bolt_grid(bdet, (side * (W / 2 + 0.045), 0.0, 1.62), (0, 1, 0), (0, 0, 1), 8, 2, 0.35, 0.4, (side, 0, 0))
    for dz, mesh_mat in ((0.12, "metal:galvanized"), (-0.18, "metal:galvanized")):
        box.box((W, L, 0.03), matrix=trs((0.0, 0.0, 1.62 + dz), rot), mat=mesh_mat, bevel=0.004)
        for k in range(11):                                   # screen wires
            bdet.box((0.012, L - 0.1, 0.012), matrix=trs((-W / 2 + 0.07 + (W - 0.14) * k / 10, 0.0, 1.62 + dz + 0.02), rot),
                     mat=kit.STEEL)
    box.box((W + 0.08, 0.06, 0.6), matrix=trs((0.0, L / 2 * math.cos(math.radians(deck_tilt)),
                                                  1.62 + L / 2 * math.sin(math.radians(deck_tilt))), rot), mat=BOX, bevel=0.01)
    # Exciter bridge on top.
    ex_c = Vector((0.0, 0.3, 2.25))
    kit.beam(box, (-W / 2 - 0.02, ex_c.y, ex_c.z - 0.3), (W / 2 + 0.02, ex_c.y, ex_c.z - 0.3), 0.16, 0.2, BOX, profile="I")
    box.box((0.7, 0.45, 0.4), matrix=trs(ex_c), mat=kit.DARK, bevel=0.03)
    ctx.bone("exciter", tuple(ex_c + Vector((0.45, 0.0, 0.0))), tuple(ex_c + Vector((0.75, 0.0, 0.0))), parent="deck",
             z_axis=(0, 0, 1))
    exc = ctx.geo("exciter", bone="exciter")
    for x in (0.45, -0.45):
        c = ex_c + Vector((x, 0.0, 0.0))
        exc.cylinder(0.2, 0.1, segments=20, matrix=trs(c, (0, 90, 0)), mat=kit.DARK, bevel=0.01)
        exc.box((0.11, 0.18, 0.14), matrix=trs(c + Vector((0.0, 0.0, 0.1))), mat="paint:signal_red", bevel=0.01)   # weight
    exc.cylinder(0.04, 1.0, segments=10, matrix=trs(ex_c, (0, 90, 0)), mat=kit.STEEL)
    kit.motor(frame, (W / 2 + 0.55, ex_c.y, 1.05), (0, 0, 1), 0.18, 0.45, mat=FRAME, shaft=False)
    kit.beam(frame, (W / 2 + 0.55, ex_c.y, 0.0), (W / 2 + 0.55, ex_c.y, 0.8), 0.14, 0.14, FRAME)
    # Output chutes (coarse over the lip, mid-size from the lower deck) and fines pan.
    lip = Vector((0.0, -L / 2 - 0.1, 1.62 - L / 2 * math.sin(math.radians(deck_tilt))))
    kit.chute(frame, lip + Vector((0.0, 0.0, 0.05)), lip + Vector((0.0, -0.7, -0.6)), 1.2, depth=0.14, mat=kit.DARK)
    kit.chute(frame, lip + Vector((0.0, 0.1, -0.3)), lip + Vector((0.9, 0.2, -0.9)), 0.6, depth=0.12, mat=kit.DARK)
    frame.box((W + 0.2, L - 0.4, 0.1), matrix=trs((0.0, 0.1, 0.55), (-deck_tilt * 0.5, 0.0, 0.0)), mat=kit.DARK, bevel=0.01)
    kit.hopper(frame, (0.0, L / 2 - 0.15), (1.3, 0.8), (1.0, 0.4), 2.75, 2.25, wall=0.03, mat="paint_worn:industrial_yellow",
               rim=0.04, rim_mat=kit.HAZARD)
    for x in (-0.55, 0.55):
        kit.beam(frame, (x, L / 2 + 0.2, heights[posts[2]] - 0.2), (x, L / 2 - 0.15, 2.3), 0.08, 0.08, FRAME)
    kit.warning_sign(det, (W / 2 + 0.12, -L / 2 + 0.3, 0.8), facing=(1, 0, 0), size=0.22)
    # Stations.
    common.operate_facing(ctx, frame, (-W / 2 - 1.1, -0.4, 0.0), (1.0, 0.0, 0.0))
    mb = Vector((W / 2 + 0.55, ex_c.y - 0.26, 0.62))
    frame.box((0.26, 0.12, 0.3), matrix=trs(mb), mat=kit.DARK, bevel=0.008)
    common.repair_at(ctx, det, mb + Vector((0.0, -0.06, 0.0)), (0.0, -1.0, 0.0))
    ctx.socket("input", (0.0, L / 2 - 0.15, 2.75))
    ctx.socket("output_coarse", tuple(lip + Vector((0.0, -0.7, -0.6))))
    ctx.socket("output_fines", tuple(lip + Vector((0.9, 0.2, -0.9))))
    ctx.col_box((0.0, 0.0, 0.85), (W + 0.4, L, 1.7))
    ctx.col_box((0.0, 0.0, 1.8), (W + 0.2, L + 0.2, 0.9), rot=(-deck_tilt, 0, 0))
    ctx.col_box((0.0, L / 2 - 0.15, 2.5), (1.3, 0.8, 0.5))

    throw = Vector((0.0, -math.cos(math.radians(45)), math.sin(math.radians(45))))

    def work(t):
        T, cycles = 1.0, 8
        s = 0.006 * math.sin(2 * math.pi * cycles * t / T)
        return {"deck": (throw * s, None), "exciter": (None, loop_spin((1, 0, 0), cycles, t, T))}

    ctx.clip("Idle", 1.0, True, lambda t: {}, "Stopped")
    ctx.clip("Work", 1.0, True, work, "Screening: 8 Hz linear stroke along the 45 degree throw line")
    ctx.metadata["interaction"] = {"operate": "socket_operate", "repair": "socket_repair", "input": "socket_input",
                                   "output": "socket_output_coarse", "output_fines": "socket_output_fines"}
