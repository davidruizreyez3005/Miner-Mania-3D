"""Repository path layout. All paths are derived from this file's location so
the pipeline works from any clean checkout regardless of the working
directory Blender was launched from."""

import os

BLENDER_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REPO_ROOT = os.path.dirname(BLENDER_DIR)

ASSETS_DIR = os.path.join(REPO_ROOT, "assets")
SOURCE_DIR = os.path.join(ASSETS_DIR, "source")
GENERATED_DIR = os.path.join(ASSETS_DIR, "generated")
MANIFEST_DIR = os.path.join(ASSETS_DIR, "manifests")
REPORT_DIR = os.path.join(ASSETS_DIR, "reports")
PREVIEW_DIR = os.path.join(REPORT_DIR, "previews")
WORK_DIR = os.path.join(REPO_ROOT, ".pipeline_work")

GENERATED_SUBDIRS = (
    "characters",
    "machinery",
    "vehicles",
    "environment",
    "resources",
    "props",
    "animations",
    "collisions",
    "lod",
)

# Files that must survive the clean stage (tracked placeholders).
KEEP_FILES = {".gitkeep", ".gdignore", "README.md"}


def generated(*parts):
    return os.path.join(GENERATED_DIR, *parts)


def rel(path):
    """Repository-relative POSIX path used in manifests and reports."""
    return os.path.relpath(path, REPO_ROOT).replace(os.sep, "/")


def ensure_dir(path):
    os.makedirs(path, exist_ok=True)
    return path


def set_output_root(root):
    """Redirect all generated outputs (used by the determinism re-build)."""
    global ASSETS_DIR, GENERATED_DIR, MANIFEST_DIR, REPORT_DIR, PREVIEW_DIR, WORK_DIR
    root = os.path.abspath(root)
    ASSETS_DIR = root
    GENERATED_DIR = os.path.join(root, "generated")
    MANIFEST_DIR = os.path.join(root, "manifests")
    REPORT_DIR = os.path.join(root, "reports")
    PREVIEW_DIR = os.path.join(REPORT_DIR, "previews")
    WORK_DIR = os.path.join(root, ".pipeline_work")
