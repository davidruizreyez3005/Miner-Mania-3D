"""Mine portal cut into a rock hillside.

Construction: two rock cheeks and a brow frame the adit; a concrete portal
(pillars, lintel with a sign) stands at the face; a 4 m tunnel section runs
into the hill (same profile as ``env_tunnel_straight_01`` so it chains from
``socket_tunnel_end``); a 600 mm track leads out onto a gravel apron; steel
mesh gates close the portal. Bones:

* ``gate.L`` / ``gate.R``  hinged on the pillars, open inward (+Y)

Clips: ``Idle``, ``Gates`` (open, hold, close). Origin: apron ground at the
portal centre; entrance faces -Y.
"""

import math

from mathutils import Quaternion, Vector

from utilities.meshkit import trs

from .. import kit, rocks
from ..environment import natural as nat
from ..environment import structures as st
from . import common as bc

ROCK = "stone:stone_warm"


def build(ctx):
    w, h = st.TUNNEL_W, st.TUNNEL_H
    L = 4.0
    g = ctx.geo("portal")
    det = ctx.geo("portal_detail", max_lod=1)
    hill = ctx.geo("hill")
    rng = ctx.rng.child("hill")
    # Tunnel into the hill (y 0..L).
    st.tunnel_section(ctx, g, det, ctx.rng.child("tunnel"), L, y0=L / 2)
    # Hillside: strata cliff faces either side of the portal and a brow above
    # it (the same displaced-face construction as env_cliff_01).
    face_y = 2.2                                                        # section centre: face just ahead of the portal
    cheeks = []
    for s, width, height in ((-1, 5.2, 5.6), (1, 5.2, 5.0)):
        x = s * (w / 2 + 0.55 + width / 2)
        nat.cliff_face(hill, det, rng, width, 5.6, height, ROCK, origin=(x, face_y, 0.0), taper=(s < 0, s > 0))
        cheeks.append((x, width, height))
    brow_z, brow_h = h + 0.6, 1.3                                       # sits behind the lintel, top level with the cheeks
    nat.cliff_face(hill, det, rng, w + 1.4, 5.6, brow_h, ROCK, origin=(0.0, face_y + 0.6, brow_z), layers=2, boulders=0, scree=0)
    for k in range(6):                                                  # fallen rocks at the foot
        s = rng.uniform(0.2, 0.45)
        x = rng.choice((-1, 1)) * rng.uniform(2.8, 6.5)
        rocks.rock(det, rng, (s * 1.3, s, s * 0.8), ROCK, subdivisions=2, center=(x, rng.uniform(-1.6, -1.0), 0.0), facets=4)
    # Concrete portal.
    for s in (-1, 1):
        g.box((0.6, 0.7, h + 0.4), matrix=trs((s * (w / 2 + 0.25), -0.2, (h + 0.4) / 2)), mat=bc.SLAB, bevel=0.03)
    g.box((w + 1.3, 0.8, 0.7), matrix=trs((0.0, -0.2, h + 0.55)), mat=bc.SLAB, bevel=0.03)
    g.box((2.4, 0.05, 0.5), matrix=trs((0.0, -0.625, h + 0.55)), mat="paint_clean:sign_yellow", bevel=0.01)
    det.box((2.0, 0.02, 0.2), matrix=trs((0.0, -0.66, h + 0.55)), mat="plastic:plastic_black")
    for s in (-1, 1):
        det.box((0.08, 0.02, h + 0.3), matrix=trs((s * (w / 2 - 0.03), -0.56, (h + 0.3) / 2)), mat=kit.HAZARD)
        kit.lamp(det, (s * (w / 2 + 0.25), -0.6, h + 0.05), (0.0, -0.7, -0.7), r=0.1, emit="emit:emissive_warm")
        kit.warning_sign(det, (s * (w / 2 + 0.25), -0.56, 1.6), size=0.4)
    # Track: from the tunnel end out over the apron.
    gauge = st.GAUGE
    for s in (-1, 1):
        path = [Vector((s * gauge / 2, y, 0.075)) for y in (L, -3.0)]
        g.sweep(path, profile=st._rail_profile(), mat=kit.STEEL, up_hint=(-1, 0, 0))
    for k in range(12):
        y = L - 0.3 - k * 0.6
        g.box((1.1, 0.16, 0.08), matrix=trs((0.0, y, 0.035)), mat=st.TIMBER, bevel=0.008)
    # Gravel apron.
    g.grid(8.0, 3.2, 16, 6, height_fn=lambda x, y: 0.01 * math.sin(x * 2.1) * math.cos(y * 1.7),
           matrix=trs((0.0, -1.6, 0.0)), mat="gravel:gravel", skirt=0.05)
    # Gates (steel frame + mesh), hinged on the pillars.
    gw = w / 2 - 0.11                     # two leaves meet at the centre line
    gh = 2.4
    gates = []
    for side, s in (("L", -1), ("R", 1)):
        # Hinge just inside the pillar face: an open leaf lies along the tunnel wall.
        hinge = Vector((s * (w / 2 - 0.1), -0.5, 0.05))
        name = f"gate.{side}"
        ctx.bone(name, tuple(hinge), tuple(hinge + Vector((0.0, 0.0, 0.3))))
        gg = ctx.geo(name, bone=name)
        x_far = hinge.x - s * gw
        for z in (0.1, gh / 2, gh):
            kit.beam(gg, (hinge.x, hinge.y, z), (x_far, hinge.y, z), 0.05, 0.05, "paint_worn:industrial_yellow", profile="tube")
        for x in (hinge.x, x_far):
            kit.beam(gg, (x, hinge.y, 0.08), (x, hinge.y, gh + 0.02), 0.05, 0.05, "paint_worn:industrial_yellow", profile="tube")
        for k in range(1, 9):
            x = hinge.x - s * gw * k / 9
            kit.beam(gg, (x, hinge.y, 0.1), (x, hinge.y, gh), 0.012, 0.012, "metal:galvanized", bevel=0.0)
        kit.beam(gg, (hinge.x, hinge.y, 0.15), (x_far, hinge.y, gh - 0.05), 0.03, 0.03, "paint_worn:industrial_yellow")
        gates.append((name, s))
    ctx.socket("entrance", (0.0, -2.2, 0.0), (0.0, 0.0, 180.0))
    ctx.socket("tunnel_end", (0.0, L, 0.0))
    ctx.socket("rail_end", (0.0, -3.0, 0.0))
    # Collision: rock masses (clear of the adit), portal, apron.
    for x, width, height in cheeks:
        ctx.col_box((x, face_y, height / 2), (width, 5.6, height))
    ctx.col_box((0.0, face_y + 0.6, brow_z + brow_h / 2), (w + 1.4, 5.6, brow_h))
    ctx.col_box((0.0, -1.6, 0.0), (8.0, 3.2, 0.1))
    for s in (-1, 1):
        ctx.col_box((s * (w / 2 + 0.25), -0.2, (h + 0.4) / 2), (0.6, 0.7, h + 0.4))
    ctx.col_box((0.0, -0.2, h + 0.55), (w + 1.3, 0.8, 0.7))

    def gates_clip(t):
        _, k = bc.door_swing(0.0, t, 5.0, hold=0.35)
        return {name: (None, Quaternion((0.0, 0.0, 1.0), -s * math.radians(90) * k)) for name, s in gates}

    ctx.clip("Idle", 2.0, True, lambda t: {}, "Gates closed")
    ctx.clip("Gates", 5.0, True, gates_clip, "Mesh gates swing inward, hold open, close")
    ctx.metadata["interaction"] = {"entrance": "socket_entrance", "tunnel": "socket_tunnel_end (chain env_tunnel_straight_01)",
                                   "rail": "socket_rail_end"}
