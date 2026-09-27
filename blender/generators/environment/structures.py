"""Man-made modular environment pieces: mine supports, tunnel segments, rail
track, pipework, cables, signs, lamps, fences, barriers, containers,
scaffolding, catwalks and a water tank.

Modular pieces expose ``socket_start``/``socket_end`` (or tile sockets) at
their chaining points so level tools can snap them; dimensions follow real
standards (600 mm mine gauge, 20 ft ISO container, 1.1 m handrails).
"""

import math

from mathutils import Matrix, Vector, noise

from utilities.meshkit import frame_from_axis, trs

from .. import kit

TIMBER = "wood_weathered:wood_weathered"
YELLOW = "paint_worn:industrial_yellow"


def build(ctx):
    kind = ctx.param("kind")
    fn = globals().get(f"_{kind}")
    if fn is None:
        raise ValueError(f"unknown structure kind {kind!r}")
    fn(ctx)


# ------------------------------------------------------------------ supports / tunnel

def _support_wood(ctx):
    """Mine timber set: splayed posts, cap beam, wedges, lagging boards."""
    w, h = 3.0, 2.7
    g = ctx.geo("timber")
    det = ctx.geo("timber_detail", max_lod=1)
    for s in (-1, 1):
        kit.beam(g, (s * (w / 2 - 0.05), 0.0, 0.0), (s * (w / 2 - 0.25), 0.0, h - 0.25), 0.24, 0.24, TIMBER, bevel=0.01)
        g.box((0.4, 0.4, 0.06), matrix=trs((s * (w / 2 - 0.05), 0.0, 0.03)), mat="concrete:concrete", bevel=0.01)
    kit.beam(g, (-w / 2, 0.0, h - 0.13), (w / 2, 0.0, h - 0.13), 0.26, 0.26, TIMBER, bevel=0.01)
    for x in (-0.9, -0.3, 0.3, 0.9):
        det.box((0.16, 0.26, 0.08), matrix=trs((x, 0.0, h + 0.04)), mat=TIMBER, bevel=0.008)          # wedges
    for k in range(5):                                        # lagging, centred: sets chain every 1 m
        g.box((0.18, 1.0, 0.04), matrix=trs((-1.0 + 0.5 * k, 0.0, h + 0.1)), mat=TIMBER, bevel=0.005)
    for s in (-1, 1):
        kit.bolt_heads(det, [(s * (w / 2 - 0.2), -0.13, h - 0.13)], (0, -1, 0), r=0.018)
    ctx.col_box((-(w / 2 - 0.15), 0.0, h / 2), (0.3, 0.3, h))
    ctx.col_box(((w / 2 - 0.15), 0.0, h / 2), (0.3, 0.3, h))
    ctx.col_box((0.0, 0.0, h - 0.02), (w, 1.0, 0.3))
    ctx.socket("start", (0.0, -0.5, 0.0))
    ctx.socket("end", (0.0, 0.5, 0.0))


def _arch_points(w, h, n=14):
    leg = h - w / 2
    pts = [Vector((-w / 2, 0.0, 0.0)), Vector((-w / 2, 0.0, leg))]
    for k in range(1, n):
        a = math.pi - math.pi * k / n
        pts.append(Vector((math.cos(a) * w / 2, 0.0, leg + math.sin(a) * w / 2)))
    pts += [Vector((w / 2, 0.0, leg)), Vector((w / 2, 0.0, 0.0))]
    return pts


def _col_arch(ctx, pts, thick, depth, y=0.0, pieces=6):
    """Collision for an arch polyline in the XZ plane: legs plus a few
    oriented boxes along the curve (a hull would fill the opening)."""
    legs = [(pts[0], pts[1]), (pts[-2], pts[-1])]
    crown = pts[1:-1]
    step = max(1, (len(crown) - 1) // pieces)
    idx = list(range(0, len(crown) - 1, step)) + [len(crown) - 1]
    segs = legs + [(crown[a], crown[b]) for a, b in zip(idx, idx[1:])]
    for a, b in segs:
        d = b - a
        ctx.col_box(((a.x + b.x) / 2, y, (a.z + b.z) / 2), (thick, depth, d.length + thick * 0.5),
                    rot=(0.0, math.degrees(math.atan2(d.x, d.z)), 0.0))


def _support_steel(ctx):
    """Steel arch set (TH profile) on base plates with tie rods."""
    w, h = 3.4, 3.2
    g = ctx.geo("arch")
    det = ctx.geo("arch_detail", max_lod=1)
    pts = _arch_points(w, h)
    prof = [(-0.06, -0.07), (0.06, -0.07), (0.06, -0.05), (0.015, -0.05), (0.015, 0.05), (0.06, 0.05), (0.06, 0.07),
            (-0.06, 0.07), (-0.06, 0.05), (-0.015, 0.05), (-0.015, -0.05), (-0.06, -0.05)]
    # Three arch segments joined under clamps (as real TH sets are built):
    # shorter UV islands than one continuous sweep.
    joints = (4, len(pts) - 5)
    for a, b in ((0, joints[0] + 1), (joints[0], joints[1] + 1), (joints[1], len(pts))):
        g.sweep(pts[a:b], profile=prof, mat="paint_worn:machine_green", up_hint=(0, 1, 0), caps=False)
    for s in (-1, 1):
        g.box((0.3, 0.3, 0.03), matrix=trs((s * w / 2, 0.0, 0.015)), mat=kit.DARK, bevel=0.005)
        kit.beam(det, (s * w / 2, 0.0, 0.8), (s * w / 2, 0.6, 0.8), 0.03, 0.03, kit.STEEL, profile="tube")
        kit.bolt_heads(det, [(s * w / 2 + 0.1, 0.0, 0.035), (s * w / 2 - 0.1, 0.0, 0.035)], (0, 0, 1), r=0.016)
    for k in joints:                                             # clamps over the joints
        t = (pts[k + 1] - pts[k - 1]).normalized()
        g.box((0.2, 0.19, 0.22), matrix=kit.axis_frame(pts[k], t, up=(0, 1, 0)), mat=kit.DARK, bevel=0.01)
        kit.bolt_heads(det, [pts[k] + Vector((0.0, -0.1, 0.0))], (0, -1, 0), r=0.02)
    _col_arch(ctx, pts, 0.16, 0.16)


TUNNEL_W, TUNNEL_H = 3.8, 3.5


def _tunnel(ctx):
    """4 m tunnel segment, chains along Y (sockets ``start``/``end``)."""
    L = 4.0
    tunnel_section(ctx, ctx.geo("shell"), ctx.geo("shell_detail", max_lod=1), ctx.rng.child("tunnel"), L)
    ctx.socket("start", (0.0, -L / 2, 0.0))
    ctx.socket("end", (0.0, L / 2, 0.0))


def tunnel_section(ctx, g, det, rng, L, w=TUNNEL_W, h=TUNNEL_H, y0=0.0):
    """Tunnel segment centred at ``y0``: rough rock shell (inner face displaced
    by noise that fades to zero at both ends, so identical segments chain
    seamlessly), gravel floor, two steel arch sets, wall cables, crown lamp and
    collision that keeps the passage clear. Shared with the mine entrance."""
    ny = max(2, int(round(L / 0.4)))
    off = Vector((rng.uniform(-40, 40), rng.uniform(-40, 40), rng.uniform(-40, 40)))
    prof = _arch_points(w, h, n=20)
    leg = h - w / 2
    n = len(prof)
    verts = []

    def inward(p):
        if p.z <= leg:
            return Vector((-math.copysign(1.0, p.x), 0.0, 0.0))
        return (Vector((0.0, 0.0, leg)) - Vector((p.x, 0.0, p.z))).normalized()

    for iy in range(ny + 1):
        y = -L / 2 + L * iy / ny
        fade = min(1.0, (L / 2 - abs(y)) / 0.6)
        for p in prof:
            q = Vector((p.x, y, p.z))
            amp = 0.1 * fade * min(1.0, p.z / 0.4)
            verts.append(tuple(q + inward(p) * amp * noise.noise(q * 1.3 + off) + Vector((0.0, y0, 0.0))))
    for iy in range(ny + 1):
        y = -L / 2 + L * iy / ny + y0
        verts += [(p.x * 1.18, y, p.z * 1.12) for p in prof]
    inner = lambda iy, j: iy * n + j
    outer = lambda iy, j: (ny + 1) * n + iy * n + j
    faces = []
    for iy in range(ny):
        for j in range(n - 1):
            faces.append((inner(iy, j), inner(iy, j + 1), inner(iy + 1, j + 1), inner(iy + 1, j)))
            faces.append((outer(iy, j), outer(iy + 1, j), outer(iy + 1, j + 1), outer(iy, j + 1)))
        for j in (0, n - 1):                                          # feet
            faces.append((inner(iy, j), inner(iy + 1, j), outer(iy + 1, j), outer(iy, j)))
    for iy in (0, ny):                                                # end rims
        for j in range(n - 1):
            faces.append((inner(iy, j), outer(iy, j), outer(iy, j + 1), inner(iy, j + 1)))
    g.mesh(verts, faces, mat="stone:stone_warm", recalc=True)
    g.box((w + 0.9, L, 0.1), matrix=trs((0.0, y0, -0.05)), mat="gravel:gravel", bevel=0.01)
    count = max(1, int(round(L / 2.0)))                               # one set per 2 m, uniform across chained segments
    sets = [y0 - L / 2 + L * (k + 0.5) / count for k in range(count)]
    for y in sets:
        arch = _arch_points(w - 0.4, h - 0.2, n=14)
        g.sweep([p + Vector((0.0, y, 0.0)) for p in arch], profile=[(-0.05, -0.06), (0.05, -0.06), (0.05, 0.06), (-0.05, 0.06)],
                mat="paint_worn:machine_green", up_hint=(0, 1, 0))
        for s in (-1, 1):
            det.box((0.24, 0.24, 0.02), matrix=trs((s * (w / 2 - 0.2), y, 0.01)), mat=kit.DARK, bevel=0.004)
        det.box((0.1, 0.03, 0.2), matrix=trs((-w / 2 + 0.25, y, 1.76)), mat=kit.DARK, bevel=0.004)     # cable hanger
    kit.pipe_run(det, [(-w / 2 + 0.25, y0 - L / 2, 1.7), (-w / 2 + 0.25, y0 + L / 2, 1.7)], 0.03, "rubber", flanges=False)
    kit.pipe_run(det, [(-w / 2 + 0.25, y0 - L / 2, 1.82), (-w / 2 + 0.25, y0 + L / 2, 1.82)], 0.02, "rubber:hazard_black",
                 flanges=False)
    kit.lamp(det, (0.0, y0, h - 0.3), (0.0, 0.0, -1.0), r=0.09, emit="emit:emissive_warm")
    kit.beam(det, (0.0, y0, h - 0.24), (0.0, y0, h + 0.05), 0.02, 0.02, kit.STEEL, profile="tube")
    ctx.col_box((0.0, y0, -0.05), (w + 0.9, L, 0.1))
    t = 0.2
    _col_arch(ctx, _arch_points(w + 2 * t, h + t, n=16), 2 * t, L, y=y0)   # inner face on the nominal rock face


# ------------------------------------------------------------------ rails

GAUGE = 0.6
RAIL_H = 0.11


def _rail_profile():
    return [(-0.03, 0.0), (0.03, 0.0), (0.03, 0.012), (0.008, 0.02), (0.008, 0.08), (0.02, 0.088), (0.02, RAIL_H),
            (-0.02, RAIL_H), (-0.02, 0.088), (-0.008, 0.08), (-0.008, 0.02), (-0.03, 0.012)]


def _track(ctx, path_fn, length, samples):
    g = ctx.geo("track")
    det = ctx.geo("track_detail", max_lod=1)
    sleeper_z = 0.085                     # sleeper top 0.075 + 10 mm tie plate
    for s in (-1, 1):
        path = [path_fn(t, s * GAUGE / 2) + Vector((0.0, 0.0, sleeper_z)) for t in [k / samples for k in range(samples + 1)]]
        # up_hint -X: profile x -> lateral, profile y -> +Z along a +Y path.
        g.sweep(path, profile=_rail_profile(), mat=kit.STEEL, up_hint=(-1, 0, 0))
    n = max(2, int(length / 0.6))
    for k in range(n):
        t = (k + 0.5) / n
        c = path_fn(t, 0.0)
        a = path_fn(min(1.0, t + 0.01), 0.0) - path_fn(max(0.0, t - 0.01), 0.0)
        yaw = math.degrees(math.atan2(a.y, a.x)) - 90.0
        g.box((1.1, 0.16, 0.08), matrix=trs(c + Vector((0.0, 0.0, 0.035)), (0, 0, yaw)), mat=TIMBER, bevel=0.008)
        for s in (-1, 1):
            det.box((0.18, 0.13, 0.01), matrix=trs(path_fn(t, s * GAUGE / 2) + Vector((0.0, 0.0, sleeper_z - 0.005)), (0, 0, yaw)),
                    mat=kit.DARK)
    return sleeper_z + RAIL_H


def _rail_straight(ctx):
    L = ctx.param("length", 2.0)
    top = _track(ctx, lambda t, off: Vector((off, -L / 2 + L * t, 0.0)), L, 2)
    ctx.col_box((0.0, 0.0, 0.1), (1.1, L, 0.2))
    ctx.socket("start", (0.0, -L / 2, 0.0))
    ctx.socket("end", (0.0, L / 2, 0.0))
    ctx.socket("cart", (0.0, 0.0, top))


def _rail_curve(ctx):
    R, ang = ctx.param("radius", 6.0), math.radians(ctx.param("angle", 22.5))

    def fn(t, off):
        a = ang * t
        rr = R - off
        return Vector((R - rr * math.cos(a), rr * math.sin(a), 0.0)) + Vector((0.0, -R * math.sin(ang) / 2, 0.0))
    top = _track(ctx, fn, R * ang, 12)
    ends = [fn(0.0, 0.0), fn(1.0, 0.0)]
    mid = fn(0.5, 0.0)
    hull = []
    for t, half in ((0.0, 0.34), (0.5, 0.55), (1.0, 0.34)):      # rails only at the ends, sleepers mid-way
        hull += [tuple(fn(t, off) + Vector((0.0, 0.0, dz))) for off in (-half, half) for dz in (0.0, 0.2)]
    ctx.col_hull(hull)
    ctx.socket("start", tuple(ends[0]))
    ctx.socket("end", tuple(ends[1]), (0.0, 0.0, -math.degrees(ang)))
    ctx.socket("cart", tuple(mid + Vector((0.0, 0.0, top))))


def _rail_buffer(ctx):
    """Buffer stop: track end with a braced timber/steel frame and bumper."""
    L = 1.5
    top = _track(ctx, lambda t, off: Vector((off, -L / 2 + L * t, 0.0)), L, 2)
    g = ctx.geo("buffer")
    yb = L / 2 - 0.2
    for s in (-1, 1):
        kit.beam(g, (s * GAUGE / 2, yb, 0.18), (s * GAUGE / 2, yb, 0.75), 0.12, 0.12, "paint_worn:signal_red")
        kit.beam(g, (s * GAUGE / 2, yb + 0.7, 0.05), (s * GAUGE / 2, yb, 0.7), 0.1, 0.1, "paint_worn:signal_red")
    kit.beam(g, (-0.5, yb, 0.62), (0.5, yb, 0.62), 0.2, 0.2, TIMBER)
    g.box((1.0, 0.1, 0.25), matrix=trs((0.0, yb - 0.12, 0.62)), mat=kit.HAZARD, bevel=0.02)
    ctx.col_box((0.0, 0.0, 0.1), (1.1, L, 0.2))
    ctx.col_box((0.0, yb + 0.25, 0.37), (1.0, 0.8, 0.74))
    ctx.socket("start", (0.0, -L / 2, 0.0))
    ctx.socket("cart", (0.0, -0.2, top))


# ------------------------------------------------------------------ pipework / cables

PIPE = "paint_worn:safety_orange"


def _pipe_stand(g, pos, h, r):
    kit.beam(g, (pos[0], pos[1], 0.0), (pos[0], pos[1], h - r - 0.02), 0.1, 0.1, kit.FRAME)
    g.box((0.3, 0.1, 0.03), matrix=trs((pos[0], pos[1], h - r - 0.03)), mat=kit.DARK, bevel=0.005)
    g.box((0.25, 0.25, 0.02), matrix=trs((pos[0], pos[1], 0.01)), mat=kit.DARK, bevel=0.005)


def _pipe_straight(ctx):
    L, r, h = 3.0, 0.14, 0.9
    g = ctx.geo("pipe")
    kit.pipe_run(g, [(0.0, -L / 2, h), (0.0, L / 2, h)], r, PIPE)
    for y in (-L / 2 + 0.5, L / 2 - 0.5):
        _pipe_stand(g, (0.0, y), h, r)
    ctx.col_cylinder((0.0, 0.0, h), r * 1.7, L, rot=(90, 0, 0))
    ctx.col_box((0.0, 0.0, (h - r) / 2), (0.3, L - 0.8, h - r))
    ctx.socket("start", (0.0, -L / 2, h))
    ctx.socket("end", (0.0, L / 2, h))


def _pipe_elbow(ctx):
    r, h, R = 0.14, 0.9, 0.6
    g = ctx.geo("pipe")
    kit.pipe_run(g, [(0.0, -1.0, h), (0.0, 0.0, h), (1.0, 0.0, h)], r, PIPE, bend=R)
    _pipe_stand(g, (0.0, -0.7), h, r)
    _pipe_stand(g, (0.7, 0.0), h, r)
    ctx.col_hull([(x, y, h + dz) for x, y in ((-0.25, -1.0), (0.25, -1.0), (1.0, -0.25), (1.0, 0.25), (-0.25, 0.25))
                  for dz in (-0.25, 0.25)] + [(0.0, -0.7, 0.0), (0.7, 0.0, 0.0)])
    ctx.socket("start", (0.0, -1.0, h))
    ctx.socket("end", (1.0, 0.0, h), (0.0, 0.0, -90.0))


def _pipe_valve(ctx):
    L, r, h = 2.0, 0.14, 0.9
    g = ctx.geo("pipe")
    kit.pipe_run(g, [(0.0, -L / 2, h), (0.0, -0.2, h)], r, PIPE)
    kit.pipe_run(g, [(0.0, 0.2, h), (0.0, L / 2, h)], r, PIPE)
    g.box((0.36, 0.4, 0.36), matrix=trs((0.0, 0.0, h)), mat=kit.DARK, bevel=0.04)
    kit.beam(g, (0.0, 0.0, h + 0.18), (0.0, 0.0, h + 0.5), 0.05, 0.05, kit.STEEL, profile="tube")
    kit.valve_wheel(g, (0.0, 0.0, h + 0.52), (0, 0, 1), 0.18)
    _pipe_stand(g, (0.0, -0.7), h, r)
    _pipe_stand(g, (0.0, 0.7), h, r)
    ctx.col_cylinder((0.0, 0.0, h), r * 1.7, L, rot=(90, 0, 0))
    ctx.col_box((0.0, 0.0, h + 0.1), (0.4, 0.45, 0.8))
    ctx.col_box((0.0, 0.0, (h - r) / 2), (0.3, 1.6, h - r))
    ctx.socket("start", (0.0, -L / 2, h))
    ctx.socket("end", (0.0, L / 2, h))
    ctx.socket("interact", (0.0, -0.6, 0.0), (0.0, 0.0, 180.0))


def _cable_reel(ctx):
    r, w = 0.6, 0.7
    g = ctx.geo("reel")
    for s in (-1, 1):
        g.cylinder(r, 0.05, segments=28, matrix=trs((s * w / 2, 0.0, r), (0, 90, 0)), mat="wood:wood_light", bevel=0.01)
    g.cylinder(r * 0.8, w - 0.05, segments=24, matrix=trs((0.0, 0.0, r), (0, 90, 0)), mat="rubber:hazard_black", bevel=0.02)
    g.cylinder(0.08, w + 0.1, segments=12, matrix=trs((0.0, 0.0, r), (0, 90, 0)), mat=kit.STEEL)
    tail = [Vector((0.0, -r * 0.78, r * 0.6)), Vector((0.2, -r - 0.3, 0.05)), Vector((0.5, -r - 0.9, 0.03))]
    kit.pipe_run(g, tail, 0.03, "rubber:hazard_black", flanges=False)
    ctx.col_cylinder((0.0, 0.0, r), r, w + 0.1, rot=(0, 90, 0))


def _cable_tray(ctx):
    L = 3.0
    g = ctx.geo("tray")
    for y in (-L / 2 + 0.3, 0.0, L / 2 - 0.3):
        kit.beam(g, (0.0, y, 0.0), (0.0, y, 2.2), 0.08, 0.08, "metal:galvanized")
        kit.beam(g, (0.0, y, 2.0), (0.45, y, 2.0), 0.06, 0.06, "metal:galvanized")
    g.box((0.4, L, 0.02), matrix=trs((0.25, 0.0, 2.02)), mat="metal:galvanized", bevel=0.004)
    for s in (0.05, 0.45):
        g.box((0.02, L, 0.08), matrix=trs((s, 0.0, 2.06)), mat="metal:galvanized", bevel=0.004)
    for k, col in enumerate(("rubber:hazard_black", "rubber:signal_red", "rubber:industrial_yellow", "rubber:hazard_black")):
        kit.pipe_run(g, [(0.12 + 0.08 * k, -L / 2, 2.06), (0.12 + 0.08 * k, L / 2, 2.06)], 0.022, col, flanges=False)
    ctx.col_box((0.2, 0.0, 1.1), (0.55, L, 2.2))
    ctx.socket("start", (0.0, -L / 2, 0.0))
    ctx.socket("end", (0.0, L / 2, 0.0))


# ------------------------------------------------------------------ signs / lamps

def _sign_warning(ctx):
    g = ctx.geo("sign")
    kit.beam(g, (0.0, 0.0, 0.0), (0.0, 0.0, 1.9), 0.06, 0.06, "metal:galvanized", profile="tube")
    g.box((0.3, 0.3, 0.04), matrix=trs((0.0, 0.0, 0.02)), mat="concrete:concrete", bevel=0.01)
    kit.warning_sign(g, (0.0, -0.03, 1.6), size=0.6)
    for z in (1.5, 1.15, 1.72):                                          # pole clamps
        g.torus(0.034, 0.008, seg_major=12, seg_minor=5, matrix=trs((0.0, 0.0, z)), mat=kit.DARK)
    g.lathe([(0.0, 1.9), (0.035, 1.9), (0.035, 1.93), (0.0, 1.95)], segments=12, mat=kit.DARK)
    g.box((0.62, 0.012, 0.2), matrix=trs((0.0, -0.036, 1.15)), mat="paint_clean:sign_white", bevel=0.004)
    g.box((0.5, 0.004, 0.06), matrix=trs((0.0, -0.044, 1.15)), mat="plastic:plastic_black")
    ctx.col_cylinder((0.0, 0.0, 0.95), 0.08, 1.9, segments=8)


def _sign_direction(ctx):
    g = ctx.geo("sign")
    det = ctx.geo("sign_detail", max_lod=1)
    g.box((0.35, 0.35, 0.12), matrix=trs((0.0, 0.0, 0.06)), mat="concrete:concrete", bevel=0.015)
    g.cylinder(0.055, 2.2, segments=12, matrix=trs((0.0, 0.0, 1.1)), mat=TIMBER, bevel=0.01)
    g.lathe([(0.0, 2.2), (0.07, 2.2), (0.07, 2.24), (0.0, 2.3)], segments=12, mat=kit.DARK)
    for k, (yaw, col) in enumerate(((20, "paint_clean:sign_green"), (-160, "paint_clean:sign_yellow"), (95, "paint_clean:sign_white"))):
        z = 1.95 - 0.28 * k
        f = trs((0.0, 0.0, z), (0, 0, yaw))
        pts = [(0.06, -0.1), (0.6, -0.1), (0.72, 0.0), (0.6, 0.1), (0.06, 0.1)]
        g.extrude(pts, 0.03, matrix=f @ trs((0.0, 0.015, 0.0), (90, 0, 0)), mat=col, bevel=0.005, segments=1)
        det.box((0.4, 0.034, 0.03), matrix=f @ trs((0.36, 0.0, 0.0)), mat="plastic:plastic_black")        # lettering strip
        kit.bolt_heads(det, [f @ Vector((0.1, -0.016, 0.0))], f.to_3x3() @ Vector((0, -1, 0)), r=0.012)
    ctx.col_cylinder((0.0, 0.0, 1.1), 0.1, 2.2, segments=8)


def _lamp_post(ctx):
    """Floodlight mast with two lamps and a control box."""
    h = 5.0
    g = ctx.geo("mast")
    g.box((0.6, 0.6, 0.3), matrix=trs((0.0, 0.0, 0.15)), mat="concrete:concrete", bevel=0.02)
    g.lathe([(0.0, 0.3), (0.1, 0.3), (0.07, h), (0.0, h)], segments=12, mat="metal:galvanized")
    kit.beam(g, (-0.5, 0.0, h - 0.1), (0.5, 0.0, h - 0.1), 0.08, 0.08, "metal:galvanized")
    for x in (-0.45, 0.45):
        kit.lamp(g, (x, -0.1, h - 0.2), (0.0, -0.7, -0.7), r=0.14, emit="emit:emissive_cool")
    g.box((0.3, 0.18, 0.45), matrix=trs((0.0, -0.12, 1.2)), mat="paint_worn:dark_steel", bevel=0.02)
    ctx.col_box((0.0, 0.0, 0.15), (0.6, 0.6, 0.3))
    ctx.col_cylinder((0.0, 0.0, h / 2), 0.12, h, segments=8)


def _lamp_hanging(ctx):
    """Tunnel lamp; origin at the ceiling mount (origin policy ``ceiling``)."""
    g = ctx.geo("lamp")
    g.box((0.3, 0.08, 0.06), matrix=trs((0.0, 0.0, -0.03)), mat=kit.DARK, bevel=0.01)             # ceiling bracket
    kit.bolt_heads(g, [(-0.11, 0.0, -0.06), (0.11, 0.0, -0.06)], (0, 0, -1), r=0.014)
    kit.beam(g, (0.0, 0.0, -0.06), (0.0, 0.0, -0.55), 0.014, 0.014, kit.STEEL, profile="tube")
    g.lathe([(0.0, -0.53), (0.05, -0.53), (0.2, -0.68), (0.2, -0.71), (0.0, -0.71)], segments=20, mat="paint_worn:machine_green")
    g.sphere(0.07, segments=12, rings=6, matrix=trs((0.0, 0.0, -0.72)), mat="emit:emissive_warm")
    for k in range(4):                                                  # wire guard
        a = k * math.pi / 2
        kit.beam(g, (math.cos(a) * 0.19, math.sin(a) * 0.19, -0.7), (math.cos(a) * 0.05, math.sin(a) * 0.05, -0.84), 0.01, 0.01,
                 kit.DARK, profile="tube")
    g.torus(0.05, 0.008, seg_major=12, seg_minor=4, matrix=trs((0.0, 0.0, -0.84)), mat=kit.DARK)
    ctx.col_cylinder((0.0, 0.0, -0.42), 0.2, 0.8, segments=8)
    ctx.metadata["mount"] = "ceiling: origin at the bracket top; snap to the tunnel crown"


# ------------------------------------------------------------------ fences / barriers / containers

def _fence(ctx):
    L, h = 3.0, 2.0
    g = ctx.geo("fence")
    for x in (-L / 2, L / 2):
        kit.beam(g, (x, 0.0, 0.0), (x, 0.0, h), 0.06, 0.06, "metal:galvanized", profile="tube")
        g.box((0.4, 0.2, 0.12), matrix=trs((x, 0.0, 0.06)), mat="concrete:concrete", bevel=0.01)
    for z in (0.1, h * 0.5, h - 0.05):
        kit.beam(g, (-L / 2, 0.0, z), (L / 2, 0.0, z), 0.035, 0.035, "metal:galvanized", profile="tube")
    for k in range(1, 20):                                              # welded mesh wires
        x = -L / 2 + L * k / 20
        kit.beam(g, (x, 0.0, 0.1), (x, 0.0, h - 0.05), 0.012, 0.012, "metal:galvanized", bevel=0.0)
    for k in range(1, 10):
        z = 0.1 + (h - 0.15) * k / 10
        kit.beam(g, (-L / 2, 0.012, z), (L / 2, 0.012, z), 0.012, 0.012, "metal:galvanized", bevel=0.0)
    g.box((0.4, 0.01, 0.3), matrix=trs((0.0, -0.011, 1.3)), mat="paint_clean:sign_yellow", bevel=0.004)
    ctx.col_box((0.0, 0.0, h / 2), (L, 0.2, h))
    ctx.socket("start", (-L / 2, 0.0, 0.0))
    ctx.socket("end", (L / 2, 0.0, 0.0))


def _barrier(ctx):
    L = 2.0
    g = ctx.geo("barrier")
    prof = [(-0.3, 0.0), (0.3, 0.0), (0.3, 0.08), (0.12, 0.3), (0.1, 0.8), (-0.1, 0.8), (-0.12, 0.3), (-0.3, 0.08)]
    g.extrude(prof, L, matrix=trs((-L / 2, 0.0, 0.0), (90, 0, 90)), mat="concrete:concrete", bevel=0.01)
    for s in (-1, 1):
        g.box((L * 0.9, 0.01, 0.12), matrix=trs((0.0, s * 0.111, 0.62), (s * 2.3, 0, 0)), mat=kit.HAZARD, bevel=0.002)
    ctx.col_hull([(x, y, z) for x in (-L / 2, L / 2) for y, z in ((-0.3, 0.0), (0.3, 0.0), (-0.12, 0.3), (0.12, 0.3),
                                                               (-0.1, 0.8), (0.1, 0.8))])
    ctx.socket("start", (-L / 2, 0.0, 0.0))
    ctx.socket("end", (L / 2, 0.0, 0.0))


def _container(ctx):
    """20 ft ISO shipping container: corrugated walls, corner castings, doors."""
    L, W, H = 6.06, 2.44, 2.59
    col = ctx.param("color", "machine_blue")
    g = ctx.geo("container")
    det = ctx.geo("container_detail", max_lod=1)
    paint = f"paint_worn:{col}"
    g.box((W - 0.1, L - 0.1, H - 0.1), matrix=trs((0.0, 0.0, H / 2)), mat=paint, bevel=0.01)
    for s in (-1, 1):                                                   # corrugation
        for k in range(24):
            y = -L / 2 + 0.25 + (L - 0.5) * k / 23
            g.box((0.05, 0.12, H - 0.3), matrix=trs((s * (W / 2 - 0.04), y, H / 2)), mat=paint, bevel=0.01)
    for k in range(10):
        x = -W / 2 + 0.25 + (W - 0.5) * k / 9
        g.box((0.12, 0.05, H - 0.3), matrix=trs((x, L / 2 - 0.04, H / 2)), mat=paint, bevel=0.01)
    for x in (-W / 2 + 0.06, W / 2 - 0.06):                             # corner posts + rails
        for y in (-L / 2 + 0.06, L / 2 - 0.06):
            g.box((0.14, 0.14, H), matrix=trs((x, y, H / 2)), mat=paint, bevel=0.01)
            for z in (0.06, H - 0.06):
                det.box((0.18, 0.18, 0.13), matrix=trs((x, y, z)), mat=kit.DARK, bevel=0.01)
    for z in (0.08, H - 0.08):
        for x in (-W / 2 + 0.06, W / 2 - 0.06):
            g.box((0.14, L, 0.14), matrix=trs((x, 0.0, z)), mat=paint, bevel=0.01)
    # Doors at -Y with locking bars.
    for s in (-1, 1):
        g.box((W / 2 - 0.08, 0.04, H - 0.3), matrix=trs((s * W / 4, -L / 2 + 0.02, H / 2)), mat=paint, bevel=0.008)
        for x in (s * 0.3, s * 0.85):
            kit.beam(g, (x, -L / 2 - 0.03, 0.15), (x, -L / 2 - 0.03, H - 0.15), 0.03, 0.03, kit.STEEL, profile="tube")
            det.box((0.05, 0.06, 0.2), matrix=trs((x, -L / 2 - 0.05, 1.2)), mat=kit.DARK, bevel=0.005)
    ctx.col_box((0.0, 0.0, H / 2), (W, L, H))
    ctx.socket("door", (0.0, -L / 2 - 0.8, 0.0), (0.0, 0.0, 180.0))


# ------------------------------------------------------------------ scaffold / catwalk / tank

def _scaffold(ctx):
    w, d, h = 2.0, 1.6, 4.0
    g = ctx.geo("scaffold")
    tube = "metal:galvanized"
    for x in (-w / 2, w / 2):
        for y in (-d / 2, d / 2):
            kit.beam(g, (x, y, 0.0), (x, y, h + 1.0), 0.048, 0.048, tube, profile="tube")
            g.box((0.15, 0.15, 0.02), matrix=trs((x, y, 0.01)), mat=kit.DARK, bevel=0.004)
    for z in (0.2, 2.0, h):
        for (ax, ay), (bx, by) in (((-w / 2, -d / 2), (w / 2, -d / 2)), ((w / 2, -d / 2), (w / 2, d / 2)),
                                   ((w / 2, d / 2), (-w / 2, d / 2)), ((-w / 2, d / 2), (-w / 2, -d / 2))):
            kit.beam(g, (ax, ay, z), (bx, by, z), 0.048, 0.048, tube, profile="tube")
    kit.beam(g, (-w / 2, -d / 2, 0.2), (w / 2, -d / 2, 2.0), 0.048, 0.048, tube, profile="tube")
    kit.beam(g, (w / 2, d / 2, 2.0), (-w / 2, d / 2, h), 0.048, 0.048, tube, profile="tube")
    for k in range(5):                                                  # working platform boards
        g.box((w - 0.1, 0.28, 0.04), matrix=trs((0.0, -d / 2 + 0.2 + 0.3 * k, h + 0.02)), mat=TIMBER, bevel=0.004)
    kit.railing(g, [(-w / 2, -d / 2, h), (w / 2, -d / 2, h), (w / 2, d / 2, h), (-w / 2, d / 2, h)], height=1.0, mat=tube,
                post_spacing=2.5)
    kit.ladder(g, (-w / 2 - 0.05, 0.0, 0.0), h + 1.0, width=0.42, mat=tube, facing=(-1, 0, 0))      # open -X side
    ctx.col_box((0.0, 0.0, (h + 1.0) / 2), (w + 0.1, d + 0.1, h + 1.0))


def _catwalk(ctx):
    L, w, h = 4.0, 1.0, 2.5
    g = ctx.geo("catwalk")
    kit.deck(g, (0.0, 0.0, h), (w, L), thickness=0.06)
    for y in (-L / 2 + 0.2, L / 2 - 0.2):
        for x in (-w / 2 + 0.06, w / 2 - 0.06):
            kit.beam(g, (x, y, 0.0), (x, y, h - 0.06), 0.1, 0.1, YELLOW, profile="I", up=(1, 0, 0))
            g.box((0.25, 0.25, 0.02), matrix=trs((x, y, 0.01)), mat=kit.DARK, bevel=0.004)
        kit.beam(g, (-w / 2 + 0.06, y, h - 0.4), (w / 2 - 0.06, y, h - 0.1), 0.05, 0.05, YELLOW)
    for x in (-w / 2, w / 2):
        kit.railing(g, [(x, -L / 2, h), (x, L / 2, h)], height=1.1, mat=YELLOW)
    ctx.col_box((0.0, 0.0, h - 0.03), (w, L, 0.06))
    for x in (-w / 2, w / 2):
        ctx.col_box((x, 0.0, h + 0.55), (0.06, L, 1.1))
    for y in (-L / 2 + 0.2, L / 2 - 0.2):
        ctx.col_box((0.0, y, h / 2), (w, 0.12, h))
    ctx.socket("start", (0.0, -L / 2, h))
    ctx.socket("end", (0.0, L / 2, h))


def _water_tank(ctx):
    R, h_tank, legs_h = 1.3, 2.2, 4.0
    g = ctx.geo("tank")
    g.lathe([(0.0, legs_h), (R, legs_h), (R, legs_h + h_tank), (R * 0.3, legs_h + h_tank + 0.5), (0.0, legs_h + h_tank + 0.55)],
            segments=32, mat="metal:galvanized")
    for k in range(3):
        g.torus(R + 0.01, 0.02, seg_major=32, seg_minor=5, matrix=trs((0.0, 0.0, legs_h + 0.3 + 0.8 * k)), mat=kit.DARK)
    legs = []
    for k in range(4):
        a = math.pi / 4 + k * math.pi / 2
        p = Vector((math.cos(a) * R * 1.05, math.sin(a) * R * 1.05, 0.0))
        legs.append(p)
        kit.beam(g, p, Vector((p.x * 0.85, p.y * 0.85, legs_h)), 0.16, 0.16, "paint_worn:machine_blue", profile="I")
        g.box((0.4, 0.4, 0.3), matrix=trs(p + Vector((0.0, 0.0, 0.15))), mat="concrete:concrete", bevel=0.02)
    for i in range(4):
        a, b = legs[i], legs[(i + 1) % 4]
        kit.beam(g, a + Vector((0.0, 0.0, 0.8)), b + Vector((0.0, 0.0, legs_h - 0.6)), 0.06, 0.06, "paint_worn:machine_blue",
                 profile="tube")
    kit.ladder(g, (0.0, -R * 1.2, 0.0), legs_h + h_tank, width=0.42, mat=YELLOW, facing=(0, -1, 0), cage=True)
    kit.pipe_run(g, [(0.3, 0.0, legs_h), (0.3, 0.0, 0.6), (0.3, -1.2, 0.6)], 0.08, PIPE)
    ctx.col_cylinder((0.0, 0.0, legs_h + h_tank / 2), R, h_tank)
    for p in legs:
        ctx.col_box(tuple(p * 0.93 + Vector((0.0, 0.0, legs_h / 2))), (0.2, 0.2, legs_h))
