"""Every attempt, every row field and every build must leave a line to read.

The reader has produced no successful field capture since 2026-07-31, and the
whole record of that failure is six lines. Diagnosing it needs evidence the log
does not carry today, so these tests pin the instrumentation that produces it:
one line per ATTEMPT (not per capture), the six row fields `_decode_block`
already computes and used to discard, where the alignment origin came from, how
long each attempt took, and which build was running at all.

The last one is why the three 2026-08-01 13:28 failures are unresolvable: they
wrote nothing, and "the skill never ran" and "the skill ran and said nothing"
are indistinguishable after the fact. A BUILD line makes them distinguishable
from now on.

Everything is driven through the real `_capture_position_local` and the real
`prepare()`; only mss, the reader, the scanner and the gate predicates are
faked, so the branch selection under test is the shipping one.
"""

from __future__ import annotations

import asyncio
import inspect
import re
import sys
from pathlib import Path

import pytest


pytest.importorskip("PIL")
pytest.importorskip("mss")

sys.path.insert(0, str(Path(__file__).resolve().parent))

from _stubs import install_runtime_stubs  # noqa: E402


install_runtime_stubs()

import mss as mss_module  # noqa: E402

import main  # noqa: E402
import overlay_reader  # noqa: E402


_REGION = {"left": 0, "top": 0, "width": 10, "height": 5}

# A position the frame gate accepts: a system frame is a frame, so this is the
# `ok` outcome rather than the `no_frame` one a station interior produces.
_POSITION = {"system_frame": True, "x": 1.0, "y": 2.0, "z": 3.0}


class _Printr:
    def print(self, message, color=None, server_only=False):
        pass


class _FakeGrab:
    def __init__(self, region: dict) -> None:
        self.size = (region["width"], region["height"])
        self.bgra = bytes(region["width"] * region["height"] * 4)


class _Screen:
    """One scripted payload per grab, standing in for mss.

    A script shorter than the attempt count repeats its last entry, so a test
    only has to spell out what changes between attempts.
    """

    def __init__(self, script: list[dict | None]) -> None:
        self.script = list(script)
        self.grabs = 0
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

    def payload(self) -> dict | None:
        return self.script[min(self.grabs, len(self.script)) - 1]


class _FakeReader:
    """A reader carrying the alignment provenance the real one records."""

    def __init__(self, screen: _Screen, rows: list | None = None,
                 from_cache: bool = True, refit: bool = True) -> None:
        self._screen = screen
        self._rows = rows
        self.last_from_cache = from_cache
        self.last_refit = refit
        self.last_fit_uses = 7

    def read(self, frame, count):
        if self._rows is not None:
            return 44, 0.0, self._rows
        return 44, 0.0, [{"row": 0, "kind": "zone", "trusted": True,
                          "text": f"Zone: attempt-{self._screen.grabs}"}]


class _FakeScanner:
    def __init__(self, position: dict | None = None,
                 reason: str | None = None) -> None:
        self._position = position
        self.last_reject_reason = reason

    def parse_payload(self, payload: dict) -> dict | None:
        return dict(self._position) if self._position is not None else None


def _skill(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, script, *,
           rows: list | None = None, scanner=None, reader=None,
           usable: tuple[bool, str] = (True, ""), present: bool = True):
    screen = _Screen(script)
    monkeypatch.setattr(mss_module, "mss", screen)
    monkeypatch.setattr(main.time, "sleep", lambda seconds: None)
    monkeypatch.setattr(main.overlay_reader, "block_region", lambda m: dict(_REGION))
    monkeypatch.setattr(main.overlay_reader, "capture_is_usable", lambda f, *a: usable)
    monkeypatch.setattr(main.overlay_reader, "overlay_is_present", lambda f: present)
    monkeypatch.setattr(main.overlay_reader, "overlay_ink_fraction", lambda f: 0.5)
    monkeypatch.setattr(main.overlay_reader, "overlay_row_periodicity", lambda f: 0.5)
    monkeypatch.setattr(
        main.overlay_fields, "payload_from_rows", lambda r: screen.payload()
    )
    monkeypatch.setattr(main.overlay_fields, "ring_state", lambda *a: "")

    skill = main.SC_NavPoint.__new__(main.SC_NavPoint)
    skill.printr = _Printr()
    skill.get_generated_files_dir = lambda: str(tmp_path)
    skill._get_display = lambda: 1
    skill._reader_state = ""
    skill._scanner = scanner if scanner is not None else _FakeScanner(_POSITION)
    fake_reader = reader if reader is not None else _FakeReader(screen, rows)
    skill._local_reader = lambda: fake_reader
    return skill, screen


def _trace(tmp_path: Path) -> str:
    path = tmp_path / "navpoint_poll.log"
    return path.read_text(encoding="utf-8") if path.exists() else ""


def _attempt_lines(tmp_path: Path) -> list[str]:
    return [line for line in _trace(tmp_path).splitlines() if " attempt " in line]


# --------------------------------------------------------------------- #
# One line per attempt, so the retry policy becomes measurable at all
# --------------------------------------------------------------------- #


def test_every_attempt_of_an_exhausted_capture_is_numbered_and_timed(
    tmp_path, monkeypatch
):
    """Current single-pass/held-display policy; supersedes the earlier retry rule."""
    skill, _ = _skill(tmp_path, monkeypatch, [None])

    assert skill._capture_position_local(main.MARK_CAPTURE_ATTEMPTS) is None

    lines = re.findall(r"capture attempt (\d)/1 outcome=(\w+)[^\n]*",
                       _trace(tmp_path))
    assert [n for n, _ in lines] == ["1"]
    assert {kind for _, kind in lines} == {"gate"}
    for line in _attempt_lines(tmp_path):
        assert re.search(r"\bms=\d+$", line), line


def test_a_capture_that_recovered_names_the_attempt_that_worked(
    tmp_path, monkeypatch
):
    """Current single-pass/held-display policy; supersedes the earlier retry rule."""
    skill, _ = _skill(tmp_path, monkeypatch, [None, None, {"local_frame": False}])

    assert skill._capture_position_local(main.MARK_CAPTURE_ATTEMPTS) is None

    trace = _trace(tmp_path)
    assert "capture attempt 1/1 outcome=gate" in trace
    assert "attempt 2/1" not in trace
    # The two that failed are still on the record, with the gate that refused.
    assert "capture attempt 1/1 outcome=gate gate='" in trace


def test_a_single_attempt_refusal_writes_one_attempt_line_and_the_old_one(
    tmp_path, monkeypatch
):
    """The poll loop looks once. Its attempt line must not displace the REFUSED
    line months of logs are grepped for."""
    skill, _ = _skill(tmp_path, monkeypatch, [None])

    assert skill._capture_position_local() is None

    trace = _trace(tmp_path)
    assert len(re.findall(r"capture attempt 1/1 outcome=", trace)) == 1
    assert len(_attempt_lines(tmp_path)) == 1
    assert "capture REFUSED: overlay read but no payload from 1 row(s): " in trace
    # The closing field stays the closing field: `attempts=N]` is one grep.
    assert "attempts=1]" in trace
    # And the duration landed inside the block rather than after it.
    assert re.search(r"ms=\d+ attempts=1\]", trace)


def test_the_attempt_outcome_names_the_specific_producer(tmp_path, monkeypatch):
    """`outcome=` is the vocabulary the structured outcome uses, so one grep
    counts how a session failed rather than that it failed."""
    skill, _ = _skill(
        tmp_path, monkeypatch, [None], present=False,
    )
    assert skill._capture_position_local() is None
    assert "capture attempt 1/1 outcome=absent ms=" in _trace(tmp_path)


def test_a_scanner_rejection_carries_its_reason_on_the_attempt_line(
    tmp_path, monkeypatch
):
    skill, _ = _skill(
        tmp_path,
        monkeypatch,
        [{"local_frame": False}],
        scanner=_FakeScanner(None, reason="unreadable_units"),
    )
    assert skill._capture_position_local() is None
    assert "outcome=reject reason='unreadable_units'" in _trace(tmp_path)


def test_a_refusal_with_no_reason_is_its_own_outcome(tmp_path, monkeypatch):
    """`parse_payload` returns None with the reason still unset when a payload
    carried no usable coordinates. A consumer switching on the reason alone
    cannot tell that from a capture nobody attempted."""
    skill, _ = _skill(
        tmp_path,
        monkeypatch,
        [{"local_frame": True}],
        scanner=_FakeScanner(None, reason=None),
    )
    assert skill._capture_position_local() is None
    assert "outcome=unexplained ms=" in _trace(tmp_path)


def test_a_capture_with_no_frame_is_not_reported_as_a_success(
    tmp_path, monkeypatch
):
    """A station interior reads perfectly and has no frame to put a waypoint
    in. It returns a payload, so it is not a rejection either."""
    skill, _ = _skill(
        tmp_path,
        monkeypatch,
        [{"local_frame": False}],
        scanner=_FakeScanner({"local_frame": False, "body": "", "zone": ""}),
    )
    assert skill._capture_position_local() is not None
    assert "outcome=no_frame ms=" in _trace(tmp_path)


def test_the_successful_capture_line_carries_the_total(tmp_path, monkeypatch):
    """No line in the log carried a duration, which is why the 1.1 s against
    11.1 s question needed an outside source to answer at all. The success line
    needs it as much as the refusal line does: without a working capture's
    timing there is nothing to compare a slow refusal against."""
    skill, _ = _skill(tmp_path, monkeypatch, [{"local_frame": False}])

    assert asyncio.run(skill._capture_position()) is not None

    lines = [
        line for line in _trace(tmp_path).splitlines() if " capture frame=" in line
    ]
    assert len(lines) == 1
    assert re.search(r"\bms=\d+$", lines[0]), lines[0]
    # The pre-existing fields are untouched and still lead the line.
    assert "capture frame=system pos=(1.0, 2.0, 3.0)" in lines[0]


# --------------------------------------------------------------------- #
# The six row fields that were computed and thrown away
# --------------------------------------------------------------------- #


def test_the_row_dump_carries_the_decode_numbers_it_used_to_discard(
    tmp_path, monkeypatch
):
    """`refused=1` is one bad cell and `refused=20` is a different problem, and
    the text alone cannot tell them apart. All six were already computed by
    `_decode_block` and discarded at the point of writing the row to a file."""
    rows = [
        {"row": 2, "y": 44, "colour": "white", "cost": 6.2134, "offset": 0.5,
         "refused": 4, "trusted": False, "kind": "zone",
         "text": "Zone: SolarSystem_729968885548 Pos: -3663644.4772km"},
        {"row": 3, "y": 66, "colour": "cyan", "cost": 1.0, "offset": 0.0,
         "refused": 0, "trusted": True, "kind": "zone", "margin": 30.0,
         "text": "Zone: Root Pos: -3663644.4772km"},
    ]
    rows[0]["margin"] = 11.4
    skill, _ = _skill(tmp_path, monkeypatch, [None], rows=rows)

    assert skill._capture_position_local() is None

    trace = _trace(tmp_path)
    # The pre-existing four keep their order and stay one contiguous string,
    # because that is what the existing greps match.
    assert (
        "row[2] kind='zone' trusted=False "
        "text='Zone: SolarSystem_729968885548 Pos: -3663644.4772km' "
        "refused=4 cost=6.21 margin=11.40 colour='white' offset=0.5 y=44"
    ) in trace
    for dump in [line for line in trace.splitlines() if " row[" in line]:
        for field in ("refused=", "cost=", "margin=", "colour="):
            assert field in dump, dump


def test_the_row_dump_still_only_runs_on_the_final_attempt(tmp_path, monkeypatch):
    """Eight lines of up to 88 characters per attempt, at `poll_interval: 1`,
    would bury everything else in the file."""
    body = inspect.getsource(main.SC_NavPoint._capture_attempt)
    lines = body.splitlines()
    calls = [i for i, line in enumerate(lines) if "self._trace_rows(" in line]
    assert calls, "the row dump vanished"
    for index in calls:
        indent = len(lines[index]) - len(lines[index].lstrip())
        guards = [
            line for line in lines[:index]
            if line.strip() == "if final:"
            and len(line) - len(line.lstrip()) < indent
        ]
        assert guards, "the row dump escaped its `if final:` guard"


# --------------------------------------------------------------------- #
# Alignment provenance
# --------------------------------------------------------------------- #


def test_where_the_origin_came_from_is_recorded_on_every_attempt(
    tmp_path, monkeypatch
):
    """Current single-pass/held-display policy; supersedes the earlier retry rule."""
    skill, _ = _skill(tmp_path, monkeypatch, [None])

    assert skill._capture_position_local(3) is None

    lines = [line for line in _trace(tmp_path).splitlines() if " align " in line]
    assert len(lines) == 1
    assert all(
        "align y0=44 from_cache=True refit=True fit_uses=7" in line
        for line in lines
    )


def test_a_stubbed_reader_without_provenance_cannot_break_a_capture(
    tmp_path, monkeypatch
):
    class _Bare:
        def read(self, frame, count):
            return None, None, [{"row": 0, "kind": "zone", "trusted": True,
                                 "text": "Zone: x"}]

    skill, _ = _skill(tmp_path, monkeypatch, [{"local_frame": False}],
                      reader=_Bare())
    assert skill._capture_position_local() is not None
    assert "align y0=None from_cache=None refit=None fit_uses=None" in _trace(
        tmp_path
    )


def test_the_reader_records_a_self_heal_refit():
    """The provenance has to come from the real `read`, not from the caller's
    guess about what it did."""
    reader = overlay_reader.OverlayReader.__new__(overlay_reader.OverlayReader)
    reader._fit_cache = ((1, 2, 3), 5)
    reader._fit_uses = 3
    decodes = []

    def _decode_block(frame, y0, rows):
        decodes.append(y0)
        # Nothing trusted on the first pass, which is what the stale-origin
        # case looks like and what makes the reader refit.
        return [{"trusted": len(decodes) > 1, "text": "", "row": 0}]

    reader._decode_block = _decode_block
    reader._aligned_origin = lambda frame: (5, len(decodes) == 0)
    reader.read(None, 2)

    assert decodes == [5, 5]
    assert reader.last_from_cache is True
    assert reader.last_refit is True
    assert reader.last_fit_uses == 0


def test_a_fresh_fit_is_not_reported_as_a_refit():
    reader = overlay_reader.OverlayReader.__new__(overlay_reader.OverlayReader)
    reader._fit_uses = 2
    reader._decode_block = lambda frame, y0, rows: [
        {"trusted": True, "text": "", "row": 0}
    ]
    reader._aligned_origin = lambda frame: (5, False)
    reader.read(None, 2)

    assert reader.last_from_cache is False
    assert reader.last_refit is False
    assert reader.last_fit_uses == 2


# --------------------------------------------------------------------- #
# Which build was running
# --------------------------------------------------------------------- #


def test_prepare_records_the_build_it_is_running(tmp_path, monkeypatch):
    """A session with no BUILD line is now a session the skill never activated
    in, which is the one thing the 13:28 gap could not be read for."""
    async def _base_prepare(self):
        return None

    monkeypatch.setattr(main.Skill, "prepare", _base_prepare, raising=False)
    # Blocks `from navpoint_ui.app import ...` with the ImportError prepare()
    # already handles, so no HUD server is started by a test.
    monkeypatch.setitem(sys.modules, "navpoint_ui", None)
    monkeypatch.setitem(sys.modules, "navpoint_ui.app", None)
    monkeypatch.setattr(mss_module, "mss", _Screen([None]))
    monkeypatch.setattr(main.overlay_reader, "block_region", lambda m: dict(_REGION))

    skill = main.SC_NavPoint.__new__(main.SC_NavPoint)
    skill.printr = _Printr()
    skill.get_generated_files_dir = lambda: str(tmp_path)
    skill._get_display = lambda: 1
    skill._get_poll_interval = lambda: 1
    skill._get_overlay_enabled = lambda: False
    skill._start_background_calibration = lambda: None
    skill._ring_overlay = None

    asyncio.run(skill.prepare())

    builds = [line for line in _trace(tmp_path).splitlines() if " BUILD " in line]
    assert len(builds) == 1
    line = builds[0]
    assert f"version={main.SC_NavPoint.VERSION}" in line
    for name in ("main.py=", "frame_reader.py=", "models/specialist_v8/model.onnx="):
        assert name in line
        assert f"{name}missing" not in line
    assert "display=1 poll=1s" in line
    assert "region={'left': 0, 'top': 0, 'width': 10, 'height': 5}" in line


def test_a_missing_file_does_not_cost_the_build_line(tmp_path):
    assert main.SC_NavPoint._file_stamp("no_such_file.py") == "missing"
    assert re.match(r"^\d+b@\d{4}-\d{2}-\d{2}T\d{2}:\d{2}$",
                    main.SC_NavPoint._file_stamp("main.py"))


# --------------------------------------------------------------------- #
# The policy this step measures but does not decide
# --------------------------------------------------------------------- #


def test_marking_uses_the_same_one_attempt_policy_as_polling():
    assert main.MARK_CAPTURE_ATTEMPTS == 1
