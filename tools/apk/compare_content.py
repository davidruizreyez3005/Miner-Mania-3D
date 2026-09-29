#!/usr/bin/env python3
"""Prove two APKs carry the same game: every entry outside the native
libraries (lib/) and the signature (META-INF/) must exist in both with the
same CRC-32 and size. Used to show the x86_64 emulator-test build differs
from the shipped arm64-v8a APK only in the engine's native library.

    python tools/apk/compare_content.py shipped.apk test.apk [--report out.json]
"""
from __future__ import annotations

import argparse
import difflib
import json
import struct
import sys
import zipfile

IGNORED = ("lib/", "META-INF/")
CLASS_CACHE = "assets/.godot/global_script_class_cache.cfg"
UID_CACHE = "assets/.godot/uid_cache.bin"


def entries(path: str) -> dict:
    with zipfile.ZipFile(path) as z:
        return {i.filename: (i.CRC, i.file_size) for i in z.infolist()
                if not i.filename.startswith(IGNORED) and not i.is_dir()}


def uid_entries(data: bytes) -> set:
    """Godot's uid_cache.bin: u32 count, then (u64 uid, u32 length, path)."""
    out, off = set(), 4
    for _ in range(struct.unpack_from("<I", data, 0)[0]):
        uid, n = struct.unpack_from("<QI", data, off)
        off += 12
        out.add((uid, data[off:off + n].decode("utf-8", "replace")))
        off += n
    return out


def explain(a_path: str, b_path: str, name: str) -> list:
    """Human-readable detail for a differing editor cache file."""
    with zipfile.ZipFile(a_path) as za, zipfile.ZipFile(b_path) as zb:
        da, db = za.read(name), zb.read(name)
    if name == CLASS_CACHE:
        diff = difflib.unified_diff(da.decode("utf-8", "replace").splitlines(),
                                    db.decode("utf-8", "replace").splitlines(), "a", "b", lineterm="", n=1)
        return list(diff)[:60]
    if name == UID_CACHE:
        try:
            ea, eb = uid_entries(da), uid_entries(db)
        except (struct.error, IndexError):
            return ["(unreadable uid cache)"]
        return [f"- {p} ({u})" for u, p in sorted(ea - eb, key=lambda e: e[1])][:30] + \
               [f"+ {p} ({u})" for u, p in sorted(eb - ea, key=lambda e: e[1])][:30] + \
               ([f"same {len(ea)} entries in a different order"] if ea == eb else [])
    return []


def libs(path: str) -> list:
    with zipfile.ZipFile(path) as z:
        return sorted(n for n in z.namelist() if n.startswith("lib/"))


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("a")
    ap.add_argument("b")
    ap.add_argument("--report", default="")
    args = ap.parse_args()
    a, b = entries(args.a), entries(args.b)
    only_a = sorted(set(a) - set(b))
    only_b = sorted(set(b) - set(a))
    changed = sorted(k for k in set(a) & set(b) if a[k] != b[k])
    report = {
        "a": args.a, "b": args.b, "compared_entries": len(set(a) & set(b)),
        "compared_bytes": sum(a[k][1] for k in set(a) & set(b)),
        "only_in_a": only_a, "only_in_b": only_b, "different": changed,
        "native_libs_a": libs(args.a), "native_libs_b": libs(args.b),
    }
    report["identical_content"] = not (only_a or only_b or changed)
    if args.report:
        with open(args.report, "w", encoding="utf-8") as f:
            json.dump(report, f, indent=2)
    print(f"{report['compared_entries']} entries ({report['compared_bytes'] / 1e6:.1f} MB) compared; "
          f"native libraries: {', '.join(report['native_libs_a'])} vs {', '.join(report['native_libs_b'])}")
    for label, items in (("only in " + args.a, only_a), ("only in " + args.b, only_b), ("different", changed)):
        for k in items[:20]:
            print(f"  {label}: {k}")
    for name in (CLASS_CACHE, UID_CACHE):
        if name in changed:
            print(f"  {name}:")
            for line in explain(args.a, args.b, name):
                print("    " + line)
    print("identical game content" if report["identical_content"] else "CONTENT DIFFERS")
    return 0 if report["identical_content"] else 1


if __name__ == "__main__":
    sys.exit(main())
