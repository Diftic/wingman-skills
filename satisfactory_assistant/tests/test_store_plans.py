"""Tests for schema v1-to-v2 migration and plan-model persistence.

The v1 fixture DDL below is copied verbatim from ``_SCHEMA_SQL`` as it stood
on disk at the v1 revision (SSP-P2-W01), before the v2 plan tables were
added in this work package. Building the v1 database with raw sqlite3 (not
by monkeypatching ``STORE_SCHEMA_VERSION``) is the only way to exercise a
genuine migration path rather than assume one works.
"""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime
from pathlib import Path

import pytest

from satisfactory_store import STORE_SCHEMA_VERSION, SaveStore, StoreError


NOW = datetime(2026, 7, 1, 12, 0, 0)

_V1_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS meta (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS records (
    id TEXT PRIMARY KEY,
    kind TEXT NOT NULL CHECK(kind IN ('notes', 'todos', 'goals', 'flows', 'changes')),
    title TEXT NOT NULL,
    details TEXT NOT NULL DEFAULT '',
    status TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    extra TEXT NOT NULL DEFAULT '{}'
);
CREATE TABLE IF NOT EXISTS import_sources (
    source_path TEXT PRIMARY KEY,
    sha256 TEXT NOT NULL,
    imported_at TEXT NOT NULL,
    record_count INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_records_kind_status ON records(kind, status);
CREATE INDEX IF NOT EXISTS idx_records_kind_created ON records(kind, created_at);
"""


def _db_path(tmp_path: Path) -> Path:
    return tmp_path / "planning.sqlite3"


def _build_v1_database(path: Path) -> None:
    """Create a genuine v1 database file with raw sqlite3 and the v1 DDL."""
    conn = sqlite3.connect(str(path))
    try:
        conn.executescript(_V1_SCHEMA_SQL)
        conn.execute(
            "INSERT INTO meta (key, value) VALUES ('schema_version', '1')"
        )
        conn.execute(
            "INSERT INTO meta (key, value) VALUES ('created_at', ?)",
            (NOW.isoformat(),),
        )
        conn.execute(
            "INSERT INTO records"
            " (id, kind, title, details, status, created_at, updated_at, extra)"
            " VALUES ('todo_1', 'todos', 'Build steel line', '', 'open', ?, ?, '{}')",
            (NOW.isoformat(), NOW.isoformat()),
        )
        conn.execute(
            "INSERT INTO records"
            " (id, kind, title, details, status, created_at, updated_at, extra)"
            " VALUES ('note_1', 'notes', 'Remember alt recipe', 'details here', 'open', ?, ?, '{}')",
            (NOW.isoformat(), NOW.isoformat()),
        )
        conn.commit()
    finally:
        conn.close()


# --- Migration ---


def test_v1_database_migrates_to_v2_and_keeps_journal_records(tmp_path: Path) -> None:
    path = _db_path(tmp_path)
    _build_v1_database(path)

    with SaveStore.open(path) as store:
        version = store._conn.execute(
            "SELECT value FROM meta WHERE key = 'schema_version'"
        ).fetchone()["value"]
        assert int(version) == 2 == STORE_SCHEMA_VERSION

        todo = store.get_record("todo_1")
        assert todo is not None
        assert todo["title"] == "Build steel line"
        note = store.get_record("note_1")
        assert note is not None
        assert note["details"] == "details here"

        tables = {
            row["name"]
            for row in store._conn.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            ).fetchall()
        }
        assert {"master_plans", "stage_plans", "solver_runs"} <= tables


def test_migrated_database_plan_tables_are_usable(tmp_path: Path) -> None:
    path = _db_path(tmp_path)
    _build_v1_database(path)

    with SaveStore.open(path) as store:
        store.upsert_master_plan(
            {
                "plan_id": "plan_1",
                "name": "Phase 2 assembly",
                "created_at": NOW.isoformat(),
                "updated_at": NOW.isoformat(),
            }
        )
        revision = store.save_stage_plan("plan_1", {"phase": 2, "nodes": []}, 2, NOW)
        assert revision == 1
        loaded = store.load_stage_plan("plan_1", 2)
        assert loaded is not None
        assert loaded["nodes"] == []


# --- Revision sequencing ---


def test_save_stage_plan_assigns_sequential_revisions(tmp_path: Path) -> None:
    with SaveStore.open(_db_path(tmp_path)) as store:
        store.upsert_master_plan(
            {
                "plan_id": "plan_1",
                "name": "Plan",
                "created_at": NOW.isoformat(),
                "updated_at": NOW.isoformat(),
            }
        )
        first = store.save_stage_plan("plan_1", {"note": "first solve"}, 2, NOW)
        second = store.save_stage_plan("plan_1", {"note": "second solve"}, 2, NOW)
        assert first == 1
        assert second == 2
        assert store.list_stage_revisions("plan_1", 2) == [1, 2]


def test_save_stage_plan_stamps_raw_payload_metadata(tmp_path: Path) -> None:
    with SaveStore.open(_db_path(tmp_path)) as store:
        store.upsert_master_plan(
            {
                "plan_id": "plan_1",
                "name": "Plan",
                "created_at": NOW.isoformat(),
                "updated_at": NOW.isoformat(),
            }
        )
        revision = store.save_stage_plan(
            "plan_1",
            {
                "phase": 0,
                "revision": 0,
                "created_at": "stale",
                "solver_run_id": "run_2_1_test",
            },
            2,
            NOW,
        )

        row = store._conn.execute(
            "SELECT payload FROM stage_plans WHERE plan_id = ? AND phase = ? AND revision = ?",
            ("plan_1", 2, revision),
        ).fetchone()
        payload = json.loads(row["payload"])
        assert payload["phase"] == 2
        assert payload["revision"] == 1
        assert payload["created_at"] == NOW.isoformat()
        assert payload["solver_run_id"] == "run_2_1_test"


def test_load_stage_plan_defaults_to_latest_revision(tmp_path: Path) -> None:
    with SaveStore.open(_db_path(tmp_path)) as store:
        store.upsert_master_plan(
            {
                "plan_id": "plan_1",
                "name": "Plan",
                "created_at": NOW.isoformat(),
                "updated_at": NOW.isoformat(),
            }
        )
        store.save_stage_plan("plan_1", {"note": "first solve"}, 2, NOW)
        store.save_stage_plan("plan_1", {"note": "second solve"}, 2, NOW)

        latest = store.load_stage_plan("plan_1", 2)
        assert latest is not None
        assert latest["note"] == "second solve"
        assert latest["revision"] == 2


def test_load_stage_plan_explicit_revision_loads_exactly_that_one(tmp_path: Path) -> None:
    with SaveStore.open(_db_path(tmp_path)) as store:
        store.upsert_master_plan(
            {
                "plan_id": "plan_1",
                "name": "Plan",
                "created_at": NOW.isoformat(),
                "updated_at": NOW.isoformat(),
            }
        )
        store.save_stage_plan("plan_1", {"note": "first solve"}, 2, NOW)
        store.save_stage_plan("plan_1", {"note": "second solve"}, 2, NOW)

        first = store.load_stage_plan("plan_1", 2, revision=1)
        assert first is not None
        assert first["note"] == "first solve"
        assert first["revision"] == 1


def test_load_stage_plan_missing_returns_none(tmp_path: Path) -> None:
    with SaveStore.open(_db_path(tmp_path)) as store:
        assert store.load_stage_plan("plan_missing", 2) is None


def test_save_stage_plan_revisions_are_independent_per_phase(tmp_path: Path) -> None:
    with SaveStore.open(_db_path(tmp_path)) as store:
        store.upsert_master_plan(
            {
                "plan_id": "plan_1",
                "name": "Plan",
                "created_at": NOW.isoformat(),
                "updated_at": NOW.isoformat(),
            }
        )
        phase2_rev = store.save_stage_plan("plan_1", {"note": "phase 2"}, 2, NOW)
        phase3_rev = store.save_stage_plan("plan_1", {"note": "phase 3"}, 3, NOW)
        assert phase2_rev == 1
        assert phase3_rev == 1


# --- Solver run immutability ---


def test_record_solver_run_duplicate_run_id_raises(tmp_path: Path) -> None:
    with SaveStore.open(_db_path(tmp_path)) as store:
        store.record_solver_run("run_1", "plan_1", 2, "ok", {"note": "first"}, NOW)
        with pytest.raises(StoreError):
            store.record_solver_run("run_1", "plan_1", 2, "ok", {"note": "second"}, NOW)

        run = store.get_solver_run("run_1")
        assert run is not None
        assert run["note"] == "first"


def test_get_solver_run_missing_returns_none(tmp_path: Path) -> None:
    with SaveStore.open(_db_path(tmp_path)) as store:
        assert store.get_solver_run("run_missing") is None


def test_solver_runs_have_no_update_or_delete_method() -> None:
    assert not hasattr(SaveStore, "update_solver_run")
    assert not hasattr(SaveStore, "delete_solver_run")


# --- Foreign key enforcement ---


def test_save_stage_plan_unknown_plan_id_fails(tmp_path: Path) -> None:
    with SaveStore.open(_db_path(tmp_path)) as store:
        with pytest.raises(sqlite3.IntegrityError):
            store.save_stage_plan("plan_does_not_exist", {"note": "x"}, 2, NOW)


# --- Master plan upsert ---


def test_upsert_master_plan_updates_name_and_updated_at_but_keeps_created_at(
    tmp_path: Path,
) -> None:
    with SaveStore.open(_db_path(tmp_path)) as store:
        store.upsert_master_plan(
            {
                "plan_id": "plan_1",
                "name": "Original name",
                "created_at": NOW.isoformat(),
                "updated_at": NOW.isoformat(),
            }
        )
        later = datetime(2026, 7, 2, 9, 0, 0)
        store.upsert_master_plan(
            {
                "plan_id": "plan_1",
                "name": "Renamed",
                "created_at": later.isoformat(),
                "updated_at": later.isoformat(),
            }
        )
        plan = store.get_master_plan("plan_1")
        assert plan is not None
        assert plan["name"] == "Renamed"
        assert plan["updated_at"] == later.isoformat()
        assert plan["created_at"] == NOW.isoformat()


def test_get_master_plan_missing_returns_none(tmp_path: Path) -> None:
    with SaveStore.open(_db_path(tmp_path)) as store:
        assert store.get_master_plan("plan_missing") is None


# --- Payload round trip through the store ---


def test_stage_plan_payload_round_trips_through_store(tmp_path: Path) -> None:
    payload = {
        "window_hours": 12.0,
        "pace_multiplier": 1.5,
        "demands": [["Desc_IronPlate_C", 100.0, 8.33]],
        "nodes": [{"node_id": "node_1", "machine_count": 3}],
        "assumptions": ["Base tiers only"],
    }
    with SaveStore.open(_db_path(tmp_path)) as store:
        store.upsert_master_plan(
            {
                "plan_id": "plan_1",
                "name": "Plan",
                "created_at": NOW.isoformat(),
                "updated_at": NOW.isoformat(),
            }
        )
        store.save_stage_plan("plan_1", payload, 2, NOW)
        loaded = store.load_stage_plan("plan_1", 2)
        assert loaded is not None
        for key, value in payload.items():
            assert loaded[key] == value


def test_solver_run_payload_round_trips_through_store(tmp_path: Path) -> None:
    payload = {"objective_value": 42.5, "diagnostics": [{"severity": "info", "code": "ok"}]}
    with SaveStore.open(_db_path(tmp_path)) as store:
        store.record_solver_run("run_1", "plan_1", 2, "ok", payload, NOW)
        loaded = store.get_solver_run("run_1")
        assert loaded is not None
        for key, value in payload.items():
            assert loaded[key] == value
        assert loaded["status"] == "ok"
        assert loaded["plan_id"] == "plan_1"
        assert loaded["phase"] == 2
