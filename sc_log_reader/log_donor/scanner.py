"""Scan SC installs for log files eligible for donation."""

from __future__ import annotations

import hashlib
import logging
import re
from pathlib import Path

from log_donor.dedup import DedupStore
from log_donor.handle_extractor import extract_handle
from log_donor.types import Candidate, DiscoveryResult, InstallType


logger = logging.getLogger(__name__)

# Donation is scoped to the Live install only. The InstallType literal keeps
# "PTU" / "HOTFIX" so the dedup DB schema (which stores the install name as
# free text) stays compatible with rows recorded before this restriction.
_INSTALL_NAMES: tuple[InstallType, ...] = ("Live",)
# Real SC Game.log header has `FileVersion: 4.8.180.28520` (and a duplicate
# `ProductVersion:` line) within the first 40 lines. We use FileVersion as
# the canonical per-build identifier. Earlier drafts looked for BranchName /
# BuildId, but those fields do not exist in real SC Game.log output.
_FILE_VERSION_RE = re.compile(r"FileVersion:\s*(?P<version>\S+)")

# Client-side caps mirroring the Worker's own limits, applied before the
# upload manifest is ever sent so the user sees the same numbers we act on.
MIN_UPLOAD_FILE_BYTES = 1 * 1024 * 1024
MAX_UPLOAD_FILE_BYTES = 50 * 1024 * 1024
MAX_UPLOAD_BATCH_FILES = 50


class LiveLogUnavailableError(Exception):
    """Raised when the Live install is unavailable for donation scanning."""


def discover_installs(sc_root: Path) -> dict[InstallType, Path]:
    """Return mapping of install name to install dir for installs that exist.

    Args:
        sc_root: Root directory of the Star Citizen installation tree
            (e.g. the folder containing Live/, PTU/, HOTFIX/).

    Returns:
        Dict mapping install name to its Path. Empty if sc_root does not exist.
    """
    result: dict[InstallType, Path] = {}
    if not sc_root.is_dir():
        return result
    for name in _INSTALL_NAMES:
        candidate = sc_root / name
        if candidate.is_dir():
            result[name] = candidate
    return result


def parse_game_version(game_log: Path) -> str | None:
    """Return the SC build identifier (e.g. '4.8.180.28520') or None.

    Reads the first 40 lines of the log to locate the `FileVersion:` line,
    which SC writes near the top of every Game.log. Two logs with the same
    FileVersion are guaranteed to be from the same SC build.

    Args:
        game_log: Path to a Game.log file.

    Returns:
        The version string after `FileVersion:`, or None if the file is
        missing, unreadable, or the field is not found in the first 40 lines.
    """
    try:
        with game_log.open("r", encoding="utf-8", errors="replace") as fh:
            head = "".join(next(fh, "") for _ in range(40))
    except OSError as e:
        logger.warning("could not read Game.log: %s (%s)", game_log, e)
        return None
    m = _FILE_VERSION_RE.search(head)
    if m is None:
        return None
    return m.group("version")


def is_sc_running() -> bool:
    """Return True if StarCitizen.exe is in the process list.

    Returns False if psutil is not installed or if access is denied.
    """
    try:
        import psutil
    except ImportError:
        return False
    try:
        for proc in psutil.process_iter(attrs=["name"]):
            if (proc.info.get("name") or "").lower() == "starcitizen.exe":
                return True
    except Exception:
        # psutil can raise on Windows access-denied; assume not running.
        return False
    return False


def _hash_file(path: Path, store: DedupStore | None) -> str:
    """Return SHA-256 hex digest of a file, using DedupStore cache when available.

    Args:
        path: Path to the file to hash.
        store: Optional DedupStore for read/write hash caching. Pass None to
            always compute fresh.

    Returns:
        Lowercase hex string of the SHA-256 digest.
    """
    if store is not None:
        cached = store.cached_hash(path)
        if cached is not None:
            return cached
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    digest = h.hexdigest()
    if store is not None:
        store.put_cached_hash(path, digest)
    return digest


def _discover_raw(
    sc_root: Path,
    store: DedupStore,
) -> tuple[list[Candidate], int]:
    """Scan the Live install for donation-eligible files, before client caps.

    Args:
        sc_root: The Star Citizen root dir (parent of Live / PTU / HOTFIX).
        store:   DedupStore for skipping already-uploaded files and caching hashes.

    Returns:
        Tuple of (candidates not yet uploaded, count of matching files that
        were filtered out because they are already in the dedup store).

    Raises:
        LiveLogUnavailableError: If the Live install is missing.
    """
    installs = discover_installs(sc_root)
    if "Live" not in installs:
        raise LiveLogUnavailableError(f"Live install not found under {sc_root}")

    install_dir = installs["Live"]
    game_log = install_dir / "Game.log"

    sc_running = is_sc_running()
    candidates: list[Candidate] = []
    already_uploaded_count = 0

    def _consider(path: Path, version: str) -> None:
        nonlocal already_uploaded_count
        cand = _build_candidate(path, "Live", version, store)
        if cand is None:
            return
        if store.is_uploaded(cand.sha256):
            already_uploaded_count += 1
            return
        candidates.append(cand)

    # Live Game.log
    if not sc_running and game_log.is_file():
        current_version = parse_game_version(game_log)
        if current_version is not None:
            _consider(game_log, current_version)

    # Each backup carries its own build identifier. Retention is a server-side
    # policy, so the client offers every parseable version for donation.
    logbackups = install_dir / "logbackups"
    if logbackups.is_dir():
        for path in sorted(logbackups.iterdir()):
            if not path.is_file() or path.suffix.lower() != ".log":
                continue
            file_version = parse_game_version(path)
            if file_version is None:
                continue
            _consider(path, file_version)

    return candidates, already_uploaded_count


def apply_client_caps(
    candidates: list[Candidate],
) -> tuple[list[Candidate], int, int, int]:
    """Apply the size and batch-count caps to a candidate list.

    Files under MIN_UPLOAD_FILE_BYTES (too small to carry a usable session --
    mirrors the Worker's own floor) or over MAX_UPLOAD_FILE_BYTES are dropped
    entirely. Both bounds are inclusive: a file of exactly MIN_UPLOAD_FILE_BYTES
    or exactly MAX_UPLOAD_FILE_BYTES is kept. If more than MAX_UPLOAD_BATCH_FILES
    remain, the newest files (by mtime) are kept and the rest trimmed.

    Args:
        candidates: Candidates to cap.

    Returns:
        Tuple of (kept candidates, count skipped for being undersize, count
        skipped for being oversize, count trimmed for exceeding the batch cap).
    """
    kept = [
        c for c in candidates
        if MIN_UPLOAD_FILE_BYTES <= c.size_bytes <= MAX_UPLOAD_FILE_BYTES
    ]
    skipped_undersize_count = sum(1 for c in candidates if c.size_bytes < MIN_UPLOAD_FILE_BYTES)
    skipped_oversize_count = sum(1 for c in candidates if c.size_bytes > MAX_UPLOAD_FILE_BYTES)

    trimmed_count = 0
    if len(kept) > MAX_UPLOAD_BATCH_FILES:
        kept.sort(key=lambda c: c.path.stat().st_mtime, reverse=True)
        trimmed_count = len(kept) - MAX_UPLOAD_BATCH_FILES
        kept = kept[:MAX_UPLOAD_BATCH_FILES]

    return kept, skipped_undersize_count, skipped_oversize_count, trimmed_count


def discover_candidates(
    sc_root: Path,
    store: DedupStore,
) -> list[Candidate]:
    """Walk the Live install, return all log files eligible for donation.

    Filters out:
      - the Live Game.log if StarCitizen.exe is running
      - files without a parseable FileVersion
      - files whose SHA-256 is already in the dedup store

    Does NOT apply the size/batch-count caps; use discover_candidates_with_caps
    for the preview and upload flows, which need those numbers surfaced.

    Args:
        sc_root: The Star Citizen root dir (parent of Live / PTU / HOTFIX).
        store:   DedupStore for skipping already-uploaded files and caching hashes.

    Returns:
        List of Candidate.

    Raises:
        LiveLogUnavailableError: If the Live install is missing.
    """
    candidates, _already_uploaded_count = _discover_raw(sc_root, store)
    return candidates


def discover_candidates_with_caps(
    sc_root: Path,
    store: DedupStore,
) -> DiscoveryResult:
    """Full donation scan: discovery, dedup filtering, and client-side caps.

    Args:
        sc_root: The Star Citizen root dir (parent of Live / PTU / HOTFIX).
        store:   DedupStore for skipping already-uploaded files and caching hashes.

    Returns:
        DiscoveryResult with the capped candidate list and filter counts.

    Raises:
        LiveLogUnavailableError: If the Live install is missing.
    """
    raw_candidates, already_uploaded_count = _discover_raw(sc_root, store)
    kept, skipped_undersize_count, skipped_oversize_count, trimmed_count = apply_client_caps(
        raw_candidates
    )
    return DiscoveryResult(
        candidates=kept,
        already_uploaded_count=already_uploaded_count,
        skipped_undersize_count=skipped_undersize_count,
        skipped_oversize_count=skipped_oversize_count,
        trimmed_count=trimmed_count,
    )


def _build_candidate(
    path: Path,
    install: InstallType,
    version: str,
    store: DedupStore,
) -> Candidate | None:
    try:
        size = path.stat().st_size
        sha256 = _hash_file(path, store)
    except OSError as e:
        logger.warning("could not read candidate file: %s (%s)", path, e)
        return None
    handle = extract_handle(path)
    name_prefix = handle if handle else "unknown"
    return Candidate(
        path=path,
        install=install,
        game_version=version,
        size_bytes=size,
        sha256=sha256,
        detected_handle=handle,
        renamed=f"{name_prefix}_{path.name}",
    )
