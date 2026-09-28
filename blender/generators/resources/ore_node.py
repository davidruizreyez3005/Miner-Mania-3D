"""Mineable resource nodes with ``full`` / ``damaged`` / ``depleted`` states.

Each node is a fractured host-rock mound with its resource embedded in a
material-true way: iron/copper/silver ore veins in the rock plus protruding
ore chunks, coal seams and lumps, gold nuggets in quartz, crystal clusters
(quartz, amethyst, emerald, ruby, sapphire, diamond), platinum ore with
metal chunks, plain stone, and glowing uranium, voidstone and aether
crystals. The states share the seed,
so the silhouette erodes consistently: ``damaged`` loses most protruding ore
and gains a fresh broken face, ``depleted`` is a low rubble pile with traces.

Mining sockets (``socket_mine_N``) are placed by ray-casting the generated
rock so the Mine clip's pickaxe tip lands on the surface (contract point
``mine_impact``). Origin: ground contact centre.
"""

import math

from mathutils import Matrix, Quaternion, Vector

from core import config
from utilities.meshkit import trs

from .. import rocks

RESOURCES = {
    "coal": dict(host="coal", rock="stone:stone_dark", ore="coal", feature="lumps"),
    "iron": dict(host="ore_iron", rock="stone:stone_warm", ore="iron_metal", feature="chunks"),
    "copper": dict(host="ore_copper", rock="stone:stone_gray", ore="copper", feature="chunks"),
    "silver": dict(host="ore_silver", rock="stone:stone_gray", ore="silver", feature="chunks"),
    "gold": dict(host="stone:stone_warm", rock="stone:stone_warm", ore="gold", feature="nuggets"),
    "amethyst": dict(host="stone:stone_gray", rock="stone:stone_gray", ore="crystal_amethyst_glow", feature="crystals"),
    "diamond": dict(host="stone:stone_dark", rock="stone:stone_dark", ore="crystal_diamond", feature="crystals"),
    "uranium": dict(host="stone:stone_dark", rock="stone:stone_dark", ore="crystal_uranium_glow", feature="crystals"),
    "stone": dict(host="stone:stone_gray", rock="stone:stone_warm", ore="stone:stone_warm", feature="chunks"),
    "quartz": dict(host="stone:stone_gray", rock="stone:stone_gray", ore="crystal_quartz", feature="crystals"),
    "platinum": dict(host="ore_platinum", rock="stone:stone_dark", ore="platinum", feature="chunks"),
    "emerald": dict(host="stone:stone_dark", rock="stone:stone_dark", ore="crystal_emerald", feature="crystals"),
    "ruby": dict(host="stone:stone_warm", rock="stone:stone_warm", ore="crystal_ruby", feature="crystals"),
    "sapphire": dict(host="stone:stone_gray", rock="stone:stone_gray", ore="crystal_sapphire", feature="crystals"),
    "voidstone": dict(host="stone:stone_dark", rock="stone:stone_dark", ore="crystal_voidstone_glow", feature="crystals"),
    "aether": dict(host="stone:stone_dark", rock="stone:stone_dark", ore="crystal_aether_glow", feature="crystals"),
}


def _crystal(g, base, direction, length, radius, mat, sides=6):
    """Hexagonal prism with a pyramidal tip, rooted at ``base``."""
    d = Vector(direction).normalized()
    from utilities.meshkit import frame_from_axis
    f = frame_from_axis(base, d)
    prof = [(radius, -0.05 * length), (radius, length * 0.72), (radius * 0.55, length * 0.86), (0.0, length)]
    g.lathe([(0.0, -0.05 * length)] + prof, segments=sides, matrix=f, mat=mat)


def build(ctx):
    kind = ctx.param("resource", ctx.defn.resource)
    spec = RESOURCES[kind]
    state = ctx.state
    rng = ctx.rng.child("layout")                 # same for every state
    body = ctx.geo("rock")
    ore = ctx.geo("ore")
    det = ctx.geo("ore_detail", max_lod=0)
    height = {"full": 1.1, "damaged": 0.85, "depleted": 0.38}[state]
    width = {"full": 1.55, "damaged": 1.45, "depleted": 1.7}[state]
    if state == "depleted":
        for k in range(6):
            a = 2 * math.pi * k / 6 + rng.uniform(-0.3, 0.3)
            r = rng.uniform(0.25, 0.55)
            rocks.rock(body, rng, (rng.uniform(0.4, 0.7), rng.uniform(0.35, 0.6), rng.uniform(0.18, 0.34)), spec["rock"],
                       subdivisions=3, center=(math.cos(a) * r, math.sin(a) * r, 0.0), facets=4)
        rocks.rock(body, rng, (0.9, 0.8, height), spec["host"], subdivisions=3, facets=5)
    else:
        rocks.rock(body, rng, (width, width * 0.86, height), spec["host"], subdivisions=4, facets=7 if state == "full" else 9,
                   lump=0.16)
        for k in range(3):
            a = 2 * math.pi * (k + 0.3) / 3 + rng.uniform(-0.4, 0.4)
            rocks.rock(body, rng, (rng.uniform(0.45, 0.7), rng.uniform(0.4, 0.6), rng.uniform(0.3, 0.5)), spec["rock"],
                       subdivisions=3, center=(math.cos(a) * width * 0.52, math.sin(a) * width * 0.45, 0.0), facets=5)
    body.bm.normal_update()
    # Embedded resource features.
    frng = ctx.rng.child("features")
    count = {"full": 14, "damaged": 5, "depleted": 3}[state]
    pts = rocks.surface_points(body, count * 3, frng, zmin=0.08, normal_min_z=0.0)
    placed = 0
    for p, n in pts:
        if placed >= count:
            break
        placed += 1
        feat = spec["feature"]
        tilt = (n + Vector((frng.uniform(-0.3, 0.3), frng.uniform(-0.3, 0.3), 0.4))).normalized()
        if feat == "crystals":
            cluster = 3 if state != "depleted" else 1
            for c in range(cluster):
                dirn = (tilt + Vector((frng.uniform(-0.45, 0.45), frng.uniform(-0.45, 0.45), 0.0))).normalized()
                ln = frng.uniform(0.18, 0.42) * (0.6 if state == "damaged" else 1.0)
                _crystal(ore if c == 0 else det, p - n * 0.03, dirn, ln, ln * 0.18, spec["ore"])
        elif feat == "nuggets":
            ore.icosphere(frng.uniform(0.03, 0.06), subdivisions=1, matrix=trs(p, scale=(1.3, 1.0, 0.8)), mat=spec["ore"])
            det.box((0.12, 0.08, 0.04), matrix=trs(p - n * 0.01, (frng.uniform(0, 90), 0, frng.uniform(0, 180))),
                    mat="stone_fine:sand", bevel=0.01, segments=1)
        else:                                          # chunks / lumps
            size = frng.uniform(0.07, 0.15) * (1.2 if feat == "lumps" else 1.0)
            rocks.rock(ore, frng, (size * 1.4, size * 1.1, size), spec["ore"], subdivisions=2, facets=4, bury=size * 0.4,
                       center=tuple(p - n * size * 0.3))
    if state == "damaged":                             # fresh broken face + chips on the ground
        for k in range(5):
            a = frng.uniform(0, 2 * math.pi)
            r = frng.uniform(0.85, 1.2)
            rocks.rock(det, frng, (0.12, 0.1, 0.07), spec["rock"], subdivisions=1, facets=3,
                       center=(math.cos(a) * r, math.sin(a) * r, 0.0))
    # Mining sockets around the node (full/damaged): pickaxe tip on the surface.
    if state != "depleted":
        impact = Vector(config.animation_spec()["interaction_points"]["mine_impact"])
        for i, ang in enumerate((-90.0, 150.0, 30.0)):
            a = math.radians(ang)
            outward = Vector((math.cos(a), math.sin(a), 0.0))
            origin = Vector((0.0, 0.0, impact.z)) + outward * 3.0
            dist = rocks.surface_distance(body, origin, -outward)
            if dist is None:
                continue
            surf = origin - outward * dist
            yaw = math.degrees(math.atan2(-outward.x, outward.y))       # worker faces -outward
            rz = Matrix.Rotation(math.radians(yaw), 3, "Z")
            worker = surf - rz @ Vector((impact.x, impact.y, 0.0))
            worker.z = 0.0
            ctx.socket(f"mine_{i + 1}", tuple(worker), (0.0, 0.0, yaw))
    # Collision: convex hull of the mound (sub-sampled).
    verts = [v.co.copy() for v in body.bm.verts]
    step = max(1, len(verts) // 56)
    ctx.col_hull([tuple(v) for v in verts[::step]])
    ctx.metadata["resource"] = {"type": kind, "state": state, "feature": spec["feature"],
                                "states": list(ctx.defn.states)}
