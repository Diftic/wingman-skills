"""Create a portable skill ZIP from the installer allowlist; never touch player data."""

from __future__ import annotations

import argparse
import json
import logging
from pathlib import Path
import zipfile


def build(output: Path) -> Path:
    root = Path(__file__).resolve().parent
    manifest = json.loads(
        (root / "skill_installer_config.json").read_text(encoding="utf-8")
    )
    selected = [root / name for name in manifest["files"]]
    selected += [root / "skill_installer_config.json"]
    for folder in manifest["dirs"]:
        directory = root / folder
        if not directory.is_dir():
            raise ValueError("Missing release directory: " + folder)
        selected.extend(
            p
            for p in directory.rglob("*")
            if p.is_file()
            and "__pycache__" not in p.parts
            and p.suffix not in {".pyc", ".pyo"}
        )
    for file in selected:
        if not file.is_file() or not file.resolve().is_relative_to(root):
            raise ValueError("Invalid release file: " + str(file))
    output = output.resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(output, "x", compression=zipfile.ZIP_DEFLATED) as archive:
        for file in sorted(set(selected)):
            archive.write(file, Path("sc_accountant") / file.relative_to(root))
    return output


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    logging.getLogger(__name__).info("Created %s", build(args.output))
