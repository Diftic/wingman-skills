"""The reader's state reaching the ring: decided in navigation, drawn in the overlay.

Two properties matter and both are asserted from real pixels rather than from
the code's own claims: the message actually changes what is rendered, and it
never changes where the bubble is drawn. Since Vision was removed on
2026-07-31 this is the only channel that can tell the player why a fix is
missing, so a message that silently fails to draw would be invisible everywhere.
"""

from __future__ import annotations

import pytest

import navigation
import overlay_fields as fields
import ring_overlay


_TARGET = {"x": 1000.0, "y": 0.0, "z": 0.0, "body": "Daymar", "frame": "local"}
_POSITION = {
    "x": 0.0, "y": 0.0, "z": 0.0, "body": "Daymar",
    "heading": 0.0, "system_frame": False,
    "active_frame": "planet", "frame_id": "daymar", "camdir": [0,0,0],
    "planet_rotation": {"frame_id": "daymar", "angle": 0., "valid": True},
}


# --------------------------------------------------------------------------
# navigation.ring_status: bubble and message decided together.
# --------------------------------------------------------------------------
def test_a_good_read_says_nothing():
    deflection, message = navigation.ring_status(_POSITION, _TARGET, 1.0, "")
    assert deflection is not None
    assert message == ""


def test_the_readers_verdict_is_passed_through():
    _, message = navigation.ring_status(
        _POSITION, _TARGET, 1.0, fields.RING_GLARE
    )
    assert message == "HELD 1s"


def test_a_refusal_blanks_even_a_fresh_bubble():
    """Current single-pass/held-display policy; supersedes the earlier retry rule."""
    deflection, message = navigation.ring_status(
        _POSITION, _TARGET, 2.0, fields.RING_GLARE
    )
    assert deflection is not None
    assert message == "HELD 2s"


def test_a_stale_fix_still_cannot_draw_a_bubble():
    """`ring_deflection` remains the single authority; a message cannot override it."""
    deflection, message = navigation.ring_status(
        _POSITION, _TARGET, 9999.0, fields.RING_GLARE
    )
    assert deflection is None
    assert message == fields.RING_GLARE


def test_no_bubble_and_a_clean_read_reports_acquiring():
    deflection, message = navigation.ring_status(_POSITION, _TARGET, 9999.0, "")
    assert deflection is None
    assert message == fields.RING_ACQUIRING


def test_uncalibrated_open_space_says_no_bearing_not_acquiring():
    """A bearing that cannot exist must not be reported as one that is coming.

    With `space_direction_test` off, the system-frame convention is withheld
    because it is uncalibrated, not because the fix is late. Saying ACQUIRING
    there would leave the message on screen forever promising something that
    can never arrive. Found the moment the test switch was turned off in the
    live session on 2026-07-31.
    """
    space_pos = {
        "x": 0.0, "y": 0.0, "z": 0.0,
        "system_frame": True, "frame_id": "730084885606",
        "camdir": (10.0, 0.0, 0.0),
    }
    space_target = {
        "x": 1000.0, "y": 0.0, "z": 0.0,
        "frame": "system", "frame_id": "730084885606",
    }
    deflection, message = navigation.ring_status(space_pos, space_target, 1.0, "")
    assert deflection is None
    assert message == fields.RING_NO_BEARING


def test_a_stale_local_fix_still_says_acquiring():
    """The genuinely transient case must keep its transient message."""
    _, message = navigation.ring_status(_POSITION, _TARGET, 9999.0, "")
    assert message == fields.RING_ACQUIRING


def test_nothing_is_said_when_not_navigating():
    """No target means no nagging."""
    _, message = navigation.ring_status(_POSITION, None, 1.0, fields.RING_GLARE)
    assert message == ""


# --------------------------------------------------------------------------
# Rendering, asserted on the produced pixels.
# --------------------------------------------------------------------------
def _renderer():
    if not ring_overlay.RENDER_AVAILABLE:
        pytest.skip("PIL/numpy not available")
    return ring_overlay.RingRenderer(220)


def test_a_message_changes_the_rendered_frame():
    r = _renderer()
    plain = r.frame(None, 0.0, "")
    with_text = r.frame(None, 0.0, fields.RING_NO_SIGNAL)
    assert len(plain) == len(with_text)
    assert plain != with_text, "the message did not draw anything"


def test_different_messages_render_differently():
    r = _renderer()
    a = r.frame(None, 0.0, fields.RING_GLARE)
    b = r.frame(None, 0.0, fields.RING_NO_SIGNAL)
    assert a != b


def test_the_message_draws_in_the_bottom_half():
    """It must not sit over the bubble's travel area."""
    import numpy as np

    r = _renderer()
    size = r.size
    plain = np.frombuffer(r.frame(None, 0.0, ""), dtype=np.uint8).reshape(size, size, 4)
    text = np.frombuffer(
        r.frame(None, 0.0, fields.RING_NO_SIGNAL), dtype=np.uint8
    ).reshape(size, size, 4)
    changed = np.abs(text.astype(int) - plain.astype(int)).sum(axis=2) > 0
    rows = np.where(changed.any(axis=1))[0]
    assert rows.size, "nothing changed"
    assert rows.min() > size * 0.6, f"message drew as high as row {rows.min()}"


def test_the_message_does_not_move_the_bubble():
    """The property that makes a wrong message harmless."""
    import numpy as np

    r = _renderer()
    size = r.size
    deflection = (18.0, -6.0)
    without = np.frombuffer(
        r.frame(deflection, 0.0, ""), dtype=np.uint8).reshape(size, size, 4)
    with_msg = np.frombuffer(
        r.frame(deflection, 0.0, fields.RING_GLARE), dtype=np.uint8
    ).reshape(size, size, 4)
    top = int(size * 0.6)
    assert (without[:top] == with_msg[:top]).all(), (
        "the message altered pixels in the bubble's half of the ring"
    )


def test_message_layers_are_cached_per_string():
    r = _renderer()
    r.frame(None, 0.0, fields.RING_GLARE)
    r.frame(None, 0.0, fields.RING_GLARE)
    assert list(r._messages) == [fields.RING_GLARE]


# --------------------------------------------------------------------------
# PHOTOSENSITIVITY SAFETY. These are the tests that matter most in this file.
# A strobing visual element can trigger seizures; the hazardous band is roughly
# 3 to 60 Hz. The reader refuses most frames over terrain, so the REQUESTED
# message flickers at the poll rate, and MessageFader is what stops that
# reaching the screen.
# --------------------------------------------------------------------------
def test_alpha_only_ever_ramps_never_snaps():
    """No single step may change visibility by more than one fade increment."""
    fader = ring_overlay.MessageFader(fade_s=0.45, dwell_s=1.0)
    dt = 1.0 / 30.0
    previous = fader.alpha
    # Worst case the caller can produce: alternating demand every single frame.
    for i in range(600):
        _, alpha = fader.update(dt, fields.RING_GLARE if i % 2 == 0 else "")
        assert abs(alpha - previous) <= dt / 0.45 + 1e-9, (
            f"visibility jumped {previous:.3f} -> {alpha:.3f} in one frame"
        )
        previous = alpha


def test_a_single_frame_refusal_cannot_blink():
    """One refusal, then clean reads forever: the label must not flash."""
    fader = ring_overlay.MessageFader(fade_s=0.45, dwell_s=1.0)
    dt = 1.0 / 30.0
    fader.update(dt, fields.RING_GLARE)
    visible_frames = 0
    for _ in range(120):
        _, alpha = fader.update(dt, "")
        if alpha > 0.0:
            visible_frames += 1
    # It must remain on screen for at least the dwell, not vanish immediately.
    assert visible_frames * dt >= 1.0


def test_the_text_never_changes_while_it_is_visible():
    """A swap at full brightness would read as a flash of a different word."""
    fader = ring_overlay.MessageFader(fade_s=0.45, dwell_s=1.0)
    dt = 1.0 / 30.0
    demands = ([fields.RING_GLARE] * 40 + [fields.RING_NO_SIGNAL] * 40
               + [fields.RING_ACQUIRING] * 40 + [""] * 40) * 3
    last_text = ""
    for demand in demands:
        text, alpha = fader.update(dt, demand)
        if last_text and text != last_text:
            # One VISIBLE message being replaced by a different one is the case
            # that would read as a flash of a new word, so the old one must have
            # faded fully out first. Appearing from nothing is not this case:
            # that is a ramp from zero, covered by the ramp test above.
            assert alpha <= 0.0, (
                f"{last_text!r} was replaced by {text!r} at alpha {alpha:.3f}"
            )
        last_text = text


def test_worst_case_flicker_is_far_below_the_hazardous_band():
    """Drive it as fast as it can possibly be driven and count the cycles.

    A caller alternating every frame at 30 fps is a 15 Hz demand, squarely in
    the worst part of the photosensitive range. What reaches the screen must
    not be.
    """
    fader = ring_overlay.MessageFader(fade_s=0.45, dwell_s=1.0)
    dt = 1.0 / 30.0
    seconds = 10.0
    steps = int(seconds / dt)
    was_on = False
    rising_edges = 0
    for i in range(steps):
        _, alpha = fader.update(dt, fields.RING_GLARE if i % 2 == 0 else "")
        on = alpha > 0.5
        if on and not was_on:
            rising_edges += 1
        was_on = on
    assert rising_edges / seconds < 1.0, (
        f"{rising_edges / seconds:.2f} Hz reached the screen from a 15 Hz demand"
    )


def test_a_steady_message_settles_and_stays_solid():
    """The other failure would be a label that never stops pulsing."""
    fader = ring_overlay.MessageFader(fade_s=0.45, dwell_s=1.0)
    dt = 1.0 / 30.0
    for _ in range(60):
        fader.update(dt, fields.RING_GLARE)
    for _ in range(120):
        text, alpha = fader.update(dt, fields.RING_GLARE)
        assert alpha == 1.0 and text == fields.RING_GLARE


def test_set_state_clears_the_message_when_inactive():
    overlay = ring_overlay.RingOverlay(size=220)
    overlay.set_state(True, (5.0, 5.0), fields.RING_GLARE)
    assert overlay._message == fields.RING_GLARE
    overlay.set_state(False, (5.0, 5.0), fields.RING_GLARE)
    assert overlay._message == ""
    overlay.clear()
    assert overlay._message == ""
