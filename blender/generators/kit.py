"""Shared mechanical and structural building blocks.

Used by machinery, vehicles, buildings and environment generators. Every
helper draws into a meshkit ``Geo`` in asset space (metres, +Z up, -Y front)
and follows real construction logic: members meet at joints, fasteners sit on
flanges, belts wrap their pulleys, pistons span their mounts, pads ride their
track loop.
"""

import math

from mathutils import Matrix, Quaternion, Vector

from utilities.meshkit import frame_from_axis, trs

# Common material keys.
FRAME = "paint_worn:dark_steel"
STEEL = "steel"
DARK = "steel_dark"
BOLT = "galvanized"
CHROME = "chrome"
RUBBER = "rubber"
HAZARD = "hazard"
GLASS = "glass"


def vec(v):
    return Vector(v)


def seg_frame(a, b, up=(0.0, 0.0, 1.0)):
    """Frame at ``a`` whose +Z points toward ``b``."""
    return frame_from_axis(Vector(a), Vector(b) - Vector(a), up)


def axis_frame(center, axis, up=(0.0, 0.0, 1.0)):
    return frame_from_axis(Vector(center), Vector(axis), up)


# ------------------------------------------------------------------ structure

def beam(g, a, b, w=0.1, h=None, mat=FRAME, bevel=0.004, profile="box", up=(0.0, 0.0, 1.0)):
    """Structural member from ``a`` to ``b`` (box, I-beam, channel or round tube)."""
    a, b = Vector(a), Vector(b)
    length = (b - a).length
    if length < 1e-6:
        return
    h = h or w
    f = seg_frame(a, b, up)
    if profile == "box":
        g.box((w, h, length), matrix=f @ trs((0.0, 0.0, length / 2)), mat=mat, bevel=bevel, segments=1)
    elif profile == "tube":
        g.cylinder(w / 2, length, segments=12, matrix=f @ trs((0.0, 0.0, length / 2)), mat=mat)
    elif profile in ("I", "C"):
        tf, tw = max(0.006, h * 0.12), max(0.005, w * 0.14)
        x0, x1, y0, y1 = -w / 2, w / 2, -h / 2, h / 2
        if profile == "I":
            pts = [(x0, y0), (x1, y0), (x1, y0 + tf), (tw / 2, y0 + tf), (tw / 2, y1 - tf), (x1, y1 - tf),
                   (x1, y1), (x0, y1), (x0, y1 - tf), (-tw / 2, y1 - tf), (-tw / 2, y0 + tf), (x0, y0 + tf)]
        else:
            pts = [(x0, y0), (x1, y0), (x1, y0 + tf), (x0 + tw, y0 + tf), (x0 + tw, y1 - tf), (x1, y1 - tf),
                   (x1, y1), (x0, y1)]
        g.extrude(pts, length, matrix=f, mat=mat)
    else:
        raise ValueError(f"unknown beam profile {profile}")


def frame_box(g, lo, hi, bar=0.08, mat=FRAME, top=True, bottom=True, verticals=True, profile="box"):
    """Rectangular frame of members along the 12 edges of a box."""
    x0, y0, z0 = lo
    x1, y1, z1 = hi
    h = bar / 2
    corners = [(x0 + h, y0 + h), (x1 - h, y0 + h), (x1 - h, y1 - h), (x0 + h, y1 - h)]
    for z, on in ((z0 + h, bottom), (z1 - h, top)):
        if not on:
            continue
        for i in range(4):
            (ax, ay), (bx, by) = corners[i], corners[(i + 1) % 4]
            beam(g, (ax, ay, z), (bx, by, z), bar, bar, mat, profile=profile)
    if verticals:
        for cx, cy in corners:
            beam(g, (cx, cy, z0), (cx, cy, z1), bar, bar, mat, profile=profile, up=(0.0, 1.0, 0.0))


def plate(g, center, size, mat=FRAME, bevel=0.006, rot=None, segments=1):
    g.box(size, matrix=trs(center, rot), mat=mat, bevel=bevel, segments=segments)


def gusset(g, corner, u, v, size, thick, mat=FRAME):
    """Triangular gusset plate in the plane spanned by unit vectors u, v."""
    c, u, v = Vector(corner), Vector(u).normalized(), Vector(v).normalized()
    n = u.cross(v).normalized()
    pts = [c - n * thick / 2, c + u * size - n * thick / 2, c + v * size - n * thick / 2]
    verts = [tuple(p) for p in pts] + [tuple(p + n * thick) for p in pts]
    faces = [(0, 2, 1), (3, 4, 5), (0, 1, 4, 3), (1, 2, 5, 4), (2, 0, 3, 5)]
    g.mesh(verts, faces, mat=mat, recalc=True)


# ------------------------------------------------------------------ fasteners

def bolt_heads(g, points, normal, r=0.011, h=0.008, mat=BOLT):
    n = Vector(normal).normalized()
    for p in points:
        g.cylinder(r, h, segments=6, matrix=axis_frame(Vector(p) + n * (h / 2), n), mat=mat)


def bolt_circle(g, center, axis, radius, count, r=0.009, h=0.007, mat=BOLT, phase=0.0):
    f = axis_frame(center, axis)
    ax = Vector(axis).normalized()
    pts = [f @ Vector((radius * math.cos(phase + 2 * math.pi * k / count),
                       radius * math.sin(phase + 2 * math.pi * k / count), 0.0)) for k in range(count)]
    bolt_heads(g, pts, ax, r, h, mat)


def bolt_grid(g, center, u, v, nu, nv, du, dv, normal, r=0.009, mat=BOLT):
    c, u, v = Vector(center), Vector(u).normalized(), Vector(v).normalized()
    pts = [c + u * du * (i - (nu - 1) / 2) + v * dv * (j - (nv - 1) / 2) for i in range(nu) for j in range(nv)]
    bolt_heads(g, pts, normal, r, 0.007, mat)


def flange(g, center, axis, r_out, r_in, thick, bolts=8, mat=STEEL, bolt_mat=BOLT):
    g.tube(r_out, r_in, thick, segments=24, matrix=axis_frame(center, axis), mat=mat, bevel=0.002)
    ax = Vector(axis).normalized()
    bolt_circle(g, Vector(center) + ax * thick / 2, ax, (r_out + r_in) / 2, bolts, r=max(0.006, (r_out - r_in) * 0.22),
                mat=bolt_mat)


# ------------------------------------------------------------------ pipes

def _fillet_path(points, radius, steps=5):
    """Polyline with rounded corners (pipe bends)."""
    pts = [Vector(p) for p in points]
    if len(pts) < 3 or radius <= 0:
        return pts
    out = [pts[0]]
    for i in range(1, len(pts) - 1):
        a, b, c = pts[i - 1], pts[i], pts[i + 1]
        d1, d2 = (a - b), (c - b)
        l1, l2 = d1.length, d2.length
        if l1 < 1e-6 or l2 < 1e-6:
            continue
        d1.normalize()
        d2.normalize()
        cosang = max(-1.0, min(1.0, d1.dot(d2)))
        ang = math.acos(cosang)
        if ang > math.pi - 1e-3:
            out.append(b)
            continue
        t = min(radius / math.tan(ang / 2), 0.45 * l1, 0.45 * l2)
        p0, p1 = b + d1 * t, b + d2 * t
        for k in range(steps + 1):
            s = k / steps
            q = (p0 * (1 - s) + b * s) * (1 - s) + (b * (1 - s) + p1 * s) * s     # quadratic Bezier
            out.append(q)
    out.append(pts[-1])
    return out


def pipe_run(g, points, r, mat=STEEL, bend=None, flanges=True, flange_mat=None, segments=12):
    path = _fillet_path(points, bend if bend is not None else r * 3.0)
    g.sweep(path, radius=r, segments=segments, mat=mat)
    if flanges:
        pts = [Vector(p) for p in points]
        for end, nxt in ((pts[0], pts[1]), (pts[-1], pts[-2])):
            ax = (end - nxt).normalized()
            flange(g, end - ax * 0.012, ax, r * 1.7, r * 0.95, 0.024, bolts=6, mat=flange_mat or mat)


def valve_wheel(g, center, axis, r=0.12, mat="paint:signal_red"):
    f = axis_frame(center, axis)
    g.torus(r, r * 0.12, seg_major=20, seg_minor=6, matrix=f, mat=mat)
    for k in range(3):
        a = k * math.pi / 3
        spoke = Vector((math.cos(a), math.sin(a), 0.0))
        g.cylinder(r * 0.07, 2 * r, segments=6, matrix=f @ frame_from_axis((0.0, 0.0, 0.0), spoke), mat=mat)
    g.cylinder(r * 0.2, r * 0.3, segments=10, matrix=f, mat=mat)


# ------------------------------------------------------------------ power transmission

def motor(g, center, axis, r, length, mat="paint:machine_blue", fins=14, shaft=True):
    """Electric motor: finned body, end bells, terminal box, shaft stub."""
    f = axis_frame(center, axis)
    ax = Vector(axis).normalized()
    g.cylinder(r, length, segments=24, matrix=f, mat=mat, bevel=0.01)
    for k in range(fins):
        a = 2 * math.pi * k / fins
        g.box((0.012, r * 0.18, length * 0.8), matrix=f @ trs((math.cos(a) * r, math.sin(a) * r, 0.0), (0, 0, math.degrees(a))),
              mat=mat, bevel=0.002)
    for s in (-1, 1):
        g.cylinder(r * 0.85, 0.03, segments=24, matrix=f @ trs((0, 0, s * (length / 2 + 0.012))), mat=DARK,
                   bevel=0.006)
    g.box((r * 0.6, r * 0.5, r * 0.45), matrix=f @ trs((0.0, r * 1.05, 0.0)), mat=mat, bevel=0.01)
    if shaft:
        g.cylinder(r * 0.16, r * 0.8, segments=12, matrix=f @ trs((0, 0, length / 2 + r * 0.4)), mat=STEEL)
    return Vector(center) + ax * (length / 2 + r * 0.6)


def pulley(g, center, axis, r, width, mat=DARK, grooves=2):
    f = axis_frame(center, axis)
    prof = [(0.0, -width / 2), (r, -width / 2)]
    for k in range(grooves):
        z0 = -width / 2 + width * (k + 0.2) / grooves
        z1 = -width / 2 + width * (k + 0.8) / grooves
        prof += [(r, z0), (r * 0.9, (z0 + z1) / 2), (r, z1)]
    prof += [(r, width / 2), (0.0, width / 2)]
    g.lathe(prof, segments=24, matrix=f, mat=mat)
    g.cylinder(r * 0.28, width * 1.3, segments=12, matrix=f, mat=STEEL)


def belt_loop(c1, r1, c2, r2, axis, steps=10):
    """Closed path of an open belt around two pulleys (plane normal ``axis``)."""
    c1, c2, ax = Vector(c1), Vector(c2), Vector(axis).normalized()
    d = c2 - c1
    L = d.length
    u = d.normalized()
    w = ax.cross(u).normalized()
    beta = math.asin(max(-1.0, min(1.0, (r1 - r2) / L)))
    pts = []
    # Arc around pulley 2 then pulley 1 (counter-clockwise about ax).
    a0 = -math.pi / 2 + beta
    for k in range(steps + 1):
        a = a0 + (math.pi - 2 * beta) * k / steps
        pts.append(c2 + (u * math.cos(a) + w * math.sin(a)) * r2)
    a0 = math.pi / 2 + beta
    for k in range(steps + 1):
        a = a0 + (math.pi + 2 * beta) * k / steps
        pts.append(c1 + (u * math.cos(a) + w * math.sin(a)) * r1)
    return pts


def belt(g, c1, r1, c2, r2, axis, width=0.05, thick=0.012, mat=RUBBER):
    path = belt_loop(c1, r1 + thick / 2, c2, r2 + thick / 2, axis)
    prof = [(-thick / 2, -width / 2), (thick / 2, -width / 2), (thick / 2, width / 2), (-thick / 2, width / 2)]
    g.sweep(path, profile=prof, closed_path=True, caps=False, mat=mat, up_hint=tuple(axis))


def hydraulic(g_body, g_rod, base, tip, r, body_ratio=0.55, body_mat="paint:industrial_yellow", rod_mat=CHROME):
    """Hydraulic cylinder: barrel from ``base`` toward ``tip``, chrome rod to ``tip``."""
    base, tip = Vector(base), Vector(tip)
    L = (tip - base).length
    ax = (tip - base).normalized()
    bl = L * body_ratio
    f = axis_frame(base, ax)
    g_body.cylinder(r, bl, segments=16, matrix=f @ trs((0, 0, bl / 2)), mat=body_mat, bevel=0.006)
    g_body.cylinder(r * 1.15, 0.03, segments=16, matrix=f @ trs((0, 0, bl - 0.015)), mat=DARK, bevel=0.004)
    g_body.cylinder(r * 0.8, r * 1.8, segments=12, matrix=f @ trs((0, 0, 0.0)) @ trs(rot=(0, 90, 0)), mat=DARK)
    rod_len = L - bl + 0.15 * L
    g_rod.cylinder(r * 0.45, rod_len, segments=12, matrix=axis_frame(tip - ax * rod_len / 2, ax), mat=rod_mat)
    g_rod.cylinder(r * 0.7, r * 1.6, segments=12, matrix=axis_frame(tip, ax) @ trs(rot=(0, 90, 0)), mat=DARK)


# ------------------------------------------------------------------ bulk handling

def hopper(g, center, top, bottom, z_top, z_bottom, wall=0.02, mat=FRAME, rim=0.04, rim_mat=None):
    """Tapered open-top bin: rectangular ``top``/``bottom`` sizes (x, y)."""
    cx, cy = center[0], center[1]

    def ring(sx, sy, z, inset=0.0):
        hx, hy = sx / 2 - inset, sy / 2 - inset
        return [(cx - hx, cy - hy, z), (cx + hx, cy - hy, z), (cx + hx, cy + hy, z), (cx - hx, cy + hy, z)]
    ot, ob = ring(top[0], top[1], z_top), ring(bottom[0], bottom[1], z_bottom)
    it, ib = ring(top[0], top[1], z_top, wall), ring(bottom[0], bottom[1], z_bottom + wall, wall)
    verts = ot + ob + it + ib
    faces = []
    for i in range(4):
        j = (i + 1) % 4
        faces.append((i, j, 4 + j, 4 + i))                 # outer wall
        faces.append((8 + j, 8 + i, 12 + i, 12 + j))       # inner wall
        faces.append((i, 8 + i, 8 + j, j))                 # rim top
    faces.append((4, 5, 6, 7)[::-1])                       # outer bottom
    faces.append((12, 13, 14, 15))                         # inner floor
    g.mesh(verts, faces, mat=mat, recalc=True)
    if rim:
        for i in range(4):
            a, b = Vector(ot[i]), Vector(ot[(i + 1) % 4])
            beam(g, a + Vector((0, 0, rim / 2)), b + Vector((0, 0, rim / 2)), rim, rim, rim_mat or mat)


def chute(g, a, b, width, depth=0.12, wall=0.015, mat=FRAME):
    """Open U-channel from a to b (material flows along it)."""
    a, b = Vector(a), Vector(b)
    L = (b - a).length
    f = seg_frame(a, b, (0, 0, 1))
    w, d = width / 2, depth
    pts = [(-w, 0.0), (w, 0.0), (w, d), (w - wall, d), (w - wall, wall), (-w + wall, wall), (-w + wall, d), (-w, d)]
    # Channel profile in the frame's XY: X across, Y up.
    g.extrude(pts, L, matrix=f @ trs((0.0, -d * 0.5, 0.0)), mat=mat)


# ------------------------------------------------------------------ access

def ladder(g, base, height, width=0.45, mat="paint:industrial_yellow", facing=(0.0, -1.0, 0.0), cage=False):
    base = Vector(base)
    fwd = Vector(facing).normalized()
    side = Vector((0.0, 0.0, 1.0)).cross(fwd).normalized()
    for s in (-1, 1):
        p = base + side * (s * width / 2)
        beam(g, p, p + Vector((0, 0, height)), 0.05, 0.02, mat, bevel=0.004, up=tuple(fwd))
    n = max(2, int(height / 0.3))
    for k in range(1, n + 1):
        z = height * k / (n + 1)
        beam(g, base + side * (-width / 2) + Vector((0, 0, z)), base + side * (width / 2) + Vector((0, 0, z)), 0.024,
             0.024, mat, profile="tube")
    if cage and height > 2.4:
        for z in [2.2 + 0.6 * k for k in range(int((height - 2.2) / 0.6) + 1)]:
            c = base + fwd * 0.38 + Vector((0, 0, z))
            g.torus(0.36, 0.012, seg_major=16, seg_minor=5, matrix=trs(c), mat=mat)


def railing(g, points, height=1.05, mat="paint:industrial_yellow", post_spacing=1.2, toe=True):
    pts = [Vector(p) for p in points]
    for a, b in zip(pts, pts[1:]):
        L = (b - a).length
        n = max(1, int(math.ceil(L / post_spacing)))
        for k in range(n + (1 if b is pts[-1] else 0)):
            p = a.lerp(b, k / n)
            beam(g, p, p + Vector((0, 0, height)), 0.04, 0.04, mat, profile="tube")
        for z in (height, height * 0.5):
            beam(g, a + Vector((0, 0, z)), b + Vector((0, 0, z)), 0.036, 0.036, mat, profile="tube")
        if toe:
            beam(g, a + Vector((0, 0, 0.05)), b + Vector((0, 0, 0.05)), 0.01, 0.1, mat, bevel=0.002)


def deck(g, center, size, mat="metal:galvanized", edge_mat=HAZARD, thickness=0.05):
    cx, cy, cz = center
    sx, sy = size
    g.box((sx, sy, thickness), matrix=trs((cx, cy, cz - thickness / 2)), mat=mat, bevel=0.004, segments=1)
    for dx, dy, lx, ly in ((0, -sy / 2, sx, 0.05), (0, sy / 2, sx, 0.05), (-sx / 2, 0, 0.05, sy), (sx / 2, 0, 0.05, sy)):
        g.box((lx + 0.002, ly + 0.002, thickness + 0.006), matrix=trs((cx + dx, cy + dy, cz - thickness / 2)),
              mat=edge_mat, bevel=0.002, segments=1)


# ------------------------------------------------------------------ controls / lights

def control_panel(g, center, facing=(0.0, -1.0, 0.0), size=(0.55, 0.16, 0.42), mat="paint:cream_paint"):
    """Cabinet with indicator lamps, push buttons, gauge and a main switch."""
    c = Vector(center)
    fwd = Vector(facing).normalized()
    yaw = math.degrees(math.atan2(fwd.x, -fwd.y))
    f = trs(c, (0, 0, yaw))
    sx, sy, sz = size
    g.box(size, matrix=f, mat=mat, bevel=0.012, segments=2)
    front = -sy / 2 - 0.004
    for i, col in enumerate(("emit:emissive_green", "emit:emissive_amber", "emit:emissive_red")):
        x = -sx * 0.3 + i * sx * 0.3
        g.cylinder(0.022, 0.02, segments=12, matrix=f @ trs((x, front, sz * 0.3), (90, 0, 0)), mat=col)
        g.cylinder(0.026, 0.012, segments=12, matrix=f @ trs((x, front + 0.008, sz * 0.3), (90, 0, 0)), mat=DARK)
    for i in range(3):
        x = -sx * 0.3 + i * sx * 0.3
        g.cylinder(0.018, 0.024, segments=10, matrix=f @ trs((x, front, 0.0), (90, 0, 0)), mat="plastic:plastic_black")
    g.cylinder(0.06, 0.02, segments=20, matrix=f @ trs((0.0, front, -sz * 0.28), (90, 0, 0)), mat="plastic:plastic_white")
    g.box((0.004, 0.006, 0.05), matrix=f @ trs((0.0, front - 0.012, -sz * 0.28 + 0.015), (0, 0, 0)), mat="paint:signal_red",
          bevel=0.0)
    return f


def lamp(g, center, direction, r=0.07, emit="emit:emissive_warm", housing="paint:dark_steel"):
    d = Vector(direction).normalized()
    f = axis_frame(center, d)
    g.cylinder(r, r * 1.1, segments=16, matrix=f @ trs((0, 0, -r * 0.55)), mat=housing, bevel=0.006)
    g.cylinder(r * 0.82, 0.012, segments=16, matrix=f @ trs((0, 0, 0.006)), mat=emit)
    g.torus(r * 0.9, r * 0.1, seg_major=16, seg_minor=5, matrix=f @ trs((0, 0, 0.01)), mat=DARK)


def beacon(g, center, r=0.06, emit="emit:emissive_amber"):
    c = Vector(center)
    g.cylinder(r * 1.2, 0.04, segments=16, matrix=trs(c + Vector((0, 0, 0.02))), mat=DARK, bevel=0.005)
    g.cylinder(r, r * 1.6, segments=16, matrix=trs(c + Vector((0, 0, 0.04 + r * 0.8))), mat=emit)
    g.sphere(r, segments=16, rings=6, matrix=trs(c + Vector((0, 0, 0.04 + r * 1.6))), mat=emit, scale=(1, 1, 0.5))


def warning_sign(g, center, facing=(0.0, -1.0, 0.0), size=0.3, mat="paint_clean:sign_yellow"):
    fwd = Vector(facing).normalized()
    yaw = math.degrees(math.atan2(fwd.x, -fwd.y))
    f = trs(center, (0, 0, yaw))
    h = size * 0.866
    pts = [(-size / 2, -h / 3), (size / 2, -h / 3), (0.0, 2 * h / 3)]
    g.extrude(pts, 0.006, matrix=f @ trs(rot=(90, 0, 0)), mat=mat)
    g.box((size * 0.08, 0.004, size * 0.3), matrix=f @ trs((0, -0.006, 0.02)), mat="plastic:plastic_black", bevel=0.0)


# ------------------------------------------------------------------ wheels / tracks

def wheel(g_tire, g_rim, center, axis, r, width, rim_ratio=0.62, rim_mat="paint:industrial_yellow", lugs=10,
          tread=True):
    """Tyre with tread blocks plus a dished rim with lug nuts."""
    f = axis_frame(center, axis)
    w = width / 2
    prof = [(r * rim_ratio, -w), (r * 0.94, -w), (r, -w * 0.7), (r, w * 0.7), (r * 0.94, w), (r * rim_ratio, w)]
    g_tire.lathe(prof, segments=32, matrix=f, mat=RUBBER, caps=False, closed_loop=True)
    if tread:
        n = max(12, int(2 * math.pi * r / 0.09))
        for k in range(n):
            a = 2 * math.pi * k / n
            for s in (-1, 1):
                # Block: radial height, tangential length, axial width; skewed for a chevron tread.
                g_tire.box((r * 0.06, r * 0.075, width * 0.42),
                           matrix=f @ trs((math.cos(a) * r, math.sin(a) * r, s * w * 0.45), (0, 0, math.degrees(a)))
                           @ trs(rot=(s * 14, 0, 0)), mat=RUBBER, bevel=0.004)
    rr = r * rim_ratio
    g_rim.lathe([(0.0, -w * 0.5), (rr * 0.5, -w * 0.5), (rr * 0.55, -w * 0.2), (rr, -w * 0.8), (rr, w * 0.8),
                 (rr * 0.55, w * 0.4), (0.0, w * 0.4)], segments=28, matrix=f, mat=rim_mat)
    g_rim.cylinder(rr * 0.28, w * 1.1, segments=16, matrix=f, mat=DARK, bevel=0.01)
    ax = Vector(axis).normalized()
    bolt_circle(g_rim, Vector(center) + ax * (w * 0.42), ax, rr * 0.38, lugs, r=max(0.008, rr * 0.035), mat=BOLT)


class LoopPath:
    """Stadium loop (two sprockets of radius r, centres c1/c2) in a plane.

    ``point(s)``/``tangent(s)`` by arc length along the loop, used for track
    pads and conveyor cleats that are rigged to their own bones and animated
    around the loop (seamless when a clip moves them a whole pitch count).
    """

    def __init__(self, c1, c2, r, normal):
        self.c1, self.c2, self.r = Vector(c1), Vector(c2), r
        self.n = Vector(normal).normalized()
        self.u = (self.c2 - self.c1).normalized()
        self.w = self.n.cross(self.u).normalized()          # "up" side of the loop
        self.L = (self.c2 - self.c1).length
        self.length = 2 * self.L + 2 * math.pi * r

    def _arc(self, c, a):
        # Point at angle a on a sprocket; the loop runs with decreasing a, so
        # the travel direction is d/ds = u sin(a) - w cos(a).
        u, w = self.u, self.w
        return c + (u * math.cos(a) + w * math.sin(a)) * self.r, u * math.sin(a) - w * math.cos(a)

    def _local(self, s):
        s %= self.length
        L, r = self.L, self.r
        if s < L:                                            # top run c1 -> c2
            return self.c1 + self.u * s + self.w * r, self.u
        s -= L
        if s < math.pi * r:                                  # around c2 (top -> bottom)
            return self._arc(self.c2, math.pi / 2 - s / r)
        s -= math.pi * r
        if s < L:                                            # bottom run c2 -> c1
            return self.c2 - self.u * s - self.w * r, -self.u
        s -= L
        return self._arc(self.c1, -math.pi / 2 - s / r)      # around c1 (bottom -> top)

    def point(self, s):
        return self._local(s)[0]

    def tangent(self, s):
        return self._local(s)[1].normalized()

    def frame(self, s):
        """Frame: +Y along the travel direction, +Z outward from the loop."""
        p, t = self._local(s)
        t = t.normalized()
        out = t.cross(self.n).normalized()
        if out.dot(p - (self.c1 + self.c2) / 2) < 0:
            out = -out
        x = t.cross(out)
        m = Matrix((x, t, out)).transposed().to_4x4()
        m.translation = p
        return m


def loop_pose(path, s_rest, advance):
    """(location offset, rotation) moving a part rigged at ``s_rest`` by
    ``advance`` metres along ``path`` (armature-space, about the bone head)."""
    f0 = path.frame(s_rest)
    f1 = path.frame(s_rest + advance)
    q = (f1.to_3x3() @ f0.to_3x3().inverted()).to_quaternion()
    return f1.translation - f0.translation, q
