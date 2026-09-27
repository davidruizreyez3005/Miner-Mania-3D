#!/usr/bin/env python3
"""Standalone validation of the generated assets (no Blender required).

Blender reporting a successful export proves nothing about the files that end
up on disk or in a CI artifact. This tool re-reads every file listed in the
asset manifest and re-runs the exact post-export inspection the build ran
(``assets/manifests/validation_expectations.json``), then checks what only a
whole-collection view can see:

* every manifest file exists, is non-empty and matches its recorded sha256
* every inspected file passes (errors fail; warnings fail unless their code is
  in ``pipeline_config.json`` ``validation.allowed_warning_codes``)
* recorded triangle counts equal the counts in the files
* no stale ``.glb`` sits in ``assets/generated`` without a manifest entry
* optional: the Khronos glTF-Validator (``--khronos``, needs Node + npm ci)

``--self-test`` proves the gate is not vacuous: it corrupts real generated
files in memory (truncation, bad magic, dangling references, NaN vertices,
over-budget triangles, Blender duplicate names, missing sockets, external
images, missing/broken animation data) and fails unless every mutation is
rejected while the untouched files still pass.

Exit code 0 = everything passed, 1 = validation failures, 2 = usage/setup error.
"""

import argparse
import copy
import hashlib
import json
import os
import struct
import subprocess
import sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(REPO, "blender"))

try:
    import numpy as np  # noqa: F401  (required by the inspector)
except ImportError:  # pragma: no cover
    sys.stderr.write("validate_assets: numpy is required (pip install -r requirements.txt)\n")
    sys.exit(2)

from validators import glb_inspector as gi  # noqa: E402

GENERATED = os.path.join(REPO, "assets", "generated")
MANIFEST_DIR = os.path.join(REPO, "assets", "manifests")


def load_json(path):
    with open(path, "r", encoding="utf-8") as fh:
        return json.load(fh)


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for block in iter(lambda: fh.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def manifest_files(manifest):
    """(path, recorded) pairs; ``recorded`` holds sha256/triangles when known."""
    out = {}

    def add(path, **rec):
        if path:
            out.setdefault(path, {}).update({k: v for k, v in rec.items() if v is not None})

    for a in manifest.get("assets", []):
        add(a.get("model"), sha256=a.get("sha256"), triangles=a.get("triangles"), asset=a["id"])
        for lod in a.get("lod_models", []):
            add(lod["model"], sha256=lod.get("sha256"), triangles=lod.get("triangles"), asset=a["id"])
        add(a.get("collision_model"), asset=a["id"])
        for state in (a.get("states") or {}).values():
            add(state.get("model"), sha256=state.get("sha256"), triangles=state.get("triangles"), asset=a["id"])
            for lod in state.get("lod_models", []):
                add(lod if isinstance(lod, str) else lod.get("model"), asset=a["id"])
            add(state.get("collision_model"), asset=a["id"])
        for clip in (a.get("clip_models") or {}).values():
            add(clip, asset=a["id"])
    return out


def check_collection(manifest, expectations, allowed, full_profile):
    """Returns (file_results, collection_errors)."""
    files = manifest_files(manifest)
    exp_files = expectations.get("files", {})
    results, errors = [], []
    for path in sorted(files):
        rec = files[path]
        full = os.path.join(REPO, path)
        res = {"path": path, "asset": rec.get("asset"), "errors": [], "warnings": []}
        results.append(res)
        if not os.path.isfile(full) or os.path.getsize(full) == 0:
            res["errors"].append({"code": "FILE_MISSING", "message": "listed in the manifest but missing or empty"})
            continue
        if rec.get("sha256") and sha256(full) != rec["sha256"]:
            res["errors"].append({"code": "SHA256_MISMATCH", "message": "file differs from the manifest checksum"})
        entry = exp_files.get(path)
        if entry is None:
            res["errors"].append({"code": "NO_EXPECTATIONS", "message": "no recorded inspection expectations"})
            continue
        rep = gi.inspect(full, entry["expect"])
        res["errors"] += rep.errors
        for w in rep.warnings:
            (res["warnings"] if w["code"] in allowed else res["errors"]).append(w)
        tris = rep.stats.get("triangles")
        if rec.get("triangles") is not None and tris is not None and int(rec["triangles"]) != int(tris):
            res["errors"].append({"code": "TRIANGLE_RECORD_MISMATCH",
                                  "message": f"manifest says {rec['triangles']} triangles, file has {tris}"})
    if full_profile:
        listed = set(files)
        for root, _, names in os.walk(GENERATED):
            for n in names:
                if n.endswith(".glb"):
                    rel = os.path.relpath(os.path.join(root, n), REPO).replace(os.sep, "/")
                    if rel not in listed:
                        errors.append({"code": "STALE_FILE", "message": f"{rel} is not in the manifest"})
    for path in exp_files:
        if path not in files:
            errors.append({"code": "EXPECTATION_ORPHAN", "message": f"{path} has expectations but no manifest entry"})
    return results, errors


def run_khronos(manifest_path, report_path):
    runner = os.path.join(REPO, "tools", "gltf_validator", "validate.mjs")
    if not os.path.isdir(os.path.join(REPO, "tools", "gltf_validator", "node_modules")):
        return {"status": "error", "message": "run `npm ci` in tools/gltf_validator first"}
    cmd = ["node", runner, "--strict", "--manifest", os.path.relpath(manifest_path, REPO), "--report", report_path]
    proc = subprocess.run(cmd, cwd=REPO, capture_output=True, text=True)
    sys.stdout.write(proc.stdout[-4000:])
    if proc.returncode != 0:
        sys.stderr.write(proc.stderr[-4000:])
    return {"status": "passed" if proc.returncode == 0 else "failed", "returncode": proc.returncode}


# ------------------------------------------------------------------ self-test

def _pack(js, bin_):
    jbytes = json.dumps(js, separators=(",", ":")).encode("utf-8")
    jbytes += b" " * ((4 - len(jbytes) % 4) % 4)
    bbytes = bin_ + b"\0" * ((4 - len(bin_) % 4) % 4)
    total = 12 + 8 + len(jbytes) + (8 + len(bbytes) if bbytes else 0)
    out = struct.pack("<III", gi.GLB_MAGIC, 2, total) + struct.pack("<II", len(jbytes), gi.CHUNK_JSON) + jbytes
    if bbytes:
        out += struct.pack("<II", len(bbytes), gi.CHUNK_BIN) + bbytes
    return out


def _unpack(data):
    g = gi.GLB(data)
    return copy.deepcopy(g.json), bytearray(g.bin)


def _accessor_offset(js, acc_index):
    acc = js["accessors"][acc_index]
    bv = js["bufferViews"][acc["bufferView"]]
    return bv.get("byteOffset", 0) + acc.get("byteOffset", 0)


def _mutations_static(data, expect):
    """(name, bytes, expect, expected_codes) for a static textured model."""
    js, bin_ = _unpack(data)
    out = []
    out.append(("truncated file", data[: len(data) // 2], expect, {"GLB_CORRUPT"}))
    bad = bytearray(data)
    bad[0:4] = b"glTX"
    out.append(("bad magic", bytes(bad), expect, {"GLB_CORRUPT"}))
    j = copy.deepcopy(js)
    j["meshes"][0]["primitives"][0]["attributes"]["POSITION"] = len(j["accessors"]) + 5
    out.append(("dangling accessor reference", _pack(j, bytes(bin_)), expect, {"BAD_REFERENCE", "GLB_MALFORMED"}))
    b = bytearray(bin_)
    pos = js["meshes"][0]["primitives"][0]["attributes"]["POSITION"]
    off = _accessor_offset(js, pos)
    b[off:off + 4] = struct.pack("<f", float("nan"))
    out.append(("NaN vertex", _pack(js, bytes(b)), expect, {"NAN_OR_INF", "POSITION_BOUNDS"}))
    tight = dict(expect)
    tris = gi.inspect(gi.GLB(data), expect).stats.get("triangles", 0)
    tight["triangles"] = [0, max(1, tris - 1)]
    out.append(("over the triangle budget", data, tight, {"TRIANGLE_BUDGET"}))
    j = copy.deepcopy(js)
    mesh_nodes = [i for i, n in enumerate(j["nodes"]) if "mesh" in n]
    j["nodes"][mesh_nodes[0]]["name"] = j["nodes"][mesh_nodes[0]].get("name", "mesh") + ".001"
    out.append(("Blender duplicate-name suffix", _pack(j, bytes(bin_)), expect, {"BLENDER_DUPLICATE_NAME"}))
    req = [n for n in expect.get("required_nodes", []) if n.startswith("socket_")]
    if req:
        j = copy.deepcopy(js)
        for n in j["nodes"]:
            if n.get("name") == req[0]:
                n["name"] = "renamed_" + req[0][len("socket_"):]
        out.append(("missing socket node", _pack(j, bytes(bin_)), expect, {"MISSING_NODE"}))
    if js.get("images"):
        j = copy.deepcopy(js)
        img = j["images"][0]
        img.pop("bufferView", None)
        img.pop("mimeType", None)
        img["uri"] = "textures/base_color.png"
        out.append(("external image", _pack(j, bytes(bin_)), expect, {"EXTERNAL_IMAGE", "IMAGE_INVALID"}))
    return out


def _mutations_animated(data, expect):
    js, bin_ = _unpack(data)
    out = []
    if not js.get("animations"):
        return out
    j = copy.deepcopy(js)
    j["animations"] = j["animations"][1:]
    out.append(("missing animation clip", _pack(j, bytes(bin_)), expect, {"MISSING_ANIMATION", "EMPTY_ANIMATION"}))
    anim = js["animations"][0]
    rot = next((c for c in anim["channels"] if c["target"].get("path") == "rotation"), None)
    if rot is not None:
        sampler = anim["samplers"][rot["sampler"]]
        b = bytearray(bin_)
        off = _accessor_offset(js, sampler["output"])
        b[off:off + 16] = struct.pack("<4f", 0.9, 0.9, 0.9, 0.9)
        out.append(("non-unit rotation key", _pack(js, bytes(b)), expect, {"QUAT_NOT_UNIT", "LOOP_DISCONTINUITY"}))
        b = bytearray(bin_)
        off = _accessor_offset(js, sampler["input"])
        count = js["accessors"][sampler["input"]]["count"]
        if count > 2:
            t0, t1 = struct.unpack_from("<2f", b, off)
            struct.pack_into("<2f", b, off, t1, t0)
            out.append(("non-monotonic key times", _pack(js, bytes(b)), expect, {"NON_MONOTONIC_TIME"}))
    return out


def self_test(manifest, expectations):
    exp_files = expectations.get("files", {})
    static = animated = None
    for path, entry in sorted(exp_files.items()):
        e = entry["expect"]
        if e.get("collision") or not os.path.isfile(os.path.join(REPO, path)):
            continue
        if static is None and e.get("no_animations") and e.get("triangles"):
            static = (path, e)
        if animated is None and e.get("animations") and e.get("triangles"):
            animated = (path, e)
    if static is None:
        return {"status": "error", "message": "self-test needs at least one generated static asset"}
    cases = []
    for label, base in (("static", static), ("animated", animated)):
        if base is None:
            continue
        path, e = base
        with open(os.path.join(REPO, path), "rb") as fh:
            data = fh.read()
        clean = gi.inspect(gi.GLB(data, path), e)
        cases.append({"name": f"{label} baseline {path}", "expect_clean": True, "passed": clean.ok,
                      "errors": [x["code"] for x in clean.errors]})
        muts = _mutations_static(data, e) + (_mutations_animated(data, e) if label == "animated" else [])
        for name, blob, exp, codes in muts:
            try:
                rep = gi.inspect(gi.GLB(blob, name), exp)
                got = {x["code"] for x in rep.errors}
            except gi.GLBError as exc:  # inspect() normally converts these itself
                got = {"GLB_CORRUPT"}
                rep = None
            hit = bool(got & codes)
            cases.append({"name": f"{label}: {name}", "expected_any_of": sorted(codes), "got": sorted(got), "passed": hit})
    failed = [c for c in cases if not c["passed"]]
    return {"status": "passed" if not failed else "failed", "cases": cases, "failed": len(failed)}


# ------------------------------------------------------------------ main

def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--manifest", default=None, help="manifest path (default: asset_manifest.json, else the partial one)")
    ap.add_argument("--expectations", default=None, help="expectations sidecar (default: matches the manifest)")
    ap.add_argument("--report", default=os.path.join(REPO, "assets", "reports", "standalone_validation.json"))
    ap.add_argument("--khronos", action="store_true", help="also run the Khronos glTF-Validator (strict)")
    ap.add_argument("--self-test", action="store_true", help="prove that corrupted assets are rejected")
    args = ap.parse_args(argv)

    manifest_path = args.manifest
    if manifest_path is None:
        full = os.path.join(MANIFEST_DIR, "asset_manifest.json")
        manifest_path = full if os.path.isfile(full) else os.path.join(MANIFEST_DIR, "asset_manifest.partial.json")
    if not os.path.isfile(manifest_path):
        sys.stderr.write(f"validate_assets: manifest not found: {manifest_path}\n")
        return 2
    partial = manifest_path.endswith(".partial.json")
    exp_path = args.expectations or os.path.join(
        MANIFEST_DIR, "validation_expectations.partial.json" if partial else "validation_expectations.json")
    if not os.path.isfile(exp_path):
        sys.stderr.write(f"validate_assets: expectations not found: {exp_path}\n")
        return 2
    manifest, expectations = load_json(manifest_path), load_json(exp_path)
    cfg = load_json(os.path.join(REPO, "assets", "source", "pipeline_config.json"))
    allowed = set(cfg["validation"].get("allowed_warning_codes", []))
    full_profile = manifest.get("profile") == "full" and not partial

    results, coll_errors = check_collection(manifest, expectations, allowed, full_profile)
    bad_files = [r for r in results if r["errors"]]
    report = {
        "manifest": os.path.relpath(manifest_path, REPO),
        "profile": manifest.get("profile"),
        "files_checked": len(results),
        "files_failed": len(bad_files),
        "collection_errors": coll_errors,
        "warnings_allowed": sorted(allowed),
        "files": results,
    }
    ok = not bad_files and not coll_errors
    if args.khronos:
        report["khronos"] = run_khronos(manifest_path, os.path.join(REPO, "assets", "reports", "khronos_validation.json"))
        ok = ok and report["khronos"]["status"] == "passed"
    if args.self_test:
        report["self_test"] = self_test(manifest, expectations)
        ok = ok and report["self_test"]["status"] == "passed"
    report["status"] = "passed" if ok else "failed"
    os.makedirs(os.path.dirname(args.report), exist_ok=True)
    with open(args.report, "w", encoding="utf-8") as fh:
        json.dump(report, fh, indent=2)
        fh.write("\n")

    for r in bad_files:
        for e in r["errors"]:
            print(f"ERROR {r['path']}: {e['code']}: {e['message']}")
    for e in coll_errors:
        print(f"ERROR collection: {e['code']}: {e['message']}")
    if args.self_test:
        st = report["self_test"]
        for c in st.get("cases", []):
            print(f"{'ok  ' if c['passed'] else 'FAIL'} self-test {c['name']}" +
                  ("" if c["passed"] else f" expected {c.get('expected_any_of')} got {c.get('got') or c.get('errors')}"))
        if st.get("message"):
            print(f"self-test: {st['message']}")
    n_warn = sum(len(r["warnings"]) for r in results)
    print(f"validate_assets: {report['status']}: {len(results)} files, {len(bad_files)} failed, "
          f"{len(coll_errors)} collection errors, {n_warn} allowed warnings -> {os.path.relpath(args.report, REPO)}")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
