"""Measure what the CURRENT reader costs, per scene, so an optimisation can be beaten.

DEV TOOL, not a runtime file. Wave 2 steps 3 and 4 of
`Supercalifragilistic.md`, and the measurement half of its section 10.

WHY IT EXISTS. Section 10 asks every optimisation to prove decision-for-decision
equivalence BEFORE a timing result matters, which means the timing it is
compared against has to exist first and has to be attributable. Two numbers are
already in the ledger for "a read", 831 ms and 4.5 to 4.9 s, and they came from
different paths and different scenes. **This tool exists so the next number
names its path, its scene and its frame count**, and so nobody has to average
those two together to answer "did it get faster".

WHAT IT RUNS, and it is exactly what `main.py` runs after the grab:

    capture_is_usable -> overlay_is_present -> reader.read(POSITION_ROWS)
                      -> overlay_fields.capture_payload

Same order, same arguments, same `OverlayReader` instance reused across a
session's frames, so the alignment cache warms the way it warms in the field.

FOUR THINGS THIS DOES NOT ESTABLISH, stated here because none of them is
visible in a table of milliseconds:

  1. **THE GRAB IS NOT IN ANY NUMBER HERE.** These frames are PNGs on disk. The
     raw screen grab, measured elsewhere at 4.3 ms for the block against 104 ms
     for the full monitor, is excluded from every figure below, and so is the
     PNG load. So the "attempts per second" this implies is a CEILING on the
     decode lane, not a capture rate. The plan's section 1 asks for three rates
     kept separate; this tool can measure the second and third and CANNOT
     measure the first.

  2. **IT STOPS AT `capture_payload`.** It never runs `scanner.parse_payload`,
     which holds the echo canaries and the stack echo check, so "accepted" here
     is one layer short of "the capture succeeded". Same boundary
     `stack_replay.py` draws, and `LEDGER.md` records it as boundary 1 of the
     corpus replay.

  3. **A STORED FRAME IS NOT A LIVE FRAME.** Decoding the same PNG twice is not
     two observations; it is the same pixels twice. Nothing here measures
     availability over TIME, only over the frames somebody chose to keep.

  4. **THE CORPUS IS NOT ONE WIDTH.** Three sessions were captured at 640 px and
     decode 84 cells against the 88 the runtime reads, which is fewer cells and
     therefore CHEAPER. Their timings are not comparable with the 675 px
     sessions and the tables label them.

TWO PASSES, because the parts cost differently from the whole:

  LANE PASS, every benchmarked frame. One reader per session, frames in file
  order, the shipping call sequence. Frame 0 pays for the alignment fit; the
  rest run on the cached origin. Each read is classed COLD (the fit ran inside
  it), WARM (cached origin) or WARM+SELF-HEAL (cached origin decoded nothing
  trusted, so `read` refit and decoded a SECOND time). That third class is not a
  footnote: it is the most expensive path in the reader and it fires precisely
  on the scenes that refuse.

  ATTRIBUTION PASS, the first few usable frames of each session. Alignment fit,
  block decode and semantic parse timed separately, which needs one private
  call (`_decode_block`) because the public `read` bundles the fit with it. The
  sum is checked against the lane pass's own cold `read` on the same frame and
  the check is printed, so the split is falsifiable rather than asserted.

The ledger records the alignment fit as "about 300 ms of a 870 ms read". That is
a HYPOTHESIS carried in a comment, not a canonical row. This tool measures it.

HOW TO TAKE A BASELINE THAT MEANS ANYTHING. A wall clock measures the MACHINE,
not the code, so the conditions are part of the result:

  1. SINGLE TENANT. No other agent, test run, or second copy of this tool. The
     first baseline was taken with a competing `bench_reader` run on the same
     CPU for part of it, which is why section 6 exists and why per-frame
     timestamps were added afterwards.
  2. Note whether Star Citizen is running. Section 0 probes it and prints its
     CPU seconds over the run, so "the game was up" and "the game was working"
     are told apart rather than assumed.
  3. Re-run the SAME command, so the two runs differ in the code and not in the
     arguments. The command is printed in section 0 of every report.
  4. Compare against section 6's noise floor before believing any improvement.
     Under contention that floor is the honest resolution of the whole report.

Absolute milliseconds from a contended run are an UPPER BOUND. The ratios in
sections 3 and 4, cold against warm and fit against decode, are the durable part
of such a run: both sides of each ratio were measured under the same contention.

Usage:

    python bench_reader.py                          # 40 frames per session
    python bench_reader.py --limit 0                # every frame, slow
    python bench_reader.py --label surface-01       # one session
    python bench_reader.py --out report.txt --json out.json
    python bench_reader.py --from-json out.json     # re-render, never re-measure

Credit: Mallachi
"""

from __future__ import annotations

import argparse
import json
import platform
import subprocess
import sys
import time
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

# A full corpus pass is about 1030 frames at roughly a second each, which is
# twenty minutes and long enough that nobody reruns it. 40 keeps a whole-corpus
# run inside ten minutes while leaving every session that matters at or near its
# full length, and every table below prints the frame count it used so a
# truncated session can never read as a complete one.
DEFAULT_LIMIT = 40

# Frames per session in the attribution pass. Small on purpose: it pays for a
# second alignment fit per frame and answers a question about the READER, not
# about the scene, so the frames only have to be usable ones.
DEFAULT_ATTRIB = 3

# Background brightness classes. THE BOUNDARIES ARE CHOSEN, THE BANDS THEY SIT
# BETWEEN ARE MEASURED. `LEDGER.md` records, from `jumppoint-pyro-nyx` at one
# pose with only brightness varying, that a block background median RGB of 8 to
# 34 parsed EVERY frame and 76 to 95 refused EVERY frame. Nothing measures where
# between 34 and 76 the transition happens, so 40 and 70 are labels for reading
# the table and must never be used as a gate.
BRIGHT_DARK_MAX = 40.0
BRIGHT_MID_MAX = 70.0


def brightness_class(median: float) -> str:
    """A reading label for a block background median, never a decision."""
    if median <= BRIGHT_DARK_MAX:
        return "dark"
    if median <= BRIGHT_MID_MAX:
        return "mid"
    return "bright"


def block_background(frame: np.ndarray) -> float:
    """The block's background level: the mean of its per-channel medians.

    The same statistic `LEDGER.md` reports the refusal limit in, computed on the
    FIXED block geometry rather than the reader's fitted origin, for the same
    reason `capture_is_usable` does: a saturated frame moves the fit.
    """
    left, right = ov.block_columns(frame.shape[1])
    block = frame[:ov.BLOCK_TOP + ov.ROW_PITCH * ov.MAX_ROWS + ov.ROW_HEIGHT,
                  left:right]
    if block.size == 0:
        return 0.0
    return float(np.mean(np.median(block.reshape(-1, 3), axis=0)))


def session_frames(folder: Path) -> list:
    """Every full-frame capture in a session folder, in file order.

    TWO NAMING SCHEMES, and missing the second silently dropped seven sessions
    from a tool earlier today: the logger writes `frame_NNNN.png`, while the
    seven earliest hand-taken sessions use `shot_NN.png`. Anything else in those
    folders is a debug crop and is NOT a frame, so both patterns are named
    explicitly rather than globbing `*.png`.
    """
    frames = sorted(folder.glob("frame_*.png"))
    return frames or sorted(folder.glob("shot_*.png"))


def load_frame(path: Path) -> np.ndarray:
    """One capture as the float array the reader is given at runtime.

    Outside every timed section, deliberately. PNG decoding is this tool's cost
    and not the reader's, and folding it in would inflate every figure by an
    amount that varies with the frame's width.
    """
    return np.asarray(Image.open(path).convert("RGB")).astype(np.float64)


def game_state() -> dict:
    """Which Star Citizen processes exist, and each one's CPU seconds so far.

    Section 10 asks for benchmarks WITH the game running and for its CPU load
    while it runs, so the state is measured rather than assumed either way. A
    probe that fails reports `probed: False`, which is not the same as "the game
    is not running" and must not be written up as one.

    PER PID, NOT A SUM, and that is the whole repair. The first baseline sampled
    only a total and reported `end - start`, which produced MINUS 50,554 CPU
    seconds and minus 65.77 cores on a 16-core machine. The counter was fine:
    Star Citizen EXITED part-way through the run, so the subtraction took a
    process that had been accumulating CPU since the previous evening away from
    one that no longer existed. A sum cannot tell that apart from a quiet game,
    and a per-PID sample can, so a restart or an exit is now visible instead of
    arriving as an impossible number in the section that exists to say what
    produced the numbers.

    The CPU value is formatted with the invariant culture. On a machine whose
    locale writes decimals with a comma, the previous form would have produced a
    string `float` refuses and the probe would have reported itself as failed
    for a reason that has nothing to do with the game.
    """
    command = (
        "$p = Get-Process StarCitizen -ErrorAction SilentlyContinue; "
        "if ($p) { ($p | ForEach-Object { '{0}:{1}' -f $_.Id, "
        "([double]$_.CPU).ToString("
        "[System.Globalization.CultureInfo]::InvariantCulture) }) -join ',' } "
        "else { '' }"
    )
    try:
        done = subprocess.run(
            ["powershell", "-NoProfile", "-Command", command],
            capture_output=True, text=True, timeout=60, check=False,
        )
        text = done.stdout.strip()
        pids = {}
        for item in (part for part in text.split(",") if part.strip()):
            key, value = item.split(":")
            pids[key.strip()] = float(value)
        return {
            "probed": True, "processes": len(pids), "pids": pids,
            "cpu_s": sum(pids.values()),
            "mono": time.monotonic(),
        }
    except (OSError, ValueError, subprocess.SubprocessError):
        return {"probed": False, "processes": None, "pids": None,
                "cpu_s": None, "mono": time.monotonic()}


def report_game(start: dict, end: dict, elapsed: float, out) -> None:
    """What the game was doing, or why that cannot be said.

    EVERY BRANCH THAT CANNOT SUPPORT A NUMBER SAYS SO. The one thing this may
    not do is print a figure the samples do not support, which is exactly what
    the first baseline did.
    """
    if not (start.get("probed") and end.get("probed")):
        out("  Star Citizen   CPU NOT MEASURED: the process probe failed. Its "
            "state during this run is UNKNOWN,")
        out("                 which is not the same as the game being closed.")
        return
    if not start.get("processes"):
        out("  Star Citizen   NOT RUNNING when the run started.")
        if end.get("processes"):
            out("                 It STARTED during the run, so an unknown "
                "later portion of these")
            out("                 numbers was measured against a running game.")
        return
    if not end.get("processes"):
        out(f"  Star Citizen   RUNNING at the start "
            f"({start['processes']} process(es), "
            f"{start['cpu_s']:.0f} CPU s accumulated since it was launched),")
        out("                 and GONE by the end. IT EXITED DURING THIS RUN.")
        out("                 Its CPU load during the run is therefore NOT "
            "MEASURABLE from two")
        out("                 samples: neither when it exited nor how much it "
            "used before doing so.")
        out("                 An unknown early portion of this run was measured "
            "with the game up")
        out("                 and the rest without it. Sample per session to "
            "locate that boundary.")
        return
    before, after = start.get("pids") or {}, end.get("pids") or {}
    if set(before) != set(after):
        out(f"  Star Citizen   RUNNING at both ends, but the PROCESS SET "
            f"CHANGED ({sorted(before)} -> {sorted(after)}).")
        out("                 A restart resets the counter, so no CPU delta is "
            "quoted here.")
        return
    used = sum(after[pid] - before[pid] for pid in after)
    if used < 0:
        out(f"  Star Citizen   CPU NOT MEASURED: the delta came out negative "
            f"({used:.1f} s), which is impossible.")
        out("                 Reported rather than printed as a fact. The "
            "samples are in the JSON.")
        return
    out(f"  Star Citizen   RUNNING throughout, {end['processes']} process(es), "
        f"same PIDs at both ends.")
    out(f"                 It used {used:.1f} s of CPU during this run, "
        f"{used / max(elapsed, 1e-9):.2f} cores averaged")
    out(f"                 over {elapsed:.0f} s. Idle at a menu and loaded in "
        f"flight are different")
    out("                 machines; this number says which one this was.")


class Clock:
    """Wall and CPU time for one operation.

    BOTH, because they answer different questions. Wall time is what the player
    waits. CPU time is what the game does not get, and on a machine where numpy
    reaches more than one thread it can exceed the wall time, which is itself
    worth seeing. `time.process_time` counts the WHOLE process, so a figure here
    includes anything else this tool happened to be doing on another thread; it
    does nothing else, but the caveat is real.
    """

    def __enter__(self) -> Clock:
        self.wall = self.cpu = 0.0
        self._w = time.perf_counter()
        self._c = time.process_time()
        return self

    def __exit__(self, *_) -> None:
        self.wall = time.perf_counter() - self._w
        self.cpu = time.process_time() - self._c


def lane_frame(reader, frame: np.ndarray) -> dict:
    """One frame through the shipping structural path, timed in its parts.

    Mirrors `main.py`'s capture attempt from the point the grab returns: the
    precondition, the presence check, the block read, the semantic parse. The
    reader is the CALLER'S, not a fresh one, because the alignment cache is the
    thing being measured.
    """
    record = {
        # WHEN this frame was measured, on the same clock the whole run uses.
        # Added after the first baseline, whose JSON therefore does not carry
        # it: a second benchmark process was started on this machine part-way
        # through that run and nothing in the record could say WHICH frames
        # overlapped it. A contaminated window nobody can locate contaminates
        # the whole run.
        "mono": time.monotonic(),
        "background": block_background(frame),
        "width": int(frame.shape[1]),
        "cells": int(
            (ov.block_columns(frame.shape[1])[1]
             - ov.block_columns(frame.shape[1])[0]) // ov.PITCH
        ),
    }
    with Clock() as c:
        usable, why = ov.capture_is_usable(frame)
    record["usable"] = usable
    record["unusable_reason"] = why
    record["t_precondition"] = c.wall
    with Clock() as c:
        present = ov.overlay_is_present(frame)
    record["present"] = present
    record["t_presence"] = c.wall

    record.update({
        "t_read": None, "cpu_read": None, "t_parse": None,
        "alignment": "skipped", "trusted_rows": None,
        "accepted": False, "gate": "precondition_unusable",
    })
    if not usable:
        # The shipping path does not decode an unusable frame, so neither does
        # this. Those frames are cheap by DESIGN and averaging them into a
        # decode latency would flatter the reader on exactly the scenes where it
        # struggles.
        record["t_total"] = record["t_precondition"] + record["t_presence"]
        record["cpu_total"] = 0.0
        return record

    with Clock() as c:
        _, _, rows = reader.read(frame, ov.POSITION_ROWS)
    record["t_read"] = c.wall
    record["cpu_read"] = c.cpu
    with Clock() as parse:
        payload, reason = fields.capture_payload(rows)
    record["t_parse"] = parse.wall
    record["trusted_rows"] = sum(1 for row in rows if row["trusted"])
    record["accepted"] = payload is not None
    record["gate"] = "" if payload is not None else (reason.split(":", 1)[0] or "unnamed")
    # WHICH alignment path this read actually took, from the reader's own
    # instrumentation rather than from the frame index. A revalidation refit
    # every ALIGNMENT_REVALIDATE reads lands on an ordinary warm frame, and the
    # self-heal refit lands wherever nothing decoded, so neither is predictable
    # from position in the session.
    if reader.last_from_cache is False:
        record["alignment"] = "cold"
    elif reader.last_refit:
        record["alignment"] = "warm+selfheal"
    else:
        record["alignment"] = "warm"
    record["t_total"] = (record["t_precondition"] + record["t_presence"]
                         + record["t_read"] + record["t_parse"])
    record["cpu_total"] = record["cpu_read"]
    return record


def lane_session(label: str, limit: int) -> dict:
    """Every benchmarked frame of one session, one reader, in file order."""
    frames = session_frames(CAPTURE_ROOT / label)
    total = len(frames)
    if limit:
        frames = frames[:limit]
    if not frames:
        raise SystemExit(f"No frames in {CAPTURE_ROOT / label}")
    reader = ov.OverlayReader(GLYPHS)
    records = []
    for path in frames:
        record = lane_frame(reader, load_frame(path))
        record["file"] = path.name
        records.append(record)
    return {"label": label, "available": total, "frames": records}


def attribution_session(label: str, count: int) -> list:
    """Fit, decode and parse timed separately on a few usable frames.

    The one place this tool reaches past the public API. `read` bundles the fit
    with the decode and cannot report them apart, so the fit is timed through
    `fit_alignment` and the decode through `_decode_block` at the origin that
    fit returned, which is the same pair `read` runs in the same order. The sum
    is compared against the lane pass's cold `read` on the same frame and the
    comparison is printed; if the two disagree, this split is wrong and the
    printed check is what says so.

    ONE READER FOR THE SESSION, invalidated per frame rather than rebuilt. A
    fresh `OverlayReader` reallocates the stacked template arrays, and the first
    decode against them then pays for a cold CPU cache; measured, that alone put
    this pass about 20 per cent above the lane pass on the same frames and made
    the self-check look like a broken split. The runtime reuses one reader, so
    reusing one is also the more faithful measurement.
    """
    out = []
    reader = ov.OverlayReader(GLYPHS)
    for path in session_frames(CAPTURE_ROOT / label):
        if len(out) >= count:
            break
        frame = load_frame(path)
        if not ov.capture_is_usable(frame)[0]:
            continue
        reader.invalidate_alignment()
        with Clock() as fit:
            y0, _, _ = reader.fit_alignment(frame)
        with Clock() as decode:
            rows = reader._decode_block(frame, y0, ov.POSITION_ROWS)
        with Clock() as parse:
            fields.capture_payload(rows)
        out.append({
            "label": label, "file": path.name,
            "t_fit": fit.wall, "cpu_fit": fit.cpu,
            "t_decode": decode.wall, "cpu_decode": decode.cpu,
            "t_parse": parse.wall,
        })
    return out


def noise_floor(sessions: list, repeat: int) -> dict:
    """The same pixels decoded repeatedly, to size this run's own noise.

    WITHOUT THIS THE WHOLE REPORT IS UNFALSIFIABLE. Every number here is a wall
    clock on a shared machine, and a later optimisation that beats the baseline
    by less than the machine's own run-to-run spread has demonstrated nothing.
    Repeating one decode is NOT evidence about the reader's correctness, for the
    reason `LEDGER.md` states about identical pixels; it is evidence about the
    measuring instrument, which is the one thing repetition can establish.

    Warm reads on one frame, so the fit is out of it and what remains is the
    decode plus whatever else the machine was doing.

    THE FRAME IS CHOSEN, and chosen to be the ordinary case: the first one the
    lane pass decoded as a plain warm read. Picking merely the first usable
    frame lands on a refusing one, whose every warm read triggers the self-heal
    refit, and reports the reader's most expensive path as its noise floor.
    """
    for session in sessions:
        for frame in session["frames"]:
            if frame["alignment"] != "warm":
                continue
            path = CAPTURE_ROOT / session["label"] / frame["file"]
            image = load_frame(path)
            reader = ov.OverlayReader(GLYPHS)
            reader.read(image, ov.POSITION_ROWS)
            walls = []
            for _ in range(max(repeat, 0)):
                with Clock() as c:
                    reader.read(image, ov.POSITION_ROWS)
                walls.append(c.wall)
            if not walls:
                return {}
            return {
                "label": session["label"], "file": frame["file"],
                "n": len(walls), "min": min(walls), "max": max(walls),
                "p50": float(np.median(walls)),
            }
    return {}


def report_noise(noise: dict, out) -> None:
    out("\n=== 6. This run's own noise floor")
    out("One frame, decoded repeatedly on the cached origin. It says nothing")
    out("about the reader and everything about the measurement: an optimisation")
    out("that beats the tables above by less than this spread has shown")
    out("nothing. Other work was running on this machine during the benchmark,")
    out("and that is exactly what this number prices in.")
    if not noise:
        out("\n  Not measured.")
        return
    spread = (noise["max"] - noise["min"]) / max(noise["p50"], 1e-9)
    out(f"\n  {noise['label']}/{noise['file']}, {noise['n']} warm reads of "
        f"IDENTICAL pixels:")
    out(f"    p50 {noise['p50'] * 1000:.1f} ms, min {noise['min'] * 1000:.1f}, "
        f"max {noise['max'] * 1000:.1f}")
    out(f"    spread {spread * 100:.1f} per cent of p50.")


def pct(values: list, share: float) -> float:
    """One percentile of these samples, or 0.0 when there are none."""
    return float(np.percentile(values, share)) if values else 0.0


def stat_row(values: list) -> str:
    """p50, p95 and maximum in milliseconds, with weak samples marked.

    A p95 over fewer than twenty samples is interpolated between two of the top
    handful and moves with any one of them, so it is marked rather than printed
    as though it were a distribution.
    """
    if not values:
        return f"{'-':>9s} {'-':>9s} {'-':>9s}"
    weak = "*" if len(values) < 20 else " "
    return (f"{pct(values, 50) * 1000:9.1f} "
            f"{pct(values, 95) * 1000:8.1f}{weak} "
            f"{max(values) * 1000:9.1f}")


def report_environment(sessions: list, attribution: list, start: dict,
                       end: dict, samples: list, elapsed: float, argv: list,
                       out) -> None:
    out("\n=== 0. What produced these numbers")
    out(f"  machine        {platform.processor()}")
    out(f"  platform       {platform.platform()}")
    out(f"  python         {sys.version.split()[0]}, numpy {np.__version__}")
    out(f"  reader         {GLYPHS.name}, POSITION_ROWS={ov.POSITION_ROWS}, "
        f"REFUSE_COST={ov.REFUSE_COST}, REFUSE_MARGIN={ov.REFUSE_MARGIN}")
    # A RE-RENDER MUST NOT INVENT THE COMMAND. `None` means the saved run
    # predates the stored `argv` and its arguments are simply not on record;
    # printing "(no arguments)" there would name a DIFFERENT run than the one
    # that produced every number below it.
    if argv is None:
        out("  command        NOT RECORDED in this run's JSON. Take it from "
            "whoever ran it.")
    else:
        out(f"  command        python bench_reader.py "
            f"{' '.join(argv) if argv else '(no arguments)'}")
    frames = sum(len(s["frames"]) for s in sessions)
    available = sum(s["available"] for s in sessions)
    out(f"  frames         {frames} benchmarked of {available} on disk, "
        f"{len(sessions)} sessions")
    out(f"  attribution    {len(attribution)} frames")
    out(f"  wall clock     {elapsed:.1f} s for the whole run")

    # THE MEASUREMENT WINDOW, so a contaminated run can be located rather than
    # argued about. Absent from the first baseline's JSON, which is exactly the
    # gap that made its contamination unlocatable.
    stamps = [f["mono"] for s in sessions for f in s["frames"] if "mono" in f]
    if stamps:
        out(f"  frame clock    first frame at +0.0 s, last at "
            f"+{max(stamps) - min(stamps):.1f} s on the run's monotonic clock; "
            f"per-frame stamps are in the JSON")
    else:
        out("  frame clock    NOT RECORDED in this run. If anything else was "
            "using this machine,")
        out("                 WHICH frames it overlapped cannot be recovered.")

    # STATE IT, DO NOT ASSUME IT. Section 10 asks for the game running and for
    # its load; a failed probe says so rather than reporting a convenient no.
    report_game(start, end, elapsed, out)
    if len(samples) > 2:
        changes = [
            f"+{samples[i]['mono'] - samples[0]['mono']:.0f} s"
            for i in range(1, len(samples))
            if samples[i].get("processes") != samples[i - 1].get("processes")
        ]
        out(f"  game samples   {len(samples)}, one between sessions. "
            f"{'Process count changed at ' + ', '.join(changes)
               if changes else 'The process count never changed.'}")
    elif samples:
        out("  game samples   2 only, so any change in the game's state during "
            "the run is unlocatable.")


def report_scenes(sessions: list, out) -> None:
    out("\n=== 1. Per scene, never one aggregate")
    out("`LEDGER.md` records background brightness as the dominant availability")
    out("limit, so every row carries its own. `bg` is the block background")
    out("median RGB, the same statistic the ledger's 8-to-34-parses and")
    out("76-to-95-refuses bands are measured in. THE DARK/MID/BRIGHT LABELS ARE")
    out("READING AIDS: their boundaries are chosen, and only the bands either")
    out("side of them are measured.")
    out("")
    out("`decoded` is frames that reached the reader, which is attempts minus")
    out("what the precondition rejected. `accepted` is `capture_payload`")
    out("returning a payload, which is ONE LAYER SHORT of a successful capture")
    out("because `scanner.parse_payload` never runs here.")
    out(f"\n{'session':22s} {'n':>4s} {'cells':>5s} {'bg':>6s} {'class':>6s} "
        f"{'decoded':>7s} {'accept':>6s} {'rate':>6s}   top refusal gates")
    for session in sessions:
        rows = session["frames"]
        decoded = [f for f in rows if f["usable"]]
        accepted = [f for f in rows if f["accepted"]]
        background = float(np.median([f["background"] for f in rows]))
        gates: dict = {}
        for frame in rows:
            if not frame["accepted"]:
                gates[frame["gate"]] = gates.get(frame["gate"], 0) + 1
        top = ", ".join(
            f"{g} {n}" for g, n in
            sorted(gates.items(), key=lambda kv: -kv[1])[:2]
        )
        cells = sorted({f["cells"] for f in rows})
        rate = f"{100.0 * len(accepted) / len(rows):.0f}%" if rows else "-"
        clip = "" if cells == [ov.CELLS_PER_ROW] else "  CLIPPED"
        out(f"{session['label']:22s} {len(rows):4d} "
            f"{','.join(str(c) for c in cells):>5s} {background:6.1f} "
            f"{brightness_class(background):>6s} {len(decoded):7d} "
            f"{len(accepted):6d} {rate:>6s}   {top}{clip}")


def report_latency(sessions: list, out) -> None:
    out("\n=== 2. Latency per scene, decode lane only")
    out("EVERY FIGURE EXCLUDES THE SCREEN GRAB and the PNG load. It is")
    out("precondition + presence + `read` + `capture_payload`, which is exactly")
    out("what `main.py` runs after `sct.grab` returns and nothing before it.")
    out("Frames the precondition rejected are counted in `n` and are cheap by")
    out("design, so a bright session's p50 describes a scene that mostly never")
    out("decoded. `Hz` inverts p50 and is therefore a CEILING on the decode")
    out("lane, single-threaded, with no capture in it.")
    out(f"\n{'session':22s} {'n':>4s} {'p50 ms':>9s} {'p95 ms':>9s} "
        f"{'max ms':>9s} {'CPU p50':>8s} {'p50 Hz':>7s}")
    for session in sessions:
        walls = [f["t_total"] for f in session["frames"]]
        cpus = [f["cpu_total"] for f in session["frames"]]
        p50 = pct(walls, 50)
        out(f"{session['label']:22s} {len(walls):4d} {stat_row(walls)} "
            f"{pct(cpus, 50) * 1000:8.1f} "
            f"{1.0 / p50 if p50 > 0 else 0.0:7.2f}")
    walls = [f["t_total"] for s in sessions for f in s["frames"]]
    cpus = [f["cpu_total"] for s in sessions for f in s["frames"]]
    out(f"{'ALL, and see above':22s} {len(walls):4d} {stat_row(walls)} "
        f"{pct(cpus, 50) * 1000:8.1f} "
        f"{1.0 / pct(walls, 50) if walls else 0.0:7.2f}")
    out("\n* marks a p95 over fewer than 20 samples.")


def report_alignment(sessions: list, out) -> dict:
    out("\n=== 3. Cold against warm alignment, and the third case")
    out("COLD is a read whose fit ran inside it. WARM is a read on the cached")
    out("origin. WARM+SELF-HEAL is a warm read that decoded nothing trusted, so")
    out("`read` invalidated, refit and decoded a SECOND time: it costs a fit")
    out("plus two decodes and it fires on refusing scenes, which is to say on")
    out("the scenes that were already the problem.")
    out("")
    out("Classed from the reader's own `last_from_cache` and `last_refit`, not")
    out("from the frame's position in the session, because the revalidation")
    out("refit every ALIGNMENT_REVALIDATE reads is invisible from the index.")
    buckets: dict = {"cold": [], "warm": [], "warm+selfheal": []}
    for session in sessions:
        for frame in session["frames"]:
            if frame["alignment"] in buckets:
                buckets[frame["alignment"]].append(frame["t_read"])
    out(f"\n{'alignment':16s} {'n':>4s} {'p50 ms':>9s} {'p95 ms':>9s} "
        f"{'max ms':>9s}")
    for name, values in buckets.items():
        out(f"{name:16s} {len(values):4d} {stat_row(values)}")
    cold, warm = pct(buckets["cold"], 50), pct(buckets["warm"], 50)
    if cold and warm:
        out(f"\n  Cold minus warm at p50: {(cold - warm) * 1000:.1f} ms, which is "
            f"{100.0 * (cold - warm) / cold:.0f} per cent of a cold read.")
        out("  That difference is the alignment fit AS THE CACHE SEES IT. "
            "Section 4")
        out("  times the fit directly; the two are independent and should agree.")

    out("\n--- Where the self-heal fires, per scene")
    out("THE COMPOUNDING CASE, and the reason this is not a footnote. The")
    out("self-heal fires exactly when nothing decoded, which is the bright")
    out("refusing scene that is already the availability problem. So the frames")
    out("LEAST likely to produce a fix are the MOST expensive to refuse, and a")
    out("scene gets slower precisely as it stops working.")
    out(f"\n{'session':22s} {'reads':>5s} {'cold':>5s} {'warm':>5s} "
        f"{'heal':>5s} {'heal share':>10s} {'accepted':>8s}")
    for session in sessions:
        counts: dict = {"cold": 0, "warm": 0, "warm+selfheal": 0}
        for frame in session["frames"]:
            if frame["alignment"] in counts:
                counts[frame["alignment"]] += 1
        reads = sum(counts.values())
        accepted = sum(1 for f in session["frames"] if f["accepted"])
        share = counts["warm+selfheal"] / reads if reads else 0.0
        out(f"{session['label']:22s} {reads:5d} {counts['cold']:5d} "
            f"{counts['warm']:5d} {counts['warm+selfheal']:5d} "
            f"{share * 100:9.0f}% "
            f"{100.0 * accepted / max(len(session['frames']), 1):7.0f}%")
    return {name: len(values) for name, values in buckets.items()}


def report_attribution(attribution: list, sessions: list, out) -> None:
    out("\n=== 4. Where a cold read's time goes")
    out("Fit, decode and parse timed SEPARATELY on usable frames, the fit")
    out("through `fit_alignment` and the decode through `_decode_block` at the")
    out("origin it returned. `LEDGER.md` carries the fit as `about 300 ms of a")
    out("870 ms read` in a source comment, as a HYPOTHESIS. This measures it.")
    if not attribution:
        out("\n  No usable frame was found in the attribution pass.")
        return
    fits = [a["t_fit"] for a in attribution]
    decodes = [a["t_decode"] for a in attribution]
    parses = [a["t_parse"] for a in attribution]
    out(f"\n{'part':16s} {'n':>4s} {'p50 ms':>9s} {'p95 ms':>9s} "
        f"{'max ms':>9s}   share of p50 sum")
    total = pct(fits, 50) + pct(decodes, 50) + pct(parses, 50)
    for name, values in (("alignment fit", fits), ("block decode", decodes),
                         ("semantic parse", parses)):
        share = pct(values, 50) / total if total else 0.0
        out(f"{name:16s} {len(values):4d} {stat_row(values)}   {share * 100:5.1f}%")
    out(f"\n  Summed p50s: {total * 1000:.1f} ms.")

    # THE SELF-CHECK. The split above is only believable if it adds up to the
    # whole thing measured through the public API on the same frames.
    cold = {}
    for session in sessions:
        for frame in session["frames"]:
            if frame["alignment"] == "cold":
                cold[(session["label"], frame["file"])] = frame
    pairs = [
        (a, cold[(a["label"], a["file"])]) for a in attribution
        if (a["label"], a["file"]) in cold
    ]
    out("\n  Self-check: the parts against the lane pass's own cold `read` on")
    out("  the SAME frames. A gap here means the split is wrong.")
    if not pairs:
        out("    No frame appears in both passes, so the split is UNCHECKED.")
        return
    gaps = [
        (a["t_fit"] + a["t_decode"]) - b["t_read"] for a, b in pairs
    ]
    reads = [b["t_read"] for _, b in pairs]
    out(f"    {len(pairs)} frames. fit+decode median "
        f"{pct([a['t_fit'] + a['t_decode'] for a, _ in pairs], 50) * 1000:.1f} ms "
        f"against cold read median {pct(reads, 50) * 1000:.1f} ms.")
    out(f"    Worst single-frame gap {max(abs(g) for g in gaps) * 1000:.1f} ms.")


def report_rates(sessions: list, out) -> None:
    out("\n=== 5. The three rates section 1 requires kept apart")
    out("")
    out("  1. RAW SCREEN-GRAB RATE. **NOT MEASURABLE HERE, AT ALL.** Every")
    out("     frame in this run came off disk. Nothing in this tool touches")
    out("     `mss`, and no number above may be quoted as a capture rate.")
    attempts = sum(len(s["frames"]) for s in sessions)
    decoded = sum(1 for s in sessions for f in s["frames"] if f["usable"])
    accepted = sum(1 for s in sessions for f in s["frames"] if f["accepted"])
    out(f"\n  2. DECODE-ATTEMPT RATE: {decoded} of {attempts} stored frames "
        f"reached the reader")
    out(f"     ({100.0 * decoded / attempts:.1f} per cent). The rest were "
        f"rejected by the capture")
    out("     precondition before any decoding, which is the guard working.")
    out(f"\n  3. ACCEPTED AUTHORITATIVE-POSITION RATE: {accepted} of {attempts} "
        f"({100.0 * accepted / attempts:.1f} per cent),")
    out("     and per scene in section 1, which is the only form that means")
    out("     anything. This is `capture_payload` accepting, one layer short of")
    out("     `scanner.parse_payload`, and it is a rate over STORED FRAMES and")
    out("     not over time.")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--label", action="append",
                        help="session to benchmark; repeatable, default is all")
    parser.add_argument("--limit", type=int, default=DEFAULT_LIMIT,
                        help=f"first N frames of each session, 0 for all "
                             f"(default {DEFAULT_LIMIT})")
    parser.add_argument("--attrib", type=int, default=DEFAULT_ATTRIB,
                        help=f"usable frames per session in the attribution "
                             f"pass (default {DEFAULT_ATTRIB})")
    parser.add_argument("--repeat", type=int, default=5,
                        help="warm reads of one frame for the noise floor "
                             "(default 5)")
    parser.add_argument("--json", type=Path, default=None,
                        help="write the per-frame records here")
    parser.add_argument("--out", type=Path, default=None,
                        help="write this report here as well as to stdout")
    parser.add_argument("--from-json", type=Path, default=None,
                        help="re-render the report from a saved run instead of "
                             "measuring again")
    args = parser.parse_args()

    lines: list = []

    def out(text: str = "") -> None:
        print(text, flush=True)
        lines.append(text)

    if args.from_json:
        # RE-RENDERING, NOT RE-MEASURING. A benchmark this expensive should not
        # have to be repeated to change a table, and repeating it would produce
        # DIFFERENT numbers under different machine load, which is the one thing
        # a baseline must not do quietly. The stored `argv` is printed rather
        # than this invocation's, so the report always names the command that
        # produced the measurements.
        saved = json.loads(args.from_json.read_text(encoding="utf-8"))
        sessions = saved["sessions"]
        attribution = saved["attribution"]
        noise = saved.get("noise", {})
        game_before = saved.get("game_before", {"probed": False})
        game_after = saved.get("game_after", {"probed": False})
        elapsed = saved.get("elapsed_s", 0.0)
        argv = saved.get("argv")
        samples = saved.get("game_samples", [])
    else:
        labels = args.label or sorted(
            p.name for p in CAPTURE_ROOT.iterdir()
            if p.is_dir() and session_frames(p)
        )
        started = time.perf_counter()
        game_before = game_state()
        # Each session's attribution runs IMMEDIATELY after its own lane pass,
        # not in a second sweep at the end. The self-check compares the two on
        # the same frames, and a whole corpus of drift in machine load between
        # the passes would show up there as a split that does not add up.
        sessions, attribution = [], []
        # ONE GAME SAMPLE PER SESSION. Two samples could not say WHEN Star
        # Citizen exited during the first baseline, only that it had. A sample
        # between sessions costs one process query and bounds the change to a
        # single session.
        samples = [game_before]
        for label in labels:
            sessions.append(lane_session(label, args.limit))
            attribution.extend(attribution_session(label, args.attrib))
            samples.append(game_state())
        noise = noise_floor(sessions, args.repeat)
        elapsed = time.perf_counter() - started
        game_after = game_state()
        samples.append(game_after)
        argv = sys.argv[1:]

    out("# NavPoint reader benchmark")
    out("")
    out("The CURRENT reader, measured so a later optimisation has something")
    out("honest to beat. Read the module docstring before quoting any number:")
    out("the grab is excluded, this stops at `capture_payload`, a stored frame")
    out("is not a live one, and three sessions decode at 84 cells rather than")
    out("88.")
    report_environment(sessions, attribution, game_before, game_after,
                       samples, elapsed, argv, out)
    report_scenes(sessions, out)
    report_latency(sessions, out)
    report_alignment(sessions, out)
    report_attribution(attribution, sessions, out)
    report_rates(sessions, out)
    report_noise(noise, out)

    if args.out:
        args.out.write_text("\n".join(lines) + "\n", encoding="utf-8")
        print(f"\nWrote {args.out}")
    if args.json:
        args.json.write_text(
            json.dumps({"sessions": sessions, "attribution": attribution,
                        "noise": noise, "game_before": game_before,
                        "game_after": game_after, "game_samples": samples,
                        "elapsed_s": elapsed, "argv": argv},
                       indent=1),
            encoding="utf-8",
        )
        print(f"Wrote {args.json}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
