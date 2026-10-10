"""SQLite-backed dedup state for the log donor.

Two tables:
  uploaded_files - hashes that have been successfully donated.
  hash_cache     - {abs_path -> sha256} cache keyed by (size, mtime).
"""

from __future__ import annotations

import sqlite3
from datetime import UTC, datetime
from pathlib import Path
from typing import Iterable


_SCHEMA = """
CREATE TABLE IF NOT EXISTS uploaded_files (
    content_hash  TEXT PRIMARY KEY,
    original_path TEXT NOT NULL,
    uploaded_at   TEXT NOT NULL,
    upload_id     TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS hash_cache (
    abs_path TEXT PRIMARY KEY,
    size     INTEGER NOT NULL,
    mtime    TEXT NOT NULL,
    sha256   TEXT NOT NULL
);
"""


class DedupStore:
    """SQLite-backed dedup state. Safe for single-process, in-skill use."""

    def __init__(self, db_path: Path) -> None:
        db_path.parent.mkdir(parents=True, exist_ok=True)
        self._db_path = db_path
        # check_same_thread=False: the donor UI server runs in a daemon thread
        # and shares this store with the main thread that created it. SQLite
        # itself is thread-safe (we rely on serialized writes); we just need
        # to disable Python's cross-thread guardrail. We do NOT issue concurrent
        # writes from multiple threads.
        self._conn = sqlite3.connect(str(db_path), check_same_thread=False)
        self._conn.executescript(_SCHEMA)
        self._conn.commit()

    def close(self) -> None:
        """Close the underlying database connection."""
        self._conn.close()

    def is_uploaded(self, content_hash: str) -> bool:
        """Return True if this hash has already been donated."""
        cur = self._conn.execute(
            "SELECT 1 FROM uploaded_files WHERE content_hash = ?",
            (content_hash,),
        )
        return cur.fetchone() is not None

    def record_uploaded(
        self,
        content_hash: str,
        original_path: str,
        upload_id: str,
    ) -> None:
        """Record a single file as successfully uploaded.

        Args:
            content_hash: SHA-256 hex digest of the file content.
            original_path: Absolute path of the source file.
            upload_id: Identifier returned by the donation endpoint.
        """
        self._conn.execute(
            "INSERT OR REPLACE INTO uploaded_files "
            "(content_hash, original_path, uploaded_at, upload_id) "
            "VALUES (?, ?, ?, ?)",
            (
                content_hash,
                original_path,
                datetime.now(UTC).isoformat(),
                upload_id,
            ),
        )
        self._conn.commit()

    def record_many_uploaded(
        self,
        rows: Iterable[tuple[str, str, str]],
    ) -> None:
        """Record multiple files as successfully uploaded in one transaction.

        Args:
            rows: Iterable of (content_hash, original_path, upload_id) tuples.
        """
        now = datetime.now(UTC).isoformat()
        self._conn.executemany(
            "INSERT OR REPLACE INTO uploaded_files "
            "(content_hash, original_path, uploaded_at, upload_id) "
            "VALUES (?, ?, ?, ?)",
            [(h, p, now, u) for (h, p, u) in rows],
        )
        self._conn.commit()

    def cached_hash(self, path: Path) -> str | None:
        """Return the cached SHA-256 hash if (size, mtime) still match.

        Args:
            path: Path to the file to look up.

        Returns:
            Cached hex digest string, or None on cache miss or invalidation.
        """
        try:
            st = path.stat()
        except OSError:
            return None
        cur = self._conn.execute(
            "SELECT size, mtime, sha256 FROM hash_cache WHERE abs_path = ?",
            (str(path.resolve()),),
        )
        row = cur.fetchone()
        if row is None:
            return None
        cached_size, cached_mtime, cached_sha256 = row
        if cached_size != st.st_size:
            return None
        current_mtime = datetime.fromtimestamp(st.st_mtime, tz=UTC).isoformat()
        if cached_mtime != current_mtime:
            return None
        return cached_sha256

    def put_cached_hash(self, path: Path, sha256: str) -> None:
        """Store a hash in the cache keyed by (abs_path, size, mtime).

        Args:
            path: Path to the file being cached.
            sha256: SHA-256 hex digest of the file content.
        """
        st = path.stat()
        mtime = datetime.fromtimestamp(st.st_mtime, tz=UTC).isoformat()
        self._conn.execute(
            "INSERT OR REPLACE INTO hash_cache "
            "(abs_path, size, mtime, sha256) VALUES (?, ?, ?, ?)",
            (str(path.resolve()), st.st_size, mtime, sha256),
        )
        self._conn.commit()

    def clear(self) -> None:
        """Delete all records from both tables."""
        self._conn.execute("DELETE FROM uploaded_files")
        self._conn.execute("DELETE FROM hash_cache")
        self._conn.commit()
