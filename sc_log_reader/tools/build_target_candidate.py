"""Windows cp311 candidate builder and reversible LOCAL deployment helper.

Refuses live host destinations. Real installation/publication are separate gates.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import stat
import tempfile
import uuid
import zipfile
from pathlib import Path, PurePosixPath

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = "reader-owned-files.json"


def _local(path):
    path = Path(path).absolute()
    for parent in (path, *path.parents):
        if parent.exists():
            metadata = parent.lstat()
            if (
                stat.S_ISLNK(metadata.st_mode)
                or getattr(metadata, "st_file_attributes", 0)
                & stat.FILE_ATTRIBUTE_REPARSE_POINT
            ):
                raise ValueError("Candidate deployment refuses linked paths")
    resolved = path.resolve()
    reports = (ROOT / "reports").resolve()
    temp = Path(tempfile.gettempdir()).resolve()
    relative = resolved.relative_to(temp) if resolved.is_relative_to(temp) else None
    if not resolved.is_relative_to(reports) and not (
        relative and relative.parts[0].startswith("sc-reader-t8-")
    ):
        raise ValueError(
            "Only skill reports or sc-reader-t8- task temporary directories are allowed"
        )
    return resolved


def _relative(name):
    path = PurePosixPath(name)
    if (
        path.is_absolute()
        or "\\" in name
        or ":" in name
        or ".." in path.parts
        or not path.parts
    ):
        raise ValueError("Unsafe package filename")
    return Path(*path.parts)


def _inventory(folder):
    return {
        str(path.relative_to(folder)).replace("\\", "/"): hashlib.sha256(
            path.read_bytes()
        ).hexdigest()
        for path in sorted(folder.rglob("*"))
        if path.is_file() and path.name != MANIFEST
    }


def build_candidate(output, regex_wheel, *, layout="custom"):
    output = _local(output)
    if output.exists():
        raise ValueError("Candidate output must be new")
    if layout not in {"custom", "bundled"}:
        raise ValueError("Unknown host dependency layout")
    wheel = Path(regex_wheel)
    if not wheel.name.startswith("regex-") or not wheel.name.endswith(
        "-cp311-cp311-win_amd64.whl"
    ):
        raise ValueError("Requires the qualified Windows CPython 3.11 x64 regex wheel")
    output.mkdir(parents=True)
    dependencies = output / (
        "dependencies" if layout == "custom" else "venv/Lib/site-packages"
    )
    shutil.copytree(
        ROOT / "src/sc_log_reader",
        dependencies / "sc_log_reader",
        ignore=shutil.ignore_patterns("__pycache__", "*.pyc"),
    )
    with zipfile.ZipFile(wheel) as archive:
        for entry in archive.infolist():
            relative = _relative(entry.filename)
            if entry.is_dir():
                continue
            target = dependencies / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(archive.read(entry))
    for name in ("main.py", "default_config.yaml", "CONTRACT.md", "README.md"):
        shutil.copy2(ROOT / "integrations/wingman_target" / name, output / name)
    shutil.copy2(ROOT / "LICENSE", output / "LICENSE")
    (output / MANIFEST).write_text(
        json.dumps({"layout": layout, "files": _inventory(output)}, indent=2)
    )
    return output


def _owned(folder):
    manifest = folder / MANIFEST
    if not manifest.exists():
        return []
    data = json.loads(manifest.read_text())
    files = list(data["files"]) + [MANIFEST]
    for name in files:
        _local(folder / _relative(name))
    return files


def _backup(destination, files):
    backup = destination.parent / (destination.name + ".backup-" + uuid.uuid4().hex)
    backup.mkdir(parents=True)
    for name in files:
        source = destination / _relative(name)
        if source.is_file():
            target = backup / _relative(name)
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(source), str(target))
    return backup


def deploy(candidate, destination):
    candidate, destination = _local(candidate), _local(destination)
    files = _owned(candidate)
    if not files:
        raise ValueError("Candidate ownership manifest missing")
    data = json.loads((candidate / MANIFEST).read_text())
    for name, expected in data["files"].items():
        if (
            hashlib.sha256((candidate / _relative(name)).read_bytes()).hexdigest()
            != expected
        ):
            raise ValueError("Candidate digest changed")
    owned = set(_owned(destination))
    for name in files:
        target = _local(destination / _relative(name))
        if target.exists() and name not in owned:
            raise ValueError("Refusing to overwrite a user-owned file")
    backup = _backup(destination, owned)
    for name in files:
        target = destination / _relative(name)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(candidate / _relative(name), target)
    return backup


def uninstall(destination):
    destination = _local(destination)
    return _backup(destination, _owned(destination))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True)
    parser.add_argument("--regex-wheel", required=True)
    parser.add_argument("--layout", choices=("custom", "bundled"), default="custom")
    arguments = parser.parse_args()
    candidate = build_candidate(
        arguments.output, arguments.regex_wheel, layout=arguments.layout
    )
    archive = shutil.make_archive(
        str(candidate), "zip", candidate.parent, candidate.name
    )
    print(json.dumps({"candidate": str(candidate), "archive": archive}))
