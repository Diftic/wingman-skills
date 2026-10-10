"""Server-side freshness gate and dead-filter removal (spec Items A2, A, B3).

These drive the FastAPI app through TestClient so the closure route handlers
(set_nav_target, get_nav_state, get_navpoints) are exercised exactly as the
browser hits them. The skill runtime is not imported here: navpoint_ui.app
depends only on fastapi/uvicorn plus a NavPointDatabase, so a real DB seeded
in tmp_path is the whole fixture.

Written from the spec BEFORE implementation. Against the current code the
stale/unstamped cross-body cases, the position_age_s field, the removed
"servers" key, and POSITION_FRESHNESS_S are all expected to fail; the fresh
cross-body refusal and the no-position pass-through are regression guards that
must stay green.
"""

from __future__ import annotations

import time
from pathlib import Path

import pytest

from database import NavPointDatabase


fastapi_testclient = pytest.importorskip("fastapi.testclient")
from fastapi.testclient import TestClient  # noqa: E402

from navpoint_ui import app as navapp  # noqa: E402
from navpoint_ui.app import NavPointServer  # noqa: E402


# 30s == 3 missed polls at the 10s max interval (spec A2).
_STALE_AGE_S = 31.0


def _server(tmp_path: Path) -> tuple[NavPointServer, NavPointDatabase]:
    db = NavPointDatabase(str(tmp_path))
    server = NavPointServer(db=db, port=0)
    return server, db


# ---------------------------------------------------------------------- #
# A2: module constant
# ---------------------------------------------------------------------- #


def test_position_freshness_constant_is_30s() -> None:
    assert navapp.POSITION_FRESHNESS_S == 30.0


# ---------------------------------------------------------------------- #
# A2: cross-body refusal gated on freshness
# ---------------------------------------------------------------------- #


def test_fresh_cross_body_is_refused(tmp_path: Path) -> None:
    server, db = _server(tmp_path)
    np = db.add_navpoint("Cave", "srv1", "Yela", 1.0, 2.0, 3.0)
    client = TestClient(server._app)
    # Fresh stamp, standing on a different body: the strict refusal still fires.
    server.set_position({"body": "Daymar", "captured_at": time.time()})
    r = client.post(f"/api/nav/target/{np.id}")
    assert r.status_code == 409


def test_stale_cross_body_is_not_refused(tmp_path: Path) -> None:
    server, db = _server(tmp_path)
    np = db.add_navpoint("Cave", "srv1", "Yela", 1.0, 2.0, 3.0)
    client = TestClient(server._app)
    # A stamp older than the freshness window behaves like no position at all.
    server.set_position(
        {"body": "Daymar", "captured_at": time.time() - _STALE_AGE_S}
    )
    r = client.post(f"/api/nav/target/{np.id}")
    assert r.status_code == 200
    assert r.json()["success"] is True


def test_unstamped_cross_body_is_not_refused(tmp_path: Path) -> None:
    server, db = _server(tmp_path)
    np = db.add_navpoint("Cave", "srv1", "Yela", 1.0, 2.0, 3.0)
    client = TestClient(server._app)
    # No captured_at means the position cannot be trusted for the refusal.
    server.set_position({"body": "Daymar"})
    r = client.post(f"/api/nav/target/{np.id}")
    assert r.status_code == 200
    assert r.json()["success"] is True


def test_no_position_cross_body_is_not_refused(tmp_path: Path) -> None:
    server, db = _server(tmp_path)
    np = db.add_navpoint("Cave", "srv1", "Yela", 1.0, 2.0, 3.0)
    client = TestClient(server._app)
    # No position at all: nothing to refuse against.
    server._current_position = None
    r = client.post(f"/api/nav/target/{np.id}")
    assert r.status_code == 200
    assert r.json()["success"] is True


def test_fresh_same_body_is_allowed(tmp_path: Path) -> None:
    server, db = _server(tmp_path)
    np = db.add_navpoint("Cave", "srv1", "Yela", 1.0, 2.0, 3.0)
    client = TestClient(server._app)
    # Fresh and on the matching body: the gate must not block the happy path.
    server.set_position({"body": "Yela", "captured_at": time.time()})
    r = client.post(f"/api/nav/target/{np.id}")
    assert r.status_code == 200
    assert r.json()["success"] is True


# ---------------------------------------------------------------------- #
# A2: /api/nav/state exposes position_age_s
# ---------------------------------------------------------------------- #


def test_nav_state_reports_position_age(tmp_path: Path) -> None:
    server, db = _server(tmp_path)
    client = TestClient(server._app)
    server.set_position({"body": "Yela", "captured_at": time.time() - 5.0})
    r = client.get("/api/nav/state")
    age = r.json()["position_age_s"]
    assert age is not None
    # Computed server-side; a few seconds of slack for the request round trip.
    assert 4.0 <= age <= 20.0


def test_nav_state_age_null_when_unstamped(tmp_path: Path) -> None:
    server, db = _server(tmp_path)
    client = TestClient(server._app)
    server.set_position({"body": "Yela"})
    r = client.get("/api/nav/state")
    assert r.json()["position_age_s"] is None


def test_nav_state_age_null_when_no_position(tmp_path: Path) -> None:
    server, db = _server(tmp_path)
    client = TestClient(server._app)
    server._current_position = None
    r = client.get("/api/nav/state")
    assert r.json()["position_age_s"] is None


# ---------------------------------------------------------------------- #
# B3: /api/navpoints drops the server dimension
# ---------------------------------------------------------------------- #


def test_navpoints_response_has_no_servers_key(tmp_path: Path) -> None:
    server, db = _server(tmp_path)
    db.add_navpoint("A", "srvA", "Daymar", 1.0, 1.0, 1.0)
    client = TestClient(server._app)
    data = client.get("/api/navpoints").json()
    assert "servers" not in data
    assert "navpoints" in data
    assert "bodies" in data


def test_navpoints_body_filter_still_works(tmp_path: Path) -> None:
    server, db = _server(tmp_path)
    db.add_navpoint("A", "srvA", "Daymar", 1.0, 1.0, 1.0)
    db.add_navpoint("B", "srvA", "Cellin", 2.0, 2.0, 2.0)
    client = TestClient(server._app)
    data = client.get("/api/navpoints", params={"body": "Daymar"}).json()
    names = {n["name"] for n in data["navpoints"]}
    assert names == {"A"}
