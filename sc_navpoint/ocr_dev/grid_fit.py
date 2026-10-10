"""Re-derive the character grid from a lossless capture.

DEV TOOL, not a runtime file.

The July fit gave pitch 7.496 px from JPEG screenshots, and noted that 7.510
is wrong in a way that hides: over a 76-character line the 0.014 px error
accumulates past a whole pixel and shreds template matching while every
individual glyph still looks fine. That constant is load-bearing, so it is
re-derived here on lossless data by an independent objective.

The objective is deliberately NOT "minimise ink at the cell boundary", because
that presumes where the glyph sits inside its cell. Instead it folds every ink
column into cell coordinates modulo the candidate pitch and asks how SHARP the
folded profile is. The true pitch stacks every glyph on top of itself and
leaves the inter-character gap empty; a wrong pitch smears ink across the whole
cell. That makes the answer independent of glyph width.

Usage:

    python grid_fit.py --label login --region 4200,0,5120,260

Credit: Mallachi
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np
from PIL import Image


CAPTURE_ROOT = Path(__file__).parent / "captures"


def load_block(label: str, region: str, threshold: int) -> tuple[np.ndarray, int, int]:
    """Load shot_00 and return (block luma, absolute top, absolute left)."""
    path = CAPTURE_ROOT / label / "shot_00.png"
    frame = np.asarray(Image.open(path).convert("RGB"))
    height, width = frame.shape[:2]
    x0, y0, x1, y1 = (int(v) for v in region.split(","))
    x0, y0 = max(x0, 0), max(y0, 0)
    x1, y1 = min(x1, width), min(y1, height)
    search = frame[y0:y1, x0:x1]
    lit = search.max(axis=2) > threshold
    rows = np.flatnonzero(lit.any(axis=1))
    cols = np.flatnonzero(lit.any(axis=0))
    top, bottom = y0 + int(rows[0]), y0 + int(rows[-1]) + 1
    left, right = x0 + int(cols[0]), x0 + int(cols[-1]) + 1
    return frame[top:bottom, left:right].max(axis=2).astype(np.float64), top, left


def row_bands(luma: np.ndarray, threshold: int) -> list[tuple[int, int]]:
    """Split the block into bands of consecutive rows that carry ink."""
    has = luma.max(axis=1) > threshold
    bands: list[tuple[int, int]] = []
    start: int | None = None
    for y, flag in enumerate(has):
        if flag and start is None:
            start = y
        elif not flag and start is not None:
            bands.append((start, y))
            start = None
    if start is not None:
        bands.append((start, len(has)))
    return bands


def fold(profile: np.ndarray, right_edge: float, pitch: float, bins: int) -> np.ndarray:
    """Fold the column ink profile into a single cell at the candidate pitch."""
    columns = np.arange(len(profile))
    # Measure leftward from the right edge, since the text is right-aligned and
    # error must not be allowed to accumulate away from the anchor.
    coordinate = np.mod((right_edge - columns) / pitch, 1.0)
    index = np.minimum((coordinate * bins).astype(int), bins - 1)
    return np.bincount(index, weights=profile, minlength=bins)


def sharpness(
    profile: np.ndarray, right_edge: float, pitch: float, bins: int, window: float
) -> float:
    """How concentrated the ink is once folded into one cell.

    Args:
        profile: Per-column ink totals.
        right_edge: Column index just past the last ink column.
        pitch: Candidate character pitch in pixels.
        bins: Resolution of the folded histogram.
        window: Width of the search window as a fraction of the cell. This must
            approximate the real inter-character gap: too wide and glyph ink
            swamps the empty run, which flattens the objective and lets the fit
            wander.

    Returns:
        Fraction of total ink falling in the emptiest contiguous window.
        LOWER is better: at the true pitch the gap between characters lines up
        with itself and holds almost nothing.
    """
    folded = fold(profile, right_edge, pitch, bins)
    total = folded.sum()
    if total <= 0:
        return 1.0
    span = max(int(bins * window), 1)
    rolled = np.concatenate([folded, folded])
    windows = np.array([rolled[i:i + span].sum() for i in range(bins)])
    return float(windows.min() / total)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--label", required=True)
    parser.add_argument("--region", required=True)
    parser.add_argument("--threshold", type=int, default=24)
    parser.add_argument("--bins", type=int, default=120)
    parser.add_argument("--pitch-lo", type=float, default=7.0)
    parser.add_argument("--pitch-hi", type=float, default=8.0)
    parser.add_argument("--pitch-step", type=float, default=0.0005)
    parser.add_argument("--window", type=float, default=0.25,
                        help="gap search window as a fraction of the cell")
    args = parser.parse_args(argv)

    luma, top, left = load_block(args.label, args.region, args.threshold)
    height, width = luma.shape
    print(f"Block {width}x{height} at x={left}, y={top}")
    bands = row_bands(luma, args.threshold)
    print(f"{len(bands)} text rows\n")

    candidates = np.arange(args.pitch_lo, args.pitch_hi, args.pitch_step)

    def fit(profile: np.ndarray) -> tuple[float, float]:
        scores = [
            sharpness(profile, width, p, args.bins, args.window)
            for p in candidates
        ]
        best = int(np.argmin(scores))
        return float(candidates[best]), float(scores[best])

    whole = luma.sum(axis=0)
    best_pitch, best_score = fit(whole)
    print(f"ALL ROWS TOGETHER: pitch {best_pitch:.4f} px  (emptiest half holds "
          f"{best_score * 100:.2f}% of ink)\n")

    print("Per row, fitted independently:")
    print("  row   y-range     pitch    best-gap%   gap%@global")
    per_row: list[float] = []
    for index, (band_top, band_bottom) in enumerate(bands):
        profile = luma[band_top:band_bottom].sum(axis=0)
        pitch, score = fit(profile)
        at_global = sharpness(profile, width, best_pitch, args.bins, args.window)
        per_row.append(pitch)
        print(f"  {index:3d}  {top + band_top:4d}-{top + band_bottom:<4d}  "
              f"{pitch:7.4f}   {score * 100:8.2f}   {at_global * 100:8.2f}")
    spread = float(np.max(per_row) - np.min(per_row))
    print(f"\n  spread across rows: {spread:.4f} px "
          f"(median {float(np.median(per_row)):.4f})")

    # Phase: where the empty gap sits inside the cell, at the chosen pitch.
    folded = fold(whole, width, best_pitch, args.bins)
    folded_px = folded / folded.sum() * 100.0
    print(f"\nFolded ink profile at pitch {best_pitch:.4f}, measured leftward "
          f"from the right edge (x={left + width}):")
    for i in range(args.bins):
        lo = i / args.bins * best_pitch
        bar = "#" * int(folded_px[i] * 8)
        if folded_px[i] > 0.01 or bar:
            print(f"  {lo:5.2f} px: {folded_px[i]:5.2f}% {bar}")
    empty = folded_px < 0.01
    if empty.any():
        runs = np.flatnonzero(empty)
        print(f"\n  bins with effectively zero ink: {len(runs)} of {args.bins} "
              f"-> gap spans about "
              f"{runs.min() / args.bins * best_pitch:.2f} to "
              f"{runs.max() / args.bins * best_pitch:.2f} px from a cell's right edge")
    return 0


if __name__ == "__main__":
    sys.exit(main())
