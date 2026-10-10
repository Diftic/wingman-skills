"""The ring must describe the capture that actually happened, not the read.

`overlay_fields.ring_state` answers a narrower question than the ring asks. It
is the READER's verdict on the frame it decoded, and it is written before the
scanner has looked at the payload at all. So on every path where validation is
what refused the capture, the reader's verdict is still RING_OK and the ring
went on showing a clean face through a capture that produced nothing: a
scanner rejection, a station interior with no coordinate frame in it, and a
reader that failed to load and never looked at a frame in the first place.

`ring_for_outcome` closes that by mapping the FINAL kind, and it is applied at
the point the outcome becomes final rather than where the rows were decoded.
For the five kinds the reader answers correctly its verdict is passed straight
through, because `kind` alone cannot reproduce the rows-based
ACQUIRING-versus-GLARE split and those two ask the player for opposite things.

The result is published on `_last_ring_state`, a different field from
`_reader_state`. The reader's per-attempt verdict is still worth having on its
own terms, and one field cannot answer two questions.
"""

from __future__ import annotations

import asyncio
import sys
import time
from pathlib import Path

import pytest


pytest.importorskip("PIL")
pytest.importorskip("mss")

sys.path.insert(0, str(Path(__file__).resolve().parent))

from test_main_capture import _install_runtime_stubs  # noqa: E402


_install_runtime_stubs()

import mss as mss_module  # noqa: E402

import main  # noqa: E402
import navigation  # noqa: E402
import overlay_fields as fields  # noqa: E402


_REGION = {"left": 0, "top": 0, "width": 10, "height": 5}

# What the rows-to-fields stage produced. Content is irrelevant here: which gate
# refuses which rows is `test_capture_trace.py`'s subject.
_PAYLOAD = {"local_frame": True}

_TARGET = {"x": 1000.0, "y": 0.0, "z": 0.0, "body": "Daymar", "frame": "local"}
_POSITION = {
    "x": 0.0, "y": 0.0, "z": 0.0, "body": "Daymar",
    "heading": 0.0, "system_frame": False,
    "active_frame": "planet", "frame_id": "daymar", "camdir": [0,0,0],
    "planet_rotation": {"frame_id": "daymar", "angle": 0., "valid": True},
}

# The render budget the ring strings are sized against, from
# `test_ring_state.py::test_states_are_distinct_and_short_enough_for_the_ring`.
_RING_BUDGET = 12


class _Printr:
    def print(self, message, color=None, server_only=False):
        pass


class _FakeGrab:
    def __init__(self, region: dict) -> None:
        self.size = (region["width"], region["height"])
        self.bgra = bytes(region["width"] * region["height"] * 4)


class _Screen:
    def __init__(self) -> None:
        self.grabs = 0
        self.monitors = [dict(_REGION), dict(_REGION)]

    def __call__(self) -> "_Screen":
        return self

    def __enter__(self) -> "_Screen":
        return self

    def __exit__(self, *exc_info) -> bool:
        return False

    def grab(self, region: dict) -> _FakeGrab:
        self.grabs += 1
        return _FakeGrab(region)


class _FakeReader:
    def read(self, frame, count):
        return None, None, [
            {"row": 0, "kind": "zone", "trusted": True, "text": "Zone: OOC_x"}
        ]


class _FakeScanner:
    """Returns whatever position it was told to, and a reject reason with it."""

    def __init__(self, position=None, reject_reason=None) -> None:
        self.position = position
        self.last_reject_reason = reject_reason

    def parse_payload(self, payload: dict):
        return self.position


class _RecordingOverlay:
    """A ring that records every state pushed to it."""

    def __init__(self) -> None:
        self.states: list[tuple] = []
        self.cleared = 0

    def set_state(self, active, deflection, message, **kwargs) -> None:
        self.states.append((active, deflection, message))

    def clear(self) -> None:
        self.cleared += 1


def _skill(tmp_path, monkeypatch, scanner, reader_state="") -> main.SC_NavPoint:
    """A skill driven through the real `_capture_position_local`.

    Only mss, the reader and the rows-to-fields stage are faked, so the branch
    that decides the ring state is the shipping one.
    """
    screen = _Screen()
    monkeypatch.setattr(mss_module, "mss", screen)
    monkeypatch.setattr(main.time, "sleep", lambda s: None)
    monkeypatch.setattr(main.overlay_reader, "block_region", lambda m: dict(_REGION))
    monkeypatch.setattr(
        main.overlay_reader, "capture_is_usable", lambda f, *a: (True, "")
    )
    monkeypatch.setattr(main.overlay_reader, "overlay_is_present", lambda f: True)
    monkeypatch.setattr(main.overlay_reader, "overlay_ink_fraction", lambda f: 0.5)
    monkeypatch.setattr(main.overlay_reader, "overlay_row_periodicity", lambda f: 0.5)
    monkeypatch.setattr(
        main.overlay_fields, "payload_from_rows", lambda rows: dict(_PAYLOAD)
    )

    skill = main.SC_NavPoint.__new__(main.SC_NavPoint)
    skill.printr = _Printr()
    skill.get_generated_files_dir = lambda: str(tmp_path)
    skill._get_display = lambda: 1
    skill._reader_state = reader_state
    skill._last_ring_state = ""
    skill._scanner = scanner
    skill._local_reader = lambda: _FakeReader()
    return skill


# --------------------------------------------------------------------- #
# The three paths that left the ring lying
# --------------------------------------------------------------------- #


def test_a_scanner_rejection_does_not_leave_the_ring_at_ok(tmp_path, monkeypatch):
    """The reported harm. The reader read the frame perfectly and the SCANNER
    threw the position away, so the reader's verdict is RING_OK and the ring
    said nothing at all about a capture that produced nothing."""
    skill = _skill(
        tmp_path, monkeypatch, _FakeScanner(None, reject_reason="coord_mismatch")
    )

    assert skill._capture_position_local() is None

    assert skill._last_outcome.kind == fields.KIND_REJECT
    assert skill._last_ring_state, "the ring was left with nothing to say"
    assert skill._last_outcome.ring_state
    # The reader's own verdict is untouched and still says it read cleanly.
    assert skill._reader_state == fields.RING_OK


def test_a_no_frame_capture_leaves_a_terminal_ring_state(tmp_path, monkeypatch):
    """A station interior. The scanner ACCEPTED the payload, so nothing on the
    reader's side registers a problem, and waiting produces no frame however
    long the player waits: ACQUIRING would promise a fix that cannot arrive."""
    skill = _skill(tmp_path, monkeypatch, _FakeScanner({"x": 1.0, "y": 2.0, "z": 3.0}))

    skill._capture_position_local()

    assert skill._last_outcome.kind == fields.KIND_NO_FRAME
    assert skill._last_ring_state == fields.RING_NO_FRAME
    assert skill._last_ring_state != fields.RING_OK
    assert skill._last_ring_state != fields.RING_ACQUIRING


def test_a_missing_reader_leaves_an_unavailable_ring_state(tmp_path, monkeypatch):
    """The reader never looked at a frame, so the reader's verdict describes the
    PREVIOUS capture. Pre-set clean here, which is the case that used to leave
    the ring silent while nothing whatever was being read."""
    skill = _skill(tmp_path, monkeypatch, _FakeScanner(None), reader_state="")
    skill._local_reader = lambda: None

    assert skill._capture_position_local() is None

    assert skill._last_outcome.kind == fields.KIND_NO_READER
    assert skill._last_outcome.ring_state == fields.RING_NO_SIGNAL
    assert skill._last_ring_state == fields.RING_NO_SIGNAL


def test_the_async_scanner_unavailable_branch_says_so_too(tmp_path, monkeypatch):
    """The other no-reader branch, on the outer seam. Its outcome used to take
    the dataclass default, which is RING_OK."""
    skill = _skill(tmp_path, monkeypatch, _FakeScanner(None))
    skill._scanner = None

    assert asyncio.run(skill._capture_position()) is None

    assert skill._last_outcome.ring_state == fields.RING_NO_SIGNAL
    assert skill._last_ring_state == fields.RING_NO_SIGNAL


# --------------------------------------------------------------------- #
# End to end, through the overlay
# --------------------------------------------------------------------- #


def test_the_poll_failure_branch_puts_a_message_on_the_ring(tmp_path, monkeypatch):
    """THE REPORTED HARM, end to end. The poll loop's refusal branch is the one
    path that reaches `_sync_ring` without a usable position, and it was pushing
    the READER's verdict to the overlay rather than the capture's.

    Driven with a no-frame capture on purpose, because that is a case where the
    two fields genuinely disagree: the reader read the frame cleanly, so its
    verdict is RING_OK, while the capture as a whole ended INDOORS. Asserting
    only that the message is non-empty would prove nothing here, since
    `ring_status` answers a silent reader with its own ACQUIRING fallback
    whenever there is no fix to draw. The message has to be the one the CAPTURE
    decided.
    """
    # A station interior: the scanner accepts the payload and it carries no
    # coordinates, so the poll loop's `not all(k in pos_data ...)` branch fires.
    skill = _skill(tmp_path, monkeypatch, _FakeScanner({"zone": ""}))
    overlay = _RecordingOverlay()
    skill._ring_overlay = overlay
    # A target is required: with nothing being navigated to there is nothing the
    # player needs telling, and `ring_status` says so by returning "".
    skill._db = type("_D", (), {"navpoint_to_dict": staticmethod(lambda t: _TARGET)})()
    skill._active_target = object()
    skill._last_position = None
    skill._get_space_direction_test = lambda: False

    pos_data = skill._capture_position_local()
    assert not all(k in (pos_data or {}) for k in ("x", "y", "z"))
    assert skill._last_outcome.kind == fields.KIND_NO_FRAME
    # The precondition that makes this test discriminating.
    assert skill._reader_state == fields.RING_OK

    skill._sync_ring()

    assert overlay.states, "the ring was never told anything"
    _, _, message = overlay.states[-1]
    assert message, "the ring was pushed an empty message after a refusal"
    assert message == fields.RING_NO_FRAME, (
        "the ring was told what the READER made of the frame, not how the "
        "capture ended"
    )


def test_a_clean_capture_still_leaves_the_ring_silent(tmp_path, monkeypatch):
    """The over-reporting guard. A capture that worked has nothing to say, and
    the cheapest way to get this change wrong is to put a word on the ring for
    every capture."""
    skill = _skill(
        tmp_path, monkeypatch,
        _FakeScanner(dict(_POSITION, x=1.0, y=2.0, z=3.0)),
    )
    overlay = _RecordingOverlay()
    skill._ring_overlay = overlay
    skill._db = None
    skill._active_target = object()
    skill._get_space_direction_test = lambda: False

    position = skill._capture_position_local()

    assert skill._last_outcome.kind == fields.KIND_OK
    assert skill._last_ring_state == ""

    position["captured_at"] = __import__("time").time()
    skill._last_position = position
    skill._db = type("_D", (), {"navpoint_to_dict": staticmethod(lambda t: _TARGET)})()
    skill._sync_ring()

    _, deflection, message = overlay.states[-1]
    assert message == ""
    assert deflection is not None


# --------------------------------------------------------------------- #
# The mapping itself
# --------------------------------------------------------------------- #


def test_every_kind_maps_to_something_the_ring_can_show():
    """Fail visible, never fail silent. A kind added later with no mapping would
    otherwise leave the ring clean through a capture that produced nothing, and
    a string over the render budget would be drawn off the edge of the ring.

    Enumerates the module rather than a hand-written list, so a new KIND_* is
    caught by adding it rather than by remembering to add it here too."""
    kinds = [
        getattr(fields, name) for name in dir(fields) if name.startswith("KIND_")
    ]
    assert len(kinds) >= 10, kinds

    for kind in kinds:
        # RING_OK is passed for `reader_state` deliberately: it is what the
        # reader reports on every path where validation is what refused, so it
        # is the value that made the ring lie.
        state = fields.ring_for_outcome(kind, fields.RING_OK)
        if kind == fields.KIND_OK:
            assert state == fields.RING_OK
            continue
        assert state, kind
        assert 0 < len(state) <= _RING_BUDGET, (kind, state)

    # An id nobody has written yet must still reach the ring.
    assert fields.ring_for_outcome("a_kind_from_the_future", fields.RING_OK)

    # R3b, asserted here because this is the exhaustive walk and `ring_for_outcome`
    # is the newest producer of these strings. The ring renders through PIL with
    # a bundled font, so a missing glyph draws as a literal box on the player's
    # HUD. `ACQUIRING...` is three ASCII full stops and must never become U+2026;
    # both spellings have appeared in working notes.
    assert fields.RING_ACQUIRING.encode("utf-8") == b"ACQUIRING..."
    for name in dir(fields):
        if name.startswith("RING_"):
            value = getattr(fields, name)
            assert value.encode("utf-8").decode("ascii") == value, name


def test_the_reader_verdict_survives_for_the_kinds_it_answers():
    """`kind` alone cannot reproduce the rows-based split. `absent` and
    `unusable` ask the player for opposite things, and flattening the mapping
    would tell someone in bright sunlight to type `r_displayinfo 2` for an
    overlay that is plainly on screen."""
    assert (
        fields.ring_for_outcome(fields.KIND_ABSENT, fields.RING_NO_SIGNAL)
        == fields.RING_NO_SIGNAL
    )
    assert (
        fields.ring_for_outcome(fields.KIND_UNUSABLE, fields.RING_GLARE)
        == fields.RING_GLARE
    )
    assert (
        fields.ring_for_outcome(fields.KIND_GATE, fields.RING_ACQUIRING)
        == fields.RING_ACQUIRING
    )


# --------------------------------------------------------------------- #
# Suppression: on a refusal the ring shows its no-fix face, not a bearing
# --------------------------------------------------------------------- #
#
# User decision D-1, 2026-08-02, reaffirmed after being told two further costs:
# that suppression keys on ANY ring message, so the bubble also vanishes in
# glare, which over sunlit terrain is the common case; and that intermittent
# refusals therefore toggle the bubble at up to about 0.5 Hz, since
# `poll_interval` is bounded 1 to 10 s and the hazardous photosensitive band
# starts around 3 Hz. Both accepted. The message is damped by `MessageFader`;
# the bubble is not, and extending the fader to it is deliberately a separate
# change rather than part of this one.


def test_a_refusal_draws_no_bubble():
    """Current single-pass/held-display policy; supersedes the earlier retry rule."""
    deflection, message = navigation.ring_status(
        _POSITION, _TARGET, 2.0, fields.RING_GLARE
    )
    assert deflection is not None
    assert message == "HELD 2s"


def test_the_poll_failure_branch_draws_no_bubble(tmp_path, monkeypatch):
    """Current single-pass/held-display policy; supersedes the earlier retry rule."""
    skill = _skill(
        tmp_path, monkeypatch, _FakeScanner(None, reject_reason="coord_mismatch")
    )
    overlay = _RecordingOverlay()
    skill._ring_overlay = overlay
    skill._active_target = object()
    skill._last_position = dict(_POSITION, captured_at=time.time())
    skill._db = type("_D", (), {"navpoint_to_dict": staticmethod(lambda t: _TARGET)})()
    skill._get_space_direction_test = lambda: False

    assert skill._capture_position_local() is None
    # Precondition: the fix on the books is fresh enough to draw, so a blank
    # bubble below is suppression rather than staleness.
    assert navigation.ring_deflection(
        skill._last_position, _TARGET, 1.0
    ) is not None

    skill._sync_ring()

    _, deflection, message = overlay.states[-1]
    assert deflection is not None
    assert message.startswith("HELD ")


def test_a_clean_read_still_draws_its_bubble():
    """The one that matters most here: the cheapest way to get suppression wrong
    is to blank the bubble unconditionally, which leaves the ring drawing
    nothing, ever, and no test of a refusal would notice."""
    deflection, message = navigation.ring_status(_POSITION, _TARGET, 1.0, "")
    assert deflection is not None
    assert message == ""
