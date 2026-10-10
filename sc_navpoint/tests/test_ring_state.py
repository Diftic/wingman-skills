"""The three ring states, and the overlay-present discriminator behind them.

These are COSMETIC: a wrong state shows the wrong message and can never change a
payload. The tests that matter are therefore the ones asserting exactly that
isolation, plus the real-pixel checks on both sides of the discriminator, since
a classifier validated on one class only is not validated.

Decision and wording rationale in Devlog 2026-07-31 (night).
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

import overlay_fields as fields
import overlay_reader as ov


_CAPTURES = Path(__file__).resolve().parent.parent / "ocr_dev" / "captures"


def _row(text, kind="zone", trusted=True):
    return {"row": 0, "trusted": trusted, "kind": kind, "text": text}


# --------------------------------------------------------------------------
# State selection.
# --------------------------------------------------------------------------
def test_a_payload_says_nothing():
    """Silence is the correct output when the reader is working."""
    assert fields.ring_state([], {"local_frame": False}, True) == fields.RING_OK


def test_overlay_absent_says_no_signal():
    """The one state the player must act on by typing a console command."""
    rows = [_row("Zone: SolarSystem_1 Pos: 1.0km 2.0km 3.0m")]
    assert fields.ring_state(rows, None, False) == fields.RING_NO_SIGNAL


def test_overlay_present_but_nothing_read_says_glare():
    rows = [_row("????? ?????????", None, trusted=False)]
    assert fields.ring_state(rows, None, True) == fields.RING_GLARE


def test_a_clipped_capture_is_glare_whatever_the_ink_test_says():
    """The precondition rejecting a frame settles it: too bright to decode.

    A blown-out block has plenty of near-white pixels and no row structure, so
    the ink test reads it as "no overlay" and would tell the player to type a
    console command they have already typed. Found by a live smoke test on
    2026-07-31, where a rejected frame reported NO SIGNAL.
    """
    assert fields.ring_state([], None, False, False) == fields.RING_GLARE
    assert fields.ring_state([], None, True, False) == fields.RING_GLARE


def test_position_read_but_unconfirmed_says_acquiring():
    """A missing cross-check is transient, so it must not read as GLARE.

    Telling the player to go look at darker ground when the fix is already
    arriving would send them chasing a problem that resolves itself.
    """
    rows = [_row("Zone: SolarSystem_729968885548 Pos: 1.0km 2.0km 3.0m")]
    assert fields.ring_state(rows, None, True) == fields.RING_ACQUIRING


def test_no_signal_wins_over_everything():
    """If the overlay is not on screen, no other state can be true."""
    rows = [_row("Zone: OOC_Stanton_2b_Daymar Pos: 1.0m 2.0m 3.0m")]
    assert fields.ring_state(rows, None, False) == fields.RING_NO_SIGNAL


def test_states_are_distinct_and_short_enough_for_the_ring():
    """They render at the bottom centre of a 220 px ring."""
    states = [fields.RING_ACQUIRING, fields.RING_GLARE, fields.RING_NO_SIGNAL]
    assert len(set(states)) == 3
    for state in states:
        assert 0 < len(state) <= 12, state


def test_ring_state_cannot_affect_a_payload():
    """The isolation that makes a wrong state harmless."""
    rows = [
        _row("Zone: SolarSystem_729968885548 Pos: 1.0km 2.0km 3.0m"),
        _row("Zone: Root Pos: 1.0km 2.0km 3.0m"),
    ]
    payload = fields.payload_from_rows(rows)
    assert payload is not None
    before = dict(payload)
    for present in (True, False):
        fields.ring_state(rows, payload, present)
    assert payload == before
    assert fields.payload_from_rows(rows) == before


# --------------------------------------------------------------------------
# The discriminator, on real pixels, both classes.
# --------------------------------------------------------------------------
def _full_frames(limit=3):
    from PIL import Image

    out = []
    for folder in sorted(p for p in _CAPTURES.iterdir() if p.is_dir()):
        for shot in sorted(folder.glob("*.png"))[:2]:
            img = np.asarray(Image.open(shot).convert("RGB")).astype(np.float64)
            if img.shape[1] >= 2000:
                out.append(img)
            if len(out) >= limit:
                return out
    return out


def test_overlay_detected_on_real_captures():
    frames = _full_frames()
    if not frames:
        pytest.skip("no full-screen captures on disk")
    assert all(ov.overlay_is_present(f) for f in frames)


def test_overlay_not_detected_with_r_displayinfo_off():
    """The real negative class: 20 frames captured live with the overlay OFF.

    Earlier this was a proxy (scenery cropped from elsewhere on the same
    screens), which could not be guaranteed textless and produced false
    positives that were probably clipped HUD. These frames are the known
    positive for the absent case, so the probe is validated on both sides.
    """
    from PIL import Image

    folder = _CAPTURES / "nosignal-01"
    shots = sorted(folder.glob("frame_*.png"))
    if not shots:
        pytest.skip("overlay-off capture set not present")
    verdicts = [
        ov.overlay_is_present(
            np.asarray(Image.open(s).convert("RGB")).astype(np.float64))
        for s in shots
    ]
    assert not any(verdicts), (
        f"{sum(verdicts)} of {len(verdicts)} overlay-OFF frames were read as "
        "having an overlay"
    )


def test_a_bright_diagonal_streak_is_not_text():
    """The case that broke the first version, kept as a regression.

    A smooth ramp down the rows correlates strongly with itself at EVERY lag,
    so a single-lag autocorrelation called a light streak "periodic" and scored
    it 0.763. Measuring the pitch lag against off-pitch lags cancels it.
    """
    height = ov.BLOCK_TOP + ov.ROW_PITCH * ov.MAX_ROWS + ov.ROW_HEIGHT
    width = ov.BLOCK_WIDTH + ov.RIGHT_MARGIN
    frame = np.zeros((height, width, 3))
    for y in range(height):
        x = int(y * (width - 1) / max(height - 1, 1))
        frame[y, max(0, x - 2):x + 3] = 255.0
    assert ov.overlay_ink_fraction(frame) > ov.INK_PRESENT_MIN
    assert ov.overlay_row_periodicity(frame) < ov.ROW_PERIODICITY_MIN
    assert ov.overlay_is_present(frame) is False


def test_a_blown_sky_alone_is_not_an_overlay():
    """Brightness must not be mistaken for text: this is why ink is not enough.

    A uniformly bright block is over 50 per cent near-white while containing no
    text at all, which is exactly the case that defeats an ink-only rule.
    """
    height = ov.BLOCK_TOP + ov.ROW_PITCH * ov.MAX_ROWS + ov.ROW_HEIGHT
    width = ov.BLOCK_WIDTH + ov.RIGHT_MARGIN
    sky = np.full((height, width, 3), 245.0)
    assert ov.overlay_ink_fraction(sky) > 0.9
    assert ov.overlay_is_present(sky) is False
