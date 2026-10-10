"""Schema v4 persistence: the coordinate stack stored beside what came before.

The whole migration is additive, and the tests below spend most of their effort
proving the NEGATIVE: that a database full of the user's existing waypoints
comes through with every row, every coordinate and every behaviour it had. This
project has destroyed real waypoints twice, so a migration that "should be"
harmless is not allowed to be assumed harmless.
"""

from __future__ import annotations

import dataclasses
import json
import sqlite3
from pathlib import Path

import pytest

import coordinate_stack as cs
import database as db_mod
from database import NavPointDatabase


def _db_file(db_dir: Path) -> Path:
    return db_dir / "navpoints.db"


def _user_version(db_file: Path) -> int:
    conn = sqlite3.connect(str(db_file))
    try:
        return conn.execute("PRAGMA user_version").fetchone()[0]
    finally:
        conn.close()


V3_SCHEMA = """
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
    notes TEXT NOT NULL DEFAULT '',
    frame TEXT NOT NULL DEFAULT 'local',
    frame_id TEXT NOT NULL DEFAULT ''
);
"""

# One of each legacy kind, with values chosen so a migration that touched them
# would be visible rather than plausible.
V3_ROWS = [
    ("Cave", "srv-a", 10.5, -20.25, 30.125, "Daymar", "Stanton", "ship",
     12.5, "2026-07-26T00:00:00", "surface note", "local", ""),
    ("Deep", "srv-a", 1.0e10, -2.0e10, 3.5e9, "", "", "",
     0.0, "2026-07-27T00:00:00", "space note", "system", "653869999737"),
]


def _write_v3_db(db_dir: Path) -> None:
    db_dir.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(_db_file(db_dir)))
    conn.executescript(V3_SCHEMA)
    conn.executemany(
        "INSERT INTO navpoints (name, server_id, x, y, z, body, system, zone,"
        " heading, timestamp, notes, frame, frame_id)"
        " VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
        V3_ROWS,
    )
    conn.execute("PRAGMA user_version = 3")
    conn.commit()
    conn.close()


def _stack(root=(1.0, 2.0, 3.0), nested=((10.0, 20.0, 30.0),)) -> cs.CoordinateStack:
    rows = tuple(
        cs.StackRow(x_m=x, y_m=y, z_m=z, raw_name=f"zone_{i}",
                    raw=f"Zone: zone_{i} Pos: ...", depth=i)
        for i, (x, y, z) in enumerate(nested)
    )
    return cs.CoordinateStack(
        root=cs.StackRow(x_m=root[0], y_m=root[1], z_m=root[2], raw_name="Root"),
        solar=cs.StackRow(x_m=root[0], y_m=root[1], z_m=root[2],
                          raw_name="SolarSystem_753098466557"),
        nested=rows,
        candidate_depth=(len(rows) - 1) if rows else None,
    )


def _add_stack_point(db: NavPointDatabase, name="Keeger", stack=None) -> object:
    stack = stack or _stack()
    return db.add_navpoint(
        name=name,
        server_id="",
        body="",
        x=stack.root.x_m,
        y=stack.root.y_m,
        z=stack.root.z_m,
        frame="stack",
        coordinate_schema=1,
        root_x=stack.root.x_m,
        root_y=stack.root.y_m,
        root_z=stack.root.z_m,
        coordinate_stack=cs.to_json(stack),
    )


# --------------------------------------------------------------------------- #
# Migration
# --------------------------------------------------------------------------- #

def test_v3_to_v4_is_additive_and_keeps_every_row(tmp_path: Path) -> None:
    _write_v3_db(tmp_path)
    db = NavPointDatabase(str(tmp_path))
    assert _user_version(_db_file(tmp_path)) == 4
    assert db.count_navpoints() == len(V3_ROWS)


def test_v3_rows_survive_field_for_field(tmp_path: Path) -> None:
    _write_v3_db(tmp_path)
    db = NavPointDatabase(str(tmp_path))
    rows = {np.name: np for np in db.get_navpoints()}

    cave = rows["Cave"]
    assert (cave.x, cave.y, cave.z) == (10.5, -20.25, 30.125)
    assert (cave.body, cave.system, cave.zone) == ("Daymar", "Stanton", "ship")
    assert (cave.frame, cave.frame_id) == ("local", "")
    assert (cave.heading, cave.notes, cave.server_id) == (12.5, "surface note", "srv-a")
    assert cave.timestamp == "2026-07-26T00:00:00"

    deep = rows["Deep"]
    assert (deep.x, deep.y, deep.z) == (1.0e10, -2.0e10, 3.5e9)
    assert (deep.frame, deep.frame_id) == ("system", "653869999737")


def test_legacy_rows_get_schema_zero_and_a_null_root(tmp_path: Path) -> None:
    """NULL Root is MEANINGFUL: no Root position was ever captured for these.

    Synthesising one from a body-fixed coordinate would be inventing a number,
    which is the failure mode this whole skill exists to avoid.
    """
    _write_v3_db(tmp_path)
    db = NavPointDatabase(str(tmp_path))
    for np_row in db.get_navpoints():
        assert np_row.coordinate_schema == 0
        assert (np_row.root_x, np_row.root_y, np_row.root_z) == (None, None, None)
        assert np_row.coordinate_stack is None


def test_a_legacy_system_row_is_not_reinterpreted_as_a_stack_row(tmp_path: Path) -> None:
    _write_v3_db(tmp_path)
    db = NavPointDatabase(str(tmp_path))
    deep = db.find_navpoint_by_name("Deep")
    assert deep.frame == "system"
    assert deep.frame_id == "653869999737"
    assert deep.coordinate_schema == 0


def test_the_v3_to_v4_migration_is_idempotent(tmp_path: Path) -> None:
    _write_v3_db(tmp_path)
    NavPointDatabase(str(tmp_path))
    db = NavPointDatabase(str(tmp_path))
    assert db.count_navpoints() == len(V3_ROWS)
    assert _user_version(_db_file(tmp_path)) == 4


def test_a_v2_database_reaches_v4_in_one_step(tmp_path: Path) -> None:
    """A user who skipped the v3 build must land on exactly the same shape."""
    tmp_path.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(_db_file(tmp_path)))
    conn.executescript(V3_SCHEMA.replace(
        "    frame TEXT NOT NULL DEFAULT 'local',\n    frame_id TEXT NOT NULL DEFAULT ''\n", ""
    ).replace("notes TEXT NOT NULL DEFAULT '',", "notes TEXT NOT NULL DEFAULT ''"))
    conn.execute(
        "INSERT INTO navpoints (name, server_id, x, y, z, body, system, zone,"
        " heading, timestamp, notes) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
        ("Cave", "srv", 1.0, 2.0, 3.0, "Daymar", "Stanton", "z", 0.0,
         "2026-07-26T00:00:00", "note"),
    )
    conn.execute("PRAGMA user_version = 2")
    conn.commit()
    conn.close()

    db = NavPointDatabase(str(tmp_path))
    assert _user_version(_db_file(tmp_path)) == 4
    row = db.get_navpoints()[0]
    assert row.frame == "local"
    assert row.frame_id == ""
    assert row.coordinate_schema == 0
    assert row.coordinate_stack is None


def test_the_migration_logs_no_wipe_warning(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """A wipe warning here would mean waypoints were destroyed."""
    import logging

    _write_v3_db(tmp_path)
    with caplog.at_level(logging.WARNING):
        NavPointDatabase(str(tmp_path))
    assert [r for r in caplog.records if r.levelno >= logging.WARNING] == []


# --------------------------------------------------------------------------- #
# Stack rows
# --------------------------------------------------------------------------- #

def test_a_stack_waypoint_round_trips_through_the_database(tmp_path: Path) -> None:
    db = NavPointDatabase(str(tmp_path))
    stack = _stack(root=(-4.58e10, -1.43e10, 29384.7),
                   nested=((-386.02, 209.38, -437.0), (21584.2, -23232.5, 22622.0)))
    saved = _add_stack_point(db, stack=stack)

    fetched = db.find_navpoint_by_id(saved.id)
    assert fetched.frame == "stack"
    assert fetched.coordinate_schema == 1
    assert (fetched.root_x, fetched.root_y, fetched.root_z) == stack.root.xyz
    assert cs.from_json(fetched.coordinate_stack) == stack


def test_a_stack_waypoint_survives_a_process_restart(tmp_path: Path) -> None:
    db = NavPointDatabase(str(tmp_path))
    _add_stack_point(db)
    reopened = NavPointDatabase(str(tmp_path))
    row = reopened.find_navpoint_by_name("Keeger")
    assert row is not None
    assert cs.from_json(row.coordinate_stack) is not None


def test_a_stack_waypoint_lists_renames_and_deletes(tmp_path: Path) -> None:
    db = NavPointDatabase(str(tmp_path))
    saved = _add_stack_point(db)
    assert [np.name for np in db.get_navpoints()] == ["Keeger"]

    db.rename_navpoint(saved.id, "Keeger Base")
    db.update_notes(saved.id, "docked here")
    row = db.find_navpoint_by_id(saved.id)
    assert row.name == "Keeger Base"
    assert row.notes == "docked here"
    # The rename touched nothing about the address.
    assert cs.from_json(row.coordinate_stack) is not None
    assert row.coordinate_schema == 1

    db.delete_navpoint(saved.id)
    assert db.count_navpoints() == 0


def test_stack_and_legacy_rows_coexist_and_stay_distinguishable(tmp_path: Path) -> None:
    _write_v3_db(tmp_path)
    db = NavPointDatabase(str(tmp_path))
    _add_stack_point(db)
    by_name = {np.name: np for np in db.get_navpoints()}
    assert by_name["Cave"].coordinate_schema == 0
    assert by_name["Deep"].coordinate_schema == 0
    assert by_name["Keeger"].coordinate_schema == 1
    assert {np.frame for np in by_name.values()} == {"local", "system", "stack"}


def test_x_y_z_mirror_root_for_the_existing_hud_and_listing_code(tmp_path: Path) -> None:
    """A COMPATIBILITY behaviour, recorded rather than assumed: the page and the
    listing read x/y/z on every row, so a stack row puts Root there."""
    db = NavPointDatabase(str(tmp_path))
    stack = _stack(root=(7.0, 8.0, 9.0))
    saved = _add_stack_point(db, stack=stack)
    assert (saved.x, saved.y, saved.z) == stack.root.xyz
    payload = db.navpoint_to_dict(db.find_navpoint_by_id(saved.id))
    assert (payload["x"], payload["y"], payload["z"]) == stack.root.xyz
    assert payload["coordinate_schema"] == 1


def test_the_hud_payload_does_not_carry_the_whole_stack(tmp_path: Path) -> None:
    """Nothing on the page routes, and a nested stack per waypoint would be
    paid for on every refresh."""
    db = NavPointDatabase(str(tmp_path))
    saved = _add_stack_point(db)
    payload = db.navpoint_to_dict(db.find_navpoint_by_id(saved.id))
    assert "coordinate_stack" not in payload


# --------------------------------------------------------------------------- #
# Fail-closed
# --------------------------------------------------------------------------- #

@pytest.mark.parametrize("kwargs, why", [
    (dict(coordinate_schema=0), "schema 0 is the legacy marker, not a stack"),
    (dict(root_x=None), "no Root means no long-range address"),
    (dict(root_y=None), "no Root means no long-range address"),
    (dict(root_z=None), "no Root means no long-range address"),
    (dict(coordinate_stack=None), "no nested rows means nothing to fall back from"),
    (dict(coordinate_stack="   "), "blank is not a stack"),
])
def test_an_incomplete_stack_waypoint_is_refused_at_write_time(kwargs, why, tmp_path) -> None:
    db = NavPointDatabase(str(tmp_path))
    stack = _stack()
    call = dict(
        name="wp", server_id="", body="", x=1.0, y=2.0, z=3.0, frame="stack",
        coordinate_schema=1, root_x=1.0, root_y=2.0, root_z=3.0,
        coordinate_stack=cs.to_json(stack),
    )
    call.update(kwargs)
    with pytest.raises(ValueError):
        db.add_navpoint(**call)
    assert db.count_navpoints() == 0, why


def test_an_unknown_frame_is_still_refused(tmp_path: Path) -> None:
    db = NavPointDatabase(str(tmp_path))
    with pytest.raises(ValueError):
        db.add_navpoint("wp", "", "Daymar", 1.0, 2.0, 3.0, frame="galactic")


@pytest.mark.parametrize("corrupt", [
    "not json at all",
    "{}",
    '{"schema":2,"root":{"x_m":1,"y_m":2,"z_m":3}}',
    '{"schema":1,"root":{"x_m":1,"y_m":2},"solar":{"x_m":1,"y_m":2,"z_m":3}}',
])
def test_a_corrupt_stack_is_listable_but_not_navigable(corrupt, tmp_path) -> None:
    """Fail closed for navigation, fail OPEN for the row itself. Deleting a
    waypoint because its stack column went bad is the 2026-07-26 failure with a
    different trigger."""
    db = NavPointDatabase(str(tmp_path))
    saved = _add_stack_point(db)
    conn = sqlite3.connect(str(_db_file(tmp_path)))
    conn.execute("UPDATE navpoints SET coordinate_stack = ? WHERE id = ?",
                 (corrupt, saved.id))
    conn.commit()
    conn.close()

    reopened = NavPointDatabase(str(tmp_path))
    row = reopened.find_navpoint_by_id(saved.id)
    assert row is not None
    assert row.name == "Keeger"
    assert len(reopened.get_navpoints()) == 1
    # Navigation refuses, because the stack cannot be rebuilt.
    assert cs.from_json(row.coordinate_stack) is None
    assert cs.select_route(cs.from_json(row.coordinate_stack), _stack()).mode == \
        cs.MODE_REFUSED


# --------------------------------------------------------------------------- #
# The wipe path
# --------------------------------------------------------------------------- #

def test_a_stack_waypoint_carries_no_server_id_so_no_wipe_can_key_on_it(tmp_path) -> None:
    """The local reader never emits `server_id`, and the three-agreeing-captures
    confirmation rule is REFUTED for a deterministic reader. A stack waypoint is
    therefore stored with an empty server_id, and an empty one can never make
    both sides of the wipe comparison non-empty."""
    db = NavPointDatabase(str(tmp_path))
    _add_stack_point(db, name="A")
    _add_stack_point(db, name="B")
    assert db.get_stored_server_id() == ""
    assert db.wipe_on_server_change("pub-euw1b-sc-alpha-490-99999999") == 0
    assert db.count_navpoints() == 2


def test_a_changed_solarsystem_suffix_cannot_delete_anything(tmp_path: Path) -> None:
    """The SolarSystem id is diagnostic on a stack row. It is stored inside the
    stack JSON and nothing keys a delete on it."""
    db = NavPointDatabase(str(tmp_path))
    saved = _add_stack_point(db)
    stored = json.loads(db.find_navpoint_by_id(saved.id).coordinate_stack)
    assert stored["solar"]["raw_name"] == "SolarSystem_753098466557"

    # A later session under a different SolarSystem id: still two rows, still
    # addressable, because Root is the address and the suffix is a note.
    base = _stack()
    other = dataclasses.replace(
        base, solar=dataclasses.replace(base.solar, raw_name="SolarSystem_000000000001")
    )
    _add_stack_point(db, name="Later", stack=other)
    assert db.count_navpoints() == 2


def test_the_schema_constants_are_the_ones_the_code_uses() -> None:
    assert db_mod._SCHEMA_VERSION == 4
    assert db_mod._COORDINATE_SCHEMA_STACK == cs.SCHEMA_VERSION
    assert db_mod._FRAME_STACK == "stack"
