"""The scanner-unavailable fast path publishes like every other capture.

`_capture_position` answers before it ever reaches `asyncio.to_thread` when the
scanner is unavailable: it records `KIND_NO_READER` on the shared fields and
returns. That branch used to be the one production capture that did NOT put its
outcome in the caller's sink, so a foreground tool taking that path found an
empty sink and fell back to `self._last_outcome`.

It is unlikely to misreport today. The scanner is built once, so two concurrent
callers would agree that it is unavailable. The reason to close it is the
invariant: every other capture publishes its own outcome, and one exception is
harder to reason about later than no rule at all.

Nothing here is timed. The second writer is INJECTED synchronously in the exact
window, in the manner of `test_capture_diagnostics_atomic.py`, so these tests
cannot flake.
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

from test_main_capture import _install_runtime_stubs  # noqa: E402


_install_runtime_stubs()

import main  # noqa: E402
import overlay_fields as fields  # noqa: E402
from database import NavPointDatabase  # noqa: E402


class _Printr:
    def __init__(self) -> None:
        self.calls: list[tuple] = []

    def print(self, message, color=None, server_only=False):
        self.calls.append((message, color, server_only))


def _skill(tmp_path) -> main.SC_NavPoint:
    """A skill whose scanner is unavailable, and nothing else scripted.

    Built with `__new__` because the fast path under test reads exactly one
    attribute before it answers, and giving it more would hide which one.
    """
    skill = main.SC_NavPoint.__new__(main.SC_NavPoint)
    skill.printr = _Printr()
    skill._db = NavPointDatabase(str(tmp_path))
    skill._scanner = None
    skill._last_outcome = None
    skill._last_ring_state = ""
    return skill


def test_the_scanner_unavailable_path_fills_the_caller_s_sink(tmp_path):
    """The invariant itself: this path publishes, like every other capture."""
    skill = _skill(tmp_path)

    async def _drive():
        with main._capture_sink() as sink:
            result = await skill._capture_position()
            return result, list(sink)

    result, published = asyncio.run(_drive())

    assert result is None
    assert len(published) == 1, published
    assert published[0].kind == fields.KIND_NO_READER
    assert published[0].detail == "scanner=unavailable"
    # D-2, and not this change's to revisit: the reader never ran, so its own
    # verdict says nothing about a frame this capture never looked at.
    assert published[0].ring_state == fields.RING_NO_SIGNAL
    # The SAME object the shared fields hold, not a second one built alongside.
    assert published[0] is skill._last_outcome
    assert skill._last_ring_state == fields.RING_NO_SIGNAL
    assert main._CAPTURE_SINK.get() is None


def test_a_caller_on_this_path_reports_its_own_outcome_not_the_shared_field(
    tmp_path, monkeypatch
):
    """The handoff, which is what publishing buys.

    The shared field is overwritten in the window between the capture returning
    and `mark_location` reading the outcome, which is where an unattended poll
    tick lands. The seam is wrapped rather than replaced: the real
    `_capture_position` runs underneath, so the outcome the tool reports is one
    production code published. This path never reaches `asyncio.to_thread`, so
    the `to_thread` injection the atomic tests use has no window here.
    """
    skill = _skill(tmp_path)
    real_capture = main.SC_NavPoint._capture_position

    async def _capture_then_poll_tick(attempts: int = 1):
        result = await real_capture(skill, attempts)
        # The poll tick, landing a fraction of a second later and looking while
        # the overlay was hidden. A different kind, so the assertion below can
        # tell the two apart.
        skill._last_outcome = fields.CaptureOutcome(kind=fields.KIND_ABSENT)
        return result

    monkeypatch.setattr(skill, "_capture_position", _capture_then_poll_tick)

    result = json.loads(asyncio.run(skill.mark_location()))

    # The shared field really did move on, so this is the race and not a case
    # where both writers happened to agree.
    assert skill._last_outcome.kind == fields.KIND_ABSENT
    assert result["capture_kind"] == fields.KIND_NO_READER
    # KIND_ABSENT is the one kind carrying the console-command hint, which
    # `default_config.yaml` orders relayed word for word.
    assert "hint" not in result
