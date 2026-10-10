"""Self-locating reader for the r_displayinfo overlay, on any background.

DEV TOOL, not a runtime file. This is the prototype of the runtime reader.

THE MODEL, all of it measured (see LocalOcrPlan.md Phase 1):

    observed = G * colour + H * background

  G  glyph coverage, measured on a black backdrop where `H * background`
     vanishes. Exact: every instance of a character is bit-identical.
  H  what the background still transmits after the drop shadow. Derived from G
     as `1 - dilate_down_right(G)`, which reproduces the measured H to 0.068
     against a measurement noise floor of 0.046. The shadow is the glyph OR'd
     with itself shifted right, down, and down-right.

  background is UNKNOWN and solved per cell per channel by least squares, which
  is what makes the reader background-agnostic:

      B = sum((observed - G * colour) * H) / sum(H * H)

Geometry, all measured: character pitch exactly 7.5 px, row pitch exactly 13,
glyph body 8 px tall, block right-aligned with its last ink column at screen
width minus 7. A line's left edge is snapped to a whole pixel and characters
then advance by 7.5, so every glyph sits at sub-pixel phase 0.0 or 0.5 and the
phase ALTERNATES cell to cell. Cells are 8 px wide on a 7.5 px pitch and the
shadow reaches 1 px past its glyph, so the outer column each side carries the
NEIGHBOUR's ink and is masked out of every comparison.

Rows are identified by their LABEL, never by row index: which lines appear
changes with context (in a base, on foot, in a ship, seated), though the
spacing never does.

Usage:

    python reader.py --label game-mid
    python reader.py --label game-mid --unknown     # glyphs it cannot name

Credit: Mallachi
"""

from __future__ import annotations

import argparse
import re
import sys
from collections import defaultdict
from pathlib import Path

import numpy as np
from PIL import Image

from decode import build_templates
from templates import CELL_WIDTH, COLOURS, PHASES, PITCH, ROW_HEIGHT, ROW_PITCH


CAPTURE_ROOT = Path(__file__).parent / "captures"

RIGHT_MARGIN = 7
MASK = 1
MAX_ROWS = 20

# Confidence floor, CALIBRATED not chosen. Over 359 known-correct cells the
# worst residual was 12.69 (p99 12.47) and the smallest margin 13.69; over 560
# known-bad cells the median residual was 48.18 and the median margin 4.39.
# The thresholds sit in that gap with headroom on the correct side, because the
# cost of refusing a readable cell is a Vision fallback, while the cost of
# accepting an unreadable one is a waypoint in the wrong place.
REFUSE_COST = 15.0
REFUSE_MARGIN = 8.0
REFUSED = "?"

# Lines the skill cares about, recognised by their label.
#
# MIRRORS `overlay_reader.LABELS` and must keep mirroring it. This module is the
# dev prototype that `harvest.py`, `learn.py` and `measure.py` import, so a
# divergence here means the tools that MEASURE the reader are measuring a
# different classifier than the one that ships, which is how a confident wrong
# number gets recorded. Aligned 2026-08-01 evening, when the shipping reader
# stopped anchoring; before that this copy still carried `^` anchors and had
# `camdir` first.
#
# Both properties are load-bearing, see the fuller reasoning in
# `overlay_reader.py`:
#   - patterns are UNANCHORED, because the block is right-aligned and a star in
#     the blank left margin decodes as a phantom glyph that defeats a `^` match.
#   - `zone` sorts FIRST, because it is the only kind that does not clear
#     `overlay_fields.ooc_hypothesis_refuted`, so the sole gate-blocking label
#     must win any row carrying two labels.
LABELS: list[tuple[str, str]] = [
    ("zone", r"Zone:"),
    ("camdir", r"CamDir:"),
    ("session", r"Session:"),
    ("shard", r"ShardId:"),
    ("server", r"Server:"),
]


def shift(array: np.ndarray, dy: int, dx: int) -> np.ndarray:
    """Shift a 2-D array, filling with zeros."""
    out = np.zeros_like(array)
    height, width = array.shape
    ys = slice(max(dy, 0), height + min(dy, 0))
    yd = slice(max(-dy, 0), height + min(-dy, 0))
    xs = slice(max(dx, 0), width + min(dx, 0))
    xd = slice(max(-dx, 0), width + min(-dx, 0))
    out[ys, xs] = array[yd, xd]
    return out


def transmission(glyph: np.ndarray) -> np.ndarray:
    """H, the background's remaining visibility after the drop shadow."""
    shadow = np.max(
        np.stack([shift(glyph, dy, dx) for dy in (0, 1) for dx in (0, 1)]), axis=0
    )
    return 1.0 - np.clip(shadow, 0.0, 1.0)


def match(patch: np.ndarray, glyph: np.ndarray, trans: np.ndarray,
          colour: np.ndarray) -> float:
    """Residual after solving this cell's background under a candidate glyph.

    Args:
        patch: (h, w, 3) observed pixels, outer columns already masked off.
        glyph: (h, w) coverage in 0..1.
        trans: (h, w) background transmission in 0..1.
        colour: (3,) text colour.

    Returns:
        Root mean squared residual in 0..255 units; lower is better.
    """
    denominator = float((trans * trans).sum())
    if denominator <= 1e-9:
        return float("inf")
    total = 0.0
    for channel in range(3):
        observed = patch[:, :, channel]
        ink = colour[channel] * glyph
        background = float(((observed - ink) * trans).sum() / denominator)
        background = min(max(background, 0.0), 255.0)
        residual = observed - (ink + background * trans)
        total += float((residual * residual).sum())
    return float(np.sqrt(total / (patch[:, :, 0].size * 3)))


class Reader:
    """Decodes the overlay from a full-screen RGB frame."""

    def __init__(self, template_label: str = "login",
                 glyph_file: str | None = None) -> None:
        if glyph_file:
            data = np.load(Path(__file__).parent / glyph_file)
            self.glyph = {
                (k.split("|")[0], int(k.split("|")[1])): data[k] for k in data.files
            }
        else:
            self.glyph = build_templates(template_label)
        # A blank cell is a real outcome, not the least-bad glyph. Modelling it
        # as zero coverage and full transmission lets the SAME least-squares fit
        # explain it as pure background, on any backdrop.
        for phase in range(PHASES):
            self.glyph.setdefault(
                (" ", phase), np.zeros((ROW_HEIGHT, CELL_WIDTH), dtype=np.float64)
            )
        self.trans = {key: transmission(g) for key, g in self.glyph.items()}

    def cell_boxes(self, right: float, offset: float, count: int):
        """Yield (x0, phase) for cells counted leftward from the right edge."""
        for cell in range(count):
            left = right + offset - (cell + 1) * PITCH
            x0 = int(np.floor(left))
            if x0 < 0:
                return
            yield x0, int(round((left - x0) * PHASES)) % PHASES

    def decode_row(self, band: np.ndarray, right: float, offset: float,
                   colour: np.ndarray, count: int):
        """Decode one text row; returns (text, mean residual, per-cell margin)."""
        chars: list[str] = []
        costs: list[float] = []
        margins: list[float] = []
        for x0, phase in self.cell_boxes(right, offset, count):
            patch = band[:, x0:x0 + CELL_WIDTH]
            if patch.shape[1] < CELL_WIDTH or patch.shape[0] < ROW_HEIGHT:
                break
            core = patch[:, MASK:CELL_WIDTH - MASK]
            ranked = sorted(
                (match(core, g[:, MASK:CELL_WIDTH - MASK],
                       self.trans[(c, p)][:, MASK:CELL_WIDTH - MASK], colour), c)
                for (c, p), g in self.glyph.items()
                if p == phase
            )
            cost = ranked[0][0]
            margin = ranked[1][0] - cost if len(ranked) > 1 else 0.0
            # Refuse rather than guess. Every confabulation incident in this
            # skill's history is a reader emitting a digit it did not have.
            if cost > REFUSE_COST or margin < REFUSE_MARGIN:
                chars.append(REFUSED)
            else:
                chars.append(ranked[0][1])
            costs.append(cost)
            margins.append(margin)
        if not costs:
            return "", float("inf"), []
        return "".join(reversed(chars)), float(np.mean(costs)), margins

    def fit_alignment(self, frame: np.ndarray) -> tuple[int, float, str]:
        """Find the block's vertical origin, sub-pixel offset and text colour.

        Fitted, never assumed: the vertical origin is not identical between
        captures, and a wrong sub-pixel offset silently halves accuracy.
        """
        width = frame.shape[1]
        right = width - RIGHT_MARGIN + 1
        best = (float("inf"), 0, 0.0, "white")
        for y0 in range(2, 14):
            band = frame[y0:y0 + ROW_HEIGHT]
            if band.shape[0] < ROW_HEIGHT:
                continue
            for offset in (0.0, 0.5):
                for name, rgb in COLOURS.items():
                    colour = np.asarray(rgb, dtype=np.float64)
                    _, cost, _ = self.decode_row(band, right, offset, colour, 40)
                    if cost < best[0]:
                        best = (cost, y0, offset, name)
        return best[1], best[2], best[3]

    def read(self, frame: np.ndarray, rows: int = MAX_ROWS):
        """Decode the whole block. Returns a list of per-row dicts."""
        width = frame.shape[1]
        right = width - RIGHT_MARGIN + 1
        y0, offset, _ = self.fit_alignment(frame)
        out = []
        for index in range(rows):
            top = y0 + index * ROW_PITCH
            band = frame[top:top + ROW_HEIGHT]
            if band.shape[0] < ROW_HEIGHT:
                break
            # Offset is fitted PER ROW, not once for the block. A line's
            # sub-pixel phase follows the parity of its own character count, so
            # rows of different lengths sit on different offsets; applying one
            # row's offset to the whole block decodes every mismatched row to
            # garbage while leaving the rest looking fine.
            best = None
            for row_offset in (0.0, 0.5):
                for name, rgb in COLOURS.items():
                    colour = np.asarray(rgb, dtype=np.float64)
                    text, cost, margins = self.decode_row(
                        band, right, row_offset, colour, 80
                    )
                    if best is None or cost < best[1]:
                        best = (text, cost, margins, name, row_offset)
            text, cost, margins, name, row_offset = best
            stripped = text.strip(" _.-")
            kind = next(
                (k for k, pattern in LABELS if re.search(pattern, stripped)), None
            )
            # A row is trusted only if EVERY cell in it was read. One refused
            # digit inside a coordinate makes the whole coordinate unusable, so
            # this fails closed at row level rather than emitting a partial
            # number that looks complete.
            refused = text.count(REFUSED)
            out.append({
                "row": index, "y": top, "colour": name, "cost": cost,
                "offset": row_offset, "refused": refused,
                "trusted": refused == 0,
                "text": stripped, "kind": kind,
                "margin": float(np.median(margins)) if margins else 0.0,
            })
        return y0, offset, out


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--label", default="")
    parser.add_argument("--templates", default="login")
    parser.add_argument("--glyphs", default=None, help="npz template set")
    parser.add_argument("--shot", default="shot_00.png")
    parser.add_argument("--path", default=None, help="read an arbitrary image")
    parser.add_argument("--rows", type=int, default=MAX_ROWS)
    args = parser.parse_args(argv)

    source = (
        Path(args.path) if args.path
        else CAPTURE_ROOT / args.label / args.shot
    )
    frame = np.asarray(Image.open(source).convert("RGB")).astype(np.float64)
    print(f"source: {source}  {frame.shape[1]}x{frame.shape[0]}")
    reader = Reader(args.templates, args.glyphs)
    print(f"{len(reader.glyph)} templates, "
          f"{len({c for c, _ in reader.glyph})} characters\n")
    y0, offset, rows = reader.read(frame, args.rows)
    print(f"Fitted alignment: y origin {y0}, sub-pixel offset {offset}\n")
    for row in rows:
        tag = f"[{row['kind']}]" if row["kind"] else "     "
        state = "OK     " if row["trusted"] else f"REFUSE({row['refused']:2d})"
        print(f"row {row['row']:2d} {state} {row['colour']:6s} "
              f"cost {row['cost']:5.1f} {tag} {row['text']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
