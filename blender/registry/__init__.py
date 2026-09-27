"""Asset registry. Every category module exposes ``ASSETS = [...]``; adding a
new asset is a one-line definition in one of those modules."""

import importlib

from core.definitions import ANIM_ID_PATTERN, ID_PATTERN, STATE_PATTERN
from core.errors import ConfigError

CATEGORY_MODULES = ("tools", "characters", "machinery", "vehicles", "buildings", "environment", "resources", "props")


def all_assets(cfg):
    assets = []
    for mod_name in CATEGORY_MODULES:
        mod = importlib.import_module(f"registry.{mod_name}")
        assets.extend(getattr(mod, "ASSETS", []))
    validate(assets, cfg)
    return assets


def validate(assets, cfg):
    seen = {}
    for a in assets:
        if a.id in seen:
            raise ConfigError(f"duplicate asset id '{a.id}'")
        seen[a.id] = a
        pattern = ANIM_ID_PATTERN if a.category == "animation" else ID_PATTERN
        if not pattern.match(a.id):
            raise ConfigError(f"asset id '{a.id}' violates the naming convention")
        prefix = cfg["categories"][a.category]["prefix"]
        if not a.id.startswith(prefix):
            raise ConfigError(f"asset id '{a.id}' must start with '{prefix}' for category {a.category}")
        if a.budget not in cfg["budgets"]:
            raise ConfigError(f"asset '{a.id}' uses unknown budget '{a.budget}'")
        if not a.generator_name:
            raise ConfigError(f"asset '{a.id}' has no generator")
        if a.collision not in ("convex", "none"):
            raise ConfigError(f"asset '{a.id}' collision mode must be 'convex' or 'none'")
        for s in a.states:
            if not STATE_PATTERN.match(s):
                raise ConfigError(f"asset '{a.id}' has invalid state name '{s}'")
        if a.texture_size is not None and (a.texture_size & (a.texture_size - 1)):
            raise ConfigError(f"asset '{a.id}' texture_size must be a power of two")
        if not isinstance(a.seed, int) or a.seed <= 0:
            raise ConfigError(f"asset '{a.id}' needs an explicit positive integer seed")
    # Worker tools must reference registered tool assets.
    for a in assets:
        for key in ("tool", "off_hand_tool"):
            ref = getattr(a, key, None)
            if ref and ref not in seen:
                raise ConfigError(f"{a.id}.{key} references unknown asset '{ref}'")
    return True


def smoke_set(assets):
    smoke = [a for a in assets if a.smoke]
    cats = {a.category for a in smoke}
    required = {"character", "machinery", "vehicle", "resource"}
    missing = required - cats
    if missing or not (cats & {"environment", "prop"}):
        raise ConfigError(f"smoke set must cover character, machinery, vehicle, resource and an environment prop; "
                          f"missing {sorted(missing)}")
    return smoke


def select(assets, ids=None, categories=None, profile="full"):
    chosen = smoke_set(assets) if profile == "smoke" else list(assets)
    if categories:
        chosen = [a for a in chosen if a.category in categories]
    if ids:
        want = set(ids)
        unknown = want - {a.id for a in assets}
        if unknown:
            raise ConfigError(f"unknown asset ids: {sorted(unknown)}")
        chosen = [a for a in assets if a.id in want]
    return chosen
