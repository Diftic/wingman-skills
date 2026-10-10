"""Tests for the active-save resolver.

Fixtures mirror a real Satisfactory ``Saved`` tree and use a real captured
travel-URL line so the parser is exercised against ground truth.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from satisfactory_active_save import (
    candidate_saved_roots,
    extract_active_save_reference,
    newest_log,
    resolve_active_save,
)
from satisfactory_models import STATUS_NO_ACTIVE_SAVE, STATUS_NO_LOG_FOLDER, STATUS_OK


# A real travel-URL line (trimmed of the long ClientIdentity blob) using the
# verified format: `?loadgame=<stem>?sessionName=<name>?SessionDefinition=...`
def _load_line(save_name: str, session: str) -> str:
    return (
        "[2026.06.16-18.10.11:950][318]LogEngine: Server switch level: "
        "/Game/FactoryGame/Map/GameLevel01/Persistent_Level?skiponboarding"
        "?ClientIdentity=2100000061303939"
        f"?loadgame={save_name}?sessionName={session}"
        "?SessionDefinition=SessionDef_SinglePlayer"
    )


def _backup_line(save_name: str) -> str:
    return (
        "[2026.06.16-18.34.19:781][250]LogGame: Succesfully saved a local "
        f"backup with name: {save_name}-06.16.26-20.34.19.sav"
    )


def _set_mtime(path: Path, when: float) -> None:
    os.utime(path, (when, when))


@pytest.fixture
def saved_tree(tmp_path: Path) -> Path:
    """Build a Saved/ tree with two logs and two saves.

    Older log (mtime older) references Desert_Main; newest log references
    Oil_Expansion. Both .sav files exist.
    """
    root = tmp_path / "FactoryGame" / "Saved"
    logs = root / "Logs"
    saves = root / "SaveGames" / "76561197000000000"
    logs.mkdir(parents=True)
    saves.mkdir(parents=True)

    (saves / "Desert_Main.sav").write_bytes(b"binary-savedata")
    (saves / "Oil_Expansion.sav").write_bytes(b"binary-savedata")

    old_log = logs / "FactoryGame-backup-2026.06.10-10.00.00.log"
    new_log = logs / "FactoryGame.log"
    old_log.write_text(_load_line("Desert_Main", "Mallachi"), encoding="utf-8")
    new_log.write_text(_load_line("Oil_Expansion", "Mallachi"), encoding="utf-8")

    _set_mtime(old_log, 1_000_000.0)
    _set_mtime(new_log, 2_000_000.0)
    return root


def test_extract_prefers_loadgame_travel_url() -> None:
    ref = extract_active_save_reference(_load_line("megatime", "Mallachi"))
    assert ref is not None
    assert ref.save_name == "megatime"
    assert ref.session_name == "Mallachi"


def test_extract_handles_names_with_spaces() -> None:
    ref = extract_active_save_reference(_load_line("Dessert life", "STFU and take my money"))
    assert ref is not None
    assert ref.save_name == "Dessert life"
    assert ref.session_name == "STFU and take my money"


def test_parser_ignores_unknown_intervening_token() -> None:
    """An unknown future query token must not bleed into the save name."""
    line = (
        "[2026.06.16-18.10.11:950][318]LogEngine: Server switch level: "
        "/Game/FactoryGame/Map/GameLevel01/Persistent_Level?skiponboarding"
        "?loadgame=SaveA?UnknownFuture=1?sessionName=Sess"
        "?SessionDefinition=SessionDef_SinglePlayer"
    )
    ref = extract_active_save_reference(line)
    assert ref is not None
    assert ref.save_name == "SaveA"
    assert ref.session_name == "Sess"


def test_extract_latest_load_wins() -> None:
    tail = "\n".join([_load_line("First", "S"), _load_line("Second", "S")])
    ref = extract_active_save_reference(tail)
    assert ref is not None
    assert ref.save_name == "Second"


def test_extract_newer_backup_beats_older_travel_url() -> None:
    """Chronological ordering: a newer backup line wins over an older load URL.

    Reproduces the mid-session save-switch case: the player loaded OldSave
    (travel URL), then switched to NewSave (only a backup line follows).
    """
    text = "\n".join([_load_line("OldSave", "Mallachi"), _backup_line("NewSave")])
    ref = extract_active_save_reference(text)
    assert ref is not None
    assert ref.save_name == "NewSave"


def test_extract_backfills_session_from_matching_travel_url() -> None:
    """A backup-only newest reference still recovers session from its load URL."""
    text = "\n".join([_load_line("megatime", "Mallachi"), _backup_line("megatime")])
    ref = extract_active_save_reference(text)
    assert ref is not None
    assert ref.save_name == "megatime"
    assert ref.session_name == "Mallachi"


def test_extract_falls_back_to_backup_line() -> None:
    ref = extract_active_save_reference(_backup_line("megatime"))
    assert ref is not None
    assert ref.save_name == "megatime"
    assert ref.session_name is None


def test_extract_returns_none_without_reference() -> None:
    assert extract_active_save_reference("LogTemp: nothing interesting here") is None


def test_newest_log_wins_over_older(saved_tree: Path) -> None:
    found = newest_log([saved_tree])
    assert found is not None
    _, log = found
    assert log.name == "FactoryGame.log"


def test_resolve_uses_newest_log(saved_tree: Path) -> None:
    result = resolve_active_save(configured_dir=str(saved_tree))
    assert result.status == STATUS_OK
    assert result.save_name == "Oil_Expansion"
    assert result.save_file_found is True
    assert result.save_file is not None
    assert result.save_file.name == "Oil_Expansion.sav"


def test_resolve_ignores_older_log_reference(saved_tree: Path) -> None:
    result = resolve_active_save(configured_dir=str(saved_tree))
    assert result.save_name != "Desert_Main"


def test_resolve_no_active_save_does_not_inspect_saves(tmp_path: Path) -> None:
    root = tmp_path / "FactoryGame" / "Saved"
    logs = root / "Logs"
    saves = root / "SaveGames" / "profile"
    logs.mkdir(parents=True)
    saves.mkdir(parents=True)
    (saves / "Should_Not_Be_Picked.sav").write_bytes(b"data")
    (logs / "FactoryGame.log").write_text("LogTemp: boot, no save loaded", encoding="utf-8")

    result = resolve_active_save(configured_dir=str(root))
    assert result.status == STATUS_NO_ACTIVE_SAVE
    assert result.save_name is None
    assert result.save_file is None


def test_resolve_missing_save_file_keeps_identity(tmp_path: Path) -> None:
    root = tmp_path / "FactoryGame" / "Saved"
    logs = root / "Logs"
    (root / "SaveGames" / "profile").mkdir(parents=True)
    logs.mkdir(parents=True)
    (logs / "FactoryGame.log").write_text(_load_line("Ghost_Save", "Mallachi"), encoding="utf-8")

    result = resolve_active_save(configured_dir=str(root))
    assert result.status == STATUS_OK
    assert result.save_name == "Ghost_Save"
    assert result.save_file_found is False
    assert result.save_file is None


def test_resolve_no_log_folder(tmp_path: Path) -> None:
    result = resolve_active_save(configured_dir=str(tmp_path / "does-not-exist"))
    assert result.status == STATUS_NO_LOG_FOLDER


def test_resolve_mid_log_switch_in_large_log(tmp_path: Path) -> None:
    """Regression: a newer load deep in a large log, with no later evidence.

    Streaming the whole log line-by-line must find the mid-log switch even
    though it is neither at the head nor in the tail, and no backup line
    follows it.
    """
    root = tmp_path / "FactoryGame" / "Saved"
    logs = root / "Logs"
    saves = root / "SaveGames" / "profile"
    logs.mkdir(parents=True)
    saves.mkdir(parents=True)
    (saves / "NewSave.sav").write_bytes(b"data")

    before = "\n".join(f"[ts] LogTemp: noise before {i}" for i in range(5000))
    after = "\n".join(f"[ts] LogTemp: noise after {i}" for i in range(5000))
    content = "\n".join(
        [
            _load_line("OldSave", "Mallachi"),
            before,
            _load_line("NewSave", "Mallachi"),  # mid-log switch, no later evidence
            after,
        ]
    )
    (logs / "FactoryGame.log").write_text(content, encoding="utf-8")

    result = resolve_active_save(configured_dir=str(root))
    assert result.status == STATUS_OK
    assert result.save_name == "NewSave"
    assert result.session_name == "Mallachi"
    assert result.save_file_found is True


def test_resolve_save_file_survives_oserror(tmp_path: Path, monkeypatch) -> None:
    """resolve_save_file returns None (not raise) when the filesystem errors."""
    from satisfactory_active_save import resolve_save_file

    root = tmp_path / "FactoryGame" / "Saved"
    (root / "SaveGames" / "profile").mkdir(parents=True)

    def boom(self):
        raise OSError("simulated permission error")

    monkeypatch.setattr(Path, "iterdir", boom)
    assert resolve_save_file(root, "Anything") is None


def test_resolve_full_flow_with_unresolvable_save(tmp_path: Path, monkeypatch) -> None:
    """When save lookup fails, the resolver keeps the log identity gracefully."""
    import satisfactory_active_save as sas

    root = tmp_path / "FactoryGame" / "Saved"
    logs = root / "Logs"
    (root / "SaveGames" / "profile").mkdir(parents=True)
    logs.mkdir(parents=True)
    (logs / "FactoryGame.log").write_text(_load_line("Boomtown", "Mallachi"), encoding="utf-8")

    monkeypatch.setattr(sas, "resolve_save_file", lambda *_: None)

    result = resolve_active_save(configured_dir=str(root))
    assert result.status == STATUS_OK
    assert result.save_name == "Boomtown"
    assert result.save_file_found is False


def test_resolve_save_name_with_glob_metacharacters(tmp_path: Path) -> None:
    """Save names containing brackets must resolve as literal filenames."""
    root = tmp_path / "FactoryGame" / "Saved"
    logs = root / "Logs"
    saves = root / "SaveGames" / "profile"
    logs.mkdir(parents=True)
    saves.mkdir(parents=True)
    (saves / "Factory [1].sav").write_bytes(b"data")
    (logs / "FactoryGame.log").write_text(_load_line("Factory [1]", "Mallachi"), encoding="utf-8")

    result = resolve_active_save(configured_dir=str(root))
    assert result.status == STATUS_OK
    assert result.save_name == "Factory [1]"
    assert result.save_file_found is True
    assert result.save_file.name == "Factory [1].sav"


def test_candidate_roots_dedupes_and_filters(saved_tree: Path) -> None:
    roots = candidate_saved_roots(str(saved_tree))
    assert saved_tree.resolve() in roots


# --- SSP-P0-W05: same-name save ambiguity diagnostic ---


def _seed_save(root: Path, profile: str, save_name: str) -> Path:
    profile_dir = root / "SaveGames" / profile
    profile_dir.mkdir(parents=True, exist_ok=True)
    path = profile_dir / f"{save_name}.sav"
    path.write_bytes(b"data")
    return path.resolve()


def test_find_save_files_returns_single_match(tmp_path: Path) -> None:
    from satisfactory_active_save import find_save_files

    root = tmp_path / "FactoryGame" / "Saved"
    expected = _seed_save(root, "profileA", "Megatime")
    assert find_save_files(root, "Megatime") == [expected]


def test_find_save_files_returns_no_match(tmp_path: Path) -> None:
    from satisfactory_active_save import find_save_files

    root = tmp_path / "FactoryGame" / "Saved"
    (root / "SaveGames" / "profileA").mkdir(parents=True)
    assert find_save_files(root, "Nope") == []


def test_find_save_files_finds_both_layouts_and_sorts(tmp_path: Path) -> None:
    from satisfactory_active_save import find_save_files

    root = tmp_path / "FactoryGame" / "Saved"
    in_profile = _seed_save(root, "profileB", "Same")
    # A save placed directly under SaveGames (the second known layout).
    direct = root / "SaveGames" / "Same.sav"
    direct.write_bytes(b"data")
    direct = direct.resolve()

    matches = find_save_files(root, "Same")
    assert set(matches) == {in_profile, direct}
    # Deterministically sorted, independent of iteration order.
    assert matches == sorted(matches, key=str)


def test_resolve_ambiguous_save_does_not_pick_one(tmp_path: Path) -> None:
    root = tmp_path / "FactoryGame" / "Saved"
    logs = root / "Logs"
    logs.mkdir(parents=True)
    _seed_save(root, "76561190000000001", "Same")
    _seed_save(root, "76561190000000002", "Same")
    (logs / "FactoryGame.log").write_text(_load_line("Same", "Mallachi"), encoding="utf-8")

    result = resolve_active_save(configured_dir=str(root))
    assert result.status == STATUS_OK
    assert result.save_name == "Same"
    # The physical file is left unresolved rather than picking one arbitrarily.
    assert result.save_file is None
    assert result.save_file_found is False
    # A bounded diagnostic naming the profiles is exposed.
    assert result.save_file_ambiguity is not None
    assert "2 matching" in result.save_file_ambiguity
    assert "76561190000000001" in result.save_file_ambiguity
    assert "76561190000000002" in result.save_file_ambiguity


def test_resolve_single_match_sets_no_ambiguity(tmp_path: Path) -> None:
    root = tmp_path / "FactoryGame" / "Saved"
    logs = root / "Logs"
    logs.mkdir(parents=True)
    saved = _seed_save(root, "profileA", "Unique")
    (logs / "FactoryGame.log").write_text(_load_line("Unique", "Mallachi"), encoding="utf-8")

    result = resolve_active_save(configured_dir=str(root))
    assert result.status == STATUS_OK
    assert result.save_file == saved
    assert result.save_file_found is True
    assert result.save_file_ambiguity is None


def test_ambiguous_save_diagnostic_is_bounded(tmp_path: Path) -> None:
    from satisfactory_active_save import ambiguous_save_diagnostic

    matches = [
        tmp_path / f"profile{i}" / "Same.sav" for i in range(7)
    ]
    note = ambiguous_save_diagnostic(matches)
    assert note.startswith("7 matching .sav files under profiles:")
    # Caps the profile list and signals the remainder rather than dumping all 7.
    assert "(+3 more)" in note
    assert "profile5" not in note
