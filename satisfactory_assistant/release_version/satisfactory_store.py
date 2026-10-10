"""Per-save SQLite persistence foundation for the Satisfactory Assistant skill.

This module is the pure storage layer beneath the existing JSONL
``SaveWorkspace``. It owns schema creation, stepwise migration, transactional
record CRUD, and idempotent import from the legacy JSONL files. It does not
touch ``SaveWorkspace``, ``main.py``, or any other Wingman module: only the
standard library (``sqlite3``, ``json``, ``hashlib``, ``datetime``,
``pathlib``) is imported, so this file can be tested and reasoned about in
isolation before the adapter swap that follows in a later work package.

Assumption: single writer per save. Exactly one Wingman process is expected
to hold a given save's ``planning.sqlite3`` open at a time; no cross-process
locking beyond SQLite's own defaults is implemented here.
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
from datetime import datetime
from pathlib import Path


STORE_SCHEMA_VERSION = 2

# Record kinds mirror satisfactory_workspace._KINDS. Duplicated here (rather
# than imported) because this module is restricted to stdlib-only imports.
_KINDS = ("notes", "todos", "goals", "flows", "changes")

# Status values valid for a production flow, mirroring
# satisfactory_workspace.FLOW_STATUSES.
_FLOW_STATUSES = ("planned", "building", "blocked", "balanced", "done", "archived")

# Flow fields a caller may explicitly clear via update_flow's clear_fields,
# mirroring satisfactory_workspace.CLEARABLE_FIELDS.
_CLEARABLE_FIELDS = ("details", "area", "recipe", "machines", "constraints", "inputs", "outputs")

# Columns stored directly on the records table; anything else in an
# imported/added record is legacy or kind-specific metadata and lands in
# the "extra" JSON column instead.
_CORE_FIELDS = frozenset({"id", "title", "details", "status", "created_at", "updated_at"})

_SCHEMA_SQL = """
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

# The v2 plan-model tables, appended to _SCHEMA_SQL below for fresh databases
# and reused verbatim as the v1-to-v2 migration script for existing ones, so
# a fresh create and a migrated database end up structurally identical.
_PLAN_TABLES_SQL = """
CREATE TABLE IF NOT EXISTS master_plans (
    plan_id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS stage_plans (
    stage_key TEXT PRIMARY KEY,
    plan_id TEXT NOT NULL REFERENCES master_plans(plan_id),
    phase INTEGER NOT NULL,
    revision INTEGER NOT NULL,
    created_at TEXT NOT NULL,
    payload TEXT NOT NULL,
    UNIQUE(plan_id, phase, revision)
);
CREATE TABLE IF NOT EXISTS solver_runs (
    run_id TEXT PRIMARY KEY,
    plan_id TEXT NOT NULL,
    phase INTEGER NOT NULL,
    created_at TEXT NOT NULL,
    status TEXT NOT NULL,
    payload TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_stage_plans_plan_phase_revision
    ON stage_plans(plan_id, phase, revision);
"""

_SCHEMA_SQL = _SCHEMA_SQL + _PLAN_TABLES_SQL

# Stepwise migration scaffold: maps the version a database is currently AT to
# the SQL script that brings it to the next version. v1 databases gain the
# plan-model tables verbatim; a future schema bump adds an entry keyed by the
# version being migrated away from.
_MIGRATIONS: dict[int, str] = {1: _PLAN_TABLES_SQL}


class StoreError(RuntimeError):
    """Raised for schema/version problems or invalid store operations."""


def _row_to_record(row: sqlite3.Row) -> dict[str, object]:
    """Flatten a records row into the same shape SaveWorkspace records use.

    The workspace's JSONL records carry kind-specific and legacy fields as
    plain top-level keys (there is no nested "extra" key in a JSONL line).
    To keep the two layers interchangeable, the stored "extra" JSON object is
    merged back onto the top level here rather than returned as a nested
    value.
    """
    record: dict[str, object] = {
        "id": row["id"],
        "title": row["title"],
        "details": row["details"],
        "status": row["status"],
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
    }
    extra_raw = row["extra"]
    if extra_raw:
        try:
            extra = json.loads(extra_raw)
        except json.JSONDecodeError:
            extra = {}
        if isinstance(extra, dict):
            record.update(extra)
    return record


def _parse_jsonl_lines(text: str) -> list[dict[str, object]]:
    """Parse JSONL text, tolerating the same malformed shapes the workspace does.

    Invalid JSON lines and syntactically valid JSON that is not an object
    (list, string, number, null) are skipped rather than raising, matching
    ``SaveWorkspace._read``.
    """
    records: list[dict[str, object]] = []
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            value = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(value, dict):
            records.append(value)
    return records


class SaveStore:
    """Context-managed SQLite store for one save's planning records."""

    def __init__(self, db_path: Path) -> None:
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(self.db_path))
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA foreign_keys = ON")
        self._init_schema()

    @classmethod
    def open(cls, db_path: Path) -> SaveStore:
        """Open (creating if absent) the per-save SQLite store at ``db_path``."""
        return cls(db_path)

    def __enter__(self) -> SaveStore:
        return self

    def __exit__(self, exc_type: object, exc: object, tb: object) -> None:
        self.close()

    def close(self) -> None:
        """Close the underlying SQLite connection."""
        self._conn.close()

    def _init_schema(self) -> None:
        table_exists = self._conn.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table' AND name = 'meta'"
        ).fetchone()
        if table_exists is None:
            now_iso = datetime.now().isoformat()
            with self._conn:
                self._conn.executescript(_SCHEMA_SQL)
                self._conn.execute(
                    "INSERT INTO meta (key, value) VALUES ('schema_version', ?)",
                    (str(STORE_SCHEMA_VERSION),),
                )
                self._conn.execute(
                    "INSERT INTO meta (key, value) VALUES ('created_at', ?)",
                    (now_iso,),
                )
            return

        row = self._conn.execute(
            "SELECT value FROM meta WHERE key = 'schema_version'"
        ).fetchone()
        version = int(row["value"]) if row is not None else STORE_SCHEMA_VERSION
        if version > STORE_SCHEMA_VERSION:
            raise StoreError(
                f"Database schema version {version} is newer than the "
                f"supported version {STORE_SCHEMA_VERSION}; refusing to open "
                "rather than risk a silent downgrade."
            )
        while version < STORE_SCHEMA_VERSION:
            migration_sql = _MIGRATIONS.get(version)
            if migration_sql is None:
                raise StoreError(
                    f"No migration registered from schema version {version} "
                    f"to {version + 1}."
                )
            with self._conn:
                self._conn.executescript(migration_sql)
                version += 1
                self._conn.execute(
                    "UPDATE meta SET value = ? WHERE key = 'schema_version'",
                    (str(version),),
                )

    def add_record(
        self,
        kind: str,
        record_id: str,
        title: str,
        details: str,
        status: str,
        now: datetime,
        extra: dict[str, object] | None = None,
    ) -> None:
        """Insert a new record inside a transaction.

        Raises:
            StoreError: if ``kind`` is not a recognized record kind. Raised
                before any statement runs, so an unknown kind never touches
                the database.
        """
        if kind not in _KINDS:
            raise StoreError(f"Unknown record kind: {kind}")
        iso = now.isoformat()
        extra_json = json.dumps(extra or {}, ensure_ascii=False)
        with self._conn:
            self._conn.execute(
                "INSERT INTO records"
                " (id, kind, title, details, status, created_at, updated_at, extra)"
                " VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (record_id, kind, title, details, status, iso, iso, extra_json),
            )

    def get_record(self, record_id: str) -> dict[str, object] | None:
        """Return a record by id, or None if no record has that id."""
        row = self._conn.execute(
            "SELECT id, title, details, status, created_at, updated_at, extra"
            " FROM records WHERE id = ?",
            (record_id,),
        ).fetchone()
        if row is None:
            return None
        return _row_to_record(row)

    def set_status(self, kind: str, record_id: str, status: str, now: datetime) -> bool:
        """Update a record's status within a single kind only.

        Mirrors ``SaveWorkspace.set_status_for_kind``: an id that does not
        belong to ``kind`` (or does not exist) is a no-op, returning False.

        Raises:
            StoreError: if ``kind`` is not a recognized record kind.
        """
        if kind not in _KINDS:
            raise StoreError(f"Unknown record kind: {kind}")
        with self._conn:
            cursor = self._conn.execute(
                "UPDATE records SET status = ?, updated_at = ? WHERE id = ? AND kind = ?",
                (status, now.isoformat(), record_id, kind),
            )
            return cursor.rowcount > 0

    def update_flow(
        self,
        record_id: str,
        now: datetime,
        title: str | None = None,
        details: str | None = None,
        inputs: list[str] | None = None,
        outputs: list[str] | None = None,
        status: str | None = None,
        area: str | None = None,
        recipe: str | None = None,
        machines: str | None = None,
        constraints: str | None = None,
        clear_fields: set[str] | None = None,
    ) -> bool:
        """Update fields of an existing flow record. Returns True if found.

        Mirrors ``SaveWorkspace.update_flow``: only provided, non-empty
        fields change; an empty string means "leave unchanged". Clearing a
        field to its empty value is opt-in via ``clear_fields`` and is
        applied last, so an explicit clear wins over a set in the same call.
        """
        clear = {f for f in (clear_fields or set()) if f in _CLEARABLE_FIELDS}
        with self._conn:
            row = self._conn.execute(
                "SELECT title, details, status, extra FROM records"
                " WHERE id = ? AND kind = 'flows'",
                (record_id,),
            ).fetchone()
            if row is None:
                return False

            new_title = row["title"]
            new_details = row["details"]
            new_status = row["status"]
            extra_raw = row["extra"]
            extra: dict[str, object] = json.loads(extra_raw) if extra_raw else {}

            if title is not None and title.strip():
                new_title = title.strip()
            if details is not None and details.strip():
                new_details = details.strip()
            if inputs is not None:
                extra["inputs"] = inputs
            if outputs is not None:
                extra["outputs"] = outputs
            if status is not None and status in _FLOW_STATUSES:
                new_status = status
            for field, value in (
                ("area", area),
                ("recipe", recipe),
                ("machines", machines),
                ("constraints", constraints),
            ):
                if value is not None and value.strip():
                    extra[field] = value.strip()

            for field in clear:
                if field == "details":
                    new_details = ""
                elif field in ("inputs", "outputs"):
                    extra[field] = []
                else:
                    extra[field] = ""

            self._conn.execute(
                "UPDATE records SET title = ?, details = ?, status = ?, extra = ?,"
                " updated_at = ? WHERE id = ? AND kind = 'flows'",
                (
                    new_title,
                    new_details,
                    new_status,
                    json.dumps(extra, ensure_ascii=False),
                    now.isoformat(),
                    record_id,
                ),
            )
            return True

    def list_records(
        self,
        kind: str,
        status: str | None = None,
        limit: int | None = None,
        newest_first: bool = True,
    ) -> list[dict[str, object]]:
        """List records of one kind, optionally filtered by status and capped.

        Ordered by ``created_at`` (matching the ``records(kind, created_at)``
        index), descending by default.

        Raises:
            StoreError: if ``kind`` is not a recognized record kind.
        """
        if kind not in _KINDS:
            raise StoreError(f"Unknown record kind: {kind}")
        order = "DESC" if newest_first else "ASC"
        query = (
            "SELECT id, title, details, status, created_at, updated_at, extra"
            " FROM records WHERE kind = ?"
        )
        params: list[object] = [kind]
        if status is not None:
            query += " AND status = ?"
            params.append(status)
        query += f" ORDER BY created_at {order}"
        if limit is not None:
            query += " LIMIT ?"
            params.append(limit)
        rows = self._conn.execute(query, params).fetchall()
        return [_row_to_record(row) for row in rows]

    # --- Plan persistence (schema v2) ---

    def upsert_master_plan(self, plan: dict[str, object]) -> None:
        """Insert or update a master plan row inside a transaction.

        ``created_at`` is preserved from the first insert; a later call for
        the same ``plan_id`` only updates ``name`` and ``updated_at``.

        Args:
            plan: Mapping with keys ``plan_id``, ``name``, ``created_at``,
                ``updated_at``.
        """
        with self._conn:
            self._conn.execute(
                "INSERT INTO master_plans (plan_id, name, created_at, updated_at)"
                " VALUES (?, ?, ?, ?)"
                " ON CONFLICT(plan_id) DO UPDATE SET"
                " name = excluded.name, updated_at = excluded.updated_at",
                (
                    plan["plan_id"],
                    plan["name"],
                    plan["created_at"],
                    plan["updated_at"],
                ),
            )

    def get_master_plan(self, plan_id: str) -> dict[str, object] | None:
        """Return a master plan by id, or None if no plan has that id."""
        row = self._conn.execute(
            "SELECT plan_id, name, created_at, updated_at FROM master_plans"
            " WHERE plan_id = ?",
            (plan_id,),
        ).fetchone()
        if row is None:
            return None
        return {
            "plan_id": row["plan_id"],
            "name": row["name"],
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
        }

    def next_stage_revision(self, plan_id: str, phase: int) -> int:
        """Return the next revision number for a plan/phase pair."""
        row = self._conn.execute(
            "SELECT MAX(revision) AS latest FROM stage_plans"
            " WHERE plan_id = ? AND phase = ?",
            (plan_id, phase),
        ).fetchone()
        latest = row["latest"] if row is not None and row["latest"] is not None else 0
        return latest + 1

    def save_stage_plan(
        self,
        plan_id: str,
        stage_payload: dict[str, object],
        phase: int,
        now: datetime,
        revision: int | None = None,
    ) -> int:
        """Persist a new stage plan revision inside a transaction.

        The revision is assigned automatically unless the caller reserves one
        first with ``next_stage_revision``. The stored payload is stamped with
        the final phase, revision, and created_at values so raw storage and
        ``load_stage_plan`` agree.

        Args:
            plan_id: Owning master plan id. Must already exist; an unknown
                id fails the ``stage_plans`` foreign key.
            stage_payload: JSON-able payload to store.
            phase: Project Assembly phase number the stage covers.
            now: Timestamp recorded as ``created_at`` for the new revision.
            revision: Optional pre-reserved revision number.

        Returns:
            The revision number assigned to the new row.
        """
        if revision is None:
            revision = self.next_stage_revision(plan_id, phase)
        if revision < 1:
            raise StoreError(f"Invalid stage revision: {revision}")
        stage_key = f"{plan_id}:{phase}:{revision}"
        payload = dict(stage_payload)
        payload["phase"] = phase
        payload["revision"] = revision
        payload["created_at"] = now.isoformat()
        with self._conn:
            self._conn.execute(
                "INSERT INTO stage_plans"
                " (stage_key, plan_id, phase, revision, created_at, payload)"
                " VALUES (?, ?, ?, ?, ?, ?)",
                (
                    stage_key,
                    plan_id,
                    phase,
                    revision,
                    now.isoformat(),
                    json.dumps(payload, ensure_ascii=False),
                ),
            )
            return revision

    def load_stage_plan(
        self, plan_id: str, phase: int, revision: int | None = None
    ) -> dict[str, object] | None:
        """Load a stage plan payload, defaulting to the latest revision.

        Args:
            plan_id: Owning master plan id.
            phase: Project Assembly phase number.
            revision: Specific revision to load, or None for the latest.

        Returns:
            The stored payload with ``phase``, ``revision``, and
            ``created_at`` set from the row (overriding any stale copies
            inside the payload itself), or None if no matching row exists.
        """
        if revision is None:
            row = self._conn.execute(
                "SELECT phase, revision, created_at, payload FROM stage_plans"
                " WHERE plan_id = ? AND phase = ? ORDER BY revision DESC LIMIT 1",
                (plan_id, phase),
            ).fetchone()
        else:
            row = self._conn.execute(
                "SELECT phase, revision, created_at, payload FROM stage_plans"
                " WHERE plan_id = ? AND phase = ? AND revision = ?",
                (plan_id, phase, revision),
            ).fetchone()
        if row is None:
            return None
        data: dict[str, object] = json.loads(row["payload"])
        data["phase"] = row["phase"]
        data["revision"] = row["revision"]
        data["created_at"] = row["created_at"]
        return data

    def list_stage_revisions(self, plan_id: str, phase: int) -> list[int]:
        """Return known revision numbers for a plan/phase, ascending."""
        rows = self._conn.execute(
            "SELECT revision FROM stage_plans WHERE plan_id = ? AND phase = ?"
            " ORDER BY revision ASC",
            (plan_id, phase),
        ).fetchall()
        return [row["revision"] for row in rows]

    def record_solver_run(
        self,
        run_id: str,
        plan_id: str,
        phase: int,
        status: str,
        payload: dict[str, object],
        now: datetime,
    ) -> None:
        """Record a solver run inside a transaction. Rows are immutable.

        Raises:
            StoreError: if ``run_id`` already has a recorded run. There is
                deliberately no update or delete method for solver runs:
                immutability is enforced here, not merely assumed.
        """
        with self._conn:
            existing = self._conn.execute(
                "SELECT 1 FROM solver_runs WHERE run_id = ?", (run_id,)
            ).fetchone()
            if existing is not None:
                raise StoreError(f"Solver run {run_id!r} is already recorded")
            self._conn.execute(
                "INSERT INTO solver_runs"
                " (run_id, plan_id, phase, created_at, status, payload)"
                " VALUES (?, ?, ?, ?, ?, ?)",
                (
                    run_id,
                    plan_id,
                    phase,
                    now.isoformat(),
                    status,
                    json.dumps(payload, ensure_ascii=False),
                ),
            )

    def get_solver_run(self, run_id: str) -> dict[str, object] | None:
        """Return a solver run by id, or None if no run has that id."""
        row = self._conn.execute(
            "SELECT run_id, plan_id, phase, created_at, status, payload"
            " FROM solver_runs WHERE run_id = ?",
            (run_id,),
        ).fetchone()
        if row is None:
            return None
        data: dict[str, object] = json.loads(row["payload"])
        data["run_id"] = row["run_id"]
        data["plan_id"] = row["plan_id"]
        data["phase"] = row["phase"]
        data["created_at"] = row["created_at"]
        data["status"] = row["status"]
        return data


def _import_one_file(store: SaveStore, kind: str, path: Path) -> int:
    """Import one legacy JSONL file for ``kind``. Returns records newly inserted."""
    data = path.read_bytes()
    digest = hashlib.sha256(data).hexdigest()
    source_key = str(path)

    existing = store._conn.execute(
        "SELECT sha256 FROM import_sources WHERE source_path = ?",
        (source_key,),
    ).fetchone()
    if existing is not None and existing["sha256"] == digest:
        return 0

    records = _parse_jsonl_lines(data.decode("utf-8"))
    # Legacy records may lack timestamps; default them to the import moment
    # rather than fail, per the documented risk in the implementation packet.
    now_iso = datetime.now().isoformat()
    inserted = 0
    with store._conn:
        for record in records:
            record_id = record.get("id")
            if not record_id:
                continue
            extra = {k: v for k, v in record.items() if k not in _CORE_FIELDS}
            title = str(record.get("title", ""))
            details = str(record.get("details", ""))
            status = str(record.get("status") or "open")
            created_at = str(record.get("created_at") or now_iso)
            updated_at = str(record.get("updated_at") or now_iso)
            cursor = store._conn.execute(
                "INSERT OR IGNORE INTO records"
                " (id, kind, title, details, status, created_at, updated_at, extra)"
                " VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    record_id,
                    kind,
                    title,
                    details,
                    status,
                    created_at,
                    updated_at,
                    json.dumps(extra, ensure_ascii=False),
                ),
            )
            if cursor.rowcount > 0:
                inserted += 1

        store._conn.execute(
            "INSERT OR REPLACE INTO import_sources"
            " (source_path, sha256, imported_at, record_count) VALUES (?, ?, ?, ?)",
            (source_key, digest, now_iso, inserted),
        )
    return inserted


def import_jsonl(store: SaveStore, sources: dict[str, Path]) -> dict[str, int]:
    """Import legacy JSONL files into ``store``, one kind per source path.

    Idempotent by content hash: a source whose SHA-256 matches the last
    recorded import is skipped entirely. A missing source file is skipped
    (count 0). Existing store records are never overwritten (INSERT OR
    IGNORE by id), so a duplicate id across two sources keeps whichever
    import saw it first. Source files are only ever read, never written to,
    moved, or deleted.

    Raises:
        StoreError: if any key in ``sources`` is not a recognized record kind.
    """
    counts: dict[str, int] = {}
    for kind, path in sources.items():
        if kind not in _KINDS:
            raise StoreError(f"Unknown record kind: {kind}")
        path = Path(path)
        if not path.is_file():
            counts[kind] = 0
            continue
        counts[kind] = _import_one_file(store, kind, path)
    return counts
