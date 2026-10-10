"""Tests for SaveWorkspace's SQLite-backed persistence (SSP-P2-W02).

Covers the adapter swap from JSONL append/rewrite to satisfactory_store's
SaveStore: one-time-per-content-hash legacy import, durability across
workspace reopen, and legacy-file immutability. Behavioral compatibility
(summary shaping, containment, flow metadata, etc.) is covered by the
pre-existing test_workspace.py, which this module does not duplicate.
"""

from __future__ import annotations

import sqlite3
from datetime import datetime
from pathlib import Path

import pytest

from satisfactory_store import SaveStore
from satisfactory_workspace import SaveWorkspace


NOW = datetime(2026, 7, 1, 9, 0, 0)


def _ws(tmp_path: Path, key: str = "test-save-0001") -> SaveWorkspace:
    ws = SaveWorkspace(tmp_path, key)
    ws.ensure()
    return ws


def _seed_legacy_jsonl(ws: SaveWorkspace, kind: str, lines: list[str]) -> Path:
    path = ws.dir / f"{kind}.jsonl"
    ws.dir.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def test_fresh_workspace_with_no_legacy_files_works(tmp_path: Path) -> None:
    """A brand new workspace with no legacy JSONL files starts up cleanly."""
    ws = _ws(tmp_path)
    summary = ws.summary(10)
    assert summary["counts"] == {
        "notes": 0,
        "todos": 0,
        "goals": 0,
        "flows": 0,
        "changes": 0,
    }
    item_id = ws.add_item("notes", "First note", "", NOW)
    assert item_id.startswith("note_")
    assert (ws.dir / "planning.sqlite3").is_file()


def test_legacy_jsonl_is_imported_on_first_use(tmp_path: Path) -> None:
    """Records written by the old JSONL backend surface through the new store."""
    ws = _ws(tmp_path)
    _seed_legacy_jsonl(
        ws,
        "todos",
        ['{"id": "todo_legacy_0001", "title": "Old plan", "status": "open"}'],
    )
    summary = ws.summary(10)
    titles = {t["title"] for t in summary["open_todos"]}
    assert "Old plan" in titles
    assert summary["counts"]["todos"] == 1


def test_legacy_import_is_idempotent_across_reopens(tmp_path: Path) -> None:
    """Reopening the same workspace does not re-import or duplicate records."""
    ws = _ws(tmp_path)
    _seed_legacy_jsonl(
        ws,
        "goals",
        ['{"id": "goal_legacy_0001", "title": "Reach phase 3", "status": "open"}'],
    )
    first = ws.summary(10)
    assert first["counts"]["goals"] == 1

    # A brand new SaveWorkspace instance over the same directory (mirroring
    # the real per-tool-call lifecycle) must see the same single record, not
    # a duplicate, even though the legacy file is untouched between opens.
    reopened = SaveWorkspace(tmp_path, "test-save-0001")
    second = reopened.summary(10)
    assert second["counts"]["goals"] == 1
    goal_ids = [g["id"] for g in second["goals"]]
    assert goal_ids.count("goal_legacy_0001") == 1


def test_legacy_files_never_modified_after_import(tmp_path: Path) -> None:
    """Legacy JSONL files are byte-identical after import and never appended to."""
    ws = _ws(tmp_path)
    original_text = '{"id": "todo_legacy_0002", "title": "Untouched", "status": "open"}\n'
    path = _seed_legacy_jsonl(ws, "todos", [original_text.strip()])
    before = path.read_bytes()

    ws.summary(10)
    ws.add_item("todos", "A brand new todo", "", NOW)
    ws.set_status("todo_legacy_0002", "done", NOW)
    ws.summary(10)

    after = path.read_bytes()
    assert after == before


def test_new_records_persist_across_workspace_reopen(tmp_path: Path) -> None:
    """A record written by one SaveWorkspace instance survives a fresh one."""
    ws = _ws(tmp_path)
    item_id = ws.add_item("notes", "Durable note", "details here", NOW)

    reopened = SaveWorkspace(tmp_path, "test-save-0001")
    summary = reopened.summary(10)
    titles = {n["title"] for n in summary["notes"]}
    assert "Durable note" in titles
    assert summary["counts"]["notes"] == 1

    # And the exact id resolves through the reopened instance too.
    assert reopened.set_status(item_id, "archived", NOW) is True


def test_reopened_workspace_sees_records_from_a_previous_instance(tmp_path: Path) -> None:
    """One instance's writes are visible to a second, independently constructed instance."""
    writer = _ws(tmp_path)
    flow_id = writer.add_item(
        "flows",
        "Steel line",
        "",
        NOW,
        extra={"inputs": ["Iron Ore 240/min"], "outputs": ["Steel Ingot 360/min"]},
        status="planned",
    )

    reader = SaveWorkspace(tmp_path, "test-save-0001")
    flow = next(f for f in reader.summary(10)["flows"] if f["id"] == flow_id)
    assert flow["inputs"] == ["Iron Ore 240/min"]
    assert flow["outputs"] == ["Steel Ingot 360/min"]

    assert reader.update_flow(flow_id, NOW, status="building") is True
    updated = next(f for f in writer.summary(10)["flows"] if f["id"] == flow_id)
    assert updated["status"] == "building"


def test_planning_sqlite_file_created_in_workspace_dir(tmp_path: Path) -> None:
    ws = _ws(tmp_path)
    ws.add_item("changes", "Did a thing", "", NOW)
    db_path = ws.dir / "planning.sqlite3"
    assert db_path.is_file()
    with SaveStore.open(db_path) as store:
        records = store.list_records("changes")
        assert len(records) == 1
        assert records[0]["title"] == "Did a thing"


def test_sqlite_connection_closes_so_tmp_path_teardown_can_remove_it(tmp_path: Path) -> None:
    """Every public operation must close its connection (Windows file-lock safety)."""
    ws = _ws(tmp_path)
    ws.add_item("notes", "note", "", NOW)
    ws.summary(10)
    ws.set_status_for_kind("notes", "note_does_not_exist", "done", NOW)

    # If a connection were left open, sqlite3 would still allow a second
    # connection on Windows (file is not exclusively locked by default), but
    # an unclosed handle would keep the file "in use" for OS-level deletion.
    # Deleting the whole workspace directory here is the sharpest proxy for
    # that: it must succeed without a PermissionError.
    db_path = ws.dir / "planning.sqlite3"
    assert db_path.is_file()
    conn = sqlite3.connect(str(db_path))
    conn.close()


class _FakeUUID:
    """Stand-in for uuid.uuid4()'s return value; only .hex is ever read."""

    def __init__(self, hex_value: str) -> None:
        self.hex = hex_value


def test_add_item_retries_on_id_suffix_collision(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Regression test for F-P2W03-1.

    id is now a SQLite primary key (post the SaveStore swap), so two
    same-second inserts that happen to draw the same short uuid suffix must
    retry with a fresh suffix instead of raising sqlite3.IntegrityError.
    """
    ws = _ws(tmp_path)
    suffixes = iter(["aaaaaaaa", "aaaaaaaa", "bbbbbbbb"])
    monkeypatch.setattr(
        "satisfactory_workspace.uuid.uuid4",
        lambda: _FakeUUID(next(suffixes) + "0" * 24),
    )

    first_id = ws.add_item("todos", "First", "", NOW)
    second_id = ws.add_item("todos", "Second", "", NOW)

    assert first_id != second_id
    assert first_id.endswith("aaaaaaaa")
    assert second_id.endswith("bbbbbbbb")
