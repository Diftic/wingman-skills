"""Legacy attempt arguments cannot retry a refused capture.

The real capture dispatcher is exercised with fake screenshots and decoding.
Each call gets one frame, reports its outcome and leaves another fresh capture
to the next independent call. No failed mark silently reads a later position.
"""

from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

import pytest


pytest.importorskip("PIL")
pytest.importorskip("mss")

sys.path.insert(0, str(Path(__file__).resolve().parent))

from test_main_capture import _install_runtime_stubs


_install_runtime_stubs()

import mss as mss_module

import main


_REGION = {"left": 0, "top": 0, "width": 10, "height": 5}

# What a frame the guards accept produces. Its content is irrelevant here: which
# gate refuses which rows is `test_capture_trace.py`'s subject.
_PAYLOAD = {"local_frame": False}


class _Printr:
    def print(self, message, color=None, server_only=False):
        pass


class _FakeGrab:
    def __init__(self, region: dict) -> None:
        self.size = (region["width"], region["height"])
        self.bgra = bytes(region["width"] * region["height"] * 4)


class _Screen:
    """One scripted frame per grab, standing in for mss.

    The script is the premise of the whole feature made testable: attempt two
    sees different pixels from attempt one. A script shorter than the attempt
    count repeats its last entry, so a test only has to spell out what changes.
    """

    def __init__(self, script: list[dict | None]) -> None:
        self.script = script
        self.grabs = 0
        self.gate_calls = 0
        self.monitors = [dict(_REGION), dict(_REGION)]

    def __call__(self) -> _Screen:
        return self

    def __enter__(self) -> _Screen:
        return self

    def __exit__(self, *exc_info) -> bool:
        return False

    def grab(self, region: dict) -> _FakeGrab:
        self.grabs += 1
        return _FakeGrab(region)

    def rows(self) -> list[dict]:
        """What the reader decodes off the frame this grab landed on.

        The row text carries the attempt number, so the trace proves WHICH
        frame's rows were dumped and not merely that some rows were.
        """
        payload = self.script[min(self.grabs, len(self.script)) - 1]
        return [
            {
                "row": 0,
                "kind": "zone",
                "trusted": True,
                "text": f"Zone: attempt-{self.grabs}",
                "payload": payload,
            }
        ]


class _FakeReader:
    def __init__(self, screen: _Screen) -> None:
        self._screen = screen

    def read(self, frame, count):
        return None, None, self._screen.rows()


class _FakeScanner:
    """Turns an accepted payload into a position, and records what it was given.

    The record is how a test proves a refused frame never reached the parser.
    """

    def __init__(self) -> None:
        self.last_reject_reason = None
        self.payloads: list[dict] = []

    def parse_payload(self, payload: dict) -> dict:
        self.payloads.append(payload)
        return {"x": 1.0, "y": 2.0, "z": 3.0, "payload": payload}


def _skill(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, script: list[dict | None]
) -> tuple[main.SC_NavPoint, _Screen, list[float]]:
    """A skill whose capture sees `script`, one entry per grab.

    Returns the skill, the screen (which counts grabs and gate calls), and the
    list of pauses the retry took, recorded rather than slept so the suite stays
    fast and so a test can assert the pause happened at all.
    """
    screen = _Screen(list(script))
    sleeps: list[float] = []

    def _payload_from_rows(rows: list[dict]) -> dict | None:
        # Counted, because "every guard applies to every attempt" is the claim
        # the retry lives or dies on. A true function of the rows it is given,
        # so the payload an attempt accepts came from that attempt's own frame.
        screen.gate_calls += 1
        return rows[0]["payload"]

    monkeypatch.setattr(mss_module, "mss", screen)
    monkeypatch.setattr(main.time, "sleep", sleeps.append)
    monkeypatch.setattr(main.overlay_reader, "block_region", lambda m: dict(_REGION))
    monkeypatch.setattr(
        main.overlay_reader, "capture_is_usable", lambda f, *a: (True, "")
    )
    monkeypatch.setattr(main.overlay_reader, "overlay_is_present", lambda f: True)
    monkeypatch.setattr(main.overlay_reader, "overlay_ink_fraction", lambda f: 0.5)
    monkeypatch.setattr(main.overlay_reader, "overlay_row_periodicity", lambda f: 0.5)
    monkeypatch.setattr(main.overlay_fields, "payload_from_rows", _payload_from_rows)
    monkeypatch.setattr(
        main.overlay_fields,
        "ring_state",
        lambda rows, payload, present, usable: (
            "" if payload is not None else f"NO SIGNAL {rows[0]['text']}"
        ),
    )

    skill = main.SC_NavPoint.__new__(main.SC_NavPoint)
    skill.printr = _Printr()
    skill.get_generated_files_dir = lambda: str(tmp_path)
    skill._get_display = lambda: 1
    skill._reader_state = ""
    skill._scanner = _FakeScanner()
    skill._local_reader = lambda: _FakeReader(screen)
    return skill, screen, sleeps


def _trace(tmp_path: Path) -> str:
    path = tmp_path / "navpoint_poll.log"
    return path.read_text(encoding="utf-8") if path.exists() else ""


# --------------------------------------------------------------------- #
# Cost
# --------------------------------------------------------------------- #


def test_a_readable_first_frame_is_grabbed_once(tmp_path, monkeypatch):
    """Current single-pass/held-display policy; supersedes the earlier retry rule."""
    skill, screen, sleeps = _skill(tmp_path, monkeypatch, [_PAYLOAD])

    position = skill._capture_position_local(main.MARK_CAPTURE_ATTEMPTS)

    assert position["captured_at"] > 0
    assert {k:v for k,v in position.items() if k != "captured_at"} == {"x": 1.0, "y": 2.0, "z": 3.0, "payload": _PAYLOAD}
    assert screen.grabs == 1
    assert sleeps == []
    # An unremarkable capture stays out of the log, as it always has.
    assert "read on attempt" not in _trace(tmp_path)


def test_the_default_capture_looks_exactly_once(tmp_path, monkeypatch):
    """The poll loop must not inherit the mark path's cost.

    It runs every few seconds, so a frame it loses costs a few seconds; five
    grabs and four pauses a tick would multiply its cost to buy that back.
    """
    skill, screen, sleeps = _skill(tmp_path, monkeypatch, [None])

    assert skill._capture_position_local() is None

    assert screen.grabs == 1
    assert sleeps == []
    assert "attempts=1]" in _trace(tmp_path)


def test_the_poll_seam_passes_no_attempt_count(tmp_path, monkeypatch):
    """`_capture_position` is what the poll loop calls, so the default has to
    survive the outer seam too, not just the inner one."""
    skill, screen, _ = _skill(tmp_path, monkeypatch, [None])

    assert asyncio.run(skill._capture_position()) is None

    assert screen.grabs == 1


def test_the_outer_seam_forwards_the_attempt_count(tmp_path, monkeypatch):
    """Current single-pass/held-display policy; supersedes the earlier retry rule."""
    skill, screen, _ = _skill(tmp_path, monkeypatch, [None, None, _PAYLOAD])

    position = asyncio.run(
        skill._capture_position(attempts=main.MARK_CAPTURE_ATTEMPTS)
    )

    assert position is None
    assert screen.grabs == 1


def test_the_mark_path_requests_one_attempt(tmp_path, monkeypatch):
    """Marking follows the same single-pass policy as tracking."""
    asked: list[int] = []

    async def _recording_capture(attempts: int = 1):
        asked.append(attempts)
        return None

    skill = main.SC_NavPoint.__new__(main.SC_NavPoint)
    skill._db = object()
    skill._capture_position = _recording_capture

    result = json.loads(asyncio.run(skill.mark_location("Somewhere")))

    assert asked == [main.MARK_CAPTURE_ATTEMPTS]
    assert "error" in result


# --------------------------------------------------------------------- #
# Outcome
# --------------------------------------------------------------------- #


def test_refused_mark_cannot_reach_a_later_success(tmp_path, monkeypatch):
    """Current single-pass/held-display policy; supersedes the earlier retry rule."""
    skill, screen, sleeps = _skill(tmp_path, monkeypatch, [None, None, _PAYLOAD])

    position = skill._capture_position_local(main.MARK_CAPTURE_ATTEMPTS)

    assert position is None
    assert screen.grabs == 1
    # The first frame is refused; later fake successes remain unread.
    assert screen.gate_calls == 1
    assert skill._scanner.payloads == []
    assert sleeps == []


def test_refused_first_attempt_is_named_in_the_trace(tmp_path, monkeypatch):
    """Current single-pass/held-display policy; supersedes the earlier retry rule."""
    skill, _, _ = _skill(tmp_path, monkeypatch, [None, None, _PAYLOAD])

    assert skill._capture_position_local(main.MARK_CAPTURE_ATTEMPTS) is None

    trace = _trace(tmp_path)
    assert "capture attempt 1/1" in trace
    # The first refusal is the final outcome for this call.
    assert "REFUSED" in trace


def test_one_refusal_ends_capture_and_says_so(tmp_path, monkeypatch):
    """Current single-pass/held-display policy; supersedes the earlier retry rule."""
    skill, screen, sleeps = _skill(tmp_path, monkeypatch, [None])

    assert skill._capture_position_local(main.MARK_CAPTURE_ATTEMPTS) is None

    assert screen.grabs == 1
    assert screen.gate_calls == 1
    assert sleeps == []
    trace = _trace(tmp_path)
    # One refusal line per capture, not one per frame, so a grep for REFUSED
    # still counts marks that failed rather than frames that were skipped.
    assert trace.count("REFUSED") == 1
    assert "attempts=1]" in trace
    # Every field the user greps survives the new one landing beside them.
    assert "present=True usable=True rows=1" in trace
    assert "region={'left': 0, 'top': 0, 'width': 10, 'height': 5}" in trace
    assert "ink=0.50000" in trace and "periodicity=0.50000" in trace


def test_the_row_dump_is_the_frame_the_mark_died_on(tmp_path, monkeypatch):
    """Current single-pass/held-display policy; supersedes the earlier retry rule."""
    skill, _, _ = _skill(tmp_path, monkeypatch, [None])

    assert skill._capture_position_local(main.MARK_CAPTURE_ATTEMPTS) is None

    trace = _trace(tmp_path)
    assert "row[0] kind='zone' trusted=True text='Zone: attempt-1'" in trace
    assert "attempt-2'" not in trace


def test_the_ring_reflects_the_final_attempt(tmp_path, monkeypatch):
    """Current single-pass/held-display policy; supersedes the earlier retry rule."""
    skill, _, _ = _skill(tmp_path, monkeypatch, [None])

    skill._capture_position_local(main.MARK_CAPTURE_ATTEMPTS)

    assert skill._reader_state == "NO SIGNAL Zone: attempt-1"


def test_later_success_cannot_erase_current_refusal(tmp_path, monkeypatch):
    """Current single-pass/held-display policy; supersedes the earlier retry rule."""
    skill, _, _ = _skill(tmp_path, monkeypatch, [None, _PAYLOAD])

    assert skill._capture_position_local(main.MARK_CAPTURE_ATTEMPTS) is None

    assert skill._reader_state == "NO SIGNAL Zone: attempt-1"
