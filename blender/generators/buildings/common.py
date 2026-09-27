"""Shared building parts: wall frames, corrugated cladding with openings,
windows, hinged and roll-up doors, gable and mono-pitch roofs.

Wall frames: local X runs along the wall, local Y is the outward normal and
local Z is up (X x Y = Z), origin at the wall's start at ground level.
Openings are ``(u0, u1, z0, z1)`` rectangles in that frame.

Door conventions: a hinged door's bone head lies on the hinge axis (the spec's
"door = hinge" origin); positive rotation about +Z swings a leaf that extends
along +u outward. A roll-up door's bone hangs from the drum and scales along
its length, so the curtain retracts into the drum.
"""

import math

from mathutils import Matrix, Quaternion, Vector

from utilities.meshkit import trs

from .. import kit

CLAD = "metal:corrugated"
SLAB = "concrete:concrete"
TRIM = "paint_worn:dark_steel"
FRAME = "paint_worn:machine_blue"


def wall_frame(center, normal, length):
    n = Vector(normal).normalized()
    u = n.cross(Vector((0.0, 0.0, 1.0)))
    o = Vector(center) - u * length / 2
    return Matrix(((u.x, n.x, 0.0, o.x), (u.y, n.y, 0.0, o.y), (u.z, n.z, 1.0, o.z), (0.0, 0.0, 0.0, 1.0)))


def corrugated_sheet(g, matrix, length, height, mat=CLAD, pitch=0.4, depth=0.035, thick=0.012, liner=True):
    """Trapezoidal cladding in local XZ: ribs along Z, the corrugated face
    toward +Y, plus a flat liner ``thick`` behind it facing -Y (the inside).
    Sheet edges are open; trims, flashings and kerbs cover them."""
    n = max(1, int(round(length / pitch)))
    p = length / n
    prof = []
    for k in range(n):
        u = k * p
        prof += [(u, 0.0), (u + 0.15 * p, depth), (u + 0.5 * p, depth), (u + 0.65 * p, 0.0)]
    prof.append((length, 0.0))
    m = len(prof)
    verts = [(u, d, 0.0) for u, d in prof] + [(u, d, height) for u, d in prof]
    faces = [(i, m + i, m + i + 1, i + 1) for i in range(m - 1)]
    g.mesh(verts, faces, matrix=matrix, mat=mat)
    if liner:
        g.mesh([(0.0, -thick, 0.0), (length, -thick, 0.0), (length, -thick, height), (0.0, -thick, height)], [(0, 1, 2, 3)],
               matrix=matrix, mat=mat)


def panels(length, height, openings):
    """Rectangles covering [0, length] x [0, height] minus the openings."""
    ops = sorted(openings)
    rects, u = [], 0.0
    for u0, u1, z0, z1 in ops:
        if u0 > u + 1e-6:
            rects.append((u, u0, 0.0, height))
        if z0 > 1e-6:
            rects.append((u0, u1, 0.0, z0))
        if z1 < height - 1e-6:
            rects.append((u0, u1, z1, height))
        u = u1
    if u < length - 1e-6:
        rects.append((u, length, 0.0, height))
    return rects


def clad_wall(g, center, normal, length, height, openings=(), z0=0.0, mat=CLAD, pitch=0.4):
    F = wall_frame(center, normal, length) @ Matrix.Translation((0.0, 0.0, z0))
    for u0, u1, za, zb in panels(length, height, openings):
        if u1 - u0 > 0.05 and zb - za > 0.05:
            corrugated_sheet(g, F @ Matrix.Translation((u0, 0.0, za)), u1 - u0, zb - za, mat=mat, pitch=pitch)
    return F


def wall_trims(g, F, length, height, mat=TRIM, kerb_mat=SLAB):
    """Eave flashing on top, kerb at the base and corner angles at both ends."""
    g.box((length + 0.1, 0.12, 0.1), matrix=_along(F, F @ Vector((length / 2, 0.02, height + 0.02))), mat=mat, bevel=0.006, segments=1)
    g.box((length, 0.14, 0.18), matrix=_along(F, F @ Vector((length / 2, 0.02, 0.06))), mat=kerb_mat, bevel=0.01, segments=1)
    for u in (0.0, length):
        g.box((0.1, 0.1, height), matrix=_along(F, F @ Vector((u, 0.03, height / 2))), mat=mat, bevel=0.006, segments=1)


def opening_trim(g, F, u0, u1, z0, z1, w=0.08, depth=0.07, mat=TRIM, sill=True):
    for (a, b) in (((u0 - w / 2, z0), (u0 - w / 2, z1 + w)), ((u1 + w / 2, z0), (u1 + w / 2, z1 + w))):
        c = F @ Vector((a[0], 0.02, (a[1] + b[1]) / 2))
        g.box((w, depth, b[1] - a[1]), matrix=_along(F, c), mat=mat, bevel=0.006, segments=1)
    c = F @ Vector(((u0 + u1) / 2, 0.02, z1 + w / 2))
    g.box((u1 - u0 + 2 * w, depth, w), matrix=_along(F, c), mat=mat, bevel=0.006, segments=1)
    if sill and z0 > 0.05:
        c = F @ Vector(((u0 + u1) / 2, 0.04, z0 - w / 2))
        g.box((u1 - u0 + 2 * w, depth + 0.04, w), matrix=_along(F, c), mat=mat, bevel=0.006, segments=1)


def _along(F, c):
    """Frame at point ``c`` with the wall's axes."""
    m = F.to_3x3().to_4x4()
    m.translation = c
    return m


def window(g, glass, F, u0, u1, z0, z1, mullions=1, mat=TRIM):
    opening_trim(g, F, u0, u1, z0, z1, mat=mat)
    c = F @ Vector(((u0 + u1) / 2, -0.01, (z0 + z1) / 2))
    glass.box((u1 - u0, 0.012, z1 - z0), matrix=_along(F, c), mat=kit.GLASS)
    for k in range(1, mullions + 1):
        u = u0 + (u1 - u0) * k / (mullions + 1)
        g.box((0.04, 0.04, z1 - z0), matrix=_along(F, F @ Vector((u, 0.0, (z0 + z1) / 2))), mat=mat, bevel=0.004, segments=1)


def hinged_door(ctx, name, F, u0, u1, z0, z1, mat="paint_worn:machine_green", parent="root"):
    """Door leaf on bone ``name`` hinged at u0; opens outward with +angle about +Z."""
    hinge = F @ Vector((u0 + 0.02, 0.03, z0))
    ctx.bone(name, tuple(hinge), tuple(hinge + Vector((0.0, 0.0, 0.3))), parent=parent)
    g = ctx.geo(name, bone=name)
    w, h = u1 - u0 - 0.03, z1 - z0 - 0.02
    c = F @ Vector((u0 + 0.02 + w / 2, 0.03, z0 + h / 2))
    g.box((w, 0.05, h), matrix=_along(F, c), mat=mat, bevel=0.008, segments=1)
    for zz in (0.3, 0.7):                                                # panels
        pc = F @ Vector((u0 + 0.02 + w / 2, 0.058, z0 + h * zz))
        g.box((w * 0.7, 0.008, h * 0.3), matrix=_along(F, pc), mat=mat, bevel=0.004, segments=1)
    kc = F @ Vector((u1 - 0.12, 0.07, z0 + 1.0))
    g.box((0.14, 0.03, 0.03), matrix=_along(F, kc), mat=kit.CHROME, bevel=0.006, segments=1)
    return hinge


def rollup_door(ctx, name, F, u0, u1, z0, z1, mat="metal:galvanized", housing_mat=TRIM):
    """Roll-up curtain on bone ``name`` (head at the drum, pointing down)."""
    top = F @ Vector(((u0 + u1) / 2, 0.06, z1))
    ctx.bone(name, tuple(top), tuple(top + Vector((0.0, 0.0, -0.5))))
    g = ctx.geo(name, bone=name)
    w, h = u1 - u0, z1 - z0
    slats = max(4, int(h / 0.12))
    for k in range(slats):
        zc = z1 - (k + 0.5) * h / slats
        c = F @ Vector(((u0 + u1) / 2, 0.06, zc))
        g.box((w - 0.02, 0.04, h / slats * 0.96), matrix=_along(F, c), mat=mat, bevel=0.01, segments=1)
    return top


def gable_roof(g, cx, cy, span, length, z_eave, rise, overhang=0.35, mat=CLAD, trim=TRIM):
    """Two corrugated slopes meeting at a ridge along Y."""
    half = span / 2
    theta = math.atan2(rise, half)
    slope = math.hypot(half, rise) + overhang
    for s in (-1, 1):
        # Sheet local: X along the ridge (world Y), Z down the slope, Y the roof normal.
        down = Vector((s * math.cos(theta), 0.0, -math.sin(theta)))
        normal = Vector((s * math.sin(theta), 0.0, math.cos(theta)))
        ridge = Vector((cx, cy, z_eave + rise + 0.02))
        x_axis = normal.cross(down)          # X x Y(normal) = Z(down)
        m = Matrix(((x_axis.x, normal.x, down.x, 0.0), (x_axis.y, normal.y, down.y, 0.0),
                    (x_axis.z, normal.z, down.z, 0.0), (0.0, 0.0, 0.0, 1.0)))
        if x_axis.y < 0:
            start = ridge + Vector((0.0, length / 2 + overhang, 0.0))
        else:
            start = ridge - Vector((0.0, length / 2 + overhang, 0.0))
        m.translation = start
        corrugated_sheet(g, m, length + 2 * overhang, slope, mat=mat)
        # Barge boards along the gable edges.
        for yy in (-length / 2 - overhang, length / 2 + overhang):
            a = Vector((cx, cy + yy, z_eave + rise))
            b = a + down * slope
            kit.beam(g, a, b, 0.2, 0.04, trim, up=(0, 1, 0))
    g.box((0.3, length + 2 * overhang, 0.06), matrix=trs((cx, cy, z_eave + rise + 0.05)), mat=trim, bevel=0.01, segments=1)
    return theta


def mono_roof(g, x0, x1, cy, length, z_low, z_high, overhang=0.35, mat=CLAD, trim=TRIM):
    """Single slope falling from x0 (z_high) to x1 (z_low), ridge along Y."""
    run = x1 - x0
    theta = math.atan2(z_high - z_low, abs(run))
    s = 1 if run > 0 else -1
    down = Vector((s * math.cos(theta), 0.0, -math.sin(theta)))
    normal = Vector((s * math.sin(theta), 0.0, math.cos(theta)))
    x_axis = normal.cross(down)
    m = Matrix(((x_axis.x, normal.x, down.x, 0.0), (x_axis.y, normal.y, down.y, 0.0),
                (x_axis.z, normal.z, down.z, 0.0), (0.0, 0.0, 0.0, 1.0)))
    top = Vector((x0, cy, z_high + 0.02)) - down * overhang
    m.translation = top + Vector((0.0, (-1 if x_axis.y > 0 else 1) * (length / 2 + overhang), 0.0))
    corrugated_sheet(g, m, length + 2 * overhang, math.hypot(run, z_high - z_low) + 2 * overhang, mat=mat)
    for yy in (-length / 2 - overhang, length / 2 + overhang):
        a = top + Vector((0.0, yy, 0.0))
        kit.beam(g, a, a + down * (math.hypot(run, z_high - z_low) + 2 * overhang), 0.2, 0.04, trim, up=(0, 1, 0))
    return theta


def gable_infill(g, F, length, z_eave, rise, mat=CLAD):
    """Triangular gable-end infill above the eave in wall frame F."""
    pts = [(0.0, 0.0), (length, 0.0), (length / 2, rise)]
    m = F @ Matrix.Translation((0.0, 0.0, z_eave)) @ Matrix.Rotation(math.radians(90), 4, "X")
    # Rotation maps outline Y -> wall Z (up) and extrusion Z -> -Y: shift so the sheet sits in the wall plane.
    g.extrude(pts, 0.04, matrix=Matrix.Translation(F.to_3x3() @ Vector((0.0, 0.03, 0.0))) @ m, mat=mat)


def slab(g, cx, cy, sx, sy, h=0.15, mat=SLAB):
    g.box((sx, sy, h), matrix=trs((cx, cy, h / 2)), mat=mat, bevel=0.02, segments=1)


def downpipe(g, top, bottom_z=0.1, r=0.05, mat=TRIM):
    top = Vector(top)
    kit.pipe_run(g, [top, Vector((top.x, top.y, bottom_z + 0.25)), Vector((top.x, top.y, bottom_z)) + Vector((0.0, 0.0, 0.0))],
                 r, mat, flanges=False)


def door_swing(angle_deg, t, T, hold=0.4):
    """Open-hold-close profile over T seconds (smooth), returns a Quaternion."""
    u = t / T
    ramp = (1.0 - hold) / 2
    if u < ramp:
        k = u / ramp
    elif u < ramp + hold:
        k = 1.0
    else:
        k = max(0.0, 1.0 - (u - ramp - hold) / ramp)
    k = 0.5 - 0.5 * math.cos(math.pi * k)
    return Quaternion((0.0, 0.0, 1.0), math.radians(angle_deg) * k), k
