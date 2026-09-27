"""Stylized worker head (with neck), ears, eyes and brows.

The head cage is lofted from 20-vertex horizontal rings. Feature rules are
expressed by angle (0 deg = face front, 90 deg = side) so they do not depend on
the ring resolution: pronounced chin, jaw line rising toward the ears,
tapered lower face, lips with a mouth crease, stylized nose (bridge, tip,
wings), cheekbones, eye sockets, brow ridge and occiput. The crown is closed
with a 5x5 quad grid instead of a pole.

Eyes are separate spheres skinned 100% to the eye bones (gaze can be
animated); ears and brows are rigid on the head. Those details are returned
separately because they must not be subdivided.

The neck starts inside the collar (z ~ 1.42) so the body/head seam is always
hidden by garments.
"""

import math

import bmesh
from mathutils import Matrix, Vector

from rigging.human_rig import skeleton
from utilities.meshkit import Geo, trs

from .skinned import SkinnedGeo

N = 20
GRID_A, GRID_B = 4, 6  # crown grid quads across (x) and front-to-back (y); 2*(A+B) == N
HEAD_ORIGIN = Vector((0.0, 0.005, 1.63))
EYE_RADIUS = 0.0118

# name, z, half-width (back), front depth, back depth, front half-width scale, squareness
RINGS = [
    ("n0", 1.425, 0.050, 0.044, 0.052, 1.0, 2.0),
    ("n1", 1.468, 0.049, 0.042, 0.052, 1.0, 2.0),
    ("n2", 1.503, 0.052, 0.042, 0.056, 1.0, 2.0),
    ("hj", 1.516, 0.064, 0.066, 0.058, 0.8, 2.1),
    ("h0", 1.532, 0.069, 0.08, 0.064, 0.8, 2.1),
    ("h1", 1.554, 0.071, 0.074, 0.074, 0.8, 2.1),
    ("h1m", 1.565, 0.072, 0.075, 0.08, 0.82, 2.1),
    ("h2", 1.582, 0.074, 0.08, 0.086, 0.86, 2.2),
    ("h3", 1.61, 0.077, 0.085, 0.094, 0.93, 2.35),
    ("h4", 1.645, 0.079, 0.082, 0.1, 1.0, 2.5),
    ("h5", 1.676, 0.081, 0.087, 0.102, 1.0, 2.5),
    ("h6", 1.708, 0.08, 0.085, 0.102, 1.0, 2.4),
    ("h7", 1.741, 0.071, 0.072, 0.092, 1.0, 2.2),
    ("h8", 1.765, 0.05, 0.05, 0.066, 1.0, 2.0),
]
RING_INDEX = {r[0]: i for i, r in enumerate(RINGS)}


def _sp(x, p):
    return math.copysign(abs(x) ** p, x)


def angle_of(k):
    """Signed angle in degrees of ring vertex k (0 = front, +90 = left side)."""
    a = (360.0 * k / N) % 360.0
    return a if a <= 180.0 else a - 360.0


def ks_at(*degs, tol=None):
    """Ring indices whose |angle| matches any of the given absolute angles."""
    tol = tol if tol is not None else 180.0 / N
    out = set()
    for k in range(N):
        a = abs(angle_of(k))
        for d in degs:
            if abs(a - d) <= tol + 1e-6:
                out.add(k)
    return out


def ks_between(lo, hi):
    return {k for k in range(N) if lo - 1e-6 <= abs(angle_of(k)) <= hi + 1e-6}


def ring_points(z, w, f, b, fw=1.0, squ=2.3, yc=0.005):
    pts = []
    for k in range(N):
        th = 2 * math.pi * k / N
        s, c = math.sin(th), math.cos(th)
        width = w * (fw + (1.0 - fw) * (1.0 - c)) if c > 0 else w  # lower face tapers toward the front
        x = width * _sp(s, 2.0 / squ)
        y = yc - (f if c > 0 else b) * _sp(c, 2.0 / squ)
        pts.append(Vector((x, y, z)))
    return pts


class HeadShape:
    """Head ring positions (before subdivision), shared with hair/beard."""

    def __init__(self, presentation="masculine", rng=None, nose=1.0, jaw=None):
        fem = presentation == "feminine"
        jaw = jaw if jaw is not None else (0.97 if fem else 1.08)
        rnd = rng.uniform if rng else (lambda a, b: (a + b) / 2)
        width = rnd(0.97, 1.03)
        nose = nose * rnd(0.9, 1.12)
        self.rings = {}
        for name, z, w, f, b, fw, squ in RINGS:
            self.rings[name] = ring_points(z, w * width, f, b, fw, squ)
        R = self.rings

        def move(name, ks, dx=0.0, dy=0.0, dz=0.0, sx=1.0):
            for k in sorted(ks):
                p = R[name][k]
                p.x *= sx
                p.x += dx if p.x >= 0 else -dx
                p.y += dy
                p.z += dz

        ns = nose * (0.8 if fem else 1.0)
        # Chin and jaw line.
        move("h0", ks_at(0), dy=-0.011, dz=-0.004)
        move("h0", ks_at(18), dy=-0.007, dz=-0.002)
        move("hj", ks_at(0, 18), dy=-0.006)
        move("h0", ks_between(50, 120), sx=jaw)
        move("hj", ks_between(50, 110), sx=jaw)
        move("h0", ks_at(90), dz=0.012)
        move("h0", ks_at(108), dz=0.017)
        move("hj", ks_at(108, 126), dz=0.012)
        # Lips and mouth crease.
        move("h1", ks_at(0), dy=-0.005 * (1.4 if fem else 1.0))
        move("h1", ks_at(18), dy=-0.003)
        move("h1m", ks_at(0, 18), dy=0.004)
        move("h1m", ks_at(36), dy=0.002)
        move("h2", ks_at(18), dy=-0.002)
        # Nose: a cluster displacement over three rings so it survives subdivision.
        move("h2", ks_at(0), dy=-0.028 * ns, dz=0.006)
        move("h2", ks_at(18), dy=-0.007 * ns)
        move("h3", ks_at(0), dy=-0.052 * ns)
        move("h3", ks_at(18), dy=-0.02 * ns, sx=1.2)
        move("h4", ks_at(0), dy=-0.024 * ns)
        move("h5", ks_at(0), dy=-0.006)
        # Cheekbones, eye sockets, brow ridge.
        move("h3", ks_at(36, 54), dy=-0.006, dx=0.006)
        move("h2", ks_at(54), dx=0.004)
        move("h3", ks_at(72), dx=0.004)
        move("h4", ks_at(18, 36), dy=0.007)
        move("h4", ks_at(54), dy=0.003)
        move("h5", ks_at(18, 36), dy=-0.007 * (0.6 if fem else 1.0), dz=-0.003)
        for name in ("h5", "h6", "h7"):
            move(name, ks_between(150, 180), dy=0.006)
        for name in ("n2", "hj"):
            move(name, ks_between(160, 180), dy=0.004)
        # Crown grid inside the h8 ring.
        top = R["h8"]
        ztop = 1.777
        self.cap_interior = {}
        for i in range(1, GRID_A):
            for jj in range(1, GRID_B):
                u = i / GRID_A
                v = jj / GRID_B
                x = (u - 0.5) * 2 * 0.04 * width
                y = 0.01 + (v - 0.5) * 2 * 0.05
                dome = 1.0 - ((u - 0.5) ** 2 + (v - 0.5) ** 2) * 1.5
                self.cap_interior[(i, jj)] = Vector((x, y, top[0].z + (ztop - top[0].z) * dome))
        sk = skeleton()
        self.eyes = {s: sk.joints[f"eye.{s}"].copy() for s in ("L", "R")}

    def ring(self, name):
        return self.rings[name]


def grid_boundary_order(a=GRID_A, b=GRID_B):
    """Grid boundary coordinates (i, j) for ring vertex k = 0..2(a+b)-1,
    starting at the front-center vertex and walking toward +x (ring winding).
    ``a`` must be even so front/back centers land on grid vertices."""
    half = a // 2
    coords = [(i, 0) for i in range(half, a)]
    coords += [(a, j) for j in range(0, b)]
    coords += [(i, b) for i in range(a, 0, -1)]
    coords += [(0, j) for j in range(b, 0, -1)]
    coords += [(i, 0) for i in range(0, half)]
    return coords


def head_weights(name, k):
    back = abs(angle_of(k)) >= 100
    if name == "n0":
        return {"spine_03": 0.55, "neck": 0.45}
    if name == "n1":
        return {"neck": 1.0}
    if name == "n2":
        return {"neck": 0.6, "head": 0.4} if back else {"neck": 0.45, "head": 0.55}
    if name == "hj":
        return {"head": 0.7, "neck": 0.3} if back else {"head": 1.0}
    if name == "h0":
        return {"head": 0.85, "neck": 0.15} if back else {"head": 1.0}
    return {"head": 1.0}


def build_head(shape, face_key, eye_key, brow_key, ears=True, brows="normal", ear_key=None):
    """Returns (head, details): the head cage (subdivided once) and the
    eyes/ears/brows that must not be subdivided."""
    g = SkinnedGeo("head", pattern_origin=HEAD_ORIGIN)
    g.subdivide = 1
    det = SkinnedGeo("head_details", pattern_origin=HEAD_ORIGIN)
    rings = []
    for name, *_ in RINGS:
        pts = shape.rings[name]
        rings.append([g.vert(p, head_weights(name, k)) for k, p in enumerate(pts)])
    for i in range(len(RINGS) - 1):
        ra, rb = rings[i], rings[i + 1]
        for k in range(N):
            k2 = (k + 1) % N
            g.face([ra[k], ra[k2], rb[k2], rb[k]], face_key)
    top = rings[-1]
    grid = {}
    order = grid_boundary_order()
    if len(order) != N:
        raise ValueError("crown grid does not match ring resolution")
    for k, ij in enumerate(order):
        grid[ij] = top[k]
    for ij, p in shape.cap_interior.items():
        grid[ij] = g.vert(p, {"head": 1.0})
    for i in range(GRID_A):
        for jj in range(GRID_B):
            g.face([grid[(i, jj)], grid[(i + 1, jj)], grid[(i + 1, jj + 1)], grid[(i, jj + 1)]], face_key)
    g.face(list(reversed(rings[0])), face_key)
    bmesh.ops.recalc_face_normals(g.bm, faces=list(g.bm.faces))
    for side, c in shape.eyes.items():
        eye = Geo("eye")
        eye.sphere(EYE_RADIUS, segments=14, rings=9, mat=eye_key)
        det.append_rigid(eye, f"eye.{side}", Matrix.Translation(c))
    if ears:
        for s in (1.0, -1.0):
            ear = Geo("ear")
            outline = [(0.0, -0.026), (0.012, -0.03), (0.022, -0.02), (0.027, 0.0), (0.024, 0.018),
                       (0.012, 0.03), (-0.004, 0.03), (-0.012, 0.018), (-0.01, 0.0), (-0.006, -0.016)]
            ear.extrude(outline, 0.011, mat=ear_key or face_key, bevel=0.0035, segments=2)
            outer = ear.faces_facing((0, 0, 1), 0.95)
            if outer:
                ear.inset_panels(outer[:1], 0.0055, -0.0045)
            m = trs((s * 0.076, 0.02, 1.634)) @ Matrix(((0, 0, s, 0), (1, 0, 0, 0), (0, 1, 0, 0), (0, 0, 0, 1))) \
                @ Matrix.Rotation(math.radians(-8), 4, "Z")
            det.append_rigid(ear, "head", m)
    if brows != "none":
        th = {"normal": 0.0042, "thick": 0.006, "thin": 0.003}.get(brows, 0.0042)
        for s in (1.0, -1.0):
            b = Geo("brow")
            path = []
            for t in (0.0, 0.33, 0.66, 1.0):
                x = s * (0.016 + 0.036 * t)
                z = 1.676 + 0.006 * math.sin(math.pi * t) - 0.002 * t
                y = -0.094 + 0.022 * t * t
                path.append((x, y, z))
            prof = [(-0.0025, -th), (0.0025, -th), (0.0025, th), (-0.0025, th)]
            b.sweep(path, profile=prof, mat=brow_key, up_hint=(0, -1, 0))
            det.append_rigid(b, "head")
    return g, det
