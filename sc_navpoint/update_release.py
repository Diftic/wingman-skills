"""Update the release_version folder with all runtime-necessary files.

Credit: Mallachi
"""

import argparse
import json
import shutil
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile


SKILL_DIR = Path(__file__).parent
RELEASE_DIR = SKILL_DIR / "release_version"

RELEASE_FILES = [
    "__init__.py",
    "coordinate_stack.py",
    "active_frame.py",
    "distance_precision.py",
    "frame_reader.py",
    "planet_rotation.py",
    "site_rotation.py",
    "navpoint_location_names.py",
    "frame_names.json",
    "database.py",
    "default_config.yaml",
    "installer.bat",
    "TESTER_README.md",
    "LICENSE",
    "main.py",
    "learned_fields.py",
    "specialist_reader.py",
    "navigation.py",
    "overlay_fields.py",
    "overlay_reader.py",
    "overlay_win32.py",
    "ring_overlay.py",
    "scanner.py",
    "telemetry.py",
]

RELEASE_DIRS = [
    "_vendor",
    "navpoint_ui",
    "models/specialist_v8",
]


def update_release(destination: Path = RELEASE_DIR) -> Path:
    """Build a fresh release folder; never overwrite an existing artifact."""
    missing = [name for name in RELEASE_FILES + RELEASE_DIRS
               if not (SKILL_DIR / name).exists()]
    if missing:
        raise FileNotFoundError(f"Missing release inputs: {', '.join(missing)}")
    destination = destination.resolve()
    if destination.exists():
        raise FileExistsError(f"Use --output with a new folder: {destination}")
    destination.mkdir(parents=True)

    for filename in RELEASE_FILES:
        src = SKILL_DIR / filename
        shutil.copy2(src, destination / filename)
        print(f"  Copied {filename}")

    for dirname in RELEASE_DIRS:
        src = SKILL_DIR / dirname
        shutil.copytree(
            src,
            destination / dirname,
            ignore=shutil.ignore_patterns("__pycache__", "*.pyc", "*.pyo", ".pytest_cache"),
        )
        print(f"  Copied {dirname}/")

    print(f"\nRelease folder built: {destination}")
    return destination


def package_release(destination: Path, archive: Path) -> None:
    """ZIP the fresh release with a single sc_navpoint folder at its root."""
    with ZipFile(archive, "x", compression=ZIP_DEFLATED) as package:
        for path in sorted(destination.rglob("*")):
            if path.is_file():
                package.write(path, Path("sc_navpoint") / path.relative_to(destination))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=RELEASE_DIR)
    parser.add_argument("--zip", action="store_true", help="Also create a versioned installer ZIP")
    args = parser.parse_args()
    version = json.loads((SKILL_DIR / "skill_installer_config.json").read_text(encoding="utf-8"))["version"]
    archive = SKILL_DIR / f"sc_navpoint_v{version}.zip"
    if args.zip and archive.exists():
        parser.error(f"Archive already exists: {archive}")
    destination = update_release(args.output)
    if args.zip:
        package_release(destination, archive)
        print(f"Installer ZIP: {archive}")
