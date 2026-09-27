"""Hair and facial hair shells derived from the head cage.

Hairlines are defined per head ring as angle masks (0 deg = face front), so
every style shares the head topology and skin weights. Shells are offset from
the scalp, their borders fold back to the scalp (no visible gaps), and styles
add volume, fringes, ponytails or buns. Everything is skinned like the head.
"""

import math

from mathutils import Matrix, Vector

from utilities.meshkit import Geo

from .head import GRID_A, GRID_B, HEAD_ORIGIN, N, RINGS, angle_of, grid_boundary_order, head_weights
from .skinned import SkinnedGeo

# Minimum |angle| covered per ring for a standard hairline (None = not covered).
HAIRLINE = {"n2": None, "hj": 145, "h0": 132, "h1": 124, "h1m": 120, "h2": 110, "h3": 100, "h4": 80,
            "h5": 62, "h6": 38, "h7": 0, "h8": 0}
LONG_HAIRLINE = dict(HAIRLINE, n2=150, hj=128, h0=118, h1=108, h1m=104, h2=96, h3=88)

STYLE = {
    #            thickness top/side/back, hairline, extras
    "buzz":      (0.003, 0.0025, 0.003, HAIRLINE),
    "short":     (0.012, 0.008, 0.009, HAIRLINE),
    "side_part": (0.017, 0.009, 0.01, HAIRLINE),
    "curly":     (0.024, 0.018, 0.02, HAIRLINE),
    "ponytail":  (0.011, 0.008, 0.009, HAIRLINE),
    "bun":       (0.011, 0.008, 0.009, HAIRLINE),
    "long":      (0.013, 0.011, 0.016, LONG_HAIRLINE),
}


def _center():
    return Vector((0.0, 0.01, 1.64))


def _normal(p):
    d = p - _center()
    d.z *= 0.75
    return d.normalized()


def build_hair(shape, style, color_key, helmet=False, rng=None):
    if style in (None, "none", "bald"):
        return None
    if style not in STYLE:
        raise ValueError(f"unknown hair style {style}")
    t_top, t_side, t_back, line = STYLE[style]
    if helmet:
        t_top = min(t_top, 0.009)
        t_side = min(t_side, 0.008)
    key = f"hair:{color_key}"
    g = SkinnedGeo("hair", pattern_origin=HEAD_ORIGIN)
    g.subdivide = 1
    names = [r[0] for r in RINGS]
    covered = {}
    verts = {}

    def thickness(p, ring, k):
        a = abs(angle_of(k)) if k is not None else 0.0
        top = max(0.0, min(1.0, (p.z - 1.69) / 0.07))
        back = max(0.0, min(1.0, (a - 90) / 60.0))
        t = t_side + (t_top - t_side) * top + (t_back - t_side) * back * (1 - top)
        if style == "side_part" and p.x > 0 and p.z > 1.7:
            t += 0.006
        if style == "curly" and rng is not None:
            t += 0.004 * math.sin(p.x * 180 + p.z * 140) * math.cos(p.y * 170)
        return t

    for name in names:
        amin = line.get(name)
        if amin is None:
            continue
        for k, p in enumerate(shape.rings[name]):
            if abs(angle_of(k)) + 1e-6 >= amin:
                covered[(name, k)] = True
                w = head_weights(name, k)
                verts[(name, k)] = g.vert(p + _normal(p) * thickness(p, name, k), w)
    # Rings: faces where all four corners are covered.
    for i in range(len(names) - 1):
        a, b = names[i], names[i + 1]
        for k in range(N):
            k2 = (k + 1) % N
            quad = [(a, k), (a, k2), (b, k2), (b, k)]
            if all(q in covered for q in quad):
                g.face([verts[q] for q in quad], key)
    # Crown grid (always covered).
    grid = {}
    top = "h8"
    for k, ij in enumerate(grid_boundary_order()):
        grid[ij] = verts[(top, k)]
    for ij, p in shape.cap_interior.items():
        grid[ij] = g.vert(p + _normal(p) * thickness(p, top, None), {"head": 1.0})
    for i in range(GRID_A):
        for jj in range(GRID_B):
            g.face([grid[(i, jj)], grid[(i + 1, jj)], grid[(i + 1, jj + 1)], grid[(i, jj + 1)]], key)
    _fold_border(g, key)
    if style == "ponytail":
        _ponytail(g, key)
    elif style == "bun":
        _bun(g, key)
    elif style in ("side_part", "short") and not helmet:
        _fringe(g, shape, key, 0.012 if style == "short" else 0.02)
    return g


def _fold_border(g, key):
    """Fold every open border back toward the scalp so the shell reads as volume."""
    bm = g.bm
    bm.normal_update()
    nxt = {}
    for e in bm.edges:
        if len(e.link_faces) == 1:
            f = e.link_faces[0]
            for lp in f.loops:
                if lp.edge == e:
                    nxt[lp.vert] = lp.link_loop_next.vert
    done = set()
    names = g.group_names()
    for start in list(nxt):
        if start in done:
            continue
        chain = []
        v = start
        while v not in done and v in nxt:
            done.add(v)
            chain.append(v)
            v = nxt[v]
        inner = {}
        for v in chain:
            w = {names[gi]: wt for gi, wt in v[g.dl].items()}
            inner[v] = g.vert(v.co - _normal(v.co) * 0.009, w, pat=v[g.pat])
        for a in chain:
            b = nxt[a]
            if b not in inner:
                continue
            f = bm.faces.new([b, a, inner[a], inner[b]])
            f.material_index = g.mat(key)
            f.smooth = True


def _fringe(g, shape, key, amount):
    """A swept fringe along the front hairline."""
    geo = Geo("fringe")
    path = []
    for i in range(7):
        t = i / 6.0
        a = math.radians(-50 + 100 * t)
        x = 0.078 * math.sin(a)
        y = 0.004 - 0.09 * math.cos(a)
        z = 1.716 + 0.01 * math.cos(a) + (0.004 if t > 0.5 else 0.0)
        path.append(Vector((x, y - 0.006, z)))
    prof = [(-0.004, -amount * 0.5), (0.006, -amount * 0.5), (0.008, amount * 0.6), (-0.003, amount * 0.7)]
    geo.sweep(path, profile=prof, mat=key, up_hint=(0, -1, 0.4))
    g.append_rigid(geo, "head")


def _ponytail(g, key):
    geo = Geo("ponytail")
    path = [Vector((0, 0.1, 1.66)), Vector((0, 0.125, 1.62)), Vector((0, 0.132, 1.57)), Vector((0, 0.128, 1.52)),
            Vector((0, 0.118, 1.48))]
    scales = [1.0, 1.1, 1.0, 0.8, 0.45]
    geo.sweep(path, radius=0.022, segments=10, mat=key, scales=scales, up_hint=(1, 0, 0))
    geo.torus(0.02, 0.005, seg_major=12, seg_minor=6, matrix=Matrix.Translation((0, 0.108, 1.653)) @
              Matrix.Rotation(math.radians(70), 4, "X"), mat="plastic:plastic_black")

    def w(co):
        t = max(0.0, min(1.0, (1.62 - co.z) / 0.12))
        return {"head": 1.0 - 0.45 * t, "neck": 0.45 * t}
    g.append_geo(geo, w)


def _bun(g, key):
    geo = Geo("bun")
    geo.sphere(0.04, segments=14, rings=9, mat=key, matrix=Matrix.Translation((0, 0.098, 1.705)),
               scale=(1.0, 0.85, 0.9))
    g.append_rigid(geo, "head")


BEARDS = {
    # ring -> (min |angle|, max |angle|)
    "full": {"n2": (0, 70), "hj": (0, 112), "h0": (0, 110), "h1": (22, 104), "h1m": (26, 100), "h2": (0, 98),
             "h3": (84, 100)},
    "goatee": {"hj": (0, 32), "h0": (0, 34), "h1": (0, 18)},
    "mustache": {"h2": (0, 40), "h1m": (0, 34)},
    "stubble": {"n2": (0, 70), "hj": (0, 112), "h0": (0, 110), "h1": (22, 104), "h1m": (26, 100), "h2": (0, 98)},
}


def build_beard(shape, style, color_key):
    if style in (None, "none"):
        return None
    if style not in BEARDS:
        raise ValueError(f"unknown beard style {style}")
    mask = BEARDS[style]
    thick = {"full": 0.011, "goatee": 0.009, "mustache": 0.006, "stubble": 0.0016}[style]
    key = f"hair:{color_key}"
    g = SkinnedGeo("beard", pattern_origin=HEAD_ORIGIN)
    g.subdivide = 1
    names = [r[0] for r in RINGS]
    verts = {}
    for name, (lo, hi) in mask.items():
        for k, p in enumerate(shape.rings[name]):
            a = abs(angle_of(k))
            if lo - 1e-6 <= a <= hi + 1e-6:
                n = (p - Vector((0, 0.0, 1.6))).normalized()
                verts[(name, k)] = g.vert(p + n * thick, head_weights(name, k))
    for i in range(len(names) - 1):
        a, b = names[i], names[i + 1]
        for k in range(N):
            k2 = (k + 1) % N
            quad = [(a, k), (a, k2), (b, k2), (b, k)]
            if all(q in verts for q in quad):
                g.face([verts[q] for q in quad], key)
    if not g.bm.faces:
        g.bm.free()
        return None
    _fold_border(g, key)
    return g
