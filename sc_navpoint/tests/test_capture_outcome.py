"""A capture must be able to say HOW it failed, not just that it did.

There are more than a dozen distinct failure producers on the capture path and,
until `CaptureOutcome` existed, one channel to report them: a `None` return.
`NavPointScanner.last_reject_reason` is not a second channel, and these tests
pin both ways it lies. It stays None when `parse_payload` refuses a payload
carrying no coordinates, so a consumer switching on it cannot tell that from a
capture nobody attempted. And it can be SET on a branch that still returns a
payload, so reading it without first checking for a payload reports a safety
refusal that never happened.

The concurrency test is here for a different reason: the poll loop runs on its
own thread and a spoken `mark_location` runs on the caller's, so two captures
can already arrive together, and underneath them sits one reader with a mutable
alignment cache.
"""

from __future__ import annotations

import dataclasses
import inspect
import sys
import threading
import time
from pathlib import Path

import pytest


pytest.importorskip("PIL")
pytest.importorskip("mss")

sys.path.insert(0, str(Path(__file__).resolve().parent))

from _stubs import install_runtime_stubs  # noqa: E402


install_runtime_stubs()

import mss as mss_module  # noqa: E402

import main  # noqa: E402
import overlay_fields as fields  # noqa: E402
from scanner import NavPointScanner  # noqa: E402


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
        return 44, 0.0, self._rows


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
    """A skill wired so exactly one capture producer fires."""
    monkeypatch.setattr(mss_module, "mss", lambda: _FakeSct(grab_exc))
    monkeypatch.setattr(main.overlay_reader, "block_region", lambda m: dict(_REGION))
    monkeypatch.setattr(main.overlay_reader, "capture_is_usable", lambda f, *a: usable)
    monkeypatch.setattr(main.overlay_reader, "overlay_is_present", lambda f: present)
    monkeypatch.setattr(main.overlay_reader, "overlay_ink_fraction", lambda f: 0.5)
    monkeypatch.setattr(main.overlay_reader, "overlay_row_periodicity", lambda f: 0.5)
    monkeypatch.setattr(main.overlay_fields, "payload_from_rows", lambda rows: payload)

    skill = main.SC_NavPoint.__new__(main.SC_NavPoint)
    skill.printr = _Printr()
    skill.get_generated_files_dir = lambda: str(tmp_path)
    skill._get_display = lambda: 1
    skill._reader_state = ""
    skill._scanner = scanner if scanner is not None else NavPointScanner()
    skill._local_reader = lambda: reader
    return skill


_TRUSTED_ROW = {"row": 0, "kind": "zone", "trusted": True, "text": "Zone: x"}


# --------------------------------------------------------------------- #
# The object and its vocabulary
# --------------------------------------------------------------------- #


def test_the_outcome_carries_exactly_the_agreed_fields():
    assert dataclasses.is_dataclass(fields.CaptureOutcome)
    assert fields.CaptureOutcome.__dataclass_params__.frozen
    names = [f.name for f in dataclasses.fields(fields.CaptureOutcome)]
    assert names == [
        "kind",
        "position",
        "overlay_present",
        "frame_usable",
        "ring_state",
        "gate",
        "reject_reason",
        "attempts",
        "metrics",
        "detail",
    ]


def test_there_is_no_source_field():
    """It would be a constant with one reader, and a constant field invites a
    future reader to believe there is a second producer."""
    names = {f.name for f in dataclasses.fields(fields.CaptureOutcome)}
    assert "source" not in names


def test_an_outcome_cannot_be_edited_after_the_fact():
    outcome = fields.CaptureOutcome(kind=fields.KIND_OK)
    with pytest.raises(dataclasses.FrozenInstanceError):
        outcome.kind = fields.KIND_GATE


def test_the_kind_vocabulary_is_an_interface():
    """Grepped out of month-old logs, so the VALUES are pinned as literals and
    not through the constants that carry them."""
    assert fields.KIND_OK == "ok"
    assert fields.KIND_NO_READER == "no_reader"
    assert fields.KIND_NO_GRAB == "no_grab"
    assert fields.KIND_UNUSABLE == "unusable"
    assert fields.KIND_ABSENT == "absent"
    assert fields.KIND_DECODE_ERROR == "decode_error"
    assert fields.KIND_GATE == "gate"
    assert fields.KIND_REJECT == "reject"
    assert fields.KIND_UNEXPLAINED == "unexplained"
    assert fields.KIND_NO_FRAME == "no_frame"


def test_no_kind_names_a_model():
    """Local OCR is the only reader. A kind naming Vision would be a promise of
    a fallback that does not exist."""
    kinds = [name for name in dir(fields) if name.startswith("KIND_")]
    assert len(kinds) == 10
    assert not any("VISION" in name.upper() for name in kinds)


# --------------------------------------------------------------------- #
# Every producer, through the real capture path
# --------------------------------------------------------------------- #


def test_a_missing_reader_is_its_own_kind(tmp_path, monkeypatch):
    skill = _skill(tmp_path, monkeypatch, reader=None)
    assert skill._capture_position_local() is None
    assert skill._last_outcome.kind == fields.KIND_NO_READER
    # Nothing was asked of a frame, so nothing is claimed about one.
    assert skill._last_outcome.overlay_present is None
    assert skill._last_outcome.frame_usable is None


def test_a_failed_grab_is_its_own_kind(tmp_path, monkeypatch):
    skill = _skill(
        tmp_path, monkeypatch,
        reader=_FakeReader([]), grab_exc=OSError("no such display"),
    )
    assert skill._capture_position_local() is None
    outcome = skill._last_outcome
    assert outcome.kind == fields.KIND_NO_GRAB
    assert "OSError: no such display" in outcome.detail
    assert outcome.overlay_present is None and outcome.frame_usable is None


def test_an_unusable_frame_is_its_own_kind(tmp_path, monkeypatch):
    skill = _skill(
        tmp_path, monkeypatch,
        reader=_FakeReader([]), usable=(False, "rows saturated"),
    )
    assert skill._capture_position_local() is None
    outcome = skill._last_outcome
    assert outcome.kind == fields.KIND_UNUSABLE
    assert outcome.frame_usable is False
    assert outcome.detail == "rows saturated"


def test_an_absent_overlay_is_its_own_kind(tmp_path, monkeypatch):
    skill = _skill(tmp_path, monkeypatch, reader=_FakeReader([]), present=False)
    assert skill._capture_position_local() is None
    outcome = skill._last_outcome
    assert outcome.kind == fields.KIND_ABSENT
    assert outcome.overlay_present is False
    assert outcome.frame_usable is True


def test_a_decode_that_raised_is_its_own_kind(tmp_path, monkeypatch):
    skill = _skill(
        tmp_path, monkeypatch,
        reader=_FakeReader([], exc=ValueError("glyph bank corrupt")),
    )
    assert skill._capture_position_local() is None
    outcome = skill._last_outcome
    assert outcome.kind == fields.KIND_DECODE_ERROR
    assert outcome.detail == "ValueError: glyph bank corrupt"


def test_a_field_gate_names_itself_on_the_outcome(tmp_path, monkeypatch):
    """The five gates ask genuinely different things of the player, so the id
    has to survive as far as whoever writes the message."""
    monkeypatch.setattr(
        main.overlay_fields, "refusal_reason",
        lambda rows: "body_scale: a container above the SolarSystem line reads "
                     "330.7421km from its origin",
    )
    skill = _skill(tmp_path, monkeypatch, reader=_FakeReader([_TRUSTED_ROW]))
    assert skill._capture_position_local() is None
    outcome = skill._last_outcome
    assert outcome.kind == fields.KIND_GATE
    assert outcome.gate.startswith("body_scale:")
    assert outcome.reject_reason == ""


def test_a_scanner_refusal_carries_its_reason(tmp_path, monkeypatch):
    class _Rejecting:
        last_reject_reason = "frame_mismatch"

        def parse_payload(self, payload):
            return None

    skill = _skill(
        tmp_path, monkeypatch, reader=_FakeReader([_TRUSTED_ROW]),
        scanner=_Rejecting(), payload={"local_frame": False},
    )
    assert skill._capture_position_local() is None
    outcome = skill._last_outcome
    assert outcome.kind == fields.KIND_REJECT
    assert outcome.reject_reason == "frame_mismatch"
    assert outcome.gate == ""


# --------------------------------------------------------------------- #
# The two producers that were on nobody's list
# --------------------------------------------------------------------- #


def test_a_refusal_with_no_reason_is_unexplained_not_a_rejection(
    tmp_path, monkeypatch
):
    """Driven through the REAL scanner, because the claim is about what
    `parse_payload` leaves behind on this branch."""
    payload = {"local_frame": True, "body_token": "Stanton_1_Daymar", "zone": ""}
    scanner = NavPointScanner()

    assert scanner.parse_payload(dict(payload)) is None
    assert scanner.last_reject_reason is None

    skill = _skill(
        tmp_path, monkeypatch, reader=_FakeReader([_TRUSTED_ROW]),
        scanner=scanner, payload=payload,
    )
    assert skill._capture_position_local() is None
    assert skill._last_outcome.kind == fields.KIND_UNEXPLAINED
    assert skill._last_outcome.reject_reason == ""


def test_a_station_interior_reads_cleanly_and_has_no_frame(tmp_path, monkeypatch):
    """Current single-pass/held-display policy; supersedes the earlier retry rule."""
    scanner = NavPointScanner()
    parsed = scanner.parse_payload({"local_frame": False})
    assert parsed

    skill = _skill(
        tmp_path, monkeypatch, reader=_FakeReader([_TRUSTED_ROW]),
        scanner=scanner, payload={"local_frame": False},
    )
    position = skill._capture_position_local()
    outcome = skill._last_outcome
    assert outcome.kind == fields.KIND_NO_FRAME
    assert outcome.position == position
    assert position["captured_at"] > 0
    assert {k:v for k,v in position.items() if k != "captured_at"} == parsed


def test_a_set_reject_reason_beside_a_payload_is_not_a_rejection(
    tmp_path, monkeypatch
):
    """THE REGRESSION GUARD. `parse_payload` sets `unreadable_units` and STILL
    returns the dict on this branch, so any code that reads the reason without
    first checking for a payload reports a safety refusal that never happened."""
    payload = {"local_frame": False, "system_pos_raw": ["1.0km", "2.0", "3.0km"]}
    scanner = NavPointScanner()
    parsed = scanner.parse_payload(dict(payload))
    assert parsed
    assert scanner.last_reject_reason == "unreadable_units"

    skill = _skill(
        tmp_path, monkeypatch, reader=_FakeReader([_TRUSTED_ROW]),
        scanner=scanner, payload=payload,
    )
    assert skill._capture_position_local() is not None
    assert skill._last_outcome.kind == fields.KIND_NO_FRAME
    assert skill._last_outcome.kind != fields.KIND_REJECT


def test_a_failing_measurement_cannot_break_a_capture(tmp_path, monkeypatch):
    """Current single-pass/held-display policy; supersedes the earlier retry rule."""

    class _HostileRow(dict):
        def get(self, *args, **kwargs):
            raise RuntimeError("this row refuses to be measured")

    scanner = NavPointScanner()
    skill = _skill(
        tmp_path, monkeypatch, reader=_FakeReader([_HostileRow()]),
        scanner=scanner, payload={"local_frame": False},
    )

    position = skill._capture_position_local()

    assert {k:v for k,v in position.items() if k != "captured_at"} == scanner.parse_payload({"local_frame": False})
    assert skill._last_outcome.kind == fields.KIND_NO_FRAME
    # As many measurements as could be taken, and no exception either way.
    assert skill._last_outcome.metrics["rows"] == 1
    assert "trusted" not in skill._last_outcome.metrics


# --------------------------------------------------------------------- #
# What the outcome must NOT have changed
# --------------------------------------------------------------------- #


def test_the_scanner_signature_is_untouched():
    """One validation path, and the outcome object travels alongside it rather
    than through it."""
    assert (
        str(inspect.signature(NavPointScanner.parse_payload))
        == "(self, data: dict) -> dict | None"
    )


def test_the_capture_seams_still_return_position_or_none(tmp_path, monkeypatch):
    """Twenty existing tests call these and assert `is None` or `== position`.
    The structured outcome travels alongside, never instead."""
    skill = _skill(tmp_path, monkeypatch, reader=None)
    assert skill._capture_position_local() is None
    assert not inspect.iscoroutinefunction(
        main.SC_NavPoint._capture_position_local
    )


def test_the_capture_call_sites_are_the_same_five(tmp_path):
    """The seam did not sprout a new caller while it was being changed."""
    source = (Path(main.__file__).with_name("main.py")).read_text(encoding="utf-8")
    sites = [line for line in source.splitlines() if "_capture_position(" in line]
    assert len(sites) == 5
    assert sum(1 for line in sites if line.strip().startswith("async def")) == 1
    assert sum(1 for line in sites if "await self._capture_position(" in line) == 4


# --------------------------------------------------------------------- #
# The capture lock
# --------------------------------------------------------------------- #


def test_the_lock_is_taken_in_exactly_one_function_and_holds_no_await():
    """A lock held across an await would deadlock the moment the capture moves
    off the event loop, which is the next step after this one."""
    source = inspect.getsource(main.SC_NavPoint)
    assert source.count("_capture_lock") == 2  # the assignment and the acquisition
    body = inspect.getsource(main.SC_NavPoint._capture_position_local)
    assert "_capture_lock" in body
    assert "await" not in body


def test_two_threads_never_capture_at_once(tmp_path, monkeypatch):
    """The poll thread and a spoken command can already arrive together, and
    one shared reader with a mutable alignment cache sits underneath."""
    inside: list[int] = []
    overlaps: list[int] = []

    class _SlowReader:
        def read(self, frame, count):
            inside.append(1)
            if len(inside) > 1:
                overlaps.append(1)
            time.sleep(0.05)
            inside.pop()
            return 44, 0.0, [_TRUSTED_ROW]

    skill = _skill(
        tmp_path, monkeypatch, reader=_SlowReader(), payload={"local_frame": False},
    )
    skill._capture_lock = threading.Lock()

    threads = [
        threading.Thread(target=skill._capture_position_local) for _ in range(2)
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=5)

    assert not any(thread.is_alive() for thread in threads)
    assert overlaps == []


def test_a_second_thread_cannot_restamp_a_running_capture(tmp_path, monkeypatch):
    """The capture clock is started INSIDE the lock. Started outside, a second
    thread arriving mid-capture restamps it, and the first capture's REFUSED
    line and success line then report elapsed time since the SECOND capture's
    start. Under contention that is the opposite of what the field wants to
    know: how long the player waited for the answer they got."""
    entered = threading.Event()
    release = threading.Event()
    seen: list[float] = []

    class _WaitingReader:
        def read(self, frame, count):
            seen.append(skill._capture_started_at)
            entered.set()
            release.wait(timeout=5)
            return 44, 0.0, [_TRUSTED_ROW]

    skill = _skill(
        tmp_path, monkeypatch, reader=_WaitingReader(),
        payload={"local_frame": False},
    )
    skill._capture_lock = threading.Lock()

    first = threading.Thread(target=skill._capture_position_local)
    first.start()
    assert entered.wait(timeout=5)

    second = threading.Thread(target=skill._capture_position_local)
    second.start()
    # Long enough that a second thread which stamped the clock BEFORE taking
    # the lock would already have done so.
    time.sleep(0.05)
    mid_capture = skill._capture_started_at
    release.set()
    first.join(timeout=5)
    second.join(timeout=5)

    assert not first.is_alive() and not second.is_alive()
    assert mid_capture == seen[0], (
        "a waiting thread restamped the running capture's clock"
    )


def test_a_skill_built_without_init_still_serialises(tmp_path, monkeypatch):
    """The tests build the skill with `__new__`, and so does anything driving
    the capture path directly. A missing lock must not mean no lock."""
    skill = _skill(
        tmp_path, monkeypatch, reader=_FakeReader([_TRUSTED_ROW]),
        payload={"local_frame": False},
    )
    assert not hasattr(skill, "_capture_lock")
    assert skill._capture_position_local() is not None
    assert not main._FALLBACK_CAPTURE_LOCK.locked()
