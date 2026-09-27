"""Rigid-frame mining haul truck.

Construction: ladder-frame chassis on a steered front axle and a dual-wheel
rear axle; offset cab (left, over the front wheel) with a ladder, handrails
and mirrors; engine bonnet with radiator grille and headlights; dump body
hinged at the rear, lifted by two hoist cylinders. Bones:

* ``chassis``                       sprung body (suspension bounce/roll)
* ``susp_* / steer_* / wheel_*``    per-wheel suspension, steering, spin
* ``bed``                           dump body, tips about +X at the rear hinge
* ``hoist_barrel.L/R``, ``hoist_rod.L/R``  hoist cylinders (follow the bed)
* ``door``                          cab door, hinged about +Z

Clips (in place; ``speeds`` metadata gives the matching ground speed):
``Idle``, ``Drive``, ``Steer_Left``, ``Steer_Right``, ``Dump``, ``Door``.
Origin: ground centre between the axles; front -Y.
"""

import math

from mathutils import Quaternion, Vector

from utilities.meshkit import trs

from .. import kit
from . import common as vc

BODY = "paint_worn:industrial_yellow"
BED = "paint_worn:industrial_yellow"


def build(ctx):
    L, W = 6.4, 3.0
    r_front, r_rear = 0.78, 0.78
    tyre_w = 0.52
    y_front, y_rear = -1.95, 1.55
    frame_z = 1.05
    ctx.bone("chassis", (0.0, 0.0, frame_z), (0.0, 0.0, frame_z + 0.4))
    ch = ctx.geo("chassis", bone="chassis")
    det = ctx.geo("chassis_detail", bone="chassis", max_lod=1)
    glass = ctx.geo("glass", bone="chassis")
    # Frame rails and cross members.
    for x in (-0.55, 0.55):
        kit.beam(ch, (x, -L / 2 + 0.35, frame_z), (x, L / 2 - 0.3, frame_z), 0.18, 0.4, kit.FRAME, profile="I")
    for y in (-2.6, -1.1, 0.3, 1.9):
        kit.beam(ch, (-0.55, y, frame_z), (0.55, y, frame_z), 0.14, 0.3, kit.FRAME, profile="C")
    # Axles and differential.
    ch.cylinder(0.12, 2.1, segments=12, matrix=trs((0.0, y_front, r_front), (0, 90, 0)), mat=kit.DARK)
    ch.cylinder(0.16, 2.0, segments=14, matrix=trs((0.0, y_rear, r_rear), (0, 90, 0)), mat=kit.DARK)
    ch.sphere(0.3, segments=16, rings=8, matrix=trs((0.0, y_rear, r_rear)), mat=kit.DARK, scale=(1.0, 1.2, 1.0))
    for x in (-0.55, 0.55):                                  # leaf springs / struts
        kit.beam(ch, (x, y_front - 0.5, frame_z - 0.12), (x, y_front + 0.5, frame_z - 0.12), 0.1, 0.08, kit.DARK)
        kit.hydraulic(ch, ch, (x * 1.3, y_rear - 0.2, r_rear + 0.1), (x * 1.1, y_rear - 0.2, frame_z + 0.1), 0.07,
                      body_mat=kit.DARK)
    # Engine bonnet, grille, bumper, headlights.
    hood_c = Vector((0.0, -2.35, frame_z + 0.62))
    ch.box((1.7, 1.4, 1.0), matrix=trs(hood_c), mat=BODY, bevel=0.06, segments=2)
    ch.box((1.5, 0.06, 0.78), matrix=trs(hood_c + Vector((0.0, -0.72, -0.05))), mat=kit.DARK, bevel=0.01)
    for k in range(8):
        ch.box((1.42, 0.04, 0.03), matrix=trs(hood_c + Vector((0.0, -0.76, -0.38 + 0.095 * k))), mat=kit.STEEL, bevel=0.004)
    ch.box((W - 0.3, 0.3, 0.3), matrix=trs((0.0, -L / 2 + 0.12, frame_z - 0.1)), mat=kit.HAZARD, bevel=0.03)
    for x in (-0.95, 0.95):
        kit.lamp(det, (x, -L / 2 + 0.02, frame_z + 0.2), (0.0, -1.0, 0.0), r=0.09, emit="emit:emissive_cool")
        kit.lamp(det, (x * 0.9, hood_c.y - 0.72, hood_c.z + 0.3), (0.0, -1.0, 0.0), r=0.07, emit="emit:emissive_warm")
    ex = Vector((0.75, -1.7, frame_z + 1.1))
    kit.pipe_run(ch, [ex, ex + Vector((0.0, 0.0, 1.1))], 0.07, kit.DARK, flanges=False)
    # Deck over the front wheels, cab on the left, railing + ladder.
    deck_z = frame_z + 1.12
    kit.deck(ch, (0.0, -2.1, deck_z), (W - 0.2, 1.7), thickness=0.06)
    cab_c = Vector((-0.8, -2.0, deck_z + 0.85))
    vc.cab(ch, glass, cab_c, (1.25, 1.35, 1.6), BODY, roof_mat=kit.DARK)
    vc.seat(ch, cab_c + Vector((0.0, 0.15, -0.35)))
    ch.box((0.5, 0.4, 0.35), matrix=trs(cab_c + Vector((0.0, -0.45, -0.3))), mat=kit.DARK, bevel=0.03)   # dash
    ch.cylinder(0.17, 0.03, segments=20, matrix=trs(cab_c + Vector((0.0, -0.25, -0.05)), (55, 0, 0)), mat="plastic:plastic_black")
    kit.beacon(det, (cab_c.x, cab_c.y, cab_c.z + 0.85))
    kit.railing(ch, [(0.2, -1.3, deck_z), (1.4, -1.3, deck_z), (1.4, -2.9, deck_z), (0.2, -2.9, deck_z)],
                mat="paint_worn:industrial_yellow")
    kit.ladder(ch, (-W / 2 + 0.05, -1.25, 0.35), deck_z - 0.35, width=0.5, mat="paint_worn:industrial_yellow",
               facing=(-1, 0, 0))
    for side, x in ((-1, -W / 2 - 0.15), (1, W / 2 + 0.15)):                   # mirrors
        kit.beam(det, (x * 0.8, -2.6, deck_z + 0.9), (x, -2.8, deck_z + 1.1), 0.03, 0.03, kit.DARK, profile="tube")
        det.box((0.06, 0.25, 0.4), matrix=trs((x, -2.8, deck_z + 1.2)), mat=kit.DARK, bevel=0.02)
    # Cab door (hinged at its front edge).
    hinge = cab_c + Vector((-0.64, -0.62, 0.0))
    ctx.bone("door", tuple(hinge), tuple(hinge + Vector((0.0, 0.0, 0.4))), parent="chassis")
    door = ctx.geo("door", bone="door")
    door.box((0.05, 1.15, 1.4), matrix=trs(hinge + Vector((0.0, 0.6, 0.0))), mat=BODY, bevel=0.02)
    ctx.geo("door_glass", bone="door").box((0.02, 0.9, 0.6), matrix=trs(hinge + Vector((-0.01, 0.6, 0.25))), mat=kit.GLASS)
    door.box((0.04, 0.15, 0.04), matrix=trs(hinge + Vector((-0.04, 1.0, -0.1))), mat=kit.CHROME, bevel=0.01)
    # Fuel tank + steps on the right.
    ch.cylinder(0.35, 1.4, segments=20, matrix=trs((W / 2 - 0.45, -0.5, frame_z - 0.1), (90, 0, 0)), mat=kit.DARK, bevel=0.03)
    # Wheels.
    spin = []
    for name, x, y, r, steer, dual in (("fl", -1.2, y_front, r_front, True, False), ("fr", 1.2, y_front, r_front, True, False),
                                       ("rl", -1.05, y_rear, r_rear, False, True), ("rr", 1.05, y_rear, r_rear, False, True)):
        side = -1 if x < 0 else 1
        spin.append(vc.wheel_rig(ctx, name, (x, y, r), r, tyre_w, side, steer=steer, dual=dual))
    # Dump body (tips about the rear hinge).
    hinge_y, hinge_z = L / 2 - 0.45, frame_z + 0.3
    ctx.bone("bed", (0.0, hinge_y, hinge_z), (0.3, hinge_y, hinge_z), parent="chassis", z_axis=(0, 0, 1))
    bed = ctx.geo("bed", bone="bed")
    bdet = ctx.geo("bed_detail", bone="bed", max_lod=1)
    by0, by1 = -1.25, L / 2 - 0.1
    bz0 = frame_z + 0.35
    verts = [(-1.45, by0, bz0 + 1.2), (1.45, by0, bz0 + 1.2), (1.45, by1, bz0 + 1.0), (-1.45, by1, bz0 + 1.0),
             (-1.2, by0 + 0.1, bz0 + 0.1), (1.2, by0 + 0.1, bz0 + 0.1), (1.2, by1, bz0 + 0.35), (-1.2, by1, bz0 + 0.35)]
    faces = [(4, 5, 6, 7)[::-1], (0, 1, 5, 4)[::-1], (1, 2, 6, 5)[::-1], (3, 0, 4, 7)[::-1], (2, 3, 7, 6)[::-1]]
    bed.mesh(verts, faces, mat=BED, recalc=True)
    thick = [(x * 0.97, y, z - 0.04) for x, y, z in verts]
    bed.mesh(thick, [f[::-1] for f in faces], mat=BED, recalc=True)
    bed.box((3.1, 0.25, 0.25), matrix=trs((0.0, by0 - 0.05, bz0 + 1.3)), mat=BED, bevel=0.04)       # front lip
    bed.box((3.0, 1.1, 0.12), matrix=trs((0.0, by0 - 0.55, bz0 + 1.45), (-8, 0, 0)), mat=BED, bevel=0.03)   # canopy
    for k in range(5):
        bdet.box((0.1, by1 - by0 - 0.3, 0.12), matrix=trs((-1.2 + 0.6 * k, (by0 + by1) / 2, bz0 + 0.02)), mat=kit.DARK,
                 bevel=0.01)
    for y in (by0 + 0.8, by0 + 1.8, by0 + 2.8):
        for x in (-1.47, 1.47):
            bed.box((0.06, 0.12, 1.0), matrix=trs((x, y, bz0 + 0.65)), mat=BED, bevel=0.01)
    # Hoist cylinders.
    lift_pts = {}
    for s, x in (("L", -0.7), ("R", 0.7)):
        base = Vector((x, -0.6, frame_z + 0.05))
        tip = Vector((x, 0.35, bz0 + 0.12))
        lift_pts[s] = (base, tip)
        ctx.bone(f"hoist_barrel.{s}", tuple(base), tuple(base + (tip - base).normalized() * 0.3), parent="chassis")
        ctx.bone(f"hoist_rod.{s}", tuple(tip), tuple(tip + (tip - base).normalized() * 0.3), parent=f"hoist_barrel.{s}")
        kit.hydraulic(ctx.geo(f"hoist_barrel.{s}", bone=f"hoist_barrel.{s}"), ctx.geo(f"hoist_rod.{s}", bone=f"hoist_rod.{s}"),
                      base, tip, 0.1, body_ratio=0.55, body_mat=kit.DARK)
    for x in (-1.1, 1.1):
        kit.lamp(det, (x, L / 2 - 0.1, frame_z - 0.05), (0.0, 1.0, 0.0), r=0.06, emit="emit:emissive_red")
    # Sockets.
    ctx.socket("driver", tuple(cab_c + Vector((0.0, 0.15, -0.3))), bone="chassis")
    ctx.socket("entry", (-W / 2 - 0.6, -1.25, 0.0), (0.0, 0.0, -90.0))
    ctx.socket("load", (0.0, (by0 + by1) / 2, bz0 + 1.6), bone="bed")
    ctx.socket("dump", (0.0, L / 2 + 1.2, 0.0))
    # Collision.
    ctx.col_box((0.0, 0.0, frame_z), (1.4, L - 0.6, 0.6))
    ctx.col_box((0.0, (by0 + by1) / 2, bz0 + 0.7), (3.0, by1 - by0, 1.4))
    ctx.col_box((0.0, -2.2, deck_z + 0.2), (W - 0.2, 1.9, deck_z - 0.3))
    ctx.col_box(tuple(cab_c), (1.3, 1.4, 1.65))
    for x, y, r in ((-1.2, y_front, r_front), (1.2, y_front, r_front), (-1.05, y_rear, r_rear), (1.05, y_rear, r_rear)):
        ctx.col_cylinder((x, y, r), r, tyre_w * (1.0 if abs(x) > 1.1 else 2.2), rot=(0, 90, 0))

    speed = 4.0                                        # m/s for Drive
    T = 2 * math.pi * r_rear * 2 / speed               # two full wheel turns per loop

    def drive(t):
        out = vc.spin_wheels(spin, r_rear, speed * t)
        bob = 0.012 * math.sin(2 * math.pi * 3 * t / T)
        out["chassis"] = (Vector((0.0, 0.0, bob)), Quaternion((0, 1, 0), 0.004 * math.sin(2 * math.pi * 2 * t / T)))
        return out

    def steer(sign):
        def fn(t):
            u = 0.5 - 0.5 * math.cos(2 * math.pi * t / 2.0)
            q = Quaternion((0, 0, 1), sign * math.radians(30) * u)
            return {"steer_fl": (None, q), "steer_fr": (None, q)}
        return fn

    def dump(t):
        Td = 6.0
        u = t / Td
        k = min(1.0, u / 0.35) if u < 0.6 else max(0.0, 1.0 - (u - 0.6) / 0.35)
        ang = -math.radians(50) * (0.5 - 0.5 * math.cos(math.pi * k))
        out = {"bed": (None, Quaternion((1, 0, 0), ang))}
        for s, (base, tip) in lift_pts.items():
            qb, ext = vc.linkage_pose(base, tip, (0.0, hinge_y, hinge_z), (1, 0, 0), ang)
            out[f"hoist_barrel.{s}"] = (None, qb)
            out[f"hoist_rod.{s}"] = (ext, None)
        return out

    def door(t):
        u = 0.5 - 0.5 * math.cos(2 * math.pi * t / 2.4)
        return {"door": (None, Quaternion((0, 0, 1), -math.radians(75) * u))}

    def idle(t):
        return {"chassis": (Vector((0.0, 0.0, 0.002 * math.sin(2 * math.pi * 10 * t / 2.0))), None)}

    ctx.clip("Idle", 2.0, True, idle, "Engine idling (body shiver)")
    ctx.clip("Drive", T, True, drive, f"Driving at {speed} m/s: wheels roll, suspension bounce (in place)")
    ctx.clip("Steer_Left", 2.0, True, steer(1.0), "Front wheels steer left 30 degrees and back")
    ctx.clip("Steer_Right", 2.0, True, steer(-1.0), "Front wheels steer right 30 degrees and back")
    ctx.clip("Dump", 6.0, False, dump, "Hoists tip the dump body 50 degrees, hold, lower")
    ctx.clip("Door", 2.4, False, door, "Cab door opens 75 degrees and closes")
    ctx.metadata["speeds"] = {"drive_mps": speed, "wheel_radius_m": r_rear, "max_steer_deg": 30}
    ctx.metadata["interaction"] = {"driver": "socket_driver", "entry": "socket_entry", "load": "socket_load",
                                   "dump": "socket_dump"}
