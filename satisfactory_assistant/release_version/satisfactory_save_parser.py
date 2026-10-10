"""Read Satisfactory save snapshots through the quarantined Node parser.

This module is intentionally small: Python owns process isolation, paths,
timeouts, and JSON validation; the TypeScript parser owns the binary save
format. The parser script prints a compact snapshot to stdout and never writes
to the live save.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator


class SaveParserError(RuntimeError):
    """Raised when the local save parser cannot produce a snapshot."""


_MISSING_PARSER_MARKER = "Could not load @etothepii/satisfactory-file-parser"


def _missing_parser_message() -> str:
    parser_dir = parser_script_path().parent
    return (
        "Satisfactory save parser dependency is not installed. Run install.bat "
        "again with Node.js/npm available, or run `npm ci --omit=dev --ignore-scripts` "
        f"in {parser_dir}. You can also configure Satisfactory Parser Runtime "
        "Directory to a folder containing node_modules."
    )


def _format_parser_failure(stderr: str, returncode: int) -> str:
    if _MISSING_PARSER_MARKER in stderr:
        return _missing_parser_message()
    return stderr or f"Save parser exited with {returncode}."


def _skill_dir() -> Path:
    return Path(__file__).resolve().parent


def _repo_root() -> Path:
    return _skill_dir().parents[1]


def parser_script_path() -> Path:
    """Return the bundled Node extraction script."""
    return _skill_dir() / "tools" / "save_parser" / "extract_save_snapshot.cjs"


def default_parser_runtime_dir() -> Path | None:
    """Find a local parser runtime without network access.

    Lookup favors a future bundled ``node_modules`` directory, then the audited
    development runtime under ``.tmp``. Returning ``None`` is valid: the Node
    script can still resolve globally installed modules, or the caller can pass
    an explicit runtime directory from skill settings.
    """
    local_runtime = _skill_dir() / "tools" / "save_parser"
    if (local_runtime / "node_modules" / "@etothepii" / "satisfactory-file-parser").is_dir():
        return local_runtime

    audited_runtime = _repo_root() / ".tmp" / "satisfactory-parser-audit" / "runtime"
    if (audited_runtime / "node_modules" / "@etothepii" / "satisfactory-file-parser").is_dir():
        return audited_runtime
    return None


def resolve_node_executable(configured_node: str = "") -> str:
    """Resolve the Node executable path used for the parser subprocess."""
    if configured_node.strip():
        return configured_node.strip()
    found = shutil.which("node")
    if found:
        return found
    return "node"


@contextmanager
def copied_save(save_file: Path, target_dir: Path) -> Iterator[Path]:
    """Copy ``save_file`` into ``target_dir`` and yield the copy's path.

    The copy is deleted when the context exits. Parsing this copy instead of
    the live ``.sav`` file avoids a torn read: the game can autosave-write the
    live file while a parser subprocess is still reading it.

    Args:
        save_file: Physical ``.sav`` file to duplicate.
        target_dir: Directory the copy is written into; created if missing.

    Yields:
        Path to the private copy inside ``target_dir``.

    Raises:
        SaveParserError: If ``save_file`` is not a file, or the copy fails.
    """
    save_path = save_file.resolve()
    if not save_path.is_file():
        raise SaveParserError(f"Save file not found: {save_file}")

    target_dir.mkdir(parents=True, exist_ok=True)

    fd, raw_copy_path = tempfile.mkstemp(
        prefix="parse_", suffix=".sav", dir=str(target_dir)
    )
    os.close(fd)
    copy_path = Path(raw_copy_path)
    try:
        shutil.copy2(save_path, copy_path)
    except OSError as exc:
        copy_path.unlink(missing_ok=True)
        raise SaveParserError(f"Failed to copy save file for parsing: {exc}") from exc

    try:
        yield copy_path
    finally:
        try:
            copy_path.unlink(missing_ok=True)
        except OSError:
            pass


def extract_save_snapshot(
    save_file: Path,
    *,
    parser_runtime_dir: str = "",
    parser_module_dir: str = "",
    node_executable: str = "",
    summary_only: bool = False,
    timeout_seconds: int = 90,
) -> dict[str, Any]:
    """Parse ``save_file`` into a compact JSON snapshot.

    Args:
        save_file: Physical ``.sav`` file to parse. The caller may pass a copy
            if it wants stronger live-save isolation.
        parser_runtime_dir: Optional directory containing ``node_modules``.
        parser_module_dir: Optional absolute parser package directory.
        node_executable: Optional Node executable path.
        summary_only: Ask the Node wrapper to omit the full machine array.
        timeout_seconds: Hard parser subprocess timeout.
    """
    save_path = save_file.resolve()
    if not save_path.is_file():
        raise SaveParserError(f"Save file not found: {save_file}")

    script = parser_script_path()
    if not script.is_file():
        raise SaveParserError(f"Save parser script not found: {script}")

    env = os.environ.copy()
    runtime = parser_runtime_dir.strip()
    module_dir = parser_module_dir.strip()
    if runtime:
        env["SATISFACTORY_PARSER_RUNTIME"] = str(Path(runtime).resolve())
    elif "SATISFACTORY_PARSER_RUNTIME" not in env:
        default_runtime = default_parser_runtime_dir()
        if default_runtime is not None:
            env["SATISFACTORY_PARSER_RUNTIME"] = str(default_runtime)
    if module_dir:
        env["SATISFACTORY_PARSER_MODULE"] = str(Path(module_dir).resolve())

    command = [resolve_node_executable(node_executable), str(script), str(save_path)]
    if summary_only:
        command.append("--summary-only")

    try:
        completed = subprocess.run(
            command,
            cwd=str(_skill_dir()),
            env=env,
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
            check=False,
        )
    except FileNotFoundError as exc:
        raise SaveParserError("Node.js was not found. Install Node or configure node path.") from exc
    except subprocess.TimeoutExpired as exc:
        raise SaveParserError(
            f"Save parser timed out after {timeout_seconds} seconds."
        ) from exc

    if completed.returncode != 0:
        stderr = completed.stderr.strip()
        raise SaveParserError(_format_parser_failure(stderr, completed.returncode))

    try:
        snapshot = json.loads(completed.stdout)
    except json.JSONDecodeError as exc:
        raise SaveParserError("Save parser returned invalid JSON.") from exc

    if not isinstance(snapshot, dict):
        raise SaveParserError("Save parser returned a non-object JSON payload.")
    return snapshot
