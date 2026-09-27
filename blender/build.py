"""Primary build entry point.

    blender --background --factory-startup --python blender/build.py -- [--profile smoke|full]

Stages: clean -> generate -> rig -> animate -> optimize -> collision -> LOD ->
export -> validate -> manifest -> report. Exits non-zero on any failure
(Blender itself returns 0 for uncaught Python exceptions, so this wrapper
converts every failure into an explicit exit code).
"""

import os
import sys
import traceback

BLENDER_DIR = os.path.dirname(os.path.abspath(__file__))
if BLENDER_DIR not in sys.path:
    sys.path.insert(0, BLENDER_DIR)


def _argv():
    return sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []


def main():
    try:
        from core import cli
        code = cli.run(_argv())
    except SystemExit as exc:
        code = exc.code if isinstance(exc.code, int) else 1
    except BaseException as exc:  # noqa: BLE001 - convert everything into a failing exit code
        traceback.print_exc()
        sys.stderr.write(f"ERROR: build aborted: {type(exc).__name__}: {exc}\n")
        code = 1
    sys.stdout.flush()
    sys.stderr.flush()
    return code


if __name__ == "__main__":
    sys.exit(main())
