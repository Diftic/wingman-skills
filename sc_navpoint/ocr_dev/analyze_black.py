"""Stage 1 analysis: measure the overlay's exact text colours on a black backdrop.

DEV TOOL, not a runtime file.

With r_displayinfo drawn over solid black, a text pixel is `coverage * colour`.
Two consequences drive this script:

  1. CHROMATICITY IS INVARIANT TO COVERAGE. Blending with black scales all three
     channels by the same factor, so every pixel of a given text colour has the
     same ratio between channels no matter how faint it is. That makes the
     colours separable at any anti-aliasing level, and it is a falsifiable
     prediction: if chromaticity drifts with intensity, the backdrop is not
     black or the blend is not linear, and the rest of this reasoning is wrong.
  2. DIVIDING BY THE COLOUR RECOVERS COVERAGE. Once the colours are known,
     white, yellow and orange glyphs all normalise to the same greyscale
     coverage map, so one template set serves all three, and colour survives as
     a free per-field discriminator.

Usage:

    python analyze_black.py --label login --region 4000,0,5120,300

Credit: Mallachi
"""

from __future__ import annotations

import argparse
import sys
from collections import Counter
from pathlib import Path

import numpy as np
from PIL import Image, ImageFilter


CAPTURE_ROOT = Path(__file__).parent / "captures"


def load_set(label: str) -> list[tuple[str, np.ndarray]]:
    """Load every shot in a capture set, in filename order."""
    out_dir = CAPTURE_ROOT / label
    paths = sorted(out_dir.glob("shot_*.png"))
    if not paths:
        raise SystemExit(f"no shots found in {out_dir}")
    return [(p.name, np.asarray(Image.open(p).convert("RGB"))) for p in paths]


def parse_region(text: str, width: int, height: int) -> tuple[int, int, int, int]:
    """Parse an 'x0,y0,x1,y1' region, clamped to the frame."""
    x0, y0, x1, y1 = (int(v) for v in text.split(","))
    return max(x0, 0), max(y0, 0), min(x1, width), min(y1, height)


def ink_bbox(region: np.ndarray, threshold: int) -> tuple[int, int, int, int]:
    """Bounding box of lit pixels within a region, as (top, bottom, left, right)."""
    lit = region.max(axis=2) > threshold
    rows = np.flatnonzero(lit.any(axis=1))
    cols = np.flatnonzero(lit.any(axis=0))
    if rows.size == 0 or cols.size == 0:
        raise SystemExit("no ink found in the search region")
    return int(rows[0]), int(rows[-1]) + 1, int(cols[0]), int(cols[-1]) + 1


def cluster_colours(
    pixels: np.ndarray, floor: int, tolerance: float
) -> list[tuple[np.ndarray, int]]:
    """Group pixels by chromaticity, which is coverage-invariant on black.

    Args:
        pixels: (N, 3) uint8 array of lit pixels.
        floor: Ignore pixels dimmer than this when forming clusters, because
            quantisation makes the ratio noisy near zero.
        tolerance: Max chromaticity distance to join an existing cluster.

    Returns:
        List of (mean chromaticity, pixel count), most populous first.
    """
    strong = pixels[pixels.max(axis=1) >= floor].astype(np.float64)
    if len(strong) == 0:
        return []
    chroma = strong / strong.max(axis=1, keepdims=True)

    centres: list[np.ndarray] = []
    counts: list[int] = []
    sums: list[np.ndarray] = []
    for c in chroma:
        for i, centre in enumerate(centres):
            if float(np.abs(c - centre).max()) <= tolerance:
                counts[i] += 1
                sums[i] += c
                centres[i] = sums[i] / counts[i]
                break
        else:
            centres.append(c.copy())
            counts.append(1)
            sums.append(c.copy())

    order = np.argsort(counts)[::-1]
    return [(centres[i], counts[i]) for i in order]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--label", required=True)
    parser.add_argument("--region", required=True, help="x0,y0,x1,y1 search box")
    parser.add_argument("--threshold", type=int, default=24)
    parser.add_argument("--chroma-floor", type=int, default=80)
    parser.add_argument("--chroma-tol", type=float, default=0.10)
    args = parser.parse_args(argv)

    shots = load_set(args.label)
    name, frame = shots[0]
    height, width = frame.shape[:2]
    x0, y0, x1, y1 = parse_region(args.region, width, height)
    search = frame[y0:y1, x0:x1]
    print(f"Loaded {len(shots)} shots, screen {width}x{height}")
    print(f"Search region x {x0}..{x1}, y {y0}..{y1}\n")

    top, bottom, left, right = ink_bbox(search, args.threshold)
    abs_top, abs_left = y0 + top, x0 + left
    abs_bottom, abs_right = y0 + bottom, x0 + right
    print("Ink bounding box (absolute screen coordinates):")
    print(f"  rows {abs_top}..{abs_bottom}   height {bottom - top}")
    print(f"  cols {abs_left}..{abs_right}   width {right - left}")
    print(f"  right edge sits {width - abs_right} px from the screen's right edge\n")

    block = frame[abs_top:abs_bottom, abs_left:abs_right]
    luma = block.max(axis=2)

    # BACKDROP. The premise of the whole stage. Selecting merely-dark pixels
    # would sweep in the faint tails of the glyphs themselves and slander a
    # clean backdrop, so exclude anything within `halo` px of any ink.
    halo = 5
    dilated = np.asarray(
        Image.fromarray(luma, mode="L").filter(ImageFilter.MaxFilter(halo))
    )
    far = block[dilated == 0]
    pure = int((far == 0).all(axis=1).sum())
    print(f"Backdrop check, {len(far)} px more than {halo // 2} px from any ink:")
    print(f"  exactly (0,0,0): {pure} ({100.0 * pure / max(len(far), 1):.2f}%)")
    print(f"  max RGB among them: {far.max(axis=0) if len(far) else 'n/a'}")
    verdict = "PURE BLACK, coverage model holds" if pure == len(far) else "NOT pure black"
    print(f"  -> {verdict}\n")

    lit = block[luma > args.threshold]
    print(f"Lit pixels (luma > {args.threshold}): {len(lit)}\n")

    clusters = cluster_colours(lit, args.chroma_floor, args.chroma_tol)
    print(f"Colour clusters by chromaticity (floor {args.chroma_floor}, "
          f"tol {args.chroma_tol}):")
    for centre, count in clusters:
        if count < 20:
            continue
        # Full-coverage representative: the brightest pixels of this cluster,
        # which is the text colour itself at alpha 1.
        chroma_all = lit.astype(np.float64) / np.maximum(
            lit.max(axis=1, keepdims=True), 1
        )
        member = np.abs(chroma_all - centre).max(axis=1) <= args.chroma_tol
        members = lit[member]
        peak_luma = int(members.max(axis=1).max())
        peak = members[members.max(axis=1) >= peak_luma - 1]
        common = Counter(map(tuple, peak.reshape(-1, 3))).most_common(3)
        print(f"\n  chromaticity {np.round(centre, 4)}  ({count} strong px, "
              f"{len(members)} total)")
        print(f"    full-coverage RGB, most common: "
              f"{', '.join(f'{c} x{n}' for c, n in common)}")
        levels = len(np.unique(members.max(axis=1)))
        print(f"    distinct intensity levels: {levels} (the coverage ramp)")

    # FALSIFICATION TEST for claim 1: does chromaticity hold as pixels get
    # fainter? Run it on EVERY cluster, not just the dominant one. On white it
    # is close to vacuous, since (1,1,1) deviates only if the channels diverge;
    # the tinted colours are where the model can actually be caught out.
    chroma_all = lit.astype(np.float64) / np.maximum(lit.max(axis=1, keepdims=True), 1)
    for centre, count in clusters:
        if count < 20:
            continue
        member = np.abs(chroma_all - centre).max(axis=1) <= args.chroma_tol
        members, mchroma = lit[member], chroma_all[member]
        mluma = members.max(axis=1)
        vacuous = " (near-vacuous for neutral grey)" if np.ptp(centre) < 0.02 else ""
        print(f"\nCoverage-invariance test, chromaticity "
              f"{np.round(centre, 4)}{vacuous}:")
        for lo, hi in ((200, 256), (120, 200), (60, 120), (25, 60)):
            sel = (mluma >= lo) & (mluma < hi)
            if sel.sum() < 10:
                continue
            band = mchroma[sel]
            print(f"  luma {lo:3d}-{hi:3d}: n={int(sel.sum()):6d}  "
                  f"chroma mean {np.round(band.mean(axis=0), 4)}  "
                  f"max dev {float(np.abs(band - centre).max()):.4f}")

    # STABILITY across the set, on the block region only. A whole-block count
    # conflates two different things: rendering noise, which would sink the
    # template plan, and text that genuinely changed between frames (FPS,
    # frame times, clocks). Split it PER TEXT ROW so they can be told apart:
    # rows carrying static text must be bit-identical, or the premise is dead.
    if len(shots) > 1:
        print("\nBlock-region differences against shot_00:")
        for other_name, other in shots[1:]:
            region = other[abs_top:abs_bottom, abs_left:abs_right]
            differing = int((region != block).any(axis=2).sum())
            pct = 100.0 * differing / (block.size // 3)
            print(f"  {other_name}: {differing} differing px ({pct:.3f}%)")

        row_has_ink = luma.max(axis=1) > args.threshold
        bands: list[tuple[int, int]] = []
        start: int | None = None
        for y, has in enumerate(row_has_ink):
            if has and start is None:
                start = y
            elif not has and start is not None:
                bands.append((start, y))
                start = None
        if start is not None:
            bands.append((start, len(row_has_ink)))

        print(f"\nPer-text-row change across the {len(shots)} frames "
              f"({len(bands)} rows detected):")
        static_rows = 0
        for band_top, band_bottom in bands:
            base_band = block[band_top:band_bottom]
            worst = 0
            for _, other in shots[1:]:
                region = other[abs_top + band_top:abs_top + band_bottom,
                               abs_left:abs_right]
                worst = max(worst, int((region != base_band).any(axis=2).sum()))
            if worst == 0:
                static_rows += 1
            flag = "IDENTICAL" if worst == 0 else f"{worst} px changed"
            print(f"  y {abs_top + band_top:4d}-{abs_top + band_bottom:4d}: {flag}")
        print(f"  -> {static_rows} of {len(bands)} rows bit-identical across all frames")

    crop_path = CAPTURE_ROOT / args.label / "strip.png"
    Image.fromarray(block, mode="RGB").save(crop_path)
    print(f"\nBlock crop written: {crop_path} "
          f"({right - left}x{bottom - top} at x={abs_left}, y={abs_top})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
