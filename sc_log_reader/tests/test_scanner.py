"""Tests for log_donor.scanner."""

from __future__ import annotations

from pathlib import Path

import pytest

from log_donor.dedup import DedupStore
from log_donor.scanner import (
    LiveLogUnavailableError,
    MAX_UPLOAD_BATCH_FILES,
    MAX_UPLOAD_FILE_BYTES,
    MIN_UPLOAD_FILE_BYTES,
    apply_client_caps,
    discover_candidates,
    discover_candidates_with_caps,
    discover_installs,
    parse_game_version,
)
from log_donor.types import Candidate


def test_discover_installs_finds_existing_dirs(fake_sc_install: Path) -> None:
    # Donation is scoped to Live only (scanner._INSTALL_NAMES); PTU is on
    # disk in the fixture but is intentionally never looked at.
    installs = discover_installs(fake_sc_install)
    assert set(installs.keys()) == {"Live"}
    assert installs["Live"] == fake_sc_install / "Live"


def test_discover_installs_skips_missing_dirs(tmp_path: Path) -> None:
    root = tmp_path / "StarCitizen"
    (root / "Live").mkdir(parents=True)
    # no PTU, no HOTFIX
    installs = discover_installs(root)
    assert set(installs.keys()) == {"Live"}


def test_discover_installs_returns_empty_for_missing_root(tmp_path: Path) -> None:
    assert discover_installs(tmp_path / "nonexistent") == {}


def test_parse_game_version_reads_file_version(fake_sc_install: Path) -> None:
    version = parse_game_version(fake_sc_install / "Live" / "Game.log")
    assert version == "4.8.180.28520"


def test_parse_game_version_returns_none_for_missing_file(tmp_path: Path) -> None:
    assert parse_game_version(tmp_path / "nope.log") is None


def test_discover_candidates_includes_all_parseable_versions(
    fake_sc_install: Path, tmp_path: Path, sc_not_running
) -> None:
    store = DedupStore(db_path=tmp_path / "state.sqlite")
    cands = discover_candidates(fake_sc_install, store)
    # Expected (Live only -- donation is scoped to the Live install):
    #   Live/Game.log + both parseable Live/logbackups files
    # Excluded: everything under PTU/ (out of scope entirely).
    paths = {c.path.name for c in cands}
    assert "Game.log" in paths
    assert "Game_match.log" in paths
    assert "Game_old.log" in paths
    assert all(c.install == "Live" for c in cands)
    assert len(cands) == 3
    versions = {c.path.name: c.game_version for c in cands}
    assert versions["Game.log"] == "4.8.180.28520"
    assert versions["Game_match.log"] == "4.8.180.28520"
    assert versions["Game_old.log"] == "4.7.2.99999"


def test_discover_candidates_excludes_live_gamelog_when_sc_running(
    fake_sc_install: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("log_donor.scanner.is_sc_running", lambda: True)
    store = DedupStore(db_path=tmp_path / "state.sqlite")
    cands = discover_candidates(fake_sc_install, store)
    # Game.log entries excluded; logbackups kept.
    game_log_count = sum(1 for c in cands if c.path.name == "Game.log")
    assert game_log_count == 0
    match_count = sum(1 for c in cands if c.path.name == "Game_match.log")
    assert match_count == 1
    assert {c.path.name for c in cands} == {"Game_match.log", "Game_old.log"}


def test_discover_candidates_raises_when_live_install_missing(
    tmp_path: Path,
) -> None:
    root = tmp_path / "StarCitizen"
    (root / "PTU").mkdir(parents=True)  # Live absent
    store = DedupStore(db_path=tmp_path / "state.sqlite")
    with pytest.raises(LiveLogUnavailableError):
        discover_candidates(root, store)


def test_discover_candidates_excludes_unversioned_backup(
    tmp_path: Path, sc_not_running
) -> None:
    # A backup .log with no parseable FileVersion (a truncated write, a
    # rotated-in non-SC file, whatever) must be skipped, while a parseable
    # sibling in the same logbackups folder is still offered. Game.log is
    # made unparseable here too so the assertion isolates the backup loop.
    root = tmp_path / "StarCitizen"
    backups = root / "Live" / "logbackups"
    backups.mkdir(parents=True)
    (root / "Live" / "Game.log").write_text("no version line here\n")
    (backups / "Game_versioned.log").write_text("FileVersion: 4.7.2.99999\n")
    (backups / "Game_unversioned.log").write_text("just some text, no version\n")
    store = DedupStore(db_path=tmp_path / "state.sqlite")
    candidates = discover_candidates(root, store)
    names = {c.path.name for c in candidates}
    assert "Game_unversioned.log" not in names
    assert names == {"Game_versioned.log"}
    assert candidates[0].game_version == "4.7.2.99999"


def test_discover_candidates_uses_parseable_backups_when_live_version_unparseable(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("log_donor.scanner.is_sc_running", lambda: False)
    root = tmp_path / "StarCitizen"
    backups = root / "Live" / "logbackups"
    backups.mkdir(parents=True)
    (root / "Live" / "Game.log").write_text("no version line here\n")
    (backups / "Game_old.log").write_text("FileVersion: 4.7.2.99999\n")
    store = DedupStore(db_path=tmp_path / "state.sqlite")
    candidates = discover_candidates(root, store)
    assert [c.path.name for c in candidates] == ["Game_old.log"]
    assert candidates[0].game_version == "4.7.2.99999"


def _make_candidate(path: Path, size_bytes: int, sha_seed: str, name: str) -> Candidate:
    path.write_bytes(b"x")
    return Candidate(
        path=path, install="Live", game_version="v1",
        size_bytes=size_bytes, sha256=sha_seed * 64, detected_handle="M",
        renamed=f"M_{name}",
    )


def test_apply_client_caps_drops_oversize_files(tmp_path: Path) -> None:
    ok_cand = _make_candidate(tmp_path / "ok.log", MIN_UPLOAD_FILE_BYTES, "a", "ok.log")
    big_cand = _make_candidate(
        tmp_path / "big.log", MAX_UPLOAD_FILE_BYTES + 1, "b", "big.log"
    )
    kept, skipped_undersize, skipped_oversize, trimmed = apply_client_caps([ok_cand, big_cand])
    assert kept == [ok_cand]
    assert skipped_undersize == 0
    assert skipped_oversize == 1
    assert trimmed == 0


def test_apply_client_caps_drops_undersize_files(tmp_path: Path) -> None:
    small_cand = _make_candidate(
        tmp_path / "small.log", MIN_UPLOAD_FILE_BYTES - 1, "a", "small.log"
    )
    ok_cand = _make_candidate(tmp_path / "ok.log", MIN_UPLOAD_FILE_BYTES, "b", "ok.log")
    kept, skipped_undersize, skipped_oversize, trimmed = apply_client_caps(
        [small_cand, ok_cand]
    )
    assert kept == [ok_cand]
    assert skipped_undersize == 1
    assert skipped_oversize == 0
    assert trimmed == 0


def test_apply_client_caps_accepts_exact_min_and_max_boundaries(tmp_path: Path) -> None:
    at_min = _make_candidate(tmp_path / "min.log", MIN_UPLOAD_FILE_BYTES, "a", "min.log")
    at_max = _make_candidate(tmp_path / "max.log", MAX_UPLOAD_FILE_BYTES, "b", "max.log")
    kept, skipped_undersize, skipped_oversize, trimmed = apply_client_caps([at_min, at_max])
    assert kept == [at_min, at_max]
    assert skipped_undersize == 0
    assert skipped_oversize == 0
    assert trimmed == 0


def test_apply_client_caps_trims_batch_keeping_newest(tmp_path: Path) -> None:
    import os

    candidates = []
    base_time = 1_700_000_000
    for i in range(MAX_UPLOAD_BATCH_FILES + 3):
        cand = _make_candidate(
            tmp_path / f"f{i}.log", MIN_UPLOAD_FILE_BYTES, f"{i:064x}"[0], f"f{i}.log"
        )
        # Explicit, strictly ascending mtimes so index order == age order
        # (newest last) regardless of filesystem timestamp resolution.
        os.utime(cand.path, (base_time + i, base_time + i))
        candidates.append(cand)

    kept, skipped_undersize, skipped_oversize, trimmed = apply_client_caps(candidates)
    assert skipped_undersize == 0
    assert skipped_oversize == 0
    assert trimmed == 3
    assert len(kept) == MAX_UPLOAD_BATCH_FILES
    # Newest files (highest index, written last) are kept.
    kept_names = {c.renamed for c in kept}
    for i in range(3, MAX_UPLOAD_BATCH_FILES + 3):
        assert f"M_f{i}.log" in kept_names


def test_discover_candidates_with_caps_wires_already_uploaded_count(
    fake_sc_install: Path, tmp_path: Path, sc_not_running
) -> None:
    store = DedupStore(db_path=tmp_path / "state.sqlite")
    first = discover_candidates(fake_sc_install, store)
    for c in first:
        store.record_uploaded(c.sha256, str(c.path), "test-upload")

    result = discover_candidates_with_caps(fake_sc_install, store)
    assert result.candidates == []
    assert result.already_uploaded_count == len(first)
    assert result.skipped_undersize_count == 0
    assert result.skipped_oversize_count == 0
    assert result.trimmed_count == 0


def test_discover_candidates_dedups_known_hashes(
    fake_sc_install: Path, tmp_path: Path, sc_not_running
) -> None:
    store = DedupStore(db_path=tmp_path / "state.sqlite")
    # First discovery
    first = discover_candidates(fake_sc_install, store)
    # Record all as uploaded
    for c in first:
        store.record_uploaded(c.sha256, str(c.path), "test-upload")
    # Second discovery should return zero
    second = discover_candidates(fake_sc_install, store)
    assert second == []


def test_discover_candidates_sets_renamed_with_handle(
    fake_sc_install: Path, tmp_path: Path, sc_not_running
) -> None:
    store = DedupStore(db_path=tmp_path / "state.sqlite")
    cands = discover_candidates(fake_sc_install, store)
    for c in cands:
        assert c.renamed.startswith("Mallachi_")


def test_discover_candidates_falls_back_to_unknown_when_no_handle(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("log_donor.scanner.is_sc_running", lambda: False)
    root = tmp_path / "StarCitizen"
    live = root / "Live"
    (live / "logbackups").mkdir(parents=True)
    # Game.log with no handle line
    (live / "Game.log").write_text(
        "<2026-05-14T13:41:52.133Z> FileVersion: 4.8.180.28520\n"
    )
    (live / "logbackups" / "Game_match.log").write_text(
        "<2026-05-14T13:41:52.133Z> FileVersion: 4.8.180.28520\n"
    )
    store = DedupStore(db_path=tmp_path / "state.sqlite")
    cands = discover_candidates(root, store)
    assert all(c.detected_handle is None for c in cands)
    assert all(c.renamed.startswith("unknown_") for c in cands)
