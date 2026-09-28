#!/usr/bin/env python3
"""Markdown summary of an asset build for the GitHub Actions job summary.

Reads the reports the pipeline wrote (assets/reports/*.json); any report that
is missing is listed as not run. Standard library only. Exit code 1 when a
report that exists says it failed, so the summary step can double as a gate.
"""

import json
import os
import sys

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
REPORTS = os.path.join(REPO, "assets", "reports")


def load(name):
    path = os.path.join(REPORTS, name)
    if not os.path.isfile(path):
        return None
    with open(path, "r", encoding="utf-8") as fh:
        return json.load(fh)


def main():
    out = []
    failed = False
    build = load("build_report.json")
    if build is None:
        out.append("## Asset build\n\nNo build report was written (the build did not reach the report stage).")
        failed = True
    else:
        failed |= build.get("status") != "passed"
        out.append(f"## Asset build ({build.get('profile')}): **{build.get('status', '?').upper()}**\n")
        out.append(f"Blender {build.get('blender_version')} - {build.get('successful_assets')}/{build.get('asset_count')} assets ok"
                   f" - {build.get('triangles_total_lod0')} LOD0 triangles - {build.get('animation_count')} clips"
                   f" - {build.get('duration_s')} s\n")
        out.append("| category | total | ok | failed |\n|---|---:|---:|---:|")
        for cat, c in sorted((build.get("categories") or {}).items()):
            out.append(f"| {cat} | {c.get('total')} | {c.get('ok')} | {c.get('failed')} |")
        errors = build.get("errors") or []
        if errors:
            out.append("\n### Errors\n")
            out += [f"- `{e.get('asset') or 'build'}` ({e.get('stage')}): {e.get('message')}" for e in errors[:50]]
        warnings = build.get("warnings") or []
        if warnings:
            counts = {}
            for w in warnings:
                counts[w.get("code")] = counts.get(w.get("code"), 0) + 1
            out.append("\n### Allowed warnings\n")
            out += [f"- {code}: {n}" for code, n in sorted(counts.items())]
    for title, name, key in (("Standalone GLB validation", "standalone_validation.json", "files_failed"),
                             ("Khronos glTF-Validator", "khronos_validation.json", None),
                             ("Godot import validation", "godot_validation.json", "files_failed")):
        rep = load(name)
        if rep is None:
            out.append(f"\n## {title}\n\nnot run")
            continue
        status = rep.get("status") or ("passed" if not rep.get("errors") and not rep.get("unaccepted_warnings") else "failed")
        failed |= status != "passed"
        files = rep.get("files")
        detail = f"{rep.get('files_checked', len(files) if isinstance(files, list) else '?')} files"
        if key:
            detail += f", {rep.get(key)} failed"
        out.append(f"\n## {title}: **{status.upper()}**\n\n{detail}")
        st = rep.get("self_test")
        if st:
            n = len(st.get("cases", []))
            out.append(f"\nNegative self-test: {st.get('status')} ({n - st.get('failed', 0)}/{n} cases)")
    text = "\n".join(out) + "\n"
    sys.stdout.write(text)
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
