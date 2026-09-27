"""Site utility pickup (4x4 service vehicle).

Construction: body-on-frame pickup with a two-door cab, bull bar, roof light
bar and beacon, service bed with toolbox and ladder rack. Bones:

* ``chassis``                       sprung body
* ``susp_* / steer_* / wheel_*``    suspension, front steering, wheel spin
* ``door.L`` / ``door.R``           cab doors, hinged at the A-pillars

Clips: ``Idle``, ``Drive``, ``Steer_Left``, ``Steer_Right``, ``Door``.
Origin: ground centre; front -Y.
"""

import math

from mathutils import Quaternion, Vector

from utilities.meshkit import trs

from .. import kit
from . import common as vc

BODY = "paint_worn:white_paint"


def build(ctx):
    r, tw = 0.38, 0.28
    y_front, y_rear = -1.35, 1.4
    frame_z = 0.62
    ctx.bone("chassis", (0.0, 0.0, frame_z), (0.0, 0.0, frame_z + 0.3))
    body = ctx.geo("body", bone="chassis")
    det = ctx.geo("body_detail", bone="chassis", max_lod=1)
    glass = ctx.geo("glass", bone="chassis")
    for x in (-0.45, 0.45):
        kit.beam(body, (x, -2.0, frame_z - 0.08), (x, 2.05, frame_z - 0.08), 0.08, 0.14, kit.DARK, profile="C")
    # Bonnet + grille + bull bar.
    body.box((1.8, 1.25, 0.5), matrix=trs((0.0, -1.55, frame_z + 0.35)), mat=BODY, bevel=0.06, segments=2)
    body.box((1.5, 0.05, 0.3), matrix=trs((0.0, -2.18, frame_z + 0.32)), mat=kit.DARK, bevel=0.01)
    kit.beam(body, (-0.85, -2.35, frame_z + 0.1), (0.85, -2.35, frame_z + 0.1), 0.05, 0.05, kit.DARK, profile="tube")
    kit.beam(body, (-0.85, -2.35, frame_z + 0.45), (0.85, -2.35, frame_z + 0.45), 0.05, 0.05, kit.DARK, profile="tube")
    for x in (-0.55, 0.55):
        kit.beam(body, (x, -2.35, frame_z - 0.05), (x, -2.35, frame_z + 0.5), 0.05, 0.05, kit.DARK, profile="tube")
        kit.lamp(det, (x * 1.25, -2.19, frame_z + 0.42), (0.0, -1.0, 0.0), r=0.08, emit="emit:emissive_cool")
        kit.lamp(det, (x * 1.5, 2.15, frame_z + 0.35), (0.0, 1.0, 0.0), r=0.05, emit="emit:emissive_red")
    # Cab.
    cab_c = Vector((0.0, -0.4, frame_z + 0.85))
    vc.cab(body, glass, cab_c, (1.8, 1.4, 1.1), BODY, roof_mat=BODY)
    body.box((1.8, 1.3, 0.4), matrix=trs((0.0, -0.4, frame_z + 0.25)), mat=BODY, bevel=0.04)
    for x in (-0.4, 0.4):
        vc.seat(body, (x, -0.25, frame_z + 0.5))
    det.box((1.4, 0.2, 0.08), matrix=trs((0.0, -0.55, cab_c.z + 0.6)), mat=kit.DARK, bevel=0.02)     # light bar
    for k in range(6):
        det.box((0.16, 0.02, 0.05), matrix=trs((-0.6 + 0.24 * k, -0.66, cab_c.z + 0.6)), mat="emit:emissive_cool")
    kit.beacon(det, (0.55, -0.2, cab_c.z + 0.56), r=0.05)
    # Service bed with toolbox and ladder rack.
    body.box((1.8, 1.9, 0.14), matrix=trs((0.0, 1.1, frame_z + 0.1)), mat=BODY, bevel=0.03)
    for x in (-0.88, 0.88):
        body.box((0.06, 1.9, 0.5), matrix=trs((x, 1.1, frame_z + 0.4)), mat=BODY, bevel=0.02)
    body.box((1.8, 0.06, 0.5), matrix=trs((0.0, 2.05, frame_z + 0.4)), mat=BODY, bevel=0.02)
    body.box((1.6, 0.45, 0.4), matrix=trs((0.0, 0.45, frame_z + 0.4)), mat="paint_worn:signal_red", bevel=0.02)   # toolbox
    for y in (0.3, 1.9):
        kit.beam(body, (-0.88, y, frame_z + 0.65), (-0.88, y, frame_z + 1.45), 0.04, 0.04, kit.DARK, profile="tube")
        kit.beam(body, (0.88, y, frame_z + 0.65), (0.88, y, frame_z + 1.45), 0.04, 0.04, kit.DARK, profile="tube")
        kit.beam(body, (-0.88, y, frame_z + 1.45), (0.88, y, frame_z + 1.45), 0.04, 0.04, kit.DARK, profile="tube")
    for x in (-0.2, 0.2):
        kit.beam(body, (x, 0.3, frame_z + 1.47), (x, 1.9, frame_z + 1.47), 0.04, 0.03, "metal:galvanized")
    # Doors.
    for side, sx in (("L", -1), ("R", 1)):
        hinge = Vector((sx * 0.91, -1.05, frame_z + 0.6))
        name = f"door.{side}"
        ctx.bone(name, tuple(hinge), tuple(hinge + Vector((0.0, 0.0, 0.3))), parent="chassis")
        dg = ctx.geo(name, bone=name)
        dg.box((0.05, 1.05, 0.95), matrix=trs(hinge + Vector((0.0, 0.53, 0.0))), mat=BODY, bevel=0.02)
        ctx.geo(f"door_glass.{side}", bone=name).box((0.02, 0.85, 0.42), matrix=trs(hinge + Vector((sx * 0.01, 0.52, 0.55))),
                                                     mat=kit.GLASS)
        dg.box((0.03, 0.14, 0.03), matrix=trs(hinge + Vector((sx * 0.03, 0.9, 0.1))), mat=kit.CHROME, bevel=0.008)
        det.box((0.05, 0.14, 0.2), matrix=trs((sx * 1.0, -1.05, frame_z + 1.0)), mat=kit.DARK, bevel=0.02)   # mirror
    spin = []
    for name, x, y, steer in (("fl", -0.82, y_front, True), ("fr", 0.82, y_front, True), ("rl", -0.82, y_rear, False),
                              ("rr", 0.82, y_rear, False)):
        spin.append(vc.wheel_rig(ctx, name, (x, y, r), r, tw, -1 if x < 0 else 1, steer=steer, rim_mat="metal:gunmetal"))
    ctx.socket("driver", (-0.4, -0.25, frame_z + 0.6), bone="chassis")
    ctx.socket("passenger", (0.4, -0.25, frame_z + 0.6), bone="chassis")
    ctx.socket("entry", (-1.5, -0.6, 0.0), (0.0, 0.0, -90.0))
    ctx.socket("cargo", (0.0, 1.2, frame_z + 0.2), bone="chassis")
    ctx.col_box((0.0, -0.1, frame_z + 0.3), (1.9, 4.4, 0.8))
    ctx.col_box(tuple(cab_c), (1.85, 1.45, 1.15))
    for x, y in ((-0.82, y_front), (0.82, y_front), (-0.82, y_rear), (0.82, y_rear)):
        ctx.col_cylinder((x, y, r), r, tw, rot=(0, 90, 0))

    speed = 6.0
    T = 2 * math.pi * r * 4 / speed

    def drive(t):
        out = vc.spin_wheels(spin, r, speed * t)
        out["chassis"] = (Vector((0.0, 0.0, 0.008 * math.sin(2 * math.pi * 4 * t / T))), None)
        return out

    def steer(sign):
        def fn(t):
            q = Quaternion((0, 0, 1), sign * math.radians(32) * (0.5 - 0.5 * math.cos(2 * math.pi * t / 2.0)))
            return {"steer_fl": (None, q), "steer_fr": (None, q)}
        return fn

    def door(t):
        u = 0.5 - 0.5 * math.cos(2 * math.pi * t / 2.0)
        return {"door.L": (None, Quaternion((0, 0, 1), math.radians(70) * u)),
                "door.R": (None, Quaternion((0, 0, 1), -math.radians(70) * u))}

    ctx.clip("Idle", 2.0, True, lambda t: {"chassis": (Vector((0.0, 0.0, 0.001 * math.sin(2 * math.pi * 12 * t / 2.0))), None)},
             "Engine idling")
    ctx.clip("Drive", T, True, drive, f"Driving at {speed} m/s (in place)")
    ctx.clip("Steer_Left", 2.0, True, steer(1.0), "Front wheels steer left 32 degrees and back")
    ctx.clip("Steer_Right", 2.0, True, steer(-1.0), "Front wheels steer right 32 degrees and back")
    ctx.clip("Door", 2.0, False, door, "Both doors open 70 degrees and close")
    ctx.metadata["speeds"] = {"drive_mps": speed, "wheel_radius_m": r, "max_steer_deg": 32}
    ctx.metadata["interaction"] = {"driver": "socket_driver", "passenger": "socket_passenger", "entry": "socket_entry",
                                   "cargo": "socket_cargo"}
