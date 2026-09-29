#!/usr/bin/env python3
"""Add an x86_64 twin of the Android export preset, for the emulator test.

The shipped APK is arm64-v8a only. CI emulators are x86_64: they can run it
through ARM translation, but that translation does not cover every
instruction of the engine binary. This writes a second preset that is an
exact copy of preset "Android" (same filters, options, package, version and
signing) except that it builds for x86_64 and is not runnable, so the test
build carries the same game content natively (tools/apk/compare_content.py
proves it). CI only - the file is not committed with this preset.

    python tools/apk/add_emulator_preset.py [--name NAME] [--extra-include PATTERN] [export_presets.cfg]

--extra-include adds a pattern to the copy's include filter (e.g. an
override.cfg for an experiment build); the default copy adds nothing.
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

SOURCE = "Android"
NAME = "Android x86_64 (emulator test)"


def sections(text: str) -> list:
    """[(header, body)] in file order; header '' for anything before the first section."""
    out, header, body = [], "", []
    for line in text.splitlines(keepends=True):
        if re.match(r"^\[[^\]]+\]\s*$", line):
            out.append((header, "".join(body)))
            header, body = line.strip(), []
        else:
            body.append(line)
    out.append((header, "".join(body)))
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("path", nargs="?", default="export_presets.cfg")
    ap.add_argument("--name", default=NAME)
    ap.add_argument("--extra-include", default="")
    args = ap.parse_args()
    name = args.name
    path = Path(args.path)
    secs = sections(path.read_text(encoding="utf-8"))
    presets: dict = {}
    for header, body in secs:
        m = re.match(r"^\[preset\.(\d+)(\.options)?\]$", header)
        if m:
            presets.setdefault(int(m.group(1)), {})["options" if m.group(2) else "main"] = body
    src = next((i for i, p in presets.items() if f'\nname="{SOURCE}"\n' in "\n" + p.get("main", "")), None)
    if src is None:
        print(f"error: no preset named {SOURCE}", file=sys.stderr)
        return 1
    # Drop an earlier copy (idempotent), then append the new one.
    old = next((i for i, p in presets.items() if f'\nname="{name}"\n' in "\n" + p.get("main", "")), None)
    keep = [(h, b) for h, b in secs if not (old is not None and h in (f"[preset.{old}]", f"[preset.{old}.options]"))]
    idx = max(i for i in presets if i != old) + 1
    main = presets[src]["main"]
    main = re.sub(r'(?m)^name=".*"$', f'name="{name}"', main)
    main = re.sub(r"(?m)^runnable=true$", "runnable=false", main)
    main = re.sub(r'(?m)^export_path=".*"$', 'export_path="build/MinerMania3D-x86_64-emulator.apk"', main)
    if args.extra_include:
        main, n = re.subn(r'(?m)^include_filter="(.*)"$',
                          lambda m: f'include_filter="{m.group(1)}{", " if m.group(1) else ""}{args.extra_include}"', main)
        if n != 1:
            print("error: include_filter not found in the preset", file=sys.stderr)
            return 1
    opts = presets[src]["options"]
    for abi, on in (("armeabi-v7a", False), ("arm64-v8a", False), ("x86", False), ("x86_64", True)):
        opts, n = re.subn(rf"(?m)^architectures/{re.escape(abi)}=(true|false)$",
                          f"architectures/{abi}={'true' if on else 'false'}", opts)
        if n != 1:
            print(f"error: architectures/{abi} not found in the preset options", file=sys.stderr)
            return 1
    text = "".join((h + "\n" if h else "") + b for h, b in keep)
    if not text.endswith("\n\n"):
        text = text.rstrip("\n") + "\n\n"
    text += f"[preset.{idx}]\n{main.rstrip()}\n\n[preset.{idx}.options]\n{opts.rstrip()}\n"
    path.write_text(text, encoding="utf-8")
    print(f'added preset.{idx} "{name}" (x86_64) from preset.{src} "{SOURCE}"')
    return 0


if __name__ == "__main__":
    sys.exit(main())
