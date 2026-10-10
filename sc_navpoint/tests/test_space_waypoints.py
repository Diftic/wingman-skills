"""Space waypoints: system-frame extraction, guidance, and frame separation.

Open space has no body-fixed frame, but a point not attached to a rotating body
keeps a stable address in the star system's own frame. That was measured on
2026-07-26: a parked ship's SolarSystem position was byte-identical over five
minutes, while a stationary point on Daymar's surface drifted through that same
frame at 122.7 m/s. See Devlog.

The fixtures use the real open-space capture from that session.
"""

from __future__ import annotations

import json

import pytest


pytest.importorskip("PIL")
pytest.importorskip("mss")

from navigation import (  # noqa: E402
    LocalFrameUnavailable,
    camdir_orientation,
    relative_deflection,
    space_guidance,
)
from scanner import NavPointScanner  # noqa: E402


# The 2026-07-26 deep-space capture, Drake Clipper parked in Stanton.
_REAL_SYSTEM_POS = ["-60077861.1780km", "21737086.4624km", "19428930.4479km"]


@pytest.fixture
def scanner() -> NavPointScanner:
    return NavPointScanner()


def _space_payload(**overrides) -> dict:
    data = {
        "local_frame": False,
        "location": "StantonSolarSystem",
        "server_id": "pub-euw1b-sc-alpha-490-12232296-game-82",
        "system_zone_id": "729494885309",
        "system_pos_raw": list(_REAL_SYSTEM_POS),
        "root_pos_raw": list(_REAL_SYSTEM_POS),
    }
    data.update(overrides)
    return data


def _parse(scanner: NavPointScanner, **overrides):
    return scanner.parse_payload(_space_payload(**overrides))


# --- extraction -----------------------------------------------------------


def test_open_space_capture_yields_system_coordinates(scanner: NavPointScanner):
    result = _parse(scanner)
    assert result is not None
    assert result["local_frame"] is False
    assert result["system_frame"] is True
    assert result["frame_id"] == "729494885309"
    # km tokens converted to metres.
    assert result["x"] == pytest.approx(-60077861178.0)
    assert result["y"] == pytest.approx(21737086462.4)
    assert result["z"] == pytest.approx(19428930447.9)


def test_body_stays_empty_so_body_keyed_guards_still_refuse(scanner: NavPointScanner):
    """Space captures must not start satisfying surface-only checks."""
    result = _parse(scanner)
    assert result["body"] == ""
    assert result["system"] == ""


def test_root_line_disagreement_is_rejected(scanner: NavPointScanner):
    """Root duplicates SolarSystem, so disagreement means one read is wrong."""
    bad = list(_REAL_SYSTEM_POS)
    bad[1] = "21737086.9624km"  # 500 m out
    result = _parse(scanner, root_pos_raw=bad)
    assert result is None
    assert scanner.last_reject_reason == "frame_mismatch"


def test_root_line_absent_is_tolerated(scanner: NavPointScanner):
    """The tripwire is a bonus check, not a requirement."""
    data = _space_payload()
    del data["root_pos_raw"]
    result = scanner.parse_payload(data)
    assert result is not None
    assert result["system_frame"] is True


def test_missing_unit_suffix_is_refused(scanner: NavPointScanner):
    """Same 1000x guard as the surface path: never assume the unit."""
    bad = list(_REAL_SYSTEM_POS)
    bad[0] = "-60077861.1780"
    result = _parse(scanner, system_pos_raw=bad)
    assert result is not None  # still a valid open-space read, minus coordinates
    assert "system_frame" not in result
    assert scanner.last_reject_reason == "unreadable_units"


def test_open_space_without_system_lines_is_unchanged(scanner: NavPointScanner):
    """A station interior has no SolarSystem Pos to read; that is not an error."""
    data = _space_payload()
    del data["system_pos_raw"], data["root_pos_raw"]
    result = scanner.parse_payload(data)
    assert result is not None
    assert "system_frame" not in result
    assert scanner.last_reject_reason is None




# --- guidance -------------------------------------------------------------


def test_deflection_is_zero_when_pointing_at_the_target():
    camdir = (70, 0, -97)
    forward, _, _ = camdir_orientation(camdir)
    origin = (0.0, 0.0, 0.0)
    target = tuple(c * 5_000_000.0 for c in forward)
    d = relative_deflection(camdir, origin, target)
    assert d["total_offset_deg"] == pytest.approx(0.0, abs=1e-6)
    assert d["yaw_offset_deg"] == pytest.approx(0.0, abs=1e-6)
    assert d["pitch_offset_deg"] == pytest.approx(0.0, abs=1e-6)


def test_deflection_is_180_when_the_target_is_behind():
    camdir = (70, 0, -97)
    forward, _, _ = camdir_orientation(camdir)
    d = relative_deflection(camdir, (0.0, 0.0, 0.0), tuple(-c * 1e6 for c in forward))
    assert d["total_offset_deg"] == pytest.approx(180.0, abs=1e-6)


def test_yaw_sign_is_positive_to_the_right():
    camdir = (70, 0, -97)
    forward, right, _ = camdir_orientation(camdir)
    target = tuple(f + r for f, r in zip(forward, right))  # 45 degrees right
    d = relative_deflection(camdir, (0.0, 0.0, 0.0), target)
    assert d["yaw_offset_deg"] == pytest.approx(45.0, abs=1e-6)


def test_pitch_sign_is_positive_upward():
    camdir = (70, 0, -97)
    forward, _, up = camdir_orientation(camdir)
    target = tuple(f + u for f, u in zip(forward, up))
    d = relative_deflection(camdir, (0.0, 0.0, 0.0), target)
    assert d["pitch_offset_deg"] == pytest.approx(45.0, abs=1e-6)


def test_deflection_refuses_a_zero_length_target():
    with pytest.raises(LocalFrameUnavailable):
        relative_deflection((70, 0, -97), (1.0, 2.0, 3.0), (1.0, 2.0, 3.0))


def test_space_guidance_reports_no_compass_bearing():
    """There is no north in open space, so no bearing is invented."""
    g = space_guidance((70, 0, -97), (0.0, 0.0, 0.0), (1e9, 0.0, 0.0))
    assert "horizontal_bearing_deg" not in g
    assert "direction_label" not in g
    assert g["frame"] == "system"


def test_space_guidance_without_camdir_gives_distance_only():
    g = space_guidance(None, (0.0, 0.0, 0.0), (3.0, 4.0, 0.0))
    assert g["distance_m"] == pytest.approx(5.0)
    assert "horizontal_offset_deg" not in g
    assert g["turn_instruction"] == "Direction not available in open space"


def test_space_distance_is_plain_euclidean():
    """Flat Cartesian is exactly right here, unlike on a curved surface."""
    g = space_guidance(None, (0.0, 0.0, 0.0), (3e9, 4e9, 0.0))
    assert g["distance_km"] == pytest.approx(5e6)


# --- what the HUD is given -----------------------------------------------


def test_navpoint_dict_carries_the_frame_for_the_hud(tmp_path):
    """The HUD cannot tell a space waypoint from a broken one without this."""
    from database import NavPointDatabase

    db = NavPointDatabase(str(tmp_path))
    np_row = db.add_navpoint(
        name="wreck", server_id="", body="", x=1.0, y=2.0, z=3.0,
        frame="system", frame_id="729494885314",
    )
    d = db.navpoint_to_dict(np_row)
    assert d["frame"] == "system"
    assert d["frame_id"] == "729494885314"
    # Coordinates still go to the HUD: it is a display that can use them, unlike
    # the conversation model.
    assert (d["x"], d["y"], d["z"]) == (1.0, 2.0, 3.0)


def test_tool_result_dict_omits_coordinates():
    """Raw XYZ reaching the conversation model made the TTS switch language.

    System-frame values are eleven digits long, so this is not cosmetic.
    """
    import main as main_mod
    from database import NavPoint

    np_row = NavPoint(
        id=1, name="wreck", server_id="", x=-6.0077861178e10, y=2.17e10, z=1.94e10,
        body="", system="", zone="", heading=0.0, timestamp="t", notes="",
        frame="system", frame_id="729494885314",
    )
    skill = main_mod.SC_NavPoint.__new__(main_mod.SC_NavPoint)
    d = skill._navpoint_to_result_dict(np_row)
    for axis in ("x", "y", "z"):
        assert axis not in d
    assert d["frame"] == "system"
    assert d["name"] == "wreck"


# --- the seam: scanner output must actually feed the guidance --------------


def test_scanner_supplies_camdir_in_open_space(scanner: NavPointScanner):
    """The first live run reported 'heading data is not available'.

    Cause: the open-space branch never carried camdir, so guidance could only
    report distance and the ring had nothing to draw. Both sides were tested
    and green; the JOIN between them was not. This test is that join.
    """
    result = _parse(scanner, camdir=[-11.0, 22.0, -33.0])
    assert result["camdir"] == (-11.0, 22.0, -33.0)


def test_scanner_output_feeds_guidance_end_to_end(scanner: NavPointScanner, monkeypatch):
    """Drive guidance from real scanner output, never a hand-written dict.

    Direction is suppressed in shipped builds until the system-frame CamDir
    convention is calibrated, so the flag is enabled here to test the wiring
    that will be used once it is.
    """
    import navigation

    monkeypatch.setattr(navigation, "SPACE_DIRECTION_CALIBRATED", True)
    pos = _parse(scanner, camdir=[70.0, 0.0, -97.0])
    target = (pos["x"] + 2.5e8, pos["y"], pos["z"])
    g = navigation.space_guidance(pos.get("camdir"), (pos["x"], pos["y"], pos["z"]), target)
    # The camdir must reach the guidance: that seam was broken once already.
    assert "horizontal_offset_deg" in g
    assert "total_offset_deg" in g


def test_open_space_without_a_camdir_line_still_parses(scanner: NavPointScanner):
    """CamDir needs r_displayinfo 2+; absent it, degrade to distance only."""
    data = _space_payload()
    result = scanner.parse_payload(data)
    assert result is not None
    assert "camdir" not in result
    g = space_guidance(result.get("camdir"), (0.0, 0.0, 0.0), (1e9, 0.0, 0.0))
    assert g["turn_instruction"] == "Direction not available in open space"
    assert g["distance_km"] == pytest.approx(1e6)


# --- direction is withheld until calibrated -------------------------------


def test_space_direction_is_suppressed_by_default():
    """Measured 108.7 deg out against a known in-game marker on 2026-07-26.

    A confidently wrong direction is worse than none: it sent the user flying
    the wrong way. Distance stays, because distance is verified correct.
    """
    import navigation

    assert navigation.SPACE_DIRECTION_CALIBRATED is False
    g = space_guidance((70, 0, -97), (0.0, 0.0, 0.0), (1e9, 1e9, 0.0))
    assert "horizontal_offset_deg" not in g
    assert "total_offset_deg" not in g
    assert g["distance_km"] == pytest.approx(1_414_213.6, rel=1e-6)
    assert "108.7" in g["direction_note"]


def test_enabling_the_flag_restores_offsets(monkeypatch):
    """The wiring must be ready for the calibrated convention."""
    import navigation

    monkeypatch.setattr(navigation, "SPACE_DIRECTION_CALIBRATED", True)
    g = navigation.space_guidance((70, 0, -97), (0.0, 0.0, 0.0), (1e9, 1e9, 0.0))
    assert "horizontal_offset_deg" in g
    assert "total_offset_deg" in g
