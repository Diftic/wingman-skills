"""Find Dyson Sphere Program saves and the active (newest) save.

The game writes saves to ``<Documents>\\Dyson Sphere Program\\Save``. Documents
is often redirected (for example to OneDrive), so the Windows "Documents"
known folder is used, never a fixed path. The game log does not name the
loaded save, so the active save is the newest complete ``.dsv`` file: the game
writes the running game there at every autosave and at exit.
"""

from __future__ import annotations

import os
import sys
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

SAVE_SUFFIX = ".dsv"
# A save that changed less than this many seconds ago may still be in progress.
SETTLE_SECONDS = 2.0
_IGNORED_STEMS = ("_autosave_errored",)

STATUS_OK = "ok"
STATUS_NO_SAVE_FOLDER = "no_save_folder"
STATUS_NO_SAVE = "no_save"


@dataclass(frozen=True)
class ActiveSaveFile:
    status: str
    save_dir: Path | None = None
    path: Path | None = None
    modified: datetime | None = None
    size: int = 0
    settling: bool = False

    @property
    def confirmed(self) -> bool:
        return self.status == STATUS_OK


def _windows_documents() -> Path | None:
    if sys.platform != "win32":
        return None
    try:
        import ctypes
        from ctypes import wintypes

        class _GUID(ctypes.Structure):
            _fields_ = [
                ("Data1", wintypes.DWORD),
                ("Data2", wintypes.WORD),
                ("Data3", wintypes.WORD),
                ("Data4", ctypes.c_ubyte * 8),
            ]

        # FOLDERID_Documents {FDD39AD0-238F-46AF-ADB4-6C85480369C7}
        folder_id = _GUID(
            0xFDD39AD0, 0x238F, 0x46AF, (ctypes.c_ubyte * 8)(0xAD, 0xB4, 0x6C, 0x85, 0x48, 0x03, 0x69, 0xC7)
        )
        out = ctypes.c_wchar_p()
        shell32 = ctypes.windll.shell32  # type: ignore[attr-defined]
        if shell32.SHGetKnownFolderPath(ctypes.byref(folder_id), 0, None, ctypes.byref(out)) != 0:
            return None
        try:
            return Path(out.value) if out.value else None
        finally:
            ctypes.windll.ole32.CoTaskMemFree(out)  # type: ignore[attr-defined]
    except (OSError, AttributeError, ValueError):
        return None


def candidate_save_dirs(configured_dir: str = "") -> list[Path]:
    """Save folders to try, best first (configured, Documents, OneDrive, home)."""
    candidates: list[Path] = []
    if configured_dir.strip():
        candidates.append(Path(os.path.expandvars(configured_dir.strip())).expanduser())
    documents = _windows_documents()
    if documents is not None:
        candidates.append(documents / "Dyson Sphere Program" / "Save")
    home = Path.home()
    for env in ("OneDrive", "OneDriveConsumer", "OneDriveCommercial"):
        value = os.environ.get(env)
        if value:
            candidates.append(Path(value) / "Documents" / "Dyson Sphere Program" / "Save")
    candidates.append(home / "Documents" / "Dyson Sphere Program" / "Save")
    candidates.append(home / "OneDrive" / "Documents" / "Dyson Sphere Program" / "Save")
    unique: list[Path] = []
    for path in candidates:
        if path not in unique:
            unique.append(path)
    return unique


def find_save_dir(configured_dir: str = "") -> Path | None:
    for path in candidate_save_dirs(configured_dir):
        try:
            if path.is_dir():
                return path
        except OSError:
            continue
    return None


def list_saves(save_dir: Path) -> list[Path]:
    try:
        return [
            path
            for path in save_dir.glob(f"*{SAVE_SUFFIX}")
            if path.is_file() and path.stem not in _IGNORED_STEMS
        ]
    except OSError:
        return []


def find_active_save(configured_dir: str = "", now: float | None = None) -> ActiveSaveFile:
    """Return the newest save; ``settling`` is True while it may still be written."""
    save_dir = find_save_dir(configured_dir)
    if save_dir is None:
        return ActiveSaveFile(status=STATUS_NO_SAVE_FOLDER)
    newest: tuple[float, int, Path] | None = None
    for path in list_saves(save_dir):
        try:
            stat = path.stat()
        except OSError:
            continue
        if newest is None or stat.st_mtime > newest[0]:
            newest = (stat.st_mtime, stat.st_size, path)
    if newest is None:
        return ActiveSaveFile(status=STATUS_NO_SAVE, save_dir=save_dir)
    mtime, size, path = newest
    current = time.time() if now is None else now
    return ActiveSaveFile(
        status=STATUS_OK,
        save_dir=save_dir,
        path=path,
        modified=datetime.fromtimestamp(mtime),
        size=size,
        settling=(current - mtime) < SETTLE_SECONDS,
    )
