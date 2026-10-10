"""Tests for the per-save SQLite store foundation (satisfactory_store)."""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime
from pathlib import Path

import pytest

from satisfactory_store import (
    STORE_SCHEMA_VERSION,
    SaveStore,
    StoreError,
    import_jsonl,
)


NOW = datetime(2026, 6, 17, 15, 30, 12)


def _db_path(tmp_path: Path) -> Path:
    return tmp_path / "planning.sqlite3"


# --- Schema and version handling ---


def test_open_creates_current_schema(tmp_path: Path) -> None:
    with SaveStore.open(_db_path(tmp_path)) as store:
        tables = {
            row["name"]
            for row in store._conn.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            ).fetchall()
        }
        assert {"meta", "records", "import_sources"} <= tables
        version = store._conn.execute(
            "SELECT value FROM meta WHERE key = 'schema_version'"
        ).fetchone()["value"]
        assert int(version) == STORE_SCHEMA_VERSION == 2


def test_reopen_is_stable(tmp_path: Path) -> None:
    path = _db_path(tmp_path)
    with SaveStore.open(path) as store:
        store.add_record("todos", "todo_1", "First", "", "open", NOW)

    with SaveStore.open(path) as store:
        version = store._conn.execute(
            "SELECT value FROM meta WHERE key = 'schema_version'"
        ).fetchone()["value"]
        assert int(version) == STORE_SCHEMA_VERSION
        assert store.get_record("todo_1") is not None


def test_newer_schema_version_raises_store_error(tmp_path: Path) -> None:
    path = _db_path(tmp_path)
    with SaveStore.open(path):
        pass  # create the schema, then close.

    # Simulate a database written by a future, newer version of this module.
    conn = sqlite3.connect(str(path))
    conn.execute("UPDATE meta SET value = '99' WHERE key = 'schema_version'")
    conn.commit()
    conn.close()

    with pytest.raises(StoreError):
        SaveStore.open(path)


# --- CRUD ---


def test_add_and_get_record_round_trip_with_extra(tmp_path: Path) -> None:
    with SaveStore.open(_db_path(tmp_path)) as store:
        store.add_record(
            "flows",
            "flow_1",
            "Steel beam line",
            "player wording preserved",
            "planned",
            NOW,
            extra={
                "area": "Northern Forest",
                "recipe": "Steel Beam (Foundry)",
                "inputs": ["Iron Ore 240/min", "Coal 240/min"],
                "outputs": ["Steel Beam 360/min"],
            },
        )
        record = store.get_record("flow_1")
        assert record is not None
        assert record["title"] == "Steel beam line"
        assert record["details"] == "player wording preserved"
        assert record["status"] == "planned"
        assert record["area"] == "Northern Forest"
        assert record["recipe"] == "Steel Beam (Foundry)"
        assert record["inputs"] == ["Iron Ore 240/min", "Coal 240/min"]
        assert record["outputs"] == ["Steel Beam 360/min"]
        assert record["created_at"] == NOW.isoformat()
        assert record["updated_at"] == NOW.isoformat()


def test_get_record_missing_id_returns_none(tmp_path: Path) -> None:
    with SaveStore.open(_db_path(tmp_path)) as store:
        assert store.get_record("does_not_exist") is None


def test_add_record_unknown_kind_raises_before_write(tmp_path: Path) -> None:
    with SaveStore.open(_db_path(tmp_path)) as store:
        with pytest.raises(StoreError):
            store.add_record("widgets", "x_1", "Bad", "", "open", NOW)
        count = store._conn.execute("SELECT COUNT(*) AS n FROM records").fetchone()["n"]
        assert count == 0


def test_set_status_missing_id_returns_false(tmp_path: Path) -> None:
    with SaveStore.open(_db_path(tmp_path)) as store:
        assert store.set_status("todos", "todo_missing", "done", NOW) is False


def test_set_status_updates_matching_kind_and_id(tmp_path: Path) -> None:
    with SaveStore.open(_db_path(tmp_path)) as store:
        store.add_record("todos", "todo_1", "Build steel", "", "open", NOW)
        assert store.set_status("todos", "todo_1", "done", NOW) is True
        record = store.get_record("todo_1")
        assert record["status"] == "done"


def test_set_status_mismatched_kind_is_noop(tmp_path: Path) -> None:
    with SaveStore.open(_db_path(tmp_path)) as store:
        store.add_record("flows", "flow_1", "Steel line", "", "planned", NOW)
        assert store.set_status("todos", "flow_1", "archived", NOW) is False
        record = store.get_record("flow_1")
        assert record["status"] == "planned"


def test_set_status_unknown_kind_raises(tmp_path: Path) -> None:
    with SaveStore.open(_db_path(tmp_path)) as store:
        with pytest.raises(StoreError):
            store.set_status("widgets", "todo_1", "done", NOW)


def test_list_records_unknown_kind_raises(tmp_path: Path) -> None:
    with SaveStore.open(_db_path(tmp_path)) as store:
        with pytest.raises(StoreError):
            store.list_records("widgets")


# --- update_flow ---


def test_update_flow_changes_only_given_fields(tmp_path: Path) -> None:
    with SaveStore.open(_db_path(tmp_path)) as store:
        store.add_record(
            "flows", "flow_1", "Steel", "orig", "planned", NOW,
            extra={"inputs": ["a"], "outputs": ["b"]},
        )
        assert store.update_flow(
            "flow_1", NOW, status="building", outputs=["Steel Ingot 360/min"]
        ) is True
        record = store.get_record("flow_1")
        assert record["status"] == "building"
        assert record["outputs"] == ["Steel Ingot 360/min"]
        assert record["inputs"] == ["a"]  # unchanged


def test_update_flow_empty_metadata_leaves_unchanged(tmp_path: Path) -> None:
    with SaveStore.open(_db_path(tmp_path)) as store:
        store.add_record(
            "flows", "flow_1", "Line", "", "planned", NOW, extra={"area": "Keep"}
        )
        assert store.update_flow("flow_1", NOW, area="", recipe="") is True
        record = store.get_record("flow_1")
        assert record["area"] == "Keep"


def test_update_flow_clears_string_and_list_fields(tmp_path: Path) -> None:
    with SaveStore.open(_db_path(tmp_path)) as store:
        store.add_record(
            "flows", "flow_1", "Line", "orig details", "planned", NOW,
            extra={
                "area": "Northern Forest",
                "recipe": "Steel Beam (Foundry)",
                "machines": "Foundry x8",
                "constraints": "power<=200MW",
                "inputs": ["Iron Ore 240/min"],
                "outputs": ["Steel Beam 360/min"],
            },
        )
        assert store.update_flow(
            "flow_1",
            NOW,
            clear_fields={
                "area", "recipe", "machines", "constraints",
                "details", "inputs", "outputs",
            },
        ) is True
        record = store.get_record("flow_1")
        assert record["area"] == ""
        assert record["recipe"] == ""
        assert record["machines"] == ""
        assert record["constraints"] == ""
        assert record["details"] == ""
        assert record["inputs"] == []
        assert record["outputs"] == []


def test_update_flow_unknown_id_returns_false(tmp_path: Path) -> None:
    with SaveStore.open(_db_path(tmp_path)) as store:
        assert store.update_flow("flow_nope", NOW, status="done") is False


def test_update_flow_cannot_target_non_flow_record(tmp_path: Path) -> None:
    with SaveStore.open(_db_path(tmp_path)) as store:
        store.add_record("todos", "todo_1", "Build steel", "", "open", NOW)
        assert store.update_flow("todo_1", NOW, status="done") is False
        record = store.get_record("todo_1")
        assert record["status"] == "open"


# --- list_records ordering, filter, limit ---


def test_list_records_ordering_filter_and_limit(tmp_path: Path) -> None:
    with SaveStore.open(_db_path(tmp_path)) as store:
        early = datetime(2026, 6, 17, 10, 0, 0)
        mid = datetime(2026, 6, 17, 11, 0, 0)
        late = datetime(2026, 6, 17, 12, 0, 0)
        store.add_record("todos", "todo_a", "A", "", "open", early)
        store.add_record("todos", "todo_b", "B", "", "open", mid)
        store.add_record("todos", "todo_c", "C", "", "done", late)

        newest = store.list_records("todos")
        assert [r["id"] for r in newest] == ["todo_c", "todo_b", "todo_a"]

        oldest = store.list_records("todos", newest_first=False)
        assert [r["id"] for r in oldest] == ["todo_a", "todo_b", "todo_c"]

        open_only = store.list_records("todos", status="open")
        assert {r["id"] for r in open_only} == {"todo_a", "todo_b"}

        capped = store.list_records("todos", limit=2)
        assert len(capped) == 2
        assert [r["id"] for r in capped] == ["todo_c", "todo_b"]


def test_list_records_isolated_by_kind(tmp_path: Path) -> None:
    with SaveStore.open(_db_path(tmp_path)) as store:
        store.add_record("todos", "todo_1", "A todo", "", "open", NOW)
        store.add_record("goals", "goal_1", "A goal", "", "open", NOW)
        assert [r["id"] for r in store.list_records("todos")] == ["todo_1"]
        assert [r["id"] for r in store.list_records("goals")] == ["goal_1"]


# --- Transactionality ---


def test_check_violation_rolls_back_batch(tmp_path: Path) -> None:
    """A CHECK-violating statement mid-batch must leave zero rows committed."""
    with SaveStore.open(_db_path(tmp_path)) as store:
        with pytest.raises(sqlite3.IntegrityError):
            with store._conn:
                store._conn.execute(
                    "INSERT INTO records"
                    " (id, kind, title, details, status, created_at, updated_at, extra)"
                    " VALUES ('good_1', 'todos', 'Good', '', 'open', 'x', 'x', '{}')"
                )
                store._conn.execute(
                    "INSERT INTO records"
                    " (id, kind, title, details, status, created_at, updated_at, extra)"
                    " VALUES ('bad_1', 'bogus', 'Bad', '', 'open', 'x', 'x', '{}')"
                )
        assert store.get_record("good_1") is None
        assert store.get_record("bad_1") is None
        count = store._conn.execute("SELECT COUNT(*) AS n FROM records").fetchone()["n"]
        assert count == 0


# --- Import ---


def _write_jsonl(path: Path, lines: list[str]) -> None:
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def test_import_jsonl_first_import_counts_records_and_tolerates_junk(tmp_path: Path) -> None:
    todos_path = tmp_path / "todos.jsonl"
    _write_jsonl(
        todos_path,
        [
            json.dumps({"id": "todo_1", "title": "First", "status": "open"}),
            "not json {{{",
            "[]",
            json.dumps({"id": "todo_2", "title": "Second", "status": "open"}),
        ],
    )
    with SaveStore.open(_db_path(tmp_path)) as store:
        counts = import_jsonl(store, {"todos": todos_path})
        assert counts == {"todos": 2}
        assert store.get_record("todo_1") is not None
        assert store.get_record("todo_2") is not None
        assert store.list_records("todos")


def test_import_jsonl_second_import_is_noop(tmp_path: Path) -> None:
    todos_path = tmp_path / "todos.jsonl"
    _write_jsonl(todos_path, [json.dumps({"id": "todo_1", "title": "First", "status": "open"})])
    with SaveStore.open(_db_path(tmp_path)) as store:
        first = import_jsonl(store, {"todos": todos_path})
        assert first == {"todos": 1}
        second = import_jsonl(store, {"todos": todos_path})
        assert second == {"todos": 0}


def test_import_jsonl_modified_source_imports_only_new_ids(tmp_path: Path) -> None:
    todos_path = tmp_path / "todos.jsonl"
    _write_jsonl(
        todos_path,
        [json.dumps({"id": "todo_1", "title": "Original title", "status": "open"})],
    )
    with SaveStore.open(_db_path(tmp_path)) as store:
        import_jsonl(store, {"todos": todos_path})

        # Modify the source: change todo_1's title (should NOT overwrite the
        # store's copy) and add a brand new id (should be imported).
        _write_jsonl(
            todos_path,
            [
                json.dumps({"id": "todo_1", "title": "Changed title", "status": "open"}),
                json.dumps({"id": "todo_2", "title": "New todo", "status": "open"}),
            ],
        )
        counts = import_jsonl(store, {"todos": todos_path})
        assert counts == {"todos": 1}

        untouched = store.get_record("todo_1")
        assert untouched["title"] == "Original title"
        added = store.get_record("todo_2")
        assert added["title"] == "New todo"


def test_import_jsonl_duplicate_id_across_two_files_keeps_first(tmp_path: Path) -> None:
    todos_path = tmp_path / "todos.jsonl"
    goals_path = tmp_path / "goals.jsonl"
    _write_jsonl(todos_path, [json.dumps({"id": "dup_1", "title": "From todos", "status": "open"})])
    _write_jsonl(goals_path, [json.dumps({"id": "dup_1", "title": "From goals", "status": "open"})])
    with SaveStore.open(_db_path(tmp_path)) as store:
        counts = import_jsonl(store, {"todos": todos_path, "goals": goals_path})
        assert counts["todos"] == 1
        assert counts["goals"] == 0  # id already taken by the todos import
        record = store.get_record("dup_1")
        assert record["title"] == "From todos"


def test_import_jsonl_unknown_legacy_fields_land_in_extra(tmp_path: Path) -> None:
    todos_path = tmp_path / "todos.jsonl"
    _write_jsonl(
        todos_path,
        [json.dumps({"id": "todo_1", "title": "Legacy", "status": "open", "old_field": "keep me"})],
    )
    with SaveStore.open(_db_path(tmp_path)) as store:
        import_jsonl(store, {"todos": todos_path})
        record = store.get_record("todo_1")
        assert record["old_field"] == "keep me"


def test_import_jsonl_source_files_byte_identical_after_import(tmp_path: Path) -> None:
    todos_path = tmp_path / "todos.jsonl"
    _write_jsonl(todos_path, [json.dumps({"id": "todo_1", "title": "First", "status": "open"})])
    before = todos_path.read_bytes()
    with SaveStore.open(_db_path(tmp_path)) as store:
        import_jsonl(store, {"todos": todos_path})
    after = todos_path.read_bytes()
    assert before == after


def test_import_jsonl_missing_file_is_skipped(tmp_path: Path) -> None:
    with SaveStore.open(_db_path(tmp_path)) as store:
        counts = import_jsonl(store, {"todos": tmp_path / "does_not_exist.jsonl"})
        assert counts == {"todos": 0}


def test_import_jsonl_missing_timestamps_get_a_default(tmp_path: Path) -> None:
    todos_path = tmp_path / "todos.jsonl"
    _write_jsonl(todos_path, [json.dumps({"id": "todo_1", "title": "No timestamps", "status": "open"})])
    with SaveStore.open(_db_path(tmp_path)) as store:
        import_jsonl(store, {"todos": todos_path})
        record = store.get_record("todo_1")
        assert record["created_at"]
        assert record["updated_at"]


def test_import_jsonl_unknown_kind_raises(tmp_path: Path) -> None:
    todos_path = tmp_path / "todos.jsonl"
    _write_jsonl(todos_path, [json.dumps({"id": "todo_1", "title": "X", "status": "open"})])
    with SaveStore.open(_db_path(tmp_path)) as store:
        with pytest.raises(StoreError):
            import_jsonl(store, {"widgets": todos_path})
