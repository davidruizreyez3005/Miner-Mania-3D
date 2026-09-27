"""Troughed belt conveyor segment (modular, chains head-to-tail).

Mechanics: a geared motor turns the head pulley, pulling the belt over
troughing idlers; the tail pulley and belt cleats follow. Each cleat is a
rigid part on its own bone moved along the belt loop, so the belt visibly
travels in plain glTF (no texture-transform extension); a clip advances the
cleats a whole number of pitches so the loop is seamless. Bones:

* ``head_pulley`` / ``tail_pulley``  spin about +X
* ``cleat_NN``                        ride the belt loop

Clips: ``Idle`` (stopped), ``Work`` (belt at 0.8 m/s). Origin: ground point
below the centre of the belt (the segment's placement pivot); sockets
``input`` (tail) and ``output`` (head) mark the chaining points.
"""

import math

from mathutils import Vector

from animation.machine_anim import loop_spin
from utilities.meshkit import trs

from .. import kit
from . import common

FRAME = "paint_worn:industrial_yellow"


def build(ctx):
    length = ctx.param("length", 6.0)
    belt_w = 0.8
    h = 0.95                       # belt top height
    r = 0.2                        # pulley radius
    half = length / 2
    frame = ctx.geo("frame")
    det = ctx.geo("frame_detail", max_lod=1)
    # Stringers and legs.
    for x in (-belt_w / 2 - 0.12, belt_w / 2 + 0.12):
        kit.beam(frame, (x, -half + 0.1, h - 0.18), (x, half - 0.1, h - 0.18), 0.1, 0.2, FRAME, profile="C")
    n_legs = max(2, int(round(length / 2.0)) + 1)
    for k in range(n_legs):
        y = -half + 0.4 + (length - 0.8) * k / (n_legs - 1)
        for x in (-belt_w / 2 - 0.12, belt_w / 2 + 0.12):
            kit.beam(frame, (x, y, 0.0), (x, y, h - 0.28), 0.08, 0.08, FRAME)
            frame.box((0.22, 0.22, 0.02), matrix=trs((x, y, 0.01)), mat=kit.DARK, bevel=0.004)
        kit.beam(frame, (-belt_w / 2 - 0.12, y, 0.35), (belt_w / 2 + 0.12, y, 0.35), 0.06, 0.06, FRAME)
    # Belt: static loop around both pulleys (troughing implied by the idlers).
    c_tail = Vector((0.0, half - 0.25, h - r))
    c_head = Vector((0.0, -half + 0.25, h - r))
    loop = kit.LoopPath(c_tail, c_head, r + 0.01, (1.0, 0.0, 0.0))
    belt = ctx.geo("belt")
    path = [loop.point(loop.length * k / 64) for k in range(64)]
    prof = [(-0.006, -belt_w / 2), (0.006, -belt_w / 2), (0.006, belt_w / 2), (-0.006, belt_w / 2)]
    belt.sweep(path, profile=prof, closed_path=True, caps=False, mat="rubber", up_hint=(1, 0, 0))
    # Troughing idlers (top) and return rollers (bottom).
    idl = ctx.geo("idlers")
    n_idl = int((length - 0.8) / 0.6) + 1
    for k in range(n_idl):
        y = -half + 0.4 + (length - 0.8) * k / max(1, n_idl - 1)
        idl.cylinder(0.05, belt_w * 0.5, segments=10, matrix=trs((0.0, y, h - 0.06), (0, 90, 0)), mat=kit.STEEL)
        for s in (-1, 1):
            # Wing rollers tilted 20 degrees to trough the belt.
            idl.cylinder(0.05, belt_w * 0.32, segments=10, matrix=trs((s * belt_w * 0.38, y, h - 0.02), (0, 90 - s * 20, 0)),
                         mat=kit.STEEL)
        kit.beam(det, (-belt_w / 2 - 0.1, y, h - 0.12), (belt_w / 2 + 0.1, y, h - 0.12), 0.04, 0.03, kit.DARK)
        if k % 2 == 0:
            idl.cylinder(0.045, belt_w * 1.02, segments=10, matrix=trs((0.0, y, h - 2 * r - 0.07), (0, 90, 0)), mat=kit.STEEL)
    # Pulleys (spin) with bearings.
    for name, c in (("head_pulley", c_head), ("tail_pulley", c_tail)):
        ctx.bone(name, tuple(c), tuple(c + Vector((0.4, 0.0, 0.0))), z_axis=(0, 0, 1))
        pg = ctx.geo(name, bone=name)
        pg.cylinder(r, belt_w + 0.06, segments=24, matrix=trs(c, (0, 90, 0)), mat=kit.DARK, bevel=0.01)
        pg.cylinder(0.05, belt_w + 0.4, segments=12, matrix=trs(c, (0, 90, 0)), mat=kit.STEEL)
        for x in (-belt_w / 2 - 0.16, belt_w / 2 + 0.16):
            frame.box((0.1, 0.22, 0.16), matrix=trs(c + Vector((x, 0.0, 0.0))), mat=kit.DARK, bevel=0.01)
    # Drive: geared motor on the head end.
    gm = Vector((belt_w / 2 + 0.45, c_head.y, c_head.z))
    frame.box((0.34, 0.36, 0.34), matrix=trs(gm), mat="paint_worn:machine_blue", bevel=0.03)
    kit.motor(frame, gm + Vector((0.0, 0.42, 0.0)), (0, 1, 0), 0.14, 0.34, mat="paint_worn:machine_blue", shaft=False)
    kit.beam(frame, (belt_w / 2 + 0.12, c_head.y, c_head.z - 0.2), (gm.x + 0.2, c_head.y, c_head.z - 0.2), 0.08, 0.08,
             FRAME)
    # Side guards with hazard edge, skirt boards at the tail.
    for x in (-belt_w / 2 - 0.06, belt_w / 2 + 0.06):
        frame.box((0.02, 1.2, 0.18), matrix=trs((x, c_tail.y - 0.5, h + 0.08)), mat=kit.HAZARD, bevel=0.004)
    kit.warning_sign(det, (belt_w / 2 + 0.2, 0.0, h - 0.18), facing=(1, 0, 0), size=0.22)
    # Cleats on bones around the loop.
    pitch_count = int(loop.length / 0.55)
    pitch = loop.length / pitch_count
    cleat_s = []
    for i in range(pitch_count):
        sidx = i * pitch
        f = loop.frame(sidx)
        name = f"cleat_{i:02d}"
        ctx.bone(name, tuple(f.translation), tuple(f.translation + f.to_3x3() @ Vector((0.0, 0.0, 0.15))),
                 z_axis=tuple(f.to_3x3() @ Vector((0.0, 1.0, 0.0))))
        cg = ctx.geo(name, bone=name)
        cg.box((belt_w * 0.9, 0.035, 0.03), matrix=f @ trs((0.0, 0.0, 0.02)), mat="rubber", bevel=0.006)
        cleat_s.append((name, sidx))
    # Stations.
    # Starter box on a post beside the drive: the mechanic's service bolt.
    sb = Vector((gm.x + 0.33, gm.y, 0.62))
    frame.box((0.3, 0.3, 0.36), matrix=trs(sb), mat=kit.DARK, bevel=0.01)
    kit.beam(frame, (sb.x, sb.y, 0.0), (sb.x, sb.y, sb.z - 0.18), 0.06, 0.06, FRAME)
    common.repair_at(ctx, det, sb + Vector((0.15, 0.0, 0.0)), (1.0, 0.0, 0.0))
    ctx.socket("input", (0.0, c_tail.y, h + 0.05))
    ctx.socket("output", (0.0, c_head.y - r - 0.05, h))
    ctx.col_box((0.0, 0.0, h / 2), (belt_w + 0.34, length, h))
    ctx.col_box((gm.x + 0.02, gm.y + 0.2, gm.z), (0.4, 0.8, 0.4))

    speed = 0.8
    T = 4 * pitch / speed          # clip moves the belt exactly four cleat pitches

    # Whole pulley turns per clip keep the loop seamless (pulley surface speed
    # differs from the belt by a few percent, which is invisible).
    turns = max(1, round(speed * T / (2 * math.pi * r)))

    def work(t):
        adv = speed * t
        out = {"head_pulley": (None, loop_spin((1, 0, 0), turns, t, T)),
               "tail_pulley": (None, loop_spin((1, 0, 0), turns, t, T))}
        for name, s0 in cleat_s:
            out[name] = kit.loop_pose(loop, s0, adv)
        return out

    ctx.clip("Idle", 1.0, True, lambda t: {}, "Stopped")
    ctx.clip("Work", T, True, work, f"Belt running at {speed} m/s (cleats advance four pitches per loop)")
    ctx.metadata["interaction"] = {"input": "socket_input", "output": "socket_output", "repair": "socket_repair"}
    ctx.metadata["speeds"] = {"belt_mps": speed}
