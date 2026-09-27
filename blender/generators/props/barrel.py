"""Steel oil drum (55 US gal) and wooden barrel.

Construction rules: rolled top/bottom chimes, two rolling hoops at 1/3 and 2/3
height, lid with 2" and 3/4" bungs. Origin at the base center.
"""

import math

from utilities.meshkit import trs


def build(ctx):
    style = ctx.param("style", "steel")
    if style == "wood":
        return _wood(ctx)
    color = ctx.param("color", "signal_red")
    h = ctx.param("height", 0.88)
    r = ctx.param("radius", 0.292)
    body = ctx.geo("drum")
    lip = 0.014
    hoop_z = (h * 0.34, h * 0.66)
    prof = [(0.0, 0.004), (r - 0.018, 0.004), (r - 0.006, 0.0), (r + 0.004, 0.006), (r + 0.004, 0.022),
            (r, 0.03)]
    for hz in hoop_z:
        prof += [(r, hz - 0.018), (r + lip, hz - 0.008), (r + lip, hz + 0.008), (r, hz + 0.018)]
    prof += [(r, h - 0.03), (r + 0.004, h - 0.022), (r + 0.004, h - 0.006), (r - 0.006, h),
             (r - 0.018, h - 0.004), (r - 0.022, h - 0.012), (0.0, h - 0.012)]
    body.lathe(prof, segments=40, mat=f"paint:{color}")
    # Bungs on the lid.
    det = ctx.geo("bungs", max_lod=0)
    for (bx, br) in ((r * 0.55, 0.032), (-r * 0.55, 0.018)):
        det.cylinder(br, 0.014, segments=16, matrix=trs((bx, 0.0, h - 0.012 + 0.007)), mat="steel_dark",
                     bevel=0.003)
        det.cylinder(br * 0.55, 0.01, segments=6, matrix=trs((bx, 0.0, h - 0.012 + 0.018)), mat="steel_dark",
                     bevel=0.002)
    ctx.col_cylinder((0.0, 0.0, h / 2), r + lip, h, segments=12)


def _wood(ctx):
    h = ctx.param("height", 0.9)
    r_mid = ctx.param("radius", 0.33)
    r_end = r_mid * 0.84
    staves = 18
    body = ctx.geo("staves")
    rng = ctx.rng.child("staves")
    for i in range(staves):
        a0 = 2 * math.pi * i / staves
        a1 = 2 * math.pi * (i + 0.94) / staves
        rows = 7
        verts = []
        for k in range(rows + 1):
            z = h * k / rows
            bulge = r_end + (r_mid - r_end) * math.sin(math.pi * z / h)
            for a in (a0, a1):
                verts.append((bulge * math.cos(a), bulge * math.sin(a), z))
        faces = []
        inner = []
        t = 0.022
        for k in range(rows + 1):
            z = h * k / rows
            bulge = r_end + (r_mid - r_end) * math.sin(math.pi * z / h) - t
            for a in (a0, a1):
                inner.append((bulge * math.cos(a), bulge * math.sin(a), z))
        allv = verts + inner
        n = len(verts)
        for k in range(rows):
            a, b, c, d = 2 * k, 2 * k + 1, 2 * k + 3, 2 * k + 2
            faces.append((a, b, c, d))
            faces.append((n + b, n + a, n + d, n + c))
            faces.append((a, d, n + d, n + a))
            faces.append((b, n + b, n + c, c))
        faces.append((0, n + 0, n + 1, 1))
        top = 2 * rows
        faces.append((top, top + 1, n + top + 1, n + top))
        body.mesh(allv, faces, mat="wood:wood_dark", pattern_offset=(rng.uniform(0, 9), 0, 0))
    lids = ctx.geo("lids")
    for z in (0.02, h - 0.02):
        lids.cylinder(r_end - 0.02, 0.03, segments=24, matrix=trs((0, 0, z)), mat="wood:wood_light", bevel=0.004)
    hoops = ctx.geo("hoops")
    for z in (0.06, h * 0.3, h * 0.7, h - 0.06):
        rr = r_end + (r_mid - r_end) * math.sin(math.pi * z / h) + 0.004
        hoops.tube(rr + 0.006, rr - 0.002, 0.035, segments=32, matrix=trs((0, 0, z)), mat="steel_dark", bevel=0.002)
    ctx.col_cylinder((0.0, 0.0, h / 2), r_mid + 0.01, h, segments=12)
