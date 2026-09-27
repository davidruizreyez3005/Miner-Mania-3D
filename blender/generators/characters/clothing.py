"""Garments derived from the body cage.

A garment copies cage faces by zone (so every garment vertex inherits the
exact skin weights of the body under it), offsets them along the body normals
(thickness + looseness), then finishes open borders with rolled hems, cuffs,
waistbands or collars. Border faces are created with face-consistent winding,
so open shells never need a (fragile) global normal recalculation.

Each garment also reports which body zones it hides; the worker assembly
deletes those body faces (no hidden triangles, no z-fighting).
"""

import math

import bmesh
from mathutils import Matrix, Vector
from mathutils.kdtree import KDTree

from utilities.meshkit import Geo, frame_from_axis

from .body import ARM_L, ARM_R, HAND_L, HAND_R, LEG_L, LEG_R, NECK, TORSO
from .skinned import SkinnedGeo


def zones(region, bands):
    return {region * 100 + b for b in bands}


def arm_zones(bands):
    return zones(ARM_L, bands) | zones(ARM_R, bands)


def leg_zones(bands):
    return zones(LEG_L, bands) | zones(LEG_R, bands)


def hand_zones():
    return {r * 100 + i for r in (HAND_L, HAND_R) for i in range(100)}


SLEEVES = {"long": 7, "rolled": 5, "short": 2, "none": 0}


class Garment:
    def __init__(self, name, cage):
        self.cage = cage
        self.g = SkinnedGeo(name)
        self.g.subdivide = 1
        self.details = []          # (Geo, matrix, max_lod, rigid) details, never subdivided
        self.vmap = {}
        self.hides = set()
        self.names = cage.group_names()
        self._kd = None

    # ------------------------------------------------------------ building
    def add_region(self, zone_set, mat_key, thickness, face_filter=None, mat_fn=None):
        cage = self.cage
        faces = [f for f in cage.bm.faces if f[cage.fzone] in zone_set and (face_filter is None or face_filter(f))]
        for f in faces:
            for v in f.verts:
                if v in self.vmap:
                    continue
                w = {self.names[gi]: wt for gi, wt in v[cage.dl].items()}
                t = thickness(v) if callable(thickness) else thickness
                self.vmap[v] = self.g.vert(v.co + v.normal * t, w, pat=v[cage.pat])
        for f in faces:
            key = mat_fn(f) if mat_fn else mat_key
            nf = self.g.bm.faces.new([self.vmap[v] for v in f.verts])
            nf.material_index = self.g.mat(key or mat_key)
            nf.smooth = True
        return faces

    def boundary_loops(self):
        """Open borders as ordered edge chains [(a, b), ...] following face winding."""
        bm = self.g.bm
        nxt = {}
        for e in bm.edges:
            if len(e.link_faces) != 1:
                continue
            f = e.link_faces[0]
            for lp in f.loops:
                if lp.edge == e:
                    a, b = lp.vert, lp.link_loop_next.vert
                    nxt[a] = b
                    break
        loops = []
        seen = set()
        for start in list(nxt.keys()):
            if start in seen:
                continue
            chain = []
            v = start
            while v not in seen and v in nxt:
                seen.add(v)
                chain.append((v, nxt[v]))
                v = nxt[v]
            if chain:
                loops.append(chain)
        return loops

    def _outward(self, v):
        """Direction continuing the surface past a border vertex."""
        acc = Vector()
        for e in v.link_edges:
            o = e.other_vert(v)
            if len(e.link_faces) == 2:
                acc += (v.co - o.co).normalized()
        return acc.normalized() if acc.length > 1e-9 else Vector((0, 0, -1))

    def _vnormal(self, v):
        n = Vector()
        for f in v.link_faces:
            n += f.normal
        return n.normalized() if n.length > 1e-9 else Vector((0, 0, 1))

    def extrude_border(self, loop, steps, mat_key):
        """Extrude a border chain through successive offsets.

        ``steps`` is a list of callables ``f(v, outward, normal) -> Vector``
        giving each new ring position from the previous ring vertex.
        """
        g = self.g
        bm = g.bm
        bm.normal_update()
        ring = {}
        for a, b in loop:
            ring[a] = a
        order = [a for a, _ in loop]
        closed = loop[-1][1] == loop[0][0]
        if not closed:
            order.append(loop[-1][1])
            ring[loop[-1][1]] = loop[-1][1]
        base_out = {v: self._outward(v) for v in order}
        base_n = {v: self._vnormal(v) for v in order}
        prev = {v: v for v in order}
        names = g.group_names()
        for step in steps:
            cur = {}
            for v in order:
                p = prev[v]
                co = step(p, base_out[v], base_n[v])
                w = {names[gi]: wt for gi, wt in p[g.dl].items()}
                cur[v] = g.vert(co, w, pat=p[g.pat])
            pairs = list(zip(order, order[1:])) + ([(order[-1], order[0])] if closed else [])
            for a, b in pairs:
                f = bm.faces.new([prev[b], prev[a], cur[a], cur[b]])
                f.material_index = g.mat(mat_key)
                f.smooth = True
            prev = cur
        return prev

    def hem(self, loop, mat_key, out=0.008, fold=0.009):
        """Rolled hem/cuff: extend past the border, then fold back under."""
        self.extrude_border(loop, [
            lambda p, o, n: p.co + o * out + n * 0.002,
            lambda p, o, n: p.co + o * 0.002 - n * fold,
            lambda p, o, n: p.co - o * out * 1.2,
        ], mat_key)

    # ------------------------------------------------------------ details
    def _kdtree(self):
        if self._kd is None:
            cage = self.cage
            verts = [v for v in cage.bm.verts if v.is_valid]
            kd = KDTree(len(verts))
            for i, v in enumerate(verts):
                kd.insert(v.co, i)
            kd.balance()
            self._kd = (kd, verts)
        return self._kd

    def weights_at(self, co):
        kd, verts = self._kdtree()
        acc = {}
        tot = 0.0
        for (p, i, d) in kd.find_n(co, 3):
            w = 1.0 / max(d, 1e-4)
            tot += w
            for gi, wt in verts[i][self.cage.dl].items():
                acc[self.names[gi]] = acc.get(self.names[gi], 0.0) + wt * w
        return {k: v / tot for k, v in acc.items()}

    def surface_frame(self, target, offset):
        """Point on the (offset) body surface nearest to ``target`` with its normal."""
        kd, verts = self._kdtree()
        p, i, d = kd.find(target)
        v = verts[i]
        n = v.normal.copy()
        return v.co + n * offset, n

    def patch(self, target, size, offset, mat_key, up=(0.0, 0.0, 1.0), flap=True, max_lod=99):
        """Pocket-like patch sitting on the surface near ``target``."""
        pos, n = self.surface_frame(Vector(target), offset)
        z = n
        y = Vector(up) - z * Vector(up).dot(z)
        y.normalize()
        x = y.cross(z)
        m = Matrix((x, y, z)).transposed().to_4x4()
        m.translation = pos + n * (size[2] * 0.5)
        geo = Geo("patch")
        geo.box(size, mat=mat_key, bevel=min(size) * 0.3, segments=1)
        if flap:
            geo.box((size[0] * 1.04, size[1] * 0.3, size[2] * 1.4), mat=mat_key, bevel=0.002, segments=1,
                    center=(0, size[1] * 0.38, size[2] * 0.3))
        self.details.append((geo, m, max_lod, True))

    def button_line(self, points, offset, mat_key, radius=0.0055):
        for p in points:
            pos, n = self.surface_frame(Vector(p), offset)
            m = frame_from_axis(pos + n * 0.001, n)
            geo = Geo("button")
            geo.cylinder(radius, 0.004, segments=8, mat=mat_key, bevel=0.0012, bevel_segments=1)
            self.details.append((geo, m, 0, True))

    def strip(self, points, offset, width, depth, mat_key, max_lod=99):
        """Thin strip following surface points (zippers, tie, straps)."""
        path = []
        for p in points:
            pos, n = self.surface_frame(Vector(p), offset)
            path.append(pos + n * depth * 0.5)
        geo = Geo("strip")
        prof = [(-width / 2, -depth / 2), (width / 2, -depth / 2), (width / 2, depth / 2), (-width / 2, depth / 2)]
        geo.sweep(path, profile=prof, mat=mat_key, up_hint=(0, -1, 0))
        self.details.append((geo, Matrix.Identity(4), max_lod, False))

    def finish(self):
        """Return (garment SkinnedGeo, [(detail SkinnedGeo, max_lod), ...]).

        Small rigid details (pockets, buttons, buckles) use one weight set taken
        at their center so they never distort; strips (zippers, belts, ties)
        follow the surface with per-vertex weights."""
        groups = {}
        for geo, m, max_lod, rigid in self.details:
            det = groups.get(max_lod)
            if det is None:
                det = groups[max_lod] = SkinnedGeo(f"{self.g.name}_details_lod{max_lod}")
            if rigid:
                w = self.weights_at(m.translation)
                det.append_geo(geo, lambda co, w=w: w, m)
            else:
                det.append_geo(geo, self.weights_at, m)
        return self.g, sorted(((d, lod) for lod, d in groups.items()), key=lambda x: x[1])


# ---------------------------------------------------------------- outfits

def _loose(base, extra_by_ring):
    def fn(v):
        z = v.co.z
        t = base
        for (z0, z1, e) in extra_by_ring:
            if z0 <= z <= z1:
                t += e
        return t
    return fn


def _torso_face_k(cage, f):
    """Column index of a torso band face (0..17) from its vertex zones."""
    cen = f.calc_center_median()
    th = math.atan2(cen.x, -cen.y)
    return int(round((th % (2 * math.pi)) / (2 * math.pi) * 18 - 0.5)) % 18


def armhole_filter(cage):
    """Exclude torso faces around the arm openings (sleeveless vests)."""
    def keep(f):
        z = f[cage.fzone]
        if z // 100 != TORSO:
            return True
        band = z % 100
        if band not in (5, 6, 7):
            return True
        c = f.calc_center_median()
        lateral = abs(c.x) / max(abs(c.x) + abs(c.y), 1e-6)
        return lateral < (0.62 if band == 5 else 0.55)
    return keep


def shirt(cage, color_key, sleeves="long", tucked=True, collar=True, pockets=True, buttons=True,
          fabric="fabric", name="shirt", loose=0.0, hem_bands=None):
    gm = Garment(name, cage)
    key = f"{fabric}:{color_key}"
    lo_band = 2 if tucked else 1
    bands = range(lo_band, 9)
    s_end = SLEEVES[sleeves]
    thick = _loose(0.0065 + loose, [(0.95, 1.13, 0.006 + loose), (1.13, 1.3, 0.003)])
    gm.add_region(zones(TORSO, bands), key, thick)
    if s_end:
        gm.add_region(arm_zones(range(0, s_end)), key, 0.006 + loose * 0.5)
    loops = gm.boundary_loops()
    for lp in loops:
        zc = sum(a.co.z for a, _ in lp) / len(lp)
        xc = sum(abs(a.co.x) for a, _ in lp) / len(lp)
        if xc > 0.25:  # sleeve end (rolled sleeves get a thick cuff)
            gm.hem(lp, key, out=0.006 if sleeves != "rolled" else 0.012, fold=0.01 if sleeves != "rolled" else 0.022)
        elif zc > 1.4:  # neckline
            if collar:
                gm.extrude_border(lp, [
                    lambda p, o, n: p.co + Vector((0, 0, 0.022)) + n * -0.004,
                    lambda p, o, n: p.co + n * 0.012 + Vector((0, 0, 0.004)),
                    lambda p, o, n: p.co + n * 0.01 + Vector((0, 0, -0.03)),
                ], key)
            else:
                gm.hem(lp, key, out=0.004, fold=0.006)
        else:  # bottom hem
            gm.hem(lp, key, out=0.01, fold=0.012)
    hides = zones(TORSO, range(lo_band + (1 if tucked else 0), 10)) | zones(NECK, (0, 1))
    if s_end:
        hides |= arm_zones(range(0, max(0, s_end - 1)))
    gm.hides = hides
    if pockets:
        for sx in (1, -1):
            gm.patch((0.075 * sx, -0.12, 1.3), (0.085, 0.1, 0.006), 0.01, key, max_lod=1)
    if buttons:
        gm.button_line([(0.0, -0.13, z) for z in (1.08, 1.17, 1.26, 1.35)], 0.012, "plastic:plastic_white")
    return gm


def pants(cage, color_key, fabric="denim", name="pants", end_band=7, knee_patch=None, cargo=False):
    gm = Garment(name, cage)
    key = f"{fabric}:{color_key}"
    thick = _loose(0.012, [(0.5, 0.92, 0.006), (0.2, 0.5, 0.004)])

    def mat_fn(f):
        if knee_patch and f[cage.fzone] % 100 in (3, 4) and f[cage.fzone] // 100 in (LEG_L, LEG_R):
            c = f.calc_center_median()
            if c.y < -0.01:
                return knee_patch
        return key
    gm.add_region(zones(TORSO, (0, 1, 2)), key, thick)
    gm.add_region(leg_zones(range(0, end_band)), key, thick, mat_fn=mat_fn)
    for lp in gm.boundary_loops():
        zc = sum(a.co.z for a, _ in lp) / len(lp)
        if zc > 0.9:  # waistband
            gm.extrude_border(lp, [
                lambda p, o, n: p.co + Vector((0, 0, 0.022)) + n * 0.003,
                lambda p, o, n: p.co + n * -0.012,
                lambda p, o, n: p.co + Vector((0, 0, -0.02)),
            ], key)
        else:
            gm.hem(lp, key, out=0.006, fold=0.008)
    gm.hides = zones(TORSO, (0, 1)) | leg_zones(range(0, end_band - 1))
    if cargo:
        for sx in (1, -1):
            gm.patch((0.14 * sx, -0.02, 0.66), (0.11, 0.13, 0.012), 0.012, key, up=(0, 0, 1), max_lod=1)
    return gm


def coveralls(cage, color_key, stripe=True, name="coveralls", sleeves="long"):
    gm = Garment(name, cage)
    key = f"fabric:{color_key}"
    s_end = SLEEVES[sleeves]
    thick = _loose(0.009, [(0.95, 1.2, 0.006), (0.55, 0.9, 0.004)])

    def mat_fn(f):
        z = f[cage.fzone]
        if stripe and z // 100 in (LEG_L, LEG_R) and z % 100 == 5:
            return "reflective"
        if stripe and z // 100 in (ARM_L, ARM_R) and z % 100 == 3:
            return "reflective"
        return key
    gm.add_region(zones(TORSO, range(0, 9)), key, thick)
    gm.add_region(leg_zones(range(0, 7)), key, thick, mat_fn=mat_fn)
    if s_end:
        gm.add_region(arm_zones(range(0, s_end)), key, 0.008, mat_fn=mat_fn)
    for lp in gm.boundary_loops():
        zc = sum(a.co.z for a, _ in lp) / len(lp)
        xc = sum(abs(a.co.x) for a, _ in lp) / len(lp)
        if zc > 1.4 and xc < 0.2:
            gm.extrude_border(lp, [
                lambda p, o, n: p.co + Vector((0, 0, 0.024)) + n * -0.004,
                lambda p, o, n: p.co + n * 0.012 + Vector((0, 0, 0.004)),
                lambda p, o, n: p.co + n * 0.01 + Vector((0, 0, -0.03)),
            ], key)
        else:
            gm.hem(lp, key, out=0.007, fold=0.01)
    gm.hides = zones(TORSO, range(0, 10)) | zones(NECK, (0, 1)) | leg_zones(range(0, 6))
    if s_end:
        gm.hides |= arm_zones(range(0, max(0, s_end - 1)))
    gm.strip([(0.0, -0.1, z) for z in (0.93, 1.05, 1.17, 1.29, 1.4, 1.46)], 0.014, 0.012, 0.004, "steel",
             max_lod=1)
    gm.patch((0.08, -0.12, 1.3), (0.09, 0.1, 0.006), 0.014, key, max_lod=1)
    return gm


def vest(cage, color_key, stripes=True, name="vest", pockets=0, fabric="fabric", over=0.022):
    gm = Garment(name, cage)
    key = f"{fabric}:{color_key}"

    def mat_fn(f):
        if not stripes:
            return key
        band = f[cage.fzone] % 100
        if band in (3, 5):
            return "reflective"
        if band in (6, 7, 8):
            k = _torso_face_k(cage, f)
            if k in (2, 15, 7, 10):
                return "reflective"
        return key
    thick = _loose(over, [(0.95, 1.13, 0.006)])
    gm.add_region(zones(TORSO, range(2, 9)), key, thick, face_filter=armhole_filter(cage), mat_fn=mat_fn)
    for lp in gm.boundary_loops():
        gm.hem(lp, key, out=0.004, fold=0.008)
    for i in range(pockets):
        row, col = divmod(i, 2)
        sx = 1 if col == 0 else -1
        gm.patch((0.08 * sx, -0.13, 1.1 + 0.1 * row), (0.08, 0.07, 0.012), over + 0.006, key, max_lod=1)
    return gm


def gloves(cage, color_key, fabric="leather", name="gloves"):
    gm = Garment(name, cage)
    key = f"{fabric}:{color_key}"
    gm.add_region(hand_zones(), key, lambda v: 0.0035 if (v[cage.vzone] % 100) >= 10 else 0.005)
    gm.add_region(arm_zones((7,)), key, 0.012)
    for lp in gm.boundary_loops():
        gm.extrude_border(lp, [
            lambda p, o, n: p.co + o * 0.012 + n * 0.006,
            lambda p, o, n: p.co - n * 0.014,
        ], key)
    gm.hides = hand_zones() | arm_zones((7,))
    return gm


def tie(cage, color_key):
    gm = Garment("tie", cage)
    pts = [(0.0, -0.12, z) for z in (1.44, 1.38, 1.3, 1.22, 1.15)]
    gm.strip(pts, 0.014, 0.05, 0.006, f"fabric:{color_key}", max_lod=1)
    return gm


def belt(cage, leather_key="leather:leather_brown", buckle_key="brass", z=1.0, name="belt"):
    """A belt band around the waist (over pants) with a buckle."""
    gm = Garment(name, cage)
    path = []
    for k in range(18):
        a = cage.rings["torso"][2][k].co
        b = cage.rings["torso"][3][k].co
        p = a.lerp(b, 0.35)
        n = (cage.rings["torso"][2][k].normal + cage.rings["torso"][3][k].normal).normalized()
        path.append(p + n * 0.02)
    geo = Geo("belt")
    geo.sweep(path, profile=[(-0.004, -0.02), (0.004, -0.02), (0.004, 0.02), (-0.004, 0.02)], mat=leather_key,
              closed_path=True, caps=False, up_hint=(0, 0, 1))
    gm.details.append((geo, Matrix.Identity(4), 99, False))
    front = path[0]
    bk = Geo("buckle")
    bk.box((0.05, 0.008, 0.04), mat=buckle_key, bevel=0.003, segments=1)
    gm.details.append((bk, Matrix.Translation(front + Vector((0, -0.005, 0))), 99, True))
    return gm
