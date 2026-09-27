"""Tracked hydraulic excavator.

Construction: undercarriage with two track frames (sprocket at the rear,
idler at the front, road and carrier rollers) and a slewing ring carrying the
upper structure (cab front-left, engine house and counterweight at the rear);
boom, stick and bucket are driven by hydraulic cylinders whose barrels and
rods stay connected through the whole motion. Every track pad is rigged to
its own bone and travels around the track loop. Bones:

* ``swing``                          upper structure, slews about +Z
* ``boom`` / ``stick`` / ``bucket``  digging linkage, rotate about +X
* ``cyl_*_barrel`` / ``cyl_*_rod``   hydraulic cylinders (follow the linkage)
* ``sprocket.L/R``, ``idler.L/R``    track wheels, spin about +X
* ``pad_NN.L`` / ``pad_NN.R``        track pads (ride the loop)

Clips: ``Idle``, ``Dig`` (dig, lift, swing 90 degrees, dump, return) and
``Travel`` (tracks drive forward in place). Origin: ground centre.
"""

import math

from mathutils import Matrix, Quaternion, Vector

from animation.machine_anim import loop_spin
from utilities.meshkit import trs

from .. import kit
from . import common as vc

BODY = "paint_worn:industrial_yellow"


def build(ctx):
    track_x, track_len, track_w = 1.05, 3.4, 0.55
    r_spr = 0.36
    y_spr, y_idl = track_len / 2 - 0.15, -track_len / 2 + 0.15
    zc = r_spr + 0.06
    under = ctx.geo("undercarriage")
    udet = ctx.geo("undercarriage_detail", max_lod=1)
    loops = {}
    pads = {}
    for side, sx in (("L", 1), ("R", -1)):
        x = sx * track_x
        # Track frame and rollers.
        under.box((0.34, track_len - 0.6, 0.42), matrix=trs((x, 0.0, zc)), mat=kit.DARK, bevel=0.03)
        for k in range(5):
            y = -track_len / 2 + 0.75 + (track_len - 1.5) * k / 4
            under.cylinder(0.13, track_w * 0.7, segments=14, matrix=trs((x, y, 0.2), (0, 90, 0)), mat=kit.DARK, bevel=0.01)
        for y in (-0.6, 0.6):
            udet.cylinder(0.08, 0.18, segments=12, matrix=trs((x, y, zc + r_spr - 0.04), (0, 90, 0)), mat=kit.DARK)
        for name, y, r in ((f"sprocket.{side}", y_spr, r_spr), (f"idler.{side}", y_idl, r_spr - 0.02)):
            c = Vector((x, y, zc))
            ctx.bone(name, tuple(c), tuple(c + Vector((0.3 * sx, 0.0, 0.0))), z_axis=(0, 0, 1))
            wg = ctx.geo(name, bone=name)
            wg.cylinder(r - 0.03, track_w * 0.6, segments=20, matrix=trs(c, (0, 90, 0)), mat=kit.DARK, bevel=0.01)
            if name.startswith("sprocket"):
                for k in range(10):
                    a = 2 * math.pi * k / 10
                    wg.box((0.06, 0.05, track_w * 0.3), matrix=trs(c, (0, 90, 0)) @ trs((math.cos(a) * (r - 0.02),
                                                                                        math.sin(a) * (r - 0.02), 0.0),
                                                                                       (0, 0, math.degrees(a))), mat=kit.DARK)
        # Pads around the loop (top run moves forward = -Y).
        loop = kit.LoopPath((x, y_spr, zc), (x, y_idl, zc), r_spr + 0.02, (1.0, 0.0, 0.0))
        count = int(loop.length / 0.24)
        pitch = loop.length / count
        loops[side] = (loop, pitch)
        pads[side] = []
        for i in range(count):
            f = loop.frame(i * pitch)
            bn = f"pad_{i:02d}.{side}"
            ctx.bone(bn, tuple(f.translation), tuple(f.translation + f.to_3x3() @ Vector((0.0, 0.0, 0.15))),
                     z_axis=tuple(f.to_3x3() @ Vector((0.0, 1.0, 0.0))))
            pg = ctx.geo(bn, bone=bn)
            pg.box((track_w, pitch * 0.92, 0.05), matrix=f @ trs((0.0, 0.0, 0.02)), mat=kit.DARK, bevel=0.008, segments=1)
            pg.box((track_w * 0.95, 0.04, 0.035), matrix=f @ trs((0.0, 0.0, 0.06)), mat=kit.DARK)   # grouser
            pads[side].append((bn, i * pitch))
    # Car body and slewing ring.
    under.box((1.2, 1.4, 0.35), matrix=trs((0.0, 0.0, zc + 0.12)), mat=kit.DARK, bevel=0.04)
    under.cylinder(0.75, 0.16, segments=32, matrix=trs((0.0, 0.0, zc + 0.37)), mat=kit.DARK, bevel=0.02)
    # --- upper structure (slews)
    ring_z = zc + 0.45
    ctx.bone("swing", (0.0, 0.0, ring_z), (0.0, 0.0, ring_z + 0.5))
    up = ctx.geo("upper", bone="swing")
    updet = ctx.geo("upper_detail", bone="swing", max_lod=1)
    glass = ctx.geo("glass", bone="swing")
    up.box((2.3, 2.9, 0.22), matrix=trs((0.0, 0.25, ring_z + 0.11)), mat=kit.DARK, bevel=0.03)
    up.box((2.3, 1.0, 1.0), matrix=trs((0.0, 1.3, ring_z + 0.72)), mat=BODY, bevel=0.1, segments=2)          # counterweight
    up.box((1.3, 1.3, 0.95), matrix=trs((0.45, 0.45, ring_z + 0.68)), mat=BODY, bevel=0.05, segments=2)      # engine hood
    for k in range(6):
        updet.box((0.9, 0.04, 0.02), matrix=trs((0.45, -0.2 + 0.12 * k, ring_z + 1.16)), mat=kit.DARK, bevel=0.004)
    kit.pipe_run(up, [(0.8, 0.9, ring_z + 1.1), (0.8, 0.9, ring_z + 1.7)], 0.06, kit.DARK, flanges=False)
    cab_c = Vector((-0.6, -0.55, ring_z + 1.0))
    vc.cab(up, glass, cab_c, (0.95, 1.2, 1.55), BODY, roof_mat=kit.DARK)
    vc.seat(up, cab_c + Vector((0.0, 0.1, -0.35)))
    kit.beacon(updet, (-0.6, -0.5, ring_z + 1.85))
    kit.lamp(updet, (-0.2, -1.1, ring_z + 1.7), (0.0, -1.0, -0.2), emit="emit:emissive_cool")
    kit.railing(up, [(0.05, -0.3, ring_z + 1.15), (1.1, -0.3, ring_z + 1.15)], height=0.5, mat=BODY, toe=False)
    # --- digging linkage (rest pose: boom raised, stick hanging, bucket curled)
    boom_p = Vector((0.25, -0.75, ring_z + 0.45))
    boom_mid = boom_p + Vector((0.0, -1.3, 1.5))
    boom_tip = boom_p + Vector((0.0, -2.9, 1.9))
    stick_tip = boom_tip + Vector((0.0, -0.55, -1.9))
    ctx.bone("boom", tuple(boom_p), tuple(boom_p + Vector((0.3, 0.0, 0.0))), parent="swing", z_axis=(0, 0, 1))
    ctx.bone("stick", tuple(boom_tip), tuple(boom_tip + Vector((0.3, 0.0, 0.0))), parent="boom", z_axis=(0, 0, 1))
    ctx.bone("bucket", tuple(stick_tip), tuple(stick_tip + Vector((0.3, 0.0, 0.0))), parent="stick", z_axis=(0, 0, 1))
    boom = ctx.geo("boom", bone="boom")
    kit.beam(boom, boom_p, boom_mid, 0.36, 0.5, BODY, bevel=0.04, up=(0, 1, 0))
    kit.beam(boom, boom_mid, boom_tip, 0.34, 0.44, BODY, bevel=0.04, up=(0, 1, 0))
    boom.cylinder(0.14, 0.5, segments=16, matrix=trs(boom_p, (0, 90, 0)), mat=kit.DARK)
    boom.cylinder(0.12, 0.46, segments=16, matrix=trs(boom_tip, (0, 90, 0)), mat=kit.DARK)
    stick = ctx.geo("stick", bone="stick")
    kit.beam(stick, boom_tip + Vector((0.0, 0.2, 0.35)), stick_tip, 0.3, 0.36, BODY, bevel=0.03, up=(0, 1, 0))
    stick.cylinder(0.1, 0.4, segments=16, matrix=trs(stick_tip, (0, 90, 0)), mat=kit.DARK)
    bucket = ctx.geo("bucket", bone="bucket")
    bprof = [(stick_tip + Vector((0.0, 0.05, 0.05))), (stick_tip + Vector((0.0, -0.55, 0.0))),
             (stick_tip + Vector((0.0, -0.75, -0.35))), (stick_tip + Vector((0.0, -0.5, -0.62))),
             (stick_tip + Vector((0.0, -0.1, -0.55)))]
    for sgn in (-1, 1):                                   # side plates
        pts = [p + Vector((sgn * 0.42, 0.0, 0.0)) for p in bprof]
        verts = [tuple(p) for p in pts] + [tuple(p + Vector((sgn * 0.03, 0.0, 0.0))) for p in pts]
        n = len(pts)
        faces = [tuple(range(n))[::-1] if sgn > 0 else tuple(range(n)), tuple(range(n, 2 * n)) if sgn > 0 else tuple(range(2 * n - 1, n - 1, -1))]
        faces += [(i, (i + 1) % n, n + (i + 1) % n, n + i) for i in range(n)]
        bucket.mesh(verts, faces, mat=BODY, recalc=True)
    shell = [bprof[0], bprof[1], bprof[2], bprof[3], bprof[4]]
    kit.beam(bucket, bprof[1] + Vector((-0.42, 0.0, 0.0)), bprof[1] + Vector((0.42, 0.0, 0.0)), 0.05, 0.05, kit.DARK)
    for a, b in zip(shell, shell[1:]):
        d = (b - a)
        # seg_frame(up=X): local Z along the segment, local Y = world X (width), local X = plate normal.
        bucket.box((0.03, 0.86, d.length + 0.02), matrix=kit.seg_frame(a, b, (1, 0, 0)) @ trs((0.0, 0.0, d.length / 2)),
                   mat=BODY, bevel=0.005)
    for k in range(5):                                    # teeth
        x = -0.34 + 0.17 * k
        bucket.box((0.07, 0.14, 0.05), matrix=trs(bprof[3] + Vector((x, -0.08, -0.02)), (30, 0, 0)), mat=kit.STEEL, bevel=0.01)
    # Hydraulic cylinders (barrel on the driving body, rod on the driven body).
    cyls = [
        ("boom_l", "swing", Vector((0.05, -0.2, ring_z + 0.35)), boom_mid + Vector((-0.2, 0.25, -0.2)), "boom", boom_p),
        ("boom_r", "swing", Vector((0.45, -0.2, ring_z + 0.35)), boom_mid + Vector((0.2, 0.25, -0.2)), "boom", boom_p),
        ("stick", "boom", boom_mid + Vector((0.0, -0.1, 0.35)), boom_tip + Vector((0.0, 0.35, 0.45)), "stick", boom_tip),
        ("bucket", "stick", boom_tip + Vector((0.0, -0.05, 0.2)), stick_tip + Vector((0.0, 0.1, 0.25)), "bucket", stick_tip),
    ]
    for name, parent, base, tip, _, _ in cyls:
        bb, rb = f"cyl_{name}_barrel", f"cyl_{name}_rod"
        ctx.bone(bb, tuple(base), tuple(base + (tip - base).normalized() * 0.3), parent=parent)
        ctx.bone(rb, tuple(tip), tuple(tip + (tip - base).normalized() * 0.3), parent=bb)
        kit.hydraulic(ctx.geo(bb, bone=bb), ctx.geo(rb, bone=rb), base, tip, 0.085, body_ratio=0.55, body_mat=BODY)
    # Sockets and collision.
    ctx.socket("driver", tuple(cab_c + Vector((0.0, 0.1, -0.3))), bone="swing")
    ctx.socket("entry", (-track_x - 0.9, -0.55, 0.0), (0.0, 0.0, -90.0))
    ctx.socket("bucket_teeth", tuple(bprof[3]), bone="bucket")
    ctx.col_box((track_x, 0.0, zc), (track_w + 0.1, track_len, 2 * zc))
    ctx.col_box((-track_x, 0.0, zc), (track_w + 0.1, track_len, 2 * zc))
    ctx.col_box((0.0, 0.25, ring_z + 0.6), (2.3, 2.9, 1.2))
    ctx.col_box(tuple(cab_c), (1.0, 1.25, 1.6))
    ctx.col_hull([tuple(p + Vector((dx, 0.0, 0.0))) for p in (boom_p, boom_mid, boom_tip, stick_tip, bprof[2], bprof[3])
                  for dx in (-0.45, 0.45)])

    def linkage(boom_a, stick_a, bucket_a, swing_a):
        out = {"swing": (None, Quaternion((0, 0, 1), swing_a)),
               "boom": (None, Quaternion((1, 0, 0), boom_a)),
               "stick": (None, Quaternion((1, 0, 0), stick_a)),
               "bucket": (None, Quaternion((1, 0, 0), bucket_a))}
        angles = {"boom": boom_a, "stick": stick_a, "bucket": bucket_a}
        for name, _, base, tip, driven, pivot in cyls:
            qb, ext = vc.linkage_pose(base, tip, pivot, (1, 0, 0), angles[driven])
            out[f"cyl_{name}_barrel"] = (None, qb)
            out[f"cyl_{name}_rod"] = (ext, None)
        return out

    def dig(t):
        T = 7.0
        keys = [(0.0, (0.0, 0.0, 0.0, 0.0)), (1.2, (-0.35, 0.35, -0.3, 0.0)), (2.2, (-0.32, 0.75, 0.9, 0.0)),
                (3.0, (0.1, 0.55, 1.0, 0.0)), (4.0, (0.15, 0.4, 1.0, 1.5708)), (4.7, (0.1, 0.1, -0.5, 1.5708)),
                (5.6, (0.05, 0.1, -0.2, 0.8)), (7.0, (0.0, 0.0, 0.0, 0.0))]
        for (t0, v0), (t1, v1) in zip(keys, keys[1:]):
            if t0 <= t <= t1:
                u = (t - t0) / (t1 - t0)
                u = u * u * (3 - 2 * u)
                v = [a + (b - a) * u for a, b in zip(v0, v1)]
                return linkage(*v)
        return linkage(0.0, 0.0, 0.0, 0.0)

    speed = 1.2

    def travel_clip():
        loop, pitch = loops["L"]
        T = 4 * pitch / speed
        turns = max(1, round(speed * T / (2 * math.pi * r_spr)))

        def travel(t):
            adv = speed * t
            out = {}
            for side in ("L", "R"):
                lp, _ = loops[side]
                for bn, s0 in pads[side]:
                    out[bn] = kit.loop_pose(lp, s0, adv)
                out[f"sprocket.{side}"] = (None, loop_spin((1, 0, 0), turns, t, T))
                out[f"idler.{side}"] = (None, loop_spin((1, 0, 0), turns, t, T))
            return out
        return T, travel

    ctx.clip("Idle", 2.0, True, lambda t: linkage(0.0, 0.0, 0.0, 0.0), "Parked, linkage at rest")
    ctx.clip("Dig", 7.0, True, dig, "Dig cycle: lower, curl to fill, lift, swing 90 degrees, dump, return")
    T, travel = travel_clip()
    ctx.clip("Travel", T, True, travel, f"Tracks drive at {speed} m/s (in place): pads circulate, sprockets turn")
    ctx.metadata["speeds"] = {"travel_mps": speed, "swing_deg_per_s": 90 / 1.0}
    ctx.metadata["interaction"] = {"driver": "socket_driver", "entry": "socket_entry", "dig_point": "socket_bucket_teeth"}
