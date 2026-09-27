"""Work boots with their own designed topology.

The upper is lofted from 10-vertex sections along the calf axis (shaft) and
then along the foot (heel -> arch -> ball -> toe box -> tip); a separate
rubber sole slab with a heel block sits under it. Weights follow the
construction: shaft = calf, ankle = calf/foot blend, arch = foot, ball =
foot/toe blend, toe box = toe. Laces and the pull tab are LOD0 details.
"""

import math

import bmesh
from mathutils import Matrix, Vector

from rigging.human_rig import skeleton
from utilities.meshkit import Geo

from .skinned import SkinnedGeo

N = 10


def _section_ring(center, e_side, e_up, half_w, half_up, down_bias=0.0):
    pts = []
    for i in range(N):
        a = math.radians(18 + 36 * i)
        c, s = math.cos(a), math.sin(a)
        up = half_up if s > 0 else half_up * (1.0 - down_bias)
        pts.append(center + e_side * (half_w * c) + e_up * (up * s))
    return pts


def build_boots(leather_key="leather:leather_brown", sole_key="rubber_sole", toe_key=None, shaft_top=0.285,
                laces_key="fabric:hazard_black"):
    sk = skeleton()
    j = sk.joints
    g = SkinnedGeo("boots")
    g.subdivide = 1
    hard = SkinnedGeo("boots_soles")     # hard-surface soles: never subdivided
    det = SkinnedGeo("boots_details")
    sole_h = 0.022
    for side in ("L", "R"):
        sx = 1.0 if side == "L" else -1.0
        cf, ft, to = f"calf.{side}", f"foot.{side}", f"toe.{side}"
        ankle = j[f"ankle.{side}"]
        knee = j[f"knee.{side}"]
        axis = (ankle - knee).normalized()
        inner = Vector((-sx, 0, 0))
        front = Vector((0, -1, 0))
        e_in = (inner - axis * inner.dot(axis)).normalized()
        e_f = (front - axis * front.dot(axis)).normalized()
        x0 = ankle.x
        rings = []
        weights = []
        # Shaft sections (horizontal-ish rings around the lower leg).
        for z, r_in, r_f, w in ((shaft_top, 0.056, 0.058, {cf: 1.0}), (0.2, 0.052, 0.054, {cf: 1.0}),
                                (0.125, 0.052, 0.058, {cf: 0.6, ft: 0.4})):
            t = (knee.z - z) / (knee.z - ankle.z)
            c = knee.lerp(ankle, t)
            pts = []
            for i in range(N):
                a = math.radians(18 + 36 * i)
                ci, sf = math.cos(a), math.sin(a)
                pts.append(c + e_in * (r_in * ci) + e_f * (r_f * sf) + Vector((0, 0.006, 0)))
            rings.append(pts)
            weights.append(w)
        # Foot sections perpendicular to Y: (y, top z, half width, weights)
        side_e = Vector((-sx, 0, 0))
        up_e = Vector((0, 0, 1))
        for y, ztop, hw, w in ((0.07, 0.11, 0.05, {ft: 1.0}), (0.0, 0.1, 0.054, {ft: 1.0}),
                               (-0.07, 0.085, 0.058, {ft: 0.75, to: 0.25}),
                               (-0.12, 0.07, 0.06, {ft: 0.4, to: 0.6}), (-0.175, 0.058, 0.055, {to: 1.0}),
                               (-0.212, 0.045, 0.038, {to: 1.0})):
            zmid = (ztop + sole_h) / 2
            half_up = (ztop - sole_h) / 2
            c = Vector((x0 + sx * (0.004 if y < -0.05 else 0.0), y, zmid))
            rings.append(_section_ring(c, side_e, up_e, hw, half_up))
            weights.append(w)
        vrings = [[g.vert(p, w) for p in pts] for pts, w in zip(rings, weights)]
        # The shaft rings are ordered around the leg axis; the foot rings around Y.
        # Bridge each consecutive pair with the minimal-twist alignment.
        for a, b in zip(vrings, vrings[1:]):
            _bridge(g, a, b, leather_key if b is not vrings[-1] else (toe_key or leather_key))
        tip = vrings[-1]
        f = g.face(list(tip), toe_key or leather_key)
        bmesh.ops.inset_individual(g.bm, faces=[f], thickness=0.012, depth=0.004)
        for v in f.verts:
            g.set_weights(v, {to: 1.0})
        # Shaft opening: fold inward and down to show the leather thickness.
        top = vrings[0]
        t_top = (knee.z - shaft_top) / (knee.z - ankle.z)
        c_top = knee.lerp(ankle, t_top) + Vector((0, 0.006, 0))
        lip = [g.vert(v.co + (c_top - v.co).normalized() * 0.008 + Vector((0, 0, -0.012)), {cf: 1.0}) for v in top]
        _bridge(g, top, lip, leather_key, flip=True)
        # Sole slab: rounded foot outline extruded downward.
        outline = []
        for i in range(24):
            a = 2 * math.pi * i / 24
            ca, sa = math.cos(a), math.sin(a)
            y = -0.07 + (0.15 if sa > 0 else 0.155) * sa
            y = min(0.105, max(-0.225, y))
            wdt = 0.058 if sa < 0 else 0.052
            outline.append((x0 + sx * 0.002 + wdt * ca, y))
        sole = Geo("sole")
        sole.extrude(outline, sole_h, mat=sole_key, bevel=0.006, segments=1)
        # Heel block: the sole is thicker under the heel (both start at the ground).
        heel = [(x0 + 0.05 * math.cos(2 * math.pi * i / 12), 0.058 + 0.045 * math.sin(2 * math.pi * i / 12))
                for i in range(12)]
        sole.extrude(heel, sole_h + 0.012, mat=sole_key, bevel=0.003, segments=1)

        def sole_w(co, ft=ft, to=to):
            t = max(0.0, min(1.0, (-co.y - 0.04) / 0.1))
            return {ft: 1.0 - 0.7 * t, to: 0.7 * t}
        hard.append_geo(sole, sole_w)
        # Laces across the instep and a pull tab (LOD0 details).
        lace = Geo("laces")
        for i, (y, z) in enumerate(((-0.075, 0.09), (-0.05, 0.105), (-0.025, 0.12), (0.0, 0.14), (0.01, 0.18),
                                    (0.012, 0.22))):
            lace.box((0.05, 0.006, 0.004), matrix=Matrix.Translation((x0, y - 0.009, z + 0.004)) @
                     Matrix.Rotation(math.radians(20 + 12 * i), 4, "X"), mat=laces_key, bevel=0.0015, segments=1)
        det.append_geo(lace, lambda co, ft=ft, cf=cf: {ft: 1.0} if co.z < 0.14 else {cf: 1.0})
        tab = Geo("tab")
        tab.box((0.03, 0.006, 0.03), matrix=Matrix.Translation((x0, 0.06, shaft_top + 0.008)), mat=leather_key,
                bevel=0.003, segments=1)
        det.append_rigid(tab, cf)
    return g, hard, det


def _bridge(g, loop_a, loop_b, key, flip=False):
    """Quad band between equally oriented loops (cyclic offset only, never
    reversed, so consecutive bands keep a consistent winding)."""
    n = len(loop_a)
    best = None
    for off in range(n):
        cost = sum((loop_a[k].co - loop_b[(k + off) % n].co).length for k in range(n))
        if best is None or cost < best[0]:
            best = (cost, [loop_b[(k + off) % n] for k in range(n)])
    lb = best[1]
    for k in range(n):
        k2 = (k + 1) % n
        quad = [loop_a[k], loop_a[k2], lb[k2], lb[k]]
        if flip:
            quad.reverse()
        g.face(quad, key)
