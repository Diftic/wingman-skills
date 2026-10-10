"""The capture path must name the gate that refused it, in navpoint_poll.log.

A mark that fails writes nothing a human can read: the skill's `logger` output
never reaches wingman-core.log (see main._poll_trace), so before this
instrumentation existed a refusal cost a live probe session against a running
game to explain. These tests pin the trace itself, one test per gate, because
an instrument nobody proved emits is indistinguishable from silence when the
failure finally happens.

Every gate is driven through the real `_capture_position_local`. Only the
collaborators are faked (mss, the reader, the gate predicates), so the branch
selection under test is the shipping one.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest


pytest.importorskip("PIL")
pytest.importorskip("mss")

sys.path.insert(0, str(Path(__file__).resolve().parent))

from test_main_capture import _install_runtime_stubs  # noqa: E402


_install_runtime_stubs()

import mss as mss_module  # noqa: E402

import main  # noqa: E402
import overlay_fields as fields  # noqa: E402


_REGION = {"left": 0, "top": 0, "width": 10, "height": 5}


class _Printr:
    def print(self, message, color=None, server_only=False):
        pass


class _FakeGrab:
    def __init__(self, region: dict) -> None:
        self.size = (region["width"], region["height"])
        self.bgra = bytes(region["width"] * region["height"] * 4)


class _FakeSct:
    def __init__(self, exc: Exception | None) -> None:
        self._exc = exc
        self.monitors = [dict(_REGION), dict(_REGION)]

    def __enter__(self) -> _FakeSct:
        return self

    def __exit__(self, *exc_info) -> bool:
        return False

    def grab(self, region: dict) -> _FakeGrab:
        if self._exc is not None:
            raise self._exc
        return _FakeGrab(region)


class _FakeReader:
    def __init__(self, rows: list, exc: Exception | None = None) -> None:
        self._rows = rows
        self._exc = exc

    def read(self, frame, count):
        if self._exc is not None:
            raise self._exc
        return None, None, self._rows


class _FakeScanner:
    def __init__(self, result: dict | None, reason: str | None = None) -> None:
        self._result = result
        self.last_reject_reason = reason

    def parse_payload(self, payload: dict) -> dict | None:
        return self._result


def _skill(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    *,
    reader=None,
    scanner=None,
    grab_exc: Exception | None = None,
    usable: tuple[bool, str] = (True, ""),
    present: bool = True,
    payload: dict | None = None,
):
    """A skill wired so exactly one capture gate refuses."""
    monkeypatch.setattr(mss_module, "mss", lambda: _FakeSct(grab_exc))
    monkeypatch.setattr(main.overlay_reader, "block_region", lambda m: dict(_REGION))
    monkeypatch.setattr(main.overlay_reader, "capture_is_usable", lambda f, *a: usable)
    monkeypatch.setattr(main.overlay_reader, "overlay_is_present", lambda f: present)
    monkeypatch.setattr(main.overlay_reader, "overlay_ink_fraction", lambda f: 0.5)
    monkeypatch.setattr(main.overlay_reader, "overlay_row_periodicity", lambda f: 0.5)
    monkeypatch.setattr(main.overlay_fields, "payload_from_rows", lambda rows: payload)
    monkeypatch.setattr(main.overlay_fields, "ring_state", lambda *a: "")

    skill = main.SC_NavPoint.__new__(main.SC_NavPoint)
    skill.printr = _Printr()
    skill.get_generated_files_dir = lambda: str(tmp_path)
    skill._get_display = lambda: 1
    skill._reader_state = ""
    skill._scanner = scanner
    skill._local_reader = lambda: reader
    return skill


def _trace(tmp_path: Path) -> str:
    path = tmp_path / "navpoint_poll.log"
    return path.read_text(encoding="utf-8") if path.exists() else ""


def test_missing_reader_is_named(tmp_path, monkeypatch):
    skill = _skill(tmp_path, monkeypatch, reader=None, scanner=_FakeScanner({}))
    assert skill._capture_position_local() is None
    assert "capture REFUSED: reader=unavailable" in _trace(tmp_path)


def test_missing_scanner_is_named(tmp_path, monkeypatch):
    skill = _skill(tmp_path, monkeypatch, reader=_FakeReader([]), scanner=None)
    assert skill._capture_position_local() is None
    assert "scanner=unavailable" in _trace(tmp_path)


def test_grab_failure_names_the_display(tmp_path, monkeypatch):
    skill = _skill(
        tmp_path,
        monkeypatch,
        reader=_FakeReader([]),
        scanner=_FakeScanner({}),
        grab_exc=OSError("no such display"),
    )
    assert skill._capture_position_local() is None
    trace = _trace(tmp_path)
    assert "capture REFUSED: screen grab failed on display 1" in trace
    assert "OSError: no such display" in trace


def test_unusable_frame_reports_its_reason(tmp_path, monkeypatch):
    skill = _skill(
        tmp_path,
        monkeypatch,
        reader=_FakeReader([]),
        scanner=_FakeScanner({}),
        usable=(False, "rows saturated"),
    )
    assert skill._capture_position_local() is None
    assert "frame unusable (rows saturated)" in _trace(tmp_path)


def test_absent_overlay_is_distinguished_from_an_unreadable_one(tmp_path, monkeypatch):
    skill = _skill(
        tmp_path,
        monkeypatch,
        reader=_FakeReader([]),
        scanner=_FakeScanner({}),
        present=False,
    )
    assert skill._capture_position_local() is None
    trace = _trace(tmp_path)
    assert "overlay not on screen" in trace
    # The player action differs for the two, so the line must not blur them.
    assert "frame unusable" not in trace


def test_decode_exception_is_recorded(tmp_path, monkeypatch):
    skill = _skill(
        tmp_path,
        monkeypatch,
        reader=_FakeReader([], exc=ValueError("glyph bank corrupt")),
        scanner=_FakeScanner({}),
    )
    assert skill._capture_position_local() is None
    assert "decode raised ValueError: glyph bank corrupt" in _trace(tmp_path)


def test_rows_without_payload_report_the_row_count(tmp_path, monkeypatch):
    skill = _skill(
        tmp_path,
        monkeypatch,
        reader=_FakeReader([{"row": 0}, {"row": 1}]),
        scanner=_FakeScanner({}),
        payload=None,
    )
    assert skill._capture_position_local() is None
    assert "no payload from 2 row(s)" in _trace(tmp_path)


def test_parse_rejection_carries_the_gate_name(tmp_path, monkeypatch):
    skill = _skill(
        tmp_path,
        monkeypatch,
        reader=_FakeReader([{"row": 0}]),
        scanner=_FakeScanner(None, reason="unreadable_units"),
        payload={"local_frame": False},
    )
    assert skill._capture_position_local() is None
    assert "parse_payload rejected the read (reason='unreadable_units')" in _trace(
        tmp_path
    )


def test_geometry_is_recorded_so_a_misaimed_capture_is_visible(tmp_path, monkeypatch):
    """An overlay the player never enabled and a capture aimed at the wrong
    pixels produce the same refusal, so the region has to be in the line."""
    skill = _skill(
        tmp_path,
        monkeypatch,
        reader=_FakeReader([]),
        scanner=_FakeScanner({}),
        present=False,
    )
    skill._capture_position_local()
    trace = _trace(tmp_path)
    assert "region={'left': 0, 'top': 0, 'width': 10, 'height': 5}" in trace
    assert "ink=0.50000" in trace and "periodicity=0.50000" in trace


def test_a_good_capture_stays_quiet(tmp_path, monkeypatch):
    """The poll loop already logs one line per successful tick. A second line
    here would double every healthy session's trace and bury the refusals."""
    position = {"local_frame": False, "x": 1.0, "y": 2.0, "z": 3.0}
    skill = _skill(
        tmp_path,
        monkeypatch,
        reader=_FakeReader([{"row": 0}]),
        scanner=_FakeScanner(position),
        payload={"local_frame": False},
    )
    assert skill._capture_position_local() == position
    assert "REFUSED" not in _trace(tmp_path)


# --------------------------------------------------------------------- #
# Which of the five `payload_from_rows` gates refused
# --------------------------------------------------------------------- #
#
# "no payload from 3 row(s)" names the symptom and not one of five different
# causes, each of which asks something different of the player: move, look at
# darker ground, wait a tick, or accept that this spot cannot be marked. The ids
# below are an INTERFACE, asserted as literal strings rather than through the
# GATE_* constants, because a log file written months ago is grepped for the
# string and renaming the constant's value must break a test, not a search.
#
# Every row text is a real line, taken from the captures the sibling gate tests
# were built from, so the shapes match what the parsers in `overlay_fields`
# actually see.


def _row(text: str, kind: str = "zone", trusted: bool = True, row: int = 0) -> dict:
    return {"row": row, "trusted": trusted, "kind": kind, "text": text}


_SYSTEM_ROW = _row(
    "Zone: SolarSystem_745338555312 Pos: -16104284.9222km "
    "7588008.0968km 119.0037km"
)
_ROOT_ROW = _row("Zone: Root Pos: -16104284.9222km 7588008.0968km 119.0037km")
_SHIP_ROW = _row("Zone: DRAK_Clipper_742164815970 Pos: 0.00m 11.56m 2.83m")
_PYRO3_ROWS = [_row("Zone: pyro3 Pos: 330.7421km 218.7408km 119.0037km"),
               _SYSTEM_ROW, _ROOT_ROW]


def test_gate_no_system_line_is_named():
    """No SolarSystem line at all, so there is no frame to place anything in."""
    reason = fields.refusal_reason([_SHIP_ROW, _ROOT_ROW])
    assert reason.startswith("no_system_line:")
    assert "SolarSystem" in reason


def test_gate_refused_above_is_named_with_its_count():
    """An unreadable row above SolarSystem that could still BE an OOC line."""
    rows = [
        _row("Zone: ???_?yro_1_Bloom Pos: 1m 2m 3m", trusted=False),
        _SYSTEM_ROW,
        _ROOT_ROW,
    ]
    reason = fields.refusal_reason(rows)
    assert reason.startswith("refused_above:")
    # The count is the thing that says whether one row or the whole block went.
    assert "1 unreadable row(s)" in reason


def test_gate_body_scale_is_named_with_the_distance_it_read():
    """The Pyro 3 stack, where the container is the size of a world."""
    reason = fields.refusal_reason(_PYRO3_ROWS)
    assert reason.startswith("body_scale:")
    # Without the measurement the player cannot tell a real surface from a
    # threshold that needs moving.
    assert "330.7421km" in reason


def test_gate_no_coordinate_is_named():
    """A zone line that answers neither question, so it clears no guard."""
    rows = [
        _row("Zone: P5_?2 Pos: ???.????km ???.????km ???.????km", trusted=False),
        _SYSTEM_ROW,
        _ROOT_ROW,
    ]
    reason = fields.refusal_reason(rows)
    assert reason.startswith("no_coordinate:")


def test_gate_no_root_is_named():
    """A clean SolarSystem line with nothing to cross-check it against."""
    reason = fields.refusal_reason([_SHIP_ROW, _SYSTEM_ROW])
    assert reason.startswith("no_root:")


def test_a_payload_has_no_reason():
    """An empty reason and a refusal must not be confusable."""
    rows = [
        _row("CamDir: -20  26 -174 FOV: 44 Focal: 3.00 FStop: 64.0", "camdir"),
        _SHIP_ROW,
        _row("Zone: SolarSystem_730084885606 Pos: -16104264604.7km "
             "7587753462.6km 13096.9m"),
        _row("Zone: Root Pos: -16104264604.7km 7587753462.6km 13096.9m"),
    ]
    assert fields.payload_from_rows(rows) is not None
    assert fields.refusal_reason(rows) == ""


# The same Pyro 3 stack with an unreadable Root line. Since schema 1 a COMPLETE
# Pyro 3 stack no longer refuses the capture at all: the coordinate stack reads
# those rows without needing a name, which is the whole point of the rework, and
# `test_a_complete_pyro_3_stack_now_captures` below pins that. Damaging Root is
# what still produces a refusal reaching the trace, and it leaves the legacy
# `body_scale` gate at the front of the reason exactly where the grep expects it.
_PYRO3_ROWS_NO_ROOT = [
    _PYRO3_ROWS[0],
    _SYSTEM_ROW,
    _row("Zone: Root Pos: -16104284.9222km 7588008.0968km 119.00?7km",
         trusted=False),
]


def test_the_gate_name_reaches_the_trace_file(tmp_path, monkeypatch):
    """The whole point: the id has to survive as far as navpoint_poll.log."""
    skill = _skill(
        tmp_path,
        monkeypatch,
        reader=_FakeReader(_PYRO3_ROWS_NO_ROOT),
        scanner=_FakeScanner({}),
        payload=None,
    )
    assert skill._capture_position_local() is None
    trace = _trace(tmp_path)
    assert "no payload from 3 row(s): body_scale:" in trace
    # The fields the user greps must survive the new clause landing beside them.
    assert "present=True usable=True rows=3" in trace
    # And the stack's own gate is named beside it, so a log says which parser
    # refused rather than leaving the newer one silent.
    assert "stack: stack_root_unreadable" in trace


def test_a_complete_pyro_3_stack_now_captures(tmp_path, monkeypatch):
    """Current single-pass/held-display policy; supersedes the earlier retry rule."""
    skill = _skill(
        tmp_path,
        monkeypatch,
        reader=_FakeReader(_PYRO3_ROWS),
        scanner=_FakeScanner({"captured": True}),
        payload=None,
    )
    position = skill._capture_position_local()
    assert position["captured"] is True
    assert position["captured_at"] > 0
    assert fields.payload_from_rows(_PYRO3_ROWS) is None
    stack, reason = fields.stack_from_rows(_PYRO3_ROWS)
    assert reason == ""
    assert stack.local_candidate.raw_name == "pyro3"


def test_the_decoded_rows_reach_the_trace_with_their_refusal_marks(
    tmp_path, monkeypatch
):
    """The gate says which question failed, the rows say what it was asked of.

    The `?` marks are the payload of this line: they are where the reader gave
    up, and a text logged without them looks like a clean read that was refused
    for no reason.
    """
    rows = [
        _row("Zone: p?ro3 Pos: 330.7421km ???.????km 119.0037km",
             trusted=False, row=3),
        _row("Zone: SolarSystem_745338555312 Pos: -16104284.9222km "
             "7588008.0968km 119.0037km", row=4),
    ]
    skill = _skill(
        tmp_path,
        monkeypatch,
        reader=_FakeReader(rows),
        scanner=_FakeScanner({}),
        payload=None,
    )
    assert skill._capture_position_local() is None
    trace = _trace(tmp_path)
    assert (
        "row[3] kind='zone' trusted=False "
        "text='Zone: p?ro3 Pos: 330.7421km ???.????km 119.0037km'"
    ) in trace
    assert "row[4] kind='zone' trusted=True" in trace
    # Untruncated, marks included: the tail is where the answer usually is.
    assert "119.0037km'" in trace


def test_a_gate_walk_that_raises_cannot_change_the_capture(tmp_path, monkeypatch):
    """Instrumentation must never be the reason a capture fails differently.

    The gate walk parses real overlay text, so it can raise on a row shape it
    was not built for. If that took the refusal path with it, the trace would
    report a decode error that never happened.
    """
    def _boom(rows):
        raise RuntimeError("gate walk exploded")

    monkeypatch.setattr(main.overlay_fields, "refusal_reason", _boom)
    skill = _skill(
        tmp_path,
        monkeypatch,
        reader=_FakeReader([{"row": 0}]),
        scanner=_FakeScanner({}),
        payload=None,
    )
    assert skill._capture_position_local() is None
    trace = _trace(tmp_path)
    assert "no payload from 1 row(s): gate unknown (RuntimeError: gate walk " in trace
    assert "decode raised" not in trace
