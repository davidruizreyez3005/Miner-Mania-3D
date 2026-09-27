"""Hand tools and handheld equipment.

Every tool is authored in *grip space*: origin at the main (right-hand) grip,
handle along +Z toward the working head, working face toward -Y. Two-handed
tools put their secondary grip at a standard offset (see
assets/source/animation_clips.json ``grips``), so every compatible tool works
with the shared animation library:

* pickaxe / sledgehammer: left hand 0.30 m down the handle (z = -0.30)
* shovel: left hand on the D-grip end (z = -0.40), opposite palm
* jackhammer: T-bar along Z, left grip at z = +0.36, body hangs along -X

Exported tool GLBs keep this origin/orientation, so in Godot a tool attaches to
the ``hand_tool.R`` BoneAttachment3D with an identity transform.
"""

import math

from mathutils import Matrix, Vector

from utilities.meshkit import frame_from_axis, trs

WOOD = "wood:wood_light"
STEEL = "steel_dark"
BRIGHT = "steel"


def _handle(g, z0, z1, r0, r1, mat=WOOD, oval=0.82, swell=0.1):
    prof = [(0.0, z0 - 0.004), (r0 * 0.8, z0 - 0.004), (r0 * 1.15, z0 + 0.01), (r0, z0 + 0.03)]
    for t in (0.3, 0.6, 0.85):
        z = z0 + (z1 - z0) * t
        r = r0 + (r1 - r0) * t + swell * r0 * math.sin(math.pi * t) * 0.3
        prof.append((r, z))
    prof += [(r1, z1), (0.0, z1)]
    g.lathe(prof, segments=12, matrix=trs(scale=(1.0, oval, 1.0)), mat=mat)


def pickaxe(g, d):
    _handle(g, -0.43, 0.47, 0.019, 0.017)
    d.cylinder(0.021, 0.12, segments=12, matrix=trs((0, 0, -0.33), scale=(1.0, 0.85, 1.0)), mat="leather:leather_black",
               bevel=0.003)
    head_z = 0.455
    g.cylinder(0.03, 0.07, segments=12, matrix=trs((0, 0, head_z)), mat=STEEL, bevel=0.006)
    pick = [Vector((0, -0.02, head_z)), Vector((0, -0.1, head_z - 0.004)), Vector((0, -0.19, head_z - 0.02)),
            Vector((0, -0.27, head_z - 0.05))]
    prof = [(0.0, -0.022), (0.016, 0.0), (0.0, 0.022), (-0.016, 0.0)]
    g.sweep(pick, profile=prof, mat=STEEL, scales=[1.0, 0.85, 0.55, 0.12], up_hint=(1, 0, 0))
    adze = [Vector((0, 0.02, head_z)), Vector((0, 0.1, head_z - 0.003)), Vector((0, 0.18, head_z - 0.016)),
            Vector((0, 0.23, head_z - 0.035))]
    prof2 = [(-0.02, -0.018), (0.02, -0.018), (0.024, 0.018), (-0.024, 0.018)]
    g.sweep(adze, profile=prof2, mat=STEEL, scales=[1.0, 0.9, 0.7, 0.35], up_hint=(0, 0, 1))
    d.cylinder(0.009, 0.064, segments=8, matrix=trs((0, 0, head_z + 0.036)), mat=WOOD)


def sledgehammer(g, d):
    _handle(g, -0.43, 0.44, 0.02, 0.018)
    d.cylinder(0.022, 0.12, segments=12, matrix=trs((0, 0, -0.33), scale=(1.0, 0.85, 1.0)), mat="rubber", bevel=0.003)
    g.box((0.085, 0.2, 0.085), matrix=trs((0, 0, 0.47)), mat=STEEL, bevel=0.01, segments=2)
    for sy in (-1, 1):
        g.box((0.09, 0.012, 0.09), matrix=trs((0, sy * 0.1, 0.47)), mat=BRIGHT, bevel=0.006, segments=1)


def hammer(g, d):
    _handle(g, -0.1, 0.23, 0.014, 0.012)
    d.cylinder(0.0165, 0.11, segments=10, matrix=trs((0, 0, -0.03), scale=(1.0, 0.85, 1.0)), mat="rubber:hazard_black",
               bevel=0.003)
    g.box((0.026, 0.05, 0.032), matrix=trs((0, 0, 0.245)), mat=STEEL, bevel=0.004, segments=1)
    g.cylinder(0.016, 0.035, segments=12, matrix=frame_from_axis((0, -0.035, 0.245), (0, -1, 0)), mat=BRIGHT,
               bevel=0.003)
    claw = [Vector((0, 0.02, 0.25)), Vector((0, 0.06, 0.245)), Vector((0, 0.09, 0.225))]
    g.sweep(claw, profile=[(-0.012, -0.008), (0.012, -0.008), (0.01, 0.008), (-0.01, 0.008)], mat=STEEL,
            scales=[1.0, 0.8, 0.4], up_hint=(0, 0, 1))


def rock_hammer(g, d):
    _handle(g, -0.09, 0.25, 0.014, 0.012, mat="leather:leather_brown")
    g.cylinder(0.014, 0.03, segments=10, matrix=frame_from_axis((0, -0.025, 0.265), (0, -1, 0)), mat=BRIGHT,
               bevel=0.003)
    g.box((0.024, 0.03, 0.03), matrix=trs((0, 0, 0.265)), mat=STEEL, bevel=0.004, segments=1)
    pick = [Vector((0, 0.015, 0.265)), Vector((0, 0.07, 0.262)), Vector((0, 0.13, 0.245))]
    g.sweep(pick, profile=[(0, -0.012), (0.009, 0), (0, 0.012), (-0.009, 0)], mat=STEEL, scales=[1.0, 0.7, 0.1],
            up_hint=(1, 0, 0))


def shovel(g, d):
    _handle(g, -0.56, 0.37, 0.018, 0.018)
    # D-grip at the handle end.
    dpath = [Vector((0.0, 0.0, -0.55)), Vector((0.05, 0.0, -0.6)), Vector((0.05, 0.0, -0.68)), Vector((0.0, 0.0, -0.7)),
             Vector((-0.05, 0.0, -0.68)), Vector((-0.05, 0.0, -0.6)), Vector((0.0, 0.0, -0.55))]
    g.sweep(dpath, radius=0.012, segments=8, mat="plastic:plastic_black", closed_path=True, caps=False,
            up_hint=(0, 1, 0))
    g.cylinder(0.024, 0.1, segments=12, matrix=trs((0, 0, 0.39)), mat=STEEL, radius_top=0.02, bevel=0.004)
    # Blade: curved spade plate, concave toward -Y.
    verts, faces = [], []
    nu, nv = 6, 6
    for j in range(nv + 1):
        t = j / nv
        z = 0.43 + 0.3 * t
        half = 0.12 * (1.0 - 0.75 * max(0.0, t - 0.55) / 0.45) if t > 0.55 else 0.12 * (0.8 + 0.2 * t / 0.55)
        for i in range(nu + 1):
            u = -1.0 + 2.0 * i / nu
            x = u * half
            y = 0.03 * (u * u) - 0.012
            verts.append((x, y, z))
    base = len(verts)
    verts += [(x, y + 0.004, z) for x, y, z in verts]
    for j in range(nv):
        for i in range(nu):
            a = j * (nu + 1) + i
            faces.append((a, a + 1, a + nu + 2, a + nu + 1))
            faces.append((base + a, base + a + nu + 1, base + a + nu + 2, base + a + 1))
    for j in range(nv):
        for i in (0, nu):
            a = j * (nu + 1) + i
            b = a + nu + 1
            faces.append((a, b, base + b, base + a) if i == 0 else (a, base + a, base + b, b))
    for i in range(nu):
        a = i
        faces.append((a, base + a, base + a + 1, a + 1))
        a = nv * (nu + 1) + i
        faces.append((a, a + 1, base + a + 1, base + a))
    g.mesh(verts, faces, mat="paint_worn:safety_orange", recalc=True)


def jackhammer(g, d):
    # T-bar along Z: right grip at z=0, left grip at z=0.36, body center at z=0.18.
    g.cylinder(0.016, 0.46, segments=10, matrix=trs((0, 0, 0.18)), mat=STEEL, bevel=0.003)
    for z in (0.0, 0.36):
        d.cylinder(0.021, 0.1, segments=10, matrix=trs((0, 0, z)), mat="rubber", bevel=0.004)
    body_axis = Vector((-1, 0, 0))
    top = Vector((-0.03, 0, 0.18))
    g.cylinder(0.048, 0.1, segments=16, matrix=frame_from_axis(top + body_axis * 0.05, body_axis),
               mat="paint:industrial_yellow", bevel=0.008)
    g.cylinder(0.04, 0.3, segments=16, matrix=frame_from_axis(top + body_axis * 0.25, body_axis),
               mat="metal:dark_steel", bevel=0.004)
    for i in range(5):
        d.cylinder(0.046, 0.012, segments=16, matrix=frame_from_axis(top + body_axis * (0.14 + 0.05 * i), body_axis),
                   mat="steel", bevel=0.002)
    g.cylinder(0.022, 0.05, segments=12, matrix=frame_from_axis(top + body_axis * 0.425, body_axis), mat=STEEL)
    g.cylinder(0.012, 0.19, segments=8, matrix=frame_from_axis(top + body_axis * 0.54, body_axis), mat=BRIGHT,
               radius_top=0.003)
    hose = [top + Vector((-0.1, 0.045, 0.02)), top + Vector((-0.14, 0.09, 0.05)), top + Vector((-0.1, 0.16, 0.1)),
            top + Vector((0.0, 0.2, 0.12))]
    d.sweep(hose, radius=0.011, segments=8, mat="rubber", up_hint=(0, 0, 1))


def wrench(g, d):
    g.box((0.018, 0.028, 0.26), matrix=trs((0, 0, 0.02)), mat="paint_worn:signal_red", bevel=0.005, segments=1)
    g.box((0.024, 0.06, 0.05), matrix=trs((0, -0.012, 0.17)), mat=STEEL, bevel=0.005, segments=1)
    g.box((0.022, 0.05, 0.016), matrix=trs((0, -0.035, 0.205)), mat=STEEL, bevel=0.004, segments=1)
    d.cylinder(0.011, 0.03, segments=8, matrix=frame_from_axis((0, 0.0, 0.15), (1, 0, 0)), mat=BRIGHT, bevel=0.002)


def tablet(g, d):
    g.box((0.02, 0.19, 0.26), matrix=trs((0, -0.02, 0.1)), mat="plastic:plastic_black", bevel=0.01, segments=2)
    g.box((0.004, 0.165, 0.23), matrix=trs((0.011, -0.02, 0.1)), mat="emit_soft:emissive_cool", bevel=0.002,
          segments=1)
    d.box((0.024, 0.2, 0.03), matrix=trs((0, -0.02, -0.02)), mat="rubber:industrial_yellow", bevel=0.008, segments=1)


def clipboard(g, d):
    g.box((0.012, 0.23, 0.31), matrix=trs((0, -0.03, 0.12)), mat="wood:wood_dark", bevel=0.004, segments=1)
    g.box((0.004, 0.2, 0.26), matrix=trs((0.008, -0.03, 0.1)), mat="plastic:plastic_white", bevel=0.001, segments=1)
    d.box((0.016, 0.08, 0.03), matrix=trs((0.006, -0.03, 0.265)), mat="steel", bevel=0.004, segments=1)


def radio(g, d):
    g.box((0.035, 0.06, 0.12), matrix=trs((0, 0, 0.045)), mat="plastic:plastic_black", bevel=0.008, segments=2)
    g.box((0.004, 0.045, 0.04), matrix=trs((0.018, 0, 0.07)), mat="emit_soft:emissive_green", bevel=0.001, segments=1)
    d.cylinder(0.005, 0.1, segments=6, matrix=trs((0, 0.018, 0.15)), mat="rubber", radius_top=0.003)
    d.cylinder(0.008, 0.012, segments=8, matrix=trs((0, -0.018, 0.112)), mat="plastic:signal_red")


def remote_control(g, d):
    g.box((0.07, 0.22, 0.12), matrix=trs((0, -0.08, 0.02)), mat="paint:industrial_yellow", bevel=0.012, segments=2)
    for sy in (-0.13, -0.03):
        d.cylinder(0.007, 0.05, segments=8, matrix=frame_from_axis((0.045, sy, 0.04), (1, 0, 0)), mat="rubber")
        d.sphere(0.012, segments=8, rings=6, matrix=trs((0.072, sy, 0.04)), mat="plastic:plastic_black")
    d.cylinder(0.012, 0.012, segments=10, matrix=frame_from_axis((0.036, -0.08, 0.075), (1, 0, 0)),
               mat="plastic:signal_red", bevel=0.002)


def toolbox(g, d):
    # Carried by the handle: the box hangs toward -Y (the hand's distal direction).
    g.box((0.2, 0.2, 0.46), matrix=trs((0, -0.155, 0.0)), mat="paint:signal_red", bevel=0.01, segments=2)
    g.box((0.21, 0.02, 0.47), matrix=trs((0, -0.07, 0.0)), mat="paint:signal_red", bevel=0.006, segments=1)
    g.cylinder(0.012, 0.2, segments=10, matrix=trs((0, 0, 0.0)), mat="plastic:plastic_black", bevel=0.003)
    for sz in (-0.11, 0.11):
        g.box((0.02, 0.05, 0.02), matrix=trs((0, -0.03, sz)), mat="steel_dark", bevel=0.004, segments=1)
    for sz in (-0.2, 0.2):
        d.box((0.03, 0.03, 0.02), matrix=trs((0.1, -0.08, sz)), mat="steel", bevel=0.003, segments=1)


def scanner(g, d):
    _handle(g, -0.06, 0.06, 0.018, 0.018, mat="rubber", swell=0.0)
    g.box((0.05, 0.18, 0.07), matrix=trs((0, -0.07, 0.09)), mat="paint:industrial_yellow", bevel=0.012, segments=2)
    g.box((0.004, 0.06, 0.04), matrix=trs((0.026, -0.03, 0.1)), mat="emit_soft:emissive_cool", bevel=0.001,
          segments=1)
    d.cylinder(0.02, 0.03, segments=12, matrix=frame_from_axis((0, -0.17, 0.09), (0, -1, 0)), mat="steel",
               bevel=0.003)


def lantern(g, d):
    g.cylinder(0.05, 0.14, segments=14, matrix=frame_from_axis((0, -0.14, 0), (0, -1, 0)), mat="glass")
    g.cylinder(0.055, 0.025, segments=14, matrix=frame_from_axis((0, -0.06, 0), (0, -1, 0)), mat="paint:signal_red",
               bevel=0.004)
    g.cylinder(0.058, 0.03, segments=14, matrix=frame_from_axis((0, -0.225, 0), (0, -1, 0)), mat="paint:signal_red",
               bevel=0.004)
    g.cylinder(0.02, 0.07, segments=10, matrix=frame_from_axis((0, -0.14, 0), (0, -1, 0)), mat="emit:emissive_warm")
    bail = [Vector((0, -0.06, -0.05)), Vector((0, -0.01, -0.04)), Vector((0, 0.01, 0.0)), Vector((0, -0.01, 0.04)),
            Vector((0, -0.06, 0.05))]
    g.sweep(bail, radius=0.004, segments=6, mat="steel_dark", up_hint=(1, 0, 0))


BUILDERS = {
    "pickaxe": pickaxe, "sledgehammer": sledgehammer, "hammer": hammer, "rock_hammer": rock_hammer,
    "shovel": shovel, "jackhammer": jackhammer, "wrench": wrench, "tablet": tablet, "clipboard": clipboard,
    "radio": radio, "remote_control": remote_control, "toolbox": toolbox, "scanner": scanner, "lantern": lantern,
}


def build_tool(kind, main, detail):
    if kind not in BUILDERS:
        raise ValueError(f"unknown tool kind '{kind}'")
    BUILDERS[kind](main, detail)


def build(ctx):
    kind = ctx.param("kind")
    main = ctx.geo("tool")
    detail = ctx.geo("tool_detail", max_lod=0)
    build_tool(kind, main, detail)
    # Collision: one convex hull around each Geo's vertices (few points).
    pts = [v.co.copy() for v in main.bm.verts]
    lo = Vector((min(p.x for p in pts), min(p.y for p in pts), min(p.z for p in pts)))
    hi = Vector((max(p.x for p in pts), max(p.y for p in pts), max(p.z for p in pts)))
    ctx.col_box(((lo + hi) / 2), (hi - lo))
    ctx.metadata["attach_socket"] = ctx.param("socket", "hand_tool.R")
    ctx.metadata["grip"] = ctx.param("grip")
