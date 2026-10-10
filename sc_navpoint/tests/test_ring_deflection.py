"""What the ring is allowed to draw.

`ring_deflection` is the single authority for whether a bubble may appear at
all, so these tests are mostly about REFUSAL. Every case that returns None is a
case where drawing a direction would be a claim the skill cannot support, and
this skill's whole history of incidents is confident wrong numbers reaching the
player. A missing bubble costs a glance at the HUD page; a wrong one costs a
flight in the wrong direction.

Written against the shapes the runtime actually produces: positions as
`scanner.parse_payload` returns them, targets as
`NavPointDatabase.navpoint_to_dict` returns them.
"""

from __future__ import annotations

import pytest

import navigation
from navigation import POSITION_FRESHNESS_S, calculate_bearing, ring_deflection


def _surface_pos(**over) -> dict:
    pos = {
        "x": 100.0,
        "y": 0.0,
        "z": 295_000.0,
        "body": "Daymar",
        "heading": 0.0,
        "active_frame": "planet",
        "frame_id": "daymar",
        "camdir": [0, 0, 0],
        "planet_rotation": {"frame_id": "daymar", "angle": 0., "valid": True},
        "captured_at": 1.0,
    }
    pos.update(over)
    return pos


def _surface_target(**over) -> dict:
    target = {
        "x": 1100.0,
        "y": 0.0,
        "z": 295_000.0,
        "body": "Daymar",
        "frame": "local",
        "frame_id": "",
    }
    target.update(over)
    return target


def _space_pos(**over) -> dict:
    pos = {
        "x": -1.89408e10,
        "y": -2.61006e9,
        "z": 627_710.0,
        "body": "",
        "system_frame": True,
        "frame_id": "729494885314",
        "camdir": (0.0, 0.0, 0.0),
    }
    pos.update(over)
    return pos


def _space_target(**over) -> dict:
    target = {
        "x": -1.89308e10,
        "y": -2.61006e9,
        "z": 627_710.0,
        "body": "",
        "frame": "system",
        "frame_id": "729494885314",
    }
    target.update(over)
    return target


# ── nothing to draw ───────────────────────────────────────────────────────── #


def test_no_target_draws_nothing() -> None:
    assert ring_deflection(_surface_pos(), None, 1.0) is None


def test_no_position_draws_nothing() -> None:
    assert ring_deflection(None, _surface_target(), 1.0) is None


def test_unstamped_position_draws_nothing() -> None:
    """An age of None means the capture carried no timestamp, so its age is
    unknown, and unknown age is treated as stale rather than as fresh."""
    assert ring_deflection(_surface_pos(), _surface_target(), None) is None


def test_stale_position_draws_nothing() -> None:
    stale = POSITION_FRESHNESS_S + 0.1
    assert ring_deflection(_surface_pos(), _surface_target(), stale) is None


def test_position_exactly_at_the_freshness_limit_still_draws() -> None:
    assert ring_deflection(_surface_pos(), _surface_target(), POSITION_FRESHNESS_S)


def test_missing_coordinates_draw_nothing() -> None:
    assert ring_deflection(_surface_pos(x=None), _surface_target(), 1.0) is None
    assert ring_deflection(_surface_pos(), _surface_target(z=None), 1.0) is None


# ── surface frame ─────────────────────────────────────────────────────────── #


def test_surface_deflection_matches_the_bearing_the_voice_reports() -> None:
    """One number, two instruments: the ring must agree with what is spoken."""
    pos, target = _surface_pos(), _surface_target()
    bearing = calculate_bearing(
        from_pos=(pos["x"], pos["y"], pos["z"]),
        to_pos=(target["x"], target["y"], target["z"]),
        current_heading=pos["heading"],
        use_local_frame=True,
    )
    from _stubs import install_runtime_stubs
    install_runtime_stubs()
    from main import SC_NavPoint
    bearing = SC_NavPoint._active_guidance(pos, target, bearing)
    assert ring_deflection(pos, target, 1.0) == (
        bearing["horizontal_offset_deg"],
        bearing["vertical_angle_deg"],
    )


def test_cross_body_draws_nothing() -> None:
    assert ring_deflection(_surface_pos(), _surface_target(body="Yela"), 1.0) is None


def test_body_comparison_ignores_case() -> None:
    assert ring_deflection(_surface_pos(body="daymar"), _surface_target(), 1.0)


def test_no_local_frame_draws_nothing() -> None:
    """Inside a station or an asteroid base there is no body-fixed frame at all."""
    assert ring_deflection(_surface_pos(body=""), _surface_target(), 1.0) is None


def test_camera_yaw_rotates_the_calibrated_deflection() -> None:
    """The bubble shows where the target is relative to where you point, so
    turning the camera must move it even when nothing else changed."""
    straight = ring_deflection(_surface_pos(), _surface_target(), 1.0)
    turned = ring_deflection(_surface_pos(camdir=[0,0,90]), _surface_target(), 1.0)
    assert straight is not None and turned is not None
    # Offsets wrap into (-180, 180], so the difference is compared on the
    # circle: a raw subtraction can read 270 for a 90 degree turn.
    delta = ((straight[0] - turned[0] + 180.0) % 360.0) - 180.0
    assert abs(delta) == pytest.approx(90.0, abs=0.2)


# ── system frame ──────────────────────────────────────────────────────────── #


def test_uncalibrated_system_frame_draws_nothing() -> None:
    """Direction in open space was measured 108.7 degrees out on 2026-07-26 and
    is withheld until calibrated. The ring must honour that, not route around
    it."""
    assert navigation.SPACE_DIRECTION_CALIBRATED is False
    assert ring_deflection(_space_pos(), _space_target(), 1.0) is None


def test_calibrated_system_frame_draws_the_offsets(monkeypatch) -> None:
    monkeypatch.setattr(navigation, "SPACE_DIRECTION_CALIBRATED", True)
    result = ring_deflection(_space_pos(), _space_target(), 1.0)
    assert result is not None
    yaw, pitch = result
    assert isinstance(yaw, float) and isinstance(pitch, float)


def test_system_frame_from_another_session_draws_nothing(monkeypatch) -> None:
    """The system frame is per session: a waypoint recorded under a different
    SolarSystem zone id no longer points anywhere."""
    monkeypatch.setattr(navigation, "SPACE_DIRECTION_CALIBRATED", True)
    other = _space_target(frame_id="111111111111")
    assert ring_deflection(_space_pos(), other, 1.0) is None


def test_system_frame_without_camdir_draws_nothing(monkeypatch) -> None:
    monkeypatch.setattr(navigation, "SPACE_DIRECTION_CALIBRATED", True)
    assert ring_deflection(_space_pos(camdir=None), _space_target(), 1.0) is None


def test_mixed_frames_draw_nothing(monkeypatch) -> None:
    """A surface position and a deep-space waypoint are different coordinate
    systems; the same numbers mean different places."""
    monkeypatch.setattr(navigation, "SPACE_DIRECTION_CALIBRATED", True)
    assert ring_deflection(_surface_pos(), _space_target(), 1.0) is None
    assert ring_deflection(_space_pos(), _surface_target(), 1.0) is None


def test_standing_on_a_space_waypoint_draws_nothing(monkeypatch) -> None:
    """Zero separation has no direction, and it must degrade to no bubble
    rather than to an exception in the render thread."""
    monkeypatch.setattr(navigation, "SPACE_DIRECTION_CALIBRATED", True)
    here = _space_pos()
    target = _space_target(x=here["x"], y=here["y"], z=here["z"])
    assert ring_deflection(here, target, 1.0) is None
