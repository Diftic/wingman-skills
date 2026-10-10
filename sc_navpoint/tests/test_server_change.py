"""Two-capture confirmation for wipe-on-relog and the echo badge (v4.9.0.4).

On 2026-07-20 a single hallucinated server_id (from a Vision echo of the prompt
example) tripped wipe-on-relog and destroyed the user's renamed waypoint. The
wipe now fires only after TWO consecutive captures agree on the same new
server_id, mirroring the arrival auto-stop's two-poll confirmation. These tests
drive _handle_server_change through _capture_position with a real database and
recording fakes.

main.py imports the Wingman runtime at module scope; _stubs installs minimal
stand-ins before it is imported. scanner still imports PIL/mss for real, so the
module skips cleanly if either is unavailable.
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from unittest.mock import MagicMock

import pytest


pytest.importorskip("PIL")
pytest.importorskip("mss")

from _stubs import LogType, install_runtime_stubs  # noqa: E402


install_runtime_stubs()

import main  # noqa: E402
from database import NavPointDatabase  # noqa: E402


# ---------------------------------------------------------------------- #
# Fakes
# ---------------------------------------------------------------------- #


class _FakeScanner:
    """Returns a caller-supplied position dict, standing in for OCR + parse."""

    def __init__(self, pos: dict | None) -> None:
        self._pos = pos
        self.last_reject_reason: str | None = None



    def read_payload(self) -> dict | None:
        return dict(self._pos) if self._pos is not None else None


class _RejectedScanner:
    """Always reports a capture rejected for an unsupported body name."""

    def __init__(self) -> None:
        self.last_reject_reason: str | None = None



    def read_payload(self) -> dict | None:
        self.last_reject_reason = "implausible_body"
        return None


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


def _make_skill(*, scanner, db: NavPointDatabase | None) -> main.SC_NavPoint:
    skill = main.SC_NavPoint.__new__(main.SC_NavPoint)
    skill._scanner = scanner
    skill._implausible_badge_shown = False
    skill._db = db
    skill._ui_server = _RecordingUI()
    skill._ui_window = None
    skill._active_target = None
    skill._nav_task = None
    skill._pending_server_change = None
    skill.printr = _RecordingPrintr()


    skill._get_display = lambda: 1
    skill._stop_nav_polling = MagicMock()
    # Inject at the local-reader boundary and retain each capture's refusal.
    skill._reader_state = ""
    skill._reader = None
    # `attempts` because the real read takes it now; this fixture answers the
    # same whatever it is given, and the wipe gate counts CAPTURES rather than
    # the frames one capture looked at, which is what these tests assert.
    skill._capture_position_local = lambda attempts=1: scanner.read_payload()
    return skill


def _pos(server_id: str) -> dict:
    return {"x": 1.0, "y": 2.0, "z": 3.0, "body": "Daymar", "server_id": server_id}


def _warnings(skill: main.SC_NavPoint) -> list:
    return [c for c in skill.printr.calls if c[1] == LogType.WARNING]


# ---------------------------------------------------------------------- #
# Two-capture wipe gate
# ---------------------------------------------------------------------- #


def test_first_differing_capture_sets_pending_no_wipe(tmp_path: Path) -> None:
    db = NavPointDatabase(str(tmp_path))
    db.add_navpoint("Old", "pub-euw1b-sc-alpha-490-11111111-game-82", "Daymar", 1.0, 2.0, 3.0)
    skill = _make_skill(scanner=_FakeScanner(_pos("pub-euw1b-sc-alpha-490-22222222-game-82")), db=db)
    skill._active_target = db.find_navpoint_by_name("Old")

    asyncio.run(skill._capture_position())

    # A single new-server read never wipes; it only arms the confirmation.
    assert db.count_navpoints() == 1
    assert skill._pending_server_change == "pub-euw1b-sc-alpha-490-22222222-game-82"
    assert skill._active_target is not None
    assert not _warnings(skill)


def test_third_consecutive_capture_wipes(tmp_path: Path) -> None:
    db = NavPointDatabase(str(tmp_path))
    db.add_navpoint("Old", "pub-euw1b-sc-alpha-490-11111111-game-82", "Daymar", 1.0, 2.0, 3.0)
    skill = _make_skill(scanner=_FakeScanner(_pos("pub-euw1b-sc-alpha-490-22222222-game-82")), db=db)
    skill._active_target = db.find_navpoint_by_name("Old")

    asyncio.run(skill._capture_position())
    asyncio.run(skill._capture_position())
    # Two is no longer enough.
    assert db.count_navpoints() == 1
    asyncio.run(skill._capture_position())

    # THREE consecutive agreeing captures now prove the change (was two: the
    # model misread the same way twice and deleted real waypoints).
    assert db.count_navpoints() == 0
    assert skill._pending_server_change is None
    assert skill._active_target is None
    skill._stop_nav_polling.assert_called()
    assert None in skill._ui_server.set_active_target_calls
    warnings = _warnings(skill)
    assert warnings, "expected a WARNING chat badge on the confirmed change"
    assert all(c[2] is False for c in warnings)
    assert any("Server changed" in c[0] for c in warnings)


def test_differing_then_matching_resets_pending_no_wipe(tmp_path: Path) -> None:
    db = NavPointDatabase(str(tmp_path))
    db.add_navpoint("Old", "pub-euw1b-sc-alpha-490-11111111-game-82", "Daymar", 1.0, 2.0, 3.0)
    scanner = _FakeScanner(_pos("pub-euw1b-sc-alpha-490-22222222-game-82"))
    skill = _make_skill(scanner=scanner, db=db)
    skill._active_target = db.find_navpoint_by_name("Old")

    asyncio.run(skill._capture_position())
    assert skill._pending_server_change == "pub-euw1b-sc-alpha-490-22222222-game-82"

    # Next capture reads back the stored server: a transient misread, cleared.
    scanner._pos = _pos("pub-euw1b-sc-alpha-490-11111111-game-82")
    asyncio.run(skill._capture_position())

    assert db.count_navpoints() == 1
    assert skill._pending_server_change is None
    assert not _warnings(skill)


def test_two_different_new_servers_do_not_wipe(tmp_path: Path) -> None:
    db = NavPointDatabase(str(tmp_path))
    db.add_navpoint("Old", "pub-euw1b-sc-alpha-490-11111111-game-82", "Daymar", 1.0, 2.0, 3.0)
    scanner = _FakeScanner(_pos("pub-euw1b-sc-alpha-490-33333333-game-82"))
    skill = _make_skill(scanner=scanner, db=db)
    skill._active_target = db.find_navpoint_by_name("Old")

    asyncio.run(skill._capture_position())
    assert skill._pending_server_change == "pub-euw1b-sc-alpha-490-33333333-game-82"

    # A different new server on the second read is not a confirmation; re-arm.
    scanner._pos = _pos("pub-euw1b-sc-alpha-490-44444444-game-82")
    asyncio.run(skill._capture_position())

    assert db.count_navpoints() == 1
    assert skill._pending_server_change == "pub-euw1b-sc-alpha-490-44444444-game-82"
    assert not _warnings(skill)


def test_no_pending_when_server_matches_stored(tmp_path: Path) -> None:
    db = NavPointDatabase(str(tmp_path))
    db.add_navpoint("Keep", "pub-euw1b-sc-alpha-490-55555555-game-82", "Daymar", 1.0, 2.0, 3.0)
    skill = _make_skill(scanner=_FakeScanner(_pos("pub-euw1b-sc-alpha-490-55555555-game-82")), db=db)
    skill._active_target = db.find_navpoint_by_name("Keep")

    asyncio.run(skill._capture_position())

    assert db.count_navpoints() == 1
    assert skill._pending_server_change is None
    assert not _warnings(skill)


# ---------------------------------------------------------------------- #
# Unsupported-body badge fires once and only once
# ---------------------------------------------------------------------- #


def test_implausible_badge_prints_once_only() -> None:
    skill = _make_skill(scanner=_RejectedScanner(), db=None)

    for _ in range(3):
        assert asyncio.run(skill._capture_position()) is None

    echo_badges = [
        c
        for c in skill.printr.calls
        if c[1] == LogType.WARNING and "body name did not pass" in c[0]
    ]
    assert len(echo_badges) == 1


# ---------------------------------------------------------------------- #
# Malformed server tokens must never wipe (data-loss incident 2026-07-26)
# ---------------------------------------------------------------------- #


@pytest.mark.parametrize(
    "garbled",
    [
        "pub-euw1b-5c-alpha-490-12286454-game-142",  # s misread as 5, observed live
        "pub-euw1b-12269732_070",                    # structure lost, observed live
        "",
        "pub-euw1b-sc-alpha-490-12232296-game",      # truncated
        "some random text",
    ],
)
def test_garbled_server_token_never_wipes(tmp_path: Path, garbled: str) -> None:
    """Six waypoints were deleted mid-session by two agreeing misreads.

    An unreadable token is not evidence of a different server, so it must not be
    able to destroy anything however many times it repeats.
    """
    db = NavPointDatabase(str(tmp_path))
    db.add_navpoint("Keep", "pub-euw1b-sc-alpha-490-11111111-game-82", "Daymar", 1.0, 2.0, 3.0)
    skill = _make_skill(scanner=_FakeScanner(_pos(garbled)), db=db)

    for _ in range(5):
        asyncio.run(skill._capture_position())

    assert db.count_navpoints() == 1, "a garbled server token wiped waypoints"
    assert skill._pending_server_change is None


def test_garbled_token_warns_once(tmp_path: Path) -> None:
    db = NavPointDatabase(str(tmp_path))
    db.add_navpoint("Keep", "pub-euw1b-sc-alpha-490-11111111-game-82", "Daymar", 1.0, 2.0, 3.0)
    skill = _make_skill(scanner=_FakeScanner(_pos("pub-euw1b-5c-alpha-490-1-game-1")), db=db)
    for _ in range(3):
        asyncio.run(skill._capture_position())
    unreadable = [c for c in _warnings(skill) if "could not be read cleanly" in c[0]]
    assert len(unreadable) == 1, "the degraded-tracking badge must appear once only"
