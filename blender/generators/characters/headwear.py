"""Headwear, built in character space and attached rigidly to the
``helmet_attachment`` socket (exported as a swappable node; Godot creates a
BoneAttachment3D). The same builders produce the standalone equipment GLBs
(origin moved to the socket point).

Construction rules: hard hats are a thin shell (outer + inner wall, so the
underside reads correctly), a brim that extends at the front, three
reinforcing ribs, and an optional miner's lamp (housing, emissive lens,
bracket, cable). Clearance over the head + hair is >= 12 mm.
"""

import math

from mathutils import Matrix, Vector

from utilities.meshkit import Geo, frame_from_axis, trs

SOCKET = Vector((0.0, 0.004, 1.69))
BASE_Z = 1.698          # rim of the helmet shell (just above the brows)
CENTER_Y = 0.008


def _dome_profile(r0, h, thickness):
    outer = []
    steps = 8
    for i in range(steps + 1):
        t = i / steps
        a = t * math.pi / 2
        outer.append((r0 * math.cos(a) * (1.0 - 0.06 * t), h * math.sin(a)))
    outer[-1] = (0.0, h)
    inner = [(max(0.0, r - thickness), max(0.0, z - thickness)) for r, z in reversed(outer)]
    inner[0] = (0.0, h - thickness)
    return outer + inner


def hardhat(geo_main, geo_detail, color_key, lamp=False, ribs=True):
    shell_key = f"plastic_gloss:{color_key}"
    sx, sy = 0.97, 1.1
    m = trs((0.0, CENTER_Y, BASE_Z), scale=(sx, sy, 1.0))
    prof = _dome_profile(0.103, 0.118, 0.006)
    geo_main.lathe(prof, segments=28, matrix=m, mat=shell_key, closed_loop=True, caps=False)
    # Brim: flat band, longer at the front (visor).
    n = 28
    outer, inner = [], []
    for k in range(n):
        a = 2 * math.pi * k / n
        c, s = math.cos(a), math.sin(a)
        front = max(0.0, -s)            # -Y is the front
        r_out = 0.118 + 0.028 * front ** 2 + 0.006 * abs(c)
        r_in = 0.1
        outer.append(Vector((r_out * c * sx, r_out * s * sy + CENTER_Y, 0.0)))
        inner.append(Vector((r_in * c * sx, r_in * s * sy + CENTER_Y, 0.0)))
    verts, faces = [], []
    for k in range(n):
        o, i = outer[k], inner[k]
        droop = 0.006 * max(0.0, -math.sin(2 * math.pi * k / n))
        verts += [(o.x, o.y, BASE_Z - 0.002 - droop), (o.x, o.y, BASE_Z + 0.004 - droop),
                  (i.x, i.y, BASE_Z + 0.012), (i.x, i.y, BASE_Z - 0.004)]
    for k in range(n):
        a = 4 * k
        b = 4 * ((k + 1) % n)
        for j in range(4):
            j2 = (j + 1) % 4
            faces.append((a + j, b + j, b + j2, a + j2))
    geo_main.mesh(verts, faces, mat=shell_key)
    if ribs:
        for off in (-0.028, 0.0, 0.028):
            path = []
            for i in range(9):
                t = i / 8.0
                ang = math.pi * (0.12 + 0.76 * t)
                y = -math.cos(ang) * 0.103 * sy + CENTER_Y
                z = BASE_Z + math.sin(ang) * 0.118 + 0.003
                xx = off * (1.0 - 0.35 * math.sin(ang) ** 8) * math.sin(ang)
                path.append(Vector((xx, y, z)))
            geo_main.sweep(path, radius=0.006, segments=6, mat=shell_key, up_hint=(0, 0, 1))
    # Suspension headband peeks out under the rim.
    geo_detail.tube(0.092, 0.086, 0.014, segments=24, matrix=trs((0, CENTER_Y, BASE_Z - 0.004), scale=(1.0, 1.1, 1.0)),
                    mat="plastic:plastic_black")
    if lamp:
        front = Vector((0.0, CENTER_Y - 0.103 * sy - 0.004, BASE_Z + 0.055))
        geo_main.box((0.05, 0.012, 0.035), matrix=trs(front + Vector((0, -0.004, 0))), mat="plastic:plastic_black",
                     bevel=0.004, segments=1)
        axis = Vector((0, -1, 0.08)).normalized()
        body = frame_from_axis(front + Vector((0, -0.025, 0.004)), axis)
        geo_main.cylinder(0.024, 0.036, segments=16, matrix=body, mat="metal:dark_steel", bevel=0.004)
        geo_main.cylinder(0.026, 0.008, segments=16, matrix=body @ Matrix.Translation((0, 0, 0.018)),
                          mat="steel", bevel=0.002)
        geo_main.cylinder(0.019, 0.004, segments=16, matrix=body @ Matrix.Translation((0, 0, 0.023)),
                          mat="emit:emissive_warm")
        cable = [front + Vector((0.02, 0.0, 0.0)), Vector((0.05, CENTER_Y - 0.06, BASE_Z + 0.06)),
                 Vector((0.09, CENTER_Y + 0.02, BASE_Z + 0.03)), Vector((0.08, CENTER_Y + 0.1, BASE_Z + 0.01)),
                 Vector((0.03, CENTER_Y + 0.118, BASE_Z - 0.01))]
        geo_detail.sweep(cable, radius=0.004, segments=6, mat="rubber", up_hint=(0, 0, 1))


def cap(geo_main, geo_detail, color_key):
    key = f"fabric:{color_key}"
    m = trs((0.0, CENTER_Y + 0.004, BASE_Z - 0.012), scale=(0.95, 1.05, 1.0))
    prof = _dome_profile(0.098, 0.082, 0.004)
    geo_main.lathe(prof, segments=24, matrix=m, mat=key, closed_loop=True, caps=False)
    verts = []
    faces = []
    n = 9
    for i in range(n + 1):
        t = i / n
        a = math.radians(-70 + 140 * t)
        for r, dz in ((0.094, 0.0), (0.165, -0.012)):
            x = r * math.sin(a) * 0.95
            y = CENTER_Y - r * math.cos(a) * 1.05
            verts.append((x, y, BASE_Z - 0.01 + dz - 0.01 * (r - 0.094) * abs(math.sin(a)) * 8))
    base = len(verts)
    verts += [(x, y, z - 0.005) for x, y, z in verts]
    for i in range(n):
        a, b, c, d = 2 * i, 2 * i + 1, 2 * i + 3, 2 * i + 2
        faces.append((a, b, c, d))
        faces.append((base + b, base + a, base + d, base + c))
        faces.append((b, base + b, base + c, c))
        faces.append((a, d, base + d, base + a))
    faces.append((0, base + 0, base + 1, 1))
    faces.append((2 * n, 2 * n + 1, base + 2 * n + 1, base + 2 * n))
    geo_main.mesh(verts, faces, mat=key)
    geo_detail.cylinder(0.01, 0.006, segments=8, matrix=trs((0, CENTER_Y + 0.004, BASE_Z + 0.07)), mat=key,
                        bevel=0.002)


def beanie(geo_main, geo_detail, color_key):
    key = f"knit:{color_key}"
    m = trs((0.0, CENTER_Y, BASE_Z - 0.03), scale=(0.95, 1.05, 1.0))
    prof = _dome_profile(0.097, 0.12, 0.005)
    geo_main.lathe(prof, segments=24, matrix=m, mat=key, closed_loop=True, caps=False)
    geo_main.tube(0.104, 0.094, 0.04, segments=24, matrix=trs((0, CENTER_Y, BASE_Z - 0.01), scale=(0.95, 1.05, 1.0)),
                  mat=key, bevel=0.006)


def bush_hat(geo_main, geo_detail, color_key):
    key = f"fabric:{color_key}"
    m = trs((0.0, CENTER_Y, BASE_Z - 0.005), scale=(0.95, 1.05, 1.0))
    prof = _dome_profile(0.094, 0.09, 0.005)
    geo_main.lathe(prof, segments=24, matrix=m, mat=key, closed_loop=True, caps=False)
    prof_b = [(0.092, 0.004), (0.17, -0.014), (0.172, -0.02), (0.092, -0.004)]
    geo_main.lathe(prof_b, segments=28, matrix=trs((0, CENTER_Y, BASE_Z), scale=(0.95, 1.05, 1.0)), mat=key,
                   closed_loop=True, caps=False)
    geo_detail.tube(0.097, 0.092, 0.018, segments=24, matrix=trs((0, CENTER_Y, BASE_Z + 0.012), scale=(0.95, 1.05, 1.0)),
                    mat="leather:leather_brown")


def earmuffs(geo_main, over_helmet=True):
    key = "plastic:plastic_red"
    for s in (1.0, -1.0):
        c = Vector((s * 0.093, 0.02, 1.636))
        m = frame_from_axis(c, (s, 0, 0))
        geo_main.cylinder(0.036, 0.034, segments=16, matrix=m, mat=key, bevel=0.008)
        geo_main.cylinder(0.03, 0.012, segments=16, matrix=m @ Matrix.Translation((0, 0, -0.022)),
                          mat="plastic:plastic_black", bevel=0.004)
    top = 1.83 if over_helmet else 1.79
    r = 0.125 if over_helmet else 0.1
    path = []
    for i in range(11):
        a = math.pi * i / 10
        path.append(Vector((math.cos(a) * r * 0.95, 0.02, 1.656 + math.sin(a) * (top - 1.656))))
    geo_main.sweep(path, profile=[(-0.004, -0.009), (0.004, -0.009), (0.004, 0.009), (-0.004, 0.009)], mat="steel_dark",
                   up_hint=(0, 1, 0))


BUILDERS = {"hardhat": hardhat, "hardhat_lamp": lambda a, b, c: hardhat(a, b, c, lamp=True), "cap": cap,
            "beanie": beanie, "bush_hat": bush_hat}


def build(kind, color_key, ctx_geo, ear_protection=False, name="helmet"):
    """Create headwear Geos through ``ctx_geo(name, max_lod)``; returns list of Geo."""
    if kind in (None, "none"):
        out = []
        if ear_protection:
            g = ctx_geo(name + "_earmuffs", 99)
            earmuffs(g, over_helmet=False)
            out.append(g)
        return out
    if kind not in BUILDERS:
        raise ValueError(f"unknown headwear '{kind}'")
    main = ctx_geo(name, 99)
    detail = ctx_geo(name + "_detail", 0)
    BUILDERS[kind](main, detail, color_key)
    if ear_protection:
        earmuffs(main, over_helmet=kind.startswith("hardhat"))
    return [main, detail]
