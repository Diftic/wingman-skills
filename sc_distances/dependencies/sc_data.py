"""Where the location data comes from, and how it stays current (same idea as the SC Log Reader's rules).

The skill ships data/<system>.json. Star Citizen patches move and add locations far more often than
the skill is reinstalled, so the maintained copy lives on GitHub. The skill reads index.json there
(small: one revision and checksum per system file) at start and every few hours, and downloads only
the system files whose revision went up. A download is used only when it validates; it is cached in
the skill's generated-files folder. At start, each system takes the higher revision of the bundled
file and the cached download. Offline, the skill keeps working with what it has.

Pure logic, no Wingman imports. fetch() is injectable so tests run without a network.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import tempfile
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Awaitable, Callable, Optional
from urllib.parse import urlsplit

DATA_URL = "https://raw.githubusercontent.com/Diftic/wingman-skills/main/sc_distances/data/"
INDEX_NAME = "index.json"
FORMAT = 1  # highest data format this code understands
MAX_FILE_BYTES = 16 * 1024 * 1024
MAX_NAME_CHARS = 120
FETCH_TIMEOUT_SECONDS = 15
_KEY = re.compile(r"^[a-z0-9_]{1,40}$")

# fetch(url) -> (HTTP status, body). Errors raise; check() turns them into a status problem.
Fetch = Callable[[str], Awaitable[tuple[int, bytes]]]


class DataError(ValueError):
    """A data or index file, or a URL, that must not be used."""


@dataclass
class DataStatus:
    revisions: dict[str, int] = field(default_factory=dict)
    sources: dict[str, str] = field(default_factory=dict)  # "bundled" or "downloaded"
    last_check: Optional[float] = None
    problem: Optional[str] = None


def validate_url(url: str) -> str:
    """Only a plain HTTPS folder on raw.githubusercontent.com: no credentials, query or fragment."""
    parts = urlsplit(url)
    if (parts.scheme != "https" or parts.hostname != "raw.githubusercontent.com"
            or parts.username or parts.password or parts.port or parts.query or parts.fragment):
        raise DataError("data URL must be an https://raw.githubusercontent.com/... folder")
    return url if url.endswith("/") else url + "/"


def _write_atomic(path: Path, raw: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(prefix=path.name + ".", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(raw)
        os.replace(name, path)
    finally:
        if os.path.exists(name):
            os.unlink(name)


def _json(raw: bytes) -> dict:
    if len(raw) > MAX_FILE_BYTES:
        raise DataError("file is too large")
    try:
        data = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, ValueError) as error:
        raise DataError(f"not valid JSON: {error}") from None
    if not isinstance(data, dict):
        raise DataError("not a JSON object")
    fmt = data.get("format")
    if not isinstance(fmt, int) or isinstance(fmt, bool) or fmt < 1:
        raise DataError("missing format")
    if fmt > FORMAT:
        raise DataError(f"data format {fmt} needs a newer SC_distances skill")
    return data


def _check_locations(locations: object, where: str) -> None:
    if not isinstance(locations, dict):
        raise DataError(f"{where}: locations is not an object")
    for name, entry in locations.items():
        pos = entry.get("pos_km") if isinstance(entry, dict) else None
        if (not isinstance(name, str) or not name or len(name) > MAX_NAME_CHARS
                or not isinstance(pos, list) or len(pos) != 3
                or not all(isinstance(c, (int, float)) and not isinstance(c, bool) for c in pos)):
            raise DataError(f"{where}: bad location entry {str(name)[:40]!r}")


def validate_system(raw: bytes, sha256: Optional[str] = None) -> dict:
    """Parse and check one system file. Raises DataError."""
    if sha256 is not None and hashlib.sha256(raw).hexdigest() != sha256:
        raise DataError("checksum does not match the index")
    data = _json(raw)
    if not isinstance(data.get("system"), str) or not isinstance(data.get("revision"), int):
        raise DataError("missing system or revision")
    solar = data.get("solar")
    if not isinstance(solar, dict):
        raise DataError("missing solar")
    _check_locations(solar.get("locations"), "solar")
    for group in ("planetary", "lunar"):
        bodies = data.get(group)
        if not isinstance(bodies, dict):
            raise DataError(f"missing {group}")
        for body, g in bodies.items():
            if not isinstance(g, dict) or not isinstance(g.get("radius_km"), (int, float)):
                raise DataError(f"{group}.{str(body)[:40]}: missing radius_km")
            if body not in solar["locations"]:
                raise DataError(f"{group}.{str(body)[:40]}: body is not in solar")
            _check_locations(g.get("locations"), f"{group}.{body}")
    return data


def validate_index(raw: bytes) -> dict:
    """Parse and check index.json: {format, revision, systems: {key: {file, revision, sha256}}}."""
    data = _json(raw)
    systems = data.get("systems")
    if not isinstance(systems, dict):
        raise DataError("index has no systems")
    for key, item in systems.items():
        if (not _KEY.match(str(key)) or not isinstance(item, dict)
                or item.get("file") != f"{key}.json" or not isinstance(item.get("revision"), int)
                or not re.fullmatch(r"[0-9a-f]{64}", str(item.get("sha256", "")))):
            raise DataError(f"index entry {str(key)[:40]!r} is malformed")
    return data


class DataStore:
    """Holds the running system data and replaces a system when GitHub has a newer revision."""

    def __init__(self, bundled_dir: Path | str, cache_dir: Path | str, url: str = DATA_URL) -> None:
        self.url = validate_url(url)
        self._bundled = Path(bundled_dir)
        self._cache = Path(cache_dir)
        self.status = DataStatus()
        self.systems: dict[str, dict] = {}
        self._load_best()

    def _read(self, path: Path) -> Optional[dict]:
        try:
            return validate_system(path.read_bytes())
        except (OSError, DataError):
            return None

    def _load_best(self) -> None:
        keys = {p.stem for d in (self._bundled, self._cache) if d.is_dir()
                for p in d.glob("*.json") if p.name != INDEX_NAME and _KEY.match(p.stem)}
        for key in sorted(keys):
            bundled = self._read(self._bundled / f"{key}.json")
            cached = self._read(self._cache / f"{key}.json")
            # A skill update can ship newer data than the last download.
            if cached and (not bundled or cached["revision"] > bundled["revision"]):
                self._use(key, cached, "downloaded")
            elif bundled:
                self._use(key, bundled, "bundled")

    def _use(self, key: str, data: dict, source: str) -> None:
        self.systems = {**self.systems, data["system"]: data}
        self.status.revisions = {**self.status.revisions, key: data["revision"]}
        self.status.sources = {**self.status.sources, key: source}

    async def check(self, fetch: Optional[Fetch] = None) -> list[str]:
        """Ask GitHub for newer data. Returns the names of the systems that were updated. Never raises."""
        fetch = fetch or http_fetch
        self.status.last_check = time.time()
        try:
            status, raw = await fetch(self.url + INDEX_NAME)
            if status != 200:
                raise DataError(f"index: HTTP {status}")
            index = validate_index(raw)
        except Exception as error:  # noqa: BLE001 - network or data problem; keep what we have
            self.status.problem = f"update check failed: {error}"
            return []
        updated, problems = [], []
        for key, item in sorted(index["systems"].items()):
            if item["revision"] <= self.status.revisions.get(key, -1):
                continue
            try:
                status, raw = await fetch(self.url + item["file"])
                if status != 200:
                    raise DataError(f"HTTP {status}")
                data = validate_system(raw, item["sha256"])
                if data["revision"] != item["revision"]:
                    raise DataError("revision does not match the index")
            except Exception as error:  # noqa: BLE001
                problems.append(f"{key}: {error}")
                continue
            try:
                _write_atomic(self._cache / item["file"], raw)
            except OSError:
                pass  # still use it for this run; the next start downloads it again
            self._use(key, data, "downloaded")
            updated.append(data["system"])
        self.status.problem = "; ".join(problems) or None
        return updated


async def http_fetch(url: str) -> tuple[int, bytes]:
    """Default fetch: GET without redirects, with a size cap. aiohttp ships with Wingman Core."""
    import aiohttp

    timeout = aiohttp.ClientTimeout(total=FETCH_TIMEOUT_SECONDS)
    headers = {"Accept": "application/json", "User-Agent": "WingmanAI-SC_distances"}
    async with aiohttp.ClientSession(timeout=timeout) as session:
        async with session.get(url, headers=headers, allow_redirects=False) as resp:
            if resp.status != 200:
                return resp.status, b""
            chunks, size = [], 0
            while size <= MAX_FILE_BYTES:
                chunk = await resp.content.readany()
                if not chunk:
                    break
                chunks.append(chunk)
                size += len(chunk)
            return resp.status, b"".join(chunks)[: MAX_FILE_BYTES + 1]
