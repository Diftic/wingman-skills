"""Build the installer ZIP: sc_distances_v<version>.zip plus its .sha256, next to this skill.

The ZIP has a single sc_distances folder at its root with the runtime files, installer.bat and
README.md (users run installer.bat from the extracted folder). The version comes from
default_config.yaml. An existing archive is never overwritten.

    python tools/package.py
"""
from __future__ import annotations

import hashlib
import re
import sys
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

SKILL_DIR = Path(__file__).resolve().parent.parent
PACKAGE_FILES = ["__init__.py", "main.py", "default_config.yaml", "installer.bat", "README.md"]
PACKAGE_DIRS = ["dependencies", "data"]
SKIP = {"__pycache__", ".pytest_cache"}


def version() -> str:
    text = (SKILL_DIR / "default_config.yaml").read_text(encoding="utf-8")
    match = re.search(r"^version:\s*([0-9][0-9.]*)\s*$", text, re.MULTILINE)
    if not match:
        raise ValueError("no version in default_config.yaml")
    return match.group(1)


def package_files() -> list[Path]:
    files = [SKILL_DIR / name for name in PACKAGE_FILES]
    for folder in PACKAGE_DIRS:
        files += [p for p in sorted((SKILL_DIR / folder).rglob("*"))
                  if p.is_file() and not SKIP & set(p.relative_to(SKILL_DIR).parts)]
    missing = [str(p.relative_to(SKILL_DIR)) for p in files if not p.exists()]
    if missing:
        raise FileNotFoundError(f"Missing package inputs: {', '.join(missing)}")
    return files


def build(archive: Path) -> str:
    with ZipFile(archive, "x", compression=ZIP_DEFLATED) as package:
        for path in package_files():
            name = (Path("sc_distances") / path.relative_to(SKILL_DIR)).as_posix()
            data = path.read_bytes()
            if path.suffix == ".bat":  # cmd.exe needs CRLF line endings for labels and goto
                data = data.replace(b"\r\n", b"\n").replace(b"\n", b"\r\n")
            package.writestr(name, data)
    digest = hashlib.sha256(archive.read_bytes()).hexdigest()
    archive.with_name(archive.name + ".sha256").write_text(f"{digest}  {archive.name}\n", encoding="ascii")
    return digest


def main() -> int:
    archive = SKILL_DIR / f"sc_distances_v{version()}.zip"
    if archive.exists():
        print(f"Archive already exists: {archive}", file=sys.stderr)
        return 1
    digest = build(archive)
    print(f"Installer ZIP: {archive}\nSHA-256: {digest}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
