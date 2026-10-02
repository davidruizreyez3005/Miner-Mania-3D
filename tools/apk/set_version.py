#!/usr/bin/env python3
"""Stamp the Android version into export_presets.cfg for a build.

Android installs an APK over an existing install (keeping its data) only
when the package and the signing key match and the version code does not go
down. The version code is therefore taken from the commit being built: the
minutes since 2020-01-01 UTC of its committer date, so every later commit -
on any branch, debug or release build - gets a higher code. The version name
is the game's version (project.godot application/config/version) plus the
build: "1.0.0+3558885".

    python tools/apk/set_version.py [--commit HEAD] [--name 1.2.0] [--presets export_presets.cfg] [--github-env]

Prints "<code> <name>"; with --github-env also appends APK_VERSION_CODE and
APK_VERSION_NAME to $GITHUB_ENV. Every preset in the file gets the version.
"""
from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
EPOCH = 1577836800          # 2020-01-01T00:00:00Z
MAX_CODE = 2100000000       # Google Play's limit for versionCode


def version_code(commit_unix: int) -> int:
    code = (commit_unix - EPOCH) // 60
    if code < 2 or code > MAX_CODE:
        raise ValueError(f"commit time {commit_unix} gives version code {code} outside 2..{MAX_CODE}")
    return code


def game_version(project: Path) -> str:
    m = re.search(r'^config/version="([^"]*)"', project.read_text(encoding="utf-8"), re.M)
    return m.group(1) if m else "1.0.0"


def stamp(text: str, code: int, name: str) -> str:
    text, n_code = re.subn(r"^version/code=.*$", f"version/code={code}", text, flags=re.M)
    text, n_name = re.subn(r"^version/name=.*$", f'version/name="{name}"', text, flags=re.M)
    if n_code == 0 or n_name == 0:
        raise ValueError("export presets without version/code or version/name")
    return text


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--commit", default="HEAD")
    ap.add_argument("--presets", default=str(ROOT / "export_presets.cfg"))
    ap.add_argument("--github-env", action="store_true")
    ap.add_argument("--name", default="", help="version name (a release's x.y.z); the code still comes from the commit")
    a = ap.parse_args()
    ct = subprocess.run(["git", "-C", str(ROOT), "log", "-1", "--format=%ct", a.commit],
                        capture_output=True, text=True, check=True).stdout.strip()
    code = version_code(int(ct))
    name = a.name or f"{game_version(ROOT / 'project.godot')}+{code}"
    p = Path(a.presets)
    p.write_text(stamp(p.read_text(encoding="utf-8"), code, name), encoding="utf-8")
    print(f"{code} {name}")
    if a.github_env and os.environ.get("GITHUB_ENV"):
        with open(os.environ["GITHUB_ENV"], "a", encoding="utf-8") as f:
            f.write(f"APK_VERSION_CODE={code}\nAPK_VERSION_NAME={name}\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
