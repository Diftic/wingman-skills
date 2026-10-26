"""Choosing between bundled and downloaded data, and checking GitHub for newer revisions (no network)."""

from __future__ import annotations

import asyncio
import hashlib
import json
from pathlib import Path

import pytest

from sc_data import DATA_URL, DataError, DataStore, validate_url

URL = DATA_URL


def system_bytes(name: str, revision: int, fmt: int = 1) -> bytes:
    data = {"system": name, "format": fmt, "revision": revision,
            "solar": {"locations": {name: {"type": "star", "pos_km": [0, 0, 0]}}},
            "planetary": {}, "lunar": {}}
    return json.dumps(data).encode()


def index_bytes(files: dict[str, bytes], revisions: dict[str, int]) -> bytes:
    systems = {k: {"file": f"{k}.json", "revision": revisions[k],
                   "sha256": hashlib.sha256(raw).hexdigest()} for k, raw in files.items()}
    return json.dumps({"format": 1, "revision": max(revisions.values()), "systems": systems}).encode()


class FakeGitHub:
    def __init__(self, files: dict[str, bytes]) -> None:
        self.files = files
        self.requests: list[str] = []
        self.fail = False

    async def __call__(self, url: str) -> tuple[int, bytes]:
        self.requests.append(url)
        if self.fail:
            raise OSError("offline")
        name = url.removeprefix(URL)
        return (200, self.files[name]) if name in self.files else (404, b"")


@pytest.fixture
def dirs(tmp_path: Path) -> tuple[Path, Path]:
    bundled, cache = tmp_path / "bundled", tmp_path / "cache"
    bundled.mkdir()
    (bundled / "alpha.json").write_bytes(system_bytes("Alpha", 1))
    return bundled, cache


def check(store: DataStore, fetch: FakeGitHub) -> list[str]:
    return asyncio.run(store.check(fetch))


def test_start_takes_the_higher_revision_of_bundled_and_cached(dirs):
    bundled, cache = dirs
    cache.mkdir()
    (cache / "alpha.json").write_bytes(system_bytes("Alpha", 5))
    assert DataStore(bundled, cache).status.sources == {"alpha": "downloaded"}
    (bundled / "alpha.json").write_bytes(system_bytes("Alpha", 9))
    store = DataStore(bundled, cache)
    assert (store.status.sources, store.status.revisions) == ({"alpha": "bundled"}, {"alpha": 9})


def test_newer_revision_is_downloaded_validated_and_cached(dirs):
    bundled, cache = dirs
    new = system_bytes("Alpha", 2)
    store = DataStore(bundled, cache)
    assert check(store, FakeGitHub({"index.json": index_bytes({"alpha": new}, {"alpha": 2}),
                                    "alpha.json": new})) == ["Alpha"]
    assert store.status.revisions["alpha"] == 2
    assert (cache / "alpha.json").read_bytes() == new
    assert DataStore(bundled, cache).status.sources == {"alpha": "downloaded"}


def test_unchanged_revision_downloads_only_the_index(dirs):
    bundled, cache = dirs
    fetch = FakeGitHub({"index.json": index_bytes({"alpha": system_bytes("Alpha", 1)}, {"alpha": 1})})
    assert check(DataStore(bundled, cache), fetch) == []
    assert fetch.requests == [URL + "index.json"]


def test_a_new_system_in_the_index_is_added(dirs):
    bundled, cache = dirs
    beta = system_bytes("Beta", 1)
    store = DataStore(bundled, cache)
    check(store, FakeGitHub({"index.json": index_bytes({"beta": beta}, {"beta": 1}), "beta.json": beta}))
    assert set(store.systems) == {"Alpha", "Beta"}


def test_a_file_that_fails_its_checksum_is_not_used(dirs):
    bundled, cache = dirs
    good, bad = system_bytes("Alpha", 2), system_bytes("Alpha", 2).replace(b'"pos_km": [0', b'"pos_km": [7')
    store = DataStore(bundled, cache)
    assert check(store, FakeGitHub({"index.json": index_bytes({"alpha": good}, {"alpha": 2}),
                                    "alpha.json": bad})) == []
    assert store.status.revisions["alpha"] == 1
    assert "checksum" in store.status.problem
    assert not (cache / "alpha.json").exists()


def test_a_newer_data_format_is_refused(dirs):
    bundled, cache = dirs
    future = system_bytes("Alpha", 2, fmt=2)
    store = DataStore(bundled, cache)
    assert check(store, FakeGitHub({"index.json": index_bytes({"alpha": future}, {"alpha": 2}),
                                    "alpha.json": future})) == []
    assert "newer SC_distances skill" in store.status.problem


def test_offline_keeps_the_data_it_has(dirs):
    bundled, cache = dirs
    fetch = FakeGitHub({})
    fetch.fail = True
    store = DataStore(bundled, cache)
    assert check(store, fetch) == []
    assert set(store.systems) == {"Alpha"}
    assert "offline" in store.status.problem


@pytest.mark.parametrize("url", ["http://raw.githubusercontent.com/a/b/main/data/",
                                 "https://github.com/a/b/raw/main/data/",
                                 "https://user:pw@raw.githubusercontent.com/a/b/main/data/",
                                 "https://raw.githubusercontent.com/a/b/main/data/?x=1"])
def test_only_plain_raw_github_https_urls_are_accepted(url):
    with pytest.raises(DataError):
        validate_url(url)
