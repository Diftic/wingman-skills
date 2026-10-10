"""The ring renderer and the overlay's placement, with no window involved.

Everything here runs headless: the renderer produces bytes, and placement is a
pure function of a monitor rectangle. The one thing these tests CANNOT show is
whether the window actually appears over Star Citizen, because that depends on
the game's display mode and on the desktop compositor. That check is a live
one, and the Devlog says so rather than letting a green suite imply it.
"""

from __future__ import annotations

import pytest

import overlay_win32
from ring_overlay import RingOverlay, RingRenderer, state_colour


pytest.importorskip("numpy")
pytest.importorskip("PIL")

import numpy as np  # noqa: E402


_SIZE = 220


@pytest.fixture(scope="module")
def renderer() -> RingRenderer:
    return RingRenderer(_SIZE)


def _pixels(frame: bytes, size: int = _SIZE):
    """Frame bytes back into a (h, w, 4) BGRA array."""
    return np.frombuffer(frame, dtype=np.uint8).reshape(size, size, 4)


# ── colour, ported from the browser ring ──────────────────────────────────── #


def test_dead_ahead_is_green_and_pulses() -> None:
    colour, pulse = state_colour(0.0, 0.0)
    assert colour == (0, 232, 144)
    assert pulse is True


def test_pulse_stops_outside_five_degrees() -> None:
    assert state_colour(6.0, 0.0)[1] is False


def test_colour_is_still_green_at_twenty_degrees() -> None:
    assert state_colour(20.0, 0.0)[0] == (0, 232, 144)


def test_colour_walks_green_to_amber_to_red() -> None:
    mid = state_colour(32.0, 0.0)[0]
    late = state_colour(70.0, 0.0)[0]
    assert (0, 232, 144) != mid != (255, 182, 72)
    assert late[0] > mid[0]  # redder
    assert state_colour(120.0, 0.0)[0] == (255, 77, 94)


def test_offset_combines_both_axes() -> None:
    """A target 30 degrees right and 30 up is further off than either alone."""
    assert state_colour(30.0, 30.0)[0] != state_colour(30.0, 0.0)[0]


# ── geometry ──────────────────────────────────────────────────────────────── #


def test_dead_ahead_puts_the_bubble_in_the_centre(renderer: RingRenderer) -> None:
    x, y = renderer.bubble_centre(0.0, 0.0)
    assert (x, y) == (renderer.centre, renderer.centre)


def test_target_above_puts_the_bubble_above_centre(renderer: RingRenderer) -> None:
    """Screen y grows downward, so a positive pitch must LOWER y."""
    _x, y = renderer.bubble_centre(0.0, 20.0)
    assert y < renderer.centre


def test_target_right_puts_the_bubble_right(renderer: RingRenderer) -> None:
    x, _y = renderer.bubble_centre(20.0, 0.0)
    assert x > renderer.centre


def test_the_bubble_stops_at_the_wall(renderer: RingRenderer) -> None:
    """Past 45 degrees the bubble pins and only the colour keeps moving; it must
    never wander outside the boundary circle and off the instrument."""
    for yaw, pitch in ((45.0, 0.0), (120.0, 0.0), (100.0, 100.0), (-180.0, 40.0)):
        x, y = renderer.bubble_centre(yaw, pitch)
        radius = ((x - renderer.centre) ** 2 + (y - renderer.centre) ** 2) ** 0.5
        assert radius <= renderer.travel + 1e-6


def test_the_bubble_reaches_the_wall_exactly_at_forty_five(renderer: RingRenderer) -> None:
    x, _y = renderer.bubble_centre(45.0, 0.0)
    assert x - renderer.centre == pytest.approx(renderer.travel)


def test_geometry_scales_with_the_configured_size() -> None:
    small, large = RingRenderer(160), RingRenderer(400)
    assert large.r_bubble > small.r_bubble
    assert large.travel > small.travel
    # Proportions are preserved, so the instrument reads the same at any size.
    assert large.travel / large.r_rose == pytest.approx(small.travel / small.r_rose, rel=1e-3)


# ── frames ────────────────────────────────────────────────────────────────── #


def test_a_frame_is_exactly_one_bgra_bitmap(renderer: RingRenderer) -> None:
    assert len(renderer.frame(None)) == _SIZE * _SIZE * 4


def test_every_pixel_is_premultiplied(renderer: RingRenderer) -> None:
    """UpdateLayeredWindow expects premultiplied alpha; unpremultiplied pixels
    show up as bright fringing over dark scenery, which is exactly the artefact
    a colour-keyed overlay would have had."""
    px = _pixels(renderer.frame((10.0, -5.0))).astype(np.int16)
    assert (px[..., :3] <= px[..., 3:4] + 1).all()


def test_corners_are_fully_transparent(renderer: RingRenderer) -> None:
    """The ring is a circle in a square canvas; the corners must let the game
    through completely."""
    px = _pixels(renderer.frame((0.0, 0.0)))
    for y, x in ((0, 0), (0, _SIZE - 1), (_SIZE - 1, 0), (_SIZE - 1, _SIZE - 1)):
        assert px[y, x, 3] == 0


def test_the_no_fix_face_draws_no_bubble(renderer: RingRenderer) -> None:
    """A target with no trustworthy position shows the instrument and no
    direction, rather than a bubble pointing somewhere invented."""
    idle = _pixels(renderer.frame(None)).astype(np.int16)
    live = _pixels(renderer.frame((0.0, 0.0))).astype(np.int16)
    # Bubble green against the rose's blue accent: measured, not guessed. The
    # accent's antialiasing peaks at G=164 with G-R=99, the bubble reaches
    # G=209 with G-R=208, so this threshold sits in the gap between them.
    def _bubble_pixels(px):
        return ((px[..., 1] > 180) & (px[..., 1] - px[..., 2] > 100)).sum()

    assert _bubble_pixels(idle) == 0
    assert _bubble_pixels(live) > 0


def test_a_dead_ahead_fix_draws_a_green_bubble_at_the_centre(renderer: RingRenderer) -> None:
    px = _pixels(renderer.frame((0.0, 0.0))).astype(np.int16)
    c = int(renderer.centre)
    b, g, r, a = px[c, c]
    assert a > 200
    assert g > r and g > b  # the green of an on-course bubble


def test_a_hard_right_target_draws_the_bubble_to_the_right(renderer: RingRenderer) -> None:
    px = _pixels(renderer.frame((40.0, 0.0))).astype(np.int16)
    c = int(renderer.centre)
    offset = int(renderer.travel * 40.0 / 45.0)
    assert px[c, c + offset, 3] > px[c, c - offset, 3]


def test_the_frame_changes_as_the_target_moves(renderer: RingRenderer) -> None:
    assert renderer.frame((0.0, 0.0)) != renderer.frame((30.0, 10.0))


def test_the_on_course_pulse_animates(renderer: RingRenderer) -> None:
    """The glow breathes on a 1.2s period, so the two quarter-phase frames (the
    extremes of the sine, 0.35 and 0.15 alpha) must differ even though the
    bubble has not moved. Half a period apart would be the same brightness."""
    assert renderer.frame((0.0, 0.0), 0.3) != renderer.frame((0.0, 0.0), 0.9)


# ── placement ─────────────────────────────────────────────────────────────── #


def test_the_ring_hangs_from_the_top_centre_of_the_screen(monkeypatch) -> None:
    monkeypatch.setattr(overlay_win32, "get_monitor_rect", lambda index: (0, 0, 5120, 1440))
    overlay = RingOverlay(size=_SIZE, display=1)
    x, y = overlay._placement()
    assert y == 0                       # flush with the top edge
    assert x + _SIZE // 2 == 5120 // 2  # centred horizontally


def test_placement_follows_the_configured_monitor(monkeypatch) -> None:
    """The ring belongs on the screen the game is on, which is the screen the
    skill is already told to capture."""
    monkeypatch.setattr(
        overlay_win32, "get_monitor_rect", lambda index: (5120, -200, 1920, 1080)
    )
    overlay = RingOverlay(size=_SIZE, display=2)
    x, y = overlay._placement()
    assert y == -200
    assert x == 5120 + (1920 - _SIZE) // 2


# ── state, without starting the thread ────────────────────────────────────── #


def test_clearing_drops_the_target() -> None:
    overlay = RingOverlay(size=_SIZE)
    overlay.set_state(True, (10.0, 2.0))
    overlay.clear()
    assert overlay._active is False
    assert overlay._target is None


def test_going_inactive_discards_a_stale_deflection() -> None:
    """Navigation stopping must not leave a last-known bubble behind to be
    shown again the moment a new target appears."""
    overlay = RingOverlay(size=_SIZE)
    overlay.set_state(False, (10.0, 2.0))
    assert overlay._target is None


def test_an_active_target_with_no_fix_stays_visible() -> None:
    overlay = RingOverlay(size=_SIZE)
    overlay.set_state(True, None)
    assert overlay._active is True
    assert overlay._target is None


def test_sizes_are_clamped_to_something_drawable() -> None:
    assert RingRenderer(10).size == 80
    assert RingOverlay(size=10)._size == 80
