"""
SC_LogReader - Event Log

Append-only JSONL log of all game events. Covers every meaningful event from
the parser and logic layers so sibling skills (SC_Accountant, etc.) can query
game history by type and time without re-parsing Game.log.

Each entry carries:
  - timestamp / event_type / location / player_name — universal context
  - data — full event-specific fields (varies by event_type)
  - amount_auec — normalised financial value (+received / -spent) or None
  - item_name — normalised item name where relevant, or None

Entries older than 30 days are trimmed on startup.

Author: Mallachi
"""

from __future__ import annotations

import json
import logging
import threading
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path

from atomic_io import atomic_write_text

logger = logging.getLogger(__name__)


@dataclass
class EventLogEntry:
    """A single logged game event."""

    timestamp: str              # ISO 8601 from the log line
    event_type: str             # e.g. "reward_earned", "shop_buy", "injury"
    location: str               # ambient location at time of event ("" if unknown)
    player_name: str            # ambient player name ("" if unknown)
    data: dict = field(default_factory=dict)   # event-specific fields
    amount_auec: float | None = None  # +received / -spent; None if not financial
    item_name: str | None = None      # normalised item name; None if not applicable
    movement_category: str | None = None  # area/economy/work/inventory/reputation
    movement_verb: str | None = None      # bought/sold/entered/completed/etc.
    confidence: str | None = None         # high/medium/low
    fingerprint: str | None = None        # stable-ish dedupe/correlation key
    source_events: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        """Convert to JSON-serialisable dictionary."""
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> EventLogEntry:
        """Deserialise from a stored dictionary.

        Unknown keys are silently dropped so old log entries remain readable
        after fields are added or removed.
        """
        known = set(cls.__dataclass_fields__)
        filtered = {k: v for k, v in data.items() if k in known}
        return cls(**filtered)


class EventLog:
    """Append-only event log backed by a JSONL file.

    All events that pass through the SC_LogReader logic layer are written here,
    regardless of user notification settings. The log persists across sessions
    and is trimmed to the most recent 30 days on startup.
    """

    def __init__(self, log_path: Path) -> None:
        self._path = log_path
        self._lock = threading.Lock()
        # Write watermark — set before catch-up to skip already-written entries
        self._watermark_ts: str | None = None
        self._watermark_count: int = 0       # how many entries share that timestamp
        self._seen_at_watermark: int = 0     # counter incremented during dedup check

    @property
    def path(self) -> Path:
        """Return the log file path."""
        return self._path

    # ------------------------------------------------------------------
    # Write
    # ------------------------------------------------------------------

    def set_write_watermark(self) -> None:
        """Read the last timestamp already in the log and set a dedup gate.

        Call this once after trim() and before the parser starts catch-up.
        Subsequent append() calls will skip entries whose timestamps fall
        at or before the watermark, preventing duplicate catch-up writes on
        Wingman restarts within the same game session.
        """
        if not self._path.exists():
            return

        watermark_ts: str | None = None
        watermark_count = 0

        try:
            with open(self._path, "r", encoding="utf-8") as f:
                for raw in f:
                    raw = raw.strip()
                    if not raw:
                        continue
                    try:
                        d = json.loads(raw)
                        ts = d.get("timestamp")
                        if not ts:
                            continue
                        if ts != watermark_ts:
                            watermark_ts = ts
                            watermark_count = 1
                        else:
                            watermark_count += 1
                    except (json.JSONDecodeError, TypeError):
                        pass
        except OSError:
            logger.exception("EventLog: failed to read %s for watermark", self._path)
            return

        with self._lock:
            self._watermark_ts = watermark_ts
            self._watermark_count = watermark_count
            self._seen_at_watermark = 0

        logger.info(
            "EventLog: write watermark set — %s (%d entries at that ts)",
            watermark_ts,
            watermark_count,
        )

    def append(self, entry: EventLogEntry) -> None:
        """Append a single entry to the log file.

        Entries at or before the write watermark are silently skipped to
        prevent duplicates when catch-up replays a session on restart.
        """
        with self._lock:
            # Watermark dedup check
            if self._watermark_ts:
                if entry.timestamp < self._watermark_ts:
                    return
                if entry.timestamp == self._watermark_ts:
                    self._seen_at_watermark += 1
                    if self._seen_at_watermark <= self._watermark_count:
                        return

        self._path.parent.mkdir(parents=True, exist_ok=True)
        try:
            with open(self._path, "a", encoding="utf-8") as f:
                f.write(json.dumps(entry.to_dict()) + "\n")
        except OSError:
            logger.exception("EventLog: failed to append entry to %s", self._path)

    # ------------------------------------------------------------------
    # Read / Query
    # ------------------------------------------------------------------

    def query(
        self,
        event_type: str | list[str] | None = None,
        start: datetime | None = None,
        end: datetime | None = None,
        limit: int = 500,
    ) -> list[EventLogEntry]:
        """Query log entries with optional filters.

        Args:
            event_type: Single type string or list of type strings to match.
                        None returns all types.
            start: Only include entries at or after this time.
            end: Only include entries before this time.
            limit: Maximum entries to return (most recent first).

        Returns:
            List of matching entries, most recent first.
        """
        entries = self._read_all()

        if event_type is not None:
            if isinstance(event_type, str):
                event_type = [event_type]
            type_set = set(event_type)
            entries = [e for e in entries if e.event_type in type_set]

        if start:
            start_iso = start.isoformat()
            entries = [e for e in entries if e.timestamp >= start_iso]

        if end:
            end_iso = end.isoformat()
            entries = [e for e in entries if e.timestamp < end_iso]

        entries.reverse()
        return entries[:limit]

    # ------------------------------------------------------------------
    # Maintenance
    # ------------------------------------------------------------------

    def trim(self, days: int = 30) -> int:
        """Remove entries older than ``days`` days.

        Returns:
            Number of entries removed.
        """
        if not self._path.exists():
            return 0

        cutoff = datetime.now(tz=timezone.utc) - timedelta(days=days)
        cutoff_iso = cutoff.isoformat()

        entries = self._read_all()
        original_len = len(entries)
        entries = [e for e in entries if e.timestamp >= cutoff_iso]
        removed = original_len - len(entries)

        if removed > 0:
            try:
                text = "".join(json.dumps(e.to_dict()) + "\n" for e in entries)
                atomic_write_text(self._path, text)
                logger.info(
                    "EventLog: trimmed %d entries older than %d days", removed, days
                )
            except OSError:
                logger.exception("EventLog: failed to write trimmed log to %s", self._path)

        return removed

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _read_all(self) -> list[EventLogEntry]:
        """Read all entries from the JSONL file (oldest first)."""
        if not self._path.exists():
            return []

        entries: list[EventLogEntry] = []
        try:
            with open(self._path, "r", encoding="utf-8") as f:
                for line_num, line in enumerate(f, 1):
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        data = json.loads(line)
                        entries.append(EventLogEntry.from_dict(data))
                    except (json.JSONDecodeError, TypeError, KeyError):
                        logger.warning(
                            "EventLog: skipping malformed entry at line %d", line_num
                        )
        except OSError:
            logger.exception("EventLog: failed to read %s", self._path)

        return entries
