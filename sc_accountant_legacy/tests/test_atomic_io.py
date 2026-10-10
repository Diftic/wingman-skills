"""Tests for crash-safe atomic writes (audit finding NEW-A).

Covers the shared atomic_write_text helper and the delete_transaction
rewrite path that reaches it during background sync.

Author: Mallachi
"""

from __future__ import annotations

import os
import sys

import pytest

_skill_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _skill_dir not in sys.path:
    sys.path.insert(0, _skill_dir)

from atomic_io import atomic_write_text  # noqa: E402
from factories import make_transaction  # noqa: E402


def _tmp_files(directory):
    """Return leftover atomic-write temp files in a directory."""
    return list(directory.glob("*.tmp"))


class TestAtomicWriteText:
    def test_replaces_existing_content(self, tmp_path):
        target = tmp_path / "data.json"
        target.write_text("old", encoding="utf-8")
        atomic_write_text(target, "new")
        assert target.read_text(encoding="utf-8") == "new"
        assert _tmp_files(tmp_path) == []

    def test_creates_missing_parent(self, tmp_path):
        target = tmp_path / "nested" / "data.json"
        atomic_write_text(target, "hello")
        assert target.read_text(encoding="utf-8") == "hello"

    def test_replace_failure_preserves_original_and_leaves_no_temp(
        self, tmp_path, monkeypatch
    ):
        target = tmp_path / "data.json"
        target.write_text("original", encoding="utf-8")

        def boom(src, dst):
            raise OSError("simulated replace failure")

        monkeypatch.setattr("atomic_io.os.replace", boom)

        with pytest.raises(OSError):
            atomic_write_text(target, "replacement")

        # Old content fully intact; the failed write never touched the target.
        assert target.read_text(encoding="utf-8") == "original"
        # Temp file cleaned up on failure.
        assert _tmp_files(tmp_path) == []


class TestDeleteTransactionAtomic:
    def test_delete_leaves_remaining_intact_no_temp(self, store, tmp_path):
        store.append_transaction(make_transaction(id="t1"))
        store.append_transaction(make_transaction(id="t2"))
        store.append_transaction(make_transaction(id="t3"))

        deleted = store.delete_transaction("t2")
        assert deleted is not None
        assert deleted.id == "t2"

        remaining = {t.id for t in store.query_transactions()}
        assert remaining == {"t1", "t3"}
        assert _tmp_files(tmp_path) == []
