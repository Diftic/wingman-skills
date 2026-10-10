"""`update_position` must refuse a payload that carries no coordinate frame.

A station or asteroid-base interior produces a TRUTHY payload with neither a
body nor a system frame in it. `mark_location` refuses that and `navigate_to`
refuses it, both by name. `update_position` did not: it walked past the falsy
guard, read `pos_data.get("x")` on a payload that has no `x`, and reported

    {"position": {"x": null, "y": null, "z": null, "body": ""}}

as an ordinary successful reading. That is the largest player-visible lie on
the capture path, because nothing in the result says the reading failed.

The guard keys on `_capture_frame(...) is None`, never on `not
pos_data.get("body")`: a deep-space fix has an empty body and a perfectly good
system frame, and refusing that would cost the player a legitimate reading.
"""

from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest


pytest.importorskip("PIL")
pytest.importorskip("mss")

sys.path.insert(0, str(Path(__file__).resolve().parent))

from _stubs import install_runtime_stubs  # noqa: E402


install_runtime_stubs()

import main  # noqa: E402
import overlay_fields as fields  # noqa: E402
from database import NavPointDatabase  # noqa: E402


_MAIN_SRC = (Path(main.__file__).with_name("main.py")).read_text(encoding="utf-8")

# What a station interior actually returns: the overlay read cleanly, and there
# is genuinely no frame at this location.
_NO_FRAME_PAYLOAD = {"body": "", "zone": "", "local_frame": False}

# Open space. Empty body, system frame set, coordinates present.
_SPACE_PAYLOAD = {
    "body": "",
    "system_frame": True,
    "x": 1.0,
    "y": 2.0,
    "z": 3.0,
    "zone": "",
}


class _Printr:
    def __init__(self) -> None:
        self.calls: list[tuple] = []

    def print(self, message, color=None, server_only=False):
        self.calls.append((message, color, server_only))


class _RecordingUI:
    def __init__(self) -> None:
        self.url = ""
        self.set_active_target_calls: list = []

    def set_position(self, pos_data: dict) -> None:
        pass

    def set_active_target(self, target) -> None:
        self.set_active_target_calls.append(target)

    def notify_update(self) -> None:
        pass


def _outcome(kind: str, **kwargs) -> fields.CaptureOutcome:
    return fields.CaptureOutcome(kind=kind, **kwargs)


def _skill(db=None) -> main.SC_NavPoint:
    """A skill whose capture is dictated, so the GUARD is what is under test."""
    skill = main.SC_NavPoint.__new__(main.SC_NavPoint)
    skill.printr = _Printr()
    skill._db = db
    skill._ui_server = _RecordingUI()
    skill._ui_window = None
    skill._active_target = None
    skill._hud_opened = False
    skill._get_display = lambda: 1
    skill._get_poll_interval = lambda: 5
    skill._get_arrival_alert_m = lambda: 1000.0
    skill._get_arrival_stop_m = lambda: 250.0
    skill._start_nav_polling = MagicMock()
    skill._stop_nav_polling = MagicMock()
    skill._sync_ring = lambda: None
    return skill


def _capturing(skill: main.SC_NavPoint, pos_data, outcome) -> None:
    """Wire a capture that returns `pos_data` and ends on `outcome`."""

    async def _capture(attempts: int = 1):
        skill._last_outcome = outcome
        return dict(pos_data) if pos_data else pos_data

    skill._capture_position = _capture
    skill._last_outcome = outcome


def test_update_position_refuses_a_station_interior(tmp_path) -> None:
    """The reported bug, end to end. A frameless payload is not a position."""
    skill = _skill(db=NavPointDatabase(str(tmp_path)))
    _capturing(skill, _NO_FRAME_PAYLOAD, _outcome(fields.KIND_OK))
    result = json.loads(asyncio.run(skill.update_position()))

    assert result["capture_kind"] == fields.KIND_NO_FRAME
    assert "position" not in result
    # The overlay WAS read here, so telling the player to switch it on would be
    # a console command relayed word for word for no reason.
    assert "hint" not in result
    assert "r_displayinfo" not in json.dumps(result)


def test_update_position_and_mark_location_agree_on_a_truthy_no_frame_payload(
    tmp_path,
) -> None:
    """One kind, one message, whichever tool the player happened to ask."""
    errors = []
    for tool in ("mark_location", "update_position"):
        skill = _skill(db=NavPointDatabase(str(tmp_path)))
        _capturing(skill, _NO_FRAME_PAYLOAD, _outcome(fields.KIND_OK))
        errors.append(json.loads(asyncio.run(getattr(skill, tool)()))["error"])

    assert len(set(errors)) == 1, errors
    assert "No usable coordinate frame" in errors[0]


def test_a_system_frame_capture_still_reports_its_position(tmp_path) -> None:
    """The over-refusal guard. A deep-space fix has an empty body and is a
    perfectly good reading; a guard written as `not pos_data.get("body")` would
    throw it away."""
    skill = _skill(db=NavPointDatabase(str(tmp_path)))
    _capturing(skill, _SPACE_PAYLOAD, _outcome(fields.KIND_OK))
    result = json.loads(asyncio.run(skill.update_position()))

    assert "error" not in result
    assert result["position"]["x"] == 1.0
    assert result["position"]["y"] == 2.0
    assert result["position"]["z"] == 3.0


def test_update_position_uses_the_shared_frame_helper() -> None:
    """There were already two open-coded copies of this predicate before
    `_capture_frame` existed to stop that. A third would drift the same way."""
    start = _MAIN_SRC.index("async def update_position")
    end = _MAIN_SRC.index("def stop_navigation", start)
    body = _MAIN_SRC[start:end]

    assert "_capture_frame(" in body
    assert "system_frame" not in body
