"""Refusing a waypoint captured at the Star Citizen main menu.

At the main menu the overlay still decodes a complete, valid stack:
`Zone: SolarSystem_200000000001 Pos: -0.00m 0.04m 1.74m` and
`Zone: Root Pos: -0.00m 0.04m 1.74m`, with no nested rows. Every gate that
existed before this one validates SHAPE (units, agreement, echoes); none of
them asks whether the shape describes a place in the game, so a player could
mark a waypoint at the menu. Lars decided 2026-08-11 that this must be
refused.

The gate lives in `NavPointScanner.parse_payload`, downstream of BOTH parsers
(`overlay_fields.payload_from_rows` and `stack_from_rows`) and of the retained
Vision path, because that is the one validation seam every payload shape
passes through.
"""

from __future__ import annotations

import glob
from pathlib import Path

import pytest


pytest.importorskip("PIL")
pytest.importorskip("mss")

import numpy as np  # noqa: E402
from PIL import Image  # noqa: E402

import overlay_fields as fields  # noqa: E402
import overlay_reader as ov  # noqa: E402
from scanner import NavPointScanner  # noqa: E402


_CAPTURES = Path(__file__).resolve().parent.parent / "ocr_dev" / "captures"
_GLYPHS = Path(__file__).resolve().parent.parent / "overlay_glyphs.npz"

# The real menu reading: 5/5 frames, two sessions. sqrt(0.04^2 + 1.74^2) m.
MENU_POS_RAW = ["-0.00m", "0.04m", "1.74m"]

# Same digits, corrupted unit suffix (the 1000x failure mode this project has
# been burned by before). Still refuses, which pins how much headroom the
# floor has below the real menu reading before that specific corruption could
# ever accidentally clear it.
MENU_KM_VARIANT_POS_RAW = ["-0.00km", "0.04km", "1.74km"]

# The smallest observed REAL Root magnitude: 1.3889e10 m, over 647 accepted
# stacks across 23 sessions. Expressed in km, on one axis.
SMALLEST_REAL_ROOT_POS_RAW = ["13889000.0km", "0.0km", "0.0km"]

# Per-session minima from the same corpus, each its own accept case.
SESSION_MINIMA_POS_RAW = [
    ["14998000.0km", "0.0km", "0.0km"],  # 1.4998e10 m
    ["15001000.0km", "0.0km", "0.0km"],  # 1.5001e10 m
    ["17796000.0km", "0.0km", "0.0km"],  # 1.7796e10 m
    ["49384000.0km", "0.0km", "0.0km"],  # 4.9384e10 m
]

# The stack-schema equivalent of MENU_POS_RAW, for the stack-only case.
_MENU_STACK_DICT = {
    "schema": 1,
    "root": {"x_m": -0.0, "y_m": 0.04, "z_m": 1.74, "raw_name": "Root", "raw": ""},
    "solar": {
        "x_m": -0.0, "y_m": 0.04, "z_m": 1.74,
        "raw_name": "SolarSystem_200000000001", "raw": "",
    },
    "nested": [],
    "candidate_depth": None,
}


def _space_payload(pos_raw: list[str]) -> dict:
    """A minimal legacy space payload at the given magnitude.

    `system_pos_raw` and `root_pos_raw` carry the SAME values, so the
    SolarSystem/Root agreement check upstream of the gate under test never
    interferes with what these tests pin.
    """
    return {
        "local_frame": False,
        "system_pos_raw": list(pos_raw),
        "root_pos_raw": list(pos_raw),
    }


def _captures(session: str) -> list[Path]:
    paths = sorted(
        Path(p) for p in glob.glob(str(_CAPTURES / session / "shot_*.png"))
    )
    if not paths:
        pytest.skip(f"{session} capture corpus not present")
    return paths


# --------------------------------------------------------------------- #
# T1: real pixels, end to end. The one that matters.
# --------------------------------------------------------------------- #


@pytest.mark.parametrize("session", ["login", "login-black"])
def test_no_frame_from_either_login_session_yields_a_position(session):
    """Every frame from both login captures refuses with `no_game_world`.

    Phrased so that a frame refusing EARLIER (an unusable frame, an unreadable
    row) passes trivially: what matters is that none of them ever reaches an
    accepted position.
    """
    for path in _captures(session):
        frame = np.asarray(Image.open(path).convert("RGB")).astype(np.float64)
        usable, _ = ov.capture_is_usable(frame)
        if not usable:
            continue
        reader = ov.OverlayReader(_GLYPHS)
        _, _, rows = reader.read(frame, ov.POSITION_ROWS)
        payload, _ = fields.capture_payload(rows)
        scanner = NavPointScanner()
        result = scanner.parse_payload(payload) if payload is not None else None
        assert result is None, f"{path}: menu capture yielded a position"
        if payload is not None:
            assert scanner.last_reject_reason == "no_game_world", (
                f"{path}: refused for {scanner.last_reject_reason!r}, "
                "not no_game_world"
            )


@pytest.mark.parametrize("session", ["login", "login-black"])
def test_login_frames_still_decode_a_payload_from_both_parsers(session):
    """Documents that the gate is DOWNSTREAM of both parsers.

    If this failed, `test_no_frame_from_either_login_session_yields_a_position`
    could be passing for the wrong reason: an earlier gate refusing the frame
    outright, rather than this gate refusing a payload that decoded cleanly.
    """
    decoded = 0
    for path in _captures(session):
        frame = np.asarray(Image.open(path).convert("RGB")).astype(np.float64)
        usable, _ = ov.capture_is_usable(frame)
        if not usable:
            continue
        reader = ov.OverlayReader(_GLYPHS)
        _, _, rows = reader.read(frame, ov.POSITION_ROWS)
        payload, _ = fields.capture_payload(rows)
        if payload is not None:
            decoded += 1
    assert decoded > 0, f"{session}: no frame produced a payload to gate at all"


# --------------------------------------------------------------------- #
# T2: boundary and direction
# --------------------------------------------------------------------- #


def test_menu_magnitude_refuses():
    scanner = NavPointScanner()
    assert scanner.parse_payload(_space_payload(MENU_POS_RAW)) is None
    assert scanner.last_reject_reason == "no_game_world"


def test_menu_magnitude_with_km_unit_corruption_still_refuses():
    """A dropped 'k' inflates the menu reading 1000x; even then it refuses."""
    scanner = NavPointScanner()
    result = scanner.parse_payload(_space_payload(MENU_KM_VARIANT_POS_RAW))
    assert result is None
    assert scanner.last_reject_reason == "no_game_world"


def test_smallest_real_root_accepts():
    scanner = NavPointScanner()
    result = scanner.parse_payload(_space_payload(SMALLEST_REAL_ROOT_POS_RAW))
    assert result is not None
    assert scanner.last_reject_reason is None


@pytest.mark.parametrize("pos_raw", SESSION_MINIMA_POS_RAW)
def test_session_minima_accept(pos_raw):
    scanner = NavPointScanner()
    result = scanner.parse_payload(_space_payload(pos_raw))
    assert result is not None
    assert scanner.last_reject_reason is None


# --------------------------------------------------------------------- #
# T3: both sources, which the real fixture cannot distinguish
# --------------------------------------------------------------------- #


def test_stack_only_payload_at_menu_magnitude_refuses():
    """No root_pos_raw or system_pos_raw at all, only the schema-1 stack."""
    payload = {"local_frame": False, "coordinate_stack": dict(_MENU_STACK_DICT)}
    assert "root_pos_raw" not in payload and "system_pos_raw" not in payload
    scanner = NavPointScanner()
    result = scanner.parse_payload(payload)
    assert result is None
    assert scanner.last_reject_reason == "no_game_world"


def test_legacy_only_payload_at_menu_magnitude_refuses():
    """No coordinate_stack at all, only the legacy pos_raw fields."""
    payload = _space_payload(MENU_POS_RAW)
    assert "coordinate_stack" not in payload
    scanner = NavPointScanner()
    result = scanner.parse_payload(payload)
    assert result is None
    assert scanner.last_reject_reason == "no_game_world"


# --------------------------------------------------------------------- #
# T5: the ORDER decision (2026-08-11) — corruption outranks "no world"
# --------------------------------------------------------------------- #


def test_a_disagreeing_sub_floor_pair_reports_frame_mismatch_not_no_game_world():
    """A payload that is BOTH sub-floor AND internally disagreeing must be
    diagnosed as corrupt, not as a location claim.

    A disagreeing SolarSystem/Root pair means AT LEAST ONE of the two numbers
    is wrong; concluding "the player is not in a game world" from a number
    already known to be wrong is the weaker diagnosis, since it replaces a
    precise fact (a misread happened) with a vaguer one (you are nowhere).
    `no_game_world` may therefore only fire on a pair already proven
    internally consistent, which is why the SolarSystem/Root crosscheck runs
    BEFORE the magnitude check in the legacy space branch (2026-08-11
    decision). Here `system_pos_raw` (~3.7 m) and `root_pos_raw` (~374 m) are
    both individually sub-floor, but they disagree by ~297 m against an
    allowed tolerance of ~1 m, so the crosscheck must win.
    """
    payload = {
        "local_frame": False,
        "system_pos_raw": ["1.0m", "2.0m", "3.0m"],       # magnitude ~3.7 m
        "root_pos_raw": ["100.0m", "200.0m", "300.0m"],   # magnitude ~374 m
    }
    scanner = NavPointScanner()
    result = scanner.parse_payload(payload)
    assert result is None
    assert scanner.last_reject_reason == "frame_mismatch"


def test_a_disagreeing_sub_floor_stack_reports_frame_mismatch_not_no_game_world():
    """The stack-source equivalent, for the same reasoning as above.

    Unlike the legacy path, this ordering was never a decision that could
    drift: `_validated_stack` runs `coordinate_stack.solar_root_agree`
    unconditionally, before `parse_payload` ever reaches the stack half of
    the no-game-world gate, so a disagreeing stack.root/stack.solar pair is
    refused as `frame_mismatch` by construction, whatever magnitude it is at.
    This test proves the construction is reachable (it is: both rows here
    are sub-floor, ~3.7 m and ~374 m) rather than assuming it, and pins the
    same "corruption outranks no_game_world" guarantee for the stack source.
    No order-mutation applies here the way it does for the legacy half: there
    is no adjacent code to reorder, since `_validated_stack` is a separate,
    always-first call rather than a movable block inside `parse_payload`.
    """
    stack_dict = {
        "schema": 1,
        "root": {"x_m": 1.0, "y_m": 2.0, "z_m": 3.0, "raw_name": "Root", "raw": ""},
        "solar": {
            "x_m": 100.0, "y_m": 200.0, "z_m": 300.0,
            "raw_name": "SolarSystem_1", "raw": "",
        },
        "nested": [],
        "candidate_depth": None,
    }
    payload = {"local_frame": False, "coordinate_stack": stack_dict}
    scanner = NavPointScanner()
    result = scanner.parse_payload(payload)
    assert result is None
    assert scanner.last_reject_reason == "frame_mismatch"


# --------------------------------------------------------------------- #
# T4: garbage does not slip past
# --------------------------------------------------------------------- #


def test_an_unreadable_root_row_yields_no_position_refused_upstream():
    """A Root row with a corrupted component cannot blind the gate.

    The gate can only see a vector it can read; this proves that when Root is
    unreadable, an EARLIER gate refuses the capture instead of the payload
    quietly passing through with no long-range vector to check.
    """
    rows = [
        {"row": 0, "trusted": True, "kind": "zone", "text":
         "Zone: SolarSystem_200000000001 Pos: -0.00m 0.04m 1.74m"},
        {"row": 1, "trusted": False, "kind": "zone", "text":
         "Zone: Root Pos: -0.00m 0.0?m 1.74m"},
    ]
    assert fields.payload_from_rows(rows) is None
