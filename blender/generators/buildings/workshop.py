"""Open-front maintenance workshop (8 x 6 m) with a travelling chain hoist.

Construction: slab with a painted service bay, steel columns, clad back and
side walls, mono-pitch roof falling to the back, a workbench with vise and
tool board at the contract bench height, gas bottles, and an I-beam runway
over the bay carrying a hoist trolley. Bones:

* ``trolley``  hoist trolley, travels along the runway (+X)
* ``hook``     chain block hook (child of trolley), raises/lowers (+Z)

Clips: ``Idle``, ``Hoist`` (trolley travels out, hook lowers and lifts,
trolley returns). Origin: slab base centre; open front -Y.
"""

import math

from mathutils import Matrix, Vector

from core import config
from utilities.meshkit import trs

from .. import kit
from ..machinery import common as mc
from . import common as bc

SLAB_H = 0.15


def build(ctx):
    W, D = 8.0, 6.0
    z_front, z_back = 4.2, 3.4
    g = ctx.geo("shell")
    det = ctx.geo("shell_detail", max_lod=1)
    bc.slab(g, 0.0, 0.0, W + 0.4, D + 0.4, SLAB_H)
    bay = Vector((2.0, -0.4, SLAB_H))
    det.box((3.4, 4.6, 0.005), matrix=trs(bay + Vector((0.0, 0.0, 0.0025))), mat="paint_worn:industrial_yellow")   # bay marking
    det.box((3.2, 4.4, 0.006), matrix=trs(bay + Vector((0.0, 0.0, 0.003))), mat=bc.SLAB)
    cols = [(-W / 2 + 0.15, -D / 2 + 0.15), (W / 2 - 0.15, -D / 2 + 0.15), (0.0, -D / 2 + 0.15),
            (-W / 2 + 0.15, D / 2 - 0.15), (W / 2 - 0.15, D / 2 - 0.15)]
    for x, y in cols:
        top = z_front + (z_back - z_front) * (y + D / 2) / D
        kit.beam(g, (x, y, SLAB_H), (x, y, top), 0.2, 0.2, bc.FRAME, profile="I", up=(0, 1, 0))
    kit.beam(g, (-W / 2, -D / 2 + 0.15, z_front - 0.12), (W / 2, -D / 2 + 0.15, z_front - 0.12), 0.2, 0.3, bc.FRAME, profile="I")
    # Walls: back and sides (sides follow the roof slope with a stepped top).
    Fb = bc.clad_wall(g, (0.0, D / 2, 0.0), (0.0, 1.0, 0.0), W, z_back - SLAB_H, z0=SLAB_H)
    bc.wall_trims(det, Fb, W, z_back - SLAB_H)
    for s in (-1, 1):
        F = bc.clad_wall(g, (s * W / 2, 0.0, 0.0), (s, 0.0, 0.0), D, z_back - SLAB_H, z0=SLAB_H)
        bc.wall_trims(det, F, D, z_back - SLAB_H)
        # Sloped infill between the wall top and the roof.
        y0, y1 = -D / 2, D / 2
        pts = [(y0, z_back), (y1, z_back), (y0, z_front)]
        verts = [(s * W / 2, y, z) for y, z in pts] + [(s * (W / 2 - 0.04), y, z) for y, z in pts]
        g.mesh(verts, [(0, 1, 2), (5, 4, 3), (0, 3, 4, 1), (1, 4, 5, 2), (2, 5, 3, 0)], mat=bc.CLAD, recalc=True)
    _roof(g, W, D, z_front, z_back)
    # Workbench along the left wall at the contract bench height (load_surface z).
    ip = config.animation_spec()["interaction_points"]
    bench_h = ip["load_surface"][2]
    bx, by = -W / 2 + 0.55, 0.6
    g.box((0.7, 2.4, 0.06), matrix=trs((bx, by, SLAB_H + bench_h - 0.03)), mat="wood:wood_dark", bevel=0.008)
    kit.frame_box(g, (bx - 0.32, by - 1.15, SLAB_H), (bx + 0.32, by + 1.15, SLAB_H + bench_h - 0.06), bar=0.05, mat=bc.TRIM,
                  top=True)
    g.box((0.62, 2.3, 0.03), matrix=trs((bx, by, SLAB_H + 0.25)), mat="wood:wood_dark", bevel=0.004)
    det.box((0.2, 0.14, 0.12), matrix=trs((bx + 0.2, by - 0.9, SLAB_H + bench_h + 0.06)), mat="paint_worn:machine_blue", bevel=0.01)
    det.cylinder(0.012, 0.3, segments=8, matrix=trs((bx + 0.33, by - 0.9, SLAB_H + bench_h + 0.08), (0, 90, 0)), mat=kit.STEEL)
    g.box((0.04, 2.4, 1.0), matrix=trs((-W / 2 + 0.06, by, SLAB_H + bench_h + 0.75)), mat="wood:wood_light", bevel=0.005)
    for k in range(7):                                                  # hanging tools on the board
        z = SLAB_H + bench_h + 0.45 + 0.25 * (k % 3)
        y = by - 1.0 + 0.32 * k
        det.box((0.03, 0.05, 0.28), matrix=trs((-W / 2 + 0.1, y, z)), mat=kit.DARK if k % 2 else "paint:signal_red", bevel=0.004)
    # Gas bottles chained to the right wall.
    for k, col in enumerate(("paint:machine_blue", "paint:signal_red")):
        p = Vector((W / 2 - 0.3, D / 2 - 1.0 - 0.35 * k, SLAB_H))
        g.lathe([(0.0, 0.0), (0.12, 0.0), (0.12, 1.2), (0.06, 1.35), (0.0, 1.35)], segments=14,
                matrix=trs(p), mat=col)
        det.cylinder(0.03, 0.1, segments=8, matrix=trs(p + Vector((0.0, 0.0, 1.4))), mat="brass")
    # Hoist runway and trolley.
    rz = z_front - 0.45
    kit.beam(g, (-0.4, -0.4, rz), (W / 2 - 0.2, -0.4, rz), 0.14, 0.24, kit.DARK, profile="I", up=(0, 1, 0))
    kit.beam(g, (W / 2 - 0.2, -0.4, rz + 0.12), (W / 2 - 0.2, -0.4, z_front - 0.1), 0.1, 0.1, kit.DARK)
    kit.beam(g, (-0.4, -0.4, rz + 0.12), (-0.4, -0.4, z_front - 0.2), 0.1, 0.1, kit.DARK)
    t0 = Vector((0.4, -0.4, rz - 0.12))
    ctx.bone("trolley", tuple(t0), tuple(t0 + Vector((0.3, 0.0, 0.0))))
    tr = ctx.geo("trolley", bone="trolley")
    tr.box((0.3, 0.28, 0.12), matrix=trs(t0 + Vector((0.0, 0.0, -0.02))), mat="paint_worn:industrial_yellow", bevel=0.01)
    for sx in (-0.1, 0.1):
        for sy in (-0.1, 0.1):
            tr.cylinder(0.04, 0.03, segments=10, matrix=trs(t0 + Vector((sx, sy, 0.1)), (90, 0, 0)), mat=kit.DARK)
    tr.box((0.22, 0.2, 0.3), matrix=trs(t0 + Vector((0.0, 0.0, -0.25))), mat="paint_worn:industrial_yellow", bevel=0.02)
    h0 = t0 + Vector((0.0, 0.0, -1.6))
    ctx.bone("hook", tuple(h0), tuple(h0 + Vector((0.0, 0.0, 0.3))), parent="trolley")
    hk = ctx.geo("hook", bone="hook")
    hk.box((0.1, 0.06, 0.12), matrix=trs(h0 + Vector((0.0, 0.0, 0.08))), mat=kit.DARK, bevel=0.01)
    hk.torus(0.05, 0.012, seg_major=12, seg_minor=5, matrix=trs(h0 + Vector((0.0, 0.0, -0.03)), (90, 0, 0)), mat=kit.STEEL)
    hk.cylinder(0.008, 1.2, segments=6, matrix=trs(h0 + Vector((0.0, 0.0, 0.74))), mat=kit.STEEL)    # chain drop
    # Stations and sockets.
    reach = -ip["load_surface"][1]                    # hands land 0.15 m in from the bench edge
    ctx.socket("workbench", (bx + 0.35 + reach - 0.15, by, SLAB_H), (0.0, 0.0, -90.0))
    ctx.socket("repair_bay", tuple(bay), (0.0, 0.0, 0.0))
    ctx.socket("entrance", (0.0, -D / 2 - 1.0, 0.0), (0.0, 0.0, 180.0))
    kit.lamp(det, (0.0, 0.5, z_front - 0.95), (0.0, 0.0, -1.0), r=0.14, emit="emit:emissive_cool")
    kit.beam(det, (0.0, 0.5, z_front - 0.8), (0.0, 0.5, z_front - 0.5), 0.02, 0.02, kit.STEEL, profile="tube")
    ctx.col_box((0.0, 0.0, SLAB_H / 2), (W + 0.4, D + 0.4, SLAB_H))
    ctx.col_box((0.0, D / 2, (z_back + SLAB_H) / 2), (W, 0.2, z_back - SLAB_H))
    for s in (-1, 1):
        ctx.col_box((s * W / 2, 0.0, (z_back + SLAB_H) / 2), (0.2, D, z_back - SLAB_H))
    for x, y in cols[:3]:
        ctx.col_box((x, y, (z_front + SLAB_H) / 2), (0.22, 0.22, z_front - SLAB_H))
    ctx.col_hull([(x, y, z + dz) for x in (-W / 2 - 0.3, W / 2 + 0.3) for y, z in ((-D / 2 - 0.3, z_front), (D / 2 + 0.3, z_back))
                  for dz in (0.0, 0.15)])
    ctx.col_box((bx, by, SLAB_H + bench_h / 2), (0.7, 2.4, bench_h))

    def hoist(t):
        T = 8.0
        u = t / T
        travel = 2.0

        def smooth(a, b):
            k = min(1.0, max(0.0, (u - a) / (b - a)))
            return 0.5 - 0.5 * math.cos(math.pi * k)
        x = travel * (smooth(0.0, 0.25) - smooth(0.75, 1.0))
        drop = 0.9 * (smooth(0.3, 0.45) - smooth(0.55, 0.7))
        return {"trolley": (Vector((x, 0.0, 0.0)), None), "hook": (Vector((0.0, 0.0, -drop)), None)}

    ctx.clip("Idle", 2.0, True, lambda t: {}, "Hoist parked")
    ctx.clip("Hoist", 8.0, True, hoist, "Trolley travels over the bay, hook lowers and lifts, trolley returns")
    ctx.metadata["interaction"] = {"workbench": "socket_workbench", "repair_bay": "socket_repair_bay",
                                   "entrance": "socket_entrance"}


def _roof(g, W, D, z_front, z_back):
    """Mono-pitch roof falling from the open front to the back wall."""
    over = 0.35
    run = D + 2 * over
    drop = (z_front - z_back) * run / D
    theta = math.atan2(z_front - z_back, D)
    down = Vector((0.0, math.cos(theta), -math.sin(theta)))
    normal = Vector((0.0, math.sin(theta), math.cos(theta)))
    x_axis = normal.cross(down)
    m = Matrix(((x_axis.x, normal.x, down.x, 0.0), (x_axis.y, normal.y, down.y, 0.0), (x_axis.z, normal.z, down.z, 0.0),
                (0.0, 0.0, 0.0, 1.0)))
    start = Vector((0.0, -D / 2 - over, z_front + over * math.tan(theta) + 0.02))
    start -= x_axis * (W / 2 + over)                 # sheet runs along local X from this end
    m.translation = start
    bc.corrugated_sheet(g, m, W + 2 * over, math.hypot(run, drop))
    for x in (-W / 2 - over, W / 2 + over):
        a = Vector((x, -D / 2 - over, z_front + over * math.tan(theta)))
        kit.beam(g, a, a + down * math.hypot(run, drop), 0.2, 0.04, bc.TRIM, up=(1, 0, 0))
    g.box((W + 2 * over, 0.16, 0.12), matrix=trs((0.0, D / 2 + over, z_back - over * math.tan(theta) - 0.08)), mat=bc.TRIM,
          bevel=0.01)
