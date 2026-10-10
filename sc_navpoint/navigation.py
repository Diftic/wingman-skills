"""
navigation.py — Bearing and direction calculations for SC NavPoint
Author: Mallachi
"""

import math


def calculate_bearing(
    from_pos: tuple[float, float, float],
    to_pos: tuple[float, float, float],
    current_heading: float = 0.0,
) -> dict:
    """Calculate navigation bearing from current position to target.

    Star Citizen uses a right-handed coordinate system where X/Z define the
    horizontal plane and Y is the vertical axis. Heading is measured in degrees.

    Args:
        from_pos: Current (x, y, z) position in game units.
        to_pos: Target (x, y, z) position in game units.
        current_heading: Player's current heading in degrees (0 = north).

    Returns:
        Dict with bearing data for the HUD.
    """
    dx = to_pos[0] - from_pos[0]
    dy = to_pos[1] - from_pos[1]
    dz = to_pos[2] - from_pos[2]

    distance = math.sqrt(dx**2 + dy**2 + dz**2)
    distance_km = distance / 1000.0

    # Horizontal bearing: atan2(X, Z) maps to compass degrees
    horizontal_bearing = math.degrees(math.atan2(dx, dz)) % 360

    # Offset from current heading: negative = turn left, positive = turn right
    horizontal_offset = ((horizontal_bearing - current_heading + 180) % 360) - 180

    # Vertical (elevation) angle
    horiz_dist = math.sqrt(dx**2 + dz**2)
    if horiz_dist > 0:
        vertical_angle = math.degrees(math.atan2(dy, horiz_dist))
    else:
        vertical_angle = 90.0 if dy > 0 else -90.0

    return {
        "distance_m": round(distance, 1),
        "distance_km": round(distance_km, 3),
        "horizontal_bearing_deg": round(horizontal_bearing, 1),
        "horizontal_offset_deg": round(horizontal_offset, 1),
        "vertical_angle_deg": round(vertical_angle, 1),
        "direction_label": _bearing_to_label(horizontal_bearing),
        "turn_instruction": _turn_instruction(horizontal_offset),
        "elevation_instruction": _elevation_instruction(vertical_angle),
    }


def _bearing_to_label(bearing: float) -> str:
    """Convert bearing in degrees to a cardinal/intercardinal direction."""
    directions = ["N", "NE", "E", "SE", "S", "SW", "W", "NW"]
    idx = int((bearing + 22.5) / 45) % 8
    return directions[idx]


def _turn_instruction(offset_deg: float) -> str:
    """Generate a turn instruction from heading offset."""
    if abs(offset_deg) <= 5:
        return "Ahead"
    side = "right" if offset_deg > 0 else "left"
    abs_offset = abs(offset_deg)
    if abs_offset > 150:
        return "Turn around"
    if abs_offset > 90:
        return f"Hard {side}"
    if abs_offset > 45:
        return f"Turn {side}"
    return f"Bear {side} {abs_offset:.0f}°"


def _elevation_instruction(angle_deg: float) -> str:
    """Generate an elevation instruction from vertical angle."""
    if abs(angle_deg) <= 5:
        return "Level"
    direction = "up" if angle_deg > 0 else "down"
    return f"Pitch {direction} {abs(angle_deg):.0f}°"


def format_distance(distance_km: float) -> str:
    """Format distance for display."""
    if distance_km >= 1_000_000:
        return f"{distance_km / 1_000_000:.2f} Gm"
    if distance_km >= 1_000:
        return f"{distance_km / 1_000:.1f} Mm"
    if distance_km >= 1:
        return f"{distance_km:.1f} km"
    return f"{distance_km * 1000:.0f} m"
