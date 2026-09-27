"""Rig, skin-weight and deformation validation.

Characters:
* hierarchy, names, parents, rest transforms and bone frames match the
  shared ``humanoid_worker_v1`` spec; armature at the origin, unit scale,
  rest pose == bind pose;
* mesh binding (Armature modifier, parenting) and vertex groups map to
  deforming bones only;
* weights: normalized, <= 4 influences, no tiny weights, no unweighted
  vertices, no influence from bones far from the vertex (region leaks),
  left/right symmetry;
* scripted pose tests (shoulder raise, elbow, wrist, hip, knee, ankle,
  spine twist) measuring joint collapse, edge stretch and flipped faces.

Machines: root bone, rigid (single-bone, weight 1.0) skinning.
"""

import math
import re

import bpy
import numpy as np
from mathutils import Euler, Matrix, Quaternion, Vector
from mathutils.kdtree import KDTree

from core.errors import ValidationIssue

from . import human_rig

BONE_NAME_RE = re.compile(r"^[a-z][a-z0-9_]*(\.[LR])?$")

POSE_TESTS = [
    # name, {bone: (axis, degrees)}, joints [(parent, child)]
    ("shoulder_raise", {"upper_arm.L": ("Z", 80), "upper_arm.R": ("Z", -80)},
     [("clavicle.L", "upper_arm.L"), ("clavicle.R", "upper_arm.R")]),
    ("elbow_bend", {"forearm.L": ("X", 120), "forearm.R": ("X", 120)},
     [("upper_arm.L", "forearm.L"), ("upper_arm.R", "forearm.R")]),
    ("wrist_flex", {"hand.L": ("X", 60), "hand.R": ("X", 60)}, [("forearm.L", "hand.L"), ("forearm.R", "hand.R")]),
    ("hip_flexion", {"thigh.L": ("X", 90), "thigh.R": ("X", 90)}, [("pelvis", "thigh.L"), ("pelvis", "thigh.R")]),
    ("knee_bend", {"calf.L": ("X", -120), "calf.R": ("X", -120)}, [("thigh.L", "calf.L"), ("thigh.R", "calf.R")]),
    ("ankle_flex", {"foot.L": ("X", 30), "foot.R": ("X", 30)}, [("calf.L", "foot.L"), ("calf.R", "foot.R")]),
    ("spine_twist", {"spine_01": ("Y", 14), "spine_02": ("Y", 14), "spine_03": ("Y", 12)},
     [("spine_01", "spine_02"), ("spine_02", "spine_03")]),
]


def _reach(bone):
    """Max distance (m) from a bone segment at which it may influence a vertex.
    Generous enough for joint blend falloff on chunky bodies/garments, tight
    enough to catch cross-region leaks (e.g. hand weights on a thigh)."""
    b = bone.split(".")[0]
    if b in ("pelvis", "spine_01", "spine_02", "spine_03", "neck", "head", "clavicle", "root"):
        return 0.34
    if b in ("upper_arm", "forearm", "thigh", "calf"):
        return 0.24
    if b == "hand":
        return 0.1
    if b in ("foot", "toe"):
        return 0.14
    if b.startswith("eye"):
        return 0.025
    return 0.05  # fingers


def _seg_dist(p, a, b):
    ab = b - a
    t = max(0.0, min(1.0, (p - a).dot(ab) / max(ab.length_squared, 1e-12)))
    return (p - (a + ab * t)).length


def _weights(obj):
    names = {vg.index: vg.name for vg in obj.vertex_groups}
    out = []
    for v in obj.data.vertices:
        out.append({names[g.group]: g.weight for g in v.groups if g.weight > 0.0})
    return out


def validate(ctx):
    if ctx.character is not None:
        return validate_character(ctx)
    return validate_mechanical(ctx)


def validate_mechanical(ctx):
    issues = []
    arm = ctx.armature
    bones = arm.data.bones
    if "root" not in bones:
        issues.append(ValidationIssue("error", "RIG_NO_ROOT", "mechanical rig lacks a root bone"))
    for b in bones:
        if b.parent is None and b.name != "root":
            issues.append(ValidationIssue("error", "RIG_ORPHAN_BONE", f"bone {b.name} has no parent"))
        if not BONE_NAME_RE.match(b.name):
            issues.append(ValidationIssue("error", "RIG_BONE_NAME", f"bone name {b.name!r} violates convention"))
    for o in ctx.final_meshes:
        mods = [m for m in o.modifiers if m.type == "ARMATURE"]
        if not mods or mods[0].object is not arm:
            issues.append(ValidationIssue("error", "RIG_NOT_BOUND", f"{o.name} is not bound to {arm.name}"))
            continue
        for vi, w in enumerate(_weights(o)):
            if len(w) != 1 or abs(sum(w.values()) - 1.0) > 1e-4:
                issues.append(ValidationIssue("error", "RIG_NOT_RIGID", f"{o.name}: vertex {vi} weights {w} (expected rigid)"))
                break
    return issues


def validate_character(ctx):
    cfg = ctx.cfg["deformation"]
    issues = []
    arm = ctx.armature
    sk = human_rig.skeleton()
    bones = arm.data.bones
    have = [b.name for b in bones]
    want = sk.bone_names
    missing = [b for b in want if b not in have]
    extra = [b for b in have if b not in want]
    if missing:
        issues.append(ValidationIssue("error", "RIG_MISSING_BONES", f"missing bones {missing}"))
    if extra:
        issues.append(ValidationIssue("error", "RIG_EXTRA_BONES", f"unexpected bones {extra}"))
    if arm.matrix_world != Matrix.Identity(4):
        issues.append(ValidationIssue("error", "RIG_TRANSFORM", "armature object must be at the origin with unit scale"))
    for spec in sk.specs:
        if spec.name not in bones:
            continue
        b = bones[spec.name]
        if not BONE_NAME_RE.match(b.name):
            issues.append(ValidationIssue("error", "RIG_BONE_NAME", f"bone name {b.name!r} violates convention"))
        pname = b.parent.name if b.parent else None
        if pname != spec.parent:
            issues.append(ValidationIssue("error", "RIG_HIERARCHY", f"{b.name} parent {pname} != {spec.parent}"))
        if (b.head_local - Vector(spec.head)).length > 1e-4 or (b.tail_local - Vector(spec.tail)).length > 1e-4:
            issues.append(ValidationIssue("error", "RIG_REST_POSITION", f"{b.name} rest head/tail differ from spec"))
        if spec.z_axis is not None:
            z = b.matrix_local.to_3x3().col[2]
            want_z = Vector(spec.z_axis)
            y = (Vector(spec.tail) - Vector(spec.head)).normalized()
            want_z = (want_z - y * want_z.dot(y)).normalized()
            if z.dot(want_z) < 0.999:
                issues.append(ValidationIssue("error", "RIG_BONE_ROLL", f"{b.name} bone frame (roll) differs from spec"))
        if b.use_deform != spec.deform:
            issues.append(ValidationIssue("error", "RIG_DEFORM_FLAG", f"{b.name} deform flag {b.use_deform} != {spec.deform}"))
        if spec.name.endswith(".L"):
            mirror = bones.get(human_rig.Skeleton.mirror_name(spec.name))
            if mirror is not None:
                h = b.head_local
                mh = mirror.head_local
                if (Vector((-h.x, h.y, h.z)) - mh).length > 1e-4:
                    issues.append(ValidationIssue("error", "RIG_ASYMMETRIC", f"{b.name}/{mirror.name} not mirrored"))
    for pb in arm.pose.bones:
        if pb.matrix_basis != Matrix.Identity(4):
            issues.append(ValidationIssue("error", "RIG_NOT_AT_REST", f"{pb.name} is posed in the rest state"))
            break
    deform = set(sk.deform_bones)
    mesh = ctx.final_meshes[0] if ctx.final_meshes else None
    if mesh is None:
        return issues + [ValidationIssue("error", "RIG_NO_MESH", "no skinned mesh to validate")]
    mods = [m for m in mesh.modifiers if m.type == "ARMATURE"]
    if not mods or mods[0].object is not arm or mesh.parent is not arm:
        issues.append(ValidationIssue("error", "RIG_NOT_BOUND", f"{mesh.name} is not bound/parented to {arm.name}"))
        return issues
    bad_groups = [vg.name for vg in mesh.vertex_groups if vg.name not in deform]
    if bad_groups:
        issues.append(ValidationIssue("error", "RIG_BAD_GROUPS", f"vertex groups for non-deform bones: {bad_groups}"))
    weights = _weights(mesh)
    co = [v.co.copy() for v in mesh.data.vertices]
    stats = {"vertices": len(weights), "max_influences": 0, "unweighted": 0, "not_normalized": 0, "tiny": 0,
             "region_leaks": 0}
    leak_examples = []
    for vi, w in enumerate(weights):
        if not w:
            stats["unweighted"] += 1
            continue
        stats["max_influences"] = max(stats["max_influences"], len(w))
        if abs(sum(w.values()) - 1.0) > cfg["weight_sum_tolerance"]:
            stats["not_normalized"] += 1
        if min(w.values()) < cfg["min_weight"] - 1e-6:
            stats["tiny"] += 1
        for bname, wt in w.items():
            if wt < 0.05 or bname not in bones:
                continue
            b = bones[bname]
            if _seg_dist(co[vi], b.head_local, b.tail_local) > _reach(bname):
                stats["region_leaks"] += 1
                if len(leak_examples) < 5:
                    leak_examples.append(f"v{vi}->{bname}")
    if stats["unweighted"]:
        issues.append(ValidationIssue("error", "WEIGHTS_MISSING", f"{stats['unweighted']} unweighted vertices"))
    if stats["max_influences"] > cfg["max_influences"]:
        issues.append(ValidationIssue("error", "WEIGHTS_INFLUENCES", f"{stats['max_influences']} influences > {cfg['max_influences']}"))
    if stats["not_normalized"]:
        issues.append(ValidationIssue("error", "WEIGHTS_NOT_NORMALIZED", f"{stats['not_normalized']} vertices do not sum to 1"))
    if stats["tiny"]:
        issues.append(ValidationIssue("error", "WEIGHTS_TINY", f"{stats['tiny']} vertices carry weights < {cfg['min_weight']}"))
    if stats["region_leaks"]:
        issues.append(ValidationIssue("error", "WEIGHTS_REGION_LEAK",
                                      f"{stats['region_leaks']} weights from unrelated distant bones, e.g. {leak_examples}"))
    sym = _symmetry(co, weights, cfg["symmetry_tolerance"])
    stats["symmetry_pairs"] = sym["pairs"]
    stats["symmetry_mismatch"] = sym["mismatch"]
    if sym["pairs"] and sym["mismatch"] / sym["pairs"] > 0.01:
        issues.append(ValidationIssue("error", "WEIGHTS_ASYMMETRIC",
                                      f"{sym['mismatch']}/{sym['pairs']} mirrored vertex pairs have asymmetric weights"))
    deform_stats, deform_issues = deformation_tests(ctx, mesh, arm, weights)
    issues += deform_issues
    ctx.metadata["weights"] = stats
    ctx.metadata["deformation"] = deform_stats
    return issues


def _symmetry(co, weights, tol):
    kd = KDTree(len(co))
    for i, p in enumerate(co):
        kd.insert(p, i)
    kd.balance()
    pairs = mism = 0
    for i, p in enumerate(co):
        if p.x < 0.02:
            continue
        hit = kd.find(Vector((-p.x, p.y, p.z)))
        if hit[2] is None or hit[2] > 0.0008:
            continue
        j = hit[1]
        pairs += 1
        wa = weights[i]
        wb = {human_rig.Skeleton.mirror_name(k): v for k, v in weights[j].items()}
        keys = set(wa) | set(wb)
        if max(abs(wa.get(k, 0.0) - wb.get(k, 0.0)) for k in keys) > max(tol, 0.05):
            mism += 1
    return {"pairs": pairs, "mismatch": mism}


def _posed_coords(mesh):
    bpy.context.view_layer.update()
    deps = bpy.context.evaluated_depsgraph_get()
    ev = mesh.evaluated_get(deps)
    me = ev.to_mesh()
    n = len(me.vertices)
    arr = np.empty(n * 3, dtype=np.float64)
    me.vertices.foreach_get("co", arr)
    ev.to_mesh_clear()
    return arr.reshape(n, 3)


def deformation_tests(ctx, mesh, arm, weights):
    cfg = ctx.cfg["deformation"]
    issues = []
    rest = _posed_coords(mesh)
    me = mesh.data
    edges = np.array([e.vertices[:] for e in me.edges], dtype=np.int64)
    tris = []
    me.calc_loop_triangles()
    for t in me.loop_triangles:
        tris.append(t.vertices[:])
    tris = np.array(tris, dtype=np.int64)
    bone_w = {}
    for vi, w in enumerate(weights):
        for b, wt in w.items():
            bone_w.setdefault(b, np.zeros(len(weights)))[vi] = wt
    # Rigid regions: vertices dominated (>= 0.98) by a single bone. Edges/faces
    # there must move rigidly; creases (blend regions) may fold under LBS.
    dom_w = np.array([max(w.values()) if w else 0.0 for w in weights])
    bone_ids = {b: i for i, b in enumerate(sorted(bone_w))}
    dom_b = np.array([bone_ids[max(w, key=w.get)] if w else -1 for w in weights])
    rigid_v = dom_w >= 0.98
    min_len = 0.002
    results = {}
    for name, rot, joints in POSE_TESTS:
        for pb in arm.pose.bones:
            pb.rotation_mode = "QUATERNION"
            pb.rotation_quaternion = Quaternion()
        for b, (axis, deg) in rot.items():
            e = Euler((0, 0, 0))
            setattr(e, axis.lower(), math.radians(deg))
            arm.pose.bones[b].rotation_quaternion = e.to_quaternion()
        posed = _posed_coords(mesh)
        tested = np.zeros(len(weights))
        for b in rot:
            if b in bone_w:
                tested = np.maximum(tested, bone_w[b])
        for p, c in joints:
            for b in (p, c):
                if b in bone_w:
                    tested = np.maximum(tested, bone_w[b])
        mask_v = tested > 0.05
        emask = mask_v[edges[:, 0]] & mask_v[edges[:, 1]]
        e = edges[emask]
        lr = np.linalg.norm(rest[e[:, 0]] - rest[e[:, 1]], axis=1)
        lp = np.linalg.norm(posed[e[:, 0]] - posed[e[:, 1]], axis=1)
        ok = lr > min_len  # sub-2mm slivers from subdivision are numerical noise
        ratio = lp[ok] / lr[ok]
        stretch = float(ratio.max()) if ratio.size else 1.0
        squash = float(ratio.min()) if ratio.size else 1.0
        ee_ok = e[ok]
        rigid_e = rigid_v[ee_ok[:, 0]] & rigid_v[ee_ok[:, 1]] & (dom_b[ee_ok[:, 0]] == dom_b[ee_ok[:, 1]])
        rigid_ratio = ratio[rigid_e]
        rigid_squash = float(np.abs(rigid_ratio - 1.0).max()) if rigid_ratio.size else 0.0
        tmask = mask_v[tris[:, 0]] & mask_v[tris[:, 1]] & mask_v[tris[:, 2]]
        tt = tris[tmask]
        flips = 0
        rigid_flips = 0
        rigid_count = 0
        if len(tt):
            nr = np.cross(rest[tt[:, 1]] - rest[tt[:, 0]], rest[tt[:, 2]] - rest[tt[:, 0]])
            npz = np.cross(posed[tt[:, 1]] - posed[tt[:, 0]], posed[tt[:, 2]] - posed[tt[:, 0]])
            # Expected normal: the rest normal transformed by the linear blend of
            # every influencing bone's pose rotation (unposed bones = identity).
            expected = np.zeros_like(nr)
            wsum = np.zeros(len(tt))
            for b, wv in bone_w.items():
                fw = wv[tt].mean(axis=1)
                if not np.any(fw > 0):
                    continue
                pbm = arm.pose.bones[b].matrix.to_3x3()
                rbm = arm.data.bones[b].matrix_local.to_3x3()
                r = np.array(pbm @ rbm.inverted())
                expected += fw[:, None] * (nr @ r.T)
                wsum += fw
            valid = (np.linalg.norm(nr, axis=1) > 1e-12) & (wsum > 0)
            dots = np.einsum("ij,ij->i", expected, npz)
            flipped = (dots < 0.0) & valid
            flips = int(flipped.sum())
            rigid_t = rigid_v[tt[:, 0]] & rigid_v[tt[:, 1]] & rigid_v[tt[:, 2]]
            rigid_flips = int((flipped & rigid_t).sum())
            rigid_count = int(rigid_t.sum())
        flip_ratio = flips / max(1, len(tt))
        thick = []
        for p, c in joints:
            if p not in bone_w or c not in bone_w:
                continue
            ring = (bone_w[p] >= 0.25) & (bone_w[c] >= 0.25)
            if ring.sum() < 4:
                continue
            j_rest = np.array(arm.data.bones[c].head_local)
            j_pose = np.array(arm.pose.bones[c].head)
            d_rest = np.linalg.norm(rest[ring] - j_rest, axis=1).mean()
            d_pose = np.linalg.norm(posed[ring] - j_pose, axis=1).mean()
            thick.append(d_pose / max(d_rest, 1e-9))
        thickness = float(min(thick)) if thick else 1.0
        worst = {}
        if ratio.size:
            ee = e[ok]
            k_hi = int(np.argmax(ratio))
            k_lo = int(np.argmin(ratio))
            worst = {"stretch_at": [round(float(x), 3) for x in rest[ee[k_hi, 0]]],
                     "squash_at": [round(float(x), 3) for x in rest[ee[k_lo, 0]]]}
        rigid_flip_ratio = rigid_flips / max(1, rigid_count)
        results[name] = {"worst": worst, "max_stretch": round(stretch, 3), "min_edge_ratio": round(squash, 3),
                         "rigid_edge_deviation": round(rigid_squash, 4),
                         "flipped_ratio": round(flip_ratio, 5), "rigid_flipped_ratio": round(rigid_flip_ratio, 5),
                         "joint_thickness": round(thickness, 3), "tested_vertices": int(mask_v.sum())}
        if stretch > cfg["max_edge_stretch"]:
            issues.append(ValidationIssue("error", "DEFORM_STRETCH", f"{name}: edge stretch {stretch:.2f} > {cfg['max_edge_stretch']}"))
        if squash < cfg["min_edge_ratio"]:
            issues.append(ValidationIssue("error", "DEFORM_SQUASH", f"{name}: edge collapse {squash:.2f} < {cfg['min_edge_ratio']}"))
        if rigid_squash > cfg["max_rigid_edge_deviation"]:
            issues.append(ValidationIssue("error", "DEFORM_RIGID_REGION",
                                          f"{name}: rigidly weighted region deforms (edge length change {rigid_squash:.2f})"))
        if flip_ratio > cfg["max_flipped_face_ratio"]:
            issues.append(ValidationIssue("error", "DEFORM_FLIPS", f"{name}: {flip_ratio * 100:.2f}% faces flipped"))
        if rigid_flip_ratio > cfg["max_rigid_flipped_ratio"]:
            issues.append(ValidationIssue("error", "DEFORM_RIGID_FLIPS",
                                          f"{name}: {rigid_flip_ratio * 100:.2f}% faces flipped outside joint creases"))
        if thickness < cfg["min_joint_thickness_ratio"]:
            issues.append(ValidationIssue("error", "DEFORM_COLLAPSE", f"{name}: joint collapses to {thickness:.2f} of rest thickness"))
    for pb in arm.pose.bones:
        pb.rotation_quaternion = Quaternion()
        pb.location = Vector()
    bpy.context.view_layer.update()
    return results, issues
