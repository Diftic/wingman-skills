"""Decode the overlay over an ARBITRARY background, using unmixing.

DEV TOOL, not a runtime file.

On the black login screen a pixel is `coverage * colour`, so dividing by the
colour recovers coverage exactly. In game that fails: a partially covered pixel
is

    observed = coverage * colour + (1 - coverage) * background

and no division undoes the second term. But the background is essentially
constant across one 8x13 character cell, so for a CANDIDATE template it can be
solved for rather than guessed. Given the template's coverage map T and the
known text colour C, the per-channel background B minimising squared error is

    B = sum((P - C*T) * (1 - T)) / sum((1 - T)^2)

and the residual after substituting it back is the match score. The right
template explains the cell with one flat background; a wrong one cannot.

This also makes the score meaningful as a confidence: a cell whose best and
second-best residuals are close is a cell that should be REFUSED, which is the
behaviour LocalOcrPlan Phase 1 requires.

Usage:

    python decode.py --templates login --label game-bright --rows 16

Credit: Mallachi
"""

from __future__ import annotations

import argparse
import sys
from collections import defaultdict
from pathlib import Path

import numpy as np
from PIL import Image

from templates import (
    BLOCK_TOP,
    CELL_WIDTH,
    COLOURS,
    PHASES,
    PITCH,
    ROWS,
    ROW_HEIGHT,
    ROW_PITCH,
    cells,
    coverage_map,
    fit_origin,
    load_block,
    row_colour,
    row_window,
)


CAPTURE_ROOT = Path(__file__).parent / "captures"

# Measured twice, on two capture paths a fortnight apart: the block's last ink
# column is the screen width minus 7.
RIGHT_MARGIN = 7


def build_templates(label: str) -> dict[tuple[str, int], np.ndarray]:
    """Build coverage templates in 0..1 from a black-background capture."""
    block = load_block(label)
    groups: dict[tuple[str, int], list[np.ndarray]] = defaultdict(list)
    for index, text in ROWS:
        top, bottom = row_window(index)
        _, colour = row_colour(block, top, bottom)
        cover = coverage_map(block, top, bottom, colour)
        origin, _ = fit_origin(cover, text)
        for char, phase, patch in cells(cover, text, origin):
            groups[(char, phase)].append(patch)
    return {
        key: np.clip(np.stack(v).mean(axis=0) / 255.0, 0.0, 1.0)
        for key, v in groups.items()
    }


def match(patch: np.ndarray, template: np.ndarray, colour: np.ndarray) -> float:
    """Residual after solving for the cell's background under this template.

    Args:
        patch: (h, w, 3) observed pixels.
        template: (h, w) coverage in 0..1.
        colour: (3,) text colour.

    Returns:
        Root mean squared residual in 0..255 units. Lower is better.
    """
    transparency = 1.0 - template
    denominator = float((transparency * transparency).sum())
    if denominator <= 1e-9:
        # A template with full coverage everywhere carries no background
        # information; refuse to score it rather than divide by zero.
        return float("inf")
    total = 0.0
    for channel in range(3):
        observed = patch[:, :, channel]
        ink = colour[channel] * template
        background = float(((observed - ink) * transparency).sum() / denominator)
        residual = observed - (ink + background * transparency)
        total += float((residual * residual).sum())
    return float(np.sqrt(total / patch[:, :, 0].size / 3))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--templates", default="login")
    parser.add_argument("--label", required=True)
    parser.add_argument("--rows", type=int, default=16)
    parser.add_argument("--cells", type=int, default=80)
    parser.add_argument("--shot", default="shot_00.png")
    args = parser.parse_args(argv)

    template = build_templates(args.templates)
    known = sorted({c for c, _ in template})
    print(f"{len(template)} templates covering {len(known)} characters: "
          f"{''.join(known)}\n")

    frame = np.asarray(
        Image.open(CAPTURE_ROOT / args.label / args.shot).convert("RGB")
    ).astype(np.float64)
    height, width = frame.shape[:2]
    right = width - RIGHT_MARGIN + 1
    print(f"Frame {width}x{height}, block right edge x={right}\n")

    for row in range(args.rows):
        top = BLOCK_TOP + row * ROW_PITCH
        if top + ROW_HEIGHT > height:
            break
        band = frame[top:top + ROW_HEIGHT]

        best_overall = None
        for colour_name, rgb in COLOURS.items():
            colour = np.asarray(rgb, dtype=np.float64)
            for phase in range(PHASES):
                # `phase` is the ROW's origin offset. Each cell's own sub-pixel
                # phase then ALTERNATES from it with cell parity, because the
                # pitch is 7.5, and a cell must be scored against templates of
                # its own phase. Matching a whole row against one phase scores
                # every other cell against the wrong template set.
                text: list[str] = []
                scores: list[float] = []
                margins: list[float] = []
                for cell in range(args.cells):
                    left = right + phase * 0.5 - (cell + 1) * PITCH
                    x0 = int(np.floor(left))
                    if x0 < 0:
                        break
                    patch = band[:, x0:x0 + CELL_WIDTH]
                    if patch.shape[1] < CELL_WIDTH:
                        break
                    cell_phase = int(round((left - x0) * PHASES)) % PHASES
                    ranked = sorted(
                        (match(patch, proto, colour), c)
                        for (c, p), proto in template.items()
                        if p == cell_phase
                    )
                    text.append(ranked[0][1])
                    scores.append(ranked[0][0])
                    margins.append(ranked[1][0] - ranked[0][0] if len(ranked) > 1 else 0.0)
                if not scores:
                    continue
                mean_score = float(np.mean(scores))
                candidate = (mean_score, colour_name, phase, text, scores, margins)
                if best_overall is None or mean_score < best_overall[0]:
                    best_overall = candidate

        if best_overall is None:
            continue
        mean_score, colour_name, phase, text, scores, margins = best_overall
        rendered = "".join(reversed(text))
        print(f"row {row:2d}  y={top:3d}  {colour_name:6s} phase {phase}  "
              f"residual {mean_score:6.2f}")
        print(f"        {rendered}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
