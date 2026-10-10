"""Pure data structures for the Satisfactory Assistant skill.

These dataclasses are intentionally free of any Wingman AI imports so the
resolver and workspace logic can be unit-tested without the full app.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path


# Result statuses returned by the active-save resolver.
STATUS_OK = "ok"
STATUS_NO_LOG_FOLDER = "no_log_folder"
STATUS_NO_ACTIVE_SAVE = "no_active_save"


@dataclass
class ActiveSaveReference:
    """A save reference extracted from a single log line.

    `save_name` is the save file stem (e.g. ``megatime`` for ``megatime.sav``).
    `session_name` is the in-game session name, which can differ from the save
    file name (autosaves are named after the session, not the file).
    """

    save_name: str
    session_name: str | None = None


@dataclass
class ActiveSaveResult:
    """Outcome of resolving the active save from the newest log file."""

    status: str
    save_name: str | None = None
    session_name: str | None = None
    save_file: Path | None = None
    save_file_found: bool = False
    # Set only when multiple ``<save_name>.sav`` files match across profile
    # directories. The physical save file is then left unresolved
    # (``save_file=None``) so the caller never silently picks one; this string
    # is a compact, bounded diagnostic for the user/assistant. Internal only;
    # not part of the Core API.
    save_file_ambiguity: str | None = None
    log_file: Path | None = None
    log_mtime: datetime | None = None
    root: Path | None = None

    @property
    def confirmed(self) -> bool:
        return self.status == STATUS_OK
