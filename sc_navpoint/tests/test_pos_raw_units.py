"""Coordinate extraction from the OOC zone Pos line, with per-axis units.

SC 4.9 (CL 12302499) omits `CamPos Planet Zone` while on a planet surface, so the
OOC zone `Pos:` line became the primary coordinate source. That line autoscales
its unit PER COMPONENT, so a dropped suffix is a silent factor-of-1000 error.
See Devlog 2026-07-26.
"""

import json

import pytest

from scanner import NavPointScanner


@pytest.fixture
def scanner():
    return NavPointScanner()


def _payload(**overrides):
    """A minimal valid local-frame payload, overridable per test."""
    data = {
        "local_frame": True,
        "body_token": "Stanton_2b_Daymar",
        "pos_raw": ["9810.08m", "-174.2880km", "238.0511km"],
        "x": None,
        "y": None,
        "z": None,
        "zone": "DRAK_Clipper_737234004249",
        "location": "Stanton2b",
        "server_id": "pub-euw1b-sc-alpha-490-12232296-game-82",
    }
    data.update(overrides)
    return data


def _parse(scanner, **overrides):
    return scanner.parse_payload(_payload(**overrides))


# --- the unit parser itself ------------------------------------------------


@pytest.mark.parametrize(
    ("token", "expected"),
    [
        ("9810.08m", 9810.08),
        ("-174.2880km", -174288.0),
        ("238.0511km", 238051.1),
        ("0.00m", 0.0),
        ("11.57m", 11.57),
        ("+5.5km", 5500.0),
        ("  238.0511km  ", 238051.1),
        ("238.0511KM", 238051.1),
        ("42M", 42.0),
    ],
)
def test_parse_length_accepts_suffixed_tokens(token, expected):
    assert NavPointScanner._parse_length_m(token) == pytest.approx(expected)


@pytest.mark.parametrize(
    "token",
    [
        "9810.08",  # no suffix: the 1000x error mode, must never be assumed
        "",
        None,
        "km",
        "abc",
        "1.2.3km",
        "9810.08 mm",
        "9810,08m",  # comma decimal separator
        "1e3m",  # exponent form is not what the overlay prints
    ],
)
def test_parse_length_rejects_unsuffixed_or_malformed(token):
    assert NavPointScanner._parse_length_m(token) is None


# --- pos_raw as the primary source ----------------------------------------


def test_pos_raw_is_converted_to_metres(scanner):
    """The real 2026-07-26 Daymar reading must parse to the metres it means."""
    result = _parse(scanner)
    assert result is not None
    assert result["x"] == pytest.approx(9810.08)
    assert result["y"] == pytest.approx(-174288.0)
    assert result["z"] == pytest.approx(238051.1)
    assert result["body"] == "Daymar"
    assert result["system"] == "Stanton"


def test_pos_raw_works_without_campos(scanner):
    """The 4.9 surface case: CamPos absent entirely, capture still succeeds."""
    data = _payload()
    del data["x"], data["y"], data["z"]
    result = scanner.parse_payload(data)
    assert result is not None
    assert result["x"] == pytest.approx(9810.08)


def test_missing_unit_suffix_is_refused(scanner):
    """A component with no unit is refused, never assumed to be metres."""
    result = _parse(scanner, pos_raw=["9810.08m", "-174.2880", "238.0511km"])
    assert result is None
    assert scanner.last_reject_reason == "unreadable_units"


def test_wrong_length_pos_raw_is_refused(scanner):
    result = _parse(scanner, pos_raw=["9810.08m", "-174.2880km"])
    assert result is None
    assert scanner.last_reject_reason == "unreadable_units"


def test_null_component_is_refused(scanner):
    """A component the model could not read must not be silently dropped."""
    result = _parse(scanner, pos_raw=["9810.08m", None, "238.0511km"])
    assert result is None
    assert scanner.last_reject_reason == "unreadable_units"


def test_no_coordinates_at_all_is_refused_without_a_unit_reason(scanner):
    data = _payload()
    del data["x"], data["y"], data["z"]
    del data["pos_raw"]
    result = scanner.parse_payload(data)
    assert result is None
    assert scanner.last_reject_reason is None


# --- CamPos as cross-check, and legacy compatibility ----------------------


def test_campos_agreeing_with_pos_raw_is_accepted(scanner):
    """Both readings present and consistent: the 4.8-style in-frame case."""
    result = _parse(scanner, x=9810.08, y=-174288.0, z=238051.1)
    assert result is not None
    assert result["x"] == pytest.approx(9810.08)


def test_campos_within_rounding_tolerance_is_accepted(scanner):
    """The OOC line prints 0.1 m resolution, so sub-metre disagreement is fine."""
    result = _parse(scanner, x=9810.12, y=-174287.6, z=238051.35)
    assert result is not None


def test_campos_disagreeing_with_pos_raw_is_refused(scanner):
    """Two independent reads that conflict mean one is wrong; trust neither."""
    result = _parse(scanner, x=9810.08, y=-174288.0, z=999999.0)
    assert result is None
    assert scanner.last_reject_reason == "coord_mismatch"


def test_campos_only_still_works(scanner):
    """Legacy path: pos_raw absent, CamPos present (deep-space or older builds)."""
    data = _payload(x=519474.308929, y=436066.432518, z=736357.378582)
    del data["pos_raw"]
    result = scanner.parse_payload(data)
    assert result is not None
    assert result["x"] == pytest.approx(519474.308929)


def test_partial_campos_is_not_used_as_a_source(scanner):
    data = _payload(x=9810.08, y=None, z=None)
    del data["pos_raw"]
    result = scanner.parse_payload(data)
    assert result is None


def test_signed_coordinate_triplet_survives(scanner):
    """Signed, explicitly unit-suffixed coordinates remain valid."""
    result = _parse(scanner, pos_raw=["111000.0m", "-222000.0m", "333000.0m"])
    assert result is not None
