"""Procedural rock shapes shared by resource nodes and environment rocks.

Rocks start from an icosphere, get a flattened footprint, low-frequency
lumpiness plus planar cleavage facets (so they read as fractured stone, not
blobs), and sit on the ground with a slightly buried base. All randomness
comes from the asset's seeded RNG (mathutils noise is deterministic).
"""

import math

import bmesh
from mathutils import Matrix, Vector, noise
from mathutils.bvhtree import BVHTree


def rock(g, rng, size, mat, subdivisions=3, lump=0.18, facets=7, flat=0.35, bury=0.06, center=(0.0, 0.0, 0.0),
         yaw=None):
    """Add one rock to Geo ``g``. ``size`` = (x, y, z) extents in metres."""
    sx, sy, sz = size
    tmp = bmesh.new()
    bmesh.ops.create_icosphere(tmp, subdivisions=subdivisions, radius=1.0)
    off = Vector((rng.uniform(-50, 50), rng.uniform(-50, 50), rng.uniform(-50, 50)))
    planes = []
    for _ in range(facets):
        n = Vector((rng.uniform(-1, 1), rng.uniform(-1, 1), rng.uniform(-0.3, 1.0))).normalized()
        planes.append((n, rng.uniform(0.62, 0.9)))
    for v in tmp.verts:
        d = v.co.normalized()
        r = 1.0 + lump * noise.noise(d * 1.6 + off) + 0.35 * lump * noise.noise(d * 4.0 + off * 2.0)
        p = d * r
        for n, k in planes:                     # cleavage facets: clip against planes
            h = p.dot(n)
            if h > k:
                p -= n * (h - k)
        if p.z < -flat:                         # flattened footprint
            p.z = -flat - (p.z + flat) * 0.15
        v.co = p
    zmin = min(v.co.z for v in tmp.verts)
    zmax = max(v.co.z for v in tmp.verts)
    for v in tmp.verts:
        v.co.z = (v.co.z - zmin) / max(zmax - zmin, 1e-6)          # 0..1
        v.co.x *= sx / 2
        v.co.y *= sy / 2
        v.co.z = v.co.z * (sz + bury) - bury
    a = yaw if yaw is not None else rng.uniform(0, 360)
    m = Matrix.Translation(Vector(center)) @ Matrix.Rotation(math.radians(a), 4, "Z")
    for v in tmp.verts:
        v.co = m @ v.co
    bmesh.ops.recalc_face_normals(tmp, faces=list(tmp.faces))
    return g._append(tmp, Matrix.Identity(4), mat, (rng.uniform(0, 30), rng.uniform(0, 30), 0.0))


def surface_points(g, count, rng, zmin=0.1, zmax=1e9, normal_min_z=-0.2):
    """Random points (+normals) on the faces of Geo ``g`` (for embedding ore)."""
    faces = [f for f in g.bm.faces if zmin <= f.calc_center_median().z <= zmax and f.normal.z >= normal_min_z]
    if not faces:
        return []
    areas = [f.calc_area() for f in faces]
    total = sum(areas)
    out = []
    for _ in range(count):
        r = rng.uniform(0, total)
        acc = 0.0
        for f, a in zip(faces, areas):
            acc += a
            if acc >= r:
                out.append((f.calc_center_median().copy(), f.normal.copy()))
                break
    return out


def surface_distance(g, origin, direction):
    """Distance from ``origin`` along ``direction`` to the surface of ``g``."""
    tree = BVHTree.FromBMesh(g.bm)
    hit = tree.ray_cast(Vector(origin), Vector(direction).normalized())
    return None if hit[0] is None else hit[3]
