"""Tests for log_donor.donor_ui.app.DonorServer's FastAPI routes.

Uses fastapi.testclient.TestClient against server._app directly -- start()
is never called, so no real socket is bound. server._port is whatever was
passed to the constructor, and TestClient's base_url is pinned to that same
host:port so the Host-header check (see verify_host in app.py) passes for
the "legitimate" requests and can be deliberately broken for the negative
tests.
"""

from __future__ import annotations

import threading
import time
from pathlib import Path
from textwrap import dedent

from fastapi.testclient import TestClient

from log_donor.dedup import DedupStore
from log_donor.donor_ui.app import DonorServer
from log_donor.scanner import MIN_UPLOAD_FILE_BYTES
from log_donor.types import UploadResult


_PORT = 17864


def _gamelog_text(file_version: str, tag: str, pad: bool = True) -> str:
    # `tag` makes Game.log and its logbackup byte-distinct (and therefore
    # sha256-distinct) even though they share a FileVersion -- the shared
    # fake_sc_install fixture writes byte-identical content for its "match"
    # pair, which collapses their hashes and defeats sha256-based filtering
    # tests.
    header = dedent(
        f"""\
        <2026-05-14T13:41:52.133Z> Log started on Thu May 14 13:41:52 2026 [{tag}]
        <2026-05-14T13:41:52.133Z> Built on May 12 2026 16:25:50
        <2026-05-14T13:41:52.133Z> FileVersion: {file_version}
        <2026-05-14T13:41:52.133Z> ProductVersion: {file_version}
        <2026-05-14T13:42:05.194Z> [Notice] <AccountLoginCharacterStatus_Character> Character: createdAt 1778766100411 - geid 204821589567 - name Mallachi - state STATE_UNSPECIFIED [Team_GameServices][Login]
        """
    )
    if not pad:
        return header
    # Padded past MIN_UPLOAD_FILE_BYTES so these candidates survive the
    # donor's client-side minimum-size cap (tag keeps the padding itself
    # byte-distinct between Game.log and its logbackup too).
    return header + ("X" * MIN_UPLOAD_FILE_BYTES + tag + "\n")


def _make_live_install(root: Path, version: str = "4.8.180.28520", pad: bool = True) -> Path:
    """Build a synthetic Live-only SC install with two distinct-content files."""
    live = root / "Live"
    (live / "logbackups").mkdir(parents=True)
    (live / "Game.log").write_text(_gamelog_text(version, tag="live", pad=pad))
    (live / "logbackups" / "Game_match.log").write_text(
        _gamelog_text(version, tag="backup", pad=pad)
    )
    return root


def _make_server(sc_root: Path | None, store: DedupStore, port: int = _PORT) -> DonorServer:
    return DonorServer(
        sc_root_provider=lambda: sc_root,
        store=store,
        worker_url_provider=lambda: "https://w.example",
        worker_token_provider=lambda: "worker-token",
        client_version="sc_log_reader-test",
        wingman_version="1.0",
        port=port,
    )


def _client(server: DonorServer) -> TestClient:
    return TestClient(server._app, base_url=f"http://127.0.0.1:{server.port}")


def _session_headers(server: DonorServer) -> dict[str, str]:
    # White-box: tests run in-process, so we can read the token straight off
    # the server instance instead of scraping it out of the served HTML.
    return {"X-Donor-Session": server._session_token}


def _wait_until_done(client: TestClient, timeout: float = 5.0) -> dict:
    deadline = time.time() + timeout
    while time.time() < deadline:
        data = client.get("/api/status").json()
        if data["phase"] == "done":
            return data
        time.sleep(0.02)
    raise TimeoutError("upload job did not reach phase=done in time")


class _FakeUploader:
    """Records what candidates it was asked to upload; never touches the network."""

    last_candidates: list | None = None

    def __init__(self, **_kwargs) -> None:
        pass

    def __enter__(self) -> "_FakeUploader":
        return self

    def __exit__(self, *_args: object) -> None:
        pass

    def upload(self, candidates, progress_cb):
        _FakeUploader.last_candidates = list(candidates)
        for i, _ in enumerate(candidates, start=1):
            progress_cb(i)
        return UploadResult(upload_id="fake-upload", files=[], total_bytes_uploaded=0)


# ---------------------------------------------------------------------------
# Preview JSON shape
# ---------------------------------------------------------------------------


def test_preview_returns_full_shape_with_candidates(
    fake_sc_install: Path, tmp_path: Path, sc_not_running
) -> None:
    store = DedupStore(db_path=tmp_path / "state.sqlite")
    server = _make_server(fake_sc_install, store)
    client = _client(server)

    r = client.get("/api/preview")
    assert r.status_code == 200
    data = r.json()

    assert data["sc_root_configured"] is True
    assert data["error"] is None
    assert isinstance(data["header"], str) and data["header"]
    assert isinstance(data["consent_text"], str) and "Star Citizen" in data["consent_text"]
    assert data["already_uploaded_count"] == 0
    assert data["skipped_undersize_count"] == 0
    assert data["skipped_oversize_count"] == 0
    assert data["trimmed_count"] == 0
    # Three candidates from the Live install: Game.log and Game_match.log
    # (byte-identical, so a shared sha256) plus Game_old.log. Under the new
    # per-file-version retention design the older-build Game_old.log is
    # offered too; server-side policy decides what to keep.
    assert len(data["candidates"]) == 3
    for c in data["candidates"]:
        assert set(c.keys()) == {"sha256", "renamed", "install", "size_bytes", "handle"}
        assert c["install"] == "Live"
        assert len(c["sha256"]) == 64


def test_preview_reports_sc_root_not_configured(tmp_path: Path) -> None:
    store = DedupStore(db_path=tmp_path / "state.sqlite")
    server = _make_server(None, store)
    client = _client(server)

    data = client.get("/api/preview").json()
    assert data["sc_root_configured"] is False
    assert data["error"] is None
    assert data["candidates"] == []


def test_preview_surfaces_skipped_undersize_count(
    tmp_path: Path, sc_not_running
) -> None:
    # A real (tiny, unpadded) Game.log -- below the 1 MB floor -- must be
    # counted as skipped, not silently vanish into "no logs found".
    root = _make_live_install(tmp_path / "StarCitizen", pad=False)
    store = DedupStore(db_path=tmp_path / "state.sqlite")
    server = _make_server(root, store)
    client = _client(server)

    data = client.get("/api/preview").json()
    assert data["error"] is None
    assert data["candidates"] == []
    assert data["skipped_undersize_count"] == 2  # Game.log + its logbackup
    assert data["skipped_oversize_count"] == 0


def test_preview_surfaces_scan_error_distinctly_from_empty(tmp_path: Path) -> None:
    # sc_root exists but has no Live install at all -- LiveLogUnavailableError.
    root = tmp_path / "StarCitizen"
    root.mkdir()
    store = DedupStore(db_path=tmp_path / "state.sqlite")
    server = _make_server(root, store)
    client = _client(server)

    data = client.get("/api/preview").json()
    assert data["sc_root_configured"] is True
    assert data["error"] is not None
    assert data["header"] == data["error"]
    assert data["candidates"] == []


# ---------------------------------------------------------------------------
# Session token
# ---------------------------------------------------------------------------


def test_upload_without_session_token_is_forbidden(
    fake_sc_install: Path, tmp_path: Path
) -> None:
    store = DedupStore(db_path=tmp_path / "state.sqlite")
    server = _make_server(fake_sc_install, store)
    client = _client(server)

    r = client.post("/api/upload", json={"sha256": []})
    assert r.status_code == 403


def test_reset_without_session_token_is_forbidden(
    fake_sc_install: Path, tmp_path: Path
) -> None:
    store = DedupStore(db_path=tmp_path / "state.sqlite")
    server = _make_server(fake_sc_install, store)
    client = _client(server)

    r = client.post("/api/reset", json={})
    assert r.status_code == 403


def test_upload_with_wrong_session_token_is_forbidden(
    fake_sc_install: Path, tmp_path: Path
) -> None:
    store = DedupStore(db_path=tmp_path / "state.sqlite")
    server = _make_server(fake_sc_install, store)
    client = _client(server)

    r = client.post(
        "/api/upload", json={"sha256": []}, headers={"X-Donor-Session": "not-the-token"}
    )
    assert r.status_code == 403


# ---------------------------------------------------------------------------
# Host header check
# ---------------------------------------------------------------------------


def test_wrong_host_header_is_forbidden_on_every_route(
    fake_sc_install: Path, tmp_path: Path
) -> None:
    store = DedupStore(db_path=tmp_path / "state.sqlite")
    server = _make_server(fake_sc_install, store)
    client = _client(server)
    bad_host = {"host": "evil.example"}

    assert client.get("/api/preview", headers=bad_host).status_code == 403
    assert client.get("/api/status", headers=bad_host).status_code == 403
    assert client.get("/", headers=bad_host).status_code == 403
    assert client.get("/static/app.js", headers=bad_host).status_code == 403
    assert (
        client.post(
            "/api/upload",
            json={"sha256": []},
            headers={**bad_host, **_session_headers(server)},
        ).status_code
        == 403
    )


def test_localhost_host_header_is_accepted(fake_sc_install: Path, tmp_path: Path) -> None:
    store = DedupStore(db_path=tmp_path / "state.sqlite")
    server = _make_server(fake_sc_install, store)
    client = _client(server)

    r = client.get("/api/preview", headers={"host": f"localhost:{server.port}"})
    assert r.status_code == 200


# ---------------------------------------------------------------------------
# Static containment
# ---------------------------------------------------------------------------


def test_static_serves_known_file(fake_sc_install: Path, tmp_path: Path) -> None:
    store = DedupStore(db_path=tmp_path / "state.sqlite")
    server = _make_server(fake_sc_install, store)
    client = _client(server)

    r = client.get("/static/app.js")
    assert r.status_code == 200


def test_static_blocks_windows_drive_traversal(fake_sc_install: Path, tmp_path: Path) -> None:
    store = DedupStore(db_path=tmp_path / "state.sqlite")
    server = _make_server(fake_sc_install, store)
    client = _client(server)

    for filename in ("C:foo", "C:\\Windows\\System32\\drivers\\etc\\hosts"):
        r = client.get("/static/" + filename)
        assert r.status_code == 404, filename


def test_static_blocks_relative_traversal(fake_sc_install: Path, tmp_path: Path) -> None:
    store = DedupStore(db_path=tmp_path / "state.sqlite")
    server = _make_server(fake_sc_install, store)
    client = _client(server)

    r = client.get("/static/..\\..\\main.py")
    assert r.status_code == 404


def test_index_serves_session_meta_tag(fake_sc_install: Path, tmp_path: Path) -> None:
    store = DedupStore(db_path=tmp_path / "state.sqlite")
    server = _make_server(fake_sc_install, store)
    client = _client(server)

    r = client.get("/")
    assert r.status_code == 200
    assert f'content="{server._session_token}"' in r.text


# ---------------------------------------------------------------------------
# Upload restricted to previewed sha256 set
# ---------------------------------------------------------------------------


def test_upload_only_includes_previewed_sha256(
    tmp_path: Path, sc_not_running, monkeypatch
) -> None:
    monkeypatch.setattr("log_donor.donor_ui.app.Uploader", _FakeUploader)
    root = _make_live_install(tmp_path / "StarCitizen")
    store = DedupStore(db_path=tmp_path / "state.sqlite")
    server = _make_server(root, store)
    client = _client(server)

    preview = client.get("/api/preview").json()
    assert len(preview["candidates"]) == 2
    chosen_sha256 = preview["candidates"][0]["sha256"]

    r = client.post(
        "/api/upload",
        json={"sha256": [chosen_sha256]},
        headers=_session_headers(server),
    )
    assert r.status_code == 202

    status = _wait_until_done(client)
    assert status["result"]["top_level_error"] is None
    assert _FakeUploader.last_candidates is not None
    assert len(_FakeUploader.last_candidates) == 1
    assert _FakeUploader.last_candidates[0].sha256 == chosen_sha256


def test_upload_with_empty_sha256_list_uploads_nothing(
    fake_sc_install: Path, tmp_path: Path, sc_not_running, monkeypatch
) -> None:
    monkeypatch.setattr("log_donor.donor_ui.app.Uploader", _FakeUploader)
    store = DedupStore(db_path=tmp_path / "state.sqlite")
    server = _make_server(fake_sc_install, store)
    client = _client(server)

    r = client.post(
        "/api/upload", json={"sha256": []}, headers=_session_headers(server)
    )
    assert r.status_code == 202

    status = _wait_until_done(client)
    assert status["result"]["succeeded_count"] == 0


# ---------------------------------------------------------------------------
# Concurrent upload -> 409
# ---------------------------------------------------------------------------


def test_second_upload_while_running_returns_409(
    fake_sc_install: Path, tmp_path: Path, sc_not_running, monkeypatch
) -> None:
    block = threading.Event()

    def _slow_discover(_sc_root, _store):
        block.wait(timeout=5.0)
        return []

    monkeypatch.setattr("log_donor.donor_ui.app.discover_candidates", _slow_discover)
    store = DedupStore(db_path=tmp_path / "state.sqlite")
    server = _make_server(fake_sc_install, store)
    client = _client(server)
    headers = _session_headers(server)

    try:
        r1 = client.post("/api/upload", json={"sha256": []}, headers=headers)
        assert r1.status_code == 202

        r2 = client.post("/api/upload", json={"sha256": []}, headers=headers)
        assert r2.status_code == 409
    finally:
        block.set()
        _wait_until_done(client)


def test_reset_while_running_returns_409(
    fake_sc_install: Path, tmp_path: Path, sc_not_running, monkeypatch
) -> None:
    block = threading.Event()

    def _slow_discover(_sc_root, _store):
        block.wait(timeout=5.0)
        return []

    monkeypatch.setattr("log_donor.donor_ui.app.discover_candidates", _slow_discover)
    store = DedupStore(db_path=tmp_path / "state.sqlite")
    server = _make_server(fake_sc_install, store)
    client = _client(server)
    headers = _session_headers(server)

    try:
        r1 = client.post("/api/upload", json={"sha256": []}, headers=headers)
        assert r1.status_code == 202

        r2 = client.post("/api/reset", json={}, headers=headers)
        assert r2.status_code == 409
    finally:
        block.set()
        _wait_until_done(client)
