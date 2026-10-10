"""Update the release_version folder with runtime-necessary files.

Copies every runtime file and directory listed below into a freshly
regenerated release_version/, mirroring the current source tree
(satisfactory_adapter.py and the rest of the Phase-3 planner modules,
the data/ catalog, and the save_parser Node helper plus package-lock).
"""

from __future__ import annotations

import shutil
import sys
from pathlib import Path


SKILL_DIR = Path(__file__).parent.resolve()
RELEASE_DIR = SKILL_DIR / "release_version"

RELEASE_FILES = [
    "__init__.py",
    "default_config.yaml",
    "install.bat",
    "logo.png",
    "main.py",
    "RELEASE_NOTES_v0.5.0.txt",
    "satisfactory_active_save.py",
    "satisfactory_actuals.py",
    "satisfactory_adapter.py",
    "satisfactory_construction.py",
    "satisfactory_dataset.py",
    "satisfactory_docs.py",
    "satisfactory_extraction.py",
    "satisfactory_install.py",
    "satisfactory_logistics.py",
    "satisfactory_map.py",
    "satisfactory_master_plan.py",
    "satisfactory_mirror.py",
    "satisfactory_models.py",
    "satisfactory_plan_models.py",
    "satisfactory_progression.py",
    "satisfactory_reference.py",
    "satisfactory_reports.py",
    "satisfactory_save_parser.py",
    "satisfactory_scenarios.py",
    "satisfactory_solver.py",
    "satisfactory_store.py",
    "satisfactory_workspace.py",
    "skill_installer_config.json",
    "TESTER_README.md",
]

# Directory copies: node_modules is intentionally excluded; install.bat restores it with npm ci from package-lock.json.
RELEASE_DIRS = [
    ("data", None),
    ("tools/save_parser", shutil.ignore_patterns("node_modules", "*.log")),
]


def _say(message: str) -> None:
    sys.stdout.write(message + "\n")


def _ensure_release_dir_is_safe() -> None:
    resolved = RELEASE_DIR.resolve()
    try:
        resolved.relative_to(SKILL_DIR)
    except ValueError as exc:
        raise RuntimeError(f"Refusing release directory outside skill: {resolved}") from exc


def update_release() -> None:
    _ensure_release_dir_is_safe()
    if RELEASE_DIR.exists():
        shutil.rmtree(RELEASE_DIR)
    RELEASE_DIR.mkdir()

    for filename in RELEASE_FILES:
        src = SKILL_DIR / filename
        if not src.exists():
            _say(f"  WARNING: {filename} not found, skipping")
            continue
        shutil.copy2(src, RELEASE_DIR / filename)
        _say(f"  Copied {filename}")

    for rel_dir, ignore in RELEASE_DIRS:
        src_dir = SKILL_DIR / rel_dir
        if not src_dir.exists():
            _say(f"  WARNING: {rel_dir} not found, skipping")
            continue
        dest_dir = RELEASE_DIR / rel_dir
        shutil.copytree(src_dir, dest_dir, ignore=ignore)
        _say(f"  Copied directory {rel_dir}")

    _say(f"\nRelease folder updated: {RELEASE_DIR}")


if __name__ == "__main__":
    _say("Updating satisfactory_assistant release_version...")
    update_release()
