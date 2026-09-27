"""Pure-math model of the humanoid rig: rest frames, FK and analytic IK.

All clip authoring happens here, independent of any Blender scene, so the
animation library is computed once per build and reused by every worker
variant (they share the skeleton). Rest frames are derived from the skeleton
spec exactly like Blender's ``align_roll``; library.py verifies them against
the real armature before writing keys.

Frames are 4x4 matrices in armature space; the worker faces -Y, +X is its
left. Bone axes: Y along the bone; trunk/limb Z forward; hand/finger Z toward
the palm; foot/toe Z up; socket Y = item up, socket Z = item front.
"""

import math

from mathutils import Matrix, Quaternion, Vector

from rigging.human_rig import skeleton

UP = Vector((0.0, 0.0, 1.0))
FWD = Vector((0.0, -1.0, 0.0))


def frame(origin, y_axis, z_hint):
    y = Vector(y_axis).normalized()
    z = Vector(z_hint)
    z = (z - y * z.dot(y))
    if z.length < 1e-9:
        alt = Vector((1, 0, 0)) if abs(y.x) < 0.9 else Vector((0, 0, 1))
        z = alt - y * alt.dot(y)
    z.normalize()
    x = y.cross(z)
    m = Matrix((x, y, z)).transposed().to_4x4()
    m.translation = Vector(origin)
    return m


def rot_local(flex=0.0, twist=0.0, side=0.0):
    """Quaternion from semantic local rotations in degrees (X flex, Y twist, Z side)."""
    q = Quaternion((0.0, 0.0, 1.0), math.radians(side))
    q = q @ Quaternion((1.0, 0.0, 0.0), math.radians(flex))
    q = q @ Quaternion((0.0, 1.0, 0.0), math.radians(twist))
    return q


def mirrored(bone, flex=0.0, twist=0.0, side=0.0):
    """Semantic rotation for ``bone``; right-side bones mirror twist and side."""
    if bone.endswith(".R"):
        return rot_local(flex, -twist, -side)
    return rot_local(flex, twist, side)


class RigModel:
    def __init__(self):
        sk = skeleton()
        self.sk = sk
        self.names = [b.name for b in sk.specs]
        self.parent = {b.name: b.parent for b in sk.specs}
        self.rest = {}
        for b in sk.specs:
            self.rest[b.name] = frame(b.head, Vector(b.tail) - Vector(b.head), b.z_axis)
        self.rest_rel = {}
        for n in self.names:
            p = self.parent[n]
            self.rest_rel[n] = self.rest[n] if p is None else self.rest[p].inverted() @ self.rest[n]
        self.length = {b.name: (Vector(b.tail) - Vector(b.head)).length for b in sk.specs}
        self.children = {n: [c for c in self.names if self.parent[c] == n] for n in self.names}

    # ------------------------------------------------------------------ FK
    def fk(self, basis_rot, basis_loc=None):
        """World (armature-space) matrices for local basis rotations/locations."""
        basis_loc = basis_loc or {}
        world = {}
        for n in self.names:
            q = basis_rot.get(n)
            b = Matrix.Identity(4) if q is None else q.to_matrix().to_4x4()
            if n in basis_loc:
                b = Matrix.Translation(basis_loc[n]) @ b
            p = self.parent[n]
            world[n] = (self.rest_rel[n] if p is None else world[p] @ self.rest_rel[n]) @ b
        return world

    def world_of(self, name, basis_rot, basis_loc, cache):
        """Lazy FK for a single bone (used inside the solver)."""
        if name in cache:
            return cache[name]
        p = self.parent[name]
        q = basis_rot.get(name)
        b = Matrix.Identity(4) if q is None else q.to_matrix().to_4x4()
        if name in basis_loc:
            b = Matrix.Translation(basis_loc[name]) @ b
        m = (self.rest_rel[name] if p is None else self.world_of(p, basis_rot, basis_loc, cache) @ self.rest_rel[name]) @ b
        cache[name] = m
        return m

    def basis_for_world(self, name, desired_world, parent_world):
        """Local basis rotation that realises ``desired_world`` orientation."""
        base = self.rest_rel[name] if parent_world is None else parent_world @ self.rest_rel[name]
        rel = base.inverted() @ desired_world
        q = rel.to_quaternion()
        q.normalize()
        return q

    # ------------------------------------------------------------------ IK
    def two_bone(self, upper, lower, target, pole, parent_world, basis_rot, basis_loc):
        """Analytic two-bone IK.

        Places ``lower``'s tail (wrist/ankle) at ``target`` with the middle
        joint bending toward ``pole``. The hinge axis becomes each bone's
        local X so the joint bends through the bone's own flexion axis, and
        its sign is chosen to stay closest to the un-rotated frame (minimal
        twist). Returns (q_upper, q_lower, reach_error).
        """
        la = self.length[upper]
        lb = self.length[lower]
        base_u = parent_world @ self.rest_rel[upper]
        root = base_u.translation.copy()
        t = Vector(target)
        d = t - root
        dist = d.length
        reach = la + lb
        err = 0.0
        if dist > reach * 0.9999:
            err = dist - reach * 0.9999
            d = d.normalized() * reach * 0.9999
            dist = reach * 0.9999
        dist = max(dist, abs(la - lb) + 1e-4)
        dn = d.normalized()
        # Bend plane from the pole vector.
        pv = Vector(pole) - root
        side = pv - dn * pv.dot(dn)
        if side.length < 1e-6:
            side = base_u.to_3x3().col[2] - dn * base_u.to_3x3().col[2].dot(dn)
        side.normalize()
        cos_a = (la * la + dist * dist - lb * lb) / (2 * la * dist)
        cos_a = max(-1.0, min(1.0, cos_a))
        a = math.acos(cos_a)
        mid = root + dn * (la * math.cos(a)) + side * (la * math.sin(a))
        end = root + dn * dist
        dir_u = (mid - root).normalized()
        dir_l = (end - mid).normalized()
        hinge = dir_u.cross(dir_l)
        if hinge.length < 1e-6:
            hinge = side.cross(dn)
        hinge.normalize()
        # Upper bone frame: Y = dir_u, X = +-hinge (closest to un-rotated X).
        x_ref = base_u.to_3x3().col[0]
        hx = hinge if hinge.dot(x_ref) >= 0 else -hinge
        mu = _frame_xy(root, hx, dir_u)
        q_u = self.basis_for_world(upper, mu, parent_world)
        base_l = mu @ self.rest_rel[lower]
        x_ref_l = base_l.to_3x3().col[0]
        hx_l = hinge if hinge.dot(x_ref_l) >= 0 else -hinge
        ml = _frame_xy(mid, hx_l, dir_l)
        q_l = self.basis_for_world(lower, ml, mu)
        return q_u, q_l, err

    def socket_to_hand(self, side, socket_world):
        """Hand bone world frame that puts ``hand_tool.<side>`` at ``socket_world``."""
        return socket_world @ self.rest_rel[f"hand_tool.{side}"].inverted()


def _frame_xy(origin, x_axis, y_axis):
    y = y_axis.normalized()
    x = (x_axis - y * x_axis.dot(y)).normalized()
    z = x.cross(y)
    m = Matrix((x, y, z)).transposed().to_4x4()
    m.translation = origin
    return m


def socket_frame(origin, up, front):
    """Socket frame from item-up (socket Y) and item-front (socket Z) directions."""
    return frame(origin, up, front)


def hand_socket_frame(side, grip_point, palm_normal, finger_dir):
    """Socket frame from a desired palm normal and finger (distal) direction.

    Mirrors the rest-pose relation: left hand P = D x T, right hand P = T x D;
    socket Y = thumb direction T, socket Z = distal direction D.
    """
    p = Vector(palm_normal).normalized()
    d = Vector(finger_dir)
    d = (d - p * d.dot(p)).normalized()
    t = p.cross(d) if side == "L" else d.cross(p)
    return frame(grip_point, t, d)


_MODEL = None


def model():
    global _MODEL
    if _MODEL is None:
        _MODEL = RigModel()
    return _MODEL
