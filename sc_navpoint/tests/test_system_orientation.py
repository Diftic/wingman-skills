"""The system-frame CamDir convention, measured in flight 2026-07-28.

Every anchor here came from flying the vector and watching which coordinate
moved, not from reading the overlay and interpreting it. That distinction
matters: the first attempt at this convention was fitted to surface data and
validated only on its forward vector, which is exactly why it was 108.7 degrees
wrong the first time anyone asked it for a yaw/pitch split.

The system frame is left-handed, +X east, +Y north, +Z up, origin at the star.
"""

from __future__ import annotations

import math

import pytest

from navigation import system_camdir_orientation, system_deflection


def _close(a, b, tol=1e-9) -> bool:
    return all(abs(x - y) < tol for x, y in zip(a, b))


# ── the three flown anchors ───────────────────────────────────────────────── #


def test_all_zero_points_north() -> None:
    """Flown: holding CamDir (0,0,0) and flying straight moved Y positive only."""
    forward, _right, _up = system_camdir_orientation((0.0, 0.0, 0.0))
    assert _close(forward, (0.0, 1.0, 0.0))


def test_pitch_ninety_points_up() -> None:
    """Flown: pitching the nose up reads (90, 0, 0)."""
    forward, _right, _up = system_camdir_orientation((90.0, 0.0, 0.0))
    assert _close(forward, (0.0, 0.0, 1.0))


def test_yaw_minus_ninety_points_east() -> None:
    """Flown: yawing RIGHT from north reads (0, 0, -90), and right of north is
    east. The sign is the trap here, reported identically twice."""
    forward, _right, _up = system_camdir_orientation((0.0, 0.0, -90.0))
    assert _close(forward, (1.0, 0.0, 0.0))


def test_yaw_plus_ninety_points_west() -> None:
    forward, _right, _up = system_camdir_orientation((0.0, 0.0, 90.0))
    assert _close(forward, (-1.0, 0.0, 0.0))


def test_rolling_right_puts_the_right_axis_downward() -> None:
    """Flown: rolling right reads (0, 90, 0). Roll the ship fully right and its
    right side is pointing at the floor."""
    forward, right, up = system_camdir_orientation((0.0, 90.0, 0.0))
    assert _close(forward, (0.0, 1.0, 0.0))   # roll never moves the nose
    assert _close(right, (0.0, 0.0, -1.0))
    assert _close(up, (1.0, 0.0, 0.0))


# ── handedness ────────────────────────────────────────────────────────────── #


def test_facing_north_puts_east_on_the_right() -> None:
    """The screenshot evidence: the star's direction had a negative X component
    and it appeared LEFT of the crosshair, so +X is right while facing north."""
    _forward, right, _up = system_camdir_orientation((0.0, 0.0, 0.0))
    assert _close(right, (1.0, 0.0, 0.0))


def test_facing_east_puts_south_on_the_right() -> None:
    _forward, right, _up = system_camdir_orientation((0.0, 0.0, -90.0))
    assert _close(right, (0.0, -1.0, 0.0))


def test_up_is_up_when_level() -> None:
    _forward, _right, up = system_camdir_orientation((0.0, 0.0, 0.0))
    assert _close(up, (0.0, 0.0, 1.0))


def test_nose_up_tilts_up_backwards() -> None:
    """Pitched fully up, the camera's up axis lies along the old backwards."""
    _forward, _right, up = system_camdir_orientation((90.0, 0.0, 0.0))
    assert _close(up, (0.0, -1.0, 0.0))


def test_the_basis_stays_orthonormal_everywhere() -> None:
    for camdir in ((0, 0, 0), (30, 45, 0), (-60, 170, 25), (12, -95, -80), (89, 12, 44)):
        f, r, u = system_camdir_orientation(camdir)
        for v in (f, r, u):
            assert math.isclose(math.sqrt(sum(c * c for c in v)), 1.0, abs_tol=1e-9)
        for a, b in ((f, r), (f, u), (r, u)):
            assert abs(sum(x * y for x, y in zip(a, b))) < 1e-9


# ── the mirror this replaces ──────────────────────────────────────────────── #


def test_system_and_surface_conventions_have_different_forward_axes() -> None:
    """Both camera bases are correctly handed, but zero-angle forward differs."""
    from navigation import camdir_orientation

    surface_f, surface_r, _ = camdir_orientation((0.0, 0.0, 0.0))
    system_f, system_r, _ = system_camdir_orientation((0.0, 0.0, 0.0))
    assert _close(surface_f, system_r)
    assert _close(surface_r, tuple(-v for v in system_f))


# ── deflection ────────────────────────────────────────────────────────────── #


def test_a_target_dead_ahead_reads_zero() -> None:
    d = system_deflection((0.0, 0.0, 0.0), (0.0, 0.0, 0.0), (0.0, 1e6, 0.0))
    assert abs(d["yaw_offset_deg"]) < 1e-9
    assert abs(d["pitch_offset_deg"]) < 1e-9
    assert abs(d["total_offset_deg"]) < 1e-9


def test_a_target_to_the_east_of_north_reads_yaw_right() -> None:
    """Facing north with the target due east: 90 degrees to the RIGHT, positive."""
    d = system_deflection((0.0, 0.0, 0.0), (0.0, 0.0, 0.0), (1e6, 0.0, 0.0))
    assert d["yaw_offset_deg"] == pytest.approx(90.0)


def test_a_target_to_the_west_of_north_reads_yaw_left() -> None:
    d = system_deflection((0.0, 0.0, 0.0), (0.0, 0.0, 0.0), (-1e6, 0.0, 0.0))
    assert d["yaw_offset_deg"] == pytest.approx(-90.0)


def test_a_target_above_reads_pitch_up() -> None:
    d = system_deflection((0.0, 0.0, 0.0), (0.0, 0.0, 0.0), (0.0, 1e6, 1e6))
    assert d["pitch_offset_deg"] == pytest.approx(45.0)
    assert abs(d["yaw_offset_deg"]) < 1e-9


def test_turning_toward_a_target_reduces_its_offset() -> None:
    """The property that makes the ring usable: aiming at the thing shrinks the
    bubble's displacement."""
    target = (1e6, 1e6, 0.0)  # north-east of the origin
    far = system_deflection((0.0, 0.0, 0.0), (0.0, 0.0, 0.0), target)
    near = system_deflection((0.0, 0.0, -45.0), (0.0, 0.0, 0.0), target)
    assert far["total_offset_deg"] == pytest.approx(45.0)
    assert near["total_offset_deg"] == pytest.approx(0.0, abs=1e-9)


def test_roll_does_not_move_the_total_offset() -> None:
    """Roll rotates the yaw/pitch split around the screen, never the angle
    between the nose and the target. This holds whichever way the roll sign
    turns out to go, which is why the assumed sign cannot corrupt the geometry."""
    target = (3e5, 1e6, 2e5)
    total = {
        round(system_deflection((0.0, roll, 0.0), (0.0, 0.0, 0.0), target)["total_offset_deg"], 9)
        for roll in (0.0, 30.0, -30.0, 90.0, 180.0)
    }
    assert len(total) == 1


def test_the_screenshot_geometry_reproduces() -> None:
    """2026-07-28, CamDir (0,0,0) at SolarSystem Pos (4333097.2057km,
    -14361738.6551km, 10.9287km), looking at the Nyx star at the origin.

    The game's own readout under the map said 0.00 deg, -73.21 deg, 15.00 Gm,
    and the star appeared LEFT of the crosshair. All three must come out.
    """
    here = (4333097.2057e3, -14361738.6551e3, 10.9287e3)
    star = (0.0, 0.0, 0.0)
    d = system_deflection((0.0, 0.0, 0.0), here, star)

    assert d["distance_m"] / 1e9 == pytest.approx(15.0, abs=0.01)  # 15.00 Gm
    assert d["yaw_offset_deg"] < 0  # the star is to the LEFT, as seen on screen
    assert d["total_offset_deg"] == pytest.approx(16.79, abs=0.05)
    assert abs(d["pitch_offset_deg"]) < 0.01  # we are in the system's plane

    # And the game's own position readout, from the same coordinates.
    az = math.degrees(math.atan2(here[1], here[0]))
    el = math.degrees(math.asin(here[2] / math.dist(here, star)))
    assert az == pytest.approx(-73.21, abs=0.01)
    assert el == pytest.approx(0.00, abs=0.01)
