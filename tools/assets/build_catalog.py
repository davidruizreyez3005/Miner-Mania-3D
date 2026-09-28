#!/usr/bin/env python3
"""Build the game's runtime asset catalog from the pipeline manifests.

    python tools/assets/build_catalog.py [--manifest assets/manifests/asset_manifest.json]
                                         [--out assets/generated/catalog.json] [--check]

assets/manifests is pipeline output that Godot ignores (and never exports),
so the game reads this trimmed catalog instead. Everything is converted to
Godot space (Blender +Z up / -Y front -> Godot +Y up / +Z front):
positions (x, y, z) -> (x, z, -y); quaternions (w, x, y, z) -> (x, z, -y, w);
bounds and dimensions accordingly. Output is deterministic (sorted keys, no
timestamps). --check verifies every referenced file exists.
"""

import argparse
import json
import os
import sys

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def res(path):
    return "res://" + path if path else ""


def g_pos(p):
    return [round(p[0], 4), round(p[2], 4), round(-p[1], 4)]


def g_quat(wxyz):
    w, x, y, z = wxyz
    return [round(x, 6), round(z, 6), round(-y, 6), round(w, 6)]


def g_bounds(bmin, bmax):
    lo = [bmin[0], bmin[2], -bmax[1]]
    hi = [bmax[0], bmax[2], -bmin[1]]
    return [round(v, 4) for v in lo], [round(v, 4) for v in hi]


def entry(a, humanoid_loops):
    lo, hi = g_bounds(a["bounds_min_m"], a["bounds_max_m"])
    d = a["dimensions_m"]
    sockets = {}
    for s in a.get("socket_transforms", []):
        sockets[s["name"]] = {"pos": [round(v, 4) for v in s["godot_location_m"]],
                              "rot": g_quat(s["blender_rotation_quat_wxyz"]), "bone": s.get("bone") or ""}
    meta = a.get("metadata", {})
    clips = {}
    for c in meta.get("clips", []):
        clips[c["name"]] = {"loop": bool(c.get("loop", False)), "duration": float(c.get("duration", 0.0))}
    if a["type"] in ("character", "animation"):
        for name, loop in humanoid_loops.items():
            clips.setdefault(name, {"loop": loop, "duration": 0.0})
    out = {
        "id": a["id"], "type": a["type"], "model": res(a["model"]), "triangles": a["triangles"],
        "lods": [{"level": l["level"], "model": res(l["model"]), "triangles": l["triangles"]} for l in a.get("lod_models", [])],
        "collision": res(a.get("collision_model") or ""),
        "dims": [round(d[0], 4), round(d[2], 4), round(d[1], 4)],
        "bounds_min": lo, "bounds_max": hi,
        "sockets": sockets, "clips": clips, "animations": list(a.get("animations", [])),
        "tags": list(a.get("tags", [])), "budget": a.get("budget", ""),
    }
    keep = {k: meta[k] for k in ("resource", "speeds", "wheels", "interaction", "character", "capsule") if k in meta}
    if keep:
        out["metadata"] = keep
    if "states" in a:
        out["states"] = {}
        for st, sd in a["states"].items():
            out["states"][st] = {"model": res(sd["model"]), "lods": [res(m) for m in sd.get("lod_models", [])],
                                 "collision": res(sd.get("collision_model") or ""), "triangles": sd.get("triangles", 0)}
    if a.get("clip_models"):
        out["clip_models"] = {k: res(v) for k, v in sorted(a["clip_models"].items())}
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--manifest", default=os.path.join(REPO, "assets/manifests/asset_manifest.json"))
    ap.add_argument("--animations", default=os.path.join(REPO, "assets/manifests/animations.json"))
    ap.add_argument("--out", default=os.path.join(REPO, "assets/generated/catalog.json"))
    ap.add_argument("--check", action="store_true")
    args = ap.parse_args()
    with open(args.manifest, encoding="utf-8") as fh:
        manifest = json.load(fh)
    humanoid = {}
    anim_doc = {}
    if os.path.exists(args.animations):
        with open(args.animations, encoding="utf-8") as fh:
            anim_doc = json.load(fh)
        humanoid = {k: bool(v.get("loop", False)) for k, v in anim_doc.get("clips", {}).items()}
    assets = {a["id"]: entry(a, humanoid) for a in manifest["assets"]}
    catalog = {
        "schema": 1,
        "source": "assets/manifests/asset_manifest.json",
        "pipeline_version": manifest.get("pipeline_version", ""),
        "profile": manifest.get("profile", ""),
        "asset_count": len(assets),
        "humanoid": {"skeleton": anim_doc.get("skeleton", ""), "library_model": res(anim_doc.get("library_model", "")),
                     "clips": {k: {"loop": bool(v.get("loop")), "duration": float(v.get("duration_s") or 0.0),
                                   "events": v.get("events_s", {}), "tool": v.get("tool") or "",
                                   "speed_mps": float((v.get("root_motion") or {}).get("speed_mps", 0.0))}
                               for k, v in sorted(anim_doc.get("clips", {}).items())},
                     "interaction_points": anim_doc.get("interaction_points", {})},
        "assets": dict(sorted(assets.items())),
    }
    missing = []
    if args.check:
        for a in assets.values():
            files = [a["model"], a["collision"]] + [l["model"] for l in a["lods"]]
            for st in a.get("states", {}).values():
                files += [st["model"], st["collision"]] + st["lods"]
            for f in files:
                if f and not os.path.exists(os.path.join(REPO, f[len("res://"):])):
                    missing.append(f)
    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    with open(args.out, "w", encoding="utf-8") as fh:
        json.dump(catalog, fh, indent=1, sort_keys=True)
        fh.write("\n")
    print(f"catalog: {len(assets)} assets -> {os.path.relpath(args.out, REPO)}")
    if missing:
        print(f"error: {len(missing)} referenced files missing, e.g. {missing[:5]}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
