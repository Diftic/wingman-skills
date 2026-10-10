"""Active-save resolver for Satisfactory.

The active save is established from the NEWEST Satisfactory log file, never by
guessing the newest ``.sav``. A newer save file is not proof that it is the
loaded save; only the newest log confirms what the player actually loaded.

Ground truth (verified against a real install, FactoryGame 4.x):

    Saved/
    |-- Logs/
    |   |-- FactoryGame.log                       (live, newest while running)
    |   |-- FactoryGame-backup-<date>.log         (rotated)
    |-- SaveGames/
        |-- <steam-or-epic-id>/
            |-- <SaveName>.sav

The load is recorded in Unreal "travel" URLs that look like::

    ...?loadgame=megatime?sessionName=Mallachi?SessionDefinition=SessionDef_SinglePlayer

`?` is the token delimiter and values are written literally (spaces allowed,
never URL-encoded), so the URL is parsed by splitting on ``?`` into
``key=value`` chunks rather than with a fragile regex.

Detection uses CHRONOLOGICAL evidence order: the newest recognized reference
wins, whether it is a travel URL or a local-backup line. This matters after a
mid-session save switch, where the most recent evidence is a backup line for the
new save while an older travel URL still names the old save.
"""

from __future__ import annotations

import os
from collections.abc import Iterable
from datetime import datetime
from pathlib import Path

from satisfactory_models import (
    STATUS_NO_ACTIVE_SAVE,
    STATUS_NO_LOG_FOLDER,
    STATUS_OK,
    ActiveSaveReference,
    ActiveSaveResult,
)


# Matches the game's own (misspelled) local-backup line:
#   LogGame: Succesfully saved a local backup with name: megatime-06.16.26-20.34.19.sav
_BACKUP_MARKER = "saved a local backup with name:"


def expand_path(raw: str) -> Path:
    """Expand environment variables and ``~`` in a user-supplied path."""
    return Path(os.path.expandvars(os.path.expanduser(raw))).resolve()


def candidate_saved_roots(configured_dir: str = "") -> list[Path]:
    """Build the ordered list of candidate Satisfactory ``Saved`` roots.

    A configured path is an explicit override: when set, only that directory is
    considered (auto-detection is skipped entirely) so the skill never wanders
    into a different install. Common per-platform locations are used only when
    nothing is configured. Only existing directories are returned, de-duplicated
    by resolved path.
    """
    if configured_dir:
        configured = expand_path(configured_dir)
        return [configured] if configured.is_dir() else []

    candidates: list[Path] = []

    local_appdata = os.environ.get("LOCALAPPDATA")
    if local_appdata:
        candidates.append(Path(local_appdata) / "FactoryGame" / "Saved")

    home = Path.home()
    # Best-effort, non-invasive Linux / Proton locations.
    candidates.append(home / ".local" / "share" / "FactoryGame" / "Saved")
    candidates.append(
        home
        / ".steam"
        / "steam"
        / "steamapps"
        / "compatdata"
        / "526870"
        / "pfx"
        / "drive_c"
        / "users"
        / "steamuser"
        / "AppData"
        / "Local"
        / "FactoryGame"
        / "Saved"
    )

    seen: set[str] = set()
    roots: list[Path] = []
    for path in candidates:
        try:
            resolved = path.resolve()
        except OSError:
            continue
        key = str(resolved).lower()
        if key in seen:
            continue
        seen.add(key)
        if resolved.is_dir():
            roots.append(resolved)
    return roots


def find_logs(root: Path) -> list[Path]:
    """Return all ``*.log`` files under ``<root>/Logs``."""
    logs_dir = root / "Logs"
    if not logs_dir.is_dir():
        return []
    return [p for p in logs_dir.glob("*.log") if p.is_file()]


def newest_log(roots: list[Path]) -> tuple[Path, Path] | None:
    """Find the newest log across all roots.

    Returns ``(root, log_path)`` for the newest log by mtime, or ``None`` if no
    logs exist anywhere.
    """
    best: tuple[float, Path, Path] | None = None
    for root in roots:
        for log in find_logs(root):
            try:
                mtime = log.stat().st_mtime
            except OSError:
                continue
            if best is None or mtime > best[0]:
                best = (mtime, root, log)
    if best is None:
        return None
    return best[1], best[2]


def _parse_travel_tokens(line: str) -> dict[str, str]:
    """Parse ``loadgame`` / ``sessionName`` out of an Unreal travel URL line.

    The query is delimiter-based: split the travel string on ``?`` into chunks,
    then split each chunk on the first ``=`` into ``key=value``. ``?`` is never
    valid in a Windows save filename and values are taken literally otherwise,
    so names with spaces are preserved and any unknown intervening query token
    (e.g. a future ``?Foo=1`` between ``loadgame`` and ``sessionName``) cannot
    bleed into the save name.
    """
    query_start = line.find("?")
    if query_start == -1:
        return {}
    tokens: dict[str, str] = {}
    for chunk in line[query_start + 1:].split("?"):
        if "=" not in chunk:
            continue
        key, value = chunk.split("=", 1)
        key = key.strip()
        value = value.strip()
        if key in ("loadgame", "sessionName") and value and key not in tokens:
            tokens[key] = value
    return tokens


def _save_name_from_backup_line(line: str) -> str | None:
    """Derive a save name from a local-backup line.

    ``...with name: megatime-06.16.26-20.34.19.sav`` -> ``megatime``.
    """
    idx = line.lower().find(_BACKUP_MARKER)
    if idx == -1:
        return None
    tail = line[idx + len(_BACKUP_MARKER):].strip()
    if not tail.lower().endswith(".sav"):
        return None
    stem = tail[: -len(".sav")]
    # Strip a trailing "-<date>-<time>" backup suffix if present.
    parts = stem.rsplit("-", 2)
    name = parts[0] if len(parts) == 3 else stem
    return name.strip() or None


def extract_active_save_from_lines(lines: Iterable[str]) -> ActiveSaveReference | None:
    """Extract the active save from a forward stream of log lines.

    Uses chronological (not source-type) priority: the LAST recognized
    reference wins, whether it is a travel URL or a local-backup line. This is a
    single forward pass with O(1) memory, so it can stream a log of any size
    line-by-line and never miss a mid-session switch.

    When the newest evidence is a backup line (which carries no session name),
    the session name is back-filled from the most recent travel URL that named
    the same save earlier in the stream.
    """
    newest_save: str | None = None
    newest_session: str | None = None
    travel_sessions: dict[str, str] = {}

    for line in lines:
        if "loadgame=" in line:
            tokens = _parse_travel_tokens(line)
            save = tokens.get("loadgame")
            if save:
                session = tokens.get("sessionName")
                newest_save, newest_session = save, session
                if session:
                    travel_sessions[save] = session
                continue
        if _BACKUP_MARKER in line.lower():
            save = _save_name_from_backup_line(line)
            if save:
                newest_save, newest_session = save, None

    if newest_save is None:
        return None
    if newest_session is None:
        newest_session = travel_sessions.get(newest_save)
    return ActiveSaveReference(newest_save, newest_session)


def extract_active_save_reference(log_text: str) -> ActiveSaveReference | None:
    """Extract the active save from in-memory log text (splits into lines)."""
    return extract_active_save_from_lines(log_text.splitlines())


# Cap the profile names listed in an ambiguity diagnostic so the context line
# stays short even when many profile directories hold the same save name.
_MAX_AMBIGUITY_PROFILES = 4


def find_save_files(root: Path, save_name: str) -> list[Path]:
    """Return every ``<save_name>.sav`` under ``SaveGames``, deterministically.

    Searches both known layouts: per-profile subdirectories
    (``SaveGames/<profile>/<save_name>.sav``) and saves placed directly under
    ``SaveGames``. The save name is used as a literal filename (never a glob
    pattern), so names with metacharacters like ``[`` or ``]`` resolve correctly
    (e.g. ``Factory [1].sav``).

    Results are sorted so that "exactly one match" versus "multiple matches"
    never depends on filesystem iteration order. Any filesystem error degrades
    to an empty list rather than raising, matching the resolver's defensive
    posture (permissions, a profile dir removed mid-scan).
    """
    save_games = root / "SaveGames"
    target = f"{save_name}.sav"
    matches: list[Path] = []
    try:
        if not save_games.is_dir():
            return []
        # Some layouts keep saves directly under SaveGames.
        direct = save_games / target
        if direct.is_file():
            matches.append(direct.resolve())
        for profile in save_games.iterdir():
            if not profile.is_dir():
                continue
            candidate = profile / target
            if candidate.is_file():
                matches.append(candidate.resolve())
    except OSError:
        return []
    return sorted(set(matches), key=str)


def resolve_save_file(root: Path, save_name: str) -> Path | None:
    """Locate the single ``<save_name>.sav`` under ``<root>/SaveGames/``.

    Returns the matching path only when it is unique. With no match, or with
    multiple matches across different profile directories, returns ``None`` so
    the caller never silently picks one of several ambiguous files. Use
    ``find_save_files`` when the full match list (and any ambiguity) is needed.
    """
    matches = find_save_files(root, save_name)
    return matches[0] if len(matches) == 1 else None


def ambiguous_save_diagnostic(matches: list[Path]) -> str:
    """Build a compact, bounded note describing duplicate save-file matches.

    Names the containing profile directories (not full paths) and caps the list
    so the rendered context line stays short even with many duplicates.
    """
    profiles = [p.parent.name for p in matches]
    shown = profiles[:_MAX_AMBIGUITY_PROFILES]
    extra = len(profiles) - len(shown)
    suffix = f" (+{extra} more)" if extra > 0 else ""
    return f"{len(matches)} matching .sav files under profiles: {', '.join(shown)}{suffix}"


def resolve_active_save(configured_dir: str = "") -> ActiveSaveResult:
    """Resolve the active save strictly from the newest log file.

    The newest log is streamed line-by-line (O(1) memory), so a save switch is
    detected wherever it occurs, regardless of log size.
    """
    roots = candidate_saved_roots(configured_dir)
    if not roots:
        return ActiveSaveResult(status=STATUS_NO_LOG_FOLDER)

    found = newest_log(roots)
    if found is None:
        return ActiveSaveResult(status=STATUS_NO_LOG_FOLDER)

    root, log_file = found

    # The log can rotate or vanish between selection and reading; treat that as
    # "no active save" rather than letting an OSError escape.
    try:
        log_mtime = datetime.fromtimestamp(log_file.stat().st_mtime)
        with log_file.open("r", encoding="utf-8", errors="replace") as handle:
            reference = extract_active_save_from_lines(handle)
    except OSError:
        return ActiveSaveResult(status=STATUS_NO_ACTIVE_SAVE, root=root)

    if reference is None:
        return ActiveSaveResult(
            status=STATUS_NO_ACTIVE_SAVE,
            log_file=log_file,
            log_mtime=log_mtime,
            root=root,
        )

    # A unique match resolves the physical file; multiple matches across
    # profiles are left unresolved with a diagnostic so identity stays based on
    # the active-log save name only (see SSP-P0-W03/W05).
    matches = find_save_files(root, reference.save_name)
    save_file = matches[0] if len(matches) == 1 else None
    ambiguity = ambiguous_save_diagnostic(matches) if len(matches) >= 2 else None
    return ActiveSaveResult(
        status=STATUS_OK,
        save_name=reference.save_name,
        session_name=reference.session_name,
        save_file=save_file,
        save_file_found=save_file is not None,
        save_file_ambiguity=ambiguity,
        log_file=log_file,
        log_mtime=log_mtime,
        root=root,
    )
