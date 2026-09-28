"""Negative self-test of the character rig/skinning gates.

    blender --background --factory-startup --python blender/validators/selftest_rig.py

Builds the smoke worker up to its skinned, cleaned, joined mesh, checks that it
passes ``rig_validation.validate_character``, then injects real skinning
defects and requires each to be rejected:

* a shin patch bound to the thigh (tears at the knee)   -> DEFORM_STRETCH
* a chest vertex weighted to the left hand               -> WEIGHTS_REGION_LEAK
* a vertex with no weights                               -> WEIGHTS_MISSING
* five influences on one vertex                          -> WEIGHTS_INFLUENCES

Exit code 0 when every case behaves, 1 otherwise. Outputs go to a temporary
directory; nothing in assets/ is touched.
"""

import os
import shutil
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from mathutils import Vector  # noqa: E402

from core import config, paths, scene as scn, stages  # noqa: E402
from core.context import BuildContext  # noqa: E402
from exporters import assembly  # noqa: E402
from generators import resolve  # noqa: E402
from materials.library import MaterialLibrary  # noqa: E402
import registry  # noqa: E402
from rigging import rig_validation as rv  # noqa: E402

WORKER = "chr_worker_miner_01"


def skinned_worker(cfg):
    d = next(a for a in registry.all_assets(cfg) if a.id == WORKER)
    scn.reset_scene(cfg, d.seed)
    ctx = BuildContext(d, cfg, MaterialLibrary, None)
    ctx.begin_state(d.states[0])
    stages.stage_generate(ctx, resolve(d.generator_name))
    stages.stage_rig(ctx)
    parts = [o for o in ctx.objects if o.type == "MESH"]
    stages._clean_parts(parts, cfg["deformation"])
    _, meshes, _ = assembly.assemble(ctx, parts)
    ctx.final_meshes = meshes
    return ctx, meshes[0]


def set_weights(mesh, vids, weights):
    for vg in mesh.vertex_groups:
        vg.remove(vids)
    for bone, w in weights.items():
        vg = mesh.vertex_groups.get(bone) or mesh.vertex_groups.new(name=bone)
        vg.add(vids, w, "REPLACE")


def errors(ctx):
    return {i.code for i in rv.validate_character(ctx) if i.severity == "error"}


def main():
    cfg = config.pipeline_config()
    tmp = tempfile.mkdtemp(prefix="mm_rig_selftest_")
    paths.set_output_root(tmp)
    cases = []
    try:
        ctx, _ = skinned_worker(cfg)
        got = errors(ctx)
        cases.append(("untouched worker passes", not got, got))

        ctx, mesh = skinned_worker(cfg)
        patch = [v.index for v in mesh.data.vertices if 0.25 < v.co.z < 0.40 and v.co.x > 0.03]
        set_weights(mesh, patch, {"thigh.L": 1.0})
        got = errors(ctx)
        cases.append((f"shin patch bound to the thigh ({len(patch)} vertices)", "DEFORM_STRETCH" in got, got))

        ctx, mesh = skinned_worker(cfg)
        target = Vector((0.0, -0.12, 1.25))
        v = min(mesh.data.vertices, key=lambda v: (v.co - target).length)
        set_weights(mesh, [v.index], {"spine_03": 0.4, "hand.L": 0.6})
        got = errors(ctx)
        cases.append(("chest vertex weighted to hand.L", "WEIGHTS_REGION_LEAK" in got, got))

        ctx, mesh = skinned_worker(cfg)
        for vg in mesh.vertex_groups:
            vg.remove([10])
        got = errors(ctx)
        cases.append(("vertex without weights", "WEIGHTS_MISSING" in got, got))

        ctx, mesh = skinned_worker(cfg)
        set_weights(mesh, [20], {"spine_01": 0.2, "spine_02": 0.2, "spine_03": 0.2, "pelvis": 0.2, "neck": 0.2})
        got = errors(ctx)
        cases.append(("vertex with five influences", "WEIGHTS_INFLUENCES" in got, got))
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    failed = 0
    for name, ok, got in cases:
        failed += not ok
        print(f"{'ok  ' if ok else 'FAIL'} rig self-test: {name} -> {sorted(got)}")
    print(f"rig self-test: {len(cases) - failed}/{len(cases)} cases behaved")
    sys.stdout.flush()
    return 1 if failed else 0


if __name__ == "__main__":
    code = main()
    sys.exit(code)
