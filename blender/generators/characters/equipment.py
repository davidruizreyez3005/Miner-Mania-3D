"""Wearable equipment attached to standard sockets.

Items are authored in character space around their socket point (up = +Z,
front = -Y), so exported equipment GLBs attach to the matching socket bone in
Godot with an identity transform.
"""

import math

from mathutils import Matrix, Vector

from utilities.meshkit import frame_from_axis, trs

BACK_SOCKET = Vector((0.0, 0.135, 1.33))
WAIST_SOCKET = Vector((-0.165, 0.035, 1.0))


def backpack(g, d, color_key="canvas_tarp"):
    key = f"fabric:{color_key}"
    c = BACK_SOCKET + Vector((0.0, 0.075, -0.03))
    g.box((0.3, 0.14, 0.38), matrix=trs(c), mat=key, bevel=0.04, segments=2)
    g.box((0.31, 0.1, 0.12), matrix=trs(c + Vector((0, 0.03, 0.15)), (12, 0, 0)), mat=key, bevel=0.03, segments=2)
    g.box((0.22, 0.05, 0.16), matrix=trs(c + Vector((0, 0.085, -0.07))), mat=key, bevel=0.02, segments=2)
    for sx in (-0.09, 0.09):
        d.box((0.035, 0.012, 0.03), matrix=trs(c + Vector((sx, 0.075, 0.06))), mat="plastic:plastic_black",
              bevel=0.004, segments=1)
    roll = frame_from_axis(c + Vector((0, 0.01, 0.24)), (1, 0, 0))
    g.cylinder(0.045, 0.32, segments=12, matrix=roll, mat="fabric:olive", bevel=0.01)


def pouch(g, d, leather="leather:leather_brown"):
    c = WAIST_SOCKET + Vector((-0.02, 0.0, -0.02))
    g.box((0.05, 0.12, 0.13), matrix=trs(c), mat=leather, bevel=0.012, segments=2)
    g.box((0.056, 0.13, 0.04), matrix=trs(c + Vector((-0.003, 0, 0.06))), mat=leather, bevel=0.01, segments=1)
    d.cylinder(0.008, 0.01, segments=8, matrix=frame_from_axis(c + Vector((-0.032, 0, 0.05)), (-1, 0, 0)),
               mat="brass", bevel=0.002)


def radio_holster(g, d):
    c = WAIST_SOCKET + Vector((-0.015, 0.02, 0.0))
    g.box((0.04, 0.065, 0.13), matrix=trs(c), mat="plastic:plastic_black", bevel=0.01, segments=2)
    g.box((0.006, 0.05, 0.04), matrix=trs(c + Vector((-0.022, 0, 0.03))), mat="emit_soft:emissive_green",
          bevel=0.001, segments=1)
    d.cylinder(0.005, 0.11, segments=6, matrix=trs(c + Vector((0, 0.02, 0.12))), mat="rubber", radius_top=0.003)


def tool_belt_pouches(g, d, leather="leather:leather_tan"):
    c = WAIST_SOCKET + Vector((-0.015, -0.01, -0.03))
    g.box((0.055, 0.16, 0.14), matrix=trs(c), mat=leather, bevel=0.012, segments=2)
    g.box((0.07, 0.1, 0.1), matrix=trs(c + Vector((-0.012, -0.03, -0.01))), mat=leather, bevel=0.012, segments=2)
    d.cylinder(0.008, 0.1, segments=8, matrix=trs(c + Vector((-0.02, 0.04, 0.09)), (10, 0, 0)), mat=
               "wood:wood_light")
    d.box((0.018, 0.028, 0.06), matrix=trs(c + Vector((-0.02, -0.05, 0.08))), mat="paint:signal_red", bevel=0.004,
          segments=1)


def glasses(g):
    """Safety glasses (rigid on the head)."""
    for s in (1.0, -1.0):
        c = Vector((s * 0.034, -0.093, 1.651))
        rim = []
        for i in range(10):
            a = 2 * math.pi * i / 10
            rim.append(c + Vector((0.021 * math.cos(a), 0.0, 0.014 * math.sin(a))))
        g.sweep(rim, radius=0.0022, segments=5, mat="plastic:plastic_black", closed_path=True, caps=False,
                up_hint=(0, -1, 0))
        g.cylinder(0.019, 0.002, segments=12, matrix=frame_from_axis(c, (0, -1, 0)) @ Matrix.Diagonal((1, 0.68, 1, 1)),
                   mat="glass")
        g.sweep([c + Vector((s * 0.021, 0, 0.004)), Vector((s * 0.078, -0.03, 1.656)), Vector((s * 0.08, 0.03, 1.646))],
                radius=0.002, segments=5, mat="plastic:plastic_black", up_hint=(0, 0, 1))
    g.sweep([Vector((0.013, -0.094, 1.654)), Vector((0.0, -0.097, 1.657)), Vector((-0.013, -0.094, 1.654))],
            radius=0.002, segments=5, mat="plastic:plastic_black", up_hint=(0, 0, 1))


BACK_ITEMS = {"backpack": backpack}
WAIST_ITEMS = {"pouch": pouch, "radio": radio_holster, "tool_belt": tool_belt_pouches}
