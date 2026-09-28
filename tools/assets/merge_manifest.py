#!/usr/bin/env python3
"""Merge a partial asset build into the full manifests (local development).

    python tools/assets/merge_manifest.py

`blender/build.py --only ... --no-clean` writes asset_manifest.partial.json
and validation_expectations.partial.json for just the rebuilt assets. This
folds them into asset_manifest.json / validation_expectations.json (entries
replaced by id / path, sorted as the pipeline sorts them) so the runtime
catalog and the standalone validator see the whole library. CI never needs
this: it always runs full builds.
"""

import json
import os
import sys

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
MAN = os.path.join(REPO, "assets", "manifests")


def load(name):
    with open(os.path.join(MAN, name), encoding="utf-8") as fh:
        return json.load(fh)


def main():
    part_path = os.path.join(MAN, "asset_manifest.partial.json")
    if not os.path.exists(part_path):
        print("no partial manifest to merge", file=sys.stderr)
        return 1
    full = load("asset_manifest.json")
    part = load("asset_manifest.partial.json")
    by_id = {a["id"]: a for a in full["assets"]}
    for a in part["assets"]:
        by_id[a["id"]] = a
    full["assets"] = sorted(by_id.values(), key=lambda a: (a["type"], a["id"]))
    full["asset_count"] = len(full["assets"])
    with open(os.path.join(MAN, "asset_manifest.json"), "w", encoding="utf-8") as fh:
        json.dump(full, fh, indent=2)
        fh.write("\n")
    exp = load("validation_expectations.json")
    pexp = load("validation_expectations.partial.json")
    exp["files"].update(pexp["files"])
    exp["files"] = dict(sorted(exp["files"].items()))
    with open(os.path.join(MAN, "validation_expectations.json"), "w", encoding="utf-8") as fh:
        json.dump(exp, fh, indent=1, sort_keys=True)
        fh.write("\n")
    print(f"merged {len(part['assets'])} assets -> {full['asset_count']} in asset_manifest.json")
    return 0


if __name__ == "__main__":
    sys.exit(main())
