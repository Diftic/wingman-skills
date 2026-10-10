"""Find glyphs the template set cannot name, and render them for labelling.

DEV TOOL, not a runtime file.

The login-screen capture only ever showed the characters that screen happened
to display, so the template set is missing `3`, `k`, `g`, `x`, `h`, `u` and most
uppercase. Rather than transcribe an in-game line by eye (which produced a wrong
transcription twice, both times on the CamDir line), this finds the cells that
match nothing well, groups them by their actual bitmap, and renders one image
per group to be identified by looking at ONE magnified glyph.

New coverage maps are taken from a channel whose background is near zero. On
the red interior wall of capture `game-mid` the green channel sits at about
2/255, so `observed_green / 255` is the glyph coverage to within 0.008, which
is the same quantity the black-background capture yields.

Usage:

    python learn.py --label game-mid --channel 1 --out unknown.png

Credit: Mallachi
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np
from PIL import Image

from reader import CAPTURE_ROOT, MASK, RIGHT_MARGIN, Reader, match
from templates import CELL_WIDTH, COLOURS, ROW_HEIGHT, ROW_PITCH


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--label", required=True)
    parser.add_argument("--templates", default="login")
    parser.add_argument("--shot", default="shot_00.png")
    parser.add_argument("--channel", type=int, default=1,
                        help="channel whose background is nearest zero")
    parser.add_argument("--rows", type=int, default=16)
    parser.add_argument("--cost", type=float, default=30.0,
                        help="cells above this residual are treated as unknown")
    parser.add_argument("--out", default="unknown.png")
    args = parser.parse_args(argv)

    frame = np.asarray(
        Image.open(CAPTURE_ROOT / args.label / args.shot).convert("RGB")
    ).astype(np.float64)
    reader = Reader(args.templates)
    y0, _, rows = reader.read(frame, args.rows)
    width = frame.shape[1]
    right = width - RIGHT_MARGIN + 1
    plane = frame[:, :, args.channel] / 255.0

    # Group unknown cells by their bitmap. Rendering is deterministic, so every
    # instance of one character at one phase is the same map; a group with many
    # members is a real character, a singleton is probably noise.
    groups: list[dict] = []
    for row in rows:
        top = row["y"]
        band = frame[top:top + ROW_HEIGHT]
        if band.shape[0] < ROW_HEIGHT:
            continue
        colour = np.asarray(COLOURS[row["colour"]], dtype=np.float64)
        for x0, phase in reader.cell_boxes(right, row["offset"], 80):
            patch = band[:, x0:x0 + CELL_WIDTH]
            if patch.shape[1] < CELL_WIDTH:
                break
            core = patch[:, MASK:CELL_WIDTH - MASK]
            ranked = sorted(
                (match(core, g[:, MASK:CELL_WIDTH - MASK],
                       reader.trans[(c, p)][:, MASK:CELL_WIDTH - MASK], colour), c)
                for (c, p), g in reader.glyph.items()
                if p == phase
            )
            if ranked[0][0] <= args.cost:
                continue
            bitmap = plane[top:top + ROW_HEIGHT, x0:x0 + CELL_WIDTH]
            if bitmap.max() < 0.15:
                continue  # blank cell, not a glyph
            for group in groups:
                if group["phase"] == phase and float(
                    np.abs(group["map"] - bitmap).max()
                ) < 0.06:
                    group["n"] += 1
                    group["sum"] += bitmap
                    group["map"] = group["sum"] / group["n"]
                    break
            else:
                groups.append({"phase": phase, "n": 1, "map": bitmap.copy(),
                               "sum": bitmap.copy(), "guess": ranked[0][1]})

    groups = [g for g in groups if g["n"] >= 2]
    groups.sort(key=lambda g: -g["n"])
    print(f"{len(groups)} distinct unnamed glyph shapes (2+ instances):")
    for index, group in enumerate(groups):
        print(f"  {index:2d}: phase {group['phase']}  n={group['n']:3d}  "
              f"currently misread as {group['guess']!r}")

    if groups:
        scale = 6
        pad = 2
        tile_w = CELL_WIDTH + pad
        sheet = np.zeros((ROW_HEIGHT, tile_w * len(groups)), dtype=np.float64)
        for index, group in enumerate(groups):
            sheet[:, index * tile_w:index * tile_w + CELL_WIDTH] = group["map"]
        image = Image.fromarray(
            np.clip(sheet * 255, 0, 255).astype(np.uint8), mode="L"
        ).resize((sheet.shape[1] * scale, sheet.shape[0] * scale), Image.NEAREST)
        out_path = CAPTURE_ROOT / args.label / args.out
        image.save(out_path)
        print(f"\nRendered {len(groups)} glyphs left to right: {out_path}")
        json.dump(
            [{"index": i, "phase": g["phase"], "n": g["n"],
              "map": g["map"].round(4).tolist()} for i, g in enumerate(groups)],
            open(CAPTURE_ROOT / args.label / "unknown.json", "w"),
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
