"""Shared dataclasses for the log_donor package."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal


InstallType = Literal["Live", "PTU", "HOTFIX"]


@dataclass
class Candidate:
    """One log file eligible for donation."""

    path: Path
    install: InstallType
    game_version: str
    size_bytes: int
    sha256: str
    detected_handle: str | None
    renamed: str  # "{handle_or_unknown}_{original_name}"


@dataclass
class DiscoveryResult:
    """Raw output of a donation scan, before it is shaped for the preview dialog."""

    candidates: list[Candidate]
    already_uploaded_count: int  # files filtered out by local dedup
    skipped_undersize_count: int  # files filtered out by the client-side minimum size
    skipped_oversize_count: int  # files filtered out by the client-side maximum size
    trimmed_count: int  # files filtered out by the client-side batch cap


@dataclass
class PreviewSummary:
    """What the preview dialog shows the player before they confirm."""

    candidates: list[Candidate]
    total_bytes: int
    per_install_counts: dict[str, int]
    per_install_bytes: dict[str, int]
    already_uploaded_count: int  # files filtered out by local dedup
    skipped_undersize_count: int  # files filtered out by the client-side minimum size
    skipped_oversize_count: int  # files filtered out by the client-side maximum size
    trimmed_count: int  # files filtered out by the client-side batch cap


@dataclass
class FileUploadResult:
    """Per-file outcome of an upload attempt."""

    sha256: str
    renamed: str
    succeeded: bool
    already_uploaded: bool  # true if Worker said the hash was known
    error: str | None = None


@dataclass
class UploadResult:
    """Aggregate outcome of one /upload/begin -> PUTs -> /upload/complete cycle."""

    upload_id: str | None
    files: list[FileUploadResult] = field(default_factory=list)
    total_bytes_uploaded: int = 0
    error: str | None = None

    @property
    def succeeded_count(self) -> int:
        return sum(1 for f in self.files if f.succeeded)

    @property
    def failed_count(self) -> int:
        return sum(1 for f in self.files if not f.succeeded and not f.already_uploaded)
