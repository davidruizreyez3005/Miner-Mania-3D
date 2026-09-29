#!/usr/bin/env python3
"""Keep models the game never shows out of the APK.

    python tools/assets/export_filter.py [--check] [--list]

The runtime asset set is everything the content data references (resources,
facilities, tooling, worker roles, cosmetics, region vegetation, world
modules - the same rules as ContentDB.all_asset_ids) plus the ids named in
game code. Every other generated asset (test mannequin, spare tools, ...)
is added to the Android preset's exclude_filter in export_presets.cfg.
--check fails when the preset is out of date (CI); --list prints the sets.
"""
import json
import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parents[2]
# Godot's export filters only know * and ?, so unused LOD models and the
# per-clip animation files are listed one by one (from the catalog). Crews
# use the level-2 character LODs with the shared clip library.
BASE_EXCLUDES = ["tests/*", "tools/*", "blender/*", "docs/*", "godot/*", "assets/source/*",
                 "assets/generated/collisions/*",
                 "assets/generated/audio/audio_manifest.json", "assets/generated/textures/textures.json", "build/*", "*.md"]
CREW_LOD = 2
ID_RE = re.compile(r'"((?:bld|mach|veh|env|prop|res|tool|chr)_[a-z0-9_]+_\d{2})"')


def load(name):
    return json.loads((ROOT / "data" / name).read_text(encoding="utf-8"))


def referenced() -> set:
    ids = set()
    for r in load("resources.json")["resources"]:
        ids.add(r.get("node_asset", ""))
    fac = load("facilities.json")
    for f in fac["facilities"]:
        ids.add(f.get("asset", ""))
    for t in fac.get("depth_equipment", {}).get("tools", {}).get("tiers", []):
        ids.add(t.get("tool_asset", ""))
        ids.add(t.get("machine_asset", ""))
    for role in load("workers.json")["roles"]:
        ids.update(role.get("variants", []))
    for c in load("cosmetics.json")["cosmetics"]:
        ids.add(c.get("asset", ""))
    for reg in load("regions.json")["regions"]:
        ids.update(reg.get("look", {}).get("vegetation", []))
    for m in json.loads((ROOT / "data" / "world" / "modules.json").read_text(encoding="utf-8"))["modules"]:
        ids.add(m.get("asset", ""))
    for src in (ROOT / "game").rglob("*.gd"):
        ids.update(ID_RE.findall(src.read_text(encoding="utf-8")))
    ids.discard("")
    return ids


def main() -> int:
    catalog = json.loads((ROOT / "assets" / "generated" / "catalog.json").read_text(encoding="utf-8"))["assets"]
    used = referenced()
    missing = sorted(i for i in used if i not in catalog)
    unused = sorted(i for i in catalog if i not in used and catalog[i].get("type") != "animation")
    patterns = list(BASE_EXCLUDES)
    for aid in unused:
        model = catalog[aid]["model"].replace("res://", "")
        patterns.append(f"{pathlib.PurePosixPath(model).parent}/{aid}*")
    for aid in sorted(catalog):
        a = catalog[aid]
        lods = [(int(l.get("level", 0)), l["model"]) for l in a.get("lods", [])]
        for st in a.get("states", {}).values():
            lods += [(0, m) for m in st.get("lods", [])]
        for level, model in lods:
            if a.get("type") == "character" and level == CREW_LOD and aid not in unused:
                continue
            m = pathlib.PurePosixPath(model.replace("res://", ""))
            patterns.append(f"{m.parent}/{m.stem}*")
        for clip_model in sorted(a.get("clip_models", {}).values()):
            m = pathlib.PurePosixPath(clip_model.replace("res://", ""))
            patterns.append(f"{m.parent}/{m.stem}.*")
    line = 'exclude_filter="' + ", ".join(patterns) + '"'
    if "--list" in sys.argv:
        print("used:", " ".join(sorted(used)))
        print("unused:", " ".join(unused))
    if missing:
        print("error: referenced assets missing from the catalog: " + ", ".join(missing))
        return 1
    preset = ROOT / "export_presets.cfg"
    text = preset.read_text(encoding="utf-8")
    new = re.sub(r"^exclude_filter=.*$", line, text, count=1, flags=re.M)
    if "--check" in sys.argv:
        if new != text:
            print("export_presets.cfg exclude_filter is out of date - run tools/assets/export_filter.py")
            return 1
        print(f"export filter up to date ({len(used)} assets shipped, {len(unused)} excluded)")
        return 0
    preset.write_text(new, encoding="utf-8")
    print(f"export filter: {len(used)} assets shipped, {len(unused)} excluded: {', '.join(unused)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
