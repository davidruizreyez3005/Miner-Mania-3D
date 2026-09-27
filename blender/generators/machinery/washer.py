"""Trommel washer (rotating drum screen).

Mechanics: a motor and pinion drive the girth gear of an inclined perforated
drum riding on four trunnion rollers; spray bars wash the ore as it tumbles
down; fines drop through the screen into the undersize pan, oversize leaves
by the discharge chute. Bones:

* ``drum``     drum + girth gear, spins about its inclined axis
* ``pinion``   drive pinion, spins about its parallel axis

Clips: ``Idle`` (stopped drum, pinion idling) and ``Work`` (drum at 0.5 rev/s).
Origin: base centre; feed at +Y (high end), discharge at -Y.
"""

import math

from mathutils import Vector

from animation.machine_anim import loop_spin
from utilities.meshkit import trs

from .. import kit
from . import common

FRAME = "paint_worn:machine_green"
TILT = math.radians(5.0)
GEAR_TEETH, PINION_TEETH = 48, 12          # 4:1 so both loop on whole turns


def build(ctx):
    L, R = 4.2, 0.85
    z_mid = 1.55
    axis_dir = Vector((0.0, -math.cos(TILT), -math.sin(TILT)))       # downhill toward -Y
    c = Vector((0.0, 0.0, z_mid))
    base = ctx.geo("frame")
    det = ctx.geo("frame_detail", max_lod=1)
    for x in (-1.0, 1.0):
        kit.beam(base, (x, -L / 2 - 0.2, 0.15), (x, L / 2 + 0.2, 0.15), 0.18, 0.3, FRAME, profile="I")
    for y in (-L / 2 + 0.2, L / 2 - 0.2):
        kit.beam(base, (-1.0, y, 0.2), (1.0, y, 0.2), 0.14, 0.2, FRAME, profile="I")
    # Trunnion roller stands (rollers touch the tyre rings).
    tyre_off = [-L / 2 + 0.6, L / 2 - 0.6]
    for s in tyre_off:
        p = c + axis_dir * (-s)
        for x in (-0.62, 0.62):
            roller = p + Vector((x, 0.0, -R * 0.8))
            kit.beam(base, (x * 1.1, roller.y, 0.3), (x * 1.1, roller.y, roller.z - 0.15), 0.18, 0.18, FRAME)
            base.cylinder(0.18, 0.22, segments=20, matrix=kit.axis_frame(roller, axis_dir), mat=kit.DARK, bevel=0.01)
            base.box((0.34, 0.3, 0.12), matrix=trs((x * 1.1, roller.y, roller.z - 0.2)), mat=kit.DARK, bevel=0.01)
    # Drum (rotates about its own axis).
    ctx.bone("drum", tuple(c), tuple(c + axis_dir * 0.5), z_axis=(0, 0, 1))
    drum = ctx.geo("drum", bone="drum")
    ddet = ctx.geo("drum_detail", bone="drum", max_lod=1)
    f = kit.axis_frame(c, axis_dir)
    drum.tube(R, R - 0.03, L, segments=36, matrix=f, mat="metal:galvanized", bevel=0.005)
    for k in range(6):                                          # stiffening rings
        z = -L / 2 + 0.2 + (L - 0.4) * k / 5
        drum.torus(R + 0.02, 0.025, seg_major=36, seg_minor=6, matrix=f @ trs((0.0, 0.0, z)), mat=kit.DARK)
    for k in range(12):                                         # longitudinal bars
        a = 2 * math.pi * k / 12
        drum.box((0.04, 0.05, L - 0.1), matrix=f @ trs((math.cos(a) * (R + 0.015), math.sin(a) * (R + 0.015), 0.0),
                                                      (0, 0, math.degrees(a))), mat=kit.DARK, bevel=0.005)
    for s in tyre_off:                                          # tyre rings riding the rollers
        drum.tube(R + 0.1, R + 0.01, 0.16, segments=36, matrix=f @ trs((0.0, 0.0, s)), mat=kit.STEEL, bevel=0.01)
    gear_z = 0.2
    drum.tube(R + 0.18, R + 0.02, 0.12, segments=48, matrix=f @ trs((0.0, 0.0, gear_z)), mat=kit.DARK, bevel=0.004)
    for k in range(GEAR_TEETH):                                 # girth gear teeth
        a = 2 * math.pi * k / GEAR_TEETH
        ddet.box((0.04, 0.05, 0.12), matrix=f @ trs((math.cos(a) * (R + 0.2), math.sin(a) * (R + 0.2), gear_z),
                                                    (0, 0, math.degrees(a))), mat=kit.DARK, bevel=0.004)
    for k in range(3):                                          # internal lifters seen through the ends
        a = 2 * math.pi * k / 3
        drum.box((0.08, 0.12, L - 0.2), matrix=f @ trs((math.cos(a) * (R - 0.09), math.sin(a) * (R - 0.09), 0.0),
                                                      (0, 0, math.degrees(a))), mat="steel", bevel=0.01)
    # Drive: motor + pinion meshing with the girth gear.
    gear_c = c + axis_dir * gear_z
    pin_c = gear_c + Vector((R + 0.32, 0.0, -0.1))
    ctx.bone("pinion", tuple(pin_c), tuple(pin_c + axis_dir * 0.4), z_axis=(0, 0, 1))
    pg = ctx.geo("pinion", bone="pinion")
    pg.cylinder(0.12, 0.14, segments=16, matrix=kit.axis_frame(pin_c, axis_dir), mat=kit.DARK, bevel=0.008)
    for k in range(PINION_TEETH):
        a = 2 * math.pi * k / PINION_TEETH
        pg.box((0.03, 0.035, 0.14), matrix=kit.axis_frame(pin_c, axis_dir) @ trs((math.cos(a) * 0.13, math.sin(a) * 0.13, 0.0),
                                                                                (0, 0, math.degrees(a))), mat=kit.DARK)
    mot = pin_c + axis_dir * (-0.75)
    kit.motor(base, mot, axis_dir, 0.2, 0.5, mat=FRAME, shaft=False)
    base.box((0.5, 0.5, 0.35), matrix=trs(pin_c + axis_dir * (-0.3) + Vector((0.0, 0.0, -0.3))), mat=kit.DARK, bevel=0.02)
    kit.beam(base, (pin_c.x, pin_c.y + 0.2, 0.3), (pin_c.x, pin_c.y + 0.2, pin_c.z - 0.45), 0.2, 0.2, FRAME)
    # Feed hopper (+Y), spray bar, discharge chute (-Y), undersize pan.
    top = c + axis_dir * (-L / 2 - 0.1)
    kit.hopper(base, (0.0, top.y + 0.35), (1.4, 1.1), (0.5, 0.5), top.z + 1.1, top.z + 0.35, wall=0.03,
               mat="paint_worn:industrial_yellow", rim=0.05, rim_mat=kit.HAZARD)
    for x in (-0.6, 0.6):
        kit.beam(base, (x, top.y + 0.35, 0.3), (x, top.y + 0.35, top.z + 0.4), 0.1, 0.1, FRAME)
    sb0 = c + axis_dir * (-L / 2 + 0.3) + Vector((0.0, 0.0, R + 0.35))
    sb1 = c + axis_dir * (L / 2 - 0.3) + Vector((0.0, 0.0, R + 0.35))
    kit.pipe_run(base, [sb0 + Vector((1.1, 0.0, 0.0)), sb0, sb1], 0.045, "paint_worn:machine_blue", flanges=False)
    for k in range(8):
        n = sb0.lerp(sb1, (k + 0.5) / 8)
        det.cylinder(0.02, 0.06, segments=8, matrix=trs(n + Vector((0.0, 0.0, -0.05))), mat=kit.BOLT)
    for y in (sb0.y, sb1.y):
        kit.beam(base, (1.1, y, 0.3), (1.1, y, sb0.z + 0.05), 0.08, 0.08, FRAME)
    low = c + axis_dir * (L / 2 + 0.05)
    kit.chute(base, low + Vector((0.0, 0.0, -0.4)), low + Vector((0.0, -0.9, -1.0)), 0.9, depth=0.16, mat=kit.DARK)
    base.box((1.5, L - 0.8, 0.12), matrix=trs((0.0, 0.0, 0.42)), mat=kit.DARK, bevel=0.01)
    # Stations: lever console by the drive side, service bolt on the gearbox.
    common.operate_facing(ctx, base, (1.9, -1.3, 0.0), (-1.0, 0.0, 0.0))
    gb = Vector((1.25, 1.75, 0.55))
    base.box((0.3, 0.3, 0.45), matrix=trs(gb), mat=kit.DARK, bevel=0.01)
    common.repair_at(ctx, det, gb + Vector((0.15, 0.0, 0.0)), (1.0, 0.0, 0.0))
    ctx.socket("input", tuple(top + Vector((0.0, 0.35, 1.1))))
    ctx.socket("output", tuple(low + Vector((0.0, -0.9, -1.0))))
    ctx.col_box((0.0, 0.0, 0.2), (2.2, L + 0.4, 0.4))
    ctx.col_cylinder(tuple(c), R + 0.22, L, rot=(90 + math.degrees(TILT), 0, 0))
    ctx.col_box((0.0, top.y + 0.35, top.z + 0.72), (1.4, 1.1, 0.8))

    ratio = GEAR_TEETH // PINION_TEETH

    def work(t):
        T, turns = 4.0, 2
        return {"drum": (None, loop_spin(tuple(axis_dir), turns, t, T)),
                "pinion": (None, loop_spin(tuple(-axis_dir), turns * ratio, t, T))}

    def idle(t):
        return {"pinion": (None, loop_spin(tuple(axis_dir), 2, t, 2.0))}

    ctx.clip("Idle", 2.0, True, idle, "Drum stopped, drive idling")
    ctx.clip("Work", 4.0, True, work, "Drum turning at 0.5 rev/s driven by the pinion")
    ctx.metadata["interaction"] = {"operate": "socket_operate", "repair": "socket_repair", "input": "socket_input",
                                   "output": "socket_output"}
