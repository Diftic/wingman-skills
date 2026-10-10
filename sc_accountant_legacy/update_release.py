"""Update the release_version folder with all runtime-necessary files.

Credit: Mallachi
"""

import shutil
from pathlib import Path


SKILL_DIR = Path(__file__).parent
RELEASE_DIR = SKILL_DIR / "release_version"

RELEASE_FILES = [
    "RELEASE_NOTES_v4.7.2.txt",
    "TESTER_README.txt",
    "__init__.py",
    "assets.py",
    "atomic_io.py",
    "default_config.yaml",
    "futures.py",
    "guid_resolver.py",
    "hauling.py",
    "install.bat",
    "logo.png",
    "main.py",
    "market_data.py",
    "models.py",
    "planning.py",
    "positions.py",
    "reports.py",
    "statements.py",
    "store.py",
]

RELEASE_DIRS = [
    "accountant_ui",
    "data",
]


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
        if not src.exists():
            print(f"  WARNING: {dirname}/ not found, skipping")
            continue
        shutil.copytree(
            src,
            RELEASE_DIR / dirname,
            ignore=shutil.ignore_patterns("__pycache__", "*.pyc", "*.pyo"),
        )
        print(f"  Copied {dirname}/")

    print(f"\nRelease folder updated: {RELEASE_DIR}")


if __name__ == "__main__":
    print("Updating sc_accountant release_version...")
    update_release()
