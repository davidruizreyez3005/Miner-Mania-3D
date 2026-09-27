"""Bind worker meshes to the shared humanoid skeleton."""

import numpy as np

from core.errors import PipelineError

from . import armature_utils, human_rig


def clean_weights(obj, max_influences=4, min_weight=0.01, allowed=None):
    """Keep the strongest ``max_influences`` weights >= ``min_weight`` and
    renormalise to exactly 1.0; every vertex must end up weighted."""
    names = {vg.index: vg.name for vg in obj.vertex_groups}
    if allowed is not None:
        bad = sorted(n for n in names.values() if n not in allowed)
        if bad:
            raise PipelineError(f"{obj.name}: vertex groups for non-deform/unknown bones: {bad}")
    me = obj.data
    per_vertex = []
    for v in me.vertices:
        ws = sorted(((g.weight, g.group) for g in v.groups if g.weight > 0.0), reverse=True)
        ws = [(w, gi) for w, gi in ws[:max_influences] if w >= min_weight] or ws[:1]
        if not ws:
            raise PipelineError(f"{obj.name}: vertex {v.index} has no skin weights")
        tot = sum(w for w, _ in ws)
        per_vertex.append([(gi, w / tot) for w, gi in ws])
    # Rewrite groups.
    for vg in obj.vertex_groups:
        vg.remove(list(range(len(me.vertices))))
    for vi, ws in enumerate(per_vertex):
        for gi, w in ws:
            obj.vertex_groups[gi].add([vi], w, "REPLACE")


def finalize(ctx):
    sk = human_rig.skeleton()
    # Every humanoid shares the armature (root node) name, so Godot's imported
    # track paths are identical across workers, the mannequin and the
    # anim_worker_* libraries: one AnimationLibrary drives them all.
    arm = armature_utils.create_armature(human_rig.NAME, sk.specs)
    ctx.armature = arm
    allowed = set(sk.deform_bones)
    for o in ctx.objects:
        if o.type != "MESH" or o.get("mm_attach_bone"):
            continue
        if not o.vertex_groups:
            raise PipelineError(f"{o.name}: skinned part has no vertex groups")
        clean_weights(o, ctx.cfg["deformation"]["max_influences"], ctx.cfg["deformation"]["min_weight"], allowed)
        armature_utils.bind(o, arm)
    ctx.metadata["skeleton"] = sk.describe()
