"""Harvest missing glyph templates from occupancy-verified rows.

DEV TOOL, not a runtime file.

Where `learn.py` discovers unknown shapes and asks a human to name them, this
takes the labels from truth strings that have already passed the occupancy
check in `measure.py`. That makes the label certain rather than judged, so it
is the right tool for closing a known gap and the wrong tool for exploring an
unknown one.

Coverage maps come from a channel whose background is near zero. On this
capture's red wall the green channel sits at about 2/255, so
`observed_green / 255` is the glyph coverage to within 0.008.

Only rows that pass occupancy are harvested, and only (character, phase) pairs
that are ABSENT are added. An existing template is never overwritten: doing so
once already regressed every `5` at one phase into an `S`.

Usage:

    python harvest.py --label game-mid --glyphs glyphs.npz

Credit: Mallachi
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np
from PIL import Image

from measure import BLANK, TRUTH_SETS
from reader import CAPTURE_ROOT, RIGHT_MARGIN, Reader
from templates import CELL_WIDTH, ROW_HEIGHT


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--label", required=True)
    parser.add_argument("--glyphs", default="glyphs.npz")
    parser.add_argument("--shot", default="shot_00.png")
    parser.add_argument("--out", default="glyphs.npz")
    args = parser.parse_args(argv)

    # Look the truth set up by label rather than importing measure.TRUTH, which
    # is a module global that measure.main() fills at run time and is therefore
    # EMPTY on import. That import silently broke this tool when measure.py
    # grew a second capture: every run died on max() of an empty sequence, so
    # the gap this tool exists to close stayed open with the pixels on disk.
    truth_set = TRUTH_SETS[args.label]

    frame = np.asarray(
        Image.open(CAPTURE_ROOT / args.label / args.shot).convert("RGB")
    ).astype(np.float64)
    reader = Reader(glyph_file=args.glyphs)
    before = len(reader.glyph)
    y0, _, rows = reader.read(frame, max(truth_set) + 1)
    right = frame.shape[1] - RIGHT_MARGIN + 1
    green = frame[:, :, 1] / 255.0

    harvested: dict[tuple[str, int], np.ndarray] = {}
    skipped_rows: list[int] = []
    for row in rows:
        index = row["row"]
        if index not in truth_set:
            continue
        truth = truth_set[index]
        band = green[row["y"]:row["y"] + ROW_HEIGHT]

        # Re-run the occupancy gate here rather than trusting it was run
        # elsewhere: harvesting from a row whose truth is misaligned would
        # poison the template set with confidently-wrong labels.
        occupancy = []
        for x0, _ in reader.cell_boxes(right, row["offset"], len(truth)):
            cell = band[:, x0:x0 + CELL_WIDTH]
            occupancy.append(bool(cell.size and cell.max() > BLANK))
        occupancy = list(reversed(occupancy))
        if any(o != (c != " ") for o, c in zip(occupancy, truth)):
            skipped_rows.append(index)
            continue

        for cell, (x0, phase) in enumerate(
            reader.cell_boxes(right, row["offset"], len(truth))
        ):
            char = truth[len(truth) - 1 - cell]
            if char == " ":
                continue
            key = (char, phase)
            if key in reader.glyph or key in harvested:
                continue
            patch = band[:, x0:x0 + CELL_WIDTH]
            if patch.shape != (ROW_HEIGHT, CELL_WIDTH) or patch.max() <= BLANK:
                continue
            harvested[key] = np.clip(patch, 0.0, 1.0)

    if skipped_rows:
        print(f"rows skipped, occupancy disagreed: {skipped_rows}")
    print(f"harvested {len(harvested)} missing templates: "
          f"{', '.join(f'{c!r}/{p}' for c, p in sorted(harvested, key=str))}")

    reader.glyph.update(harvested)
    out = Path(__file__).parent / args.out
    np.savez(out, **{f"{c}|{p}": g for (c, p), g in reader.glyph.items()})
    print(f"{before} -> {len(reader.glyph)} templates over "
          f"{len({c for c, _ in reader.glyph})} characters; saved {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
