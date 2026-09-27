"""Procedural mesh construction kit.

A :class:`Geo` accumulates parts into one bmesh. Every part records

* a material *key* per face (resolved against the shared material library),
* a ``pattern_coord`` point attribute holding the vertex position in the
  part's own local frame (meters). Procedural materials read it so wood grain,
  brushed metal and rust patterns follow each part instead of swimming in
  world space, and texel density stays consistent between assets.

All primitives produce closed, outward-facing geometry unless documented.
"""

import math

import bmesh
import bpy
from mathutils import Matrix, Quaternion, Vector

from core import scene as scn

PATTERN_ATTR = "pattern_coord"
IDENTITY = Matrix.Identity(4)


# ---------------------------------------------------------------- transforms

def trs(loc=(0.0, 0.0, 0.0), rot=None, scale=(1.0, 1.0, 1.0)):
    """Build a 4x4 matrix. ``rot`` may be Euler degrees (xyz), a Quaternion or a 3x3/4x4 Matrix."""
    if rot is None:
        r = Matrix.Identity(4)
    elif isinstance(rot, Quaternion):
        r = rot.to_matrix().to_4x4()
    elif isinstance(rot, Matrix):
        r = rot.to_4x4() if len(rot) == 3 else rot.copy()
    else:
        rx, ry, rz = (math.radians(a) for a in rot)
        r = (Matrix.Rotation(rz, 4, "Z") @ Matrix.Rotation(ry, 4, "Y") @ Matrix.Rotation(rx, 4, "X"))
    s = Matrix.Diagonal((scale[0], scale[1], scale[2], 1.0))
    return Matrix.Translation(Vector(loc)) @ r @ s


def frame_from_axis(origin, axis, up_hint=(0.0, 0.0, 1.0)):
    """Matrix whose local +Z points along ``axis`` (used to orient cylinders/pistons)."""
    z = Vector(axis).normalized()
    up = Vector(up_hint)
    if abs(z.dot(up.normalized())) > 0.98:
        up = Vector((1.0, 0.0, 0.0)) if abs(z.x) < 0.9 else Vector((0.0, 1.0, 0.0))
    x = up.cross(z).normalized()
    y = z.cross(x).normalized()
    m = Matrix((x, y, z)).transposed().to_4x4()
    m.translation = Vector(origin)
    return m


def look_frame(origin, target, up_hint=(0.0, 0.0, 1.0)):
    return frame_from_axis(origin, Vector(target) - Vector(origin), up_hint)


def segments_for(radius, detail=1.0, lo=6, hi=48):
    """Circle resolution that keeps silhouettes smooth at mobile screen sizes."""
    n = int(round(8 + 64 * radius * detail))
    n = max(lo, min(hi, n))
    return n + (n % 2)


# ---------------------------------------------------------------------- Geo

class Geo:
    """Accumulator for one output object."""

    def __init__(self, name, **props):
        self.name = name
        self.bm = bmesh.new()
        self.mat_keys = []
        self.pat = self.bm.verts.layers.float_vector.new(PATTERN_ATTR)
        self.props = dict(props)

    # -- bookkeeping -----------------------------------------------------
    def mat_index(self, key):
        if not key:
            raise ValueError(f"{self.name}: material key must be a non-empty string")
        if key not in self.mat_keys:
            self.mat_keys.append(key)
        return self.mat_keys.index(key)

    def _append(self, tmp, matrix, mat, pattern_offset=None, local_keys=None, pattern_matrix=None, free=True):
        """Copy a temporary bmesh into this Geo.

        Primitives are built in their own bmesh so destructive bmesh operators
        (bevel, inset) can never touch previously added parts. Pattern
        coordinates store the part-local position before ``matrix``.
        """
        keys = local_keys or [mat]
        remap = [self.mat_index(k or mat) for k in keys]
        off = Vector(pattern_offset or (0.0, 0.0, 0.0))
        m = matrix if matrix is not None else IDENTITY
        flip = m.to_3x3().determinant() < 0
        vmap = {}
        for v in tmp.verts:
            p = v.co.copy()
            nv = self.bm.verts.new(m @ p)
            nv[self.pat] = (pattern_matrix @ p if pattern_matrix is not None else p) + off
            vmap[v] = nv
        faces = []
        for f in tmp.faces:
            vs = [vmap[v] for v in f.verts]
            if flip:
                vs.reverse()
            try:
                nf = self.bm.faces.new(vs)
            except ValueError:
                continue
            idx = f.material_index if f.material_index < len(remap) else 0
            nf.material_index = remap[idx]
            nf.smooth = True
            faces.append(nf)
        if free:
            tmp.free()
        return faces

    @staticmethod
    def _bevel_tmp(tmp, offset, segments, edge_filter=None):
        if offset <= 0.0:
            return
        edges = [e for e in tmp.edges if edge_filter is None or edge_filter(e)]
        if edges:
            bmesh.ops.bevel(tmp, geom=edges, offset=offset, offset_type="OFFSET", segments=max(1, segments),
                            profile=0.5, affect="EDGES", clamp_overlap=True)

    # -- raw faces -------------------------------------------------------
    def poly(self, points, matrix=IDENTITY, mat="steel", pattern_offset=None):
        """Single polygon (open surface)."""
        tmp = bmesh.new()
        tmp.faces.new([tmp.verts.new(Vector(p)) for p in points])
        return self._append(tmp, matrix, mat, pattern_offset)

    def mesh(self, verts, faces, matrix=IDENTITY, mat="steel", pattern_offset=None, face_mats=None, recalc=False):
        """Arbitrary vertex/face lists. ``face_mats`` optionally gives a key per face."""
        tmp = bmesh.new()
        vs = [tmp.verts.new(Vector(p)) for p in verts]
        keys = [mat]
        for i, idx in enumerate(faces):
            f = tmp.faces.new([vs[k] for k in idx])
            if face_mats and face_mats[i]:
                if face_mats[i] not in keys:
                    keys.append(face_mats[i])
                f.material_index = keys.index(face_mats[i])
        if recalc:
            bmesh.ops.recalc_face_normals(tmp, faces=list(tmp.faces))
        return self._append(tmp, matrix, mat, pattern_offset, local_keys=keys)

    # -- primitives ------------------------------------------------------
    def box(self, size, matrix=IDENTITY, mat="steel", bevel=0.0, segments=2, pattern_offset=None, center=(0, 0, 0)):
        tmp = bmesh.new()
        bmesh.ops.create_cube(tmp, size=1.0)
        sx, sy, sz = size
        cx, cy, cz = center
        for v in tmp.verts:
            v.co = Vector((v.co.x * sx + cx, v.co.y * sy + cy, v.co.z * sz + cz))
        if bevel > 0.0:
            self._bevel_tmp(tmp, min(bevel, 0.49 * min(abs(sx), abs(sy), abs(sz))), segments)
        return self._append(tmp, matrix, mat, pattern_offset)

    def cylinder(self, radius, depth, segments=None, matrix=IDENTITY, mat="steel", bevel=0.0, bevel_segments=2,
                 caps=True, cap_inset=0.0, radius_top=None, pattern_offset=None, center_z=0.0):
        """Cylinder (or frustum when radius_top is given) along local Z, centered at center_z."""
        rt = radius if radius_top is None else radius_top
        n = segments or segments_for(max(radius, rt))
        tmp = bmesh.new()
        bmesh.ops.create_cone(tmp, cap_ends=caps, cap_tris=False, segments=n, radius1=radius, radius2=rt, depth=depth)
        if center_z:
            for v in tmp.verts:
                v.co.z += center_z
        if caps and cap_inset > 0.0:
            cap_faces = [f for f in tmp.faces if len(f.verts) == n]
            if cap_faces:
                bmesh.ops.inset_individual(tmp, faces=cap_faces, thickness=cap_inset, depth=0.0)
        if bevel > 0.0 and caps:
            tmp.normal_update()
            b = min(bevel, 0.45 * depth, 0.45 * min(radius, rt) if min(radius, rt) > 0 else bevel)

            def rim(e):
                if len(e.link_faces) != 2:
                    return False
                a, c = e.link_faces
                return a.normal.dot(c.normal) < 0.5

            self._bevel_tmp(tmp, b, bevel_segments, rim)
        return self._append(tmp, matrix, mat, pattern_offset)

    def sphere(self, radius, segments=None, rings=None, matrix=IDENTITY, mat="steel", pattern_offset=None,
               scale=(1.0, 1.0, 1.0)):
        n = segments or segments_for(radius, lo=8, hi=32)
        r = rings or max(4, n // 2)
        tmp = bmesh.new()
        bmesh.ops.create_uvsphere(tmp, u_segments=n, v_segments=r, radius=radius)
        for v in tmp.verts:
            v.co = Vector((v.co.x * scale[0], v.co.y * scale[1], v.co.z * scale[2]))
        return self._append(tmp, matrix, mat, pattern_offset)

    def icosphere(self, radius, subdivisions=2, matrix=IDENTITY, mat="stone", pattern_offset=None):
        tmp = bmesh.new()
        bmesh.ops.create_icosphere(tmp, subdivisions=subdivisions, radius=radius)
        return self._append(tmp, matrix, mat, pattern_offset)

    def lathe(self, profile, segments=None, matrix=IDENTITY, mat="steel", band_mats=None, caps=True,
              pattern_offset=None, angle=2 * math.pi, closed_loop=False):
        """Revolve an (r, z) profile around local Z.

        The profile runs counter-clockwise around the solid's cross-section
        (outer wall upward) so normals face outward. ``band_mats`` optionally
        assigns a material key per profile segment.
        """
        pts = [(max(0.0, r), z) for r, z in profile]
        n = segments or segments_for(max(r for r, _ in pts))
        full = abs(angle - 2 * math.pi) < 1e-6
        steps = n if full else n + 1
        tmp = bmesh.new()
        keys = [mat]

        def key_index(k):
            k = k or mat
            if k not in keys:
                keys.append(k)
            return keys.index(k)

        rings = []
        for r, z in pts:
            if r < 1e-7:
                v = tmp.verts.new((0.0, 0.0, z))
                rings.append([v] * steps)
                continue
            rings.append([tmp.verts.new((r * math.cos(angle * k / n), r * math.sin(angle * k / n), z))
                          for k in range(steps)])
        count = len(pts) if closed_loop else len(pts) - 1
        for j in range(count):
            ra, rb = rings[j], rings[(j + 1) % len(pts)]
            mi = key_index(band_mats[j] if band_mats and j < len(band_mats) else None)
            for k in range(n):
                k2 = (k + 1) % steps if full else k + 1
                quad = []
                for v in (ra[k], ra[k2], rb[k2], rb[k]):
                    if v not in quad:
                        quad.append(v)
                if len(quad) < 3:
                    continue
                try:
                    f = tmp.faces.new(quad)
                except ValueError:
                    continue
                f.material_index = mi
        if caps and not closed_loop and full:
            if pts[0][0] > 1e-7:
                f = tmp.faces.new(list(reversed(rings[0])))
                f.material_index = key_index(band_mats[0] if band_mats else None)
            if pts[-1][0] > 1e-7:
                f = tmp.faces.new(rings[-1])
                f.material_index = key_index(band_mats[-1] if band_mats else None)
        return self._append(tmp, matrix, mat, pattern_offset, local_keys=keys)

    def tube(self, r_outer, r_inner, depth, segments=None, matrix=IDENTITY, mat="steel", bevel=0.0,
             pattern_offset=None):
        """Hollow cylinder along Z centered at the origin (flanges, rims, rings)."""
        h = depth / 2.0
        b = min(bevel, 0.3 * (r_outer - r_inner), 0.3 * depth)
        if b > 0:
            prof = [(r_outer - b, -h), (r_outer, -h + b), (r_outer, h - b), (r_outer - b, h),
                    (r_inner + b, h), (r_inner, h - b), (r_inner, -h + b), (r_inner + b, -h)]
        else:
            prof = [(r_outer, -h), (r_outer, h), (r_inner, h), (r_inner, -h)]
        return self.lathe(prof, segments=segments or segments_for(r_outer), matrix=matrix, mat=mat,
                          caps=False, closed_loop=True, pattern_offset=pattern_offset)

    def torus(self, major, minor, seg_major=None, seg_minor=8, matrix=IDENTITY, mat="steel", pattern_offset=None):
        prof = [(major + minor * math.cos(2 * math.pi * k / seg_minor), minor * math.sin(2 * math.pi * k / seg_minor))
                for k in range(seg_minor)]
        return self.lathe(prof, segments=seg_major or segments_for(major + minor), matrix=matrix, mat=mat,
                          caps=False, closed_loop=True, pattern_offset=pattern_offset)

    def extrude(self, outline, depth, matrix=IDENTITY, mat="steel", bevel=0.0, segments=2, pattern_offset=None,
                side_mat=None):
        """Extrude a closed 2D outline (XY, counter-clockwise) along +Z from z=0 to z=depth."""
        tmp = bmesh.new()
        bottom = [tmp.verts.new((x, y, 0.0)) for x, y in outline]
        top = [tmp.verts.new((x, y, depth)) for x, y in outline]
        tmp.faces.new(list(reversed(bottom)))
        tmp.faces.new(top)
        n = len(outline)
        for i in range(n):
            j = (i + 1) % n
            f = tmp.faces.new([bottom[i], bottom[j], top[j], top[i]])
            if side_mat:
                f.material_index = 1
        if bevel > 0.0:
            self._bevel_tmp(tmp, bevel, segments)
        keys = [mat, side_mat] if side_mat else [mat]
        return self._append(tmp, matrix, mat, pattern_offset, local_keys=keys)

    def sweep(self, path, profile=None, radius=0.05, segments=8, closed_path=False, caps=True, matrix=IDENTITY,
              mat="steel", pattern_offset=None, scales=None, up_hint=(0.0, 0.0, 1.0)):
        """Sweep a closed 2D profile (counter-clockwise) along a 3D polyline with
        rotation-minimising frames. Without a profile a circle of ``radius`` is used."""
        pts = [Vector(p) for p in path]
        if len(pts) < 2:
            raise ValueError(f"{self.name}: sweep path needs at least two points")
        if profile is None:
            profile = [(radius * math.cos(2 * math.pi * k / segments), radius * math.sin(2 * math.pi * k / segments))
                       for k in range(segments)]
        m = len(pts)
        tangents = []
        for i in range(m):
            if closed_path:
                t = (pts[(i + 1) % m] - pts[i]).normalized() + (pts[i] - pts[i - 1]).normalized()
            elif i == 0:
                t = pts[1] - pts[0]
            elif i == m - 1:
                t = pts[-1] - pts[-2]
            else:
                t = (pts[i + 1] - pts[i]).normalized() + (pts[i] - pts[i - 1]).normalized()
            if t.length < 1e-9:
                t = pts[min(i + 1, m - 1)] - pts[max(i - 1, 0)]
            tangents.append(t.normalized())
        up = Vector(up_hint)
        n0 = up - tangents[0] * up.dot(tangents[0])
        if n0.length < 1e-6:
            alt = Vector((1.0, 0.0, 0.0)) if abs(tangents[0].x) < 0.9 else Vector((0.0, 1.0, 0.0))
            n0 = alt - tangents[0] * alt.dot(tangents[0])
        normals = [n0.normalized()]
        for i in range(1, m):
            q = tangents[i - 1].rotation_difference(tangents[i])
            nn = q @ normals[-1]
            nn = (nn - tangents[i] * nn.dot(tangents[i])).normalized()
            normals.append(nn)
        tmp = bmesh.new()
        rings = []
        for i in range(m):
            t, nrm = tangents[i], normals[i]
            b = t.cross(nrm)
            s_i = scales[i] if scales else 1.0
            bend = None
            miter = 1.0
            if (0 < i < m - 1) or closed_path:
                seg = (pts[(i + 1) % m] - pts[i]).normalized()
                c = max(0.3, seg.dot(t))
                miter = 1.0 / c
                bend = seg - t * seg.dot(t)
                bend = bend.normalized() if bend.length > 1e-6 else None
            ring = []
            for x, y in profile:
                off = (nrm * x + b * y) * s_i
                if bend is not None and miter != 1.0:
                    off = off + bend * off.dot(bend) * (miter - 1.0)
                ring.append(tmp.verts.new(pts[i] + off))
            rings.append(ring)
        k = len(profile)
        count = m if closed_path else m - 1
        for i in range(count):
            ra, rb = rings[i], rings[(i + 1) % m]
            for j in range(k):
                j2 = (j + 1) % k
                tmp.faces.new([ra[j], ra[j2], rb[j2], rb[j]])
        if caps and not closed_path:
            tmp.faces.new(list(reversed(rings[0])))
            tmp.faces.new(rings[-1])
        return self._append(tmp, matrix, mat, pattern_offset)

    def grid(self, size_x, size_y, nx, ny, height_fn=None, matrix=IDENTITY, mat="soil", pattern_offset=None,
             skirt=0.0):
        """Height-field grid centered at the origin; optional skirt closes the sides downward."""
        tmp = bmesh.new()
        verts = []
        for j in range(ny + 1):
            for i in range(nx + 1):
                x = -size_x / 2 + size_x * i / nx
                y = -size_y / 2 + size_y * j / ny
                z = height_fn(x, y) if height_fn else 0.0
                verts.append(tmp.verts.new((x, y, z)))
        for j in range(ny):
            for i in range(nx):
                a = j * (nx + 1) + i
                tmp.faces.new([verts[a], verts[a + 1], verts[a + nx + 2], verts[a + nx + 1]])
        if skirt > 0.0:
            border = ([verts[i] for i in range(nx + 1)] +
                      [verts[j * (nx + 1) + nx] for j in range(1, ny + 1)] +
                      [verts[ny * (nx + 1) + i] for i in range(nx - 1, -1, -1)] +
                      [verts[j * (nx + 1)] for j in range(ny - 1, 0, -1)])
            low = [tmp.verts.new((v.co.x, v.co.y, -skirt)) for v in border]
            nb = len(border)
            for i in range(nb):
                i2 = (i + 1) % nb
                tmp.faces.new([border[i2], border[i], low[i], low[i2]])
            tmp.faces.new(list(low))
        return self._append(tmp, matrix, mat, pattern_offset)

    # -- editing -----------------------------------------------------------
    def inset_panels(self, faces, thickness, depth, mat=None):
        """Inset faces to create panel breaks (a recessed seam around each panel)."""
        faces = [f for f in faces if f.is_valid]
        if not faces:
            return []
        res = bmesh.ops.inset_individual(self.bm, faces=faces, thickness=thickness, depth=depth,
                                         use_even_offset=True)
        if mat:
            mi = self.mat_index(mat)
            for f in res["faces"]:
                f.material_index = mi
        return res["faces"]

    def faces_facing(self, direction, min_dot=0.9, faces=None):
        d = Vector(direction).normalized()
        src = faces if faces is not None else self.bm.faces
        self.bm.normal_update()
        return [f for f in src if f.is_valid and f.normal.dot(d) >= min_dot]

    def set_material(self, faces, key):
        mi = self.mat_index(key)
        for f in faces:
            if f.is_valid:
                f.material_index = mi

    def transform_all(self, matrix):
        bmesh.ops.transform(self.bm, matrix=matrix, verts=list(self.bm.verts))

    def merge_from(self, other, matrix=IDENTITY):
        """Append another Geo (materials remapped)."""
        remap = {i: self.mat_index(k) for i, k in enumerate(other.mat_keys)}
        vmap = {}
        for v in other.bm.verts:
            nv = self.bm.verts.new(matrix @ v.co)
            nv[self.pat] = v[other.pat]
            vmap[v] = nv
        flip = matrix.to_3x3().determinant() < 0
        for f in other.bm.faces:
            vs = [vmap[v] for v in f.verts]
            if flip:
                vs.reverse()
            try:
                nf = self.bm.faces.new(vs)
            except ValueError:
                continue
            nf.material_index = remap[f.material_index]
            nf.smooth = f.smooth

    def is_empty(self):
        return len(self.bm.faces) == 0

    # -- output ------------------------------------------------------------
    def to_object(self, library, collection=None, smooth_angle=32.0, weighted_normals=True, shade="auto"):
        """Create the Blender object, assign library materials and normals."""
        if self.is_empty():
            raise ValueError(f"Geo '{self.name}' is empty")
        bmesh.ops.dissolve_degenerate(self.bm, dist=1e-7, edges=list(self.bm.edges))
        me = bpy.data.meshes.new(self.name)
        self.bm.normal_update()
        self.bm.to_mesh(me)
        self.bm.free()
        self.bm = None
        obj = bpy.data.objects.new(self.name, me)
        for key in self.mat_keys:
            me.materials.append(library.get(key))
        scn.link(obj, collection)
        obj["mm_kind"] = "render"
        for k, v in self.props.items():
            obj[k] = v
        apply_shading(obj, smooth_angle, weighted_normals and shade != "smooth", shade)
        return obj


def apply_shading(obj, smooth_angle=32.0, weighted=True, shade="auto"):
    me = obj.data
    if shade == "flat":
        me.shade_flat()
        return
    me.shade_smooth()
    if shade == "smooth":
        return
    me.set_sharp_from_angle(angle=math.radians(smooth_angle))
    if weighted:
        mod = obj.modifiers.new("WeightedNormal", "WEIGHTED_NORMAL")
        mod.mode = "FACE_AREA"
        mod.keep_sharp = True
        mod.weight = 50
        apply_modifiers(obj)


def apply_modifiers(obj, only_types=None):
    """Apply modifiers without operators (robust in background mode).

    ``only_types`` limits application to those modifier types; the others stay
    on the object untouched.
    """
    others = [m for m in obj.modifiers if only_types is not None and m.type not in only_types]
    saved_vis = [(m.name, m.show_viewport) for m in others]
    for m in others:
        m.show_viewport = False
    deps = bpy.context.evaluated_depsgraph_get()
    deps.update()
    ev = obj.evaluated_get(deps)
    new_me = bpy.data.meshes.new_from_object(ev, preserve_all_data_layers=True, depsgraph=deps)
    old = obj.data
    name = old.name
    old.name = name + "__old"
    new_me.name = name
    for m in list(obj.modifiers):
        if only_types is None or m.type in only_types:
            obj.modifiers.remove(m)
    obj.data = new_me
    for mname, vis in saved_vis:
        if mname in obj.modifiers:
            obj.modifiers[mname].show_viewport = vis
    if old.users == 0:
        bpy.data.meshes.remove(old)
    return obj
