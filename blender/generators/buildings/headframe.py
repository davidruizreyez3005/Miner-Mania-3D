"""Steel headframe over a vertical shaft, with its winder house.

Construction: concrete collar with the shaft opening, four-legged braced
tower with inclined back legs (they take the rope pull toward the winder),
head deck carrying the sheave wheel, cage running in shaft guides up to a
landing, and the winder house the rope runs to. Bones:

* ``sheave``  rope sheave, spins about +X (rope speed / radius)
* ``cage``    man/material cage, travels along +Z in the guides
* ``rope``    hoist rope from the sheave to the cage; a leaf bone that
              scales along its length so the rope always meets the cage

Clips: ``Idle``, ``Work`` (cage rises to the landing, holds, returns; the
sheave turns exactly as the rope moves). Origin: collar base, shaft centre;
the landing faces -Y.
"""

import math

from mathutils import Quaternion, Vector

from utilities.meshkit import trs

from .. import kit
from . import common as bc

TOWER = "paint_worn:signal_red"
COLLAR_H = 0.6
SHEAVE_R = 1.1
SHEAVE_Z = 13.4
LANDING_Z = 6.5
CAGE_H = 2.5


def build(ctx):
    g = ctx.geo("tower")
    det = ctx.geo("tower_detail", max_lod=1)
    glass = ctx.geo("glass")
    # Collar with the shaft opening and a dark pit.
    ox, oy = 1.0, 1.2
    for c, sz in (((0.0, -1.95), (5.0, 1.5)), ((0.0, 1.95), (5.0, 1.5)), ((-1.75, 0.0), (1.5, 2.4)), ((1.75, 0.0), (1.5, 2.4))):
        g.box((sz[0], sz[1], COLLAR_H), matrix=trs((c[0], c[1], COLLAR_H / 2)), mat=bc.SLAB, bevel=0.02)
    g.box((2 * ox, 2 * oy, 0.02), matrix=trs((0.0, 0.0, 0.01)), mat="coal")
    for s in (-1, 1):
        g.box((0.02, 2 * oy, COLLAR_H - 0.02), matrix=trs((s * (ox - 0.01), 0.0, COLLAR_H / 2 + 0.01)), mat="concrete:concrete_dark")
        g.box((2 * ox, 0.02, COLLAR_H - 0.02), matrix=trs((0.0, s * (oy - 0.01), COLLAR_H / 2 + 0.01)), mat="concrete:concrete_dark")
    for k in range(3):                                                  # steps up to the collar
        g.box((1.4, 0.3, COLLAR_H * (k + 1) / 4), matrix=trs((-1.6, -2.85 - 0.3 * (2 - k), COLLAR_H * (k + 1) / 8)), mat=bc.SLAB,
              bevel=0.01)
    # Shaft guides.
    for s in (-1, 1):
        kit.beam(g, (s * 0.95, 0.0, COLLAR_H), (s * 0.95, 0.0, LANDING_Z + CAGE_H + 0.6), 0.12, 0.16, "wood:wood_dark")
    # Tower legs, ties and bracing.
    base = [Vector((sx * 2.1, sy * 2.3, COLLAR_H)) for sx, sy in ((-1, -1), (1, -1), (1, 1), (-1, 1))]
    top = [Vector((sx * 1.3, sy * 1.5, 12.0)) for sx, sy in ((-1, -1), (1, -1), (1, 1), (-1, 1))]
    for a, b in zip(base, top):
        kit.beam(g, a, b, 0.26, 0.26, TOWER, profile="I", up=(0, 0, 1))
        det.box((0.5, 0.5, 0.04), matrix=trs(a + Vector((0.0, 0.0, 0.02))), mat=kit.DARK, bevel=0.005)
    levels = [COLLAR_H, 3.5, LANDING_Z - 0.1, 9.5, 11.9]               # ties sit just under the decks
    ring = lambda z: [a.lerp(b, (z - COLLAR_H) / (12.0 - COLLAR_H)) for a, b in zip(base, top)]
    for z in levels[1:]:
        r = ring(z)
        for i in range(4):
            kit.beam(g, r[i], r[(i + 1) % 4], 0.14, 0.14, TOWER)
    for z0, z1 in zip(levels, levels[1:]):
        r0, r1 = ring(z0), ring(z1)
        for i in range(4):
            j = (i + 1) % 4
            if i == 0 and z0 >= LANDING_Z - 0.2:
                continue                                                # front face above the landing stays open (ladder)
            kit.beam(det, r0[i], r1[j], 0.07, 0.07, TOWER, profile="tube")
            kit.beam(det, r0[j], r1[i], 0.07, 0.07, TOWER, profile="tube")
    # Back legs (inclined toward the winder).
    back_feet = [Vector((sx * 1.6, 8.0, 0.0)) for sx in (-1, 1)]
    back_heads = [Vector((sx * 1.3, 1.5, 11.6)) for sx in (-1, 1)]
    for a, b in zip(back_feet, back_heads):
        kit.beam(g, a, b, 0.3, 0.3, TOWER, profile="I", up=(1, 0, 0))
        g.box((0.8, 0.8, 0.5), matrix=trs(a + Vector((0.0, 0.0, 0.25))), mat=bc.SLAB, bevel=0.02)
    for t in (0.35, 0.7):
        kit.beam(g, back_feet[0].lerp(back_heads[0], t), back_feet[1].lerp(back_heads[1], t), 0.14, 0.14, TOWER)
    # Head deck with a slot for the rope, sheave pedestals, railing.
    for s in (-1, 1):
        g.box((1.2, 3.2, 0.1), matrix=trs((s * 0.95, 0.0, 12.05)), mat="metal:galvanized", bevel=0.01)
        g.box((0.24, 0.5, SHEAVE_Z - 12.1), matrix=trs((s * 0.42, SHEAVE_R, (SHEAVE_Z + 12.1) / 2)), mat=kit.DARK, bevel=0.02)
    kit.railing(det, [(0.9, -1.6, 12.1), (-1.55, -1.6, 12.1), (-1.55, 1.6, 12.1), (1.55, 1.6, 12.1), (1.55, -1.6, 12.1)],
                height=1.0, mat="paint_worn:industrial_yellow", post_spacing=1.6, toe=False)   # gap at the ladder head
    kit.beacon(det, (1.4, -1.5, 13.1))
    g.cylinder(0.08, 1.1, segments=12, matrix=trs((0.0, SHEAVE_R, SHEAVE_Z), (0, 90, 0)), mat=kit.STEEL)       # axle
    # Sheave (bone).
    sc = Vector((0.0, SHEAVE_R, SHEAVE_Z))
    ctx.bone("sheave", tuple(sc), tuple(sc + Vector((0.4, 0.0, 0.0))))
    sh = ctx.geo("sheave", bone="sheave")
    prof = [(SHEAVE_R - 0.12, -0.1), (SHEAVE_R + 0.04, -0.12), (SHEAVE_R + 0.04, -0.06), (SHEAVE_R - 0.02, -0.02),
            (SHEAVE_R - 0.02, 0.02), (SHEAVE_R + 0.04, 0.06), (SHEAVE_R + 0.04, 0.12), (SHEAVE_R - 0.12, 0.1)]
    sh.lathe(prof, segments=40, matrix=trs(sc, (0, 90, 0)), mat=kit.DARK, caps=False, closed_loop=True)
    sh.cylinder(0.22, 0.3, segments=16, matrix=trs(sc, (0, 90, 0)), mat=kit.DARK, bevel=0.02)
    for k in range(8):                                                  # spokes
        a = 2 * math.pi * k / 8
        d = Vector((0.0, math.cos(a), math.sin(a)))
        kit.beam(sh, sc + d * 0.2, sc + d * (SHEAVE_R - 0.1), 0.07, 0.07, kit.DARK, profile="tube")
    # Cage (bone) in the guides.
    c0 = Vector((0.0, 0.0, COLLAR_H))
    ctx.bone("cage", tuple(c0), tuple(c0 + Vector((0.0, 0.0, 0.5))))
    cg = ctx.geo("cage", bone="cage")
    cage_mat = "paint_worn:industrial_yellow"
    cg.box((1.6, 1.9, 0.08), matrix=trs(c0 + Vector((0.0, 0.0, 0.04))), mat=kit.DARK, bevel=0.01)
    cg.box((1.6, 1.9, 0.06), matrix=trs(c0 + Vector((0.0, 0.0, CAGE_H))), mat=cage_mat, bevel=0.01)
    for sx in (-0.78, 0.78):
        for sy in (-0.93, 0.93):
            kit.beam(cg, c0 + Vector((sx, sy, 0.05)), c0 + Vector((sx, sy, CAGE_H)), 0.06, 0.06, cage_mat)
        for k in range(1, 8):                                           # side bars
            y = -0.93 + 1.86 * k / 8
            kit.beam(cg, c0 + Vector((sx, y, 0.08)), c0 + Vector((sx, y, CAGE_H - 0.05)), 0.02, 0.02, "metal:galvanized",
                     profile="tube")
        cg.box((0.1, 0.3, 0.2), matrix=trs(c0 + Vector((sx * 1.1, 0.0, 0.3))), mat=kit.DARK, bevel=0.01)            # guide shoes
        cg.box((0.1, 0.3, 0.2), matrix=trs(c0 + Vector((sx * 1.1, 0.0, CAGE_H - 0.3))), mat=kit.DARK, bevel=0.01)
        kit.beam(cg, c0 + Vector((sx, 0.0, 0.3)), c0 + Vector((sx * 1.1, 0.0, 0.3)), 0.06, 0.06, kit.DARK)
        kit.beam(cg, c0 + Vector((sx, 0.0, CAGE_H - 0.3)), c0 + Vector((sx * 1.1, 0.0, CAGE_H - 0.3)), 0.06, 0.06, kit.DARK)
    cg.box((1.5, 0.04, CAGE_H - 0.1), matrix=trs(c0 + Vector((0.0, 0.92, CAGE_H / 2))), mat=cage_mat, bevel=0.005)
    for k in range(5):                                                  # front gate bars
        x = -0.6 + 0.3 * k
        kit.beam(cg, c0 + Vector((x, -0.93, 0.1)), c0 + Vector((x, -0.93, 1.9)), 0.025, 0.025, "metal:galvanized", profile="tube")
    kit.beam(cg, c0 + Vector((-0.75, -0.93, 1.0)), c0 + Vector((0.75, -0.93, 1.0)), 0.04, 0.04, cage_mat, profile="tube")
    cross = c0 + Vector((0.0, 0.0, CAGE_H + 0.03))
    kit.beam(cg, cross + Vector((-0.8, 0.0, 0.08)), cross + Vector((0.8, 0.0, 0.08)), 0.14, 0.16, kit.DARK)
    cg.box((0.16, 0.12, 0.2), matrix=trs(cross + Vector((0.0, 0.0, 0.26))), mat=kit.DARK, bevel=0.01)
    rope_bottom = cross + Vector((0.0, 0.0, 0.36))
    # Rope (bone): from the sheave's front tangent down to the cage crosshead.
    rope_top = Vector((0.0, 0.0, SHEAVE_Z))
    ctx.bone("rope", tuple(rope_top), tuple(rope_top + Vector((0.0, 0.0, -0.5))))
    rp = ctx.geo("rope", bone="rope")
    rope_len = (rope_top - rope_bottom).length
    rp.cylinder(0.025, rope_len, segments=8, matrix=trs((rope_top + rope_bottom) / 2), mat=kit.STEEL)
    # Winder house and the rope run to it.
    hy0, hy1, hw, hh = 12.5, 16.5, 5.0, 4.0
    Fh = bc.clad_wall(g, (0.0, hy0, 0.0), (0.0, -1.0, 0.0), hw, hh, openings=[(0.6, 1.6, 0.0, 2.1), (3.0, 4.3, 1.4, 2.4)])
    bc.wall_trims(det, Fh, hw, hh)
    bc.opening_trim(g, Fh, 0.6, 1.6, 0.0, 2.1, sill=False)
    bc.window(g, glass, Fh, 3.0, 4.3, 1.4, 2.4)
    g.box((0.9, 0.05, 2.05), matrix=trs(Fh @ Vector((1.1, 0.03, 1.03))), mat="paint_worn:machine_green", bevel=0.008)
    for s in (-1, 1):
        F = bc.clad_wall(g, (s * hw / 2, (hy0 + hy1) / 2, 0.0), (s, 0.0, 0.0), hy1 - hy0, hh)
        bc.wall_trims(det, F, hy1 - hy0, hh)
    Fb = bc.clad_wall(g, (0.0, hy1, 0.0), (0.0, 1.0, 0.0), hw, hh)
    bc.wall_trims(det, Fb, hw, hh)
    bc.gable_infill(g, Fh, hw, hh, 1.2)
    bc.gable_infill(g, Fb, hw, hh, 1.2)
    # House ridge runs along Y (gables front/back).
    bc.gable_roof(g, 0.0, (hy0 + hy1) / 2, hw + 0.1, hy1 - hy0 + 0.1, hh, 1.2, overhang=0.3)
    kit.pipe_run(det, [(1.6, hy1 - 0.8, hh + 0.4), (1.6, hy1 - 0.8, hh + 2.6)], 0.14, kit.DARK, flanges=False)
    rope_end = Vector((0.0, hy0, 3.0))
    v = Vector((0.0, rope_end.y - sc.y, rope_end.z - sc.z))
    dist = v.length
    ang = math.atan2(v.z, v.y) + math.acos(SHEAVE_R / dist)             # upper tangent point
    tangent = sc + Vector((0.0, math.cos(ang), math.sin(ang))) * SHEAVE_R
    kit.beam(g, tangent, rope_end, 0.05, 0.05, kit.STEEL, profile="tube")
    g.box((0.4, 0.1, 0.3), matrix=trs(rope_end + Vector((0.0, -0.05, 0.0))), mat=kit.DARK, bevel=0.01)
    # Landing platform and ladders.
    ly0, ly1 = -2.25, -1.0
    kit.deck(g, (0.0, (ly0 + ly1) / 2, LANDING_Z), (3.4, ly1 - ly0))
    yel = "paint_worn:industrial_yellow"
    kit.railing(det, [(1.7, ly1, LANDING_Z), (1.7, ly0, LANDING_Z), (-0.9, ly0, LANDING_Z)], height=1.1, mat=yel)
    kit.railing(det, [(-1.5, ly0, LANDING_Z), (-1.7, ly0, LANDING_Z), (-1.7, ly1, LANDING_Z)], height=1.1, mat=yel)
    # Collar -> landing outside the front face; landing -> head deck from the deck.
    kit.ladder(det, (-1.2, ly0 - 0.2, COLLAR_H), LANDING_Z - COLLAR_H, width=0.42, mat=yel, facing=(0, -1, 0), cage=True)
    kit.ladder(det, (1.2, -1.85, LANDING_Z), 12.1 - LANDING_Z, width=0.42, mat=yel, facing=(0, -1, 0), cage=True)
    kit.lamp(det, (0.0, ly0 + 0.1, LANDING_Z + 2.4), (0.0, 0.3, -0.9), r=0.1, emit="emit:emissive_warm")
    # Sockets.
    ctx.socket("cage", tuple(c0), bone="cage")
    ctx.socket("cage_entry", (0.0, -1.6, COLLAR_H), (0.0, 0.0, 180.0))
    ctx.socket("landing", (0.0, ly0 + 0.4, LANDING_Z), (0.0, 0.0, 180.0))
    ctx.socket("winder_door", tuple(Fh @ Vector((1.1, 1.2, 0.0))), (0.0, 0.0, 180.0))
    # Collision.
    for c, sz in (((0.0, -1.95), (5.0, 1.5)), ((0.0, 1.95), (5.0, 1.5)), ((-1.75, 0.0), (1.5, 2.4)), ((1.75, 0.0), (1.5, 2.4))):
        ctx.col_box((c[0], c[1], COLLAR_H / 2), (sz[0], sz[1], COLLAR_H))
    for a, b in list(zip(base, top)) + list(zip(back_feet, back_heads)):
        ctx.col_hull([tuple(p + Vector((dx, dy, 0.0))) for p in (a, b) for dx in (-0.15, 0.15) for dy in (-0.15, 0.15)])
    ctx.col_box((0.0, 0.0, 12.05), (3.1, 3.2, 0.1))
    ctx.col_box((0.0, (ly0 + ly1) / 2, LANDING_Z - 0.03), (3.4, ly1 - ly0, 0.06))
    ctx.col_cylinder(tuple(sc), SHEAVE_R + 0.05, 0.3, rot=(0, 90, 0))
    ctx.col_box((0.0, (hy0 + hy1) / 2, hh / 2), (hw, hy1 - hy0, hh))
    ctx.col_hull([(x, y, z) for y in (hy0 - 0.3, hy1 + 0.3) for x, z in ((-hw / 2 - 0.3, hh), (hw / 2 + 0.3, hh), (0.0, hh + 1.25))])

    travel = LANDING_Z - COLLAR_H

    def work(t):
        T = 12.0
        u = t / T

        def ramp(a, b):
            k = min(1.0, max(0.0, (u - a) / (b - a)))
            return 0.5 - 0.5 * math.cos(math.pi * k)
        lift = travel * (ramp(0.08, 0.42) - ramp(0.58, 0.92))
        return {"cage": (Vector((0.0, 0.0, lift)), None),
                "sheave": (None, Quaternion((1.0, 0.0, 0.0), -lift / SHEAVE_R)),
                "rope": (None, None, (1.0, (rope_len - lift) / rope_len, 1.0))}

    ctx.clip("Idle", 2.0, True, lambda t: {}, "Cage at the collar")
    ctx.clip("Work", 12.0, True, work, "Cage winds up to the landing, holds, lowers; sheave turns with the rope")
    ctx.metadata["hoist"] = {"travel_m": round(travel, 3), "sheave_radius_m": SHEAVE_R, "landing_z_m": LANDING_Z}
    ctx.metadata["interaction"] = {"cage": "socket_cage (bone cage)", "cage_entry": "socket_cage_entry",
                                   "landing": "socket_landing", "winder": "socket_winder_door"}
