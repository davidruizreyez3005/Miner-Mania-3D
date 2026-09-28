"""Site props: pallet, gas cylinder, ore sack, traffic cone, workbench and a
bench seat. ``kind`` selects the prop.

Contract dimensions: the bench seat height equals the animation contract's
``seat_height`` (the worker Sit clip puts the pelvis there) and the workbench
top equals ``load_surface`` height, so worker interactions line up.
"""

import math

import bmesh
from mathutils import Matrix, Vector, noise

from core import config
from utilities.meshkit import trs, uv_sphere

from .. import kit

WOOD = "wood:wood_light"


def build(ctx):
    fn = globals().get(f"_{ctx.param('kind')}")
    if fn is None:
        raise ValueError(f"unknown prop kind {ctx.param('kind')!r}")
    fn(ctx)


def _pallet(ctx):
    """EUR pallet 1200 x 800 x 144 mm: three bottom boards and five top deck
    boards along the length, three stringer boards across, nine blocks."""
    L, W = 1.2, 0.8
    g = ctx.geo("pallet")
    det = ctx.geo("nails", max_lod=0)
    rng = ctx.rng.child("boards")
    wood = ctx.param("wood", WOOD)
    po = lambda: (rng.uniform(0, 10), rng.uniform(0, 10), 0.0)
    board = dict(mat=wood, bevel=0.003, segments=1)
    for y, bw in ((-(W / 2 - 0.05), 0.1), (0.0, 0.145), (W / 2 - 0.05, 0.1)):
        g.box((L, bw, 0.022), matrix=trs((0.0, y, 0.011)), pattern_offset=po(), **board)              # bottom boards
    for x in (-(L / 2 - 0.05), 0.0, L / 2 - 0.05):
        for y in (-(W / 2 - 0.05), 0.0, W / 2 - 0.05):
            g.box((0.145 if x == 0.0 else 0.1, 0.145 if y == 0.0 else 0.1, 0.078), matrix=trs((x, y, 0.061)),
                  mat=wood, bevel=0.004, segments=1, pattern_offset=po())                         # blocks
        g.box((0.145 if x == 0.0 else 0.1, W, 0.022), matrix=trs((x, 0.0, 0.111)), pattern_offset=po(), **board)   # stringers
    deck = ((-0.3275, 0.145), (-0.1638, 0.1), (0.0, 0.145), (0.1638, 0.1), (0.3275, 0.145))
    for y, bw in deck:
        g.box((L, bw, 0.022), matrix=trs((0.0, y, 0.133)), pattern_offset=po(), **board)              # top deck
        for x in (-(L / 2 - 0.05), 0.0, L / 2 - 0.05):
            det.cylinder(0.006, 0.002, segments=6, matrix=trs((x, y, 0.1445)), mat="steel_dark")
    ctx.col_box((0.0, 0.0, 0.072), (L, W, 0.144))
    ctx.socket("load", (0.0, 0.0, 0.144))
    ctx.socket("fork_front", (0.0, -W / 2 - 0.6, 0.0), (0.0, 0.0, 180.0))


def _gas_cylinder(ctx):
    """Industrial gas cylinder with valve guard (carryable)."""
    col = ctx.param("color", "machine_blue")
    g = ctx.geo("cylinder")
    r, h = 0.115, 1.15
    prof = [(0.0, 0.0), (r * 0.8, 0.0), (r, 0.03), (r, h - 0.12), (r * 0.72, h - 0.04), (0.035, h), (0.0, h)]
    g.lathe(prof, segments=20, mat=f"paint_worn:{col}")
    g.torus(r + 0.004, 0.006, seg_major=20, seg_minor=4, matrix=trs((0.0, 0.0, 0.25)), mat="paint:white_paint")
    g.cylinder(0.02, 0.06, segments=10, matrix=trs((0.0, 0.0, h + 0.03)), mat="brass", bevel=0.004)
    g.cylinder(0.012, 0.05, segments=8, matrix=trs((0.03, 0.0, h + 0.04), (0, 90, 0)), mat="brass")
    g.lathe([(0.06, h - 0.03), (0.075, h - 0.03), (0.075, h + 0.1), (0.06, h + 0.1)], segments=16, mat=kit.DARK, caps=False,
            closed_loop=True)
    ctx.col_cylinder((0.0, 0.0, h / 2), r, h, segments=12)


def _ore_sack(ctx):
    """Filled jute sack, tied at the neck (a slumped, lumpy bag)."""
    g = ctx.geo("sack")
    rng = ctx.rng.child("sack")
    tmp = bmesh.new()
    uv_sphere(tmp, 20, 12, 1.0)
    off = Vector((rng.uniform(-9, 9), rng.uniform(-9, 9), rng.uniform(-9, 9)))
    for v in tmp.verts:
        d = v.co.copy()
        z01 = (d.z + 1.0) / 2                                           # 0 bottom .. 1 top
        rxy = math.hypot(d.x, d.y)
        direction = Vector((d.x / rxy, d.y / rxy, 0.0)) if rxy > 1e-6 else Vector()
        neck = 1.0 - 0.7 * max(0.0, z01 - 0.7) / 0.3                    # gathers to the tied neck
        base = min(1.0, rxy / 0.55) if z01 < 0.5 else 1.0               # rounded bottom edge
        r = 0.24 * neck * base * (1.0 + 0.12 * (1.0 - z01)) * (1.0 + 0.08 * noise.noise(d * 2.5 + off))
        v.co = direction * r + Vector((0.0, 0.0, 0.62 * max(0.0, (z01 - 0.06) / 0.94)))
    bmesh.ops.recalc_face_normals(tmp, faces=list(tmp.faces))
    g._append(tmp, Matrix.Identity(4), "fabric:canvas_tan", (rng.uniform(0, 9), rng.uniform(0, 9), 0.0))
    g.lathe([(0.05, 0.6), (0.075, 0.62), (0.07, 0.72), (0.03, 0.74), (0.0, 0.74)], segments=12, mat="fabric:canvas_tan")
    g.torus(0.056, 0.012, seg_major=12, seg_minor=5, matrix=trs((0.0, 0.0, 0.6)), mat="fabric:work_brown")
    ctx.col_cylinder((0.0, 0.0, 0.31), 0.25, 0.62, segments=10)


def _cone(ctx):
    """Traffic cone with reflective bands."""
    g = ctx.geo("cone")
    g.box((0.38, 0.38, 0.03), matrix=trs((0.0, 0.0, 0.015)), mat="rubber:hazard_black", bevel=0.01)
    g.lathe([(0.0, 0.03), (0.15, 0.03), (0.035, 0.72), (0.0, 0.72)], segments=20, mat="plastic_gloss:safety_orange")
    for z0, z1 in ((0.3, 0.38), (0.48, 0.54)):
        r0, r1 = 0.15 - 0.115 * (z0 - 0.03) / 0.69, 0.15 - 0.115 * (z1 - 0.03) / 0.69
        g.lathe([(r0 + 0.002, z0), (r1 + 0.002, z1)], segments=20, mat="reflective", caps=False)
    ctx.col_cylinder((0.0, 0.0, 0.36), 0.16, 0.72, segments=10)


def _workbench(ctx):
    """Steel-framed workbench; top at the contract load-surface height."""
    h = config.animation_spec()["interaction_points"]["load_surface"][2]
    L, W = 1.8, 0.75
    g = ctx.geo("bench")
    det = ctx.geo("bench_detail", max_lod=1)
    g.box((L, W, 0.05), matrix=trs((0.0, 0.0, h - 0.025)), mat="wood:wood_dark", bevel=0.006)
    kit.frame_box(g, (-L / 2 + 0.04, -W / 2 + 0.04, 0.0), (L / 2 - 0.04, W / 2 - 0.04, h - 0.05), bar=0.05, mat="paint_worn:machine_blue")
    g.box((L - 0.12, W - 0.12, 0.025), matrix=trs((0.0, 0.0, 0.22)), mat="wood:wood_dark", bevel=0.004)
    g.box((0.45, W - 0.1, 0.5), matrix=trs((L / 2 - 0.3, 0.0, h - 0.33)), mat="paint_worn:machine_blue", bevel=0.01)     # drawers
    for k in range(3):
        det.box((0.4, 0.01, 0.14), matrix=trs((L / 2 - 0.3, -W / 2 + 0.045, h - 0.15 - 0.16 * k)), mat="paint_worn:machine_blue",
                bevel=0.003)
        det.box((0.12, 0.02, 0.02), matrix=trs((L / 2 - 0.3, -W / 2 + 0.03, h - 0.15 - 0.16 * k)), mat="chrome", bevel=0.003)
    vx = -L / 2 + 0.2                                                   # bench vise
    det.box((0.2, 0.14, 0.1), matrix=trs((vx, -W / 2 + 0.05, h + 0.05)), mat="paint_worn:signal_red", bevel=0.01)
    det.cylinder(0.012, 0.28, segments=8, matrix=trs((vx, -W / 2 - 0.05, h + 0.05), (90, 0, 0)), mat="steel")
    ctx.col_box((0.0, 0.0, h / 2), (L, W, h))
    reach = -config.animation_spec()["interaction_points"]["load_surface"][1]
    ctx.socket("work", (0.0, -W / 2 - reach + 0.15, 0.0), (0.0, 0.0, 180.0))      # hands 0.15 m in from the edge


def _bench_seat(ctx):
    """Slatted bench; seat top at the contract seat height (Sit clip)."""
    sh = config.animation_spec()["interaction_points"]["seat_height"]
    L, D = 1.6, 0.42
    g = ctx.geo("bench")
    for k in range(4):
        g.box((L, 0.09, 0.03), matrix=trs((0.0, -D / 2 + 0.055 + 0.103 * k, sh - 0.015)), mat="wood:wood_light", bevel=0.005)
    for k in range(2):                                                  # backrest slats
        g.box((L, 0.03, 0.09), matrix=trs((0.0, D / 2 - 0.02 + 0.03 * k, sh + 0.2 + 0.12 * k), (-12, 0, 0)), mat="wood:wood_light",
              bevel=0.005)
    for x in (-L / 2 + 0.12, L / 2 - 0.12):                             # cast side frames: legs, rail, backrest
        pts = [(-0.19, 0.0), (-0.13, 0.0), (-0.11, sh - 0.1), (0.09, sh - 0.1), (0.11, 0.0), (0.17, 0.0), (0.15, sh - 0.03),
               (0.24, sh + 0.42), (0.19, sh + 0.42), (0.11, sh - 0.03), (-0.19, sh - 0.03)]
        g.extrude(pts, 0.04, matrix=Matrix(((0.0, 0.0, 1.0, x - 0.02), (1.0, 0.0, 0.0, 0.0), (0.0, 1.0, 0.0, 0.0), (0.0, 0.0, 0.0, 1.0))),
                  mat="paint_worn:dark_steel")
    ctx.col_box((0.0, 0.0, sh / 2), (L, D, sh))
    ctx.col_box((0.0, D / 2 + 0.02, sh + 0.25), (L, 0.08, 0.4))
    seat_y = config.animation_spec()["interaction_points"]["seat_point"][1]
    ctx.socket("seat", (0.0, -seat_y, 0.0))                             # Sit clip lands the pelvis on the slats
