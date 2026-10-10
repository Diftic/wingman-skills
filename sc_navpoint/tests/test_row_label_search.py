"""Classifying a row by a label that is not at the start of the row.

The overlay block is right-aligned, so every row carries a blank left margin.
A background star inside that margin decodes as a phantom glyph, and the label
then stops being the first thing on the line. Anchoring the label patterns at
position 0 made `kind` come back None for a row whose label was perfectly
readable, and a CamDir row with no kind cannot be cleared by
`overlay_fields.ooc_hypothesis_refuted`, so the whole capture refused. Measured
2026-08-01 at Pyro V L2 on 3 of 15 consecutive frames as the star drifted
through the block.

This is the same failure `overlay_fields._largest_component` was fixed for
earlier the same day, arriving at a third consumer.

PROVENANCE. Every row below is real decoded text. The three P5 L2 rows come
from the 2026-08-01 session that exposed this; the rest are rows the corpus
sweep in `ocr_dev/zone-stacks-2026-08-01.md` recorded as kind None, which is
the defect showing up in five other sessions. The one constructed row is
marked as such, because no capture on disk contains a `Server:` line.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

import overlay_reader as ov


_CAPTURES = Path(__file__).resolve().parent.parent / "ocr_dev" / "captures"
_GLYPHS = Path(__file__).resolve().parent.parent / "overlay_glyphs.npz"


# Real rows, each one classified None by the anchored form. The P5 L2 three are
# from tonight's session; the others carry their source line in the sweep.
PHANTOM_ROWS = [
    ("camdir", "? CamDir: 179   0  133 FOV: 55 Focal: 3.00 FStop: 64.0"),
    ("zone",
     "?        Zone: Root Pos: -4263921.6760km -46989288.1490km 17648.3046km"),
    ("session", "?            Session: b6c492f8-15ff-2744-b991-662795b1edbb"),
    # zone-stacks-2026-08-01.md, red-01, row 0.
    ("camdir", "???          CamDir: 149  26  -?0 F??? ?? Fo?????0.10 FStop: 64.0"),
    # red-01, row 4: a Root line whose own `Pos:` was refused as well.
    ("zone",
     "?               Zone: Root Po?? -4296206.8079km -47014547.2204km 17665"),
    # red-01, row 7.
    ("session",
     "???       ??        ??   Session: f2e0b4?1-52cd-5745???97-078ce9887e5b"),
    # red-01, row 8.
    ("shard", "?        ??        ShardId: pub_e????_12269732_090"),
]

# CONSTRUCTED, not observed. `Server:` appears in no capture on disk, so there
# is no real row to quote; the label still needs the same guarantee as the
# other four.
CONSTRUCTED_SERVER_ROW = ("server", "?        Server: 1.2.3.4")


@pytest.mark.parametrize("kind,text", PHANTOM_ROWS + [CONSTRUCTED_SERVER_ROW])
def test_a_phantom_glyph_does_not_hide_the_label(kind, text):
    assert ov.row_kind(text) == kind, (
        f"a star in the left margin cost this row its {kind} classification"
    )


def test_the_measured_camdir_row_classifies():
    """The exact row that refused 3 of 15 frames at P5 L2, character for character.

    A CamDir row that reaches `overlay_fields` without a kind cannot refute the
    OOC hypothesis, and the capture is then thrown away as unreadable even
    though every digit in it was read.
    """
    text = "? CamDir: 179   0  133 FOV: 55 Focal: 3.00 FStop: 64.0"
    assert ov.row_kind(text) == "camdir"


@pytest.mark.parametrize("kind,text", PHANTOM_ROWS + [CONSTRUCTED_SERVER_ROW])
def test_the_label_is_still_found_without_a_phantom(kind, text):
    """Searching must not cost the ordinary case it generalises."""
    assert ov.row_kind(text.lstrip("? ")) == kind


# --------------------------------------------------------------------- #
# Searching is the more permissive form, so the floor matters more
# --------------------------------------------------------------------- #


NO_LABEL = [
    ("empty", ""),
    # Real rows below the Zone stack, from the sweep. These belong to a second
    # pitch class the reader never fits, so they refuse in every capture.
    ("all refused", "?????????????????????????????????"),
    ("refused with gaps", "?????????? ????? ????????????????"),
    # Real: the label itself lost its colon, so there is nothing left to find.
    ("a label with its colon refused",
     "?               ?  ShardId? pub_euw1b_12269732_090"),
    # Real, red-01 row 6: a telemetry line the skill reads no field from.
    ("telemetry", "?                                               FPS 114.5 [65..135], -"),
    ("a bare coordinate", "Pos: 330.7421km 218.7408km 119.0037km"),
    ("the label's own word without its colon", "CamDir 179 0 133"),
]


@pytest.mark.parametrize("name,text", NO_LABEL)
def test_a_row_with_no_label_stays_unclassified(name, text):
    """A row is still classified by what it contains, not by hope."""
    assert ov.row_kind(text) is None, name


# --------------------------------------------------------------------- #
# The same thing again, from the pixels the phantom actually came out of
# --------------------------------------------------------------------- #


def test_the_p5l2_frame_that_refused_now_classifies_its_camdir_row():
    """The defect from the pixels up, not from a quoted string.

    Every assertion above takes the decoded text on trust. This one decodes
    p5l2/frame_0006.png, one of the 3 frames of 15 where the star sat in the
    left margin, and pins that the phantom is really there and that the row
    still comes back `camdir`. Reading 1 row is enough: the CamDir line is
    row 0, and a shorter read keeps this cheap.
    """
    path = _CAPTURES / "p5l2" / "frame_0006.png"
    if not path.exists() or not _GLYPHS.exists():
        pytest.skip(f"capture corpus not present: {path}")
    from PIL import Image

    frame = np.asarray(Image.open(path).convert("RGB")).astype(np.float64)
    _, _, rows = ov.OverlayReader(_GLYPHS).read(frame, rows=1)

    assert rows[0]["text"].startswith(ov.REFUSED), (
        "the phantom is gone from this frame, so it no longer tests anything"
    )
    assert "CamDir:" in rows[0]["text"]
    assert rows[0]["kind"] == "camdir"
