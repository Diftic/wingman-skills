"""A refusal that repeats is logged once, not once per capture.

The idle calibration captures every second for the whole session. On
2026-10-23 that wrote 11,388 identical "screen grab failed: Star Citizen is not
foreground" warnings into wingman-core.log, and the poll log got a REFUSED line,
an attempt line and up to eight row lines per second while the overlay was off.
The first refusal of a kind is still traced in full; repeats are counted and
summarised in one line when the cause changes or a capture succeeds.
"""

from __future__ import annotations

import logging
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
from scanner import NavPointScanner  # noqa: E402


_REGION = {"left": 0, "top": 0, "width": 10, "height": 5}
_ROW = {"row": 0, "kind": "zone", "trusted": True, "text": "Zone: x"}
_NOT_FOREGROUND = RuntimeError("Star Citizen is not foreground")


class _Printr:
    def print(self, message, color=None, server_only=False):
        pass


class _Grab:
    def __init__(self, region: dict) -> None:
        self.size = (region["width"], region["height"])
        self.bgra = bytes(region["width"] * region["height"] * 4)


class _Screen:
    """Raises whatever `state["grab"]` holds, or returns a blank frame."""

    def __init__(self, state: dict) -> None:
        self._state = state
        self.monitors = [dict(_REGION), dict(_REGION)]

    def __enter__(self) -> "_Screen":
        return self

    def __exit__(self, *exc_info) -> bool:
        return False

    def grab(self, region: dict) -> _Grab:
        if self._state["grab"] is not None:
            raise self._state["grab"]
        return _Grab(region)


class _Reader:
    def read(self, frame, count):
        return 44, 0.0, [dict(_ROW)]


def _skill(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, state: dict):
    monkeypatch.setattr(mss_module, "mss", lambda: _Screen(state))
    monkeypatch.setattr(main.overlay_reader, "block_region", lambda m: dict(_REGION))
    monkeypatch.setattr(main.overlay_reader, "capture_is_usable", lambda f, *a: (True, ""))
    monkeypatch.setattr(main.overlay_reader, "overlay_is_present", lambda f: state["present"])
    monkeypatch.setattr(main.overlay_reader, "overlay_ink_fraction", lambda f: 0.5)
    monkeypatch.setattr(main.overlay_reader, "overlay_row_periodicity", lambda f: 0.5)
    # A station interior: reads cleanly and yields a position, i.e. a good capture.
    monkeypatch.setattr(main.overlay_fields, "payload_from_rows",
                        lambda rows: {"local_frame": False} if state["present"] else None)
    monkeypatch.setattr(main, "SAVE_REFUSED_FRAMES", True)

    skill = main.SC_NavPoint.__new__(main.SC_NavPoint)
    skill.printr = _Printr()
    skill.get_generated_files_dir = lambda: str(tmp_path)
    skill._get_display = lambda: 1
    skill._reader_state = ""
    skill._scanner = NavPointScanner()
    skill._local_reader = lambda: _Reader()
    return skill


def _log(tmp_path: Path) -> str:
    path = tmp_path / "navpoint_poll.log"
    return path.read_text(encoding="utf-8") if path.exists() else ""


def _warnings(caplog) -> list[str]:
    return [r.getMessage() for r in caplog.records
            if r.levelno >= logging.WARNING and "NavPoint" in r.getMessage()]


def test_a_repeated_grab_failure_warns_the_core_log_once(tmp_path, monkeypatch, caplog):
    skill = _skill(tmp_path, monkeypatch, dict(grab=_NOT_FOREGROUND, present=True))
    with caplog.at_level(logging.WARNING):
        for _ in range(5):
            assert skill._capture_position_local() is None
    assert _warnings(caplog) == ["NavPoint screen grab failed: Star Citizen is not foreground"]


def test_a_repeated_refusal_is_traced_once(tmp_path, monkeypatch):
    skill = _skill(tmp_path, monkeypatch, dict(grab=_NOT_FOREGROUND, present=True))
    for _ in range(5):
        skill._capture_position_local()
    log = _log(tmp_path)
    assert log.count("REFUSED: screen grab failed") == 1
    assert log.count("outcome=no_grab") == 1


def test_an_absent_overlay_dumps_its_rows_and_frame_once(tmp_path, monkeypatch):
    skill = _skill(tmp_path, monkeypatch, dict(grab=None, present=False))
    for _ in range(5):
        skill._capture_position_local()
    log = _log(tmp_path)
    assert log.count("REFUSED: overlay not on screen") == 1
    assert log.count(" row[0] ") == 1
    assert len(list((tmp_path / "refused").glob("*.png"))) == 1


def test_a_change_of_cause_is_traced_and_counts_the_skipped_repeats(tmp_path, monkeypatch):
    state = dict(grab=_NOT_FOREGROUND, present=False)
    skill = _skill(tmp_path, monkeypatch, state)
    for _ in range(3):
        skill._capture_position_local()
    state["grab"] = None
    skill._capture_position_local()
    log = _log(tmp_path)
    assert "previous refusal repeated 2 more time(s)" in log
    assert log.index("repeated 2 more time(s)") < log.index("REFUSED: overlay not on screen")
    assert log.count("REFUSED: overlay not on screen") == 1


def test_a_good_capture_resets_so_the_next_failure_is_logged_again(tmp_path, monkeypatch, caplog):
    state = dict(grab=_NOT_FOREGROUND, present=True)
    skill = _skill(tmp_path, monkeypatch, state)
    with caplog.at_level(logging.WARNING):
        skill._capture_position_local()
        skill._capture_position_local()
        state["grab"] = None
        assert skill._capture_position_local() is not None
        state["grab"] = _NOT_FOREGROUND
        skill._capture_position_local()
    assert len(_warnings(caplog)) == 2
    log = _log(tmp_path)
    assert "previous refusal repeated 1 more time(s)" in log
    assert log.count("REFUSED: screen grab failed") == 2


def test_a_different_error_is_not_swallowed_as_a_repeat(tmp_path, monkeypatch, caplog):
    state = dict(grab=_NOT_FOREGROUND, present=True)
    skill = _skill(tmp_path, monkeypatch, state)
    with caplog.at_level(logging.WARNING):
        skill._capture_position_local()
        state["grab"] = OSError("no such display")
        skill._capture_position_local()
    assert len(_warnings(caplog)) == 2


def test_idle_calibration_captures_are_quiet_too(tmp_path, monkeypatch, caplog):
    skill = _skill(tmp_path, monkeypatch, dict(grab=_NOT_FOREGROUND, present=True))
    reader = _Reader()
    reader.planet_rotation_tracker = object()
    skill._local_reader = lambda: reader
    with caplog.at_level(logging.WARNING):
        for _ in range(5):
            skill._capture_position_local(calibration_only=True)
    assert len(_warnings(caplog)) == 1
    assert _log(tmp_path).count("REFUSED: screen grab failed") == 1
