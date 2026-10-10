"""HUD arrival tags in the SPA (spec v4.9.0.2 Feature D).

The tag logic (ARRIVED when dist_m <= arrival_stop_m and stop > 0, else
APPROACHING when dist_m <= arrival_alert_m and alert > 0) lives in the same
render path that owns the STALE tag and is not unit-testable without a browser,
so it is guarded at the source level: the two tag literals appear, both
thresholds are read from the nav state, and the tag is styled with the existing
green token (STALE uses --yellow; arrival uses --green). A node --check catches
any syntax slip the change introduces; it skips cleanly when node is absent.

Written from the spec BEFORE implementation; the source-level assertions are
expected to fail until app.js carries the arrival tags.
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest


_APP_JS = Path(__file__).resolve().parent.parent / "navpoint_ui" / "static" / "app.js"
_SRC = _APP_JS.read_text(encoding="utf-8")


def test_app_js_defines_arrived_tag() -> None:
    assert "ARRIVED" in _SRC


def test_app_js_defines_approaching_tag() -> None:
    assert "APPROACHING" in _SRC


def test_app_js_reads_stop_threshold() -> None:
    assert "arrival_stop_m" in _SRC


def test_app_js_reads_alert_threshold() -> None:
    assert "arrival_alert_m" in _SRC


def test_app_js_arrival_tag_uses_green_token() -> None:
    # STALE is drawn with var(--yellow); the arrival tag mirrors that mechanism
    # with the existing green token.
    assert "--green" in _SRC


def test_app_js_parses_with_node() -> None:
    node = shutil.which("node")
    if node is None:
        pytest.skip("node not on PATH; skipping JS syntax check")
    assert _APP_JS.exists(), f"app.js not found at {_APP_JS}"
    result = subprocess.run(
        [node, "--check", str(_APP_JS)],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, (
        f"node --check reported a syntax error in app.js:\n"
        f"{result.stdout}\n{result.stderr}"
    )
