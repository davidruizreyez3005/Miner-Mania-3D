"""Vehicle helpers: wheel rigs, cabs and hydraulic linkages.

Wheel bones sit on the wheel axis (spin about the bone-local axle), steering
bones on the king-pin axis, suspension bones above the hub; gameplay code can
drive them procedurally as well as through the baked clips.
"""

import math

from mathutils import Matrix, Quaternion, Vector

from utilities.meshkit import trs

from .. import kit


def wheel_rig(ctx, name, center, radius, width, side, parent="chassis", steer=False, dual=False,
              rim_mat="paint_worn:industrial_yellow", tread=True):
    """Suspension + (steering) + spinning wheel. Returns the spin bone name."""
    c = Vector(center)
    susp = f"susp_{name}"
    ctx.bone(susp, tuple(c + Vector((0.0, 0.0, 0.25))), tuple(c + Vector((0.0, 0.0, 0.5))), parent=parent)
    par = susp
    if steer:
        ctx.bone(f"steer_{name}", tuple(c), tuple(c + Vector((0.0, 0.0, 0.3))), parent=susp)
        par = f"steer_{name}"
    spin = f"wheel_{name}"
    ctx.bone(spin, tuple(c), tuple(c + Vector((side * 0.3, 0.0, 0.0))), parent=par, z_axis=(0, 0, 1))
    tyre = ctx.geo(f"tyre_{name}", bone=spin)
    rim = ctx.geo(f"rim_{name}", bone=spin)
    tread_geo = ctx.geo(f"tread_{name}", bone=spin, max_lod=1)
    offs = [0.0] if not dual else [-width * 0.55, width * 0.55]
    for o in offs:
        kit.wheel(tyre, rim, c + Vector((side * o, 0.0, 0.0)), (side, 0.0, 0.0), radius, width, rim_mat=rim_mat,
                  tread=tread, g_tread=tread_geo)
    return spin


def spin_wheels(bones, radius, distance):
    """Rotation of every wheel bone after rolling ``distance`` metres forward
    (-Y). Forward travel spins wheels about +X by distance/radius."""
    q = Quaternion((1.0, 0.0, 0.0), distance / radius)
    return {b: (None, q) for b in bones}


def cab(g, glass, center, size, mat, roof_mat=None, door_side=-1):
    """Operator cab: pillars, roof, glazing panels (glass geo) and step."""
    cx, cy, cz = center
    sx, sy, sz = size
    g.box((sx, sy, 0.12), matrix=trs((cx, cy, cz - sz / 2 + 0.06)), mat=mat, bevel=0.02)
    g.box((sx + 0.06, sy + 0.08, 0.1), matrix=trs((cx, cy, cz + sz / 2)), mat=roof_mat or mat, bevel=0.03)
    for x in (-sx / 2 + 0.04, sx / 2 - 0.04):
        for y in (-sy / 2 + 0.04, sy / 2 - 0.04):
            g.box((0.08, 0.08, sz - 0.1), matrix=trs((cx + x, cy + y, cz)), mat=mat, bevel=0.01)
    g.box((sx, 0.06, sz * 0.35), matrix=trs((cx, cy + sy / 2 - 0.03, cz - sz * 0.3)), mat=mat, bevel=0.01)   # rear wall
    # Glazing (separate alpha material).
    glass.box((sx - 0.12, 0.02, sz * 0.6), matrix=trs((cx, cy - sy / 2 + 0.03, cz + 0.05), (-8, 0, 0)), mat=kit.GLASS)
    glass.box((sx - 0.12, 0.02, sz * 0.5), matrix=trs((cx, cy + sy / 2 - 0.03, cz + 0.12)), mat=kit.GLASS)
    for x in (-sx / 2 + 0.03, sx / 2 - 0.03):
        glass.box((0.02, sy - 0.12, sz * 0.55), matrix=trs((cx + x, cy, cz + 0.08)), mat=kit.GLASS)
    return Vector((cx, cy, cz - sz / 2 + 0.12))


def seat(g, pos, facing_y=-1.0, mat="leather:leather_black"):
    p = Vector(pos)
    g.box((0.5, 0.5, 0.12), matrix=trs(p), mat=mat, bevel=0.04, segments=2)
    g.box((0.5, 0.12, 0.6), matrix=trs(p + Vector((0.0, -facing_y * 0.25, 0.33)), (-facing_y * 10, 0, 0)), mat=mat,
          bevel=0.04, segments=2)
    g.cylinder(0.06, 0.3, segments=10, matrix=trs(p + Vector((0.0, 0.0, -0.2))), mat=kit.DARK)


def linkage_pose(base, tip0, pivot, angle_axis, angle):
    """Hydraulic cylinder that connects a fixed ``base`` to ``tip0`` on a body
    rotating by ``angle`` about ``pivot``/``angle_axis``: returns the barrel
    rotation and rod extension (armature space) for machine clips."""
    q = Quaternion(Vector(angle_axis), angle)
    rot = Matrix.Translation(Vector(pivot)) @ q.to_matrix().to_4x4() @ Matrix.Translation(-Vector(pivot))
    tip = rot @ Vector(tip0)
    d0 = (Vector(tip0) - Vector(base)).normalized()
    d1 = (tip - Vector(base)).normalized()
    ext = (tip - Vector(base)).length - (Vector(tip0) - Vector(base)).length
    return d0.rotation_difference(d1), d0 * ext
