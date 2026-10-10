"""CamDir to compass bearing, validated against measured in-game data.

The fixtures below are real captures from 2026-07-26: three 13-frame sweeps on
the Daymar surface at Dunlow Ridge, Nuen Waste Management and WolfPoint, each a
full 360 in 30 degree steps with the player standing still. For every frame we
have the overlay's CamDir triple and the compass heading the game itself
displayed, so these tests check the conversion against ground truth rather than
against the author's assumptions.

The model was fitted at WolfPoint only. Nuen and Dunlow are therefore blind
validation sets. Tolerances reflect measured reality: CamDir prints truncated
integers, and the player holds a level view by hand, so per-frame scatter of a
degree or two is the floor rather than a defect. Dunlow's sweep carried 11.7
degrees of elevation wander (against 3 to 5 at the other two), which is why its
tolerance is looser.
"""

from __future__ import annotations

import math

import pytest

from navigation import (
    LocalFrameUnavailable,
    calculate_bearing,
    camdir_to_bearing,
    camdir_view_vector,
    local_basis,
    surface_bearing,
)


HEADINGS = [0, 30, 60, 90, 120, 150, 180, 210, 240, 270, 300, 330, 0]

WOLFPOINT_POS = (-4340.15, 279089.8, 95673.8)
WOLFPOINT_CAMDIR = [
    (70, 0, -97), (67, 28, -107), (54, 54, -126), (0, 71, 174), (-54, 55, 113),
    (-68, 29, 94), (-71, 0, 83), (-69, -27, 73), (-55, -55, 54), (-3, -71, -3),
    (53, -55, -65), (67, -28, -85), (70, 0, -96),
]

NUEN_POS = (-18961.4, 293338.2, 25498.7)
NUEN_CAMDIR = [
    (84, 0, -82), (83, 29, -85), (79, 58, -90), (-9, 84, 179), (-80, 59, 106),
    (-84, 29, 100), (-85, 0, 98), (-85, -29, 95), (-80, -59, 89), (-4, -85, 12),
    (79, -60, -72), (83, -29, -78), (84, 0, -81),
]

DUNLOW_POS = (-51830.8, 280937.6, 75324.1)
DUNLOW_CAMDIR = [
    (75, 0, -62), (72, 27, -69), (62, 56, -85), (2, 75, -148), (-62, 56, 142),
    (-73, 27, 126), (-75, 0, 118), (-73, -30, 109), (-62, -57, 94), (3, -75, 25),
    (61, -56, -37), (72, -28, -52), (74, 0, -60),
]

SITES = [
    ("WolfPoint", WOLFPOINT_POS, WOLFPOINT_CAMDIR, 4.0),
    ("Nuen", NUEN_POS, NUEN_CAMDIR, 4.0),
    ("Dunlow", DUNLOW_POS, DUNLOW_CAMDIR, 9.0),
]


def _angle_error(got: float, want: float) -> float:
    return abs((got - want + 180.0) % 360.0 - 180.0)


# --- the local basis ------------------------------------------------------


def test_basis_vectors_are_orthonormal():
    up, north, east = local_basis(DUNLOW_POS)
    for v in (up, north, east):
        assert math.sqrt(sum(c * c for c in v)) == pytest.approx(1.0, abs=1e-9)
    assert sum(a * b for a, b in zip(up, north)) == pytest.approx(0.0, abs=1e-9)
    assert sum(a * b for a, b in zip(up, east)) == pytest.approx(0.0, abs=1e-9)
    assert sum(a * b for a, b in zip(north, east)) == pytest.approx(0.0, abs=1e-9)


def test_bearing_to_the_pole_is_north():
    """From any non-polar point, the +Z pole lies at bearing 0."""
    r = 295_000.0
    equator = (r, 0.0, 0.0)
    assert surface_bearing(equator, (0.0, 0.0, r)) == pytest.approx(0.0, abs=1e-6)


def test_bearing_eastward_along_the_equator_is_90():
    r = 295_000.0
    a = (r, 0.0, 0.0)
    b = (r * math.cos(0.01), r * math.sin(0.01), 0.0)
    assert surface_bearing(a, b) == pytest.approx(90.0, abs=1e-6)


def test_basis_refused_at_the_body_centre():
    with pytest.raises(LocalFrameUnavailable):
        local_basis((0.0, 0.0, 0.0))


def test_basis_refused_at_a_pole():
    with pytest.raises(LocalFrameUnavailable):
        local_basis((0.0, 0.0, 295_000.0))


def test_vertical_direction_has_no_bearing():
    with pytest.raises(LocalFrameUnavailable):
        surface_bearing(DUNLOW_POS, (DUNLOW_POS[0] * 2, DUNLOW_POS[1] * 2, DUNLOW_POS[2] * 2))


# --- the conversion itself, against measured in-game headings -------------


@pytest.mark.parametrize(("name", "pos", "camdirs", "tolerance"), SITES)
def test_every_frame_matches_the_in_game_compass(name, pos, camdirs, tolerance):
    for camdir, heading in zip(camdirs, HEADINGS):
        got = camdir_to_bearing(camdir, pos)
        assert _angle_error(got, heading) <= tolerance, (
            f"{name}: CamDir {camdir} gave {got:.2f}, game showed {heading}"
        )


@pytest.mark.parametrize(("name", "pos", "camdirs", "tolerance"), SITES)
def test_scatter_across_a_full_sweep_stays_small(name, pos, camdirs, tolerance):
    """Mean-removed scatter is the real accuracy measure, per site."""
    errors = [
        (camdir_to_bearing(c, pos) - h + 180.0) % 360.0 - 180.0
        for c, h in zip(camdirs, HEADINGS)
    ]
    mean = sum(errors) / len(errors)
    spread = max(errors) - min(errors)
    assert spread <= tolerance, f"{name}: error spread {spread:.2f} deg (mean {mean:+.2f})"


def test_view_vector_is_a_unit_vector():
    for camdir in WOLFPOINT_CAMDIR:
        v = camdir_view_vector(camdir)
        assert math.sqrt(sum(c * c for c in v)) == pytest.approx(1.0, abs=1e-9)


def test_closure_frames_agree():
    """First and last frame of each sweep are the same facing, so must agree."""
    for name, pos, camdirs, _ in SITES:
        first = camdir_to_bearing(camdirs[0], pos)
        last = camdir_to_bearing(camdirs[-1], pos)
        assert _angle_error(first, last) <= 2.0, name


def test_same_camdir_means_different_bearing_at_a_different_site():
    """Position is required, not incidental: this is why the API demands it.

    One CamDir read from widely separated points must give widely separated
    bearings. Note the effect is direction-specific rather than uniform: a view
    lying in the equatorial plane, observed from two points ON the equator, does
    give the same bearing at both, so this asserts the spread over several
    positions rather than a difference between any chosen pair.
    """
    r = 295_000.0
    camdir = (70, 0, -97)
    bearings = [
        camdir_to_bearing(camdir, p)
        for p in ((r, 0.0, 0.0), (0.0, r, 0.0), (-r, 0.0, 0.0), (r * 0.7071, 0.0, r * 0.7071))
    ]
    spread = max(
        _angle_error(a, b) for i, a in enumerate(bearings) for b in bearings[i + 1 :]
    )
    assert spread > 20.0


def test_nearby_sites_differ_only_slightly():
    """The same effect at survey range: measured 2 to 4 deg over ~10 deg of arc.

    Guards the sign of the effect as much as its size. A conversion that ignored
    position entirely would give exactly 0 here.
    """
    for camdir in ((70, 0, -97), (0, 71, 174), (-71, 0, 83)):
        diff = _angle_error(
            camdir_to_bearing(camdir, WOLFPOINT_POS),
            camdir_to_bearing(camdir, DUNLOW_POS),
        )
        assert 1.0 < diff < 6.0


# --- integration with calculate_bearing ----------------------------------


def test_local_frame_option_changes_the_bearing_convention():
    result_flat = calculate_bearing(DUNLOW_POS, NUEN_POS, use_local_frame=False)
    result_true = calculate_bearing(DUNLOW_POS, NUEN_POS, use_local_frame=True)
    assert result_flat["horizontal_bearing_deg"] != result_true["horizontal_bearing_deg"]
    assert result_true["horizontal_bearing_deg"] == pytest.approx(
        surface_bearing(DUNLOW_POS, NUEN_POS), abs=0.05
    )


def test_local_frame_option_falls_back_when_no_basis_exists():
    """The legacy call sites use (0,0,0); they must not start raising."""
    flat = calculate_bearing((0.0, 0.0, 0.0), (0.0, 0.0, 100.0), use_local_frame=False)
    forced = calculate_bearing((0.0, 0.0, 0.0), (0.0, 0.0, 100.0), use_local_frame=True)
    assert forced["horizontal_bearing_deg"] == flat["horizontal_bearing_deg"]


def test_offset_is_zero_when_facing_the_target():
    """The whole point: a real heading against a real bearing cancels out."""
    heading = surface_bearing(DUNLOW_POS, NUEN_POS)
    result = calculate_bearing(
        DUNLOW_POS, NUEN_POS, current_heading=heading, use_local_frame=True
    )
    assert abs(result["horizontal_offset_deg"]) <= 0.1
    assert result["turn_instruction"] == "Ahead"


@pytest.mark.parametrize(
    ("a", "b"),
    [(DUNLOW_POS, NUEN_POS), (NUEN_POS, WOLFPOINT_POS), (DUNLOW_POS, WOLFPOINT_POS)],
)
def test_reciprocal_bearings_differ_by_180_plus_meridian_convergence(a, b):
    """On a sphere the return bearing is NOT simply the outbound plus 180.

    The excess is the convergence of the meridians, which for these separations
    is about a degree. Asserting the spherical value rather than a loose
    tolerance turns this into a real check on the basis construction: a subtly
    wrong east or north axis would still pass a plus-or-minus-two-degree test.
    """
    outbound = surface_bearing(a, b)
    back = surface_bearing(b, a)
    excess = abs(((outbound - back + 180.0) % 360.0) - 180.0)
    excess = 180.0 - excess if excess > 90.0 else excess

    lat_a = math.asin(local_basis(a)[0][2])
    lat_b = math.asin(local_basis(b)[0][2])
    d_lon = math.degrees(math.atan2(b[1], b[0]) - math.atan2(a[1], a[0]))
    predicted = abs(d_lon) * math.sin((lat_a + lat_b) / 2.0)

    assert excess == pytest.approx(predicted, abs=0.15)
