"""Minimal structured logging for headless Blender runs.

Blender's own stdout is noisy; every pipeline line is prefixed so CI logs can
be grepped (``grep -E '^(INFO|WARN|ERROR)'``).
"""

import sys
import time

_START = time.time()
_asset = None


def set_asset(asset_id):
    global _asset
    _asset = asset_id


def _emit(level, msg, stream):
    elapsed = time.time() - _START
    prefix = f"[{_asset}] " if _asset else ""
    stream.write(f"{level:<5} {elapsed:8.1f}s {prefix}{msg}\n")
    stream.flush()


def info(msg):
    _emit("INFO", msg, sys.stdout)


def warn(msg):
    _emit("WARN", msg, sys.stdout)


def error(msg):
    # Single stream keeps CI logs ordered and free of duplicates.
    _emit("ERROR", msg, sys.stdout)


class Timer:
    """Context manager recording the duration of a stage into a dict."""

    def __init__(self, sink, name):
        self.sink = sink
        self.name = name
        self.t0 = None

    def __enter__(self):
        self.t0 = time.time()
        return self

    def __exit__(self, exc_type, exc, tb):
        self.sink[self.name] = round(self.sink.get(self.name, 0.0) + time.time() - self.t0, 3)
        return False
