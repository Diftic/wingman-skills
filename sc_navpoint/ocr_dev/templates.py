"""Build and validate glyph templates from a lossless capture.

DEV TOOL, not a runtime file.

MEASURED MODEL, established 2026-07-29 on the login-screen capture. Every
constant below was fitted from pixels and is falsifiable by re-running this
script; none is assumed.

  Character pitch      exactly 7.5 px
  Row pitch            exactly 13 px, glyph body 8 px tall
  Colours              white (255,255,255), orange (255,164,0),
                       yellow (239,230,139), drawn over pure black
  Sub-pixel phase      a line's left edge is snapped to an integer pixel and
                       characters then advance by 7.5 px, so the phase of every
                       glyph in a line is fixed by the PARITY OF THE LINE'S
                       LENGTH. Two phases exist, 0.0 and 0.5, and each row uses
                       one of them throughout.

The phase result is why an earlier attempt scored 33% in sample: it keyed
templates on cell parity, which is only comparable within a single row. Once
each row's origin is fitted, every instance of a character within a row is
BIT-IDENTICAL, deviation exactly 0.00.

Two hypotheses are re-checked on every run, because both are load-bearing:

  H1  Colour normalises away. A pixel is `coverage * colour`, so dividing by
      the row's colour should make a yellow glyph and a white glyph produce the
      same coverage map, letting one template set serve all three colours.
  H2  Each character has exactly two renderings, one per phase, and is
      pixel-exact within each.

Usage:

    python templates.py --label login

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

BLOCK_TOP = 6
BLOCK_LEFT = 4514
BLOCK_RIGHT = 5114
BLOCK_WIDTH = BLOCK_RIGHT - BLOCK_LEFT

PITCH = 7.5
CELL_WIDTH = 8
ROW_PITCH = 13
ROW_HEIGHT = 13
PHASES = 2

COLOURS: dict[str, tuple[int, int, int]] = {
    "white": (255, 255, 255),
    "orange": (255, 164, 0),
    "yellow": (239, 230, 139),
}

# Row index in the pitch-7.5 class, and the verified text. Every transcription
# was checked against measured cell occupancy rather than read by eye: the
# CamDir line's runs of spaces were wrong on the first reading, which is the
# same failure the July transcription hit on the same line.
ROWS: list[tuple[int, str]] = [
    (0, "CamDir:   0   0    0 FOV: 55 Focal: 0.00 FStop: 64.0"),
    (1, "Zone: SolarSystem_200000000001 Pos: -0.00m 0.04m 1.74m"),
    (2, "Zone: Root Pos: -0.00m 0.04m 1.74m"),
    (3, "FPS 60.0 [60..60], - 16.7ms [1.7ms]"),
    (4, "Session: c657cc88-c25e-f142-bfd5-1f74fe692da6"),
]


def load_block(label: str, shot: str = "shot_00.png") -> np.ndarray:
    """Load one shot and return the overlay block as RGB."""
    frame = np.asarray(Image.open(CAPTURE_ROOT / label / shot).convert("RGB"))
    return frame[BLOCK_TOP:BLOCK_TOP + 238, BLOCK_LEFT:BLOCK_RIGHT]


def row_window(index: int) -> tuple[int, int]:
    """Vertical window for a text row, uniform across rows by construction.

    Derived from the rows' ink PROFILES, not their ink boxes. A box grows when
    a row happens to contain a descender or a bracket, which silently
    misaligns glyphs between rows.
    """
    return index * ROW_PITCH, index * ROW_PITCH + ROW_HEIGHT


def row_colour(block: np.ndarray, top: int, bottom: int) -> tuple[str, np.ndarray]:
    """Identify which of the three overlay colours a row is drawn in."""
    band = block[top:bottom].reshape(-1, 3).astype(np.float64)
    lit = band[band.max(axis=1) >= 100]
    if len(lit) == 0:
        raise SystemExit(f"row {top}-{bottom} has no strong ink")
    chroma = (lit / lit.max(axis=1, keepdims=True)).mean(axis=0)
    best, distance = "", 1e9
    for name, rgb in COLOURS.items():
        reference = np.asarray(rgb, dtype=np.float64)
        d = float(np.abs(chroma - reference / reference.max()).max())
        if d < distance:
            best, distance = name, d
    return best, np.asarray(COLOURS[best], dtype=np.float64)


def coverage_map(block: np.ndarray, top: int, bottom: int, colour: np.ndarray) -> np.ndarray:
    """Convert a row to per-pixel coverage in 0..255, undoing the text colour.

    Only the channel where the colour is strongest is used; dividing a channel
    whose colour component is near zero (orange's blue is 0) would amplify
    quantisation noise without adding information.
    """
    channel = int(np.argmax(colour))
    return block[top:bottom, :, channel].astype(np.float64) / colour[channel] * 255.0


def cells(cover: np.ndarray, text: str, origin: float):
    """Yield (char, phase, patch) for every non-space character in a line."""
    length = len(text)
    for cell in range(length):
        char = text[length - 1 - cell]
        if char == " ":
            continue
        left = origin - (cell + 1) * PITCH
        x0 = int(np.floor(left))
        if x0 < 0 or x0 + CELL_WIDTH > BLOCK_WIDTH:
            continue
        phase = int(round((left - x0) * PHASES)) % PHASES
        yield char, phase, cover[:, x0:x0 + CELL_WIDTH]


def fit_origin(cover: np.ndarray, text: str) -> tuple[float, float]:
    """Find the line's grid origin by maximising self-consistency.

    A line's own repeated characters are the ruler: at the true origin every
    instance of a character at the same phase is the same bitmap, so the
    within-class deviation collapses. No external reference is needed.

    Returns:
        (origin, worst within-class deviation at that origin).
    """
    best, best_score = 0.0, float("inf")
    for origin in np.arange(598.0, 602.0, 0.05):
        groups: dict[tuple[str, int], list[np.ndarray]] = defaultdict(list)
        for char, phase, patch in cells(cover, text, float(origin)):
            groups[(char, phase)].append(patch)
        worst = 0.0
        for patches in groups.values():
            if len(patches) < 2:
                continue
            stack = np.stack(patches)
            worst = max(worst, float(np.abs(stack - stack.mean(axis=0)).max()))
        if worst < best_score:
            best, best_score = float(origin), worst
    return best, best_score


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--label", required=True)
    parser.add_argument("--tolerance", type=float, default=1.0)
    args = parser.parse_args(argv)

    block = load_block(args.label)
    print(f"Block {block.shape[1]}x{block.shape[0]}, pitch {PITCH}, "
          f"row pitch {ROW_PITCH}\n")

    samples: dict[tuple[str, int], list[tuple[str, np.ndarray]]] = defaultdict(list)
    print("Per-row fit:")
    print("  row colour   chars  origin   worst-dev  phase  length parity")
    for index, text in ROWS:
        top, bottom = row_window(index)
        name, colour = row_colour(block, top, bottom)
        cover = coverage_map(block, top, bottom, colour)
        origin, worst = fit_origin(cover, text)
        phases = set()
        for char, phase, patch in cells(cover, text, origin):
            samples[(char, phase)].append((name, patch))
            phases.add(phase)
        first = origin - PITCH
        cell0_phase = first - np.floor(first)
        print(f"  {index:3d} {name:7s} {len(text):5d}  {origin:7.2f}  {worst:9.2f}   "
              f"{cell0_phase:.2f}   {'even' if len(text) % 2 == 0 else 'odd'}")

    # H2: is each (character, phase) a single exact bitmap?
    print(f"\nH2, bitmap identity per (character, phase), tolerance "
          f"{args.tolerance}:")
    template: dict[tuple[str, int], np.ndarray] = {}
    worst_overall = 0.0
    inconsistent = 0
    compared = 0
    for (char, phase), entries in sorted(samples.items()):
        stack = np.stack([patch for _, patch in entries])
        template[(char, phase)] = stack.mean(axis=0)
        if len(entries) < 2:
            continue
        deviation = float(np.abs(stack - stack.mean(axis=0)).max())
        worst_overall = max(worst_overall, deviation)
        compared += 1
        if deviation > args.tolerance:
            inconsistent += 1
            print(f"  {char!r:5s} phase {phase}  n={len(entries):3d}  "
                  f"deviation {deviation:8.2f}  DIFFERS")
    print(f"  {compared} classes with 2+ instances, {inconsistent} inconsistent")
    print(f"  worst deviation anywhere: {worst_overall:.2f} coverage units")
    print(f"  templates built: {len(template)}")

    # H1: does a glyph drawn in yellow normalise onto its white counterpart?
    print("\nH1, cross-colour agreement after normalising:")
    checked = 0
    worst_colour = 0.0
    for (char, phase), entries in sorted(samples.items()):
        names = {name for name, _ in entries}
        if len(names) < 2:
            continue
        by_colour = {
            name: np.stack([p for n, p in entries if n == name]).mean(axis=0)
            for name in names
        }
        keys = sorted(by_colour)
        spread = float(np.abs(by_colour[keys[0]] - by_colour[keys[1]]).max())
        worst_colour = max(worst_colour, spread)
        checked += 1
        print(f"  {char!r:5s} phase {phase}  {' vs '.join(keys)}  "
              f"max difference {spread:6.2f}")
    if checked == 0:
        print("  no character appears in two colours in this capture")
    else:
        print(f"  worst cross-colour difference: {worst_colour:.2f} coverage units")

    # In-sample classification against the templates just built.
    print("\nIn-sample classification:")
    total = correct = 0
    confusions: dict[tuple[str, str], int] = defaultdict(int)
    for (char, phase), entries in sorted(samples.items()):
        for _, patch in entries:
            scored = sorted(
                (float(np.abs(patch - proto).mean()), c)
                for (c, p), proto in template.items()
                if p == phase
            )
            total += 1
            if scored[0][1] == char:
                correct += 1
            else:
                confusions[(char, scored[0][1])] += 1
    rate = 100.0 * (total - correct) / total if total else 0.0
    print(f"  {correct}/{total} correct, error rate {rate:.2f}%")
    print("  reference points: July on the JPEG corpus 25%, "
          "cell-parity keying 33.51%")
    for (truth, guess), count in sorted(confusions.items(), key=lambda kv: -kv[1]):
        print(f"    {truth!r} read as {guess!r}: {count}")

    # Margin matters more than the error rate: a classifier that is right by a
    # hair will not survive a background that is not black.
    print("\nMatch margin (best vs runner-up, mean absolute coverage):")
    margins: list[float] = []
    for (char, phase), entries in sorted(samples.items()):
        for _, patch in entries:
            scored = sorted(
                (float(np.abs(patch - proto).mean()), c)
                for (c, p), proto in template.items()
                if p == phase
            )
            if len(scored) > 1:
                margins.append(scored[1][0] - scored[0][0])
    if margins:
        array = np.asarray(margins)
        print(f"  min {array.min():.2f}   median {np.median(array):.2f}   "
              f"mean {array.mean():.2f}")
        print(f"  instances with margin < 1.0: {int((array < 1.0).sum())} of {len(array)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
