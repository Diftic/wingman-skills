"""Replay the retained lossless corpus through the schema-1 coordinate stack.

DEV TOOL, not a runtime file. Wave 5 step 1 of
`COORDINATE_STACK_IMPLEMENTATION_PLAN.md`.

WHY IT READS PIXELS. Every coordinate-stack fixture shipped so far is a
transcription or a stored decoded row, which is the same evidence tier the
`OOC_` branch had when the ledger recorded it as never having run on real
pixels. So this decodes each retained PNG with the SHIPPING reader, at the
SHIPPING row window (`overlay_reader.POSITION_ROWS`), and feeds the decoded rows
to `overlay_fields.stack_from_rows` untouched.

FIVE QUESTIONS, in the order they decide anything:

  1. DOES IT PARSE AT ALL on real pixels, per session, with the gate that
     refused named. A parser that is perfect on transcriptions and refuses every
     real frame has not been tested by its unit tests.

  2. WHAT CHANGED against the legacy `payload_from_rows`, as a 2x2. The one
     cell that matters is stack-accepts-while-legacy-refuses: that is the
     claimed Pyro 3 surface behaviour change, and `surface-01` is where it must
     appear if it is real.

  3. IS THE STACK'S ROOT THE SAME NUMBER the legacy payload emitted, wherever
     both accepted. They read the same row through different regexes, so a
     disagreement is a defect in one of them.

  4. CONTINUITY, the only check here that can catch a CONFIDENT WRONG value.
     Consecutive accepted frames in one session must give a continuous Root
     track; a dropped unit suffix is a factor of 1000 and shows as a jump.

  5. WHAT THE LOCAL CANDIDATE ACTUALLY IS, per session: the outermost pre-Solar
     row, its depth, and how often it was present. This is EVIDENCE TOWARD the
     gate in the plan and settles NOTHING on its own, because most of these
     sessions are one stationary pose and the plan says repeated captures from
     one pose are not independent evidence.

Usage:

    python stack_replay.py                       # whole corpus
    python stack_replay.py --label surface-01    # one session
    python stack_replay.py --json out.json       # machine-readable dump

Credit: Mallachi
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

import numpy as np
from PIL import Image

SKILL_DIR = Path(__file__).resolve().parent.parent
if str(SKILL_DIR) not in sys.path:
    sys.path.insert(0, str(SKILL_DIR))

import coordinate_stack  # noqa: E402
import overlay_fields as fields  # noqa: E402
import overlay_reader as ov  # noqa: E402


CAPTURE_ROOT = Path(__file__).parent / "captures"
GLYPHS = SKILL_DIR / "overlay_glyphs.npz"

# NO ABSOLUTE JUMP THRESHOLD IS APPLIED, deliberately. The corpus contains
# quantum travel, whose legitimate per-frame displacement is not measured
# anywhere in this project, so any cutoff would be an invented number deciding
# whether a coordinate is wrong. Section 4 reports the observed extremes and
# flags only the unit-scale signature, which needs no threshold on distance.

# The unit-error signature: one axis moves by about 1000x while its neighbours
# hold still. Same constants as `session_report.py`, which found this class of
# error worth its own test.
UNIT_ERROR_LOW = 300.0
UNIT_ERROR_HIGH = 3000.0
UNIT_ERROR_FLOOR_M = 100.0
UNIT_ERROR_QUIET = 2.0


def gate_of(reason: str) -> str:
    """The stable GATE_* id at the front of a refusal reason, or a placeholder."""
    if not reason:
        return ""
    head = reason.split(":", 1)[0].strip()
    return head or "unnamed"


def load_times(label: str) -> dict:
    """Seconds since the session started, per frame, from the logger's index.

    The key is `mono`, the logger's monotonic clock. Seven sessions have no
    `index.jsonl` at all and simply return nothing, which section 4 reports
    rather than papering over.
    """
    path = CAPTURE_ROOT / label / "index.jsonl"
    if not path.exists():
        return {}
    times = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        record = json.loads(line)
        name = record.get("file")
        stamp = record.get("mono")
        if name is not None and stamp is not None:
            times[str(name)] = float(stamp)
    return times


def replay_frame(reader, path: Path) -> dict:
    """One frame, decoded once and asked both questions.

    The reader runs ONCE per frame and both parsers see the same decoded rows,
    so any difference between them is the parsers' and not the decode's.
    """
    frame = np.asarray(Image.open(path).convert("RGB")).astype(np.float64)
    usable, why = ov.capture_is_usable(frame)
    left, right = ov.block_columns(frame.shape[1])
    record = {
        "file": path.name,
        "width": int(frame.shape[1]),
        # What this frame can hold, against the 88 the runtime reads. A capture
        # narrower than the block is CLIPPED, and three sessions in this corpus
        # were taken that way, so "the shipping window" is not true of them.
        # Cells are spaced at PITCH, not CELL_WIDTH: 88 * 7.5 == BLOCK_WIDTH.
        "cells": int((right - left) // ov.PITCH),
        "usable": usable,
        "unusable_reason": "" if usable else why,
        "stack": None,
        "stack_gate": "",
        "legacy": None,
        "legacy_gate": "",
        "legacy_local": None,
        "candidate_name": None,
        "candidate_depth": None,
        "candidate_xyz": None,
        "nested_names": [],
    }
    if not usable:
        record["stack_gate"] = "precondition_unusable"
        record["legacy_gate"] = "precondition_unusable"
        return record

    _, _, rows = reader.read(frame, ov.POSITION_ROWS)
    stack, stack_reason = fields.stack_from_rows(rows)
    legacy = fields.payload_from_rows(rows)

    record["stack_gate"] = gate_of(stack_reason)
    if legacy is None:
        record["legacy_gate"] = gate_of(fields.refusal_reason(rows))
    else:
        record["legacy_local"] = bool(legacy.get("local_frame"))
        record["legacy"] = {
            "local_frame": bool(legacy.get("local_frame")),
            "root_pos_raw": legacy.get("root_pos_raw"),
            "system_pos_raw": legacy.get("system_pos_raw"),
        }
    if stack is not None:
        candidate = stack.local_candidate
        record["stack"] = {
            "root": list(stack.root.xyz),
            "solar": list(stack.solar.xyz),
            "nested": len(stack.nested),
            "candidate_depth": stack.candidate_depth,
        }
        record["nested_names"] = [row.raw_name for row in stack.nested]
        if candidate is not None:
            record["candidate_name"] = candidate.raw_name
            record["candidate_depth"] = candidate.depth
            record["candidate_xyz"] = list(candidate.xyz)
    return record


def session_frames(folder: Path) -> list:
    """Every full-frame capture in a session folder, in file order.

    TWO NAMING SCHEMES, and missing the second silently dropped seven sessions
    from the first run of this tool: the logger writes `frame_NNNN.png`, while
    the seven earliest hand-taken sessions use `shot_NN.png`. Anything else in
    those folders is a debug crop (`rows_0.png`, `cells_row1.png`, `ends.png`)
    and is NOT a frame, so the two patterns are named explicitly rather than
    globbing `*.png`.
    """
    frames = sorted(folder.glob("frame_*.png"))
    return frames or sorted(folder.glob("shot_*.png"))


def replay_session(label: str, limit: int | None) -> dict:
    """Every retained frame of one session, in file order."""
    folder = CAPTURE_ROOT / label
    frames = session_frames(folder)
    if limit:
        frames = frames[:limit]
    if not frames:
        raise SystemExit(f"No frames in {folder}")
    reader = ov.OverlayReader(GLYPHS)
    return {
        "label": label,
        "times": load_times(label),
        "frames": [replay_frame(reader, path) for path in frames],
    }


def root_raw_to_m(raw) -> tuple | None:
    """A legacy payload's raw Root triple, converted with the shared converter."""
    if not raw or len(raw) != 3:
        return None
    values = [coordinate_stack.token_to_m(token) for token in raw]
    if any(value is None for value in values):
        return None
    return (values[0], values[1], values[2])


def unit_scale_jump(before: tuple, after: tuple) -> int | None:
    """The axis that moved about 1000x while the others held still, if any."""
    for axis in range(3):
        lo, hi = before[axis], after[axis]
        if min(abs(lo), abs(hi)) < UNIT_ERROR_FLOOR_M:
            continue
        ratio = max(abs(lo), abs(hi)) / max(min(abs(lo), abs(hi)), 1e-9)
        if not UNIT_ERROR_LOW <= ratio <= UNIT_ERROR_HIGH:
            continue
        others = [i for i in range(3) if i != axis]
        quiet = True
        for other in others:
            a, b = abs(before[other]), abs(after[other])
            if max(a, b) < UNIT_ERROR_FLOOR_M:
                continue
            if max(a, b) / max(min(a, b), 1e-9) > UNIT_ERROR_QUIET:
                quiet = False
        if quiet:
            return axis
    return None


def report_parse(sessions: list, out) -> None:
    out("\n=== 1. Does the stack parse on real pixels")
    out("A REFUSAL IS A COST, NOT A DEFECT. The defect line is section 3 and 4.")
    out(f"\n{'session':14s} {'cells':>5s} {'frames':>6s} {'usable':>6s} "
        f"{'stack':>6s} {'rate':>6s}   top refusal gates")
    for session in sessions:
        frames = session["frames"]
        usable = [f for f in frames if f["usable"]]
        ok = [f for f in frames if f["stack"] is not None]
        gates = Counter(f["stack_gate"] for f in frames if f["stack"] is None)
        top = ", ".join(f"{g} {n}" for g, n in gates.most_common(3))
        rate = f"{100.0 * len(ok) / len(frames):.0f}%" if frames else "-"
        cells = sorted({f["cells"] for f in frames})
        shown = ",".join(str(c) for c in cells)
        clip = "" if cells == [ov.CELLS_PER_ROW] else "  CLIPPED"
        out(f"{session['label']:14s} {shown:>5s} {len(frames):6d} "
            f"{len(usable):6d} {len(ok):6d} {rate:>6s}   {top}{clip}")


def report_delta(sessions: list, out) -> dict:
    out("\n=== 2. Stack against the legacy parser, on the same decoded rows")
    out("The cell that matters is stack-yes/legacy-no: the claimed Pyro 3")
    out("surface change. If it is real it appears in `surface-01`.")
    totals = Counter()
    out(f"\n{'session':14s} {'both':>6s} {'stack only':>10s} "
        f"{'legacy only':>11s} {'neither':>8s}")
    for session in sessions:
        counts = Counter()
        for frame in session["frames"]:
            has_stack = frame["stack"] is not None
            has_legacy = frame["legacy"] is not None
            key = ("both" if has_stack and has_legacy else
                   "stack" if has_stack else
                   "legacy" if has_legacy else "neither")
            counts[key] += 1
            totals[key] += 1
        out(f"{session['label']:14s} {counts['both']:6d} {counts['stack']:10d} "
            f"{counts['legacy']:11d} {counts['neither']:8d}")
    out(f"{'TOTAL':14s} {totals['both']:6d} {totals['stack']:10d} "
        f"{totals['legacy']:11d} {totals['neither']:8d}")
    if totals["legacy"]:
        out("\nLEGACY-ONLY FRAMES EXIST. The stack refused a capture the shipping")
        out("parser accepted, which is a REGRESSION unless every one is explained.")

    # WHICH legacy branch was exercised, because "no regression" is only as
    # broad as the branches the corpus actually reached. The local `OOC_` branch
    # accepting nothing at all is not a pass for it; it is an absence of
    # evidence, and `CORPUS.md` already records that no real-pixel `OOC_`
    # capture exists.
    local = sum(1 for s in sessions for f in s["frames"] if f["legacy_local"])
    space = sum(1 for s in sessions for f in s["frames"]
                if f["legacy_local"] is False)
    out(f"\nLegacy accepts by branch: space {space}, local/OOC_ {local}.")
    if not local:
        out("THE LEGACY LOCAL BRANCH ACCEPTED NOTHING, so no-regression is")
        out("established for the SPACE branch only.")
    return dict(totals)


def report_agreement(sessions: list, out) -> int:
    out("\n=== 3. The stack's Root against the legacy payload's Root")
    out("Same row, two regexes. Disagreement is a defect in one of them.")
    checked = mismatched = 0
    for session in sessions:
        for frame in session["frames"]:
            if frame["stack"] is None or frame["legacy"] is None:
                continue
            legacy_root = root_raw_to_m(frame["legacy"]["root_pos_raw"])
            if legacy_root is None:
                continue
            checked += 1
            gap = coordinate_stack.distance_m(
                tuple(frame["stack"]["root"]), legacy_root
            )
            if gap > 0.0:
                mismatched += 1
                out(f"  MISMATCH {session['label']}/{frame['file']}: {gap:.3f} m")
    out(f"\n  {checked} frames carried both, {mismatched} disagreed.")
    return mismatched


def report_continuity(sessions: list, out) -> int:
    out("\n=== 4. Root continuity between consecutive accepted frames")
    out("The ONLY check here that can catch a confident WRONG coordinate.")
    out("Flags are the unit-scale signature ONLY. Distance and speed are")
    out("REPORTED, not tested: no measured bound on legitimate quantum travel")
    out("exists in this project, so a cutoff would be an invented number.")
    checked = flagged = untimed = 0
    worst_gap = (0.0, "")
    worst_speed = (0.0, "")
    for session in sessions:
        times = session["times"]
        previous = None
        for frame in session["frames"]:
            if frame["stack"] is None:
                # A refusal breaks the chain rather than bridging it: the two
                # frames either side of a gap may be minutes and a quantum jump
                # apart, and calling that a discontinuity would bury the real
                # ones.
                previous = None
                continue
            current = tuple(frame["stack"]["root"])
            if previous is not None:
                checked += 1
                where = f"{session['label']} {previous[0]} -> {frame['file']}"
                gap = coordinate_stack.distance_m(previous[1], current)
                if gap > worst_gap[0]:
                    worst_gap = (gap, where)
                elapsed = None
                if previous[0] in times and frame["file"] in times:
                    elapsed = times[frame["file"]] - times[previous[0]]
                if elapsed is None or elapsed <= 0:
                    untimed += 1
                elif gap / elapsed > worst_speed[0]:
                    worst_speed = (gap / elapsed, where)
                axis = unit_scale_jump(previous[1], current)
                if axis is not None:
                    flagged += 1
                    out(f"  FLAG {where}: axis {axis} moved about 1000x while "
                        f"its neighbours held still")
            previous = (frame["file"], current)
    out(f"\n  {checked} consecutive accepted pairs checked, {flagged} flagged.")
    out(f"  {untimed} of them had no usable timestamp pair.")
    out(f"  largest displacement {worst_gap[0]:.4e} m at {worst_gap[1] or 'none'}")
    out(f"  largest implied speed {worst_speed[0]:.4e} m/s at "
        f"{worst_speed[1] or 'none'}")
    return flagged


def report_candidate(sessions: list, out) -> None:
    out("\n=== 5. What the local candidate actually is, per session")
    out("EVIDENCE ONLY. Most of these sessions are ONE stationary pose, and the")
    out("plan states repeated captures from one pose are not independent")
    out("evidence. Nothing here may flip LOCAL_TRACKING_ENABLED.")
    out(f"\n{'session':14s} {'stacks':>6s} {'with cand':>9s}   "
        f"depth: candidate name (count)")
    for session in sessions:
        stacks = [f for f in session["frames"] if f["stack"] is not None]
        withcand = [f for f in stacks if f["candidate_name"] is not None]
        names = Counter(
            f"{f['candidate_depth']}: {f['candidate_name']}" for f in withcand
        )
        shown = "; ".join(f"{k} ({v})" for k, v in names.most_common(4))
        out(f"{session['label']:14s} {len(stacks):6d} {len(withcand):9d}   {shown}")


def report_candidate_z(sessions: list, out) -> None:
    out("\n=== 6. Does the candidate's Z pass through to SolarSystem")
    out("DIAGNOSTIC, and NOT a proposal. Z pass-through is refuted as the")
    out("body-versus-container discriminator (`pyro3` passes it, 184/184), and")
    out("nothing in the shipping parser reads it. It is measured here only")
    out("because the ledger already records world containers matching 330/330")
    out("and vehicles never matching, so it says which of the two the")
    out("candidate row is WITHOUT anyone reading a zone name.")
    out(f"\n{'session':14s} {'cands':>5s} {'Z match':>7s} {'Z differ':>8s}   "
        f"reading")
    for session in sessions:
        match = differ = 0
        for frame in session["frames"]:
            if frame["candidate_xyz"] is None or frame["stack"] is None:
                continue
            if frame["candidate_xyz"][2] == frame["stack"]["solar"][2]:
                match += 1
            else:
                differ += 1
        if not (match or differ):
            continue
        reading = ("world-anchored" if differ == 0 else
                   "VEHICLE/INTERIOR" if match == 0 else "MIXED, look at it")
        out(f"{session['label']:14s} {match + differ:5d} {match:7d} "
            f"{differ:8d}   {reading}")


def report_comotion(sessions: list, out) -> None:
    out("\n=== 7. Does the candidate frame MOVE WITH THE PLAYER")
    out("The one measurement here that needs no name, no prefix, no scale and")
    out("no Z, so no entry in `REFUTED.md` touches it. Per session it compares")
    out("the widest separation between any two candidate positions against the")
    out("widest separation between the two matching Root positions.")
    out("")
    out("READ IT AS A DESCRIPTION, NOT A DISCRIMINATOR. A ratio far above 1")
    out("means the player barely moved inside the candidate frame while that")
    out("frame travelled through the system. A ROTATING BODY does that too, so")
    out("this separates moving frames from static ones and does NOT by itself")
    out("separate a vehicle from a body. Proposing a threshold on it would be")
    out("the scale rule that `REFUTED.md` already killed.")
    out("")
    out("SPLIT BY CANDIDATE IDENTITY, and that split is the point. A session")
    out("where the candidate CHANGES mid-flight (leaving a jump point, entering")
    out("a body's zone) holds frames measured in two different frames of")
    out("reference, and spanning them together produces a number that describes")
    out("neither. The name is used ONLY to group this diagnostic; nothing")
    out("routes on it.")
    out(f"\n{'session':14s} {'n':>4s} {'candidate span m':>18s} "
        f"{'root span m':>20s} {'ratio':>10s}  candidate")
    for session in sessions:
        rows = [f for f in session["frames"]
                if f["stack"] is not None and f["candidate_xyz"] is not None]
        runs: list = []
        for frame in rows:
            if runs and runs[-1][0] == frame["candidate_name"]:
                runs[-1][1].append(frame)
            else:
                runs.append((frame["candidate_name"], [frame]))
        if len(runs) > 1:
            out(f"{session['label']:14s} CANDIDATE CHANGED {len(runs) - 1}x "
                f"WITHIN THE SESSION")
        for name, group in runs:
            if len(group) < 2:
                continue
            cand = _widest(f["candidate_xyz"] for f in group)
            root = _widest(f["stack"]["root"] for f in group)
            ratio = f"{root / cand:.3e}" if cand > 0 else "inf"
            out(f"{session['label']:14s} {len(group):4d} {cand:18.3f} "
                f"{root:20.3f} {ratio:>10s}  {name}")


def _widest(points) -> float:
    """The largest distance between any two of these positions."""
    values = [tuple(point) for point in points]
    return max(
        (coordinate_stack.distance_m(a, b) for a in values for b in values),
        default=0.0,
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--label", action="append",
                        help="session to replay; repeatable, default is all")
    parser.add_argument("--limit", type=int, default=None,
                        help="first N frames of each session")
    parser.add_argument("--json", type=Path, default=None,
                        help="write the per-frame records here")
    args = parser.parse_args()

    labels = args.label or sorted(
        p.name for p in CAPTURE_ROOT.iterdir()
        if p.is_dir() and session_frames(p)
    )
    lines: list = []

    def out(text: str = "") -> None:
        print(text)
        lines.append(text)

    out("# Coordinate-stack corpus replay")
    out(f"\nReader: {GLYPHS.name}, {ov.POSITION_ROWS} rows, "
        f"{ov.CELLS_PER_ROW} cells where the capture is wide enough.")
    out(f"Sessions: {len(labels)}. Lossless PNG only.")
    out("\nTWO BOUNDARIES, stated because neither is visible in the numbers:")
    out("  1. This stops at the PARSERS. It does not run `scanner.parse_payload`,")
    out("     which holds the echo canaries and the stack echo check, nor any")
    out("     live grab. `stack parses` is one layer short of `capture succeeds`.")
    out("  2. Section 1 reports each session's usable cell count. A session")
    out("     below 88 was captured NARROWER than the block the runtime reads")
    out("     and decodes clipped, so it is not the shipping window.")

    sessions = [replay_session(label, args.limit) for label in labels]
    report_parse(sessions, out)
    totals = report_delta(sessions, out)
    mismatched = report_agreement(sessions, out)
    flagged = report_continuity(sessions, out)
    report_candidate(sessions, out)
    report_candidate_z(sessions, out)
    report_comotion(sessions, out)

    out("\n=== Verdict")
    out(f"  stack-only frames (the intended change): {totals.get('stack', 0)}")
    out(f"  legacy-only frames (regressions unless explained): "
        f"{totals.get('legacy', 0)}")
    out(f"  Root disagreements between the two parsers: {mismatched}")
    out(f"  continuity flags: {flagged}")

    if args.json:
        args.json.write_text(
            json.dumps({"sessions": sessions}, indent=1), encoding="utf-8"
        )
        print(f"\nWrote {args.json}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
