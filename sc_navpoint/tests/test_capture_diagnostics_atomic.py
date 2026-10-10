"""A caller must be told about ITS OWN capture, not the one that finished last.

The capture lock in `_capture_position_local` releases when that function
returns, which is BEFORE `asyncio.to_thread` marshals the result back to the
awaiting coroutine. The poll thread fires every second unattended, so between
those two moments a whole second capture can finish and overwrite
`self._last_outcome`, `self._scanner.last_reject_reason` and the one-shot badge
latches. Everything the tools read to explain a refusal lived in exactly those
fields, so a spoken command could be handed the poll tick's kind, the poll
tick's reject reason and the poll tick's badge.

The worst instance is not merely a wrong label. `KIND_ABSENT` is the one kind
that carries the console-command hint, and `default_config.yaml` orders any hint
relayed to the player word for word. A tool whose own capture READ the overlay
perfectly could therefore read out an instruction to switch on something already
on screen, because an unrelated poll tick a fraction of a second later happened
to look while the overlay was hidden.

The channel is a `contextvars` sink rather than a return value or an argument,
because both capture seams have their signatures and return types pinned by
existing tests and `CaptureOutcome` may not grow a field. `asyncio.to_thread`
copies the caller's context into the worker, so the list a caller puts in the
ContextVar is the same list object the worker appends to. A capture started on
a bare `threading.Thread` gets a fresh, empty context and so cannot reach
another caller's sink, which is exactly the isolation these tests rely on.

The race is INJECTED, not waited for: the second capture is run synchronously
inside a wrapped `to_thread`, in the precise window, so nothing here is timed
and nothing here can flake.
"""

from __future__ import annotations

import asyncio
import json
import re
import sys
import threading
import time
from pathlib import Path
from unittest.mock import MagicMock

import pytest


pytest.importorskip("PIL")
pytest.importorskip("mss")

sys.path.insert(0, str(Path(__file__).resolve().parent))

from test_main_capture import _install_runtime_stubs  # noqa: E402


_install_runtime_stubs()

import mss as mss_module  # noqa: E402

import main  # noqa: E402
import overlay_fields as fields  # noqa: E402
from database import NavPointDatabase  # noqa: E402


_REGION = {"left": 0, "top": 0, "width": 10, "height": 5}

# Captured before any test monkeypatches `main.time.sleep` to a no-op: the step 4
# test needs a real pause, and `main.time` is the same module object as this one.
_real_sleep = time.sleep


class _Printr:
    def __init__(self) -> None:
        self.calls: list[tuple] = []

    def print(self, message, color=None, server_only=False):
        self.calls.append((message, color, server_only))


class _RecordingUI:
    def __init__(self) -> None:
        self.url = ""

    def set_position(self, pos_data: dict) -> None:
        pass

    def set_active_target(self, target) -> None:
        pass

    def notify_update(self) -> None:
        pass


class _FakeGrab:
    def __init__(self, region: dict) -> None:
        self.size = (region["width"], region["height"])
        self.bgra = bytes(region["width"] * region["height"] * 4)


class _Screen:
    def __init__(self) -> None:
        self.monitors = [dict(_REGION), dict(_REGION)]

    def __call__(self) -> "_Screen":
        return self

    def __enter__(self) -> "_Screen":
        return self

    def __exit__(self, *exc_info) -> bool:
        return False

    def grab(self, region: dict) -> _FakeGrab:
        return _FakeGrab(region)


class _Plan:
    """What the NEXT capture should do, swapped between capture A and capture B.

    One mutable object rather than two skills, because the whole point is that
    both captures run against the SAME skill and the same shared fields.
    """

    def __init__(self) -> None:
        self.reader_loads = True
        self.payload: dict | None = {"local_frame": True}
        self.position: dict | None = None
        self.reject_reason: str | None = None
        self.present = True
        self.rows: list[dict] = [
            {"row": 0, "kind": "zone", "trusted": True, "text": "Zone: OOC_x",
             "cost": 0.10},
        ]


class _FakeReader:
    def __init__(self, plan: _Plan) -> None:
        self._plan = plan

    def read(self, frame, count):
        return None, None, list(self._plan.rows)


class _FakeScanner:
    def __init__(self, plan: _Plan) -> None:
        self._plan = plan

    @property
    def last_reject_reason(self):
        return self._plan.reject_reason

    def parse_payload(self, payload: dict):
        return self._plan.position


def _skill(tmp_path, monkeypatch, plan: _Plan, db=None) -> main.SC_NavPoint:
    """A skill driven through the real capture path, scripted by `plan`."""
    monkeypatch.setattr(mss_module, "mss", _Screen())
    monkeypatch.setattr(main.time, "sleep", lambda s: None)
    monkeypatch.setattr(main.overlay_reader, "block_region", lambda m: dict(_REGION))
    monkeypatch.setattr(
        main.overlay_reader, "capture_is_usable", lambda f, *a: (True, "")
    )
    monkeypatch.setattr(
        main.overlay_reader, "overlay_is_present", lambda f: plan.present
    )
    monkeypatch.setattr(main.overlay_reader, "overlay_ink_fraction", lambda f: 0.5)
    monkeypatch.setattr(main.overlay_reader, "overlay_row_periodicity", lambda f: 0.5)
    monkeypatch.setattr(
        main.overlay_fields, "payload_from_rows",
        lambda rows: dict(plan.payload) if plan.payload else None,
    )

    skill = main.SC_NavPoint.__new__(main.SC_NavPoint)
    skill.printr = _Printr()
    skill.get_generated_files_dir = lambda: str(tmp_path)
    skill._db = db
    skill._ui_server = _RecordingUI()
    skill._ui_window = None
    skill._active_target = None
    skill._hud_opened = False
    skill._last_position = None
    skill._reader_state = ""
    skill._last_ring_state = ""
    skill._capture_lock = threading.Lock()
    skill._scanner = _FakeScanner(plan)
    skill._local_reader = lambda: _FakeReader(plan) if plan.reader_loads else None
    skill._get_display = lambda: 1
    skill._get_poll_interval = lambda: 5
    skill._get_arrival_alert_m = lambda: 1000.0
    skill._get_arrival_stop_m = lambda: 250.0
    skill._start_nav_polling = MagicMock()
    skill._stop_nav_polling = MagicMock()
    skill._sync_ring = lambda: None
    skill._implausible_badge_shown = False
    skill._units_badge_shown = False
    skill._frame_badge_shown = False
    skill._mismatch_badge_shown = False
    skill._server_shape_badge_shown = False
    skill._pending_server_change = None
    skill._pending_server_count = 0
    return skill


def _inject_b(monkeypatch, skill: main.SC_NavPoint, become_b) -> None:
    """Land a SECOND capture in the window the bug lives in.

    Between `_capture_position_local` returning (which releases the lock) and
    the awaiting coroutine resuming. `become_b` rewrites the plan so the second
    capture ends differently from the first.

    The second capture runs on a bare `threading.Thread`, which is what the poll
    thread is. A new thread starts with an empty context, so it cannot see the
    awaiting caller's sink; that is the isolation under test, not a convenience.

    `fired` is a list rather than a `nonlocal` flag so the closure needs no
    rebinding, and `join(timeout=5)` bounds it: nothing here waits on a clock.
    """
    real_to_thread = asyncio.to_thread
    fired: list[int] = []

    async def _to_thread_then_b(func, /, *args, **kwargs):
        result = await real_to_thread(func, *args, **kwargs)
        if not fired:
            fired.append(1)
            become_b()
            thread = threading.Thread(target=skill._capture_position_local)
            thread.start()
            thread.join(timeout=5)
            assert not thread.is_alive(), "the injected capture never finished"
        return result

    monkeypatch.setattr(main.asyncio, "to_thread", _to_thread_then_b)


def _trace(tmp_path: Path) -> str:
    path = tmp_path / "navpoint_poll.log"
    return path.read_text(encoding="utf-8") if path.exists() else ""


# --------------------------------------------------------------------- #
# The kind, the hint and the badge
# --------------------------------------------------------------------- #


def test_a_tool_reports_its_own_capture_not_the_poll_thread_s(tmp_path, monkeypatch):
    """A is a gate refusal, B is a reader that would not load. The player asked
    about A and must be told about A."""
    plan = _Plan()
    plan.payload = None  # A: the overlay was read, no payload came out of it.
    skill = _skill(tmp_path, monkeypatch, plan, db=NavPointDatabase(str(tmp_path)))

    def _become_b() -> None:
        plan.reader_loads = False  # B: KIND_NO_READER.

    _inject_b(monkeypatch, skill, _become_b)

    result = json.loads(asyncio.run(skill.mark_location()))

    # The shared field really did move on, so this is the race and not a
    # scenario where both captures happened to agree.
    assert skill._last_outcome.kind == fields.KIND_NO_READER
    assert result["capture_kind"] == fields.KIND_GATE


def test_a_tool_is_not_handed_the_overlay_hint_for_an_overlay_it_just_read(
    tmp_path, monkeypatch
):
    """The console command belongs to ONE kind, and it is relayed to the player
    word for word. A read the overlay perfectly; B looked while it was hidden."""
    plan = _Plan()
    plan.payload = None  # A: gate refusal, overlay present and read.
    skill = _skill(tmp_path, monkeypatch, plan, db=NavPointDatabase(str(tmp_path)))

    def _become_b() -> None:
        plan.present = False  # B: KIND_ABSENT, the one kind carrying the hint.

    _inject_b(monkeypatch, skill, _become_b)

    raw = asyncio.run(skill.mark_location())
    result = json.loads(raw)

    assert skill._last_outcome.kind == fields.KIND_ABSENT
    assert "hint" not in result
    assert "r_displayinfo" not in raw


def test_the_badge_names_the_caller_s_own_reject_reason(tmp_path, monkeypatch):
    """The badge goes to the chat log exactly as written, so the wrong one is
    not paraphrased into something vaguer. A's reason asks the player to hold
    still; B's asks them to look again for a different thing entirely."""
    plan = _Plan()
    plan.position = None
    plan.reject_reason = "frame_mismatch"
    skill = _skill(tmp_path, monkeypatch, plan, db=NavPointDatabase(str(tmp_path)))

    def _become_b() -> None:
        plan.reject_reason = "unreadable_units"

    _inject_b(monkeypatch, skill, _become_b)

    asyncio.run(skill.mark_location())

    messages = [message for message, _, _ in skill.printr.calls]
    assert len(messages) == 1, messages
    assert "SolarSystem and Root lines did not" in messages[0]
    assert "unit on a coordinate" not in messages[0]


def test_the_capture_line_carries_the_caller_s_own_metrics(tmp_path, monkeypatch):
    """The success line is the only control group the refusal diagnostics have,
    so a line carrying another capture's ink and trusted counts is worse than no
    line: it reads as evidence."""
    plan = _Plan()
    plan.position = {"body": "Daymar", "x": 1.0, "y": 2.0, "z": 3.0}
    skill = _skill(tmp_path, monkeypatch, plan, db=NavPointDatabase(str(tmp_path)))

    def _become_b() -> None:
        # B decodes four rows, only one of them trusted, at a much worse cost.
        plan.rows = [
            {"row": 0, "kind": "zone", "trusted": True, "text": "b", "cost": 0.90},
            {"row": 1, "kind": "zone", "trusted": False, "text": "b", "cost": 0.90},
            {"row": 2, "kind": "zone", "trusted": False, "text": "b", "cost": 0.90},
            {"row": 3, "kind": "zone", "trusted": False, "text": "b", "cost": 0.90},
        ]

    _inject_b(monkeypatch, skill, _become_b)

    asyncio.run(skill.mark_location("Cave"))

    line = [ln for ln in _trace(tmp_path).splitlines() if "capture frame=" in ln]
    assert len(line) == 1, line
    # A's numbers: one row, trusted, cost 0.10.
    assert "trusted=1/1" in line[0], line[0]
    assert "cost=0.10" in line[0], line[0]
    # B's, which the shared field is holding by now.
    assert "trusted=1/4" not in line[0], line[0]
    assert "cost=0.90" not in line[0], line[0]


# --------------------------------------------------------------------- #
# The fallback, and the lifetime of the channel
# --------------------------------------------------------------------- #


def test_a_replaced_capture_seam_still_reports_through_the_shared_field(tmp_path):
    """WHY THE FALLBACK EXISTS, named so it is not deleted as dead code.

    Eight existing tests replace the capture seams with doubles that never reach
    the code which fills the sink, so for them the shared field is the only
    answer available. Unreachable in production, where the real capture always
    publishes."""
    skill = main.SC_NavPoint.__new__(main.SC_NavPoint)
    skill.printr = _Printr()
    skill._db = NavPointDatabase(str(tmp_path))
    skill._ui_server = _RecordingUI()
    skill._sync_ring = lambda: None
    skill._get_display = lambda: 1

    async def _capture(attempts: int = 1):
        return None

    skill._capture_position = _capture
    skill._last_outcome = fields.CaptureOutcome(kind=fields.KIND_UNUSABLE)

    result = json.loads(asyncio.run(skill.mark_location()))

    assert result["capture_kind"] == fields.KIND_UNUSABLE


def test_the_sink_does_not_outlive_its_caller(tmp_path):
    """A leaked sink would hand the NEXT caller this one's outcome, which is the
    defect itself rather than a tidiness point.

    Asserted on the context manager DIRECTLY, in one context. Checking the var
    after `asyncio.run` proves nothing: `asyncio.run` runs its coroutine in a
    copy of the caller's context, so a sink set inside can never be visible
    outside it whether or not anything resets the token. Two tool calls that
    share a context are the case that can actually leak, and two tool calls on
    one event loop are ordinary.
    """
    assert main._CAPTURE_SINK.get() is None

    with main._capture_sink() as first:
        first.append(fields.CaptureOutcome(kind=fields.KIND_UNUSABLE))
        assert main._CAPTURE_SINK.get() is first
    assert main._CAPTURE_SINK.get() is None

    with main._capture_sink() as second:
        assert second == [], "the next caller inherited the previous sink"
    assert main._CAPTURE_SINK.get() is None

    # And end to end: two tool calls on ONE event loop, where the contexts are
    # genuinely shared.
    skill = main.SC_NavPoint.__new__(main.SC_NavPoint)
    skill.printr = _Printr()
    skill._db = NavPointDatabase(str(tmp_path))
    skill._ui_server = _RecordingUI()
    skill._sync_ring = lambda: None
    skill._get_display = lambda: 1
    seen: list = []

    async def _capture(attempts: int = 1):
        sink = main._CAPTURE_SINK.get()
        assert sink is not None, "the sink was never opened"
        seen.append(sink)
        return None

    skill._capture_position = _capture
    skill._last_outcome = fields.CaptureOutcome(kind=fields.KIND_UNUSABLE)

    async def _twice() -> None:
        await skill.mark_location()
        await skill.mark_location()

    asyncio.run(_twice())

    assert len(seen) == 2
    assert seen[0] is not seen[1], "both calls shared one sink"
    assert main._CAPTURE_SINK.get() is None


def test_the_capture_line_reports_the_time_the_caller_actually_waited(
    tmp_path, monkeypatch
):
    """`_capture_ms()` reads a stamp that every capture restamps inside the
    lock, so a caller reading it after its own capture returned reports the
    OTHER capture's duration, and always as a SHORTER time than it waited. A
    retry policy judged on those numbers would be judged on the wrong ones.

    A's read takes 0.25 s and B's is instant. The assertion is ONE-SIDED, so it
    cannot flake on a fast machine: with the defect the figure is near zero.
    """
    plan = _Plan()
    plan.position = {"body": "Daymar", "x": 1.0, "y": 2.0, "z": 3.0}
    skill = _skill(tmp_path, monkeypatch, plan, db=NavPointDatabase(str(tmp_path)))

    slow = {"on": True}
    real_read = _FakeReader.read

    def _maybe_slow(self, frame, count):
        if slow["on"]:
            _real_sleep(0.25)
        return real_read(self, frame, count)

    monkeypatch.setattr(_FakeReader, "read", _maybe_slow)

    def _become_b() -> None:
        slow["on"] = False

    _inject_b(monkeypatch, skill, _become_b)

    asyncio.run(skill.mark_location("Cave"))

    line = [ln for ln in _trace(tmp_path).splitlines() if "capture frame=" in ln]
    assert len(line) == 1, line
    match = re.search(r"\bms=(\d+)$", line[0])
    assert match, line[0]
    assert int(match.group(1)) >= 200, line[0]
