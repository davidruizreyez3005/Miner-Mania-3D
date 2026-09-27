"""Loading and sanity-checking of the source specifications in assets/source."""

import json
import os

from . import paths
from .errors import ConfigError

_CACHE = {}


def _load_json(name):
    path = os.path.join(paths.SOURCE_DIR, name)
    if not os.path.isfile(path):
        raise ConfigError(f"missing source specification: {paths.rel(path)}")
    try:
        with open(path, "r", encoding="utf-8") as fh:
            return json.load(fh)
    except json.JSONDecodeError as exc:
        raise ConfigError(f"{paths.rel(path)} is not valid JSON: {exc}") from exc


def _require(d, keys, where):
    for k in keys:
        if k not in d:
            raise ConfigError(f"{where}: missing required key '{k}'")


def pipeline_config():
    if "pipeline" not in _CACHE:
        cfg = _load_json("pipeline_config.json")
        _require(cfg, ("pipeline", "toolchain", "world", "categories", "budgets", "textures", "uv", "lod",
                       "collision", "deformation", "animation", "export", "validation"), "pipeline_config.json")
        for name, budget in cfg["budgets"].items():
            _require(budget, ("triangles", "texture", "file_size_mb", "lods"), f"budget '{name}'")
            lo, hi = budget["triangles"]
            if not (0 < lo < hi):
                raise ConfigError(f"budget '{name}' has an invalid triangle range {budget['triangles']}")
            tex = budget["texture"]
            if tex & (tex - 1) or tex > cfg["textures"]["max_resolution"]:
                raise ConfigError(f"budget '{name}' texture size {tex} must be a power of two <= max_resolution")
        for name, cat in cfg["categories"].items():
            _require(cat, ("prefix", "output_dir", "dimensions_m"), f"category '{name}'")
            if cat["output_dir"] not in paths.GENERATED_SUBDIRS:
                raise ConfigError(f"category '{name}' output_dir '{cat['output_dir']}' is not a generated subdir")
        _CACHE["pipeline"] = cfg
    return _CACHE["pipeline"]


def palette():
    if "palette" not in _CACHE:
        raw = _load_json("palette.json")
        flat = {}
        for group, colors in raw.items():
            if group.startswith("_"):
                continue
            for key, hexval in colors.items():
                if key in flat:
                    raise ConfigError(f"palette color '{key}' defined twice")
                flat[key] = hexval
        _CACHE["palette"] = flat
    return _CACHE["palette"]


def animation_spec():
    if "anim" not in _CACHE:
        spec = _load_json("animation_clips.json")
        _require(spec, ("skeleton", "fps", "grips", "clips", "interaction_points"), "animation_clips.json")
        for name, clip in spec["clips"].items():
            _require(clip, ("loop", "duration", "feet", "root_motion"), f"clip '{name}'")
            if clip.get("grip") and clip["grip"] not in spec["grips"]:
                raise ConfigError(f"clip '{name}' references unknown grip '{clip['grip']}'")
        _CACHE["anim"] = spec
    return _CACHE["anim"]


def required_clip_names():
    return [n for n, c in animation_spec()["clips"].items() if not c.get("optional")]


def all_clip_names():
    return list(animation_spec()["clips"].keys())


def hex_to_linear(hexval):
    """sRGB hex -> linear RGB tuple (Blender material colors are linear)."""
    hexval = hexval.lstrip("#")
    if len(hexval) != 6:
        raise ConfigError(f"invalid color '{hexval}'")
    out = []
    for i in range(3):
        c = int(hexval[2 * i:2 * i + 2], 16) / 255.0
        out.append(c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4)
    return tuple(out)


def color(key):
    pal = palette()
    if key not in pal:
        raise ConfigError(f"unknown palette color '{key}'")
    return hex_to_linear(pal[key])
