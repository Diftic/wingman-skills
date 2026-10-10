"""Behavioral tests for the two-stage arrival alert (spec v4.9.0.2 Feature A).

main.py imports the Wingman runtime plus a scanner that needs PIL/mss; the
runtime is shimmed via _stubs and the imaging deps are importorskip-gated.

The nav poll loop and navigate_to are driven with hand-built skill instances
(built with __new__, bypassing __init__/prepare which need a live Wingman) and
scripted collaborators: a scripted _capture_position feeds a controlled
sequence of position dicts, a recording printr/ui/wingman prove the
announcements and the auto-stop teardown. The two arrival attributes are
seeded to their __init__ defaults (False / 0) as a precondition.

Written from the spec BEFORE implementation. Against the current code the poll
loop carries no arrival logic and navigate_to/stop_navigation/delete_navpoint/
_handle_server_change do not reset the arrival attributes, so every assertion
that expects an announcement, a streak change, or a reset is expected to fail
until the implementation lands.
"""

from __future__ import annotations

import asyncio
import json
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest


pytest.importorskip("PIL")
pytest.importorskip("mss")

from _stubs import LogType, install_runtime_stubs  # noqa: E402


install_runtime_stubs()

import main  # noqa: E402
from database import NavPointDatabase  # noqa: E402


# Distances from a target planted at the origin. With the spec defaults
# (alert 1000 m, stop 250 m): 200 m is inside both zones, 500 m is inside the
# alert zone only, 2000 m is outside both.
IN_STOP = 200.0
IN_ALERT = 500.0
FAR = 2000.0


# ---------------------------------------------------------------------- #
# Recording collaborators
# ---------------------------------------------------------------------- #


class _RecordingPrintr:
    def __init__(self) -> None:
        self.calls: list[tuple] = []

    def print(self, message: str, color=None, server_only: bool = False) -> None:
        self.calls.append((message, color, server_only))


class _RecordingUI:
    def __init__(self) -> None:
        self.set_position_calls: list = []
        self.set_active_target_calls: list = []
        self.notify_updates: int = 0

    def set_position(self, pos_data: dict) -> None:
        self.set_position_calls.append(pos_data)

    def set_active_target(self, target) -> None:
        self.set_active_target_calls.append(target)

    def notify_update(self) -> None:
        self.notify_updates += 1


class _FakeWingman:
    def __init__(self) -> None:
        self.assistant_messages: list[str] = []
        self.speech_calls: list[tuple[str, bool]] = []
        self.tts = SimpleNamespace(speak=self._speak)
        self.conversation = SimpleNamespace(add_assistant=self._add_assistant)

    async def _speak(self, text: str, *, interrupt: bool = True) -> None:
        self.speech_calls.append((text, interrupt))

    async def _add_assistant(self, msg: str) -> None:
        self.assistant_messages.append(msg)


class _Target:
    """Minimal active-target stand-in: the poll loop reads only these fields."""

    def __init__(self, id_: int, name: str, body: str, x: float, y: float, z: float):
        self.id = id_
        self.name = name
        self.body = body
        self.x = x
        self.y = y
        self.z = z


class _ScriptedCapture:
    """Yields a scripted sequence of captures, then ends the loop.

    Each script entry is either a position dict or None (a failed capture). A
    fresh dict copy is handed out per call so the loop stamps a copy, not the
    fixture. When the script is exhausted a CancelledError is raised, which the
    loop's own outer handler swallows, so a non-stopping run ends cleanly
    without a real 5s poll delay.
    """

    def __init__(self, script: list) -> None:
        self._script = list(script)

    async def __call__(self) -> dict | None:
        if not self._script:
            raise asyncio.CancelledError
        item = self._script.pop(0)
        return dict(item) if isinstance(item, dict) else item


def _pos(x: float, body: str = "Daymar") -> dict:
    return {"x": float(x), "y": 0.0, "z": 0.0, "body": body}


def _bare_skill(db: NavPointDatabase | None = None) -> "main.SC_NavPoint":
    skill = main.SC_NavPoint.__new__(main.SC_NavPoint)
    skill._db = db
    skill._scanner = None
    skill._ui_server = _RecordingUI()
    skill._ui_window = None
    skill._active_target = None
    skill._nav_task = None
    skill.printr = _RecordingPrintr()
    skill.wingman = _FakeWingman()
    skill._audio_calls: list = []
    skill.wingman.run_in_thread = lambda fn, *a: skill._audio_calls.append((fn, a))
    # Seed the two arrival attributes to their spec __init__ defaults.
    skill._arrival_alert_done = False
    skill._arrival_stop_streak = 0
    # Two-capture wipe confirmation state (v4.9.0.4).
    skill._pending_server_change = None
    skill._stop_nav_polling = MagicMock()
    skill._start_nav_polling = MagicMock()
    # Custom-property reads return None so the threshold getters fall to their
    # defaults (alert 1000, stop 250).
    skill.retrieve_custom_property_value = lambda key, errors=None: None
    return skill


def _loop_skill(script: list) -> "main.SC_NavPoint":
    skill = _bare_skill()
    skill._active_target = _Target(1, "Cave", "Daymar", 0.0, 0.0, 0.0)
    skill._capture_position = _ScriptedCapture(script)
    return skill


def _approaching(skill) -> list:
    return [c for c in skill.printr.calls if "Approaching" in c[0]]


def _arrived(skill) -> list:
    return [
        c
        for c in skill.printr.calls
        if "Arrived." in c[0] and c[1] == LogType.POSITIVE
    ]


# ---------------------------------------------------------------------- #
# Stage 2: two-poll auto-stop confirmation
# ---------------------------------------------------------------------- #


def test_two_consecutive_in_zone_polls_stop() -> None:
    skill = _loop_skill([_pos(IN_STOP), _pos(IN_STOP)])
    asyncio.run(skill._nav_polling_loop(0))
    # Exactly one arrival announcement, fired on the second in-zone poll.
    assert len(_arrived(skill)) == 1
    # Auto-stop teardown mirrors stop_navigation.
    assert skill._active_target is None
    skill._stop_nav_polling.assert_called()
    assert None in skill._ui_server.set_active_target_calls
    # Standing inside the stop zone must not also fire the approach heads-up.
    assert _approaching(skill) == []


def test_single_in_zone_poll_does_not_stop() -> None:
    skill = _loop_skill([_pos(IN_STOP)])
    asyncio.run(skill._nav_polling_loop(0))
    assert skill._arrival_stop_streak == 1
    assert _arrived(skill) == []
    # One reading is not enough to end navigation.
    assert skill._active_target is not None


def test_out_of_zone_poll_resets_streak() -> None:
    skill = _loop_skill([_pos(IN_STOP), _pos(FAR), _pos(IN_STOP)])
    asyncio.run(skill._nav_polling_loop(0))
    # The far poll resets the streak, so the two in-zone polls are not
    # consecutive and no stop fires.
    assert skill._arrival_stop_streak == 1
    assert _arrived(skill) == []
    assert skill._active_target is not None


def test_failed_capture_between_does_not_reset_streak() -> None:
    # A transient OCR failure (None) must not defeat a confirmation in
    # progress: the two in-zone polls stay consecutive and the stop fires.
    skill = _loop_skill([_pos(IN_STOP), None, _pos(IN_STOP)])
    asyncio.run(skill._nav_polling_loop(0))
    assert len(_arrived(skill)) == 1
    assert skill._active_target is None


def test_failed_capture_does_not_count_toward_stop() -> None:
    # A failed capture also must not advance the streak.
    skill = _loop_skill([_pos(IN_STOP), None])
    asyncio.run(skill._nav_polling_loop(0))
    assert skill._arrival_stop_streak == 1
    assert _arrived(skill) == []


def test_body_mismatch_capture_neither_counts_nor_resets() -> None:
    # A body-mismatch poll produces no bearing; like a failed capture it must
    # neither count nor reset, so the confirmation still completes.
    skill = _loop_skill(
        [_pos(IN_STOP), _pos(IN_STOP, body="Yela"), _pos(IN_STOP)]
    )
    asyncio.run(skill._nav_polling_loop(0))
    assert len(_arrived(skill)) == 1
    assert skill._active_target is None


def test_arrival_announces_via_wingman_and_positive_badge() -> None:
    skill = _loop_skill([_pos(IN_STOP), _pos(IN_STOP)])
    asyncio.run(skill._nav_polling_loop(0))
    assert skill.wingman.assistant_messages == []
    assert len(_arrived(skill)) == 1
    # The audio path is invoked too.
    assert skill._audio_calls
    for fn, args in skill._audio_calls:
        asyncio.run(fn(*args))
    assert skill.wingman.speech_calls == [
        ("Arrived.", False)
    ]


# ---------------------------------------------------------------------- #
# Stage 1: approach heads-up, fired at most once
# ---------------------------------------------------------------------- #


def test_approach_alert_fires_once() -> None:
    skill = _loop_skill([_pos(IN_ALERT), _pos(IN_ALERT)])
    asyncio.run(skill._nav_polling_loop(0))
    approaching = [c for c in _approaching(skill) if c[1] == LogType.INFO]
    assert len(approaching) == 1
    assert skill._arrival_alert_done is True
    assert _arrived(skill) == []
    # Inside the alert zone but outside the stop zone: streak never builds.
    assert skill._arrival_stop_streak == 0


def test_approach_message_gives_distance_without_repeating_target() -> None:
    skill = _loop_skill([_pos(IN_ALERT)])
    asyncio.run(skill._nav_polling_loop(0))
    approaching = _approaching(skill)
    assert len(approaching) == 1
    msg = approaching[0][0]
    assert msg == "[NavPoint] Approaching: 500 meters."


def test_approach_suppressed_when_first_poll_already_in_stop_zone() -> None:
    # Arriving straight into the stop zone: the alert is marked done to avoid a
    # double announcement, but no approach heads-up is spoken.
    skill = _loop_skill([_pos(IN_STOP)])
    asyncio.run(skill._nav_polling_loop(0))
    assert _approaching(skill) == []
    assert skill._arrival_alert_done is True


# ---------------------------------------------------------------------- #
# navigate_to: initial-bearing suppression and no auto-stop
# ---------------------------------------------------------------------- #


def _nav_skill(pos: dict | None, tmp_path) -> "main.SC_NavPoint":
    db = NavPointDatabase(str(tmp_path))
    db.add_navpoint("Cave", "pub-euw1b-sc-alpha-490-11111111-game-82", "Daymar", 0.0, 0.0, 0.0)
    skill = _bare_skill(db)

    async def _cap() -> dict | None:
        return dict(pos) if pos else None

    skill._capture_position = _cap
    return skill


def test_navigate_to_in_alert_zone_marks_alert_done(tmp_path) -> None:
    skill = _nav_skill(_pos(IN_ALERT), tmp_path)
    result = json.loads(asyncio.run(skill.navigate_to("Cave")))
    assert result["success"] is True
    # The tool result already reported the distance; the next poll must not
    # repeat it, so the alert is pre-marked done.
    assert skill._arrival_alert_done is True
    assert skill._arrival_stop_streak == 0
    assert skill._active_target is not None
    skill._start_nav_polling.assert_called()
    # navigate_to itself does not speak the approach heads-up.
    assert _approaching(skill) == []


def test_navigate_to_in_stop_zone_marks_alert_done_but_does_not_stop(
    tmp_path,
) -> None:
    # Setting a target while standing on it is legitimate: the target is set
    # and polling starts; the two-poll loop handles any stop, not navigate_to.
    skill = _nav_skill(_pos(IN_STOP), tmp_path)
    result = json.loads(asyncio.run(skill.navigate_to("Cave")))
    assert result["success"] is True
    assert skill._arrival_alert_done is True
    assert skill._active_target is not None
    skill._start_nav_polling.assert_called()


def test_navigate_to_resets_prior_arrival_state(tmp_path) -> None:
    skill = _nav_skill(_pos(FAR), tmp_path)
    skill._arrival_alert_done = True
    skill._arrival_stop_streak = 7
    asyncio.run(skill.navigate_to("Cave"))
    # A fresh activation resets both; the far initial bearing does not re-mark
    # the alert.
    assert skill._arrival_alert_done is False
    assert skill._arrival_stop_streak == 0


# ---------------------------------------------------------------------- #
# State lifecycle: reset on every activation start/end
# ---------------------------------------------------------------------- #


def test_stop_navigation_resets_arrival_state() -> None:
    skill = _bare_skill()
    skill._active_target = _Target(1, "Cave", "Daymar", 0.0, 0.0, 0.0)
    skill._arrival_alert_done = True
    skill._arrival_stop_streak = 3
    skill.stop_navigation()
    assert skill._active_target is None
    assert skill._arrival_alert_done is False
    assert skill._arrival_stop_streak == 0


def test_delete_active_navpoint_resets_arrival_state(tmp_path) -> None:
    db = NavPointDatabase(str(tmp_path))
    np = db.add_navpoint("Cave", "pub-euw1b-sc-alpha-490-11111111-game-82", "Daymar", 0.0, 0.0, 0.0)
    skill = _bare_skill(db)
    skill._active_target = np
    skill._arrival_alert_done = True
    skill._arrival_stop_streak = 3
    skill.delete_navpoint("Cave")
    assert skill._active_target is None
    assert skill._arrival_alert_done is False
    assert skill._arrival_stop_streak == 0


def test_delete_non_active_navpoint_keeps_arrival_state(tmp_path) -> None:
    db = NavPointDatabase(str(tmp_path))
    active = db.add_navpoint("Cave", "pub-euw1b-sc-alpha-490-11111111-game-82", "Daymar", 0.0, 0.0, 0.0)
    db.add_navpoint("Other", "pub-euw1b-sc-alpha-490-11111111-game-82", "Daymar", 9.0, 9.0, 9.0)
    skill = _bare_skill(db)
    skill._active_target = active
    skill._arrival_alert_done = True
    skill._arrival_stop_streak = 3
    skill.delete_navpoint("Other")
    # Deleting a non-active waypoint leaves the active navigation untouched.
    assert skill._arrival_alert_done is True
    assert skill._arrival_stop_streak == 3


def test_server_change_wipe_resets_arrival_state(tmp_path) -> None:
    db = NavPointDatabase(str(tmp_path))
    np = db.add_navpoint("Cave", "pub-euw1b-sc-alpha-490-11111111-game-82", "Daymar", 0.0, 0.0, 0.0)
    skill = _bare_skill(db)
    skill._active_target = np
    skill._arrival_alert_done = True
    skill._arrival_stop_streak = 3
    # A proven change needs THREE consecutive captures agreeing on a
    # WELL-FORMED new server token (raised from two on 2026-07-26, after two
    # agreeing misreads deleted six real waypoints).
    skill._handle_server_change("pub-euw1b-sc-alpha-490-22222222-game-82")
    assert db.count_navpoints() == 1
    skill._handle_server_change("pub-euw1b-sc-alpha-490-22222222-game-82")
    assert db.count_navpoints() == 1
    skill._handle_server_change("pub-euw1b-sc-alpha-490-22222222-game-82")
    assert db.count_navpoints() == 0
    assert skill._active_target is None
    assert skill._arrival_alert_done is False
    assert skill._arrival_stop_streak == 0
