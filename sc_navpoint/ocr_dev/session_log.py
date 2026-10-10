"""Passive overlay logger: capture a whole play session for offline analysis.

DEV TOOL, not a runtime file.

WHAT THIS MEASURES, and it is not accuracy. Accuracy needs a truth string per
frame, and hand transcription is the step this project avoids because it has
introduced errors three times. What a passive session DOES answer, and nobody
has the number yet, is the REFUSAL RATE in real play: the reader reads a dark
interior perfectly and a blown sky not at all, and what decides whether it
replaces the Vision call or merely supplements it is which of those ordinary
flying actually looks like.

THREE DESIGN CHOICES, each for a measured reason:

  Strips, not screens. Everything in the reader's geometry is measured from the
  RIGHT edge of the frame, so a right-aligned crop decodes byte-identically to
  the full screen (verified on three very different backgrounds). That turns
  11 MB per frame into about 170 KB, so a 500-frame session is roughly 85 MB
  rather than 5.5 GB.

  Raw pixels, nothing else. No resize, no autocontrast. The reader solves for
  the background by least squares in raw 0-255 units, so a contrast stretch
  changes the quantity being solved for and a resample mixes neighbouring cells.
  Measured: the frame that reads 8 of 8 rows natively reads 0 of 8 after either.

  Unchanged frames are dropped, but NOT by hashing the whole strip. The overlay
  carries its own FPS and frametime line, which changes every single frame, so a
  whole-strip hash would call every frame distinct and never fire. The test is
  per row over the block columns, and which row is telemetry is LEARNED from its
  change rate rather than assumed, because a count alone cannot tell "the
  frametime ticked" from "one coordinate digit changed". A frame is kept when
  any non-telemetry row changed. That works because the background is part of
  the same pixels, so a moving player or a moving scene changes every row, while
  standing still in a static scene changes only the telemetry. The reader is
  deterministic on identical pixels, so storing those twice is one sample
  costing two files, and it would make the session look more varied than it is.

Usage, from `skills/sc_navpoint/ocr_dev`:

    python session_log.py --label session-01 --interval 3 --minutes 90

Then play normally. Stop with Ctrl+C, or let it reach the limit. To close the
alphabet gap in the same session, at some point stand on a body's surface with
`Zone: OOC_` visible against a DARK interior, at TWO different locations, and
hold still for a few seconds each; `session_report.py` finds those frames.

Credit: Mallachi
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import time
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
from PIL import Image
from mss import mss


CAPTURE_ROOT = Path(__file__).parent / "captures"

# IMPORTED, never mirrored. These constants used to be copied here, and on
# 2026-07-31 the reader's block grew from 600 to 660 while this file kept
# grabbing a 640 px strip, so the dev corpus silently stopped containing the
# whole block the runtime reads. A capture tool that disagrees with the reader
# produces a corpus that measures the wrong thing.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from overlay_reader import (  # noqa: E402
    BLOCK_TOP,
    BLOCK_WIDTH,
    MAX_ROWS as ROWS,
    RIGHT_MARGIN,
    ROW_HEIGHT,
    ROW_PITCH,
)

# Right-aligned crop that preserves the reader's geometry exactly, with slack.
STRIP_WIDTH = BLOCK_WIDTH + RIGHT_MARGIN + 8
STRIP_HEIGHT = BLOCK_TOP + ROW_PITCH * ROWS + ROW_HEIGHT + 6


def foreground_title() -> str:
    """Title of the focused window, or empty when it cannot be determined."""
    try:
        import ctypes

        user32 = ctypes.windll.user32
        handle = user32.GetForegroundWindow()
        length = user32.GetWindowTextLengthW(handle)
        buffer = ctypes.create_unicode_buffer(length + 1)
        user32.GetWindowTextW(handle, buffer, length + 1)
        return buffer.value
    except Exception:  # noqa: BLE001 - any failure means "cannot tell", not "no"
        return ""


def row_hashes(strip: np.ndarray) -> list[str]:
    """One digest per overlay row, over the block columns only.

    Per row rather than per strip because the overlay's own FPS and frametime
    line changes every frame: a whole-strip hash would report every frame as new
    and the deduplication would never fire once.
    """
    right = strip.shape[1] - RIGHT_MARGIN + 1
    left = max(right - BLOCK_WIDTH, 0)
    out = []
    for index in range(ROWS):
        top = BLOCK_TOP + index * ROW_PITCH
        band = strip[top:top + ROW_HEIGHT, left:right]
        if band.shape[0] < ROW_HEIGHT:
            break
        out.append(hashlib.sha1(band.tobytes()).hexdigest())
    return out


def changed_rows(current: list[str], previous: list[str] | None) -> set[int]:
    """Which overlay rows differ from the previous frame."""
    if previous is None or len(current) != len(previous):
        return set(range(len(current)))
    return {i for i, (a, b) in enumerate(zip(current, previous)) if a != b}


# The volatile row is LEARNED rather than assumed, because counting changed rows
# cannot tell "the frametime ticked" from "one coordinate digit changed": both
# are one row. A row that changes on virtually every frame is telemetry by
# definition, and after this many comparisons that rate is trustworthy.
VOLATILE_WARMUP = 20
VOLATILE_RATE = 0.9


class Deduplicator:
    """Keeps a frame only when something other than telemetry changed.

    Learns which rows are telemetry from their change rate instead of assuming a
    row index, because which lines appear shifts with context (in a base, on
    foot, in a ship, seated) and so does the position of the FPS line.

    Until the warm-up completes it keeps everything, which is the safe
    direction: a corpus with duplicates is an annoyance, a corpus missing the
    frames that mattered is a wasted play session.
    """

    def __init__(self, warmup: int = VOLATILE_WARMUP, rate: float = VOLATILE_RATE):
        self.warmup = warmup
        self.rate = rate
        self.previous: list[str] | None = None
        self.comparisons = 0
        self.row_changes: Counter[int] = Counter()

    def volatile(self) -> set[int]:
        """Rows that change on virtually every frame, so telemetry."""
        if self.comparisons < self.warmup:
            return set()
        return {row for row, count in self.row_changes.items()
                if count >= self.rate * self.comparisons}

    def should_keep(self, hashes: list[str]) -> bool:
        changed = changed_rows(hashes, self.previous)
        first = self.previous is None
        if not first:
            self.comparisons += 1
            for row in changed:
                self.row_changes[row] += 1
        keep = first or bool(changed - self.volatile())
        if keep:
            self.previous = hashes
        return keep


def grab_strip(sct, monitor: dict) -> tuple[np.ndarray, tuple[int, int]]:
    """Grab one screen and return (strip, full screen size).

    The strip is a view onto raw BGRA converted to RGB, with no resampling and
    no tone mapping of any kind.
    """
    shot = sct.grab(monitor)
    image = Image.frombytes("RGB", shot.size, shot.bgra, "raw", "BGRX")
    frame = np.asarray(image)
    strip = frame[0:STRIP_HEIGHT, -STRIP_WIDTH:].copy()
    return strip, (frame.shape[1], frame.shape[0])


def save_lossless(strip: np.ndarray, path: Path) -> None:
    """Write a PNG and prove it round-trips, before any run counts as data.

    Raises:
        RuntimeError: If the reloaded PNG differs from the array written.
    """
    Image.fromarray(strip, mode="RGB").save(path, format="PNG", optimize=False)
    reloaded = np.asarray(Image.open(path).convert("RGB"))
    if reloaded.shape != strip.shape or not np.array_equal(reloaded, strip):
        raise RuntimeError(f"PNG round-trip mismatch for {path}, capture is NOT lossless")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--label", required=True, help="folder name under captures/")
    parser.add_argument("--interval", type=float, default=3.0, help="seconds between grabs")
    parser.add_argument("--minutes", type=float, default=0.0, help="stop after N minutes")
    parser.add_argument("--max-frames", type=int, default=500)
    parser.add_argument("--monitor", type=int, default=1)
    parser.add_argument("--delay", type=float, default=10.0,
                        help="seconds before the first grab, to alt-tab back")
    parser.add_argument("--keep-all", action="store_true",
                        help="store every grab, including ones whose only "
                             "change was the telemetry row")
    parser.add_argument("--window", default="Star Citizen",
                        help="only capture while this text is in the focused "
                             "window title; pass an empty string to capture "
                             "whatever is on screen")
    args = parser.parse_args(argv)

    out = CAPTURE_ROOT / args.label
    out.mkdir(parents=True, exist_ok=True)
    index_path = out / "index.jsonl"

    print(f"Logging to {out}")
    print(f"  every {args.interval}s, up to {args.max_frames} distinct frames"
          + (f", stopping after {args.minutes} minutes" if args.minutes else ""))
    if args.window:
        probe = foreground_title()
        if probe:
            print(f"  capturing only while the focused window is {args.window!r} "
                  f"(now: {probe!r})")
        else:
            print("  WINDOW FILTER INERT: the focused window title could not be "
                  "read, so everything on screen will be captured.")
    print(f"  starting in {args.delay:.0f}s, stop any time with Ctrl+C\n")
    time.sleep(args.delay)

    kept = 0
    unchanged = 0
    not_in_game = 0
    grabs = 0
    started = time.monotonic()
    dedup = Deduplicator()

    try:
        with mss() as sct, index_path.open("a", encoding="utf-8") as index:
            monitor = sct.monitors[min(args.monitor, len(sct.monitors) - 1)]
            while kept < args.max_frames:
                if args.minutes and (time.monotonic() - started) > args.minutes * 60:
                    print("\nTime limit reached.")
                    break
                # Alt-tabbing must not fill the corpus with desktop, and what is
                # on the other screen is nobody's business. FAILS OPEN on
                # purpose: an empty title means the probe could not tell, and a
                # guard that silently captures nothing for ninety minutes is a
                # far worse outcome than a few frames of desktop.
                title = foreground_title()
                if args.window and title and args.window.lower() not in title.lower():
                    not_in_game += 1
                    time.sleep(args.interval)
                    continue
                strip, screen = grab_strip(sct, monitor)
                grabs += 1
                hashes = row_hashes(strip)
                changed = changed_rows(hashes, dedup.previous)
                if not dedup.should_keep(hashes) and not args.keep_all:
                    unchanged += 1
                else:
                    name = f"frame_{kept:04d}.png"
                    save_lossless(strip, out / name)
                    index.write(json.dumps({
                        "file": name,
                        "seq": kept,
                        "grab": grabs,
                        "utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                        "mono": round(time.monotonic() - started, 3),
                        "screen": list(screen),
                        "rows": hashes,
                        "changed": sorted(changed),
                    }) + "\n")
                    index.flush()
                    kept += 1
                    if kept % 10 == 0:
                        print(f"  {kept} frames kept, {unchanged} unchanged skipped",
                              end="\r", flush=True)
                time.sleep(args.interval)
    except KeyboardInterrupt:
        print("\nStopped by user.")

    elapsed = time.monotonic() - started
    size = sum(p.stat().st_size for p in out.glob("frame_*.png")) / 1e6
    print(f"\n{kept} distinct frames kept, {unchanged} unchanged frames skipped, "
          f"{not_in_game} grabs skipped with the game unfocused, "
          f"{grabs} grabs over {elapsed / 60:.1f} minutes, {size:.0f} MB on disk.")
    print(f"Next: python session_report.py --label {args.label}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
