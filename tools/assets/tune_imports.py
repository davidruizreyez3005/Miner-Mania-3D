#!/usr/bin/env python3
"""Mobile texture import settings for the generated asset library.

    python tools/assets/tune_imports.py [--check]

Every texture Godot extracted from the generated models (and the procedural
textures) is set to VRAM compression (ETC2/ASTC on phones: a fraction of the
GPU memory of lossless RGB) with mipmaps and a size cap by category -
buildings, machines and vehicles keep 1024 px, smaller things 512 px, which
is plenty at the game's camera distances. Run after the first `godot
--import` (which writes the .import files), then import again; the second
import re-processes only what changed. --check fails if a file needs tuning.
"""
import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parents[2]
GEN = ROOT / "assets" / "generated"
LARGE = {"buildings", "machinery", "vehicles", "textures"}
PARAMS = {"compress/mode": "2", "mipmaps/generate": "true", "detect_3d/compress_to": "0"}


def wanted(path: pathlib.Path) -> dict:
    folder = path.relative_to(GEN).parts[0]
    p = dict(PARAMS)
    p["process/size_limit"] = "1024" if folder in LARGE else "512"
    return p


def tune(path: pathlib.Path, check: bool) -> bool:
    text = path.read_text(encoding="utf-8")
    if 'importer="texture"' not in text:
        return False
    out = text
    for key, val in wanted(path).items():
        pat = re.compile(rf"^{re.escape(key)}=.*$", re.M)
        line = f"{key}={val}"
        if pat.search(out):
            out = pat.sub(line, out)
        else:
            out = out.rstrip("\n") + "\n" + line + "\n"
    if out == text:
        return False
    if not check:
        path.write_text(out, encoding="utf-8")
    return True


def main() -> int:
    check = "--check" in sys.argv
    files = sorted(p for p in GEN.rglob("*.import") if p.suffixes[-2:] != [".glb", ".import"])
    changed = [p for p in files if tune(p, check)]
    print(f"tune_imports: {len(files)} import files, {len(changed)} {'need tuning' if check else 'tuned'}")
    return 1 if check and changed else 0


if __name__ == "__main__":
    sys.exit(main())
