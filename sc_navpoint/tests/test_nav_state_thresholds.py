"""HUD threshold plumbing (spec v4.9.0.2 Feature D).

NavPointServer.__init__ gains arrival_alert_m / arrival_stop_m keyword args
(defaults 1000.0 / 250.0) and /api/nav/state exposes both so app.js can tag the
distance readout. These drive the FastAPI app through TestClient, exactly like
test_freshness, so the closure route handler is exercised as the browser hits
it. Only fastapi plus a real NavPointDatabase in tmp_path are needed.

Written from the spec BEFORE implementation; the constructor kwargs and the two
new state fields are expected to be absent until the implementation lands.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from database import NavPointDatabase


fastapi_testclient = pytest.importorskip("fastapi.testclient")
from fastapi.testclient import TestClient  # noqa: E402

from navpoint_ui.app import NavPointServer  # noqa: E402


def test_nav_state_carries_both_thresholds(tmp_path: Path) -> None:
    db = NavPointDatabase(str(tmp_path))
    server = NavPointServer(
        db=db, port=0, arrival_alert_m=1200.0, arrival_stop_m=300.0
    )
    client = TestClient(server._app)
    data = client.get("/api/nav/state").json()
    assert data["arrival_alert_m"] == 1200.0
    assert data["arrival_stop_m"] == 300.0


def test_nav_state_threshold_defaults(tmp_path: Path) -> None:
    db = NavPointDatabase(str(tmp_path))
    server = NavPointServer(db=db, port=0)
    client = TestClient(server._app)
    data = client.get("/api/nav/state").json()
    assert data["arrival_alert_m"] == 1000.0
    assert data["arrival_stop_m"] == 250.0
