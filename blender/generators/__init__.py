"""Generator lookup: ``"machinery.crusher"`` -> ``generators.machinery.crusher.build``."""

import importlib

from core.errors import ConfigError


def resolve(name):
    if not name or "." not in name:
        raise ConfigError(f"invalid generator name {name!r} (expected 'category.module')")
    module_name = f"generators.{name}"
    try:
        mod = importlib.import_module(module_name)
    except ModuleNotFoundError as exc:
        raise ConfigError(f"generator module {module_name} not found: {exc}") from exc
    fn = getattr(mod, "build", None)
    if not callable(fn):
        raise ConfigError(f"generator module {module_name} has no build(ctx) function")
    return fn
