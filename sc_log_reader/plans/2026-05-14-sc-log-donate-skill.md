# SC Log Donate Skill Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a "Donate logs" feature to the existing `sc_log_reader` Wingman AI skill that scans SC installs, filters logs by version, dedupes by content hash, and uploads via the `sc-log-donate` Worker built in the companion plan.

**Architecture:** A new package `skills/sc_log_reader/log_donor/` containing five focused modules (scanner, handle extractor, dedup, uploader, UI dialog). Wires into the existing skill's settings panel through a new "Help improve this skill" section. Persistent local state (uploaded hashes + cache) lives in a SQLite DB under `%APPDATA%/Wingman/sc_log_reader/`.

**Tech Stack:** Python 3.10+, `httpx` for HTTP, `sqlite3` (stdlib), `psutil` for SC-running detection, existing Wingman AI skill plumbing.

**Prereq:** The Worker plan (`2026-05-14-sc-log-donate-worker.md`) must be at least at Task 7 (working `/upload/begin`) for end-to-end integration tests. Earlier tasks can use a recorded Worker response or a mock.

---

## Spec reference

This plan implements Sections 3 (Skill-side component), 5 (skill-side dedup), 6 (data flow), 7 (error handling), 8 (privacy/consent) of:

`skills/sc_log_reader/specs/2026-05-14-sc-log-donation-tool-design.md`

---

## File structure

```
skills/sc_log_reader/
├── log_donor/                          (NEW package)
│   ├── __init__.py
│   ├── scanner.py                      install discovery + version filter + candidate hashing
│   ├── handle_extractor.py             parse player handle from a log
│   ├── dedup.py                        local SQLite for hash cache + uploaded set
│   ├── uploader.py                     Worker handshake + R2 PUTs + retries
│   ├── ui_dialog.py                    consent + preview dialog widgets
│   └── types.py                        dataclasses: Candidate, UploadResult, etc.
├── main.py                             (EDITED) add "Donate logs" settings section
├── default_config.yaml                 (EDITED) add donor.* config block
├── update_release.py                   (EDITED) inject DONOR_TOKEN at build time
└── tests/                              (NEW directory)
    ├── __init__.py
    ├── conftest.py                     fixtures: tmp install tree, mock HTTP
    ├── fixtures/
    │   ├── live/
    │   │   ├── Game.log                small synthetic Game.log
    │   │   └── logbackups/
    │   │       ├── Game_match.log      version matches Game.log
    │   │       └── Game_old.log        version does NOT match
    │   └── ptu/
    │       ├── Game.log
    │       └── logbackups/
    ├── test_scanner.py
    ├── test_handle_extractor.py
    ├── test_dedup.py
    ├── test_uploader.py
    └── test_log_donor_integration.py   wires the modules together with mock HTTP
```

**File responsibilities:**

| File | Responsibility |
|---|---|
| `log_donor/types.py` | Dataclasses for `Candidate`, `PreviewSummary`, `UploadResult`, `BeginResponse`. |
| `log_donor/scanner.py` | Walk install paths, read Game.log headers for version, filter logbackups, hash each survivor. Has `discover_candidates(config) -> list[Candidate]`. |
| `log_donor/handle_extractor.py` | Read first N lines of a log, extract player handle. Returns `str | None`. |
| `log_donor/dedup.py` | SQLite read/write for `uploaded_files` and `hash_cache` tables. |
| `log_donor/uploader.py` | POST `/upload/begin`, PUT to R2 with retry, POST `/upload/complete`. |
| `log_donor/ui_dialog.py` | Build the consent dialog and the preview dialog using existing Wingman UI primitives. |
| `main.py` (existing) | Wire a "Donate logs" button into the settings panel. |
| `default_config.yaml` (existing) | Add the `donor` config block. |
| `update_release.py` (existing) | Replace `__INJECT_AT_BUILD__` placeholder with the real DONOR_TOKEN. |

---

## Conventions

- Python files follow the project standards in `~/.claude/rules/python-standards.md`: PEP 8, 88-col line, double quotes, type hints required, Google-style docstrings, logger per module.
- Tests use `pytest`. Fixtures via `conftest.py`. Mock HTTP via a transport stub passed into `httpx.Client`.
- All paths use `pathlib.Path`. No `os.path` string concatenation.

---

## Task 0: Bootstrap log_donor package

**Files:**
- Create: `skills/sc_log_reader/log_donor/__init__.py`
- Create: `skills/sc_log_reader/log_donor/types.py`
- Create: `skills/sc_log_reader/tests/__init__.py`
- Create: `skills/sc_log_reader/tests/conftest.py`

- [ ] **Step 1: Create `skills/sc_log_reader/log_donor/__init__.py`** (empty)

- [ ] **Step 2: Create `skills/sc_log_reader/tests/__init__.py`** (empty)

- [ ] **Step 3: Write `skills/sc_log_reader/log_donor/types.py`**

```python
"""Shared dataclasses for the log_donor package."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal


InstallType = Literal["Live", "PTU", "HOTFIX"]


@dataclass
class Candidate:
    """One log file eligible for donation."""

    path: Path
    install: InstallType
    game_version: str
    size_bytes: int
    sha256: str
    detected_handle: str | None
    renamed: str  # "{handle_or_unknown}_{original_name}"


@dataclass
class PreviewSummary:
    """What the preview dialog shows the player before they confirm."""

    candidates: list[Candidate]
    total_bytes: int
    per_install_counts: dict[str, int]
    per_install_bytes: dict[str, int]
    already_uploaded_count: int  # files filtered out by local dedup


@dataclass
class FileUploadResult:
    """Per-file outcome of an upload attempt."""

    sha256: str
    renamed: str
    succeeded: bool
    already_uploaded: bool  # true if Worker said the hash was known
    error: str | None = None


@dataclass
class UploadResult:
    """Aggregate outcome of one /upload/begin → PUTs → /upload/complete cycle."""

    upload_id: str | None
    files: list[FileUploadResult] = field(default_factory=list)
    total_bytes_uploaded: int = 0
    error: str | None = None

    @property
    def succeeded_count(self) -> int:
        return sum(1 for f in self.files if f.succeeded)

    @property
    def failed_count(self) -> int:
        return sum(1 for f in self.files if not f.succeeded and not f.already_uploaded)
```

- [ ] **Step 4: Write `skills/sc_log_reader/tests/conftest.py`** with shared fixtures

```python
"""Pytest fixtures shared across log_donor tests."""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path
from textwrap import dedent

import pytest


SAMPLE_GAMELOG_HEADER = dedent(
    """\
    <14:30:22> Loading C:\\Program Files\\Roberts Space Industries\\StarCitizen\\Live\\Bin64\\StarCitizen.exe
    <14:30:22> BranchName: sc-alpha-4.7.2-LIVE
    <14:30:22> BuildId: 12345
    <14:30:22> Build Configuration: Release
    """
)


def _gamelog_text(version: str = "sc-alpha-4.7.2-LIVE", build: str = "12345") -> str:
    return dedent(
        f"""\
        <14:30:22> Loading C:\\Program Files\\Roberts Space Industries\\StarCitizen\\Bin64\\StarCitizen.exe
        <14:30:22> BranchName: {version}
        <14:30:22> BuildId: {build}
        <14:30:22> Build Configuration: Release
        <14:30:25> <AccountLoginCharacterStatus_Character> name Mallachi state STATE_CURRENT
        <14:30:30> Log started.
        """
    )


@pytest.fixture
def fake_sc_install(tmp_path: Path) -> Path:
    """Build a synthetic SC install tree under tmp_path/StarCitizen/.

    Layout:
      Live/
        Game.log         (version 4.7.2 build 12345)
        logbackups/
          Game_match.log (version 4.7.2 build 12345 - matches)
          Game_old.log   (version 4.7.1 build 11111 - does NOT match)
      PTU/
        Game.log         (version 4.7.3-PTU build 22222)
        logbackups/
          Game_match.log (version 4.7.3-PTU build 22222 - matches)
    """
    root = tmp_path / "StarCitizen"

    live = root / "Live"
    (live / "logbackups").mkdir(parents=True)
    (live / "Game.log").write_text(_gamelog_text("sc-alpha-4.7.2-LIVE", "12345"))
    (live / "logbackups" / "Game_match.log").write_text(
        _gamelog_text("sc-alpha-4.7.2-LIVE", "12345")
    )
    (live / "logbackups" / "Game_old.log").write_text(
        _gamelog_text("sc-alpha-4.7.1-LIVE", "11111")
    )

    ptu = root / "PTU"
    (ptu / "logbackups").mkdir(parents=True)
    (ptu / "Game.log").write_text(_gamelog_text("sc-alpha-4.7.3-PTU", "22222"))
    (ptu / "logbackups" / "Game_match.log").write_text(
        _gamelog_text("sc-alpha-4.7.3-PTU", "22222")
    )

    return root


@pytest.fixture
def sc_not_running(monkeypatch: pytest.MonkeyPatch) -> None:
    """Force is_sc_running() to return False during a test."""

    def fake_is_running() -> bool:
        return False

    import sys
    if "log_donor.scanner" in sys.modules:
        monkeypatch.setattr("log_donor.scanner.is_sc_running", fake_is_running)
```

- [ ] **Step 5: Commit**

```powershell
git add skills/sc_log_reader/log_donor/__init__.py skills/sc_log_reader/log_donor/types.py skills/sc_log_reader/tests/__init__.py skills/sc_log_reader/tests/conftest.py
git commit -m "feat(sc_log_reader): bootstrap log_donor package and test fixtures"
```

---

## Task 1: Handle extractor (TDD)

**Files:**
- Create: `skills/sc_log_reader/tests/test_handle_extractor.py`
- Create: `skills/sc_log_reader/log_donor/handle_extractor.py`

- [ ] **Step 1: Write the failing test**

```python
"""Tests for log_donor.handle_extractor."""

from __future__ import annotations

from pathlib import Path
from textwrap import dedent

import pytest

from log_donor.handle_extractor import extract_handle


def test_extracts_handle_from_standard_login_line(tmp_path: Path) -> None:
    log = tmp_path / "g.log"
    log.write_text(
        dedent(
            """\
            <14:30:22> BranchName: sc-alpha-4.7.2-LIVE
            <14:30:25> <AccountLoginCharacterStatus_Character> name Mallachi state STATE_CURRENT
            <14:30:30> Log started.
            """
        )
    )
    assert extract_handle(log) == "Mallachi"


def test_returns_none_when_no_handle_found(tmp_path: Path) -> None:
    log = tmp_path / "g.log"
    log.write_text("just some text without a handle line\n")
    assert extract_handle(log) is None


def test_handles_missing_file(tmp_path: Path) -> None:
    log = tmp_path / "missing.log"
    assert extract_handle(log) is None


def test_reads_only_first_n_lines(tmp_path: Path) -> None:
    """Handle should be found in early lines; deep scans are wasteful."""
    log = tmp_path / "g.log"
    body = "\n".join(["garbage line"] * 5000)
    log.write_text(
        body
        + "\n<14:30:25> <AccountLoginCharacterStatus_Character> name DeepUser state STATE_CURRENT\n"
    )
    # We do not require finding handles past 1000 lines.
    assert extract_handle(log, max_lines=1000) is None


def test_extracts_first_handle_when_multiple_present(tmp_path: Path) -> None:
    log = tmp_path / "g.log"
    log.write_text(
        dedent(
            """\
            <14:30:25> <AccountLoginCharacterStatus_Character> name FirstChar state STATE_CURRENT
            <14:35:00> <AccountLoginCharacterStatus_Character> name SecondChar state STATE_CURRENT
            """
        )
    )
    assert extract_handle(log) == "FirstChar"
```

- [ ] **Step 2: Run tests to verify they fail**

```powershell
cd skills\sc_log_reader
$env:PYTHONPATH = "."
pytest tests\test_handle_extractor.py -v
```

Expected: 5 failures (`extract_handle` not defined).

- [ ] **Step 3: Write `skills/sc_log_reader/log_donor/handle_extractor.py`**

```python
"""Extract the player's SC account handle from a Game.log file."""

from __future__ import annotations

import logging
import re
from pathlib import Path


logger = logging.getLogger(__name__)

# Matches lines like:
#   <14:30:25> <AccountLoginCharacterStatus_Character> name Mallachi state STATE_CURRENT
_HANDLE_RE = re.compile(
    r"<AccountLoginCharacterStatus_Character>\s+name\s+(?P<handle>\S+)\s+state",
)


def extract_handle(log_path: Path, max_lines: int = 1000) -> str | None:
    """Return the player's handle parsed from the first ``max_lines`` of the log.

    Args:
        log_path: Path to a Star Citizen Game.log or logbackup file.
        max_lines: Cap on how many lines to scan. Defaults to 1000.

    Returns:
        The handle as a string, or None if no handle line was found or the
        file could not be read.
    """
    try:
        with log_path.open("r", encoding="utf-8", errors="replace") as fh:
            for i, line in enumerate(fh):
                if i >= max_lines:
                    break
                m = _HANDLE_RE.search(line)
                if m:
                    return m.group("handle")
    except OSError as e:
        logger.warning("could not read log for handle extraction: %s (%s)", log_path, e)
        return None
    return None
```

- [ ] **Step 4: Run tests to verify they pass**

```powershell
pytest tests\test_handle_extractor.py -v
```

Expected: 5 passed.

- [ ] **Step 5: Commit**

```powershell
git add skills/sc_log_reader/log_donor/handle_extractor.py skills/sc_log_reader/tests/test_handle_extractor.py
git commit -m "feat(sc_log_reader): add player handle extractor for log_donor"
```

---

## Task 2: Dedup store (TDD)

**Files:**
- Create: `skills/sc_log_reader/tests/test_dedup.py`
- Create: `skills/sc_log_reader/log_donor/dedup.py`

- [ ] **Step 1: Write the failing test**

```python
"""Tests for log_donor.dedup."""

from __future__ import annotations

from pathlib import Path

import pytest

from log_donor.dedup import DedupStore


@pytest.fixture
def store(tmp_path: Path) -> DedupStore:
    return DedupStore(db_path=tmp_path / "donor_state.sqlite")


def test_initially_empty(store: DedupStore) -> None:
    assert not store.is_uploaded("a" * 64)


def test_record_and_lookup_uploaded(store: DedupStore) -> None:
    store.record_uploaded(
        content_hash="a" * 64,
        original_path="/some/path.log",
        upload_id="upload-1",
    )
    assert store.is_uploaded("a" * 64)
    assert not store.is_uploaded("b" * 64)


def test_record_many_uploaded(store: DedupStore) -> None:
    rows = [
        ("a" * 64, "/p1.log", "upload-1"),
        ("b" * 64, "/p2.log", "upload-1"),
    ]
    store.record_many_uploaded(rows)
    assert store.is_uploaded("a" * 64)
    assert store.is_uploaded("b" * 64)


def test_hash_cache_returns_none_on_miss(store: DedupStore, tmp_path: Path) -> None:
    p = tmp_path / "x.log"
    p.write_text("hello")
    assert store.cached_hash(p) is None


def test_hash_cache_stores_and_reads(store: DedupStore, tmp_path: Path) -> None:
    p = tmp_path / "x.log"
    p.write_text("hello")
    store.put_cached_hash(p, "dead" * 16)
    assert store.cached_hash(p) == "dead" * 16


def test_hash_cache_invalidates_on_size_change(store: DedupStore, tmp_path: Path) -> None:
    p = tmp_path / "x.log"
    p.write_text("hello")
    store.put_cached_hash(p, "dead" * 16)
    p.write_text("hello world longer")  # size changes
    assert store.cached_hash(p) is None


def test_clear_resets_state(store: DedupStore) -> None:
    store.record_uploaded("a" * 64, "/p.log", "u")
    store.clear()
    assert not store.is_uploaded("a" * 64)
```

- [ ] **Step 2: Run tests to verify they fail**

```powershell
pytest tests\test_dedup.py -v
```

Expected: 7 failures.

- [ ] **Step 3: Write `skills/sc_log_reader/log_donor/dedup.py`**

```python
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
        self._conn = sqlite3.connect(str(db_path))
        self._conn.executescript(_SCHEMA)
        self._conn.commit()

    def close(self) -> None:
        self._conn.close()

    def is_uploaded(self, content_hash: str) -> bool:
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
        """rows: iterable of (content_hash, original_path, upload_id)."""
        now = datetime.now(UTC).isoformat()
        self._conn.executemany(
            "INSERT OR REPLACE INTO uploaded_files "
            "(content_hash, original_path, uploaded_at, upload_id) "
            "VALUES (?, ?, ?, ?)",
            [(h, p, now, u) for (h, p, u) in rows],
        )
        self._conn.commit()

    def cached_hash(self, path: Path) -> str | None:
        """Return cached hash if (size, mtime) match, else None."""
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
        cached_size, cached_mtime, cached_hash = row
        if cached_size != st.st_size:
            return None
        # mtime stored as ISO; compare to current file mtime as ISO
        current_mtime = datetime.fromtimestamp(st.st_mtime, tz=UTC).isoformat()
        if cached_mtime != current_mtime:
            return None
        return cached_hash

    def put_cached_hash(self, path: Path, sha256: str) -> None:
        st = path.stat()
        mtime = datetime.fromtimestamp(st.st_mtime, tz=UTC).isoformat()
        self._conn.execute(
            "INSERT OR REPLACE INTO hash_cache "
            "(abs_path, size, mtime, sha256) VALUES (?, ?, ?, ?)",
            (str(path.resolve()), st.st_size, mtime, sha256),
        )
        self._conn.commit()

    def clear(self) -> None:
        self._conn.execute("DELETE FROM uploaded_files")
        self._conn.execute("DELETE FROM hash_cache")
        self._conn.commit()
```

- [ ] **Step 4: Run tests to verify they pass**

```powershell
pytest tests\test_dedup.py -v
```

Expected: 7 passed.

- [ ] **Step 5: Commit**

```powershell
git add skills/sc_log_reader/log_donor/dedup.py skills/sc_log_reader/tests/test_dedup.py
git commit -m "feat(sc_log_reader): add dedup store with hash cache"
```

---

## Task 3: Scanner - install discovery (TDD)

**Files:**
- Create: `skills/sc_log_reader/tests/test_scanner.py`
- Create: `skills/sc_log_reader/log_donor/scanner.py`

- [ ] **Step 1: Write the failing test**

```python
"""Tests for log_donor.scanner."""

from __future__ import annotations

from pathlib import Path

import pytest

from log_donor.scanner import (
    discover_installs,
    parse_game_version,
    discover_candidates,
)


def test_discover_installs_finds_existing_dirs(fake_sc_install: Path) -> None:
    installs = discover_installs(fake_sc_install)
    assert set(installs.keys()) == {"Live", "PTU"}
    assert installs["Live"] == fake_sc_install / "Live"
    assert installs["PTU"] == fake_sc_install / "PTU"


def test_discover_installs_skips_missing_dirs(tmp_path: Path) -> None:
    root = tmp_path / "StarCitizen"
    (root / "Live").mkdir(parents=True)
    # no PTU, no HOTFIX
    installs = discover_installs(root)
    assert set(installs.keys()) == {"Live"}


def test_discover_installs_returns_empty_for_missing_root(tmp_path: Path) -> None:
    assert discover_installs(tmp_path / "nonexistent") == {}


def test_parse_game_version_reads_branchname_and_build(fake_sc_install: Path) -> None:
    version = parse_game_version(fake_sc_install / "Live" / "Game.log")
    assert version == "sc-alpha-4.7.2-LIVE-12345"


def test_parse_game_version_returns_none_for_missing_file(tmp_path: Path) -> None:
    assert parse_game_version(tmp_path / "nope.log") is None
```

- [ ] **Step 2: Run tests to verify they fail**

```powershell
pytest tests\test_scanner.py -v
```

Expected: 5 failures.

- [ ] **Step 3: Write `skills/sc_log_reader/log_donor/scanner.py`** (partial - install discovery + version parse only; candidate discovery comes in Task 4)

```python
"""Scan SC installs for log files eligible for donation."""

from __future__ import annotations

import hashlib
import logging
import re
from pathlib import Path
from typing import Iterable

from log_donor.dedup import DedupStore
from log_donor.handle_extractor import extract_handle
from log_donor.types import Candidate, InstallType


logger = logging.getLogger(__name__)

_INSTALL_NAMES: tuple[InstallType, ...] = ("Live", "PTU", "HOTFIX")
_BRANCH_RE = re.compile(r"BranchName:\s*(?P<branch>\S+)")
_BUILD_RE = re.compile(r"BuildId:\s*(?P<build>\S+)")


def discover_installs(sc_root: Path) -> dict[InstallType, Path]:
    """Return mapping of install name -> install dir for installs that exist."""
    result: dict[InstallType, Path] = {}
    if not sc_root.is_dir():
        return result
    for name in _INSTALL_NAMES:
        candidate = sc_root / name
        if candidate.is_dir():
            result[name] = candidate
    return result


def parse_game_version(game_log: Path) -> str | None:
    """Return composite version string like 'sc-alpha-4.7.2-LIVE-12345' or None."""
    try:
        with game_log.open("r", encoding="utf-8", errors="replace") as fh:
            head = "".join(next(fh, "") for _ in range(40))
    except OSError as e:
        logger.warning("could not read Game.log: %s (%s)", game_log, e)
        return None
    branch_m = _BRANCH_RE.search(head)
    build_m = _BUILD_RE.search(head)
    if branch_m is None or build_m is None:
        return None
    return f"{branch_m.group('branch')}-{build_m.group('build')}"


def is_sc_running() -> bool:
    """True if StarCitizen.exe is in the process list. Returns False if psutil missing."""
    try:
        import psutil
    except ImportError:
        return False
    try:
        for proc in psutil.process_iter(attrs=["name"]):
            if (proc.info.get("name") or "").lower() == "starcitizen.exe":
                return True
    except Exception:
        # psutil can raise on Windows access-denied; assume not running.
        return False
    return False


def _hash_file(path: Path, store: DedupStore | None) -> str:
    """SHA-256 of a file, using DedupStore cache when available."""
    if store is not None:
        cached = store.cached_hash(path)
        if cached is not None:
            return cached
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    digest = h.hexdigest()
    if store is not None:
        store.put_cached_hash(path, digest)
    return digest


# discover_candidates() comes in Task 4
def discover_candidates(*args, **kwargs):  # noqa: ANN001, ANN002, ANN201
    raise NotImplementedError("discover_candidates added in Task 4")
```

- [ ] **Step 4: Run tests to verify they pass**

```powershell
pytest tests\test_scanner.py -v
```

Expected: 5 passed (the `discover_candidates` tests come in Task 4).

- [ ] **Step 5: Commit**

```powershell
git add skills/sc_log_reader/log_donor/scanner.py skills/sc_log_reader/tests/test_scanner.py
git commit -m "feat(sc_log_reader): add install discovery and game-version parse"
```

---

## Task 4: Scanner - candidate discovery with version filter (TDD)

**Files:**
- Modify: `skills/sc_log_reader/tests/test_scanner.py`
- Modify: `skills/sc_log_reader/log_donor/scanner.py`

- [ ] **Step 1: Append failing tests to `tests/test_scanner.py`**

```python
def test_discover_candidates_filters_by_version(
    fake_sc_install: Path, tmp_path: Path, sc_not_running
) -> None:
    store = DedupStore(db_path=tmp_path / "state.sqlite")
    cands = discover_candidates(fake_sc_install, store)
    # Expected:
    #   Live/Game.log (matches) + Live/logbackups/Game_match.log
    #   PTU/Game.log (matches) + PTU/logbackups/Game_match.log
    # Excluded:
    #   Live/logbackups/Game_old.log (version mismatch)
    paths = {c.path.name for c in cands}
    assert "Game.log" in paths
    assert "Game_match.log" in paths
    assert "Game_old.log" not in paths
    assert len(cands) == 4


def test_discover_candidates_excludes_live_gamelog_when_sc_running(
    fake_sc_install: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("log_donor.scanner.is_sc_running", lambda: True)
    store = DedupStore(db_path=tmp_path / "state.sqlite")
    cands = discover_candidates(fake_sc_install, store)
    # Game.log entries excluded; logbackups kept.
    game_log_count = sum(1 for c in cands if c.path.name == "Game.log")
    assert game_log_count == 0
    match_count = sum(1 for c in cands if c.path.name == "Game_match.log")
    assert match_count == 2  # one for Live, one for PTU


def test_discover_candidates_dedups_known_hashes(
    fake_sc_install: Path, tmp_path: Path, sc_not_running
) -> None:
    store = DedupStore(db_path=tmp_path / "state.sqlite")
    # First discovery
    first = discover_candidates(fake_sc_install, store)
    # Record all as uploaded
    for c in first:
        store.record_uploaded(c.sha256, str(c.path), "test-upload")
    # Second discovery should return zero
    second = discover_candidates(fake_sc_install, store)
    assert second == []


def test_discover_candidates_sets_renamed_with_handle(
    fake_sc_install: Path, tmp_path: Path, sc_not_running
) -> None:
    store = DedupStore(db_path=tmp_path / "state.sqlite")
    cands = discover_candidates(fake_sc_install, store)
    for c in cands:
        assert c.renamed.startswith("Mallachi_")


def test_discover_candidates_falls_back_to_unknown_when_no_handle(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("log_donor.scanner.is_sc_running", lambda: False)
    root = tmp_path / "StarCitizen"
    live = root / "Live"
    (live / "logbackups").mkdir(parents=True)
    # Game.log with no handle line
    (live / "Game.log").write_text(
        "<14:30:22> BranchName: sc-alpha-4.7.2-LIVE\n"
        "<14:30:22> BuildId: 12345\n"
    )
    (live / "logbackups" / "Game_match.log").write_text(
        "<14:30:22> BranchName: sc-alpha-4.7.2-LIVE\n"
        "<14:30:22> BuildId: 12345\n"
    )
    store = DedupStore(db_path=tmp_path / "state.sqlite")
    cands = discover_candidates(root, store)
    assert all(c.detected_handle is None for c in cands)
    assert all(c.renamed.startswith("unknown_") for c in cands)
```

Also add this import at the top of `tests/test_scanner.py`:

```python
from log_donor.dedup import DedupStore
```

- [ ] **Step 2: Run tests to verify the new ones fail**

```powershell
pytest tests\test_scanner.py -v
```

Expected: 5 new failures (`discover_candidates` raises `NotImplementedError`).

- [ ] **Step 3: Implement `discover_candidates` in `scanner.py`** - replace the stub at the bottom of `scanner.py` with:

```python
def discover_candidates(
    sc_root: Path,
    store: DedupStore,
) -> list[Candidate]:
    """Walk SC installs, return all log files eligible for donation.

    Filters out:
      - installs that do not exist on disk
      - the live Game.log of any install if StarCitizen.exe is running
      - logbackups whose game version does not match the install's Game.log
      - files whose SHA-256 is already in the dedup store

    Args:
        sc_root: The Star Citizen root dir (parent of Live / PTU / HOTFIX).
        store:   DedupStore for skipping already-uploaded files and caching hashes.

    Returns:
        List of Candidate, sorted by (install, path).
    """
    sc_running = is_sc_running()
    candidates: list[Candidate] = []

    for install, install_dir in discover_installs(sc_root).items():
        game_log = install_dir / "Game.log"
        version = parse_game_version(game_log)
        if version is None:
            logger.warning("install %s has no parseable version, skipping", install)
            continue

        # Live Game.log
        if not sc_running and game_log.is_file():
            cand = _build_candidate(game_log, install, version, store)
            if cand is not None and not store.is_uploaded(cand.sha256):
                candidates.append(cand)

        # logbackups/*.log filtered by version
        logbackups = install_dir / "logbackups"
        if logbackups.is_dir():
            for path in sorted(logbackups.iterdir()):
                if not path.is_file() or path.suffix.lower() != ".log":
                    continue
                file_version = parse_game_version(path)
                if file_version != version:
                    continue
                cand = _build_candidate(path, install, version, store)
                if cand is not None and not store.is_uploaded(cand.sha256):
                    candidates.append(cand)

    return candidates


def _build_candidate(
    path: Path,
    install: InstallType,
    version: str,
    store: DedupStore,
) -> Candidate | None:
    try:
        size = path.stat().st_size
    except OSError:
        return None
    sha256 = _hash_file(path, store)
    handle = extract_handle(path)
    name_prefix = handle if handle else "unknown"
    return Candidate(
        path=path,
        install=install,
        game_version=version,
        size_bytes=size,
        sha256=sha256,
        detected_handle=handle,
        renamed=f"{name_prefix}_{path.name}",
    )
```

Also remove the temporary `discover_candidates` stub at the bottom.

- [ ] **Step 4: Run tests to verify they pass**

```powershell
pytest tests\test_scanner.py -v
```

Expected: 10 passed (5 from Task 3 + 5 new).

- [ ] **Step 5: Commit**

```powershell
git add skills/sc_log_reader/log_donor/scanner.py skills/sc_log_reader/tests/test_scanner.py
git commit -m "feat(sc_log_reader): add candidate discovery with version filter and dedup"
```

---

## Task 5: Uploader - handshake (TDD)

**Files:**
- Create: `skills/sc_log_reader/tests/test_uploader.py`
- Create: `skills/sc_log_reader/log_donor/uploader.py`

- [ ] **Step 1: Write the failing test**

```python
"""Tests for log_donor.uploader.

Mocks the network via httpx.MockTransport.
"""

from __future__ import annotations

import json
from pathlib import Path

import httpx
import pytest

from log_donor.types import Candidate
from log_donor.uploader import Uploader


def _make_candidate(tmp_path: Path, name: str, content: bytes) -> Candidate:
    p = tmp_path / name
    p.write_bytes(content)
    import hashlib
    sha = hashlib.sha256(content).hexdigest()
    return Candidate(
        path=p,
        install="Live",
        game_version="sc-alpha-4.7.2-LIVE-12345",
        size_bytes=len(content),
        sha256=sha,
        detected_handle="Mallachi",
        renamed=f"Mallachi_{name}",
    )


def test_begin_sends_manifest_with_token_header(tmp_path: Path) -> None:
    cand = _make_candidate(tmp_path, "x.log", b"hello world")
    captured: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["method"] = request.method
        captured["url"] = str(request.url)
        captured["token"] = request.headers.get("X-Donor-Token")
        captured["body"] = json.loads(request.content.decode())
        return httpx.Response(
            200,
            json={
                "upload_id": "u-1",
                "files": [
                    {
                        "sha256": cand.sha256,
                        "put_url": "https://r2.example/put",
                        "key": "2026-05-14/u-1/Live/Mallachi_x.log",
                    }
                ],
            },
        )

    transport = httpx.MockTransport(handler)
    up = Uploader(
        worker_url="https://w.example",
        worker_token="secret",
        client_version="sc_log_reader v1.0",
        wingman_version="1.0",
        transport=transport,
    )
    begin = up._begin([cand])
    assert begin.upload_id == "u-1"
    assert captured["method"] == "POST"
    assert captured["url"] == "https://w.example/upload/begin"
    assert captured["token"] == "secret"
    body = captured["body"]
    assert body["files"][0]["sha256"] == cand.sha256
    assert body["files"][0]["renamed"] == cand.renamed


def test_begin_raises_on_401(tmp_path: Path) -> None:
    cand = _make_candidate(tmp_path, "x.log", b"x")

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(401, text="unauthorized")

    transport = httpx.MockTransport(handler)
    up = Uploader(
        worker_url="https://w.example",
        worker_token="wrong",
        client_version="t",
        wingman_version="t",
        transport=transport,
    )
    with pytest.raises(PermissionError):
        up._begin([cand])
```

- [ ] **Step 2: Run tests to verify they fail**

```powershell
pytest tests\test_uploader.py -v
```

Expected: 2 failures.

- [ ] **Step 3: Write `skills/sc_log_reader/log_donor/uploader.py`** (begin only - PUT and complete come in next tasks)

```python
"""Coordinates the handshake with the sc-log-donate Worker and R2 PUTs."""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

import httpx

from log_donor.types import Candidate, FileUploadResult, UploadResult


logger = logging.getLogger(__name__)


@dataclass
class _BeginFileResult:
    sha256: str
    put_url: str | None
    key: str
    already_uploaded: bool


@dataclass
class _BeginResponse:
    upload_id: str
    files: list[_BeginFileResult]


class Uploader:
    """Single-use uploader for one donation cycle.

    Use one instance per click of "Donate logs".
    """

    PUT_TIMEOUT_S = 120.0
    JSON_TIMEOUT_S = 30.0
    MAX_PUT_RETRIES = 3

    def __init__(
        self,
        worker_url: str,
        worker_token: str,
        client_version: str,
        wingman_version: str,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self._worker_url = worker_url.rstrip("/")
        self._worker_token = worker_token
        self._client_version = client_version
        self._wingman_version = wingman_version
        self._client = httpx.Client(transport=transport, timeout=self.JSON_TIMEOUT_S)

    def close(self) -> None:
        self._client.close()

    def _begin(self, candidates: list[Candidate]) -> _BeginResponse:
        body = {
            "client_version": self._client_version,
            "wingman_version": self._wingman_version,
            "files": [
                {
                    "original_name": c.path.name,
                    "renamed": c.renamed,
                    "install": c.install,
                    "game_version": c.game_version,
                    "size_bytes": c.size_bytes,
                    "sha256": c.sha256,
                }
                for c in candidates
            ],
        }
        res = self._client.post(
            f"{self._worker_url}/upload/begin",
            json=body,
            headers={"X-Donor-Token": self._worker_token},
        )
        if res.status_code == 401:
            raise PermissionError("Worker rejected token")
        res.raise_for_status()
        payload = res.json()
        files = [
            _BeginFileResult(
                sha256=f["sha256"],
                put_url=f.get("put_url"),
                key=f["key"],
                already_uploaded=bool(f.get("already_uploaded")),
            )
            for f in payload["files"]
        ]
        return _BeginResponse(upload_id=payload["upload_id"], files=files)
```

- [ ] **Step 4: Run tests to verify they pass**

```powershell
pytest tests\test_uploader.py -v
```

Expected: 2 passed.

- [ ] **Step 5: Commit**

```powershell
git add skills/sc_log_reader/log_donor/uploader.py skills/sc_log_reader/tests/test_uploader.py
git commit -m "feat(sc_log_reader): add uploader handshake (POST /upload/begin)"
```

---

## Task 6: Uploader - PUT to R2 with retry (TDD)

**Files:**
- Modify: `skills/sc_log_reader/tests/test_uploader.py`
- Modify: `skills/sc_log_reader/log_donor/uploader.py`

- [ ] **Step 1: Append failing tests**

```python
def test_put_file_succeeds_on_first_try(tmp_path: Path) -> None:
    cand = _make_candidate(tmp_path, "x.log", b"hello")
    put_calls: list[bytes] = []

    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "PUT":
            put_calls.append(request.content)
            return httpx.Response(200)
        return httpx.Response(404)

    transport = httpx.MockTransport(handler)
    up = Uploader(
        worker_url="https://w.example",
        worker_token="t",
        client_version="t",
        wingman_version="t",
        transport=transport,
    )
    ok = up._put_file(cand, "https://r2.example/put")
    assert ok is True
    assert put_calls == [b"hello"]


def test_put_file_retries_on_5xx_then_succeeds(tmp_path: Path) -> None:
    cand = _make_candidate(tmp_path, "x.log", b"hello")
    counter = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        counter["n"] += 1
        if counter["n"] < 2:
            return httpx.Response(503)
        return httpx.Response(200)

    transport = httpx.MockTransport(handler)
    up = Uploader(
        worker_url="https://w.example",
        worker_token="t",
        client_version="t",
        wingman_version="t",
        transport=transport,
    )
    ok = up._put_file(cand, "https://r2.example/put", sleep=lambda _: None)
    assert ok is True
    assert counter["n"] == 2


def test_put_file_gives_up_after_max_retries(tmp_path: Path) -> None:
    cand = _make_candidate(tmp_path, "x.log", b"hello")

    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(503)

    transport = httpx.MockTransport(handler)
    up = Uploader(
        worker_url="https://w.example",
        worker_token="t",
        client_version="t",
        wingman_version="t",
        transport=transport,
    )
    ok = up._put_file(cand, "https://r2.example/put", sleep=lambda _: None)
    assert ok is False
```

- [ ] **Step 2: Run tests to verify they fail**

```powershell
pytest tests\test_uploader.py -v
```

Expected: 3 new failures.

- [ ] **Step 3: Add `_put_file` to `uploader.py`**

Inside the `Uploader` class, after `_begin`:

```python
def _put_file(
    self,
    candidate: Candidate,
    put_url: str,
    sleep: Callable[[float], None] = time.sleep,
) -> bool:
    """PUT one file to R2. Returns True on success."""
    for attempt in range(self.MAX_PUT_RETRIES):
        try:
            with candidate.path.open("rb") as fh:
                res = self._client.put(
                    put_url,
                    content=fh.read(),
                    timeout=self.PUT_TIMEOUT_S,
                )
            if 200 <= res.status_code < 300:
                return True
            if res.status_code in (408, 425, 429) or res.status_code >= 500:
                logger.info(
                    "PUT %s got %s, retrying (attempt %d)",
                    candidate.renamed, res.status_code, attempt + 1,
                )
                sleep(2 ** attempt)
                continue
            # Non-retryable
            logger.warning(
                "PUT %s failed with %s, not retrying",
                candidate.renamed, res.status_code,
            )
            return False
        except httpx.HTTPError as e:
            logger.info(
                "PUT %s network error: %s, retrying (attempt %d)",
                candidate.renamed, e, attempt + 1,
            )
            sleep(2 ** attempt)
    return False
```

- [ ] **Step 4: Run tests to verify they pass**

```powershell
pytest tests\test_uploader.py -v
```

Expected: 5 passed.

- [ ] **Step 5: Commit**

```powershell
git add skills/sc_log_reader/log_donor/uploader.py skills/sc_log_reader/tests/test_uploader.py
git commit -m "feat(sc_log_reader): add PUT-to-R2 with bounded retries"
```

---

## Task 7: Uploader - orchestrate one full donation cycle (TDD)

**Files:**
- Modify: `skills/sc_log_reader/tests/test_uploader.py`
- Modify: `skills/sc_log_reader/log_donor/uploader.py`

- [ ] **Step 1: Append failing tests**

```python
def test_upload_happy_path(tmp_path: Path) -> None:
    cand_a = _make_candidate(tmp_path, "a.log", b"aaa")
    cand_b = _make_candidate(tmp_path, "b.log", b"bbb")

    events: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/upload/begin":
            events.append("begin")
            return httpx.Response(
                200,
                json={
                    "upload_id": "u-7",
                    "files": [
                        {
                            "sha256": cand_a.sha256,
                            "put_url": "https://r2.example/a",
                            "key": "2026-05-14/u-7/Live/Mallachi_a.log",
                        },
                        {
                            "sha256": cand_b.sha256,
                            "put_url": "https://r2.example/b",
                            "key": "2026-05-14/u-7/Live/Mallachi_b.log",
                        },
                    ],
                },
            )
        if request.url.path == "/upload/complete":
            events.append("complete")
            return httpx.Response(200, json={"upload_id": "u-7", "complete": True})
        if request.method == "PUT":
            events.append(f"put-{request.url}")
            return httpx.Response(200)
        return httpx.Response(404)

    up = Uploader(
        worker_url="https://w.example",
        worker_token="t",
        client_version="t",
        wingman_version="t",
        transport=httpx.MockTransport(handler),
    )
    progress: list[int] = []
    result = up.upload([cand_a, cand_b], progress_cb=progress.append)

    assert result.upload_id == "u-7"
    assert result.succeeded_count == 2
    assert result.failed_count == 0
    assert events[0] == "begin"
    assert events[-1] == "complete"
    assert progress == [1, 2]


def test_upload_marks_already_uploaded(tmp_path: Path) -> None:
    cand = _make_candidate(tmp_path, "x.log", b"x")

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/upload/begin":
            return httpx.Response(
                200,
                json={
                    "upload_id": "u-8",
                    "files": [
                        {
                            "sha256": cand.sha256,
                            "already_uploaded": True,
                            "key": "old-key",
                        }
                    ],
                },
            )
        if request.url.path == "/upload/complete":
            return httpx.Response(200, json={"upload_id": "u-8", "complete": True})
        return httpx.Response(404)

    up = Uploader(
        worker_url="https://w.example",
        worker_token="t",
        client_version="t",
        wingman_version="t",
        transport=httpx.MockTransport(handler),
    )
    result = up.upload([cand], progress_cb=lambda _: None)
    assert result.files[0].already_uploaded is True
    assert result.files[0].succeeded is True   # treated as success for state purposes
    assert result.total_bytes_uploaded == 0    # nothing was actually transferred


def test_upload_partial_failure(tmp_path: Path) -> None:
    cand_a = _make_candidate(tmp_path, "a.log", b"aaa")
    cand_b = _make_candidate(tmp_path, "b.log", b"bbb")

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/upload/begin":
            return httpx.Response(
                200,
                json={
                    "upload_id": "u-9",
                    "files": [
                        {
                            "sha256": cand_a.sha256,
                            "put_url": "https://r2.example/a",
                            "key": "k-a",
                        },
                        {
                            "sha256": cand_b.sha256,
                            "put_url": "https://r2.example/b",
                            "key": "k-b",
                        },
                    ],
                },
            )
        if request.url.path == "/upload/complete":
            return httpx.Response(200, json={"upload_id": "u-9", "complete": True})
        if request.method == "PUT" and "r2.example/a" in str(request.url):
            return httpx.Response(200)
        if request.method == "PUT" and "r2.example/b" in str(request.url):
            return httpx.Response(403)  # non-retryable
        return httpx.Response(404)

    up = Uploader(
        worker_url="https://w.example",
        worker_token="t",
        client_version="t",
        wingman_version="t",
        transport=httpx.MockTransport(handler),
    )
    result = up.upload([cand_a, cand_b], progress_cb=lambda _: None)
    assert result.succeeded_count == 1
    assert result.failed_count == 1
```

- [ ] **Step 2: Run tests to verify they fail**

```powershell
pytest tests\test_uploader.py -v
```

Expected: 3 new failures (`upload` not implemented).

- [ ] **Step 3: Add `upload` and `_complete` to `Uploader`**

```python
def upload(
    self,
    candidates: list[Candidate],
    progress_cb: Callable[[int], None],
) -> UploadResult:
    """Run a full begin → PUTs → complete cycle for the given candidates."""
    result = UploadResult(upload_id=None)
    if not candidates:
        return result

    try:
        begin = self._begin(candidates)
    except PermissionError as e:
        result.error = "Worker rejected token"
        return result
    except httpx.HTTPError as e:
        result.error = f"Worker unreachable: {e}"
        return result
    result.upload_id = begin.upload_id

    # Build sha256 -> Candidate lookup
    by_hash: dict[str, Candidate] = {c.sha256: c for c in candidates}

    done = 0
    for f in begin.files:
        cand = by_hash.get(f.sha256)
        if cand is None:
            continue
        if f.already_uploaded:
            result.files.append(
                FileUploadResult(
                    sha256=f.sha256,
                    renamed=cand.renamed,
                    succeeded=True,
                    already_uploaded=True,
                )
            )
            done += 1
            progress_cb(done)
            continue
        if f.put_url is None:
            result.files.append(
                FileUploadResult(
                    sha256=f.sha256,
                    renamed=cand.renamed,
                    succeeded=False,
                    already_uploaded=False,
                    error="no put_url in Worker response",
                )
            )
            done += 1
            progress_cb(done)
            continue
        ok = self._put_file(cand, f.put_url)
        if ok:
            result.total_bytes_uploaded += cand.size_bytes
        result.files.append(
            FileUploadResult(
                sha256=f.sha256,
                renamed=cand.renamed,
                succeeded=ok,
                already_uploaded=False,
                error=None if ok else "PUT failed after retries",
            )
        )
        done += 1
        progress_cb(done)

    # Always attempt /upload/complete if anything was attempted, so the
    # Worker can finalize what it can.
    try:
        self._complete(begin.upload_id)
    except httpx.HTTPError as e:
        logger.warning(
            "/upload/complete failed for %s: %s (server-side reconciler will sweep)",
            begin.upload_id, e,
        )
        # Not fatal - local state is still correct for what succeeded.

    return result


def _complete(self, upload_id: str) -> None:
    res = self._client.post(
        f"{self._worker_url}/upload/complete",
        json={"upload_id": upload_id},
        headers={"X-Donor-Token": self._worker_token},
    )
    res.raise_for_status()
```

- [ ] **Step 4: Run tests to verify they pass**

```powershell
pytest tests\test_uploader.py -v
```

Expected: 8 passed.

- [ ] **Step 5: Commit**

```powershell
git add skills/sc_log_reader/log_donor/uploader.py skills/sc_log_reader/tests/test_uploader.py
git commit -m "feat(sc_log_reader): orchestrate full donation cycle in uploader"
```

---

## Task 8: Integration test (scanner → uploader → dedup) with mock Worker

**Files:**
- Create: `skills/sc_log_reader/tests/test_log_donor_integration.py`

- [ ] **Step 1: Write the test**

```python
"""End-to-end test stitching scanner, uploader, and dedup with a mock Worker."""

from __future__ import annotations

from pathlib import Path

import httpx

from log_donor.dedup import DedupStore
from log_donor.scanner import discover_candidates
from log_donor.uploader import Uploader


def test_full_donation_cycle_records_dedup(
    fake_sc_install: Path, tmp_path: Path, sc_not_running
) -> None:
    store = DedupStore(db_path=tmp_path / "state.sqlite")
    cands = discover_candidates(fake_sc_install, store)
    assert len(cands) == 4

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/upload/begin":
            body = request.content.decode()
            import json
            payload = json.loads(body)
            files_resp = [
                {
                    "sha256": f["sha256"],
                    "put_url": f"https://r2.example/{f['sha256'][:6]}",
                    "key": f"2026-05-14/u/Live/{f['renamed']}",
                }
                for f in payload["files"]
            ]
            return httpx.Response(
                200,
                json={"upload_id": "u-int", "files": files_resp},
            )
        if request.url.path == "/upload/complete":
            return httpx.Response(200, json={"upload_id": "u-int", "complete": True})
        if request.method == "PUT":
            return httpx.Response(200)
        return httpx.Response(404)

    up = Uploader(
        worker_url="https://w.example",
        worker_token="t",
        client_version="sc_log_reader v1.0",
        wingman_version="1.0",
        transport=httpx.MockTransport(handler),
    )
    result = up.upload(cands, progress_cb=lambda _: None)

    assert result.upload_id == "u-int"
    assert result.succeeded_count == 4
    assert result.failed_count == 0

    # Record successes in dedup store, simulating what the skill will do
    rows = [
        (f.sha256, str(next(c.path for c in cands if c.sha256 == f.sha256)), result.upload_id)
        for f in result.files
        if f.succeeded and not f.already_uploaded
    ]
    store.record_many_uploaded(rows)

    # Second scan should be empty
    second = discover_candidates(fake_sc_install, store)
    assert second == []
```

- [ ] **Step 2: Run the test**

```powershell
pytest tests\test_log_donor_integration.py -v
```

Expected: 1 passed.

- [ ] **Step 3: Commit**

```powershell
git add skills/sc_log_reader/tests/test_log_donor_integration.py
git commit -m "test(sc_log_reader): integration test for full donation cycle"
```

---

## Task 9: UI dialog widgets - consent + preview

**Files:**
- Create: `skills/sc_log_reader/log_donor/ui_dialog.py`

This task is intentionally minimal: it defines pure functions/structs that
`main.py` will wire into the existing Wingman AI dialog primitives. The
Wingman UI framework is event-loop-driven and not easily unit-testable, so
we keep this file thin and put the logic worth testing in `scanner` /
`uploader` / `dedup` (already covered).

- [ ] **Step 1: Read existing dialog primitives**

Look at `skills/sc_log_reader/main.py` and how other skills (e.g.
`sc_accountant`) build dialogs in `accountant_ui/`. Match the pattern.

```powershell
Get-Content skills\sc_log_reader\main.py | Select-String -Pattern "dialog|modal|popup" -Context 1,1
```

(Reading existing patterns is part of the task - no failure expected.)

- [ ] **Step 2: Write `skills/sc_log_reader/log_donor/ui_dialog.py`**

```python
"""UI helpers for the donation flow.

The actual dialog rendering is delegated to the Wingman AI skill framework
through callbacks supplied by main.py. This module only formats text and
builds the data structures the framework consumes.
"""

from __future__ import annotations

from log_donor.types import Candidate, PreviewSummary


CONSENT_BODY = (
    "Donating your Star Citizen logs helps improve sc_log_reader's parsing.\n"
    "\n"
    "Logs contain in-game activity, including:\n"
    "  - In-game chat\n"
    "  - Player handle and character names\n"
    "  - Locations, missions, and deaths\n"
    "  - Hangar / loadout details and vehicle ownership\n"
    "  - In-game purchases and party / org membership\n"
    "  - Kill events and error stacks\n"
    "\n"
    "Logs are sent to a private donation server (Cloudflare R2). They are not\n"
    "made public and are used only to improve the skill.\n"
    "\n"
    "No background uploads happen. Donation only runs when you click the button.\n"
    "You can review what is about to be sent before confirming."
)


def build_preview(
    candidates: list[Candidate],
    already_uploaded_count: int,
) -> PreviewSummary:
    """Aggregate candidate stats for the preview dialog."""
    per_install_counts: dict[str, int] = {}
    per_install_bytes: dict[str, int] = {}
    for c in candidates:
        per_install_counts[c.install] = per_install_counts.get(c.install, 0) + 1
        per_install_bytes[c.install] = per_install_bytes.get(c.install, 0) + c.size_bytes
    return PreviewSummary(
        candidates=candidates,
        total_bytes=sum(c.size_bytes for c in candidates),
        per_install_counts=per_install_counts,
        per_install_bytes=per_install_bytes,
        already_uploaded_count=already_uploaded_count,
    )


def format_summary_header(summary: PreviewSummary) -> str:
    if not summary.candidates:
        if summary.already_uploaded_count:
            return "All eligible logs have already been donated. Thanks!"
        return "No Star Citizen logs found to donate."
    total_mb = summary.total_bytes / 1024 / 1024
    parts = [
        f"{c} {install}"
        for install, c in sorted(summary.per_install_counts.items())
    ]
    breakdown = ", ".join(parts)
    return (
        f"Found {len(summary.candidates)} logs to donate ({total_mb:.1f} MB total). "
        f"Breakdown: {breakdown}."
    )


def format_file_row(c: Candidate) -> str:
    size_kb = c.size_bytes / 1024
    handle = c.detected_handle or "unknown"
    return f"  [{c.install}] {c.renamed} ({size_kb:.0f} KB, handle: {handle})"
```

- [ ] **Step 3: Sanity-check imports**

```powershell
python -c "from log_donor.ui_dialog import build_preview, format_summary_header, CONSENT_BODY; print('ok')"
```

Expected: `ok`.

- [ ] **Step 4: Commit**

```powershell
git add skills/sc_log_reader/log_donor/ui_dialog.py
git commit -m "feat(sc_log_reader): add UI helpers for consent and preview dialogs"
```

---

## Task 10: Wire the "Donate logs" button into the skill settings panel

**Files:**
- Modify: `skills/sc_log_reader/default_config.yaml`
- Modify: `skills/sc_log_reader/main.py`

- [ ] **Step 1: Add donor config block to `default_config.yaml`**

Append (or merge into existing config):

```yaml
donor:
  worker_url: "https://sc-log-donate.<your-subdomain>.workers.dev"
  worker_token: "__INJECT_AT_BUILD__"
  consent_accepted_at: null
  last_donation_at: null
  state_db_path: "${APPDATA}/Wingman/sc_log_reader/donor_state.sqlite"
```

- [ ] **Step 2: Read `main.py` to understand the settings panel hook**

```powershell
Get-Content skills\sc_log_reader\main.py
```

Look for where the skill registers UI widgets / settings sections. Existing
patterns will dictate exact wiring - match them.

- [ ] **Step 3: Add the donation orchestration to `main.py`**

Add this function to `main.py` (top-level, near other skill methods):

```python
def _run_donation_flow(self) -> None:
    """Orchestrate one donation cycle: scan, consent, preview, upload."""
    import os
    from pathlib import Path

    from log_donor.dedup import DedupStore
    from log_donor.scanner import discover_candidates
    from log_donor.uploader import Uploader
    from log_donor.ui_dialog import (
        CONSENT_BODY,
        build_preview,
        format_summary_header,
        format_file_row,
    )

    config = self.config.get("donor", {})
    state_db_path = Path(os.path.expandvars(config["state_db_path"]))
    store = DedupStore(db_path=state_db_path)

    # Consent gate
    if not config.get("consent_accepted_at"):
        accepted = self.show_consent_dialog(  # framework primitive
            title="Donate Star Citizen logs",
            body=CONSENT_BODY,
        )
        if not accepted:
            return
        from datetime import UTC, datetime
        config["consent_accepted_at"] = datetime.now(UTC).isoformat()
        self.save_config()

    # Discover candidates
    sc_root = Path(self.config["install"]["root"])  # existing skill config
    candidates = discover_candidates(sc_root, store)
    summary = build_preview(candidates, already_uploaded_count=0)

    # Preview dialog
    proceed = self.show_preview_dialog(
        title="Donate Star Citizen logs",
        header=format_summary_header(summary),
        detail="\n".join(format_file_row(c) for c in summary.candidates),
        proceed_enabled=bool(summary.candidates),
    )
    if not proceed or not summary.candidates:
        return

    # Upload
    uploader = Uploader(
        worker_url=config["worker_url"],
        worker_token=config["worker_token"],
        client_version=self.skill_version,
        wingman_version=self.wingman_version,
    )
    try:
        progress = self.start_progress(total=len(summary.candidates), title="Donating logs")
        result = uploader.upload(summary.candidates, progress_cb=progress.update)
    finally:
        uploader.close()
        progress.close()

    # Record successful hashes
    rows = []
    for f in result.files:
        if f.succeeded and not f.already_uploaded:
            cand = next(c for c in summary.candidates if c.sha256 == f.sha256)
            rows.append((f.sha256, str(cand.path), result.upload_id or ""))
    store.record_many_uploaded(rows)

    # Update last_donation_at
    from datetime import UTC, datetime
    config["last_donation_at"] = datetime.now(UTC).isoformat()
    self.save_config()

    # Outcome toast
    if result.error:
        self.toast(f"Donation failed: {result.error}")
    elif result.failed_count > 0:
        self.toast(
            f"Donated {result.succeeded_count} of "
            f"{len(summary.candidates)} logs. {result.failed_count} will retry next time."
        )
    else:
        mb = result.total_bytes_uploaded / 1024 / 1024
        self.toast(f"Thanks! Donated {result.succeeded_count} logs ({mb:.1f} MB).")

    store.close()
```

Then register a button in the settings panel section that calls
`self._run_donation_flow()`. Exact API depends on Wingman AI's settings
plumbing - follow the same pattern other buttons in the existing skill use.

Section layout to render (text labels for the framework to materialize):

```
HEADER: Help improve this skill
BUTTON: Donate logs         -> self._run_donation_flow()
LABEL:  Last donation: {donor.last_donation_at or "Never"}
LINK:   What gets uploaded? -> self.show_consent_dialog(...) read-only
LINK:   Open log folder     -> self.os_open(self.config["install"]["root"] / "Live" / "logbackups")
LINK:   Forget my donations -> resets DedupStore + clears donor.consent_accepted_at
```

- [ ] **Step 4: Manually launch Wingman AI and verify the new section appears**

(Manual step - no automated test for UI rendering.)

```powershell
# From wingman-ai root, however the skill is normally loaded during dev:
python -m wingman_ai  # or the project's actual entry script
```

Open the skill settings; confirm a "Help improve this skill" section is
visible with the Donate logs button.

- [ ] **Step 5: Commit**

```powershell
git add skills/sc_log_reader/default_config.yaml skills/sc_log_reader/main.py
git commit -m "feat(sc_log_reader): wire Donate logs button into settings panel"
```

---

## Task 11: Build-time DONOR_TOKEN injection

**Files:**
- Modify: `skills/sc_log_reader/update_release.py`

- [ ] **Step 1: Read existing `update_release.py`**

```powershell
Get-Content skills\sc_log_reader\update_release.py
```

Understand how it currently copies files into `release_version/` and what
substitutions it performs.

- [ ] **Step 2: Add token injection**

In `update_release.py`, after copying `default_config.yaml` into
`release_version/`, add:

```python
import os
from pathlib import Path

def inject_donor_token(release_root: Path) -> None:
    """Replace __INJECT_AT_BUILD__ in release_version default_config.yaml.

    Reads token from env var DONOR_TOKEN_BUILD. Fails loudly if missing.
    """
    token = os.environ.get("DONOR_TOKEN_BUILD")
    if not token:
        raise RuntimeError(
            "DONOR_TOKEN_BUILD env var is not set. Refusing to build release "
            "with placeholder donor token."
        )
    cfg_path = release_root / "default_config.yaml"
    text = cfg_path.read_text(encoding="utf-8")
    if "__INJECT_AT_BUILD__" not in text:
        raise RuntimeError(
            f"Placeholder __INJECT_AT_BUILD__ not found in {cfg_path}. "
            "Either the substitution already happened or the placeholder was renamed."
        )
    cfg_path.write_text(
        text.replace("__INJECT_AT_BUILD__", token),
        encoding="utf-8",
    )
```

Then call `inject_donor_token(release_root)` from whatever function builds
the release artifact. Exact placement depends on the existing structure -
match the order: copy files first, then mutate.

- [ ] **Step 3: Verify the build still works with the env var set**

```powershell
$env:DONOR_TOKEN_BUILD = "test-token-for-build-only"
python skills\sc_log_reader\update_release.py
Get-Content skills\sc_log_reader\release_version\default_config.yaml | Select-String "worker_token"
```

Expected: line shows `worker_token: "test-token-for-build-only"` (not `__INJECT_AT_BUILD__`).

- [ ] **Step 4: Verify the build fails when the env var is missing**

```powershell
Remove-Item Env:\DONOR_TOKEN_BUILD
python skills\sc_log_reader\update_release.py
```

Expected: non-zero exit, error message about missing `DONOR_TOKEN_BUILD`.

- [ ] **Step 5: Commit**

```powershell
git add skills/sc_log_reader/update_release.py
git commit -m "build(sc_log_reader): inject DONOR_TOKEN into release default_config"
```

---

## Task 12: DEVLOG and TODO updates

**Files:**
- Modify: `skills/sc_log_reader/DEVLOG.md`
- Modify: `skills/sc_log_reader/TODO.md`

Per the global documentation rules (`~/.claude/rules/documentation.md`), the
DEVLOG and TODO must reflect this work.

- [ ] **Step 1: Append a new entry to `DEVLOG.md`**

```markdown
## 2026-05-14 - Log donation feature

Added `log_donor/` package and "Donate logs" settings button.

**What it does:** Scans Live / PTU / HOTFIX installs, filters logbackups
(plus active Game.log when SC is not running) to match the current Game.log
version per install, dedupes by SHA-256, then uploads via the
`sc-log-donate` Cloudflare Worker. Files are renamed in-flight to
`{handle_or_unknown}_{original_name}` so contributor attribution is visible
in R2.

**New modules:** `log_donor/scanner.py`, `handle_extractor.py`, `dedup.py`,
`uploader.py`, `ui_dialog.py`, `types.py`.

**Config additions:** `donor.*` block in `default_config.yaml`. Real token
injected at release-build time by `update_release.py` from
`DONOR_TOKEN_BUILD` env var.

**Companion repo:** `sc-log-donate` (separate, outside `wingman-ai`).
```

- [ ] **Step 2: Append open items to `TODO.md`** as appropriate

```markdown
- [ ] Wire donation toast / progress / dialog framework calls to match
      whatever the rest of `main.py` does (placeholder calls used currently)
- [ ] Verify the SC install path config key (`install.root`) matches the
      key the rest of the skill uses; rename if needed
- [ ] Once `sc-log-donate` Worker is live, run TESTER.md Smoke 5 against it
```

- [ ] **Step 3: Commit**

```powershell
git add skills/sc_log_reader/DEVLOG.md skills/sc_log_reader/TODO.md
git commit -m "docs(sc_log_reader): add log donation feature notes to DEVLOG and TODO"
```

---

## Task 13: Final test pass and manual smoke

- [ ] **Step 1: Run the full test suite**

```powershell
cd skills\sc_log_reader
$env:PYTHONPATH = "."
pytest tests\ -v
```

Expected: all tests pass.

- [ ] **Step 2: Type-check (if mypy is configured project-wide)**

```powershell
mypy log_donor\
```

Expected: no errors.

- [ ] **Step 3: Lint**

```powershell
ruff check log_donor\ tests\
ruff format --check log_donor\ tests\
```

Expected: no errors.

- [ ] **Step 4: Manual smoke (only when the Worker is live in staging)**

Follow `sc-log-donate/TESTER.md` Smoke 5 ("skill integration"):

1. Install patched skill in Wingman AI
2. Open settings → "Help improve this skill" → "Donate logs"
3. Click through consent dialog (first time only)
4. Verify preview dialog shows real log counts from your installs
5. Click Upload
6. Verify R2 dashboard receives files
7. Re-press button: confirm dialog reports "all eligible logs already donated"

- [ ] **Step 5: Final commit (only if any fixes were needed in step 4)**

```powershell
git status
# if changes:
git add <files>
git commit -m "fix(sc_log_reader): post-smoke adjustments"
```

---

## Self-review checklist

### Spec coverage

| Spec section | Implemented in task |
|---|---|
| §3 - package layout (`log_donor/`) | Tasks 0–9 |
| §3 - `scanner.py` install discovery + version filter | Tasks 3, 4 |
| §3 - handle extraction | Task 1 |
| §3 - file rename `{handle}_{name}` | Task 4 (`_build_candidate`) |
| §3 - settings panel UI | Task 10 |
| §3 - config additions to `default_config.yaml` | Task 10 |
| §3 - local SQLite (`uploaded_files` + `hash_cache`) | Task 2 |
| §3 - SC running detection | Task 3 (`is_sc_running`) |
| §5 - skill-side dedup with hash cache | Tasks 2, 4 |
| §6 - data flow scan → preview → upload | Tasks 4, 9, 10 |
| §6 - handshake payload shape | Task 5 |
| §6 - local state recorded only on success | Task 10 (`record_many_uploaded` after upload) |
| §7 - error handling: 401 → PermissionError, 5xx → retry, network → returns error | Tasks 5, 6, 7 |
| §7 - partial-failure preserves successful hashes | Tasks 7, 10 |
| §7 - `/upload/complete` failure non-fatal | Task 7 (`_complete` failure logged not raised) |
| §8 - consent gate before first donation | Task 10 (consent_accepted_at check) |
| §8 - "Forget my donations" surface | Task 10 (link wired to `DedupStore.clear()`) |
| §10 - DEVLOG / TODO updates | Task 12 |

No gaps.

### Placeholder scan

- No "TBD", "TODO" in code blocks (the TODO entries in Task 12 are
  legitimately TODOs - they're in TODO.md, exactly where TODOs belong).
- No "Similar to Task N" - all task code is repeated explicitly.
- No vague "Add appropriate error handling" - error paths are spelled out.

### Type consistency

- `Candidate` dataclass shape (Task 0) consistently used across `scanner`,
  `uploader`, `ui_dialog`.
- `InstallType` literal type `"Live" | "PTU" | "HOTFIX"` used in
  `types.py`, `scanner.py`, tests.
- `Uploader.upload(candidates, progress_cb)` signature matches `main.py`
  call site.
- `DedupStore.record_many_uploaded` accepts `Iterable[tuple[str, str, str]]`
  - call sites in tests and `main.py` pass `list[tuple[str, str, str]]`,
  which satisfies the iterable.
- Worker contract (request/response shapes) matches what the Worker plan
  emits in its `types.ts` (verified by hand against Task 2 of the Worker
  plan).

No mismatches.
