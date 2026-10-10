"""
database.py — NavPoint SQLite persistence
Author: Mallachi
"""

import logging
import sqlite3
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path


logger = logging.getLogger(__name__)

_SCHEMA = """
CREATE TABLE IF NOT EXISTS navpoints (
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


@dataclass
class NavPoint:
    id: int
    name: str
    server_id: str
    x: float
    y: float
    z: float
    planet: str
    moon: str
    system: str
    zone: str
    heading: float
    timestamp: str
    notes: str


class NavPointDatabase:
    """SQLite-backed navpoint store."""

    def __init__(self, db_dir: str) -> None:
        db_path = Path(db_dir) / "navpoints.db"
        db_path.parent.mkdir(parents=True, exist_ok=True)
        self._path = str(db_path)
        self._init_db()
        logger.info("NavPoint database at %s", self._path)

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self._path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self) -> None:
        with self._connect() as conn:
            conn.executescript(_SCHEMA)

    # ------------------------------------------------------------------ #
    # Write operations
    # ------------------------------------------------------------------ #

    def add_navpoint(
        self,
        name: str,
        server_id: str,
        x: float,
        y: float,
        z: float,
        planet: str = "",
        moon: str = "",
        system: str = "",
        zone: str = "",
        heading: float = 0.0,
        notes: str = "",
    ) -> NavPoint:
        timestamp = datetime.now().isoformat()
        with self._connect() as conn:
            cur = conn.execute(
                """INSERT INTO navpoints
                   (name, server_id, x, y, z, planet, moon, system, zone, heading, timestamp, notes)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (name, server_id, x, y, z, planet, moon, system, zone, heading, timestamp, notes),
            )
        return NavPoint(
            id=cur.lastrowid,
            name=name,
            server_id=server_id,
            x=x,
            y=y,
            z=z,
            planet=planet,
            moon=moon,
            system=system,
            zone=zone,
            heading=heading,
            timestamp=timestamp,
            notes=notes,
        )

    def delete_navpoint(self, navpoint_id: int) -> None:
        with self._connect() as conn:
            conn.execute("DELETE FROM navpoints WHERE id = ?", (navpoint_id,))

    def rename_navpoint(self, navpoint_id: int, new_name: str) -> None:
        with self._connect() as conn:
            conn.execute(
                "UPDATE navpoints SET name = ? WHERE id = ?",
                (new_name, navpoint_id),
            )

    def update_notes(self, navpoint_id: int, notes: str) -> None:
        with self._connect() as conn:
            conn.execute(
                "UPDATE navpoints SET notes = ? WHERE id = ?",
                (notes, navpoint_id),
            )

    # ------------------------------------------------------------------ #
    # Read operations
    # ------------------------------------------------------------------ #

    def get_navpoints(self, server_id: str | None = None) -> list[NavPoint]:
        with self._connect() as conn:
            if server_id:
                rows = conn.execute(
                    "SELECT * FROM navpoints WHERE server_id = ? ORDER BY timestamp DESC",
                    (server_id,),
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT * FROM navpoints ORDER BY timestamp DESC"
                ).fetchall()
        return [self._row_to_navpoint(r) for r in rows]

    def find_navpoint_by_name(self, name: str) -> NavPoint | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM navpoints WHERE LOWER(name) = LOWER(?)",
                (name,),
            ).fetchone()
        return self._row_to_navpoint(row) if row else None

    def find_navpoint_by_id(self, navpoint_id: int) -> NavPoint | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM navpoints WHERE id = ?",
                (navpoint_id,),
            ).fetchone()
        return self._row_to_navpoint(row) if row else None

    def search_navpoints(self, query: str) -> list[NavPoint]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM navpoints WHERE LOWER(name) LIKE LOWER(?) ORDER BY timestamp DESC",
                (f"%{query}%",),
            ).fetchall()
        return [self._row_to_navpoint(r) for r in rows]

    def count_navpoints(self) -> int:
        with self._connect() as conn:
            return conn.execute("SELECT COUNT(*) FROM navpoints").fetchone()[0]

    def get_distinct_servers(self) -> list[str]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT DISTINCT server_id FROM navpoints WHERE server_id != '' ORDER BY server_id"
            ).fetchall()
        return [r["server_id"] for r in rows]

    # ------------------------------------------------------------------ #
    # Serialisation
    # ------------------------------------------------------------------ #

    @staticmethod
    def _row_to_navpoint(row: sqlite3.Row) -> NavPoint:
        return NavPoint(
            id=row["id"],
            name=row["name"],
            server_id=row["server_id"],
            x=row["x"],
            y=row["y"],
            z=row["z"],
            planet=row["planet"],
            moon=row["moon"],
            system=row["system"],
            zone=row["zone"],
            heading=row["heading"],
            timestamp=row["timestamp"],
            notes=row["notes"],
        )

    @staticmethod
    def navpoint_to_dict(np: NavPoint) -> dict:
        return {
            "id": np.id,
            "name": np.name,
            "server_id": np.server_id,
            "x": np.x,
            "y": np.y,
            "z": np.z,
            "planet": np.planet,
            "moon": np.moon,
            "system": np.system,
            "zone": np.zone,
            "heading": np.heading,
            "timestamp": np.timestamp,
            "notes": np.notes,
        }
