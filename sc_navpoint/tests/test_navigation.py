"""Sanity tests for navigation.py (spec section 3: math is unchanged).

navigation.py is docstring-only in this packet, so these lock in the
current bearing/distance behaviour to catch any accidental math drift.
"""

from __future__ import annotations

from navigation import calculate_bearing, format_distance


# ---------------------------------------------------------------------- #
# calculate_bearing
# ---------------------------------------------------------------------- #


def test_bearing_straight_north() -> None:
    # Target due +Z on the X/Z plane, heading 0: dead ahead, bearing 0 (N).
    result = calculate_bearing((0.0, 0.0, 0.0), (0.0, 0.0, 100.0), current_heading=0.0)
    assert result["horizontal_bearing_deg"] == 0.0
    assert result["horizontal_offset_deg"] == 0.0
    assert result["direction_label"] == "N"
    assert result["distance_m"] == 100.0


def test_bearing_offset_positive_for_target_on_right() -> None:
    # Target due +X (east) with heading 0: turn right -> positive offset.
    result = calculate_bearing((0.0, 0.0, 0.0), (100.0, 0.0, 0.0), current_heading=0.0)
    assert result["horizontal_offset_deg"] > 0
    assert result["turn_instruction"].endswith("right")


def test_bearing_offset_negative_for_target_on_left() -> None:
    # Target due -X (west) with heading 0: turn left -> negative offset.
    result = calculate_bearing((0.0, 0.0, 0.0), (-100.0, 0.0, 0.0), current_heading=0.0)
    assert result["horizontal_offset_deg"] < 0
    assert result["turn_instruction"].endswith("left")


def test_bearing_vertical_straight_up() -> None:
    # Target directly overhead (+Y only): vertical angle is +90.
    result = calculate_bearing((0.0, 0.0, 0.0), (0.0, 100.0, 0.0), current_heading=0.0)
    assert result["vertical_angle_deg"] == 90.0


# ---------------------------------------------------------------------- #
# format_distance thresholds
# ---------------------------------------------------------------------- #


def test_format_distance_metres() -> None:
    assert format_distance(0.5) == "500 m"


def test_format_distance_kilometres() -> None:
    assert format_distance(5.0) == "5.0 km"


def test_format_distance_megametres() -> None:
    assert format_distance(5000.0) == "5.0 Mm"


def test_format_distance_gigametres() -> None:
    assert format_distance(2_000_000.0) == "2.00 Gm"
