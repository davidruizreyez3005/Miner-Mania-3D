"""Portable site office (6 x 2.6 m cabin) on concrete blocks.

Construction: steel base frame on blocks, clad cabin with corner posts,
three windows with security bars, a hinged door reached by steel steps with
a handrail, AC unit, roof edge trim, downpipe and a sign board. Bones:

* ``door``  hinged on its left jamb, opens outward

Clips: ``Idle``, ``Door``. Origin: ground centre; front -Y.
"""

from mathutils import Vector

from utilities.meshkit import trs

from .. import kit
from . import common as bc

BODY = "paint_worn:cream_paint"


def build(ctx):
    L, W, H = 6.0, 2.6, 2.6
    z0 = 0.45                                             # floor height on blocks
    g = ctx.geo("cabin")
    det = ctx.geo("cabin_detail", max_lod=1)
    glass = ctx.geo("glass")
    for x in (-L / 2 + 0.3, 0.0, L / 2 - 0.3):           # blocks
        for y in (-W / 2 + 0.3, W / 2 - 0.3):
            g.box((0.4, 0.4, 0.3), matrix=trs((x, y, 0.15)), mat=bc.SLAB, bevel=0.02)
    kit.frame_box(g, (-L / 2, -W / 2, 0.3), (L / 2, W / 2, z0), bar=0.15, mat=bc.TRIM, verticals=False)
    g.box((L, W, 0.05), matrix=trs((0.0, 0.0, z0 - 0.02)), mat=bc.TRIM, bevel=0.005)
    door = (L / 2 - 1.6, L / 2 - 0.7, 0.0, 2.05)
    wins = [(0.5, 1.7, 0.95, 2.0), (2.1, 3.3, 0.95, 2.0)]
    Ff = bc.clad_wall(g, (0.0, -W / 2, 0.0), (0.0, -1.0, 0.0), L, H, openings=[door] + wins, z0=z0, mat=BODY)
    Fb = bc.clad_wall(g, (0.0, W / 2, 0.0), (0.0, 1.0, 0.0), L, H, openings=[(2.4, 3.6, 0.95, 2.0)], z0=z0, mat=BODY)
    Fl = bc.clad_wall(g, (-L / 2, 0.0, 0.0), (-1.0, 0.0, 0.0), W, H, z0=z0, mat=BODY)
    Fr = bc.clad_wall(g, (L / 2, 0.0, 0.0), (1.0, 0.0, 0.0), W, H, z0=z0, mat=BODY)
    for F, n in ((Ff, L), (Fb, L), (Fl, W), (Fr, W)):
        bc.wall_trims(det, F, n, H, mat=bc.TRIM, kerb_mat=bc.TRIM)
    for F, (u0, u1, a, b) in [(Ff, w) for w in wins] + [(Fb, (2.4, 3.6, 0.95, 2.0))]:
        bc.window(g, glass, F, u0, u1, a, b, mullions=1)
        for k in range(1, 5):                                           # security bars
            u = u0 + (u1 - u0) * k / 5
            c = F @ Vector((u, 0.06, (a + b) / 2))
            det.cylinder(0.01, b - a, segments=6, matrix=trs(c), mat=kit.DARK)
    bc.opening_trim(g, Ff, *door, sill=False)
    bc.hinged_door(ctx, "door", Ff, *door, mat="paint_worn:machine_blue")
    # Roof: flat deck with a raised edge trim.
    g.box((L + 0.1, W + 0.1, 0.12), matrix=trs((0.0, 0.0, z0 + H + 0.06)), mat=bc.TRIM, bevel=0.01)
    g.box((L - 0.2, W - 0.2, 0.04), matrix=trs((0.0, 0.0, z0 + H + 0.14)), mat="metal:galvanized", bevel=0.005)
    # Steps + handrail up to the door.
    dx = (Ff @ Vector(((door[0] + door[1]) / 2, 0.0, 0.0))).x
    steps = 3
    for k in range(steps):
        zt = z0 * (k + 1) / (steps + 1) + 0.02
        y = -W / 2 - 0.9 + 0.28 * k
        g.box((1.1, 0.3, 0.04), matrix=trs((dx, y, zt)), mat="metal:galvanized", bevel=0.004)
    g.box((1.1, 0.9, 0.04), matrix=trs((dx, -W / 2 - 0.45 + 0.2, z0 - 0.02)), mat="metal:galvanized", bevel=0.004)
    for s in (-1, 1):
        x = dx + s * 0.55
        kit.beam(g, (x, -W / 2 - 1.05, 0.0), (x, -W / 2 - 0.05, z0), 0.05, 0.12, bc.TRIM, up=(1, 0, 0))
        kit.railing(det, [(x, -W / 2 - 1.0, 0.1), (x, -W / 2 - 0.1, z0)], height=0.95, mat="paint_worn:industrial_yellow",
                    post_spacing=1.2, toe=False)
    # AC unit, downpipe, sign board, lamp.
    ac = Fr @ Vector((W / 2, 0.25, 1.6))
    g.box((0.8, 0.4, 0.6), matrix=trs(ac + Vector((0.2 - 0.25, 0.0, 0.0))), mat="plastic:plastic_white", bevel=0.03)
    det.cylinder(0.2, 0.02, segments=20, matrix=trs(ac + Vector((0.165, 0.0, 0.05)), (0, 90, 0)), mat=kit.DARK)
    bc.downpipe(det, (-L / 2 + 0.1, -W / 2 - 0.12, z0 + H), bottom_z=0.1)
    g.box((1.8, 0.05, 0.45), matrix=trs((-0.6, -W / 2 - 0.07, z0 + H - 0.35)), mat="paint_clean:sign_green", bevel=0.01)
    det.box((1.5, 0.02, 0.12), matrix=trs((-0.6, -W / 2 - 0.1, z0 + H - 0.35)), mat="paint_clean:sign_white")
    kit.lamp(det, (dx, -W / 2 - 0.2, z0 + 2.35), (0.0, -0.5, -0.85), r=0.08, emit="emit:emissive_warm")
    # Sockets and collision.
    ctx.socket("door", (dx, -W / 2 - 1.5, 0.0), (0.0, 0.0, 180.0))
    ctx.socket("inside", (0.0, 0.0, z0))
    ctx.col_box((0.0, 0.0, (z0 + H + 0.12) / 2), (L, W, z0 + H + 0.12))
    ctx.col_hull([(dx + sx, y, z) for sx in (-0.55, 0.55) for y, z in ((-W / 2 - 1.05, 0.0), (-W / 2, 0.0), (-W / 2, z0))])

    def door_clip(t):
        q, _ = bc.door_swing(100.0, t, 3.0)
        return {"door": (None, q)}

    ctx.clip("Idle", 2.0, True, lambda t: {}, "Door closed")
    ctx.clip("Door", 3.0, True, door_clip, "Door opens outward, holds, closes")
    ctx.metadata["interaction"] = {"entry": "socket_door", "inside": "socket_inside"}
    ctx.metadata["doors"] = {"door": {"hinge": "left jamb", "opens": "outward"}}
