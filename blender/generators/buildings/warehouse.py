"""Steel portal-frame warehouse with corrugated cladding.

Construction: concrete slab, five portal frames (I-section columns and
rafters), corrugated walls with translucent window strips, gable roof with
gutters and downpipes. Front (-Y) gable: a 4 x 4.2 m roll-up door and a
personnel door. Pallet racking inside. Bones:

* ``roller_door``  roll-up curtain; scales along its length into the drum
* ``door``         personnel door, hinged on its left jamb (opens outward)

Clips: ``Idle``, ``Roller_Door`` (open, hold, close), ``Door``.
Origin: slab base centre; front -Y.
"""

from mathutils import Matrix, Vector

from utilities.meshkit import trs

from .. import kit
from . import common as bc

SLAB_H = 0.15


def build(ctx):
    W, D = ctx.param("width", 10.0), ctx.param("depth", 14.0)
    eave, rise = ctx.param("eave", 5.0), ctx.param("rise", 1.6)
    wall_h = eave - SLAB_H
    g = ctx.geo("shell")
    det = ctx.geo("shell_detail", max_lod=1)
    glass = ctx.geo("glass")
    bc.slab(g, 0.0, 0.0, W + 0.6, D + 0.6, SLAB_H)
    # Portal frames.
    frames_y = [-D / 2 + D * k / 4 for k in range(5)]
    for y in frames_y:
        for s in (-1, 1):
            # up=X puts each member's depth in the frame plane (strong axis).
            kit.beam(g, (s * (W / 2 - 0.15), y, SLAB_H), (s * (W / 2 - 0.15), y, eave), 0.22, 0.3, bc.FRAME, profile="I",
                     up=(1, 0, 0))
            kit.beam(g, (s * (W / 2 - 0.15), y, eave - 0.1), (0.0, y, eave + rise - 0.15), 0.18, 0.3, bc.FRAME, profile="I",
                     up=(1, 0, 0))
            det.box((0.4, 0.4, 0.03), matrix=trs((s * (W / 2 - 0.15), y, SLAB_H + 0.015)), mat=kit.DARK, bevel=0.004)
    for s in (-1, 1):                                                   # eave purlins
        kit.beam(g, (s * (W / 2 - 0.15), -D / 2, eave - 0.05), (s * (W / 2 - 0.15), D / 2, eave - 0.05), 0.14, 0.14, bc.FRAME)
    # Walls.
    win = [(D / 2 - 5.0 + k * 4.0, D / 2 - 3.0 + k * 4.0, 3.4 - SLAB_H, 4.3 - SLAB_H) for k in range(3)]
    for s in (-1, 1):
        F = bc.clad_wall(g, (s * W / 2, 0.0, 0.0), (s, 0.0, 0.0), D, wall_h, openings=win, z0=SLAB_H)
        bc.wall_trims(det, F, D, wall_h)
        for u0, u1, z0, z1 in win:
            bc.window(g, glass, F, u0, u1, z0, z1, mullions=2)
    Fb = bc.clad_wall(g, (0.0, D / 2, 0.0), (0.0, 1.0, 0.0), W, wall_h, z0=SLAB_H)
    bc.wall_trims(det, Fb, W, wall_h)
    bc.gable_infill(g, Fb, W, wall_h, rise)
    roller = (W / 2 - 2.0, W / 2 + 2.0, 0.0, 4.2)
    pers = (W / 2 + 3.0, W / 2 + 4.0, 0.0, 2.1)
    Ff = bc.clad_wall(g, (0.0, -D / 2, 0.0), (0.0, -1.0, 0.0), W, wall_h, openings=[roller, pers], z0=SLAB_H)
    bc.wall_trims(det, Ff, W, wall_h)
    bc.gable_infill(g, Ff, W, wall_h, rise)
    bc.opening_trim(g, Ff, *roller, sill=False)
    bc.opening_trim(g, Ff, *pers, sill=False)
    bc.rollup_door(ctx, "roller_door", Ff, *roller)
    drum = Ff @ Vector(((roller[0] + roller[1]) / 2, 0.22, roller[3] + 0.28))
    g.box((4.3, 0.36, 0.5), matrix=trs(drum), mat=bc.TRIM, bevel=0.03)
    bc.hinged_door(ctx, "door", Ff, *pers)
    # Roof, gutters, downpipes.
    bc.gable_roof(g, 0.0, 0.0, W + 0.1, D + 0.1, eave, rise)
    for s in (-1, 1):
        gx = s * (W / 2 + 0.45)
        g.box((0.16, D + 0.8, 0.12), matrix=trs((gx, 0.0, eave - 0.08)), mat=bc.TRIM, bevel=0.01)
        for y in (-D / 2 + 0.2, D / 2 - 0.2):
            kit.pipe_run(det, [(gx, y, eave - 0.12), (s * (W / 2 + 0.12), y, eave - 0.5), (s * (W / 2 + 0.12), y, 0.12)],
                         0.045, bc.TRIM, flanges=False)
    # Door furniture: lamps, sign, bollards, entrance ramp.
    for x in (-2.4, 2.4):
        kit.lamp(det, (x, -D / 2 - 0.25, 4.9), (0.0, -0.6, -0.8), r=0.1, emit="emit:emissive_warm")
    g.box((3.2, 0.06, 0.7), matrix=trs((0.0, -D / 2 - 0.08, eave + 0.55)), mat="paint_clean:sign_yellow", bevel=0.01)
    det.box((2.6, 0.02, 0.18), matrix=trs((0.0, -D / 2 - 0.115, eave + 0.55)), mat="plastic:plastic_black")
    for x in (-2.5, 2.5):
        det.cylinder(0.1, 1.0, segments=12, matrix=trs((x, -D / 2 - 0.5, 0.5)), mat="paint_worn:industrial_yellow", bevel=0.02)
    # Entrance ramp: wedge profile in (y, z), extruded along +X.
    ramp_m = Matrix(((0.0, 0.0, 1.0, -2.2), (1.0, 0.0, 0.0, -D / 2 - 0.3), (0.0, 1.0, 0.0, 0.0), (0.0, 0.0, 0.0, 1.0)))
    g.extrude([(-1.2, 0.0), (0.0, 0.0), (0.0, SLAB_H)], 4.4, matrix=ramp_m, mat=bc.SLAB)
    # Interior racking along the back wall.
    for x in (-3.0, 0.0, 3.0):
        kit.frame_box(det, (x - 1.3, D / 2 - 1.5, SLAB_H), (x + 1.3, D / 2 - 0.5, SLAB_H + 3.2), bar=0.08,
                      mat="paint_worn:safety_orange", top=False)
        for z in (1.1, 2.2):
            det.box((2.6, 1.0, 0.05), matrix=trs((x, D / 2 - 1.0, SLAB_H + z)), mat="metal:galvanized", bevel=0.004)
    for y in (-D / 4, D / 4):
        kit.lamp(det, (0.0, y, eave + 0.2), (0.0, 0.0, -1.0), r=0.16, emit="emit:emissive_cool")
        kit.beam(det, (0.0, y, eave + 0.3), (0.0, y, eave + rise - 0.3), 0.02, 0.02, kit.STEEL, profile="tube")
    # Sockets and collision.
    ctx.socket("door_main", (0.0, -D / 2 - 1.6, 0.0), (0.0, 0.0, 180.0))
    px = (Ff @ Vector(((pers[0] + pers[1]) / 2, 0.0, 0.0))).x
    ctx.socket("door_personnel", (px, -D / 2 - 1.2, 0.0), (0.0, 0.0, 180.0))
    ctx.socket("dropoff", (0.0, -1.0, SLAB_H))
    ctx.col_box((0.0, 0.0, SLAB_H / 2), (W + 0.6, D + 0.6, SLAB_H))
    for s in (-1, 1):
        ctx.col_box((s * W / 2, 0.0, SLAB_H + wall_h / 2), (0.2, D, wall_h))
    ctx.col_box((0.0, D / 2, SLAB_H + wall_h / 2), (W, 0.2, wall_h))
    xr = [Ff @ Vector((u, 0.0, 0.0)) for u in (roller[0], roller[1], pers[0], pers[1])]
    x_r0, x_r1 = sorted((xr[0].x, xr[1].x))
    x_p0, x_p1 = sorted((xr[2].x, xr[3].x))
    for a, b, z0 in ((x_r1, W / 2, 0.0), (x_p1, x_r0, 0.0), (-W / 2, x_p0, 0.0), (x_r0, x_r1, roller[3]), (x_p0, x_p1, pers[3])):
        if b - a > 0.05:
            ctx.col_box(((a + b) / 2, -D / 2, SLAB_H + (z0 + wall_h) / 2), (b - a, 0.2, wall_h - z0))
    ctx.col_hull([(x, y, z) for x in (-2.2, 2.2) for y, z in ((-D / 2 - 1.5, 0.0), (-D / 2 - 0.3, 0.0), (-D / 2 - 0.3, SLAB_H))])
    ctx.col_hull([(x, y, z) for y in (-D / 2 - 0.3, D / 2 + 0.3)
                  for x, z in ((-W / 2 - 0.3, eave), (W / 2 + 0.3, eave), (0.0, eave + rise + 0.1))])

    def roller_clip(t):
        _, k = bc.door_swing(0.0, t, 6.0, hold=0.3)
        return {"roller_door": (None, None, (1.0, 1.0 - 0.94 * k, 1.0))}

    def door_clip(t):
        q, _ = bc.door_swing(100.0, t, 3.0)
        return {"door": (None, q)}

    ctx.clip("Idle", 2.0, True, lambda t: {}, "Doors closed")
    ctx.clip("Roller_Door", 6.0, True, roller_clip, "Roll-up door opens, holds, closes")
    ctx.clip("Door", 3.0, True, door_clip, "Personnel door opens outward, holds, closes")
    ctx.metadata["interaction"] = {"vehicle_entry": "socket_door_main", "worker_entry": "socket_door_personnel",
                                   "dropoff": "socket_dropoff"}
    ctx.metadata["doors"] = {"roller_door": {"opening_m": [4.0, 4.2]}, "door": {"hinge": "left jamb", "opens": "outward"}}
