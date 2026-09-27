"""Build orchestration: clean -> per-asset stages -> manifest -> report -> gate."""

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time

import bpy

from . import config, log, paths
from .errors import ConfigError, ToolchainError


def parse_args(argv):
    p = argparse.ArgumentParser(prog="blender --background --python blender/build.py --",
                                description="Miner Mania 3D headless asset pipeline")
    p.add_argument("--profile", choices=("smoke", "full"), default="full")
    p.add_argument("--only", default="", help="comma separated asset ids (partial build)")
    p.add_argument("--category", default="", help="comma separated categories (partial build)")
    p.add_argument("--keep-going", action="store_true", help="continue after a failed asset (still exits non-zero)")
    p.add_argument("--no-clean", action="store_true", help="skip the clean stage (partial builds only)")
    p.add_argument("--verify-determinism", action="store_true",
                   help="rebuild the selection in a second Blender process and require identical GLBs")
    p.add_argument("--output-root", default="", help="write outputs under this directory instead of assets/")
    p.add_argument("--previews", action="store_true", help="render review thumbnails into assets/reports/previews")
    p.add_argument("--list", action="store_true", help="list registered assets and exit")
    return p.parse_args(argv)


def verify_toolchain(cfg):
    want = tuple(cfg["toolchain"]["blender_version"])
    have = tuple(bpy.app.version)
    if have != want:
        raise ToolchainError(f"Blender {'.'.join(map(str, want))} is required, running {bpy.app.version_string}")
    import io_scene_gltf2
    exp_want = tuple(cfg["toolchain"]["gltf_exporter_version"])
    exp_have = tuple(io_scene_gltf2.bl_info["version"])
    if exp_have != exp_want:
        raise ToolchainError(f"glTF exporter {exp_want} required, found {exp_have}")
    if not bpy.app.background:
        raise ToolchainError("the pipeline must run headless: blender --background --python blender/build.py")
    log.info(f"toolchain OK: Blender {bpy.app.version_string}, glTF exporter {'.'.join(map(str, exp_have))}")


def clean(selection, full):
    """Remove stale outputs so nothing from a previous run can leak into this one."""
    if full:
        for sub in paths.GENERATED_SUBDIRS:
            d = paths.generated(sub)
            paths.ensure_dir(d)
            for name in os.listdir(d):
                if name in paths.KEEP_FILES:
                    continue
                p = os.path.join(d, name)
                shutil.rmtree(p) if os.path.isdir(p) else os.remove(p)
        for d in (paths.MANIFEST_DIR, paths.REPORT_DIR):
            paths.ensure_dir(d)
            for name in os.listdir(d):
                if name in paths.KEEP_FILES or name == "schema":
                    continue
                p = os.path.join(d, name)
                shutil.rmtree(p) if os.path.isdir(p) else os.remove(p)
        if os.path.isdir(paths.WORK_DIR):
            shutil.rmtree(paths.WORK_DIR)
    else:
        from .stages import remove_outputs
        for a in selection:
            for s in a.states:
                remove_outputs(a.output_name(s))
            wd = os.path.join(paths.WORK_DIR, a.id)
            if os.path.isdir(wd):
                shutil.rmtree(wd)
    for sub in paths.GENERATED_SUBDIRS:
        paths.ensure_dir(paths.generated(sub))
    paths.ensure_dir(paths.MANIFEST_DIR)
    paths.ensure_dir(paths.REPORT_DIR)
    log.info("clean: stale outputs removed" + (" (full)" if full else f" ({len(selection)} assets)"))


def _hash_tree(root):
    out = {}
    for sub in paths.GENERATED_SUBDIRS:
        d = os.path.join(root, sub)
        if not os.path.isdir(d):
            continue
        for name in sorted(os.listdir(d)):
            if name.endswith(".glb"):
                with open(os.path.join(d, name), "rb") as fh:
                    out[f"{sub}/{name}"] = hashlib.sha256(fh.read()).hexdigest()
    return out


def verify_determinism(args, selection):
    tmp = tempfile.mkdtemp(prefix="mm_determinism_")
    try:
        cmd = [bpy.app.binary_path, "--background", "--factory-startup", "--python-exit-code", "1",
               "--python", os.path.join(paths.BLENDER_DIR, "build.py"), "--",
               "--profile", args.profile, "--output-root", tmp, "--only", ",".join(a.id for a in selection)]
        log.info(f"determinism: rebuilding {len(selection)} assets in a fresh Blender process")
        proc = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
        if proc.returncode != 0:
            sys.stdout.write(proc.stdout[-8000:])
            return {"status": "failed", "reason": f"rebuild exited with {proc.returncode}", "compared": 0}
        a = _hash_tree(paths.GENERATED_DIR)
        b = _hash_tree(os.path.join(tmp, "generated"))
        mismatched = sorted(k for k in a if b.get(k) != a[k])
        missing = sorted(set(a) ^ set(b))
        status = "passed" if not mismatched and not missing and a else "failed"
        for k in mismatched:
            log.error(f"determinism: {k} differs between builds")
        for k in missing:
            log.error(f"determinism: {k} only produced by one build")
        return {"status": status, "compared": len(a), "mismatched": mismatched, "missing": missing}
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def run(argv):
    started = time.time()
    args = parse_args(argv)
    if args.output_root:
        paths.set_output_root(args.output_root)
    cfg = config.pipeline_config()
    config.palette()
    config.animation_spec()
    from registry import all_assets, select
    assets = all_assets(cfg)
    if args.list:
        for a in assets:
            print(f"{a.category:<12} {a.id:<36} smoke={a.smoke} budget={a.budget} states={list(a.states)}")
        return 0
    verify_toolchain(cfg)
    ids = [s for s in args.only.split(",") if s]
    cats = [s for s in args.category.split(",") if s]
    selection = select(assets, ids=ids, categories=cats, profile=args.profile)
    if not selection:
        raise ConfigError("asset selection is empty")
    partial = bool(ids or cats)
    if partial and not args.no_clean:
        clean(selection, full=False)
    elif not partial:
        if args.no_clean:
            raise ConfigError("--no-clean is only allowed for partial builds")
        clean(selection, full=True)
    log.info(f"building {len(selection)} assets (profile={args.profile}{', partial' if partial else ''})")
    from .stages import build_asset
    results = []
    for defn in selection:
        res = build_asset(defn, cfg, args)
        results.append(res)
        if res.status != "ok" and not args.keep_going:
            log.error("stopping after first failure (use --keep-going to collect all failures)")
            break
    ok = [r for r in results if r.status == "ok"]
    # No silent omissions: every selected definition must have produced every output file.
    built = {r.id for r in ok}
    for defn in selection:
        if defn.id not in built:
            continue
        res = next(r for r in results if r.id == defn.id)
        if len(res.outputs) != len(defn.states):
            res.status = "failed"
            res.error = f"expected {len(defn.states)} outputs, got {len(res.outputs)}"
        for o in res.outputs:
            for p in [o.model] + [l["model"] for l in o.lods] + ([o.collision] if o.collision else []):
                full = os.path.join(paths.REPO_ROOT, p)
                if not os.path.isfile(full) or os.path.getsize(full) == 0:
                    res.status = "failed"
                    res.error = f"output missing or empty: {p}"
    if args.previews and ok:
        from . import previews
        previews.render_all([r for r in results if r.status == "ok"], cfg)
    from . import manifest, report
    manifest_path, man = manifest.write(results, cfg, args.profile, partial=partial)
    extra = {}
    all_ok = len(results) == len(selection) and all(r.status == "ok" for r in results)
    if args.verify_determinism and all_ok:
        extra["determinism"] = verify_determinism(args, selection)
        if extra["determinism"]["status"] != "passed":
            all_ok = False
    rep = report.write(results, cfg, args.profile, started, time.time(), extra)
    if len(results) < len(selection):
        skipped = [d.id for d in selection if d.id not in {r.id for r in results}]
        log.error(f"not built because of an earlier failure: {skipped}")
    log.info(f"manifest: {paths.rel(manifest_path)} ({man['asset_count']} assets)")
    log.info(f"report: {rep['successful_assets']}/{rep['asset_count']} assets ok, "
             f"{rep['triangles_total_lod0']} LOD0 triangles, {rep['animation_count']} animation clips")
    if not all_ok:
        log.error("BUILD FAILED")
        return 1
    log.info("BUILD PASSED")
    return 0
