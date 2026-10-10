"""The three changes made for the 1 Hz target on 2026-07-31.

  1. the Root line is MANDATORY on the local reader's space path
  2. the grab region covers the block only, and must decode identically
  3. the vertical origin is cached, and must not be believed forever

Each test here guards a way the change could be wrong, not the way it is meant
to work. The cache is the dangerous one: a stale origin decodes the gaps
between rows, which looks exactly like an unreadable scene.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

import overlay_fields as fields
import overlay_reader as ov


_CAPTURES = Path(__file__).resolve().parent.parent / "ocr_dev" / "captures"
_GLYPHS = Path(__file__).resolve().parent.parent / "overlay_glyphs.npz"


def _full_frame() -> np.ndarray:
    """A real FULL-SCREEN capture, not a strip. Skips if the corpus is absent."""
    from PIL import Image

    path = _CAPTURES / "game-mid" / "shot_00.png"
    if not path.exists():
        pytest.skip("full-screen capture corpus not present")
    frame = np.asarray(Image.open(path).convert("RGB")).astype(np.float64)
    if frame.shape[1] < 5000:
        pytest.skip("capture is a strip, not a full screen")
    return frame


# --------------------------------------------------------------------------
# 1. The Root line is mandatory on the space path.
# --------------------------------------------------------------------------
def _space_rows(include_root: bool) -> list[dict]:
    rows = [
        {"row": 0, "trusted": True, "kind": "camdir", "text":
         "CamDir: -43 8 -3 FOV: 55 Focal: 0.10 FStop: 64.0"},
        {"row": 1, "trusted": True, "kind": "zone", "text":
         "Zone: SolarSystem_729968885548 Pos: -4296208.3037km 1.0km 2.0m"},
    ]
    if include_root:
        rows.append({"row": 2, "trusted": True, "kind": "zone", "text":
                     "Zone: Root Pos: -4296208.3037km 1.0km 2.0m"})
    return rows


def test_space_payload_requires_the_root_line():
    """Without Root there is no cross-check, so nothing may be emitted."""
    assert fields.payload_from_rows(_space_rows(include_root=False)) is None


def test_space_payload_with_root_carries_it():
    payload = fields.payload_from_rows(_space_rows(include_root=True))
    assert payload is not None
    assert payload["root_pos_raw"] == payload["system_pos_raw"]


def test_local_payload_does_not_require_root():
    """The surface path has its own guards and never used the Root tripwire."""
    rows = [
        {"row": 0, "trusted": True, "kind": "zone", "text":
         "Zone: OOC_Stanton_2b_Daymar Pos: 1.0km 2.0km 3.0m"},
    ]
    payload = fields.payload_from_rows(rows)
    assert payload is not None and payload["local_frame"] is True


# --------------------------------------------------------------------------
# 2. Grabbing the block only must change no pixel the reader looks at.
# --------------------------------------------------------------------------
def test_block_region_geometry():
    monitor = {"left": 0, "top": 0, "width": 5120, "height": 1440}
    region = ov.block_region(monitor)
    assert region["width"] == ov.BLOCK_WIDTH + ov.RIGHT_MARGIN
    # The region's right edge must coincide with the monitor's.
    assert region["left"] + region["width"] == monitor["left"] + monitor["width"]
    assert region["height"] >= ov.BLOCK_TOP + ov.ROW_PITCH * ov.MAX_ROWS


def test_block_grab_equivalence():
    """A block-sized crop must decode identically to the full screen."""
    frame = _full_frame()
    region = ov.block_region(
        {"left": 0, "top": 0, "width": frame.shape[1], "height": frame.shape[0]}
    )
    cropped = frame[
        region["top"]:region["top"] + region["height"],
        region["left"]:region["left"] + region["width"],
    ]
    reader = ov.OverlayReader(_GLYPHS)
    _, _, full_rows = reader.read(frame, 10)
    reader.invalidate_alignment()
    _, _, crop_rows = reader.read(cropped, 10)
    assert [r["text"] for r in full_rows] == [r["text"] for r in crop_rows]
    assert [r["trusted"] for r in full_rows] == [r["trusted"] for r in crop_rows]


# --------------------------------------------------------------------------
# 3. The alignment cache must save work without ever being believed blindly.
# --------------------------------------------------------------------------
def test_alignment_is_cached_between_reads():
    frame = _full_frame()
    reader = ov.OverlayReader(_GLYPHS)
    calls = []
    real = reader.fit_alignment
    reader.fit_alignment = lambda f: (calls.append(1), real(f))[1]

    reader.read(frame, 4)
    reader.read(frame, 4)
    reader.read(frame, 4)
    assert len(calls) == 1, "the origin was refitted on a frame that had not moved"


def test_alignment_is_refitted_after_the_revalidation_window():
    frame = _full_frame()
    reader = ov.OverlayReader(_GLYPHS)
    calls = []
    real = reader.fit_alignment
    reader.fit_alignment = lambda f: (calls.append(1), real(f))[1]

    for _ in range(ov.ALIGNMENT_REVALIDATE + 2):
        reader.read(frame, 1)
    assert len(calls) >= 2, "a cached origin was never revalidated"


def test_alignment_cache_is_keyed_on_frame_shape():
    """A resolution change moves the block, so the cache must not survive it."""
    frame = _full_frame()
    reader = ov.OverlayReader(_GLYPHS)
    reader.read(frame, 1)
    cached = reader._fit_cache
    assert cached is not None and cached[0] == frame.shape

    narrower = frame[:, 100:]
    reader.read(narrower, 1)
    assert reader._fit_cache[0] == narrower.shape


def test_stale_cache_self_heals_when_it_decodes_nothing():
    """A poisoned origin must be dropped rather than reported as an unreadable scene."""
    frame = _full_frame()
    reader = ov.OverlayReader(_GLYPHS)
    _, _, good = reader.read(frame, 6)
    assert any(r["trusted"] for r in good)

    # Poison the cache with an origin that lands between rows.
    reader._fit_cache = (frame.shape, reader._fit_cache[1] + 5)
    reader._fit_uses = 0
    _, _, healed = reader.read(frame, 6)
    assert [r["text"] for r in healed] == [r["text"] for r in good]


def test_read_still_returns_three_values():
    """The refactor must not change the reader's contract with its callers."""
    frame = _full_frame()
    reader = ov.OverlayReader(_GLYPHS)
    result = reader.read(frame, 2)
    assert len(result) == 3
    y0, _, rows = result
    assert isinstance(y0, int) and isinstance(rows, list)
