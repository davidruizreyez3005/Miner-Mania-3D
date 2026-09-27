"""Skinned geometry container used by all character modules.

Holds a bmesh with a deform (vertex-group) layer, pattern coordinates and
per-face material keys, and converts to a Blender object with named vertex
groups. Rigid pieces (eyes, buttons, pouches) can be appended with 100%
weight to one bone.
"""

import bmesh
import bpy
from mathutils import Matrix, Vector

from core import scene as scn
from utilities.meshkit import PATTERN_ATTR, apply_modifiers


class SkinnedGeo:
    def __init__(self, name, pattern_origin=(0.0, 0.0, 0.0)):
        self.name = name
        self.bm = bmesh.new()
        self.dl = self.bm.verts.layers.deform.verify()
        self.pat = self.bm.verts.layers.float_vector.new(PATTERN_ATTR)
        self.mat_keys = []
        self.groups = {}
        self.pattern_origin = Vector(pattern_origin)
        self.subdivide = 0

    def mat(self, key):
        if key not in self.mat_keys:
            self.mat_keys.append(key)
        return self.mat_keys.index(key)

    def gidx(self, bone):
        if bone not in self.groups:
            self.groups[bone] = len(self.groups)
        return self.groups[bone]

    def vert(self, co, weights, pat=None):
        v = self.bm.verts.new(Vector(co))
        v[self.pat] = Vector(pat) if pat is not None else Vector(co) - self.pattern_origin
        tot = sum(w for w in weights.values() if w > 0)
        for b, w in weights.items():
            if w > 0:
                v[self.dl][self.gidx(b)] = w / tot
        return v

    def face(self, verts, key):
        f = self.bm.faces.new(verts)
        f.material_index = self.mat(key)
        f.smooth = True
        return f

    def set_weights(self, v, weights):
        for g in list(v[self.dl].keys()):
            del v[self.dl][g]
        tot = sum(w for w in weights.values() if w > 0)
        for b, w in weights.items():
            if w > 0:
                v[self.dl][self.gidx(b)] = w / tot

    def append_geo(self, geo, weights_fn, matrix=None):
        """Append a meshkit Geo (hard-surface detail) with weights from
        ``weights_fn(world_co) -> {bone: w}``."""
        m = matrix or Matrix.Identity(4)
        flip = m.to_3x3().determinant() < 0
        vmap = {}
        for v in geo.bm.verts:
            co = m @ v.co
            nv = self.vert(co, weights_fn(co), pat=v[geo.pat])
            vmap[v] = nv
        for f in geo.bm.faces:
            vs = [vmap[v] for v in f.verts]
            if flip:
                vs.reverse()
            try:
                nf = self.bm.faces.new(vs)
            except ValueError:
                continue
            nf.material_index = self.mat(geo.mat_keys[f.material_index])
            nf.smooth = True
        geo.bm.free()
        geo.bm = None

    def append_rigid(self, geo, bone, matrix=None):
        self.append_geo(geo, lambda co: {bone: 1.0}, matrix)

    def group_names(self):
        return [b for b, _ in sorted(self.groups.items(), key=lambda kv: kv[1])]

    def to_object(self, library, subdivide=None, props=None):
        levels = self.subdivide if subdivide is None else subdivide
        me = bpy.data.meshes.new(self.name)
        self.bm.normal_update()
        self.bm.to_mesh(me)
        self.bm.free()
        self.bm = None
        obj = bpy.data.objects.new(self.name, me)
        for g in self.group_names():
            obj.vertex_groups.new(name=g)
        for key in self.mat_keys:
            me.materials.append(library.get(key))
        scn.link(obj)
        obj["mm_kind"] = "render"
        for k, v in (props or {}).items():
            obj[k] = v
        me.shade_smooth()
        if levels:
            mod = obj.modifiers.new("Subdivision", "SUBSURF")
            mod.levels = levels
            mod.render_levels = levels
            mod.quality = 3
            mod.uv_smooth = "PRESERVE_BOUNDARIES"
            mod.boundary_smooth = "ALL"
            apply_modifiers(obj)
            me = obj.data
            me.shade_smooth()
        return obj


def copy_cage_faces(cage, faces, dst, material_key, offset_fn=None, weight_override=None):
    """Copy BodyCage faces into ``dst`` (SkinnedGeo), offsetting each vertex by
    ``offset_fn(v) -> Vector`` and keeping its skin weights. Returns the
    vertex map (cage vert -> new vert)."""
    names = cage.group_names()
    vmap = {}
    for f in faces:
        for v in f.verts:
            if v in vmap:
                continue
            w = {names[g]: wt for g, wt in v[cage.dl].items()}
            if weight_override:
                w = weight_override(v, w)
            co = v.co + (offset_fn(v) if offset_fn else Vector())
            nv = dst.vert(co, w, pat=v[cage.pat])
            vmap[v] = nv
    for f in faces:
        nf = dst.bm.faces.new([vmap[v] for v in f.verts])
        nf.material_index = dst.mat(material_key)
        nf.smooth = True
    return vmap
