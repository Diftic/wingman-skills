"""Label glyph cells from a transcribed capture, and pin the grid from labels.

DEV TOOL, not a runtime file.

Uses the labelling method established in July: every overlay line is
right-aligned, so cell k counting from the right holds character
`text[len(text) - 1 - k]`. One transcribed frame therefore yields hundreds of
labelled glyphs with no hand-labelling by eye, which is the step most likely to
introduce silent errors.

Two things happen here that the ink-concentration fit could not do:

  1. THE TRANSCRIPTION IS CHECKED, not trusted. A line's predicted ink span is
     compared against its measured span. In July this check caught a real
     two-character error in a hand transcription, so it runs before anything
     downstream consumes the labels.
  2. THE PITCH IS FITTED FROM LABELS. For a fixed character, ink starts at a
     fixed offset inside its cell, so `ink_start = A - pitch * (k + 1)` is
     linear in the cell index. Least squares over every instance of one
     character gives the pitch over a long baseline, independent of the
     glyph-shape contamination that spoils a naive gap measurement.

Usage:

    python label_cells.py --label login

Credit: Mallachi
"""

from __future__ import annotations

import argparse
import sys
from collections import defaultdict
from pathlib import Path

import numpy as np
from PIL import Image


CAPTURE_ROOT = Path(__file__).parent / "captures"

# Block origin measured by analyze_black.py on this capture set.
BLOCK_TOP = 6
BLOCK_LEFT = 4514
BLOCK_RIGHT = 5114

# Row bands in block coordinates, and what each row reads.
# Only the pitch-7.4975 rows are transcribed here: they are the class the skill
# actually reads (CamDir and the Zone/Pos lines). The pitch-6.5948 rows are
# listed with text None so the geometry code still sees them.
ROWS: list[tuple[int, int, str | None]] = [
    (0, 12, "CamDir:    0    0     0 FOV: 55 Focal: 0.00 FStop: 64.0"),
    (13, 25, "Zone: SolarSystem_200000000001 Pos: -0.00m 0.04m 1.74m"),
    (27, 35, "Zone: Root Pos: -0.00m 0.04m 1.74m"),
    (39, 50, "FPS 60.0 [60..60], - 16.7ms [1.7ms]"),
    (52, 61, "Session: c657cc88-c25e-f142-bfd5-1f74fe692da6"),
]

PITCH_GUESS = 7.4975


def load_block(label: str) -> np.ndarray:
    """Load shot_00 and return the RGB block."""
    path = CAPTURE_ROOT / label / "shot_00.png"
    frame = np.asarray(Image.open(path).convert("RGB"))
    return frame[BLOCK_TOP:BLOCK_TOP + 238, BLOCK_LEFT:BLOCK_RIGHT]


def ink_runs(profile: np.ndarray, threshold: int) -> list[tuple[int, int]]:
    """Contiguous runs of columns carrying ink, as (start, stop) pairs."""
    runs: list[tuple[int, int]] = []
    start: int | None = None
    for x, value in enumerate(profile):
        if value > threshold and start is None:
            start = x
        elif value <= threshold and start is not None:
            runs.append((start, x))
            start = None
    if start is not None:
        runs.append((start, len(profile)))
    return runs


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--label", required=True)
    parser.add_argument("--threshold", type=int, default=24)
    args = parser.parse_args(argv)

    block = load_block(args.label)
    luma = block.max(axis=2)
    width = block.shape[1]
    print(f"Block {width}x{block.shape[0]} from x={BLOCK_LEFT}, y={BLOCK_TOP}\n")

    # 1. TRANSCRIPTION CHECK. Predicted span for an n-character right-aligned
    #    line is about n * pitch; compare against what the pixels actually span.
    print("Transcription check (predicted vs measured ink span):")
    ok = True
    for top, bottom, text in ROWS:
        if text is None:
            continue
        row = luma[top:bottom].max(axis=0)
        cols = np.flatnonzero(row > args.threshold)
        measured = int(cols[-1] - cols[0] + 1)
        # The line starts at the left edge of the leftmost cell and ends with
        # the last glyph's ink, so predicted span is (n-1) pitch plus one glyph.
        predicted = (len(text) - 1) * PITCH_GUESS
        implied_chars = measured / PITCH_GUESS
        delta = implied_chars - (len(text) - 1)
        flag = "ok" if abs(delta) < 0.75 else "MISMATCH"
        ok &= abs(delta) < 0.75
        print(f"  {len(text):3d} chars  measured {measured:4d} px  "
              f"predicted >= {predicted:6.1f} px  implied {implied_chars:6.2f} cells  "
              f"delta {delta:+5.2f}  {flag}")
        if flag == "MISMATCH":
            print(f"      text: {text!r}")
    if not ok:
        print("\n  Transcription does not match the pixels. Fix it before "
              "building templates: a wrong run of spaces shifts every cell "
              "left of the error.")
    print()

    # 2. PITCH FROM LABELS. For one character class, ink starts a fixed offset
    #    into its cell, so ink_start is linear in the cell index.
    starts: dict[str, list[tuple[int, int]]] = defaultdict(list)
    for top, bottom, text in ROWS:
        if text is None:
            continue
        row = luma[top:bottom].max(axis=0)
        runs = ink_runs(row, args.threshold)
        length = len(text)
        for start, stop in runs:
            # Which cell does this run start in, at the guessed pitch?
            cell = int(round((width - start) / PITCH_GUESS - 1))
            index = length - 1 - cell
            if 0 <= index < length:
                starts[text[index]].append((cell, start))

    print("Pitch fitted per character class (ink_start = A - pitch*(cell+1)):")
    estimates: list[tuple[float, int, str]] = []
    for char, points in sorted(starts.items()):
        if len(points) < 4 or char == " ":
            continue
        cells = np.array([c for c, _ in points], dtype=float)
        xs = np.array([s for _, s in points], dtype=float)
        if float(cells.max() - cells.min()) < 10:
            continue
        slope, intercept = np.polyfit(cells + 1, xs, 1)
        residual = float(np.abs(xs - (slope * (cells + 1) + intercept)).max())
        pitch = -float(slope)
        estimates.append((pitch, len(points), char))
        print(f"  {char!r:5s} n={len(points):3d}  span {int(cells.min())}-"
              f"{int(cells.max())}  pitch {pitch:.4f}  max residual {residual:.2f} px")

    if estimates:
        weights = np.array([n for _, n, _ in estimates], dtype=float)
        values = np.array([p for p, _, _ in estimates])
        pooled = float((values * weights).sum() / weights.sum())
        print(f"\n  weighted pooled pitch: {pooled:.4f} px "
              f"(spread {values.min():.4f} to {values.max():.4f})")

    # 3. Do repeated characters render IDENTICALLY at different cells? If they
    #    do, one template per character is exact and sub-pixel phase does not
    #    matter. If they do not, templates must be phase-aware. This is the
    #    question that decides the whole classifier design.
    print("\nBitmap identity across positions (same char, different cells):")
    cell_height = luma.shape[0]
    del cell_height
    variants: list[tuple[str, int, int]] = []
    for top, bottom, text in ROWS:
        if text is None:
            continue
        length = len(text)
        rows_of: dict[str, list[np.ndarray]] = defaultdict(list)
        for cell in range(length):
            index = length - 1 - cell
            char = text[index]
            if char == " ":
                continue
            right = width - cell * pooled
            left = right - pooled
            x0, x1 = int(round(left)), int(round(left)) + 8
            if x0 < 0 or x1 > width:
                continue
            rows_of[char].append(luma[top:bottom, x0:x1])
        for char, patches in rows_of.items():
            if len(patches) < 2:
                continue
            unique: list[np.ndarray] = []
            for patch in patches:
                if not any(np.array_equal(patch, u) for u in unique):
                    unique.append(patch)
            variants.append((char, len(patches), len(unique)))

    by_char: dict[str, tuple[int, int]] = {}
    for char, total, uniq in variants:
        prev = by_char.get(char, (0, 0))
        by_char[char] = (prev[0] + total, max(prev[1], uniq))
    for char, (total, uniq) in sorted(by_char.items()):
        note = "IDENTICAL" if uniq == 1 else f"{uniq} distinct bitmaps"
        print(f"  {char!r:5s} {total:3d} instances -> {note}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
