"""Analyse a logged session: refusal rate, continuity breaks, harvest candidates.

DEV TOOL, not a runtime file.

FOUR QUESTIONS, and the corpus is unlabelled, so each is answered by something
that needs no human transcription.

  1. REFUSAL RATE BY SCENE. The headline number the session exists to produce:
     what fraction of real play the local reader can actually read, split by
     background regime, plus which gate did the refusing. A reader that is
     perfect on 5 per cent of frames replaces nothing.

  2. CONTINUITY, which is free ground truth. Consecutive frames while moving
     must give continuous positions. A dropped unit suffix is a factor of 1000,
     a sign flip is a mirror, and a digit substitution is a jump: all three
     appear as discontinuities in a track without anyone reading a screenshot.
     This is the only check here that can catch a CONFIDENT WRONG value, which
     is the failure class that matters, so it is worth more than the rest.

  3. HARVEST CANDIDATES for the alphabet gap. `k` phase 0, `O` phase 0 and `u`
     phase 1 are missing, all three live in the `OOC_` line, and harvesting a
     coverage map needs a channel whose background sits near zero. So the report
     ranks frames that carry a candidate OOC line by how dark they are.

  4. SELF-CONSISTENCY of the pair of lines that duplicate each other. Root and
     SolarSystem carry the same digits, so disagreement is a caught misread.
     Never call it independent verification: both lines share x positions,
     phases and background, and on a bright capture they decoded the SAME wrong
     coordinate.

Usage:

    python session_report.py --label session-01
    python session_report.py --label session-01 --harvest-top 20

Credit: Mallachi
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter
from pathlib import Path

import numpy as np
from PIL import Image

SKILL_DIR = Path(__file__).resolve().parent.parent
if str(SKILL_DIR) not in sys.path:
    sys.path.insert(0, str(SKILL_DIR))

import overlay_fields as fields  # noqa: E402
import overlay_reader as ov  # noqa: E402


CAPTURE_ROOT = Path(__file__).parent / "captures"
GLYPHS = SKILL_DIR / "overlay_glyphs.npz"

# Applied to BODY-FIXED positions only. A ship in atmosphere tops out well under
# this, and quantum travel cannot happen inside a body frame without leaving it.
# System-frame positions are deliberately exempt: out there a real quantum jump
# is enormous and perfectly legitimate, so a distance bound would flag normal
# play and teach everyone to ignore the report.
SPEED_LIMIT_MS = 3000.0

# A dropped or invented unit suffix moves ONE axis by a factor of 1000 while its
# neighbours barely move. That signature is what makes it findable with no truth
# strings at all, and it is the exact failure the mandatory suffix exists to stop.
UNIT_ERROR_LOW = 300.0
UNIT_ERROR_HIGH = 3000.0
# Below this the ratio test is meaningless: a coordinate crossing near zero
# produces huge ratios from ordinary motion.
UNIT_ERROR_FLOOR_M = 100.0
# The other axes must be roughly continuous for a jump to look like a unit error
# rather than like the player having moved.
UNIT_ERROR_QUIET = 2.0

# The OOC token as it looks when the three missing glyphs are misread: three
# characters then an underscore. Deliberately loose on the characters, since the
# whole point is that we cannot yet read them correctly, but anchored on the
# length and the underscore.
_CANDIDATE_OOC = re.compile(r"^Zone:\s+([A-Za-z0-9?]{3})_")


def looks_like_ooc(token: str) -> bool:
    """True when a three-character zone prefix could be a misread `OOC`.

    Written as a similarity test rather than an allowlist because the reason
    this frame is interesting is precisely that `O` at phase 0 has no template,
    so the token will NOT read as `OOC`. Confirmed misreads include `OuC`. The
    third position must still be `C` or a refusal, which is what keeps ship
    zones (`rsi_`, `EXM_`) out.
    """
    if len(token) != 3:
        return False
    if token[2] not in ("C", "c", "?"):
        return False
    hits = sum(1 for i, ch in enumerate(token) if ch in ("?", "OOC"[i], "ooc"[i]))
    return hits >= 2


def scene_of(strip: np.ndarray) -> str:
    """Bucket a frame by what its background does to the reader.

    Bright kills the signal outright; structured (an ice field, a starfield, a
    city) leaves the mean low while local contrast is high, which is the regime
    that forced the ink guard's threshold to become hybrid.
    """
    left, right = ov.block_columns(strip.shape[1])
    block = strip[ov.BLOCK_TOP:ov.BLOCK_TOP + 12 * ov.ROW_PITCH, left:right]
    if block.size == 0:
        return "empty"
    mean = float(np.mean(block))
    clipped = float(np.mean(np.any(block >= ov.CLIP_LEVEL, axis=2)))
    # Local contrast, measured the way the ink guard measures it.
    cells = block[:, : (block.shape[1] // 8) * 8].reshape(block.shape[0], -1, 8, 3)
    spread = float(np.median(cells.max(axis=2) - cells.min(axis=2)))
    if clipped >= 0.15:
        return "blown"
    if mean >= 140:
        return "bright"
    if spread >= 25:
        return "structured"
    if mean <= 45:
        return "dark"
    return "mid"


def load_times(label: str) -> dict[str, float]:
    """Seconds since the session started, per frame, from the logger's index."""
    path = CAPTURE_ROOT / label / "index.jsonl"
    if not path.exists():
        return {}
    times = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        entry = json.loads(line)
        if "mono" in entry:
            times[entry["file"]] = float(entry["mono"])
    return times


def read_all(label: str, limit: int | None) -> list[dict]:
    """Decode every frame of a session, keeping what each analysis needs."""
    folder = CAPTURE_ROOT / label
    frames = sorted(folder.glob("frame_*.png"))
    if limit:
        frames = frames[:limit]
    if not frames:
        raise SystemExit(f"No frames in {folder}")
    reader = ov.OverlayReader(GLYPHS)
    out = []
    for n, path in enumerate(frames):
        strip = np.asarray(Image.open(path).convert("RGB")).astype(np.float64)
        usable, why = ov.capture_is_usable(strip)
        record = {
            "file": path.name, "scene": scene_of(strip),
            "usable": usable, "reason": "", "rows": [], "payload": None,
        }
        if usable:
            _, _, rows = reader.read(strip, 10)
            record["rows"] = rows
            record["payload"] = fields.payload_from_rows(rows)
            if record["payload"] is None:
                # "unreadable" used to hide four different causes, which made
                # the refusal column useless for deciding what to fix next.
                position = any(
                    row["trusted"] and "SolarSystem" in (row["text"] or "")
                    for row in rows
                )
                root = any(
                    row["trusted"] and (row["text"] or "").startswith("Zone: Root ")
                    for row in rows
                )
                if not position:
                    record["reason"] = "no position row"
                elif not root:
                    record["reason"] = "no Root cross-check"
                else:
                    record["reason"] = "OOC not refuted"
        else:
            record["reason"] = "precondition: " + why
        out.append(record)
        if (n + 1) % 25 == 0:
            print(f"  read {n + 1}/{len(frames)}", end="\r", flush=True)
    print(" " * 40, end="\r")
    return out


def metres(payload: dict) -> tuple[float, float, float] | None:
    """Convert a payload's raw tokens to metres using the shipped parser."""
    from scanner import NavPointScanner

    raw = payload.get("pos_raw") or payload.get("system_pos_raw")
    coords = NavPointScanner._coords_from_pos_raw(raw)
    if coords is None:
        return None
    return coords["x"], coords["y"], coords["z"]


def frame_key(payload: dict) -> str:
    """What a position is expressed relative to; positions never mix frames."""
    if payload.get("local_frame"):
        return "local:" + str(payload.get("body_token"))
    return "system:" + str(payload.get("system_zone_id"))


def _reason_counts(group: list[dict]) -> tuple[int, int, int, int]:
    """Frames refused, split by cause. The four are mutually exclusive."""
    clipped = sum(1 for r in group if not r["usable"])
    norow = sum(1 for r in group if r["reason"] == "no position row")
    noroot = sum(1 for r in group if r["reason"] == "no Root cross-check")
    gated = sum(1 for r in group if r["reason"] == "OOC not refuted")
    return clipped, norow, noroot, gated


def report_refusals(records: list[dict]) -> None:
    print("\n=== 1. Outcome by scene")
    print("A REFUSAL IS A COST, NOT A FAILURE: it buys one Vision fallback at "
          "about\n3 s and 3000 tokens. The failure line is section 1b.")
    scenes = sorted({r["scene"] for r in records})
    print(f"\n{'scene':12s} {'frames':>7s} {'usable':>7s} {'rate':>7s}   "
          f"{'clipped':>8s} {'no row':>7s} {'no Root':>8s} {'gated':>6s}")
    for scene in scenes:
        group = [r for r in records if r["scene"] == scene]
        ok = sum(1 for r in group if r["payload"] is not None)
        clipped, norow, noroot, gated = _reason_counts(group)
        print(f"{scene:12s} {len(group):7d} {ok:7d} {ok / len(group):6.1%}   "
              f"{clipped:8d} {norow:7d} {noroot:8d} {gated:6d}")
    ok = sum(1 for r in records if r["payload"] is not None)
    clipped, norow, noroot, gated = _reason_counts(records)
    print(f"{'TOTAL':12s} {len(records):7d} {ok:7d} {ok / len(records):6.1%}   "
          f"{clipped:8d} {norow:7d} {noroot:8d} {gated:6d}")
    assert ok + clipped + norow + noroot + gated == len(records), (
        "the outcome columns must account for every frame"
    )

    # ---- 1b. The number the session actually exists to drive to zero -------
    emitted = [r for r in records if r["payload"] is not None]
    unverified = 0
    for record in emitted:
        payload = record["payload"]
        if payload.get("local_frame"):
            continue
        if payload.get("system_pos_raw") != payload.get("root_pos_raw"):
            unverified += 1
    print("\n=== 1b. FAILURE EXPOSURE (target zero)")
    print(f"  emissions WITHOUT an independent cross-check : {unverified}")
    print(f"  emissions cross-checked and consistent       : "
          f"{len(emitted) - unverified}")
    print("  Detected wrong values cannot be counted here: this corpus has no")
    print("  truth strings. Section 2's continuity check is the only test that")
    print("  can catch a confident WRONG value, so read it as the failure line.")

    trusted = Counter()
    for record in records:
        trusted[sum(1 for row in record["rows"] if row["trusted"])] += 1
    print("\nTrusted rows per frame: "
          + ", ".join(f"{k}:{v}" for k, v in sorted(trusted.items())))


def unit_scale_jump(before: tuple, after: tuple) -> int | None:
    """The axis that moved by about 1000x while the others held still, if any.

    Requires all three conditions, because any one alone fires on ordinary play:
    the axis must be large enough that the ratio means something, the ratio must
    land in the 1000x band, and the OTHER axes must be roughly continuous.

    Validated against known positives and negatives rather than trusted to be
    silent, since a broken detector and a clean corpus look identical: it fires
    on a dropped `k` in either direction and stays silent on walking, on fast
    flight, and on an axis crossing zero. A SIGN FLIP is deliberately not this
    detector's job (it leaves the magnitude untouched, which is why the
    magnitude identity is blind to it); the speed check below catches it,
    because a mirrored coordinate is twice the axis value away in one step.
    """
    for axis in range(3):
        old, new = before[axis], after[axis]
        if abs(old) < UNIT_ERROR_FLOOR_M or abs(new) < UNIT_ERROR_FLOOR_M:
            continue
        ratio = abs(new / old)
        if not (UNIT_ERROR_LOW < ratio < UNIT_ERROR_HIGH
                or UNIT_ERROR_LOW < 1 / ratio < UNIT_ERROR_HIGH):
            continue
        others = [i for i in range(3) if i != axis]
        if all(abs(after[i] - before[i]) <= max(abs(before[i]), 1.0) * UNIT_ERROR_QUIET
               for i in others):
            return axis
    return None


def report_continuity(records: list[dict], times: dict[str, float]) -> None:
    """Free ground truth: a track that jumps is a track that was misread."""
    print("\n=== 2. Continuity breaks "
          "(the only check here that catches a CONFIDENT WRONG value)")
    previous = None
    flagged = checked = timed = 0
    for record in records:
        payload = record["payload"]
        position = metres(payload) if payload else None
        if position is None:
            previous = None  # a gap is not a jump
            continue
        current = (frame_key(payload), position, record["file"])
        if previous and previous[0] == current[0]:
            checked += 1
            axis = unit_scale_jump(previous[1], current[1])
            if axis is not None:
                flagged += 1
                print(f"  UNIT-SCALE JUMP on axis {'xyz'[axis]}: "
                      f"{previous[2]} -> {current[2]}  "
                      f"{previous[1][axis]:.2f} -> {current[1][axis]:.2f}")
            elif current[0].startswith("local:"):
                # Speed is only meaningful in a body-fixed frame, and only when
                # the log recorded when each frame was taken.
                dt = times.get(current[2], 0.0) - times.get(previous[2], 0.0)
                if dt > 0:
                    timed += 1
                    step = sum((current[1][i] - previous[1][i]) ** 2
                               for i in range(3)) ** 0.5
                    if step / dt > SPEED_LIMIT_MS:
                        flagged += 1
                        print(f"  IMPOSSIBLE SPEED  {previous[2]} -> "
                              f"{current[2]}  {step:.0f} m in {dt:.1f} s "
                              f"({step / dt:.0f} m/s)")
        previous = current
    print(f"  {checked} consecutive same-frame pairs checked "
          f"({timed} of them also speed-checked), {flagged} flagged.")
    if not checked:
        print("  Nothing to check: no two consecutive frames shared a coordinate "
              "frame.")
    if checked and not times:
        print("  No index.jsonl timestamps, so only the unit-scale test ran.")


def report_crosscheck(records: list[dict]) -> None:
    print("\n=== 3. Root against SolarSystem (a tripwire, never a verification)")
    both = agree = 0
    for record in records:
        payload = record["payload"] or {}
        if "system_pos_raw" in payload and "root_pos_raw" in payload:
            both += 1
            agree += payload["system_pos_raw"] == payload["root_pos_raw"]
    if both:
        print(f"  {agree} of {both} frames carried both lines and they agreed "
              f"digit for digit.")
        if agree != both:
            print("  DISAGREEMENT FOUND: those frames are misreads the floor let "
                  "through, and they are worth inspecting by hand.")
    else:
        print("  No frame carried both lines.")


def report_harvest(records: list[dict], top: int) -> None:
    """Rank frames that could close the alphabet gap."""
    print("\n=== 4. Harvest candidates for the alphabet gap "
          "(`k` phase 0, `O` phase 0, `u` phase 1)")
    candidates = []
    for record in records:
        for row in record["rows"]:
            if row["kind"] != "zone":
                continue
            m = _CANDIDATE_OOC.match(row["text"])
            if m and looks_like_ooc(m.group(1)):
                candidates.append((record["scene"], record["file"], row["text"][:64],
                                   row["cost"], row["trusted"]))
                break
    if not candidates:
        print("  None. No frame in this session carried a line shaped like `OOC_`,")
        print("  so the gap is still open and the surface captures are still owed.")
        return
    order = {"dark": 0, "mid": 1, "structured": 2, "bright": 3, "blown": 4}
    candidates.sort(key=lambda c: (order.get(c[0], 9), c[3]))
    print(f"  {len(candidates)} frames carry a candidate OOC line. Darkest first, "
          f"since harvesting needs a near-zero channel:")
    for scene, name, text, cost, trusted in candidates[:top]:
        flag = "trusted" if trusted else "REFUSED"
        print(f"    {scene:11s} {name}  cost {cost:5.1f}  {flag}  {text}")
    print("  Feed the best DARK ones to harvest.py, then re-run measure.py.")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--label", required=True)
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--harvest-top", type=int, default=12)
    args = parser.parse_args(argv)

    if not GLYPHS.exists():
        raise SystemExit(f"Glyph bank missing: {GLYPHS}")
    print(f"Reading session {args.label}")
    records = read_all(args.label, args.limit)
    times = load_times(args.label)
    report_refusals(records)
    report_continuity(records, times)
    report_crosscheck(records)
    report_harvest(records, args.harvest_top)
    print("\nNOT MEASURED HERE, and it must not be claimed: character accuracy. "
          "\nThis corpus has no truth strings. Everything above is refusal "
          "behaviour and\nself-consistency, which can prove a misread but never "
          "prove a correct read.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
