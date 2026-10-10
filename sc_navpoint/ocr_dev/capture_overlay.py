"""Lossless screen capture of the r_displayinfo overlay, for OCR development.

DEV TOOL, not a runtime file. Deliberately absent from update_release.py's
RELEASE_FILES and from both skill_installer_config.json manifests.

Grabs the screen with `mss` (lossless, unlike the game's JPEG screenshots) and
writes PNGs. Every PNG is round-trip verified against the in-memory array before
the run is reported as successful, because a silently lossy capture would look
exactly like a bad OCR result three steps later.

Usage (run it yourself so you can see the countdown while alt-tabbed to SC):

    python capture_overlay.py --label login-black --delay 12 --shots 5

Credit: Mallachi
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

import mss
import numpy as np
from PIL import Image


CAPTURE_ROOT = Path(__file__).parent / "captures"


def grab_rgb(sct: mss.base.MSSBase, monitor: dict[str, int]) -> np.ndarray:
    """Grab one frame as an RGB array.

    Uses mss's documented `.rgb` byte order rather than reading the raw BGRA
    buffer, so the channel order is not an assumption of ours. On monochrome
    text a swap would be invisible, which is exactly why it is not guessed at.

    Args:
        sct: An open mss instance.
        monitor: An entry from `sct.monitors`.

    Returns:
        Array of shape (height, width, 3), dtype uint8, channel order RGB.
    """
    shot = sct.grab(monitor)
    image = Image.frombytes("RGB", shot.size, shot.rgb)
    return np.asarray(image)


def save_verified_png(frame: np.ndarray, path: Path) -> None:
    """Write a PNG and prove it round-trips bit-for-bit.

    Args:
        frame: RGB array to write.
        path: Destination path.

    Raises:
        RuntimeError: If the reloaded PNG differs from the array written.
    """
    Image.fromarray(frame, mode="RGB").save(path, format="PNG", optimize=False)
    reloaded = np.asarray(Image.open(path).convert("RGB"))
    if reloaded.shape != frame.shape or not np.array_equal(reloaded, frame):
        raise RuntimeError(f"PNG round-trip mismatch for {path}, capture is NOT lossless")


def describe_strip(frame: np.ndarray, rows: int = 120, cols: int = 900) -> str:
    """Summarise the top-right corner where the overlay is drawn.

    Args:
        frame: Full-screen RGB array.
        rows: Height of the corner region to summarise.
        cols: Width of the corner region to summarise.

    Returns:
        A one-line human summary of ink presence in that corner.
    """
    corner = frame[:rows, -cols:]
    luma = corner.max(axis=2)
    lit = int((luma > 40).sum())
    return (
        f"top-right {rows}x{cols}: max={int(luma.max())} "
        f"mean={luma.mean():.2f} pixels>40={lit}"
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--label", required=True, help="name for this capture set")
    parser.add_argument("--delay", type=float, default=12.0, help="seconds before shot 1")
    parser.add_argument("--shots", type=int, default=5, help="number of frames")
    parser.add_argument("--interval", type=float, default=1.0, help="seconds between")
    parser.add_argument("--monitor", type=int, default=1, help="mss monitor index")
    args = parser.parse_args(argv)

    out_dir = CAPTURE_ROOT / args.label
    out_dir.mkdir(parents=True, exist_ok=True)

    with mss.mss() as sct:
        print("Monitors:")
        for index, mon in enumerate(sct.monitors):
            tag = " <- selected" if index == args.monitor else ""
            print(f"  [{index}] {mon}{tag}")
        if args.monitor >= len(sct.monitors):
            print(f"ERROR: no monitor {args.monitor}")
            return 1
        monitor = sct.monitors[args.monitor]

        print(f"\nAlt-tab to Star Citizen now. Capturing in {args.delay:.0f}s.")
        remaining = args.delay
        while remaining > 0:
            print(f"  {remaining:.0f}...", flush=True)
            time.sleep(min(1.0, remaining))
            remaining -= 1.0

        frames: list[np.ndarray] = []
        for shot_index in range(args.shots):
            frame = grab_rgb(sct, monitor)
            path = out_dir / f"shot_{shot_index:02d}.png"
            save_verified_png(frame, path)
            frames.append(frame)
            print(f"  saved {path.name}  {frame.shape[1]}x{frame.shape[0]}  "
                  f"{describe_strip(frame)}")
            if shot_index + 1 < args.shots:
                time.sleep(args.interval)

    print("\nAll PNGs round-trip verified lossless.")

    # Frame-to-frame determinism on a static screen. On the login screen the
    # only moving thing should be the frame counter, so a large differing-pixel
    # count here is a finding, not noise to be averaged away.
    if len(frames) > 1:
        base = frames[0]
        print("\nFrame-to-frame differences against shot_00 (full screen):")
        for shot_index, frame in enumerate(frames[1:], start=1):
            differing = int((frame != base).any(axis=2).sum())
            print(f"  shot_{shot_index:02d}: {differing} differing pixels")

    print(f"\nCapture set: {out_dir}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
