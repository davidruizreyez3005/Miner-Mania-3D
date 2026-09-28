"""Build reports (assets/reports/build_report.json and .txt)."""

import datetime
import json
import os

import bpy

from . import paths


def write(results, cfg, profile, started, finished, extra=None):
    ok = [r for r in results if r.status == "ok"]
    failed = [r for r in results if r.status != "ok"]
    outputs = [o for r in ok for o in r.outputs]
    by_cat = {}
    for r in results:
        by_cat.setdefault(r.category, {"total": 0, "ok": 0, "failed": 0})
        by_cat[r.category]["total"] += 1
        by_cat[r.category]["ok" if r.status == "ok" else "failed"] += 1
    warnings = [dict(w, asset=r.id) for r in results for w in r.warnings]
    errors = [{"asset": r.id, "stage": r.failed_stage, "message": r.error} for r in failed]
    anim_names = set()
    for o in outputs:
        anim_names.update(o.animations)
    tri_total = sum(o.triangles for o in outputs)
    lod_tri_total = sum(sum(o.lod_triangles) for o in outputs)
    extra = dict(extra or {})
    # Build-level failures are errors too, so the status never says "passed"
    # for a run that exits non-zero.
    det = extra.get("determinism")
    if det and det.get("status") != "passed":
        why = det.get("reason") or (f"{len(det.get('mismatched', []))} GLBs differ between two builds "
                                    f"{det.get('mismatched', [])[:10]}, {len(det.get('missing', []))} "
                                    f"produced by only one build {det.get('missing', [])[:10]}")
        errors.append({"asset": None, "stage": "determinism", "message": why})
    if extra.get("not_built"):
        errors.append({"asset": None, "stage": "not_built",
                       "message": f"not built because of an earlier failure: {extra['not_built']}"})
    report = {
        "status": "passed" if results and not errors else "failed",
        "profile": profile,
        "blender_version": bpy.app.version_string,
        "pipeline_version": cfg["pipeline"]["version"],
        "build_started": datetime.datetime.fromtimestamp(started, datetime.timezone.utc).isoformat(),
        "build_finished": datetime.datetime.fromtimestamp(finished, datetime.timezone.utc).isoformat(),
        "duration_s": round(finished - started, 1),
        "asset_count": len(results),
        "successful_assets": len(ok),
        "failed_assets": len(failed),
        "output_files": {
            "models": len(outputs),
            "lods": sum(len(o.lods) for o in outputs),
            "collisions": sum(1 for o in outputs if o.collision),
        },
        "triangles_total_lod0": tri_total,
        "triangles_total_lods": lod_tri_total,
        "animation_count": len(anim_names),
        "animation_names": sorted(anim_names),
        "character_count": by_cat.get("character", {}).get("ok", 0),
        "machinery_count": by_cat.get("machinery", {}).get("ok", 0),
        "categories": by_cat,
        "validation_status": "passed" if not failed else "failed",
        "warnings": warnings,
        "errors": errors,
        "assets": [
            {"id": r.id, "category": r.category, "status": r.status, "timings_s": r.timings,
             "outputs": [{"name": o.name, "model": o.model, "triangles": o.triangles, "lod_triangles": o.lod_triangles,
                          "file_size": o.file_size, "animations": len(o.animations), "bones": o.bones,
                          "checks": o.checks} for o in r.outputs],
             "error": r.error}
            for r in results
        ],
    }
    report.update(extra)
    paths.ensure_dir(paths.REPORT_DIR)
    with open(os.path.join(paths.REPORT_DIR, "build_report.json"), "w", encoding="utf-8") as fh:
        json.dump(report, fh, indent=2)
        fh.write("\n")
    with open(os.path.join(paths.REPORT_DIR, "build_report.txt"), "w", encoding="utf-8") as fh:
        fh.write(render_text(report))
    return report


def render_text(r):
    lines = [
        "Miner Mania 3D - asset build report",
        "=" * 60,
        f"Status             : {r['status'].upper()}",
        f"Profile            : {r['profile']}",
        f"Blender            : {r['blender_version']}",
        f"Pipeline           : {r['pipeline_version']}",
        f"Started (UTC)      : {r['build_started']}",
        f"Duration           : {r['duration_s']} s",
        f"Assets             : {r['asset_count']} (ok {r['successful_assets']}, failed {r['failed_assets']})",
        f"Output GLBs        : {r['output_files']['models']} models, {r['output_files']['lods']} LODs, "
        f"{r['output_files']['collisions']} collision",
        f"Triangles (LOD0)   : {r['triangles_total_lod0']}",
        f"Triangles (LODs)   : {r['triangles_total_lods']}",
        f"Animations         : {r['animation_count']}",
        f"Characters         : {r['character_count']}",
        f"Machinery          : {r['machinery_count']}",
        f"Validation         : {r['validation_status'].upper()}",
    ]
    if r.get("determinism"):
        d = r["determinism"]
        lines.append(f"Determinism        : {d.get('status', 'n/a').upper()} ({d.get('compared', 0)} files compared)")
    lines += ["", "Categories:"]
    for cat, c in sorted(r["categories"].items()):
        lines.append(f"  {cat:<12} total {c['total']:>3}  ok {c['ok']:>3}  failed {c['failed']:>3}")
    lines += ["", f"Warnings ({len(r['warnings'])}):"]
    for w in r["warnings"][:200]:
        lines.append(f"  WARN  [{w.get('asset')}] {w.get('code')}: {w.get('message')}")
    lines += ["", f"Errors ({len(r['errors'])}):"]
    for e in r["errors"]:
        lines.append(f"  ERROR [{e['asset'] or 'build'}] stage={e['stage']}: {e['message']}")
    lines += ["", "Assets:"]
    for a in r["assets"]:
        for o in a["outputs"]:
            lines.append(f"  {a['status']:<6} {o['name']:<34} {o['triangles']:>7} tris  "
                         f"LODs {o['lod_triangles']}  {o['file_size'] / 1024:>8.0f} KiB  clips {o['animations']}")
        if not a["outputs"]:
            lines.append(f"  {a['status']:<6} {a['id']}")
    return "\n".join(lines) + "\n"
