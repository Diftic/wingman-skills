"""The page must never claim health it cannot verify.

Every fetch in app.js used to be wrapped in a catch that either said nothing
(`pollNavState`) or claimed success anyway (`clearTarget`, `deleteWaypoint`
ignored the response entirely). A HUD whose skill had gone away therefore froze
on its last good read, looked perfectly alive, and answered every click with
silence. That is the shape the 2026-08-01 report arrived in.

Source-level guards rather than a DOM harness: the behaviour was proven end to
end by driving real Edge over CDP (Devlog 2026-08-01), and what regresses in
practice is someone dropping the check, not the rendering.
"""

from __future__ import annotations

import re
from pathlib import Path


_APP_JS = Path(__file__).resolve().parent.parent / "navpoint_ui" / "static" / "app.js"


def _source() -> str:
    return _APP_JS.read_text(encoding="utf-8")


def _body(name: str) -> str:
    """The text of one function, up to the next top-level declaration."""
    src = _source()
    match = re.search(rf"^(?:async )?function {re.escape(name)}\(", src, re.MULTILINE)
    assert match, f"function {name} not found in app.js"
    start = match.start()
    nxt = re.search(r"\n(?:async function|function|const|let) ", src[start + 1:])
    return src[start: start + 1 + nxt.start()] if nxt else src[start:]


def test_poll_failure_marks_the_page_offline() -> None:
    body = _body("pollNavState")
    assert "setOnline(false)" in body, (
        "a failed poll must flag the page offline; swallowing it silently is "
        "what made a dead HUD indistinguishable from a live one"
    )
    assert "setOnline(true)" in body


def test_clear_target_checks_the_response() -> None:
    body = _body("clearTarget")
    assert "r.ok" in body, "clearTarget must not report success on a failed request"
    assert "setOnline(false)" in body


def test_delete_waypoint_checks_the_response() -> None:
    body = _body("deleteWaypoint")
    assert "r.ok" in body, "deleteWaypoint must not report success on a failed request"
    assert "setOnline(false)" in body


def test_idle_status_never_says_ready_while_offline() -> None:
    body = _body("idleStatus")
    assert "state.online" in body and "OFFLINE_MSG" in body


def test_offline_style_exists() -> None:
    css = (_APP_JS.parent / "style.css").read_text(encoding="utf-8")
    assert "hud-offline" in css, (
        "the offline class needs a visible style or the flag says nothing"
    )
