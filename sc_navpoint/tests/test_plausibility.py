"""Structured OCR payload validation; historical Vision adapters removed."""

from __future__ import annotations

import json

import pytest




import scanner  # noqa: E402
from scanner import NavPointScanner  # noqa: E402


@pytest.fixture
def nav_scanner() -> NavPointScanner:
    return NavPointScanner()


def _local_frame_payload(**overrides) -> dict:
    base = {
        "local_frame": True,
        "body_token": "Stanton_4_Microtech",
        "x": 1.0,
        "y": 2.0,
        "z": 3.0,
    }
    base.update(overrides)
    return base


# ---------------------------------------------------------------------- #
# Gate rejections
# ---------------------------------------------------------------------- #


def test_gate_rejects_confabulated_body_token(nav_scanner: NavPointScanner) -> None:
    # The actual confabulated token from the 2026-07-22 incident: two segments,
    # but the leading segment "LargeTop" is not a known system.
    raw = json.dumps(_local_frame_payload(body_token="LargeTop_NewBabbage"))
    assert nav_scanner.parse_payload(json.loads(raw)) is None
    assert nav_scanner.last_reject_reason == "implausible_body"


def test_gate_rejects_single_token_body(nav_scanner: NavPointScanner) -> None:
    # A single-token body_token has no "_" split, so it cannot be
    # System_designator_Body. The old lenient split let it through.
    raw = json.dumps(_local_frame_payload(body_token="Microtech"))
    assert nav_scanner.parse_payload(json.loads(raw)) is None
    assert nav_scanner.last_reject_reason == "implausible_body"


def test_gate_rejects_empty_body_token(nav_scanner: NavPointScanner) -> None:
    raw = json.dumps(_local_frame_payload(body_token=""))
    assert nav_scanner.parse_payload(json.loads(raw)) is None
    assert nav_scanner.last_reject_reason == "implausible_body"


# ---------------------------------------------------------------------- #
# Gate acceptance (case-insensitive known-system match)
# ---------------------------------------------------------------------- #


@pytest.mark.parametrize("token", ["Stanton_4_Microtech", "stanton_4_microtech"])
def test_gate_accepts_known_system_case_insensitive(
    nav_scanner: NavPointScanner, token: str
) -> None:
    raw = json.dumps(_local_frame_payload(body_token=token))
    result = nav_scanner.parse_payload(json.loads(raw))
    assert result is not None
    assert result["body"] == token.split("_")[-1]
    assert result["system"] == token.split("_")[0]
    assert nav_scanner.last_reject_reason is None


def test_gate_accepts_pyro_and_nyx(nav_scanner: NavPointScanner) -> None:
    for token in ("Pyro_1_Bloom", "Nyx_2b_Delamar"):
        result = nav_scanner.parse_payload(_local_frame_payload(body_token=token))
        assert result is not None
        assert nav_scanner.last_reject_reason is None


def test_known_systems_constant() -> None:
    assert scanner._KNOWN_SYSTEMS == frozenset({"stanton", "pyro", "nyx"})
