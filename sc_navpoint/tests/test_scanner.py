"""Structured OCR payload validation; historical Vision adapters removed."""

from __future__ import annotations

import json
from pathlib import Path

import pytest



import scanner  # noqa: E402
from scanner import NavPointScanner  # noqa: E402


_SKILL_DIR = Path(__file__).resolve().parent.parent
_SCANNER_SRC = (_SKILL_DIR / "scanner.py").read_text(encoding="utf-8")


@pytest.fixture
def nav_scanner() -> NavPointScanner:
    return NavPointScanner()




# The full local-frame JSON from spec section 1.1 output contract.
_HAPPY_JSON = {
    "local_frame": True,
    "body_token": "Stanton_4b_Clio",
    "x": 123237.455097,
    "y": -313535.207901,
    "z": 14932.665921,
    "camdir": [-27.0, 42.0, -98.0],
    "zone": "DRAK_Clipper_698212607305",
    "location": "Stanton4b",
    "altitude": 8.661078,
    "radius": 337170.0,
    "server_id": "pub-euw1b-sc-alpha-480-12061511-game-82",
}


# ---------------------------------------------------------------------- #
# Item 1: local_frame true happy path
# ---------------------------------------------------------------------- #


def test_local_frame_true_happy_path(nav_scanner: NavPointScanner) -> None:
    result = nav_scanner.parse_payload(_HAPPY_JSON)
    assert result is not None
    assert result["local_frame"] is True
    # body/system derived from body_token by "_" split (last / first token).
    assert result["body"] == "Clio"
    assert result["system"] == "Stanton"
    # x/y/z come from CamPos Planet Zone, parsed as floats.
    assert result["x"] == 123237.455097
    assert result["y"] == -313535.207901
    assert result["z"] == 14932.665921
    assert isinstance(result["x"], float)
    # camdir kept as a 3-float tuple.
    assert result["camdir"] == (-27.0, 42.0, -98.0)
    assert isinstance(result["camdir"], tuple)
    assert all(isinstance(c, float) for c in result["camdir"])
    # pass-through string fields preserved.
    assert result["zone"] == "DRAK_Clipper_698212607305"
    assert result["location"] == "Stanton4b"
    assert result["server_id"] == "pub-euw1b-sc-alpha-480-12061511-game-82"
    # altitude/radius floats when present.
    assert result["altitude"] == 8.661078
    assert result["radius"] == 337170.0
    # heading is no longer emitted; the interim planet/moon keys are gone.
    assert "heading" not in result
    assert "planet" not in result
    assert "moon" not in result


# ---------------------------------------------------------------------- #
# Item 2: local_frame false
# ---------------------------------------------------------------------- #


def test_local_frame_false(nav_scanner: NavPointScanner) -> None:
    raw = json.dumps(
        {
            "local_frame": False,
            "location": "StantonSolarSystem",
            "server_id": "pub-server-xyz",
        }
    )
    result = nav_scanner.parse_payload(json.loads(raw))
    assert result is not None
    assert result["local_frame"] is False
    assert result["body"] == ""
    # No coordinates on a frame with no OOC_ zone line.
    assert "x" not in result
    assert "y" not in result
    assert "z" not in result
    # location preserved; body/zone/system normalized empty.
    assert result["location"] == "StantonSolarSystem"
    assert result["zone"] == ""
    assert result["system"] == ""
    assert result["server_id"] == "pub-server-xyz"


# ---------------------------------------------------------------------- #
# Item 3: error / unparseable / markdown fence
# ---------------------------------------------------------------------- #


def test_error_key_returns_none(nav_scanner: NavPointScanner) -> None:
    raw = '{"error": "r_displayinfo not visible"}'
    assert nav_scanner.parse_payload(json.loads(raw)) is None








# ---------------------------------------------------------------------- #
# Item 4: local_frame true but x/y/z incomplete -> None
# ---------------------------------------------------------------------- #


def test_local_frame_true_missing_z_returns_none(
    nav_scanner: NavPointScanner,
) -> None:
    raw = json.dumps(
        {"local_frame": True, "body_token": "Stanton_4b_Clio", "x": 1.0, "y": 2.0}
    )
    assert nav_scanner.parse_payload(json.loads(raw)) is None


def test_local_frame_true_non_numeric_xyz_returns_none(
    nav_scanner: NavPointScanner,
) -> None:
    raw = json.dumps(
        {
            "local_frame": True,
            "body_token": "Stanton_4b_Clio",
            "x": "not-a-number",
            "y": 2.0,
            "z": 3.0,
        }
    )
    assert nav_scanner.parse_payload(json.loads(raw)) is None


# ---------------------------------------------------------------------- #
# Item 5: single-token body_token is rejected (plausibility gate, v4.9.0.5)
# ---------------------------------------------------------------------- #


def test_single_token_body_token_rejected(
    nav_scanner: NavPointScanner,
) -> None:
    # A body_token with no "_" is not a real OOC token (System_designator_Body).
    # The old lenient split let it through as body == system; the v4.9.0.5
    # plausibility gate now rejects it as implausible_body.
    raw = json.dumps(
        {"local_frame": True, "body_token": "Hurston", "x": 1.0, "y": 2.0, "z": 3.0}
    )
    assert nav_scanner.parse_payload(json.loads(raw)) is None
    assert nav_scanner.last_reject_reason == "implausible_body"


# ---------------------------------------------------------------------- #
# Item 6: camdir absent -> key absent (chosen convention)
# ---------------------------------------------------------------------- #


def test_camdir_absent_key_absent(nav_scanner: NavPointScanner) -> None:
    raw = json.dumps(
        {"local_frame": True, "body_token": "Stanton_4b_Clio", "x": 1.0, "y": 2.0, "z": 3.0}
    )
    result = nav_scanner.parse_payload(json.loads(raw))
    assert result is not None
    # Convention: the camdir key is ABSENT when the CamDir line is absent.
    assert "camdir" not in result


# ---------------------------------------------------------------------- #
# Item 7: null / "null" / "none" strings normalize to ""
# ---------------------------------------------------------------------- #


def test_null_string_fields_become_empty(nav_scanner: NavPointScanner) -> None:
    raw = json.dumps(
        {
            "local_frame": True,
            "body_token": "Stanton_4b_Clio",
            "x": 1.0,
            "y": 2.0,
            "z": 3.0,
            "zone": None,
            "location": "none",
            "server_id": "null",
        }
    )
    result = nav_scanner.parse_payload(json.loads(raw))
    assert result is not None
    assert result["zone"] == ""
    assert result["location"] == ""
    assert result["server_id"] == ""
    # Derivation still happens even when the pass-through fields are blank.
    assert result["body"] == "Clio"
    assert result["system"] == "Stanton"
