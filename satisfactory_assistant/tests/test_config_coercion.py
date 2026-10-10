"""Tests for defensive config coercion helpers in main.py.

main.py imports the Wingman app (api.*, skills.skill_base), so the repo root
must be importable. The test skips gracefully if those modules are unavailable.
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[3]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

main = pytest.importorskip("skills.satisfactory_assistant.main")

from satisfactory_models import ActiveSaveResult  # noqa: E402
from satisfactory_workspace import SaveWorkspace  # noqa: E402


class _WorkspaceStub:
    """Minimal stand-in exposing only what ``_workspace_for`` reads."""

    def __init__(self, base: Path) -> None:
        self._base = base

    def get_generated_files_dir(self) -> str:
        return str(self._base)


def test_coerce_int_handles_valid_and_invalid() -> None:
    assert main._coerce_int(2048, default=10, minimum=1) == 2048
    assert main._coerce_int("2048", default=10, minimum=1) == 2048
    assert main._coerce_int(None, default=10, minimum=1) == 10
    assert main._coerce_int("not-a-number", default=10, minimum=1) == 10


def test_coerce_int_clamps_to_minimum() -> None:
    assert main._coerce_int(0, default=10, minimum=4096) == 4096
    assert main._coerce_int(-5, default=10, minimum=1) == 1


def test_coerce_bool_parses_strings_explicitly() -> None:
    assert main._coerce_bool(True, default=False) is True
    assert main._coerce_bool(False, default=True) is False
    # The bug this guards against: bool("false") is True.
    assert main._coerce_bool("false", default=True) is False
    assert main._coerce_bool("False", default=True) is False
    assert main._coerce_bool("true", default=False) is True
    assert main._coerce_bool("", default=True) is False
    assert main._coerce_bool(None, default=True) is True
    assert main._coerce_bool("weird", default=True) is True


# --- SSP-P0-W02: record-type safe status action gating ---


def test_complete_todo_only_accepts_todo_ids() -> None:
    kind, error = main._resolve_status_target("complete_todo", "todo_20260617_120000_ab12")
    assert kind == "todos"
    assert error is None

    for bad in ("note_x", "goal_x", "flow_x", "chg_x", "bogus_x", ""):
        kind, error = main._resolve_status_target("complete_todo", bad)
        assert kind is None
        assert error  # concise non-empty message


def test_archive_item_infers_kind_and_rejects_audit_and_unknown() -> None:
    assert main._resolve_status_target("archive_item", "note_x") == ("notes", None)
    assert main._resolve_status_target("archive_item", "todo_x") == ("todos", None)
    assert main._resolve_status_target("archive_item", "goal_x") == ("goals", None)
    assert main._resolve_status_target("archive_item", "flow_x") == ("flows", None)

    for bad in ("chg_x", "bogus_x", ""):
        kind, error = main._resolve_status_target("archive_item", bad)
        assert kind is None
        assert error


# --- SSP-P0-W03: stable workspace identity ---


def _workspace_for(base: Path, result: ActiveSaveResult):
    # Call the real method bound to a lightweight stub; it only reads
    # get_generated_files_dir(), so no full Skill instance is needed.
    return main.SatisfactoryAssistant._workspace_for(_WorkspaceStub(base), result)


def test_workspace_identity_stable_across_save_file_state(tmp_path: Path) -> None:
    """Missing-save and found-save results for one logical save share a dir."""
    root = tmp_path / "FactoryGame" / "Saved"
    missing = ActiveSaveResult(
        status="ok", save_name="Megatime", save_file=None, save_file_found=False, root=root
    )
    found = ActiveSaveResult(
        status="ok",
        save_name="Megatime",
        save_file=root / "SaveGames" / "76561198000000000" / "Megatime.sav",
        save_file_found=True,
        root=root,
    )
    ws_missing = _workspace_for(tmp_path, missing)
    ws_found = _workspace_for(tmp_path, found)
    assert ws_missing.dir == ws_found.dir


def test_workspace_identity_disambiguates_saves(tmp_path: Path) -> None:
    root = tmp_path / "FactoryGame" / "Saved"
    a = ActiveSaveResult(status="ok", save_name="Save A", save_file=None, root=root)
    b = ActiveSaveResult(status="ok", save_name="Save B", save_file=None, root=root)
    other_root = tmp_path / "Other" / "Saved"
    c = ActiveSaveResult(status="ok", save_name="Save A", save_file=None, root=other_root)
    dirs = {_workspace_for(tmp_path, r).dir for r in (a, b, c)}
    assert len(dirs) == 3


def test_workspace_adopts_legacy_path_hash_workspace(tmp_path: Path) -> None:
    """A found save adopts records from its pre-fix path-hash workspace."""
    root = tmp_path / "FactoryGame" / "Saved"
    save_file = root / "SaveGames" / "profile" / "Megatime.sav"
    found = ActiveSaveResult(
        status="ok",
        save_name="Megatime",
        save_file=save_file,
        save_file_found=True,
        root=root,
    )
    # Seed the legacy workspace keyed on the volatile .sav path.
    legacy_key = main.safe_save_key("Megatime", str(save_file))
    legacy_dir = tmp_path / "saves" / legacy_key
    legacy_dir.mkdir(parents=True)
    (legacy_dir / "todos.jsonl").write_text(
        '{"id": "todo_legacy_0001", "title": "Pre-fix plan", "status": "open"}\n',
        encoding="utf-8",
    )

    ws = _workspace_for(tmp_path, found)
    assert ws.dir != legacy_dir  # stable key differs from the path hash
    adopted = (ws.dir / "todos.jsonl").read_text(encoding="utf-8")
    assert "Pre-fix plan" in adopted
    # Legacy directory is never deleted.
    assert (legacy_dir / "todos.jsonl").is_file()


# --- SSP-P0-W05: same-name save ambiguity diagnostic ---


def test_workspace_identity_stable_across_ambiguous_state(tmp_path: Path) -> None:
    """Missing, found, and ambiguous results for one save share a directory."""
    root = tmp_path / "FactoryGame" / "Saved"
    common = dict(status="ok", save_name="Megatime", root=root)
    missing = ActiveSaveResult(save_file=None, save_file_found=False, **common)
    found = ActiveSaveResult(
        save_file=root / "SaveGames" / "p1" / "Megatime.sav",
        save_file_found=True,
        **common,
    )
    ambiguous = ActiveSaveResult(
        save_file=None,
        save_file_found=False,
        save_file_ambiguity="2 matching .sav files under profiles: p1, p2",
        **common,
    )
    dirs = {_workspace_for(tmp_path, r).dir for r in (missing, found, ambiguous)}
    assert len(dirs) == 1


def test_save_file_note_prefers_ambiguity_over_not_found() -> None:
    ambiguous = ActiveSaveResult(
        status="ok",
        save_name="Same",
        save_file=None,
        save_file_found=False,
        save_file_ambiguity="2 matching .sav files under profiles: p1, p2",
    )
    note = main._save_file_note(ambiguous)
    assert note is not None
    assert "ambiguous save file" in note
    assert "p1, p2" in note
    assert "active-log save name only" in note
    # Bounded: a single short line.
    assert "\n" not in note
    assert len(note) <= 200


def test_save_file_note_not_found_when_no_ambiguity() -> None:
    missing = ActiveSaveResult(
        status="ok", save_name="Ghost", save_file=None, save_file_found=False
    )
    assert main._save_file_note(missing) == (
        "(save file not found on disk; planning still available)"
    )


def test_save_file_note_none_when_resolved() -> None:
    found = ActiveSaveResult(
        status="ok",
        save_name="Unique",
        save_file=Path("/games/Saved/SaveGames/p1/Unique.sav"),
        save_file_found=True,
    )
    assert main._save_file_note(found) is None


class _PlanAssistantStub:
    """Minimal stand-in exposing what ``update_satisfactory_plan`` reads."""

    def __init__(self, base: Path) -> None:
        self.workspace = SaveWorkspace(base, "test-save")

    def _allow_plan_writes(self) -> bool:
        return True

    def _resolve(self) -> ActiveSaveResult:
        return ActiveSaveResult(status="ok", save_name="Test Save", save_file=None)

    def _status_message(self, result: ActiveSaveResult) -> str:
        return ""

    def _workspace_for(self, result: ActiveSaveResult) -> SaveWorkspace:
        return self.workspace


def test_update_satisfactory_plan_accepts_output_rate_alias(tmp_path: Path) -> None:
    assistant = _PlanAssistantStub(tmp_path)

    result = asyncio.run(
        main.SatisfactoryAssistant.update_satisfactory_plan(
            assistant,
            action="add_flow",
            title="Copper Ingots",
            outputs="Copper Ingots",
            output_rate="per minute",
        )
    )

    assert result.startswith("Added production flow 'Copper Ingots'")
    flow = assistant.workspace._read("flows")[0]
    assert flow["outputs"] == ["Copper Ingots per minute"]
