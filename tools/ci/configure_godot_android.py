#!/usr/bin/env python3
"""Point the Godot editor at the Android SDK, the JDK and a debug keystore.

    python tools/ci/configure_godot_android.py --sdk <android_sdk> --java <java_home> \
        [--debug-keystore <path>] [--version 4.7]

Edits (or creates) the editor settings file Godot reads in headless export
(~/.config/godot/editor_settings-<version>.tres). Only paths are written:
keystore passwords for release builds come from environment variables
(GODOT_ANDROID_KEYSTORE_RELEASE_*) at export time and never touch disk here.
"""
import argparse
import os
import re
import sys


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--sdk", required=True)
    ap.add_argument("--java", required=True)
    ap.add_argument("--debug-keystore", default="")
    ap.add_argument("--version", default="4.7")
    a = ap.parse_args()
    cfg_home = os.environ.get("XDG_CONFIG_HOME") or os.path.join(os.path.expanduser("~"), ".config")
    path = os.path.join(cfg_home, "godot", f"editor_settings-{a.version}.tres")
    os.makedirs(os.path.dirname(path), exist_ok=True)
    values = {
        "export/android/android_sdk_path": a.sdk,
        "export/android/java_sdk_path": a.java,
    }
    if a.debug_keystore:
        values["export/android/debug_keystore"] = a.debug_keystore
        values["export/android/debug_keystore_user"] = "androiddebugkey"
        values["export/android/debug_keystore_pass"] = "android"
    text = ""
    if os.path.exists(path):
        with open(path, encoding="utf-8") as f:
            text = f.read()
    if "[resource]" not in text:
        text = '[gd_resource type="EditorSettings" format=3]\n\n[resource]\n'
    for key, val in values.items():
        line = f'{key} = "{val}"'
        pat = re.compile(rf"^{re.escape(key)} = .*$", re.M)
        if pat.search(text):
            text = pat.sub(line.replace("\\", "\\\\"), text)
        else:
            text = text.rstrip("\n") + "\n" + line + "\n"
    with open(path, "w", encoding="utf-8") as f:
        f.write(text)
    print(path)
    return 0


if __name__ == "__main__":
    sys.exit(main())
