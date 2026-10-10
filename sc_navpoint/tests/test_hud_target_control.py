"""The HUD page must be able to CHANGE navigation, not just display it.

Until 2026-08-01 the page was a mirror with buttons. Its Clear, its Navigate and
its delete moved `NavPointServer._active_target` and stopped there, while the
skill kept its own `_active_target`, its poll thread and the ring. Clearing on
the page therefore left the skill navigating, which is what "Clear target does
not work" was: the page obeyed, nothing else did.

`on_target_change` is the seam that closes it. These drive the FastAPI app
through TestClient, like test_nav_state_thresholds, so the closure route handlers
run exactly as the browser hits them.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from database import NavPointDatabase


fastapi_testclient = pytest.importorskip("fastapi.testclient")
from fastapi.testclient import TestClient  # noqa: E402

from navpoint_ui.app import NavPointServer  # noqa: E402


def _seed(tmp_path: Path):
    db = NavPointDatabase(str(tmp_path))
    alpha = db.add_navpoint("Alpha", "srv1", "Daymar", 1.0, 2.0, 3.0)
    beta = db.add_navpoint("Beta", "srv1", "Daymar", 4.0, 5.0, 6.0)
    return db, alpha, beta


def _server(db, calls):
    return NavPointServer(db=db, port=0, on_target_change=calls.append)


def test_setting_a_target_from_the_page_reaches_the_skill(tmp_path: Path) -> None:
    db, alpha, _ = _seed(tmp_path)
    calls: list = []
    client = TestClient(_server(db, calls)._app)

    assert client.post(f"/api/nav/target/{alpha.id}").status_code == 200
    assert [np.name for np in calls] == ["Alpha"]


def test_clearing_from_the_page_reaches_the_skill(tmp_path: Path) -> None:
    db, alpha, _ = _seed(tmp_path)
    calls: list = []
    client = TestClient(_server(db, calls)._app)
    client.post(f"/api/nav/target/{alpha.id}")
    calls.clear()

    assert client.delete("/api/nav/target").status_code == 200
    # None is the whole point: the skill has to be told to STOP, not merely
    # left to notice.
    assert calls == [None]


def test_deleting_the_active_waypoint_stops_navigation(tmp_path: Path) -> None:
    db, alpha, _ = _seed(tmp_path)
    calls: list = []
    client = TestClient(_server(db, calls)._app)
    client.post(f"/api/nav/target/{alpha.id}")
    calls.clear()

    assert client.delete(f"/api/navpoints/{alpha.id}").status_code == 200
    assert calls == [None]


def test_deleting_another_waypoint_leaves_navigation_alone(tmp_path: Path) -> None:
    db, alpha, beta = _seed(tmp_path)
    calls: list = []
    server = _server(db, calls)
    client = TestClient(server._app)
    client.post(f"/api/nav/target/{alpha.id}")
    calls.clear()

    assert client.delete(f"/api/navpoints/{beta.id}").status_code == 200
    assert calls == [], "deleting an unrelated row must not stop navigation"
    assert db.count_navpoints() == 1
    assert client.get("/api/nav/state").json()["active_target"]["name"] == "Alpha"


def test_a_failing_callback_never_breaks_the_endpoint(tmp_path: Path) -> None:
    """The page's own view is already correct; a broken skill callback must not
    turn a completed state change into an HTTP error the page then reports."""
    db, alpha, _ = _seed(tmp_path)

    def explode(_np):
        raise RuntimeError("boom")

    client = TestClient(
        NavPointServer(db=db, port=0, on_target_change=explode)._app
    )
    assert client.post(f"/api/nav/target/{alpha.id}").status_code == 200
    assert client.delete("/api/nav/target").status_code == 200
    assert client.delete(f"/api/navpoints/{alpha.id}").status_code == 200


def test_server_still_works_without_a_callback(tmp_path: Path) -> None:
    """The HUD server is constructible standalone (the probes and tests do it),
    so an absent callback stays a supported configuration."""
    db, alpha, _ = _seed(tmp_path)
    client = TestClient(NavPointServer(db=db, port=0)._app)

    assert client.post(f"/api/nav/target/{alpha.id}").status_code == 200
    assert client.delete("/api/nav/target").status_code == 200
    assert client.get("/api/nav/state").json()["active_target"] is None
