"""Machine-readable manifests (deterministic: no timestamps)."""

import json
import os

from . import config, paths


def _entry(result, cfg):
    d = result.defn
    outs = result.outputs
    main = outs[0]
    entry = {
        "id": d.id,
        "type": d.category,
        "model": main.model,
        "triangles": main.triangles,
        "materials": main.materials,
        "textures": main.textures,
        "texture_resolution": main.texture_resolution,
        "skeleton": main.skeleton,
        "bones": main.bones,
        "animations": list(main.animations),
        "lods": len(main.lods),
        "lod_models": [{"level": l["level"], "model": l["model"], "triangles": l["triangles"], "sha256": l.get("sha256")}
                       for l in main.lods],
        "collision": bool(main.collision),
        "collision_model": main.collision,
        "collision_shapes": main.collision_shapes,
        "scale": 1.0,
        "dimensions_m": main.dimensions,
        "bounds_min_m": main.bounds_min,
        "bounds_max_m": main.bounds_max,
        "sockets": main.sockets,
        "file_size_bytes": main.file_size,
        "sha256": main.sha256,
        "budget": d.budget,
        "seed": d.seed,
        "generator": d.generator_name,
        "tags": list(d.tags),
        "description": d.description,
        "uv": main.uv,
        "validated": all(o.validated for o in outs),
    }
    if main.clip_files:
        entry["clip_models"] = dict(main.clip_files)
    if len(d.states) > 1 or d.states[0] != "default":
        entry["states"] = {
            o.state: {"model": o.model, "triangles": o.triangles, "lod_models": [l["model"] for l in o.lods],
                      "collision_model": o.collision, "sha256": o.sha256, "dimensions_m": o.dimensions}
            for o in outs
        }
    md = result.metadata or {}
    public = {k: v for k, v in md.items() if k in ("clips", "interaction", "sockets_info", "wheels", "speeds",
                                                  "character", "resource", "attachments", "capsule", "bones")}
    if public:
        entry["metadata"] = public
    if d.category == "character":
        entry["capsule"] = cfg["collision"]["character_capsule"]
    return entry


def write(results, cfg, profile, partial=False):
    ok = [r for r in results if r.status == "ok"]
    ok.sort(key=lambda r: (r.category, r.id))
    manifest = {
        "schema_version": 1,
        "pipeline_version": cfg["pipeline"]["version"],
        "profile": profile,
        "toolchain": {
            "blender": ".".join(str(x) for x in cfg["toolchain"]["blender_version"]),
            "gltf_exporter": ".".join(str(x) for x in cfg["toolchain"]["gltf_exporter_version"]),
            "godot": cfg["toolchain"]["godot_version"],
        },
        "coordinate_system": {
            "unit": cfg["world"]["unit"], "gltf_up": cfg["world"]["gltf_up"], "gltf_front": cfg["world"]["gltf_front"],
            "blender_up": cfg["world"]["blender_up"], "blender_front": cfg["world"]["blender_front"],
        },
        "asset_count": len(ok),
        "assets": [_entry(r, cfg) for r in ok],
    }
    paths.ensure_dir(paths.MANIFEST_DIR)
    name = "asset_manifest.partial.json" if partial else "asset_manifest.json"
    out = os.path.join(paths.MANIFEST_DIR, name)
    with open(out, "w", encoding="utf-8") as fh:
        json.dump(manifest, fh, indent=2, sort_keys=False)
        fh.write("\n")
    _write_animation_manifest(ok, partial)
    _write_expectations(ok, partial)
    return out, manifest


def _write_expectations(results, partial):
    """Per-file inspector expectations, so tools/validate_assets.py can re-run
    the exact post-export checks on the files as they sit on disk."""
    files = {}
    for r in results:
        for o in r.outputs:
            for path, exp in o.expectations.items():
                files[path] = {"asset": r.id, "state": o.state, "expect": exp}
    doc = {"schema_version": 1, "files": dict(sorted(files.items()))}
    name = "validation_expectations.partial.json" if partial else "validation_expectations.json"
    with open(os.path.join(paths.MANIFEST_DIR, name), "w", encoding="utf-8") as fh:
        json.dump(doc, fh, indent=1, sort_keys=True)
        fh.write("\n")


def _write_animation_manifest(results, partial):
    spec = config.animation_spec()
    clips = {}
    source = None
    for r in results:
        if r.category in ("character", "animation") and r.outputs and r.outputs[0].animation_details:
            source = r
            if r.category == "animation":
                break
    if source is None:
        return
    details = source.outputs[0].animation_details
    for name, c in spec["clips"].items():
        det = details.get(name, {})
        clips[name] = {
            "loop": c["loop"],
            "duration_s": det.get("duration", c["duration"]),
            "frames": det.get("frames"),
            "fps": spec["fps"],
            "feet": c["feet"],
            "root_motion": c["root_motion"],
            "tool": c.get("tool"),
            "grip": c.get("grip"),
            "interaction": c.get("interaction"),
            "events_s": c.get("events", {}),
            "optional": bool(c.get("optional")),
            "measured": {k: v for k, v in det.items() if k in ("foot_slide_m", "grip_error_m", "contact_frames")},
        }
        if source.outputs[0].clip_files.get(name):
            clips[name]["model"] = source.outputs[0].clip_files[name]
    doc = {
        "skeleton": spec["skeleton"],
        "library_model": source.outputs[0].model,
        "grips": spec["grips"],
        "interaction_points": spec["interaction_points"],
        "clips": clips,
    }
    name = "animations.partial.json" if partial else "animations.json"
    with open(os.path.join(paths.MANIFEST_DIR, name), "w", encoding="utf-8") as fh:
        json.dump(doc, fh, indent=2)
        fh.write("\n")
