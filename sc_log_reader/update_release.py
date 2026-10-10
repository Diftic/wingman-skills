"""Update the release_version folder with all runtime-necessary files.

Credit: Mallachi
"""

import os
import shutil
from pathlib import Path


SKILL_DIR = Path(__file__).parent
RELEASE_DIR = SKILL_DIR / "release_version"

RELEASE_FILES = [
    "__init__.py",
    "atomic_io.py",
    "debug_emitter.py",
    "default_config.yaml",
    "event_log.py",
    "install.bat",
    "ledger.py",
    "location_names.py",
    "logic.py",
    "logo.png",
    "main.py",
    "parser.py",
    "TESTER_README.md",
]

RELEASE_DIRS = [
    "log_donor",
]


def inject_donor_token(release_root: Path) -> None:
    """Replace __INJECT_AT_BUILD__ in release_version log_donor/_build_config.py.

    Reads the build-time token from the DONOR_TOKEN_BUILD env var. Fails
    loudly if the env var is missing or the placeholder is absent so a
    half-substituted config cannot ship.

    Args:
        release_root: Path to the release_version directory.

    Raises:
        RuntimeError: If DONOR_TOKEN_BUILD is unset or the placeholder is
            already gone.
    """
    token = os.environ.get("DONOR_TOKEN_BUILD")
    if not token:
        raise RuntimeError(
            "DONOR_TOKEN_BUILD env var is not set. Refusing to build release "
            "with placeholder donor token."
        )
    cfg_path = release_root / "log_donor" / "_build_config.py"
    text = cfg_path.read_text(encoding="utf-8")
    if "__INJECT_AT_BUILD__" not in text:
        raise RuntimeError(
            f"Placeholder __INJECT_AT_BUILD__ not found in {cfg_path}. "
            "Either the substitution already happened or the placeholder was renamed."
        )
    cfg_path.write_text(
        text.replace("__INJECT_AT_BUILD__", token),
        encoding="utf-8",
    )


def update_release() -> None:
    if RELEASE_DIR.exists():
        shutil.rmtree(RELEASE_DIR)
    RELEASE_DIR.mkdir()

    for filename in RELEASE_FILES:
        src = SKILL_DIR / filename
        if not src.exists():
            print(f"  WARNING: {filename} not found, skipping")
            continue
        shutil.copy2(src, RELEASE_DIR / filename)
        print(f"  Copied {filename}")

    for dirname in RELEASE_DIRS:
        src = SKILL_DIR / dirname
        if not src.is_dir():
            print(f"  WARNING: {dirname}/ not found, skipping")
            continue
        shutil.copytree(
            src,
            RELEASE_DIR / dirname,
            ignore=shutil.ignore_patterns("__pycache__", "*.pyc"),
        )
        print(f"  Copied {dirname}/ (recursive)")

    inject_donor_token(RELEASE_DIR)
    print(f"\nRelease folder updated: {RELEASE_DIR}")


if __name__ == "__main__":
    print("Updating sc_log_reader release_version...")
    update_release()
