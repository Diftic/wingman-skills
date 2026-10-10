"""Measure in-game character accuracy against occupancy-verified truth.

DEV TOOL, not a runtime file.

The truth strings below were read from a magnified render, which is exactly the
step that has gone wrong twice in this project. So every one is CHECKED against
measured cell occupancy before it is used: a right-aligned line of n characters
must occupy n cells, and a blank cell must line up with a space in the truth.
A row whose occupancy disagrees is reported and EXCLUDED from the accuracy
figure rather than quietly dragging it around.

Occupancy is read from the green channel, whose background on this capture's
red wall sits at about 2/255, making it effectively a black-background view.

Usage:

    python measure.py --label game-mid --glyphs glyphs.npz

Credit: Mallachi
"""

from __future__ import annotations

import argparse
import sys
from collections import Counter
from pathlib import Path

import numpy as np
from PIL import Image

from reader import CAPTURE_ROOT, RIGHT_MARGIN, Reader
from templates import CELL_WIDTH, PITCH, ROW_HEIGHT

# Capture label -> row index -> truth. Only the pitch-7.5 rows; the 6.595 px
# class is not modelled and is measured separately as a refusal test.
#
# These strings are read by eye and are therefore SUSPECT. The occupancy gate
# catches any that get the spaces wrong and excludes the row. A wrong non-space
# character would survive the gate and be scored as a decoder error, which
# biases the figure DOWN, never up. That asymmetry is deliberate.
TRUTH_SETS: dict[str, dict[int, str]] = {}
TRUTH_SETS["game-mid"] = {
    0: "CamDir: -55   -3  125 FOV: 55 Focal: 0.10 FStop: 64.0",
    1: "Zone: rsi_polaris_kaboos_ext Pos: -24.59m -37.86m 1.26m",
    2: "Zone: glaciemring_segment_wtn-014 Pos: -862.60m 1180.47m -33.29m",
    3: "Zone: SolarSystem_729968885550 Pos: 6470453.8383km 13533871.9753km -33.29m",
    4: "Zone: Root Pos: 6470453.8383km 13533871.9753km -33.29m",
    5: "FPS 115.9 [27..141], - 8.8ms [8.4ms]",
    6: "Session: ce34bb31-37d7-a247-a7fb-4b6b662bdcf6",
    7: "ShardId: pub_euw1b_12269732_090",
}
TRUTH_SETS["game-bright"] = {
    1: "Zone: OOC_Stanton_2_Crusader Pos: 5295.4275km -863.1299km 5282.3349km",
    2: "Zone: SolarSystem_862650910189 Pos: -18963198.5059km "
       "-2679226.9753km 5282.3349km",
    3: "Zone: Root Pos: -18963198.5059km -2679226.9753km 5282.3349km",
    4: "FPS 36.1 [29..39], - 27.9ms [26.5ms]",
    5: "Session: 8cfec7db-ab31-204e-9087-15d877c0bdbd",
    6: "ShardId: ptu_use1b_12335477_949",
}
TRUTH: dict[int, str] = {}

BLANK = 0.12
BLANK_SPREAD = 50.0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--label", required=True)
    parser.add_argument("--glyphs", default="glyphs.npz")
    parser.add_argument("--shot", default="shot_00.png")
    args = parser.parse_args(argv)

    global TRUTH
    TRUTH = TRUTH_SETS[args.label]

    frame = np.asarray(
        Image.open(CAPTURE_ROOT / args.label / args.shot).convert("RGB")
    ).astype(np.float64)
    reader = Reader(glyph_file=args.glyphs)
    y0, _, rows = reader.read(frame, max(TRUTH) + 1)
    width = frame.shape[1]
    right = width - RIGHT_MARGIN + 1
    green = frame[:, :, 1] / 255.0

    def is_blank(band_rgb: np.ndarray, x0: int) -> bool:
        """Blank by LOCAL CONTRAST, not by darkness.

        Judging a cell blank because it is dark only works when the backdrop is
        dark; over a bright sky every cell reads as ink and the gate certifies
        nothing. Glyph ink creates a large spread inside the cell whatever the
        background level.

        The spread is measured WITHIN each channel and maxed over the three.
        Spread taken across channels is a property of the background's COLOUR,
        not of ink: on this capture's red wall (R 96, G 2) a blank cell scored
        94 that way and every cell in the block read as inked, which certified
        nothing. Per channel, over the 680 cells of the two in-game captures
        whose truth is sound, blank cells span 0 to 19 and inked cells 99 to
        255, so the threshold sits in an empty band five times wider than the
        blank spread itself.
        """
        core = band_rgb[:, x0 + 1:x0 + CELL_WIDTH - 1]
        if core.size == 0:
            return True
        spread = max(
            float(core[:, :, channel].max() - core[:, :, channel].min())
            for channel in range(3)
        )
        return spread < BLANK_SPREAD

    print("Occupancy check of each truth string:")
    usable: list[int] = []
    for row in rows:
        index = row["row"]
        if index not in TRUTH:
            continue
        truth = TRUTH[index]
        rgb_band = frame[row["y"]:row["y"] + ROW_HEIGHT]
        occupancy: list[bool] = []
        for x0, _ in reader.cell_boxes(right, row["offset"], len(truth)):
            occupancy.append(not is_blank(rgb_band, x0))
        occupancy = list(reversed(occupancy))
        expected = [c != " " for c in truth]
        # Leading cells may be blank simply because the line is short.
        mismatch = sum(1 for a, b in zip(occupancy, expected) if a != b)
        leftmost = next((i for i, v in enumerate(occupancy) if v), 0)
        flag = "ok" if mismatch == 0 else f"{mismatch} cells disagree"
        if mismatch == 0:
            usable.append(index)
        print(f"  row {index}: {len(truth):3d} chars, first ink at cell {leftmost:2d}  {flag}")
        if mismatch:
            print(f"    truth : {''.join('#' if e else '.' for e in expected)}")
            print(f"    pixels: {''.join('#' if o else '.' for o in occupancy)}")

    print(f"\n{len(usable)} of {len(TRUTH)} rows verified; measuring on those only.\n")

    total = correct = 0
    confusions: Counter[tuple[str, str]] = Counter()
    for row in rows:
        index = row["row"]
        if index not in usable:
            continue
        truth = TRUTH[index]
        band = frame[row["y"]:row["y"] + ROW_HEIGHT]
        gband = green[row["y"]:row["y"] + ROW_HEIGHT]
        got: list[str] = []
        for cell, (x0, phase) in enumerate(reader.cell_boxes(right, row["offset"],
                                                            len(truth))):
            patch = band[:, x0:x0 + CELL_WIDTH]
            if patch.shape[1] < CELL_WIDTH:
                break
            core = patch[:, 1:CELL_WIDTH - 1]
            colour = np.asarray(
                {"white": (255, 255, 255), "orange": (255, 164, 0),
                 "yellow": (239, 230, 139)}[row["colour"]], dtype=np.float64
            )
            from reader import match as match_fn
            ranked = sorted(
                (match_fn(core, g[:, 1:CELL_WIDTH - 1],
                          reader.trans[(c, p)][:, 1:CELL_WIDTH - 1], colour), c)
                for (c, p), g in reader.glyph.items() if p == phase
            )
            got.append(ranked[0][1])
        decoded = "".join(reversed(got))
        for expected, actual in zip(truth[-len(decoded):], decoded):
            total += 1
            if expected == actual:
                correct += 1
            else:
                confusions[(expected, actual)] += 1
        marks = "".join(
            " " if e == a else "^"
            for e, a in zip(truth[-len(decoded):], decoded)
        )
        print(f"  row {index}")
        print(f"    truth   {truth}")
        print(f"    decoded {decoded}")
        if marks.strip():
            print(f"            {marks}")

    if total:
        print(f"\nCHARACTER ACCURACY: {correct}/{total} = "
              f"{100.0 * correct / total:.2f}%  "
              f"(error {100.0 * (total - correct) / total:.2f}%)")
        for (expected, actual), count in confusions.most_common():
            print(f"    {expected!r} read as {actual!r}: {count}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
