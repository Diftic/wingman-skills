"""The polling loop must survive the event loop that started it.

Root cause found 2026-07-26: `_start_nav_polling` used `asyncio.create_task`,
so the task belonged to the event loop running the `navigate_to` tool call.
Wingman does not keep that loop alive afterwards, so the coroutine reached its
first `await` and was silently abandoned. Auto-tracking, the arrival heads-up
and the auto-stop had therefore never worked at all, in any frame. A live trace
logged "poll loop ENTERED" and never the tick after the first sleep.

These tests reproduce that exact shape: start polling from inside asyncio.run,
let that loop close, then check whether the loop kept running. The first test
FAILS against the create_task implementation and passes against the thread one,
which is what makes it a regression guard rather than a restatement.
"""

from __future__ import annotations

import asyncio
import sys
import time
import types
from pathlib import Path

import pytest


pytest.importorskip("PIL")
pytest.importorskip("mss")

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import main  # noqa: E402


class _Printr:
    def __init__(self) -> None:
        self.messages: list[str] = []

    def print(self, message, color=None, server_only=False):
        self.messages.append(str(message))


def _skill(tmp_path: Path):
    skill = main.SC_NavPoint.__new__(main.SC_NavPoint)
    skill._nav_task = None
    skill._poll_thread = None
    skill._poll_stop = None
    skill._active_target = object()
    skill.printr = _Printr()
    skill.get_generated_files_dir = lambda: str(tmp_path)
    skill._get_poll_interval = lambda: 1
    return skill


def test_polling_survives_the_calling_event_loop_closing(tmp_path: Path) -> None:
    ticks: list[int] = []

    async def fake_loop(interval: int) -> None:
        for _ in range(5):
            await asyncio.sleep(0.02)
            ticks.append(1)

    skill = _skill(tmp_path)
    skill._nav_polling_loop = fake_loop

    async def caller() -> None:
        # Exactly what navigate_to does: schedule polling, then return.
        skill._start_nav_polling()

    asyncio.run(caller())  # the caller's loop is now closed and gone

    deadline = time.time() + 3.0
    while time.time() < deadline and len(ticks) < 5:
        time.sleep(0.02)

    assert ticks, (
        "polling produced nothing after the calling loop closed: this is the "
        "create_task bug returning"
    )
    assert len(ticks) == 5


def test_trace_records_the_thread_start(tmp_path: Path) -> None:
    async def fake_loop(interval: int) -> None:
        await asyncio.sleep(0.01)

    skill = _skill(tmp_path)
    skill._nav_polling_loop = fake_loop
    asyncio.run(_start_via(skill))
    time.sleep(0.4)

    trace = (tmp_path / "navpoint_poll.log").read_text(encoding="utf-8")
    assert "poll THREAD started" in trace
    # A loop that returns cleanly says so, which distinguishes "finished" from
    # "silently abandoned" the next time something goes wrong here.
    assert "poll loop returned normally" in trace


async def _start_via(skill) -> None:
    skill._start_nav_polling()


def test_stop_is_honoured_and_does_not_block(tmp_path: Path) -> None:
    entered = []

    async def fake_loop(interval: int) -> None:
        entered.append(1)
        while not skill._poll_stopping():
            await asyncio.sleep(0.02)

    skill = _skill(tmp_path)
    skill._nav_polling_loop = fake_loop
    asyncio.run(_start_via(skill))
    time.sleep(0.2)
    assert entered, "loop never started"

    started = time.time()
    skill._stop_nav_polling()
    # Stopping must never wait on an in-flight capture.
    assert time.time() - started < 0.5
    assert skill._poll_stopping() is True


def test_stopping_is_false_when_no_event_exists(tmp_path: Path) -> None:
    """Harnesses build the skill with __new__ and never set the event."""
    skill = main.SC_NavPoint.__new__(main.SC_NavPoint)
    assert skill._poll_stopping() is False


def test_restart_replaces_the_previous_thread(tmp_path: Path) -> None:
    async def fake_loop(interval: int) -> None:
        while not skill._poll_stopping():
            await asyncio.sleep(0.02)

    skill = _skill(tmp_path)
    skill._nav_polling_loop = fake_loop
    asyncio.run(_start_via(skill))
    time.sleep(0.1)
    first = skill._poll_thread
    asyncio.run(_start_via(skill))
    time.sleep(0.1)
    assert skill._poll_thread is not first
    skill._stop_nav_polling()


def test_loop_survives_the_target_vanishing_mid_capture(tmp_path: Path) -> None:
    """stop_navigation during an in-flight capture must not kill the thread.

    Live crash 2026-07-26: 'poll thread DIED: AttributeError: NoneType object has
    no attribute body'. The target was read after a 3-second capture and used
    without re-checking, so clearing it mid-capture dereferenced None. The race
    predates the thread fix but could never fire while the loop was dead.
    """
    skill = _skill(tmp_path)
    skill._get_arrival_alert_m = lambda: 0.0
    skill._get_arrival_stop_m = lambda: 0.0
    skill._ui_server = None

    class _Target:
        body = "Daymar"
        name = "cave"
        x = y = z = 0.0

    skill._active_target = _Target()

    async def capture_then_clear():
        # Exactly the live sequence: the capture completes, and by the time it
        # returns the user has stopped navigation.
        skill._active_target = None
        return {"x": 1.0, "y": 2.0, "z": 3.0, "body": "", "system_frame": True}

    skill._capture_position = capture_then_clear
    skill._poll_stop = None

    # Must return rather than raise. asyncio.run surfaces any exception.
    asyncio.run(skill._nav_polling_loop(0))

    trace = (tmp_path / "navpoint_poll.log").read_text(encoding="utf-8")
    assert "target cleared during capture" in trace
