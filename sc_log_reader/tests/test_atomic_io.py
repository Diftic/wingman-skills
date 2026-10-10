"""Tests for crash-safe atomic writes in SC_LogReader (audit finding NEW-A).

Covers the shared atomic_write_text helper and the EventLog.trim rewrite
path that reaches it on startup.

Author: Mallachi
"""

from __future__ import annotations

import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

_skill_dir = Path(__file__).resolve().parent.parent
if str(_skill_dir) not in sys.path:
    sys.path.insert(0, str(_skill_dir))

from atomic_io import atomic_write_text  # noqa: E402
from event_log import EventLog, EventLogEntry  # noqa: E402


def _make_entry(ts: str) -> EventLogEntry:
    return EventLogEntry(
        timestamp=ts, event_type="test", location="", player_name=""
    )


def _tmp_files(directory: Path) -> list[Path]:
    """Return leftover atomic-write temp files in a directory."""
    return list(directory.glob("*.tmp"))


class TestEventLogTrimAtomic:
    def test_trim_content_unchanged_no_temp(self, tmp_path):
        log = EventLog(tmp_path / "events.jsonl")

        now = datetime.now(tz=timezone.utc)
        old_ts = (now - timedelta(days=40)).isoformat()
        recent_older = (now - timedelta(days=1)).isoformat()
        recent_newer = (now - timedelta(hours=1)).isoformat()

        log.append(_make_entry(old_ts))
        log.append(_make_entry(recent_older))
        log.append(_make_entry(recent_newer))

        removed = log.trim(days=30)
        assert removed == 1

        # Reader sees exactly the two recent entries, most recent first,
        # matching the pre-atomic rewrite behaviour.
        remaining = [e.timestamp for e in log.query(limit=100)]
        assert remaining == [recent_newer, recent_older]
        assert _tmp_files(tmp_path) == []


class TestAtomicWriteText:
    def test_replaces_existing_content(self, tmp_path):
        target = tmp_path / "state.json"
        target.write_text("old", encoding="utf-8")
        atomic_write_text(target, "new")
        assert target.read_text(encoding="utf-8") == "new"
        assert _tmp_files(tmp_path) == []

    def test_replace_failure_preserves_original_and_leaves_no_temp(
        self, tmp_path, monkeypatch
    ):
        target = tmp_path / "state.json"
        target.write_text("original", encoding="utf-8")

        def boom(src, dst):
            raise OSError("simulated replace failure")

        monkeypatch.setattr("atomic_io.os.replace", boom)

        with pytest.raises(OSError):
            atomic_write_text(target, "replacement")

        assert target.read_text(encoding="utf-8") == "original"
        assert _tmp_files(tmp_path) == []
