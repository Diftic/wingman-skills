"""Tests for log_donor.dedup."""

from __future__ import annotations

from pathlib import Path

import pytest

from log_donor.dedup import DedupStore


@pytest.fixture
def store(tmp_path: Path) -> DedupStore:
    return DedupStore(db_path=tmp_path / "donor_state.sqlite")


def test_initially_empty(store: DedupStore) -> None:
    assert not store.is_uploaded("a" * 64)


def test_record_and_lookup_uploaded(store: DedupStore) -> None:
    store.record_uploaded(
        content_hash="a" * 64,
        original_path="/some/path.log",
        upload_id="upload-1",
    )
    assert store.is_uploaded("a" * 64)
    assert not store.is_uploaded("b" * 64)


def test_record_many_uploaded(store: DedupStore) -> None:
    rows = [
        ("a" * 64, "/p1.log", "upload-1"),
        ("b" * 64, "/p2.log", "upload-1"),
    ]
    store.record_many_uploaded(rows)
    assert store.is_uploaded("a" * 64)
    assert store.is_uploaded("b" * 64)


def test_hash_cache_returns_none_on_miss(store: DedupStore, tmp_path: Path) -> None:
    p = tmp_path / "x.log"
    p.write_text("hello")
    assert store.cached_hash(p) is None


def test_hash_cache_stores_and_reads(store: DedupStore, tmp_path: Path) -> None:
    p = tmp_path / "x.log"
    p.write_text("hello")
    store.put_cached_hash(p, "dead" * 16)
    assert store.cached_hash(p) == "dead" * 16


def test_hash_cache_invalidates_on_size_change(store: DedupStore, tmp_path: Path) -> None:
    p = tmp_path / "x.log"
    p.write_text("hello")
    store.put_cached_hash(p, "dead" * 16)
    p.write_text("hello world longer")  # size changes
    assert store.cached_hash(p) is None


def test_clear_resets_state(store: DedupStore) -> None:
    store.record_uploaded("a" * 64, "/p.log", "u")
    store.clear()
    assert not store.is_uploaded("a" * 64)
