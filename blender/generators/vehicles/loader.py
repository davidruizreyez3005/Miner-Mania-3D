"""Articulated wheel loader.

Construction: rear frame (engine, cab, counterweight, rear axle) and front
frame (front axle, loader arms, bucket) joined by the centre articulation
hinge, which is how the loader steers. Lift and tilt cylinders stay attached
through the motion. Bones:

* ``articulation``                    front frame, yaws about +Z (steering)
* ``arms`` / ``bucket``               loader arms and bucket, rotate about +X
* ``cyl_lift.L/R``, ``cyl_tilt`` (+ ``_rod``)  hydraulic cylinders
* ``susp_* / wheel_*``                per-wheel suspension and spin

Clips: ``Idle``, ``Drive``, ``Steer_Left``, ``Steer_Right``, ``Scoop``
(lower, crowd, curl, lift, dump, lower). Origin: ground centre; front -Y.
"""

import math

from mathutils import Quaternion, Vector

from utilities.meshkit import trs

from .. import kit
from . import common as vc

BODY = "paint_worn:industrial_yellow"


def build(ctx):
    r = 0.72
    y_front, y_rear = -1.45, 1.45
    frame_z = 0.95
    hinge = Vector((0.0, -0.15, frame_z))
    rear = ctx.geo("rear_frame")
    rdet = ctx.geo("rear_detail", max_lod=1)
    glass = ctx.geo("glass")
    rear.box((1.1, 1.9, 0.5), matrix=trs((0.0, 0.8, frame_z)), mat=kit.DARK, bevel=0.04)
    rear.box((1.9, 1.3, 1.05), matrix=trs((0.0, 1.35, frame_z + 0.75)), mat=BODY, bevel=0.08, segments=2)     # engine
    rear.box((2.0, 0.35, 0.85), matrix=trs((0.0, 2.1, frame_z + 0.4)), mat=BODY, bevel=0.08, segments=2)     # counterweight
    for k in range(7):
        rdet.box((1.5, 0.03, 0.03), matrix=trs((0.0, 2.29, frame_z + 0.1 + 0.1 * k)), mat=kit.DARK, bevel=0.004)
    kit.pipe_run(rear, [(0.55, 1.1, frame_z + 1.25), (0.55, 1.1, frame_z + 1.9)], 0.06, kit.DARK, flanges=False)
    cab_c = Vector((0.0, 0.35, frame_z + 1.25))
    vc.cab(rear, glass, cab_c, (1.25, 1.2, 1.6), BODY, roof_mat=kit.DARK)
    vc.seat(rear, cab_c + Vector((0.0, 0.1, -0.35)))
    kit.beacon(rdet, (0.0, 0.5, cab_c.z + 0.85))
    for x in (-0.55, 0.55):
        kit.lamp(rdet, (x, -0.28, cab_c.z + 0.72), (0.0, -1.0, -0.15), emit="emit:emissive_cool")
        kit.lamp(rdet, (x * 1.4, 2.28, frame_z + 0.7), (0.0, 1.0, 0.0), r=0.05, emit="emit:emissive_red")
    kit.ladder(rear, (-0.95, 0.2, 0.3), frame_z + 0.3, width=0.4, mat=BODY, facing=(-1, 0, 0))
    rear.cylinder(0.14, 1.9, segments=14, matrix=trs((0.0, y_rear, r), (0, 90, 0)), mat=kit.DARK)
    spin = []
    for name, x in (("rl", -1.0), ("rr", 1.0)):
        spin.append(vc.wheel_rig(ctx, name, (x, y_rear, r), r, 0.5, -1 if x < 0 else 1, parent="root"))
    # Front frame (articulates).
    ctx.bone("articulation", tuple(hinge), tuple(hinge + Vector((0.0, 0.0, 0.4))))
    front = ctx.geo("front_frame", bone="articulation")
    front.box((0.9, 1.4, 0.5), matrix=trs((0.0, -1.0, frame_z)), mat=kit.DARK, bevel=0.04)
    front.cylinder(0.1, 0.6, segments=14, matrix=trs(hinge), mat=kit.STEEL)
    front.cylinder(0.14, 1.9, segments=14, matrix=trs((0.0, y_front, r), (0, 90, 0)), mat=kit.DARK)
    for name, x in (("fl", -1.0), ("fr", 1.0)):
        spin.append(vc.wheel_rig(ctx, name, (x, y_front, r), r, 0.5, -1 if x < 0 else 1, parent="articulation"))
    # Loader arms + bucket.
    arm_p = Vector((0.0, -0.95, frame_z + 0.85))
    arm_tip = Vector((0.0, -2.65, frame_z - 0.45))
    ctx.bone("arms", tuple(arm_p), tuple(arm_p + Vector((0.3, 0.0, 0.0))), parent="articulation", z_axis=(0, 0, 1))
    ctx.bone("bucket", tuple(arm_tip), tuple(arm_tip + Vector((0.3, 0.0, 0.0))), parent="arms", z_axis=(0, 0, 1))
    arms = ctx.geo("arms", bone="arms")
    for x in (-0.55, 0.55):
        mid = Vector((x, -1.9, frame_z + 0.55))
        kit.beam(arms, Vector((x, arm_p.y, arm_p.z)), mid, 0.14, 0.32, BODY, bevel=0.03, up=(0, 1, 0))
        kit.beam(arms, mid, Vector((x, arm_tip.y, arm_tip.z)), 0.14, 0.3, BODY, bevel=0.03, up=(0, 1, 0))
        arms.cylinder(0.1, 0.22, segments=14, matrix=trs((x, arm_p.y, arm_p.z), (0, 90, 0)), mat=kit.DARK)
    kit.beam(arms, (-0.55, -1.8, frame_z + 0.55), (0.55, -1.8, frame_z + 0.55), 0.18, 0.18, BODY)
    bucket = ctx.geo("bucket", bone="bucket")
    bw = 2.3
    back = [arm_tip + Vector((0.0, 0.05, 0.55)), arm_tip + Vector((0.0, 0.1, -0.05)), arm_tip + Vector((0.0, -0.25, -0.4)),
            arm_tip + Vector((0.0, -0.95, -0.42))]
    for a, b in zip(back, back[1:]):
        d = b - a
        # seg_frame(up=X): local Z along the segment, local Y = world X (width), local X = plate normal.
        bucket.box((0.04, bw, d.length + 0.03), matrix=kit.seg_frame(a, b, (1, 0, 0)) @ trs((0.0, 0.0, d.length / 2)),
                   mat=BODY, bevel=0.006)
    for s in (-1, 1):
        pts = [p + Vector((s * bw / 2, 0.0, 0.0)) for p in back] + [arm_tip + Vector((s * bw / 2, -0.95, 0.2))]
        verts = [tuple(p) for p in pts] + [tuple(p + Vector((-s * 0.03, 0.0, 0.0))) for p in pts]
        n = len(pts)
        faces = [tuple(range(n)), tuple(range(2 * n - 1, n - 1, -1))] + [(i, (i + 1) % n, n + (i + 1) % n, n + i) for i in range(n)]
        bucket.mesh(verts, faces, mat=BODY, recalc=True)
    bucket.box((bw + 0.04, 0.1, 0.06), matrix=trs(back[-1] + Vector((0.0, -0.03, 0.0))), mat=kit.STEEL, bevel=0.01)
    for k in range(7):
        bucket.box((0.08, 0.16, 0.05), matrix=trs(back[-1] + Vector((-1.0 + k * 0.333, -0.1, 0.0))), mat=kit.STEEL, bevel=0.01)
    # Cylinders: lift (frame -> arms), tilt (arms crossbar -> bucket top).
    cyls = [("lift.L", "articulation", Vector((-0.45, -0.55, frame_z - 0.05)), Vector((-0.45, -1.7, frame_z + 0.4)), "arms", arm_p),
            ("lift.R", "articulation", Vector((0.45, -0.55, frame_z - 0.05)), Vector((0.45, -1.7, frame_z + 0.4)), "arms", arm_p),
            ("tilt", "arms", Vector((0.0, -1.3, frame_z + 1.0)), arm_tip + Vector((0.0, 0.05, 0.55)), "bucket", arm_tip)]
    for name, parent, base, tip, _, _ in cyls:
        stem, side = (name.split(".") + [""])[:2]
        bb = f"cyl_{stem}.{side}" if side else f"cyl_{stem}"
        rb = f"cyl_{stem}_rod.{side}" if side else f"cyl_{stem}_rod"
        ctx.bone(bb, tuple(base), tuple(base + (tip - base).normalized() * 0.3), parent=parent)
        ctx.bone(rb, tuple(tip), tuple(tip + (tip - base).normalized() * 0.3), parent=bb)
        kit.hydraulic(ctx.geo(bb, bone=bb), ctx.geo(rb, bone=rb), base, tip, 0.08, body_mat=BODY)
    ctx.socket("driver", tuple(cab_c + Vector((0.0, 0.1, -0.3))))
    ctx.socket("entry", (-1.6, 0.2, 0.0), (0.0, 0.0, -90.0))
    ctx.socket("bucket_edge", tuple(back[-1]), bone="bucket")
    ctx.col_box((0.0, 1.2, frame_z + 0.4), (2.0, 2.2, 1.7))
    ctx.col_box(tuple(cab_c), (1.3, 1.25, 1.65))
    ctx.col_box((0.0, -1.0, frame_z), (1.2, 1.6, 0.8))
    ctx.col_box((0.0, -3.1, frame_z - 0.6), (bw, 1.1, 0.9))
    for x, y in ((-1.0, y_front), (1.0, y_front), (-1.0, y_rear), (1.0, y_rear)):
        ctx.col_cylinder((x, y, r), r, 0.5, rot=(0, 90, 0))

    def link(arms_a, bucket_a, steer_a=0.0):
        out = {"arms": (None, Quaternion((1, 0, 0), arms_a)), "bucket": (None, Quaternion((1, 0, 0), bucket_a)),
               "articulation": (None, Quaternion((0, 0, 1), steer_a))}
        ang = {"arms": arms_a, "bucket": bucket_a}
        for name, _, base, tip, driven, pivot in cyls:
            stem, side = (name.split(".") + [""])[:2]
            bb = f"cyl_{stem}.{side}" if side else f"cyl_{stem}"
            rb = f"cyl_{stem}_rod.{side}" if side else f"cyl_{stem}_rod"
            qb, ext = vc.linkage_pose(base, tip, pivot, (1, 0, 0), ang[driven])
            out[bb] = (None, qb)
            out[rb] = (ext, None)
        return out

    speed = 3.0
    T_drive = 2 * math.pi * r * 2 / speed

    def drive(t):
        out = vc.spin_wheels(spin, r, speed * t)
        return out

    def steer(sign):
        return lambda t: link(0.0, 0.0, sign * math.radians(35) * (0.5 - 0.5 * math.cos(2 * math.pi * t / 2.4)))

    def scoop(t):
        keys = [(0.0, (0.0, 0.0)), (1.0, (-0.05, -0.35)), (2.0, (0.02, 0.45)), (3.2, (0.75, 0.55)), (4.2, (0.8, -0.6)),
                (5.0, (0.6, -0.4)), (6.0, (0.0, 0.0))]
        for (t0, a), (t1, b) in zip(keys, keys[1:]):
            if t0 <= t <= t1:
                u = (t - t0) / (t1 - t0)
                u = u * u * (3 - 2 * u)
                return link(a[0] + (b[0] - a[0]) * u, a[1] + (b[1] - a[1]) * u)
        return link(0.0, 0.0)

    ctx.clip("Idle", 2.0, True, lambda t: link(0.0, 0.0), "Parked")
    ctx.clip("Drive", T_drive, True, drive, f"Driving at {speed} m/s (in place)")
    ctx.clip("Steer_Left", 2.4, True, steer(1.0), "Articulates 35 degrees left and back")
    ctx.clip("Steer_Right", 2.4, True, steer(-1.0), "Articulates 35 degrees right and back")
    ctx.clip("Scoop", 6.0, True, scoop, "Lower, crowd and curl the bucket, lift, dump, lower")
    ctx.metadata["speeds"] = {"drive_mps": speed, "wheel_radius_m": r, "max_articulation_deg": 35}
    ctx.metadata["interaction"] = {"driver": "socket_driver", "entry": "socket_entry", "dig_point": "socket_bucket_edge"}
