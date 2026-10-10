"""Tests for database.py against the surface-only schema v2.

These assert the SPEC (navpoint-pivot-spec.md section 1): schema v2 with a
required `body` column replacing planet/moon, a wipe-on-upgrade path for
pre-v2 databases, and body-aware read/write helpers.
"""

from __future__ import annotations

import inspect
import logging
import sqlite3
from pathlib import Path

import pytest

from database import NavPointDatabase


# ---------------------------------------------------------------------- #
# Helpers
# ---------------------------------------------------------------------- #


OLD_SCHEMA = """
CREATE TABLE navpoints (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    name        TEXT    NOT NULL,
    server_id   TEXT    NOT NULL DEFAULT '',
    x           REAL    NOT NULL DEFAULT 0,
    y           REAL    NOT NULL DEFAULT 0,
    z           REAL    NOT NULL DEFAULT 0,
    planet      TEXT    NOT NULL DEFAULT '',
    moon        TEXT    NOT NULL DEFAULT '',
    system      TEXT    NOT NULL DEFAULT '',
    zone        TEXT    NOT NULL DEFAULT '',
    heading     REAL    NOT NULL DEFAULT 0,
    timestamp   TEXT    NOT NULL,
    notes       TEXT    NOT NULL DEFAULT ''
);
"""


def _db_file(db_dir: Path) -> Path:
    return db_dir / "navpoints.db"


def _column_names(db_file: Path) -> set[str]:
    conn = sqlite3.connect(str(db_file))
    try:
        rows = conn.execute("PRAGMA table_info(navpoints)").fetchall()
    finally:
        conn.close()
    return {r[1] for r in rows}


def _user_version(db_file: Path) -> int:
    conn = sqlite3.connect(str(db_file))
    try:
        return conn.execute("PRAGMA user_version").fetchone()[0]
    finally:
        conn.close()


def _write_pre_v2_db(db_dir: Path) -> None:
    """Create a pre-v2 (user_version 0) navpoints.db with the OLD schema and a row."""
    db_file = _db_file(db_dir)
    db_dir.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_file))
    try:
        conn.executescript(OLD_SCHEMA)
        conn.execute(
            """INSERT INTO navpoints
               (name, server_id, x, y, z, planet, moon, system, zone, heading, timestamp, notes)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                "StaleStellar",
                "srv-legacy",
                1.0,
                2.0,
                3.0,
                "Crusader",
                "",
                "Stanton",
                "space",
                0.0,
                "2026-01-01T00:00:00",
                "pre-4.7 stellar waypoint",
            ),
        )
        conn.execute("PRAGMA user_version = 0")
        conn.commit()
    finally:
        conn.close()


# ---------------------------------------------------------------------- #
# Fresh init
# ---------------------------------------------------------------------- #


def test_fresh_init_creates_schema_v4(tmp_path: Path) -> None:
    NavPointDatabase(str(tmp_path))
    db_file = _db_file(tmp_path)
    assert _user_version(db_file) == 4
    cols = _column_names(db_file)
    assert "body" in cols
    assert "planet" not in cols
    assert "moon" not in cols
    # v3 adds the frame discriminator for space waypoints.
    assert "frame" in cols
    assert "frame_id" in cols
    # v4 adds the coordinate stack: Root as the long-range address, the
    # whole accepted capture beside it, and a discriminator that keeps
    # legacy rows legible as legacy.
    assert "coordinate_schema" in cols
    assert {"root_x", "root_y", "root_z"} <= cols
    assert "coordinate_stack" in cols


def test_fresh_init_logs_no_wipe_warning(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    with caplog.at_level(logging.WARNING):
        NavPointDatabase(str(tmp_path))
    warnings = [r for r in caplog.records if r.levelno >= logging.WARNING]
    assert warnings == []


# ---------------------------------------------------------------------- #
# Pre-v2 wipe-on-upgrade
# ---------------------------------------------------------------------- #


def test_pre_v2_db_is_wiped(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    _write_pre_v2_db(tmp_path)
    db_file = _db_file(tmp_path)
    # Sanity: the hand-built DB really is the old shape before init runs.
    assert _user_version(db_file) == 0
    assert "planet" in _column_names(db_file)

    with caplog.at_level(logging.WARNING):
        db = NavPointDatabase(str(tmp_path))

    # Table recreated with the new schema.
    cols = _column_names(db_file)
    assert "body" in cols
    assert "planet" not in cols
    assert "moon" not in cols
    # user_version bumped to the current schema.
    assert _user_version(db_file) == 4
    # Old rows gone.
    assert db.count_navpoints() == 0
    # A WARNING was logged about the wipe.
    warnings = [r for r in caplog.records if r.levelno >= logging.WARNING]
    assert warnings, "expected a WARNING when a non-empty pre-v2 table is wiped"


# ---------------------------------------------------------------------- #
# add_navpoint: body required
# ---------------------------------------------------------------------- #


def test_add_navpoint_rejects_empty_body(tmp_path: Path) -> None:
    db = NavPointDatabase(str(tmp_path))
    with pytest.raises(ValueError):
        db.add_navpoint("wp", "srv1", "", 1.0, 2.0, 3.0)


def test_add_navpoint_rejects_whitespace_body(tmp_path: Path) -> None:
    db = NavPointDatabase(str(tmp_path))
    with pytest.raises(ValueError):
        db.add_navpoint("wp", "srv1", "   ", 1.0, 2.0, 3.0)


def test_add_navpoint_roundtrip_stores_body(tmp_path: Path) -> None:
    db = NavPointDatabase(str(tmp_path))
    np = db.add_navpoint("Cave", "srv1", "Daymar", 10.0, 20.0, 30.0)
    assert np.body == "Daymar"
    fetched = db.find_navpoint_by_id(np.id)
    assert fetched is not None
    assert fetched.body == "Daymar"
    assert (fetched.x, fetched.y, fetched.z) == (10.0, 20.0, 30.0)


# ---------------------------------------------------------------------- #
# get_navpoints filters
# ---------------------------------------------------------------------- #


def _seed(db: NavPointDatabase) -> None:
    db.add_navpoint("A", "srvA", "Daymar", 1.0, 1.0, 1.0)
    db.add_navpoint("B", "srvA", "Cellin", 2.0, 2.0, 2.0)
    db.add_navpoint("C", "srvB", "Daymar", 3.0, 3.0, 3.0)


def test_get_navpoints_no_filter_returns_all(tmp_path: Path) -> None:
    db = NavPointDatabase(str(tmp_path))
    _seed(db)
    assert len(db.get_navpoints()) == 3


def test_get_navpoints_filter_by_body_case_insensitive(tmp_path: Path) -> None:
    db = NavPointDatabase(str(tmp_path))
    _seed(db)
    result = db.get_navpoints(body="daymar")
    assert {np.name for np in result} == {"A", "C"}


def test_get_navpoints_has_no_server_id_param() -> None:
    # Spec B3: server_id is no longer a filter dimension; the parameter is gone.
    # body stays as the one surviving filter.
    params = inspect.signature(NavPointDatabase.get_navpoints).parameters
    assert "server_id" not in params
    assert "body" in params


# ---------------------------------------------------------------------- #
# distinct helpers
# ---------------------------------------------------------------------- #


def test_get_distinct_bodies(tmp_path: Path) -> None:
    db = NavPointDatabase(str(tmp_path))
    _seed(db)
    assert db.get_distinct_bodies() == ["Cellin", "Daymar"]


def test_get_distinct_servers_removed() -> None:
    # Spec B1: get_distinct_servers is dead once server filtering goes (B3).
    assert not hasattr(NavPointDatabase, "get_distinct_servers")


# ---------------------------------------------------------------------- #
# serialisation
# ---------------------------------------------------------------------- #


def test_navpoint_to_dict_has_body_no_planet_moon(tmp_path: Path) -> None:
    db = NavPointDatabase(str(tmp_path))
    np = db.add_navpoint("Wreck", "srv1", "Yela", 5.0, 6.0, 7.0)
    d = NavPointDatabase.navpoint_to_dict(np)
    assert d["body"] == "Yela"
    assert "planet" not in d
    assert "moon" not in d


# ---------------------------------------------------------------------- #
# other operations on the new schema
# ---------------------------------------------------------------------- #


def test_delete_navpoint(tmp_path: Path) -> None:
    db = NavPointDatabase(str(tmp_path))
    np = db.add_navpoint("Temp", "srv1", "Daymar", 1.0, 2.0, 3.0)
    db.delete_navpoint(np.id)
    assert db.find_navpoint_by_id(np.id) is None
    assert db.count_navpoints() == 0


def test_rename_navpoint(tmp_path: Path) -> None:
    db = NavPointDatabase(str(tmp_path))
    np = db.add_navpoint("OldName", "srv1", "Daymar", 1.0, 2.0, 3.0)
    db.rename_navpoint(np.id, "NewName")
    fetched = db.find_navpoint_by_id(np.id)
    assert fetched is not None
    assert fetched.name == "NewName"


def test_update_notes(tmp_path: Path) -> None:
    db = NavPointDatabase(str(tmp_path))
    np = db.add_navpoint("Note", "srv1", "Daymar", 1.0, 2.0, 3.0)
    db.update_notes(np.id, "watch for rocks")
    fetched = db.find_navpoint_by_id(np.id)
    assert fetched is not None
    assert fetched.notes == "watch for rocks"


def test_find_navpoint_by_name_case_insensitive(tmp_path: Path) -> None:
    db = NavPointDatabase(str(tmp_path))
    db.add_navpoint("HiddenCache", "srv1", "Daymar", 1.0, 2.0, 3.0)
    fetched = db.find_navpoint_by_name("hiddencache")
    assert fetched is not None
    assert fetched.name == "HiddenCache"


def test_find_navpoint_by_id(tmp_path: Path) -> None:
    db = NavPointDatabase(str(tmp_path))
    np = db.add_navpoint("ById", "srv1", "Daymar", 1.0, 2.0, 3.0)
    fetched = db.find_navpoint_by_id(np.id)
    assert fetched is not None
    assert fetched.id == np.id


def test_search_navpoints(tmp_path: Path) -> None:
    db = NavPointDatabase(str(tmp_path))
    db.add_navpoint("AlphaBase", "srv1", "Daymar", 1.0, 2.0, 3.0)
    db.add_navpoint("BetaSite", "srv1", "Cellin", 4.0, 5.0, 6.0)
    result = db.search_navpoints("alpha")
    assert {np.name for np in result} == {"AlphaBase"}


def test_count_navpoints(tmp_path: Path) -> None:
    db = NavPointDatabase(str(tmp_path))
    assert db.count_navpoints() == 0
    _seed(db)
    assert db.count_navpoints() == 3


# ---------------------------------------------------------------------- #
# wipe_on_server_change (spec Item B1)
# ---------------------------------------------------------------------- #
#
# Contract:
#   - empty/whitespace current_server_id  -> 0 (OCR-garble fail-safe; an
#     unreadable server line must never wipe).
#   - a proven change is a row with a NON-EMPTY server_id different from the
#     current one; that wipes ALL rows (empty-server rows included) and returns
#     the deleted count.
#   - otherwise 0.


def test_wipe_empty_current_returns_zero(tmp_path: Path) -> None:
    db = NavPointDatabase(str(tmp_path))
    db.add_navpoint("A", "srvA", "Daymar", 1.0, 1.0, 1.0)
    assert db.wipe_on_server_change("") == 0
    assert db.count_navpoints() == 1


def test_wipe_whitespace_current_returns_zero(tmp_path: Path) -> None:
    db = NavPointDatabase(str(tmp_path))
    db.add_navpoint("A", "srvA", "Daymar", 1.0, 1.0, 1.0)
    assert db.wipe_on_server_change("   ") == 0
    assert db.count_navpoints() == 1


def test_wipe_no_rows_returns_zero(tmp_path: Path) -> None:
    db = NavPointDatabase(str(tmp_path))
    assert db.wipe_on_server_change("srvA") == 0


def test_wipe_all_same_server_returns_zero(tmp_path: Path) -> None:
    db = NavPointDatabase(str(tmp_path))
    db.add_navpoint("A", "srvA", "Daymar", 1.0, 1.0, 1.0)
    db.add_navpoint("B", "srvA", "Cellin", 2.0, 2.0, 2.0)
    assert db.wipe_on_server_change("srvA") == 0
    assert db.count_navpoints() == 2


def test_wipe_differing_server_deletes_all_including_empty(tmp_path: Path) -> None:
    db = NavPointDatabase(str(tmp_path))
    db.add_navpoint("A", "srvA", "Daymar", 1.0, 1.0, 1.0)
    db.add_navpoint("B", "srvA", "Cellin", 2.0, 2.0, 2.0)
    # An empty-server row is stale too once a proven change is seen.
    db.add_navpoint("C", "", "Yela", 3.0, 3.0, 3.0)
    deleted = db.wipe_on_server_change("srvB")
    assert deleted == 3
    assert db.count_navpoints() == 0


def test_wipe_empty_server_rows_only_no_proof(tmp_path: Path) -> None:
    db = NavPointDatabase(str(tmp_path))
    db.add_navpoint("A", "", "Daymar", 1.0, 1.0, 1.0)
    db.add_navpoint("B", "", "Cellin", 2.0, 2.0, 2.0)
    # No NON-EMPTY server_id differs, so there is no proof of a change.
    assert db.wipe_on_server_change("srvB") == 0
    assert db.count_navpoints() == 2


# ---------------------------------------------------------------------- #
# v2 -> v3: additive, and existing waypoints MUST survive
# ---------------------------------------------------------------------- #


def _write_v2_db_with_rows(db_dir: Path, rows: int = 3) -> None:
    """Build a real schema-v2 database holding surface waypoints."""
    db_file = _db_file(db_dir)
    db_dir.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_file))
    conn.executescript(
        """
        CREATE TABLE navpoints (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            server_id TEXT NOT NULL DEFAULT '',
            x REAL NOT NULL DEFAULT 0,
            y REAL NOT NULL DEFAULT 0,
            z REAL NOT NULL DEFAULT 0,
            body TEXT NOT NULL,
            system TEXT NOT NULL DEFAULT '',
            zone TEXT NOT NULL DEFAULT '',
            heading REAL NOT NULL DEFAULT 0,
            timestamp TEXT NOT NULL,
            notes TEXT NOT NULL DEFAULT ''
        );
        """
    )
    for i in range(rows):
        conn.execute(
            "INSERT INTO navpoints (name, server_id, x, y, z, body, system, zone,"
            " heading, timestamp, notes) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
            (f"cave {i}", "srv", float(i), 2.0, 3.0, "Daymar", "Stanton", "z", 0.0,
             "2026-07-26T00:00:00", "note"),
        )
    conn.execute("PRAGMA user_version = 2")
    conn.commit()
    conn.close()


def test_v2_to_v4_keeps_every_waypoint(tmp_path: Path) -> None:
    """The migration is additive: destroying valid data to add a column is not
    an acceptable upgrade path."""
    _write_v2_db_with_rows(tmp_path, rows=3)
    db = NavPointDatabase(str(tmp_path))
    assert db.count_navpoints() == 3
    assert _user_version(_db_file(tmp_path)) == 4
    names = sorted(np.name for np in db.get_navpoints())
    assert names == ["cave 0", "cave 1", "cave 2"]


def test_v2_rows_become_explicit_local_frame(tmp_path: Path) -> None:
    _write_v2_db_with_rows(tmp_path, rows=1)
    db = NavPointDatabase(str(tmp_path))
    np_row = db.get_navpoints()[0]
    assert np_row.frame == "local"
    assert np_row.frame_id == ""
    # Coordinates and body untouched by the upgrade.
    assert (np_row.x, np_row.y, np_row.z) == (0.0, 2.0, 3.0)
    assert np_row.body == "Daymar"


def test_v2_to_v4_logs_no_wipe_warning(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """A wipe warning here would mean data was destroyed."""
    _write_v2_db_with_rows(tmp_path, rows=2)
    with caplog.at_level(logging.WARNING):
        NavPointDatabase(str(tmp_path))
    assert [r for r in caplog.records if r.levelno >= logging.WARNING] == []


def test_migration_is_idempotent(tmp_path: Path) -> None:
    _write_v2_db_with_rows(tmp_path, rows=2)
    NavPointDatabase(str(tmp_path))
    db = NavPointDatabase(str(tmp_path))
    assert db.count_navpoints() == 2
    assert _user_version(_db_file(tmp_path)) == 4
