"""Natural environment pieces: rocks, boulders, cliff sections, rubble piles,
terrain tiles and vegetation.

``kind`` selects the piece; sizes come from the registry params. Rocks are
fractured (cleavage facets), sit slightly sunk into the ground plane
(origin ``embedded``) and get convex-hull collision; vegetation keeps trunks
collidable and leaves collision-free (walk-through canopy).
"""

import math

import bmesh
from mathutils import Matrix, Vector, noise

from utilities.meshkit import frame_from_axis, trs

from .. import rocks


def build(ctx):
    kind = ctx.param("kind")
    fn = {"rock": _rock, "cliff": _cliff, "pile": _pile, "terrain": _terrain, "pine": _pine, "dead_tree": _dead_tree,
          "bush": _bush, "grass": _grass}.get(kind)
    if fn is None:
        raise ValueError(f"unknown natural kind {kind!r}")
    fn(ctx)


def _hull_from(g, ctx, max_points=56):
    verts = [v.co.copy() for v in g.bm.verts]
    step = max(1, len(verts) // max_points)
    ctx.col_hull([tuple(v) for v in verts[::step]])


def _rock(ctx):
    size = ctx.param("size", (1.2, 1.0, 0.8))
    mat = ctx.param("material", "stone:stone_gray")
    g = ctx.geo("rock")
    rng = ctx.rng.child("rock")
    subdiv = 5 if max(size) > 1.5 else 4
    rocks.rock(g, rng, size, mat, subdivisions=subdiv, facets=ctx.param("facets", 7), lump=0.17)
    if ctx.param("companions", 0):
        for k in range(ctx.param("companions", 0)):
            a = 2 * math.pi * (k + rng.uniform(0, 0.5)) / ctx.param("companions", 1)
            s = [x * rng.uniform(0.25, 0.4) for x in size]
            rocks.rock(g, rng, s, mat, subdivisions=4, center=(math.cos(a) * size[0] * 0.55, math.sin(a) * size[1] * 0.55, 0.0),
                       facets=5)
    _hull_from(g, ctx)


def _cliff(ctx):
    """Modular cliff section (sockets ``tile_left``/``tile_right``)."""
    w, d, h = ctx.param("size", (6.0, 2.2, 4.5))
    cliff_face(ctx.geo("cliff"), ctx.geo("scree", max_lod=1), ctx.rng.child("cliff"), w, d, h,
               ctx.param("material", "stone:stone_warm"))
    ctx.col_box((0.0, 0.0, h / 2), (w, d, h))
    ctx.socket("tile_left", (-w / 2, 0.0, 0.0))
    ctx.socket("tile_right", (w / 2, 0.0, 0.0))


def cliff_face(g, det, rng, w, d, h, mat, origin=(0.0, 0.0, 0.0), layers=4, bury=0.1, boulders=4, scree=9,
               taper=(False, False)):
    """Displaced rock face with strata ledges that step back as they rise, a
    wavy rolled top edge and a flat back, centred on ``origin`` (base level).
    Displacement and top height fade to a shared profile at both ends, so
    sections of equal height placed side by side line up without seams;
    ``taper`` (left, right) instead rounds an end back into the hill for a
    free-standing edge. Shared with buildings."""
    o = Vector(origin)
    off = Vector((rng.uniform(-50, 50), rng.uniform(-50, 50), rng.uniform(-50, 50)))
    lh = (h + bury) / layers

    def end_weight(x):
        """0 at a seam-matched end, 1 in the interior."""
        return max(0.0, min(1.0, (w / 2 - abs(x)) / 1.0))

    def tapered(x):
        side = 0 if x < 0 else 1
        if not taper[side]:
            return 0.0
        t = max(0.0, 1.0 - (w / 2 - abs(x)) / 1.6)
        return t * t * (3 - 2 * t)

    def top(x):
        """Top height: wavy in the interior, the nominal height at the ends."""
        wave = 0.35 * noise.noise(Vector((x * 0.35 + o.x * 0.35, 7.3, 0.0)) + off) * end_weight(x)
        return h + wave - 1.2 * tapered(x) * h / 3

    beds = [(rng.uniform(-0.12, 0.12), rng.uniform(1.1, 2.0), rng.uniform(0.0, 3.0)) for _ in range(layers)]

    def face(x, y):
        """Bedding planes (sharp set-back steps with an overhanging lip),
        vertical joints splitting each bed into blocks, and fine roughness."""
        z = y + (h + bury) / 2                               # grid y -> height above the buried base
        e = end_weight(x)
        zb = z + 0.18 * noise.noise(Vector((x * 0.5 + o.x * 0.5, 1.7, 0.0)) + off) * e     # wavy bedding planes
        k = min(layers - 1, max(0, int(zb / lh)))
        frac = min(1.0, max(0.0, zb / lh - k))
        jitter, joint_w, phase = beds[k]
        disp = -0.24 * k + jitter + 0.22 * (1.0 - frac) ** 2
        j = math.floor((x + o.x + phase) / joint_w)
        disp += 0.22 * noise.noise(Vector((j * 1.7, k * 3.1, 0.5)) + off) * e          # block set-in / set-out
        p = Vector((x * 0.45 + o.x * 0.45, z * 0.7, 0.0)) + off
        disp += (0.15 * noise.noise(p) + 0.06 * noise.noise(p * 2.6) + 0.03 * noise.noise(p * 7.0)) * e
        roll = h - 0.6                                       # (heights are rescaled to top(x) afterwards)
        if z > roll:
            disp -= 1.1 * ((z - roll) / 0.6) ** 2            # rolled top edge
        return disp - 1.4 * tapered(x) + 0.4

    # Grid in (x, height), rotated upright: displacement pushes toward -Y (the face).
    m = Matrix.Translation(o + Vector((0.0, -d / 2 + 0.4, (h - bury) / 2))) @ Matrix.Rotation(math.radians(90), 4, "X")
    start = len(g.bm.verts)
    g.grid(w, h + bury, max(8, int(w * 6)), max(8, int((h + bury) * 6)), height_fn=face, matrix=m, mat=mat,
           skirt=d - 0.4)                                    # skirt closes the back at y = d/2
    g.bm.verts.ensure_lookup_table()
    for i in range(start, len(g.bm.verts)):                  # wavy / tapered top: scale each column's height
        v = g.bm.verts[i]
        zl = v.co.z - (o.z - bury)
        if zl > 0.0:
            v.co.z = (o.z - bury) + zl * (top(v.co.x - o.x) + bury) / (h + bury)
    for k in range(boulders):                                # boulders caught on the ledges
        x = rng.uniform(-w / 2 + 0.8, w / 2 - 0.8)
        z = lh * rng.randint(1, layers - 1) - bury
        s = rng.uniform(0.35, 0.6)
        y = -d / 2 + 0.4 - face(x, z - (h - bury) / 2) + s * 0.3
        z = (z + bury) * (top(x) + bury) / (h + bury) - bury           # follow the rescaled ledge
        rocks.rock(g, rng, (s * 1.4, s, s * 0.8), mat, subdivisions=3, center=tuple(o + Vector((x, y, z - s * 0.15))), facets=6)
    for k in range(scree):                                   # scree at the foot
        s = rng.uniform(0.12, 0.3)
        rocks.rock(det, rng, (s * 1.3, s, s * 0.7), mat, subdivisions=2,
                   center=tuple(o + Vector((rng.uniform(-w / 2 + 0.3, w / 2 - 0.3), -d / 2 - rng.uniform(0.0, 0.6), 0.0))), facets=3)


def _pile(ctx):
    """Rubble / ore pile: a heap of small fragments on a gravel mound."""
    r, h = ctx.param("radius", 1.4), ctx.param("height", 0.9)
    mat = ctx.param("material", "gravel:gravel")
    g = ctx.geo("heap")
    frags = ctx.geo("fragments")
    rng = ctx.rng.child("pile")
    prof = [(0.0, -0.03), (r, -0.03)] + [(r * (1.0 - t / 8) ** 1.1, h * math.sin(math.pi / 2 * t / 8)) for t in range(1, 9)]
    prof.append((0.0, h))
    g.lathe(prof, segments=32, mat=mat)
    bm = g.bm
    off = Vector((rng.uniform(-9, 9), rng.uniform(-9, 9), rng.uniform(-9, 9)))
    for v in bm.verts:
        if v.co.z > 0.02:
            v.co += Vector((0.0, 0.0, 1.0)) * 0.06 * noise.noise(v.co * 2.5 + off) * (v.co.z / h)
    for k in range(22):
        a = rng.uniform(0, 2 * math.pi)
        rr = rng.uniform(0.1, 0.95) * r
        zz = h * (1.0 - (rr / r) ** 1.4) * 0.92
        s = rng.uniform(0.12, 0.26)
        rocks.rock(frags, rng, (s * 1.3, s, s * 0.8), ctx.param("fragment_material", "stone:stone_gray"), subdivisions=2,
                   center=(math.cos(a) * rr, math.sin(a) * rr, zz - s * 0.3), facets=3)
    ctx.col_hull([(math.cos(2 * math.pi * k / 12) * r, math.sin(2 * math.pi * k / 12) * r, 0.0) for k in range(12)] +
                 [(0.0, 0.0, h)] + [(math.cos(2 * math.pi * k / 8) * r * 0.5, math.sin(2 * math.pi * k / 8) * r * 0.5, h * 0.75)
                                    for k in range(8)])


def _terrain(ctx):
    """Modular ground tile (4 x 4 m): gentle noise, gravel/soil, flat seams."""
    sx, sy = ctx.param("size", (4.0, 4.0))
    rise = ctx.param("rise", 0.0)                          # ramp height over +Y
    mound = ctx.param("mound", 0.0)
    rng = ctx.rng.child("terrain")
    off = Vector((rng.uniform(-40, 40), rng.uniform(-40, 40), 0.0))
    g = ctx.geo("ground")
    det = ctx.geo("pebbles", max_lod=0)

    def height(x, y):
        edge = min(1.0, (sx / 2 - abs(x)) / 0.4, (sy / 2 - abs(y)) / 0.4)     # seams stay exact
        base = rise * (y + sy / 2) / sy
        m = mound * max(0.0, 1.0 - (x * x + y * y) / (min(sx, sy) * 0.45) ** 2)
        return base + m + 0.05 * noise.noise(Vector((x, y, 0.0)) * 0.9 + off) * max(0.0, edge)

    g.grid(sx, sy, 24, 24, height_fn=height, mat=ctx.param("material", "gravel:gravel"), skirt=0.25)
    for k in range(25):
        x, y = rng.uniform(-sx / 2 + 0.3, sx / 2 - 0.3), rng.uniform(-sy / 2 + 0.3, sy / 2 - 0.3)
        s = rng.uniform(0.05, 0.14)
        rocks.rock(det, rng, (s * 1.3, s, s * 0.7), "stone:stone_gray", subdivisions=1, center=(x, y, height(x, y)),
                   facets=3, bury=s * 0.3)
    top = max(rise, mound) + 0.08
    ctx.col_hull([(x, y, height(x, y)) for x in (-sx / 2, 0.0, sx / 2) for y in (-sy / 2, 0.0, sy / 2)] +
                 [(x, y, -0.25) for x in (-sx / 2, sx / 2) for y in (-sy / 2, sy / 2)])
    ctx.socket("north", (0.0, sy / 2, rise))
    ctx.socket("south", (0.0, -sy / 2, 0.0))
    ctx.metadata["tile"] = {"size_m": [sx, sy], "rise_m": rise, "top_m": round(top, 3)}


def _foliage_blob(g, center, size, mat, rng, subdiv=3):
    tmp = bmesh.new()
    bmesh.ops.create_icosphere(tmp, subdivisions=subdiv, radius=1.0)
    off = Vector((rng.uniform(-30, 30), rng.uniform(-30, 30), rng.uniform(-30, 30)))
    for v in tmp.verts:
        d = v.co.normalized()
        r = 1.0 + 0.22 * noise.noise(d * 2.2 + off)
        v.co = Vector((d.x * r * size[0], d.y * r * size[1], d.z * r * size[2])) + Vector(center)
    return g._append(tmp, Matrix.Identity(4), mat, (rng.uniform(0, 9), rng.uniform(0, 9), 0.0))


def _pine(ctx):
    h = ctx.param("height", 6.0)
    rng = ctx.rng.child("pine")
    trunk = ctx.geo("trunk")
    crown = ctx.geo("crown")
    trunk.lathe([(0.0, -0.05), (0.2, -0.05), (0.17, 0.4), (0.12, h * 0.5), (0.05, h * 0.95), (0.0, h * 0.96)], segments=12,
                mat="wood_weathered:bark_brown")
    tiers = 6
    for k in range(tiers):
        z0 = h * (0.2 + 0.125 * k)
        rr = h * 0.26 * (1.0 - k / (tiers + 0.6))
        tier_h = h * 0.22
        n = 18
        prof = [(0.0, z0 - 0.05), (rr, z0), (rr * 0.6, z0 + tier_h * 0.35), (rr * 0.25, z0 + tier_h * 0.8), (0.0, z0 + tier_h)]
        start = len(crown.bm.verts)
        crown.lathe(prof, segments=n, mat="foliage:pine_green")
        crown.bm.verts.ensure_lookup_table()
        for v in crown.bm.verts[start:]:
            dd = math.hypot(v.co.x, v.co.y)
            if dd > rr * 0.6:                               # jagged, drooping rim
                a = math.atan2(v.co.y, v.co.x)
                v.co.x *= 1.0 + 0.18 * math.sin(a * 7 + k)
                v.co.y *= 1.0 + 0.18 * math.sin(a * 7 + k)
                v.co.z -= 0.12 * rng.uniform(0.5, 1.0)
    ctx.col_cylinder((0.0, 0.0, h * 0.25), 0.2, h * 0.5, segments=8)


def _dead_tree(ctx):
    """Bare, weathered tree: leaning trunk, forked branches, surface roots."""
    h = ctx.param("height", 4.5)
    rng = ctx.rng.child("dead")
    g = ctx.geo("tree")
    wood = "wood_weathered:dead_wood"
    lean = Vector((rng.uniform(-0.25, 0.25), rng.uniform(-0.25, 0.25), 0.0))
    trunk = [Vector((0.0, 0.0, -0.05))] + [Vector((0.0, 0.0, h * 0.92 * k / 6)) + lean * (k / 6) ** 1.5 for k in range(1, 7)]
    g.sweep(trunk, radius=0.24, segments=12, mat=wood, scales=[1.1, 0.95, 0.8, 0.66, 0.5, 0.34, 0.12])

    def trunk_at(z):
        k = min(6.0, max(0.0, z / (h * 0.92) * 6))
        return Vector((0.0, 0.0, z)) + lean * (k / 6) ** 1.5

    for k in range(6):
        z = h * rng.uniform(0.35, 0.82)
        a = 2 * math.pi * k / 6 + rng.uniform(-0.4, 0.4)
        ln = rng.uniform(0.9, 1.6) * (1.2 - z / h * 0.5)
        d = Vector((math.cos(a), math.sin(a), rng.uniform(0.35, 0.9))).normalized()
        base = trunk_at(z)
        pts = [base, base + d * ln * 0.35, base + d * ln * 0.7 + Vector((0.0, 0.0, 0.08)), base + d * ln + Vector((0.0, 0.0, 0.25))]
        g.sweep(pts, radius=0.075, segments=7, mat=wood, scales=[1.0, 0.75, 0.45, 0.12])
        fork = pts[2]
        d2 = (d + Vector((-d.y, d.x, 0.3)) * rng.choice((-1.0, 1.0))).normalized()
        g.sweep([pts[1], fork + d2 * 0.1, fork + d2 * ln * 0.45], radius=0.045, segments=6, mat=wood, scales=[1.0, 0.6, 0.15])
    for k in range(4):                                         # surface roots
        a = 2 * math.pi * k / 4 + rng.uniform(-0.3, 0.3)
        d = Vector((math.cos(a), math.sin(a), 0.0))
        g.sweep([Vector((0.0, 0.0, 0.35)), d * 0.45 + Vector((0.0, 0.0, 0.06)), d * 0.95 + Vector((0.0, 0.0, -0.04))],
                radius=0.1, segments=7, mat=wood, scales=[1.0, 0.6, 0.2])
    ctx.col_cylinder((0.0, 0.0, h * 0.4), 0.25, h * 0.8, segments=8)


def _bush(ctx):
    r = ctx.param("radius", 0.7)
    rng = ctx.rng.child("bush")
    g = ctx.geo("bush")
    for k in range(6):
        a = 2 * math.pi * k / 6 + rng.uniform(-0.4, 0.4)
        rr = r * rng.uniform(0.2, 0.55)
        s = r * rng.uniform(0.45, 0.65)
        _foliage_blob(g, (math.cos(a) * rr, math.sin(a) * rr, s * 0.7), (s, s, s * 0.8), ctx.param("material", "foliage:leaf_green"),
                      rng)
    _foliage_blob(g, (0.0, 0.0, r * 0.75), (r * 0.6, r * 0.6, r * 0.55), ctx.param("material", "foliage:leaf_green"), rng)


def _grass(ctx):
    r = ctx.param("radius", 0.35)
    rng = ctx.rng.child("grass")
    g = ctx.geo("blades")
    for k in range(64):
        a = rng.uniform(0, 2 * math.pi)
        rr = rng.uniform(0.0, r)
        base = Vector((math.cos(a) * rr, math.sin(a) * rr, -0.01))
        h = rng.uniform(0.25, 0.5)
        lean = Vector((math.cos(a), math.sin(a), 0.0)) * rng.uniform(0.05, 0.2)
        w = 0.02
        side = Vector((-math.sin(a), math.cos(a), 0.0)) * w
        tip = base + Vector((0.0, 0.0, h)) + lean
        t = Vector((math.cos(a), math.sin(a), 0.0)) * 0.004
        verts = [base - side, base + side, tip, base - side + t, base + side + t, tip + t]
        g.mesh([tuple(v) for v in verts], [(0, 1, 2), (4, 3, 5), (0, 3, 4, 1), (1, 4, 5, 2), (2, 5, 3, 0)],
               mat=ctx.param("material", "foliage:grass_dry"), recalc=True)
