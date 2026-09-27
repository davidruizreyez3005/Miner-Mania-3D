"""Shared procedural PBR material library.

Material keys are either fixed names (``"steel"``, ``"concrete"``) or
parametric ``kind:palette_color`` keys (``"paint:industrial_yellow"``,
``"fabric:denim_blue"``, ``"skin:skin_3"``). Colors always come from
assets/source/palette.json so the whole game shares one visual language.

Procedural graphs only use non-ray-traced inputs (noise, voronoi, waves,
pointiness, pattern coordinates) plus the per-asset baked AO mask, so every
bake pass except AO converges at one sample.

Baked materials are flattened into one texture set per asset; ``glass`` and
``emit:*`` materials stay factor-only (no textures) and are exported as
separate glTF materials.
"""

from dataclasses import dataclass

import bpy

from core.config import color
from core.errors import ConfigError

from .nodes import NB


@dataclass
class MatInfo:
    key: str
    kind: str
    baked: bool = True
    blend: str = "OPAQUE"


def _lin(c, k):
    return tuple(max(0.0, min(1.0, x * k)) for x in c)


def _tint(c, t, amount):
    return tuple(a * (1 - amount) + b * amount for a, b in zip(c, t))


# ------------------------------------------------------------------ builders
# Each builder receives (nb, param) and wires base/roughness/metallic/normal.

def _wear_masks(nb, wear, grime, scale=1.0):
    """Edge wear from pointiness broken up by noise; grime from baked AO."""
    edge = nb.map_range(nb.edge_mask(), 0.15, 0.7, 0.0, 1.0, smooth=True)
    brk = nb.noise(nb.coord(14.0 * scale), detail=3.0, roughness=0.6)
    brk = nb.map_range(brk, 0.35, 0.62, 0.0, 1.0)
    wear_m = nb.math("MULTIPLY", nb.math("MULTIPLY", edge, brk), wear * 1.6, clamp=True)
    ao = nb.ao_mask()
    # Grime collects in real crevices only: a wide AO falloff smeared broad
    # dark patches ("camouflage") over large panels.
    cav = nb.map_range(ao, 0.45, 0.88, 1.0, 0.0, smooth=True)
    gn = nb.noise(nb.coord(3.0 * scale), detail=4.0, roughness=0.55)
    gn = nb.map_range(gn, 0.3, 0.7, 0.4, 1.0)
    grime_m = nb.math("MULTIPLY", nb.math("MULTIPLY", cav, gn), grime * 1.4, clamp=True)
    return wear_m, grime_m


def build_paint(nb, col, rough=0.45, wear=0.35, grime=0.35, stripes=None):
    base = color(col) if isinstance(col, str) else col
    var = nb.noise(nb.coord(0.8), detail=3.0)
    paint = nb.mix(nb.map_range(var, 0.3, 0.7, 0.0, 1.0), _lin(base, 0.9), _lin(base, 1.06))
    if stripes is not None:
        a, b, width = stripes
        x, y, z = nb.sep(nb.coord())
        diag = nb.math("ADD", nb.math("ADD", x, z), y)
        stripe = nb.math("GREATER_THAN", nb.math("FRACT", nb.math("DIVIDE", diag, width)), 0.5)
        paint = nb.mix(stripe, color(a), color(b))
    wear_m, grime_m = _wear_masks(nb, wear, grime)
    steel = color("steel")
    col_out = nb.mix(wear_m, paint, steel)
    col_out = nb.mix(grime_m, col_out, _tint(_lin(base, 0.5), color("rust"), 0.3))
    rough_out = nb.mixf(wear_m, rough, 0.32)
    rough_out = nb.mixf(grime_m, rough_out, 0.85)
    metal_out = nb.mixf(wear_m, 0.0, 1.0)
    peel = nb.noise(nb.coord(180.0), detail=1.0)
    dents = nb.noise(nb.coord(2.5), detail=2.0)
    h = nb.math("ADD", nb.math("MULTIPLY", peel, 0.15), nb.math("MULTIPLY", dents, 0.6))
    h = nb.math("SUBTRACT", h, nb.math("MULTIPLY", wear_m, 0.5))
    nb.surface(col_out, rough_out, metal_out, nb.bump(h, 0.18, 0.01))


def build_metal(nb, col, rough=0.38, grime=0.3, brushed=True):
    base = color(col) if isinstance(col, str) else col
    c = nb.coord((1.0, 1.0, 1.0))
    if brushed:
        streak = nb.noise(nb.coord((3.0, 3.0, 60.0)), detail=2.0)
    else:
        streak = nb.noise(nb.coord(20.0), detail=2.0)
    var = nb.noise(c, scale=1.2, detail=3.0)
    col_out = nb.mix(nb.map_range(var, 0.3, 0.7, 0.0, 1.0), _lin(base, 0.88), _lin(base, 1.08))
    _, grime_m = _wear_masks(nb, 0.0, grime)
    col_out = nb.mix(grime_m, col_out, _tint(_lin(base, 0.4), color("rust"), 0.25))
    rough_out = nb.map_range(streak, 0.3, 0.7, rough - 0.08, rough + 0.1)
    rough_out = nb.mixf(grime_m, rough_out, 0.8)
    h = nb.math("MULTIPLY", streak, 0.3)
    nb.surface(col_out, rough_out, nb.mixf(grime_m, 1.0, 0.6), nb.bump(h, 0.06, 0.01))


def build_rust(nb, _param):
    n1 = nb.noise(nb.coord(2.0), detail=6.0, roughness=0.65)
    n2 = nb.noise(nb.coord(18.0), detail=3.0)
    m = nb.map_range(n1, 0.38, 0.6, 0.0, 1.0)
    col_out = nb.mix(m, color("dark_steel"), color("rust"))
    col_out = nb.mix(nb.map_range(n2, 0.4, 0.7, 0.0, 0.5), col_out, _lin(color("rust"), 0.55))
    rough_out = nb.mixf(m, 0.5, 0.9)
    metal_out = nb.mixf(m, 0.85, 0.15)
    h = nb.math("ADD", nb.math("MULTIPLY", n1, 0.7), nb.math("MULTIPLY", n2, 0.3))
    nb.surface(col_out, rough_out, metal_out, nb.bump(h, 0.35, 0.02))


def build_rubber(nb, col):
    base = color(col) if isinstance(col, str) else color("rubber")
    n = nb.noise(nb.coord(40.0), detail=2.0)
    _, grime_m = _wear_masks(nb, 0.0, 0.25)
    col_out = nb.mix(nb.map_range(n, 0.3, 0.7, 0.0, 1.0), _lin(base, 0.85), _lin(base, 1.15))
    col_out = nb.mix(grime_m, col_out, _tint(base, color("soil"), 0.4))
    nb.surface(col_out, nb.map_range(n, 0.2, 0.8, 0.78, 0.92), 0.0, nb.bump(n, 0.08, 0.01))


def build_plastic(nb, col, rough=0.42):
    base = color(col)
    n = nb.noise(nb.coord(6.0), detail=2.0)
    wear_m, grime_m = _wear_masks(nb, 0.15, 0.2)
    col_out = nb.mix(nb.map_range(n, 0.3, 0.7, 0.0, 1.0), _lin(base, 0.94), _lin(base, 1.05))
    col_out = nb.mix(wear_m, col_out, _tint(base, (0.8, 0.8, 0.8), 0.35))
    col_out = nb.mix(grime_m, col_out, _lin(base, 0.5))
    fine = nb.noise(nb.coord(220.0), detail=1.0)
    nb.surface(col_out, nb.mixf(wear_m, rough, rough + 0.2), 0.0, nb.bump(fine, 0.04, 0.005))


def build_wood(nb, col, weathered=False):
    base = color(col)
    c = nb.coord((1.0, 1.0, 1.0))
    distort = nb.noise(nb.coord((1.5, 6.0, 6.0)), detail=3.0)
    x, y, z = nb.sep(c)
    warped = nb.comb(x, nb.math("ADD", y, nb.math("MULTIPLY", distort, 0.06)),
                     nb.math("ADD", z, nb.math("MULTIPLY", distort, 0.06)))
    grain = nb.wave(warped, scale=14.0, direction="Y", profile="SAW", distortion=4.0, detail=3.0)
    grain2 = nb.wave(warped, scale=9.0, direction="Z", profile="SIN", distortion=6.0, detail=2.0)
    g = nb.math("MULTIPLY", nb.math("ADD", grain, grain2), 0.5)
    dark = _lin(base, 0.62)
    light = _lin(base, 1.12)
    if weathered:
        gray = color("wood_weathered")
        dark = _tint(dark, gray, 0.5)
        light = _tint(light, gray, 0.5)
    col_out = nb.ramp(g, [(0.0, light), (0.55, base), (1.0, dark)])
    knots = nb.voronoi(nb.coord((1.0, 5.0, 5.0)), scale=2.0)
    knot_m = nb.map_range(knots, 0.0, 0.08, 1.0, 0.0)
    col_out = nb.mix(knot_m, col_out, _lin(base, 0.45))
    _, grime_m = _wear_masks(nb, 0.0, 0.35)
    col_out = nb.mix(grime_m, col_out, _lin(base, 0.4))
    rough_out = nb.map_range(g, 0.0, 1.0, 0.62, 0.86)
    nb.surface(col_out, rough_out, 0.0, nb.bump(g, 0.25, 0.01))


def build_concrete(nb, col):
    base = color(col)
    n1 = nb.noise(nb.coord(1.5), detail=5.0, roughness=0.6)
    n2 = nb.noise(nb.coord(25.0), detail=3.0)
    pores = nb.voronoi(nb.coord(60.0), scale=1.0)
    pore_m = nb.map_range(pores, 0.0, 0.12, 1.0, 0.0)
    col_out = nb.mix(nb.map_range(n1, 0.3, 0.7, 0.0, 1.0), _lin(base, 0.86), _lin(base, 1.08))
    col_out = nb.mix(nb.math("MULTIPLY", pore_m, 0.6), col_out, _lin(base, 0.55))
    _, grime_m = _wear_masks(nb, 0.0, 0.45)
    col_out = nb.mix(grime_m, col_out, _tint(_lin(base, 0.5), color("soil"), 0.4))
    h = nb.math("SUBTRACT", nb.math("MULTIPLY", n2, 0.5), nb.math("MULTIPLY", pore_m, 0.4))
    nb.surface(col_out, nb.map_range(n2, 0.3, 0.7, 0.82, 0.95), 0.0, nb.bump(h, 0.25, 0.01))


def build_stone(nb, col, scale=1.0, strata=True):
    base = color(col)
    n1 = nb.noise(nb.coord(0.9 * scale), detail=6.0, roughness=0.62)
    n2 = nb.noise(nb.coord(6.0 * scale), detail=4.0, roughness=0.55)
    # Fracture lines: domain-warped fractal voronoi edges, masked by a low
    # frequency noise so only some cracks show (no regular cell pattern).
    warp = nb.vmath("ADD", nb.coord(2.2 * scale),
                    nb.vmath("SCALE", nb.noise(nb.coord(1.4 * scale), detail=3.0, output="Color"), scale=0.9))
    cr = nb.voronoi(warp, feature="DISTANCE_TO_EDGE", detail=1.5)
    crack = nb.map_range(cr, 0.0, 0.02, 1.0, 0.0)
    crack = nb.math("MULTIPLY", crack, nb.map_range(nb.noise(nb.coord(1.1 * scale), detail=2.0), 0.45, 0.65, 0.0, 1.0))
    col_out = nb.mix(nb.map_range(n1, 0.28, 0.72, 0.0, 1.0), _lin(base, 0.72), _lin(base, 1.15))
    if strata:
        x, y, z = nb.sep(nb.coord())
        band = nb.wave(nb.coord(), scale=1.6 * scale, direction="Z", distortion=5.0, detail=3.0)
        # Darker, slightly iron-stained bands so strata read on every stone colour.
        col_out = nb.mix(nb.math("MULTIPLY", band, 0.45), col_out, _tint(_lin(base, 0.78), color("stone_red"), 0.3))
    col_out = nb.mix(nb.math("MULTIPLY", crack, 0.6), col_out, _lin(base, 0.42))
    up = nb.map_range(nb.up_facing(), 0.55, 0.95, 0.0, 0.45)
    col_out = nb.mix(up, col_out, _tint(_lin(base, 1.1), color("sand"), 0.45))
    _, grime_m = _wear_masks(nb, 0.0, 0.5, scale)
    col_out = nb.mix(grime_m, col_out, _lin(base, 0.4))
    h = nb.math("ADD", nb.math("MULTIPLY", n1, 0.6), nb.math("MULTIPLY", n2, 0.35))
    h = nb.math("SUBTRACT", h, nb.math("MULTIPLY", crack, 0.35))
    nb.surface(col_out, nb.map_range(n2, 0.3, 0.7, 0.72, 0.92), 0.0, nb.bump(h, 0.55, 0.03))


def build_soil(nb, col, pebbles=0.3):
    base = color(col)
    n1 = nb.noise(nb.coord(1.2), detail=6.0, roughness=0.6)
    n2 = nb.noise(nb.coord(12.0), detail=3.0)
    peb = nb.voronoi(nb.coord(14.0), feature="SMOOTH_F1")
    peb_m = nb.map_range(peb, 0.0, 0.35, pebbles * 1.5, 0.0)
    col_out = nb.mix(nb.map_range(n1, 0.3, 0.7, 0.0, 1.0), _lin(base, 0.78), _lin(base, 1.12))
    col_out = nb.mix(peb_m, col_out, color("gravel"))
    h = nb.math("ADD", nb.math("MULTIPLY", n2, 0.4), peb_m)
    nb.surface(col_out, 0.92, 0.0, nb.bump(h, 0.35, 0.02))


def build_coal(nb, _param):
    v = nb.voronoi(nb.coord(9.0), feature="F1", output="Distance")
    cells = nb.voronoi(nb.coord(9.0), feature="F1", output="Color")
    n = nb.noise(nb.coord(30.0), detail=2.0)
    base = color("coal")
    col_out = nb.mix(nb.map_range(n, 0.3, 0.8, 0.0, 1.0), _lin(base, 0.8), _lin(base, 1.9))
    rough_out = nb.map_range(cells, 0.0, 1.0, 0.18, 0.6)
    nb.surface(col_out, rough_out, 0.0, nb.bump(v, 0.6, 0.02))


def build_ore(nb, host, ore, metal_flecks, fleck_color, vein_scale=4.0):
    n = nb.noise(nb.coord(vein_scale), detail=5.0, roughness=0.6, distortion=0.4)
    band = nb.wave(nb.coord(), scale=3.0, direction="Z", distortion=8.0, detail=4.0)
    m = nb.map_range(nb.math("ADD", n, nb.math("MULTIPLY", band, 0.3)), 0.45, 0.7, 0.0, 1.0)
    col_out = nb.mix(m, color(host), color(ore))
    fl = nb.voronoi(nb.coord(40.0), feature="F1")
    fleck = nb.math("MULTIPLY", nb.map_range(fl, 0.0, 0.12, 1.0, 0.0), metal_flecks)
    col_out = nb.mix(fleck, col_out, color(fleck_color))
    _, grime_m = _wear_masks(nb, 0.0, 0.4)
    col_out = nb.mix(grime_m, col_out, _lin(color(host), 0.4))
    rough_out = nb.mixf(fleck, nb.mixf(m, 0.85, 0.6), 0.3)
    nb.surface(col_out, rough_out, nb.mixf(fleck, 0.0, 0.9), nb.bump(n, 0.5, 0.02))


def build_precious(nb, col, rough=0.28):
    base = color(col)
    n = nb.noise(nb.coord(14.0), detail=4.0)
    col_out = nb.mix(nb.map_range(n, 0.3, 0.7, 0.0, 1.0), _lin(base, 0.8), _lin(base, 1.1))
    _, grime_m = _wear_masks(nb, 0.0, 0.3)
    col_out = nb.mix(grime_m, col_out, _lin(base, 0.45))
    nb.surface(col_out, nb.map_range(n, 0.3, 0.7, rough - 0.08, rough + 0.12), 1.0, nb.bump(n, 0.35, 0.01))


def build_crystal(nb, col, glow=None):
    base = color(col)
    x, y, z = nb.sep(nb.coord())
    grad = nb.map_range(z, 0.0, 0.6, 0.0, 1.0)
    col_out = nb.mix(grad, _lin(base, 0.45), _tint(base, (1.0, 1.0, 1.0), 0.25))
    n = nb.noise(nb.coord(8.0), detail=2.0)
    emission = None
    if glow is not None:
        emission = nb.mix(grad, _lin(color(glow), 0.35), color(glow))
    nb.surface(col_out, nb.map_range(n, 0.3, 0.7, 0.05, 0.18), 0.0, nb.bump(n, 0.08, 0.01), specular=0.9,
               emission=emission, emission_strength=1.0 if glow is not None else None)


def build_fabric(nb, col, weave=160.0, rough=0.9):
    base = color(col)
    c = nb.coord()
    w1 = nb.wave(c, scale=weave, direction="X", detail=0.0)
    w2 = nb.wave(c, scale=weave, direction="Z", detail=0.0)
    weave_h = nb.math("MULTIPLY", nb.math("ADD", w1, w2), 0.5)
    n = nb.noise(nb.coord(3.0), detail=3.0)
    col_out = nb.mix(nb.map_range(n, 0.3, 0.7, 0.0, 1.0), _lin(base, 0.88), _lin(base, 1.08))
    col_out = nb.mix(nb.math("MULTIPLY", weave_h, 0.18), col_out, _lin(base, 0.7))
    _, grime_m = _wear_masks(nb, 0.0, 0.25)
    col_out = nb.mix(grime_m, col_out, _tint(_lin(base, 0.55), color("soil"), 0.3))
    nb.surface(col_out, rough, 0.0, nb.bump(weave_h, 0.12, 0.004))


def build_denim(nb, col):
    base = color(col)
    c = nb.coord()
    tw = nb.wave(c, scale=220.0, direction="DIAGONAL", detail=0.0)
    fade = nb.noise(nb.coord(2.5), detail=4.0)
    col_out = nb.mix(nb.map_range(fade, 0.3, 0.75, 0.0, 1.0), _lin(base, 0.85), _tint(base, (0.8, 0.85, 0.9), 0.3))
    col_out = nb.mix(nb.math("MULTIPLY", tw, 0.22), col_out, _lin(base, 0.65))
    wear_m, grime_m = _wear_masks(nb, 0.2, 0.25)
    col_out = nb.mix(wear_m, col_out, _tint(base, (0.9, 0.9, 0.9), 0.4))
    nb.surface(col_out, 0.88, 0.0, nb.bump(tw, 0.12, 0.004))


def build_reflective(nb, _param):
    base = color("reflective_silver")
    n = nb.noise(nb.coord(300.0), detail=1.0)
    nb.surface(base, nb.map_range(n, 0.3, 0.7, 0.28, 0.4), 0.35, nb.bump(n, 0.05, 0.003))


def build_leather(nb, col):
    base = color(col)
    g = nb.voronoi(nb.coord(90.0), feature="F1")
    n = nb.noise(nb.coord(4.0), detail=3.0)
    wear_m, grime_m = _wear_masks(nb, 0.35, 0.3)
    col_out = nb.mix(nb.map_range(n, 0.3, 0.7, 0.0, 1.0), _lin(base, 0.85), _lin(base, 1.12))
    col_out = nb.mix(wear_m, col_out, _lin(base, 1.35))
    col_out = nb.mix(grime_m, col_out, _lin(base, 0.5))
    nb.surface(col_out, nb.mixf(wear_m, 0.6, 0.45), 0.0, nb.bump(g, 0.1, 0.004))


def build_skin(nb, col):
    """Body skin (hands, forearms). Pattern coordinates are world-space."""
    base = color(col)
    n = nb.noise(nb.coord(9.0), detail=3.0)
    col_out = nb.mix(nb.map_range(n, 0.3, 0.7, 0.0, 1.0), _lin(base, 0.95), _lin(base, 1.04))
    ao = nb.ao_mask()
    col_out = nb.mix(nb.map_range(ao, 0.4, 0.95, 0.6, 0.0), col_out, _tint(_lin(base, 0.6), (0.5, 0.2, 0.2), 0.2))
    pores = nb.noise(nb.coord(400.0), detail=1.0)
    nb.surface(col_out, nb.map_range(n, 0.3, 0.7, 0.5, 0.62), 0.0, nb.bump(pores, 0.03, 0.002))


def build_face(nb, col):
    """Head skin with painted features in head-local coordinates (origin at the
    face center, -Y forward): warm cheeks/nose, lips and a soft mouth line."""
    base = color(col)
    x, y, z = nb.sep(nb.coord())
    n = nb.noise(nb.coord(9.0), detail=3.0)
    col_out = nb.mix(nb.map_range(n, 0.3, 0.7, 0.0, 1.0), _lin(base, 0.95), _lin(base, 1.04))
    front = nb.map_range(y, -0.03, -0.1, 0.0, 1.0, smooth=True)
    blush = _tint(base, (0.8, 0.3, 0.26), 0.16)
    col_out = nb.mix(nb.math("MULTIPLY", front, 0.6), col_out, blush)

    def ellipse(cx, cz, rx, rz):
        dx = nb.math("DIVIDE", nb.math("SUBTRACT", x, cx), rx)
        dz = nb.math("DIVIDE", nb.math("SUBTRACT", z, cz), rz)
        d2 = nb.math("ADD", nb.math("MULTIPLY", dx, dx), nb.math("MULTIPLY", dz, dz))
        return nb.math("MULTIPLY", nb.math("EXPONENT", nb.math("MULTIPLY", d2, -1.0)), front)

    lips = ellipse(0.0, -0.066, 0.021, 0.0085)
    lip_col = _tint(_lin(base, 0.86), (0.62, 0.22, 0.22), 0.3)
    col_out = nb.mix(nb.map_range(lips, 0.25, 0.6, 0.0, 1.0), col_out, lip_col)
    line = ellipse(0.0, -0.0655, 0.018, 0.0016)
    col_out = nb.mix(nb.map_range(line, 0.3, 0.8, 0.0, 0.85), col_out, _lin(lip_col, 0.35))
    ao = nb.ao_mask()
    col_out = nb.mix(nb.map_range(ao, 0.4, 0.95, 0.6, 0.0), col_out, _tint(_lin(base, 0.6), (0.5, 0.2, 0.2), 0.2))
    pores = nb.noise(nb.coord(400.0), detail=1.0)
    rough = nb.mixf(nb.map_range(lips, 0.3, 0.7, 0.0, 1.0), nb.map_range(n, 0.3, 0.7, 0.48, 0.6), 0.36)
    nb.surface(col_out, rough, 0.0, nb.bump(pores, 0.03, 0.002))


def build_lips(nb, col):
    base = _tint(_lin(color(col), 0.85), (0.6, 0.2, 0.2), 0.3)
    n = nb.noise(nb.coord(60.0), detail=2.0)
    col_out = nb.mix(nb.map_range(n, 0.3, 0.7, 0.0, 1.0), _lin(base, 0.88), _lin(base, 1.0))
    nb.surface(col_out, 0.42, 0.0, nb.bump(n, 0.05, 0.002))


def build_hair(nb, col):
    base = color(col)
    strands = nb.noise(nb.coord((90.0, 90.0, 9.0)), detail=2.0)
    clump = nb.noise(nb.coord((12.0, 12.0, 3.0)), detail=2.0)
    col_out = nb.mix(nb.map_range(strands, 0.3, 0.7, 0.0, 1.0), _lin(base, 0.72), _tint(_lin(base, 1.25), (0.9, 0.85, 0.7), 0.08))
    col_out = nb.mix(nb.math("MULTIPLY", clump, 0.4), col_out, _lin(base, 0.6))
    h = nb.math("ADD", strands, nb.math("MULTIPLY", clump, 0.5))
    nb.surface(col_out, nb.map_range(strands, 0.3, 0.7, 0.42, 0.62), 0.0, nb.bump(h, 0.35, 0.004))


def build_eye(nb, iris_col):
    """Eye with sclera/iris/pupil drawn from eye-local pattern coordinates (gaze = -Y)."""
    x, y, z = nb.sep(nb.coord())
    d = nb.math("SQRT", nb.math("ADD", nb.math("MULTIPLY", x, x), nb.math("MULTIPLY", z, z)))
    front = nb.math("LESS_THAN", y, 0.0)
    r = 0.0125  # eye radius used by the head generator
    iris_m = nb.math("MULTIPLY", nb.map_range(d, r * 0.56, r * 0.5, 0.0, 1.0), front)
    pupil_m = nb.math("MULTIPLY", nb.map_range(d, r * 0.26, r * 0.22, 0.0, 1.0), front)
    radial = nb.noise(nb.coord(900.0), detail=1.0)
    iris = nb.mix(nb.map_range(radial, 0.3, 0.7, 0.0, 1.0), _lin(color(iris_col), 0.7), _lin(color(iris_col), 1.3))
    col_out = nb.mix(iris_m, color("eye_white"), iris)
    col_out = nb.mix(pupil_m, col_out, color("pupil"))
    nb.surface(col_out, 0.12, 0.0, None, specular=0.8)


def build_glass(nb, _param):
    nb.surface(color("glass_tint"), 0.06, 0.0, None, alpha=0.32, specular=0.9)


def build_emit(nb, col, strength=3.0):
    c = color(col)
    nb.surface(c, 0.4, 0.0, None, emission=c, emission_strength=strength)


# ------------------------------------------------------------------ registry

FIXED = {
    "steel": ("metal", lambda nb: build_metal(nb, "steel")),
    "steel_dark": ("metal", lambda nb: build_metal(nb, "dark_steel", rough=0.45)),
    "gunmetal": ("metal", lambda nb: build_metal(nb, "gunmetal", rough=0.5, brushed=False)),
    "galvanized": ("metal", lambda nb: build_metal(nb, "galvanized", rough=0.42, brushed=False)),
    "chrome": ("metal", lambda nb: build_metal(nb, "chrome", rough=0.16, grime=0.15)),
    "copper": ("metal", lambda nb: build_metal(nb, "copper_metal", rough=0.32)),
    "brass": ("metal", lambda nb: build_metal(nb, "brass", rough=0.35)),
    "rust": ("rust", lambda nb: build_rust(nb, None)),
    "rubber": ("rubber", lambda nb: build_rubber(nb, "rubber")),
    "concrete": ("concrete", lambda nb: build_concrete(nb, "concrete")),
    "concrete_dark": ("concrete", lambda nb: build_concrete(nb, "concrete_dark")),
    "coal": ("coal", lambda nb: build_coal(nb, None)),
    "ore_iron": ("ore", lambda nb: build_ore(nb, "host_rock", "iron_ore", 0.35, "iron_metal")),
    "ore_copper": ("ore", lambda nb: build_ore(nb, "host_rock", "copper_ore", 0.4, "copper_metal", 5.0)),
    "ore_silver": ("ore", lambda nb: build_ore(nb, "host_rock", "silver_ore", 0.6, "silver_metal", 6.0)),
    "ore_uranium": ("ore", lambda nb: build_ore(nb, "stone_dark", "uranium", 0.1, "uranium", 5.0)),
    "gold": ("precious", lambda nb: build_precious(nb, "gold_metal", 0.26)),
    "silver": ("precious", lambda nb: build_precious(nb, "silver_metal", 0.22)),
    "iron_metal": ("precious", lambda nb: build_precious(nb, "iron_metal", 0.4)),
    "crystal_amethyst": ("crystal", lambda nb: build_crystal(nb, "amethyst")),
    "crystal_diamond": ("crystal", lambda nb: build_crystal(nb, "diamond")),
    "crystal_uranium": ("crystal", lambda nb: build_crystal(nb, "uranium")),
    "crystal_uranium_glow": ("crystal", lambda nb: build_crystal(nb, "uranium", glow="emissive_uranium")),
    "crystal_amethyst_glow": ("crystal", lambda nb: build_crystal(nb, "amethyst", glow="emissive_crystal")),
    "reflective": ("reflective", lambda nb: build_reflective(nb, None)),
    "hazard": ("paint", lambda nb: build_paint(nb, "industrial_yellow", wear=0.4, stripes=("industrial_yellow", "hazard_black", 0.22))),
    "rubber_sole": ("rubber", lambda nb: build_rubber(nb, "rubber_sole")),
    "glass": ("glass", lambda nb: build_glass(nb, None)),
}

PARAMETRIC = {
    "paint": ("paint", lambda nb, c: build_paint(nb, c)),
    "paint_worn": ("paint", lambda nb, c: build_paint(nb, c, wear=0.55, grime=0.4, rough=0.52)),
    "paint_clean": ("paint", lambda nb, c: build_paint(nb, c, wear=0.08, grime=0.15, rough=0.35)),
    "metal": ("metal", lambda nb, c: build_metal(nb, c)),
    "plastic": ("plastic", lambda nb, c: build_plastic(nb, c)),
    "plastic_gloss": ("plastic", lambda nb, c: build_plastic(nb, c, rough=0.25)),
    "rubber": ("rubber", lambda nb, c: build_rubber(nb, c)),
    "wood": ("wood", lambda nb, c: build_wood(nb, c)),
    "wood_weathered": ("wood", lambda nb, c: build_wood(nb, c, weathered=True)),
    "concrete": ("concrete", lambda nb, c: build_concrete(nb, c)),
    "stone": ("stone", lambda nb, c: build_stone(nb, c)),
    "stone_fine": ("stone", lambda nb, c: build_stone(nb, c, scale=2.2, strata=False)),
    "soil": ("soil", lambda nb, c: build_soil(nb, c)),
    "gravel": ("soil", lambda nb, c: build_soil(nb, c, pebbles=0.9)),
    "fabric": ("fabric", lambda nb, c: build_fabric(nb, c)),
    "knit": ("fabric", lambda nb, c: build_fabric(nb, c, weave=90.0, rough=0.95)),
    "denim": ("fabric", lambda nb, c: build_denim(nb, c)),
    "leather": ("leather", lambda nb, c: build_leather(nb, c)),
    "skin": ("skin", lambda nb, c: build_skin(nb, c)),
    "face": ("skin", lambda nb, c: build_face(nb, c)),
    "hair": ("hair", lambda nb, c: build_hair(nb, c)),
    "lips": ("skin", lambda nb, c: build_lips(nb, c)),
    "eye": ("eye", lambda nb, c: build_eye(nb, c)),
    "foliage": ("fabric", lambda nb, c: build_fabric(nb, c, weave=40.0, rough=0.8)),
    "emit": ("emit", lambda nb, c: build_emit(nb, c)),
    "emit_soft": ("emit", lambda nb, c: build_emit(nb, c, strength=1.5)),
}

# Glass stays a separate (alpha-blended) material; emissive colours are baked
# into the atlas's emissive map so lamps do not add draw calls.
NON_BAKED_KINDS = {"glass"}


class MaterialLibrary:
    """Creates library materials on demand inside the current (reset) scene."""

    def __init__(self):
        self.info = {}

    def resolve(self, key):
        if key in FIXED:
            kind, fn = FIXED[key]
            return kind, (lambda nb: fn(nb))
        if ":" in key:
            kind_key, param = key.split(":", 1)
            if kind_key in PARAMETRIC:
                kind, fn = PARAMETRIC[kind_key]
                color(param)  # validates the palette key
                return kind, (lambda nb: fn(nb, param))
        raise ConfigError(f"unknown material key '{key}'")

    def get(self, key):
        name = "M_" + key.replace(":", "_")
        mat = bpy.data.materials.get(name)
        if mat is not None and mat.get("mm_key") == key:
            return mat
        kind, fn = self.resolve(key)
        mat = bpy.data.materials.new(name)
        nb = NB(mat)
        fn(nb)
        mat["mm_key"] = key
        mat["mm_kind"] = kind
        mat["mm_baked"] = kind not in NON_BAKED_KINDS
        if kind == "glass":
            mat.surface_render_method = "BLENDED"
            mat.use_backface_culling = False
        self.info[key] = MatInfo(key, kind, kind not in NON_BAKED_KINDS, "BLEND" if kind == "glass" else "OPAQUE")
        return mat

    @staticmethod
    def is_baked(mat):
        return bool(mat.get("mm_baked", True))
