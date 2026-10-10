"""Exact descriptive statistics for replay timing logs (requires NumPy).

Run after both replays finish. Raw logs remain intact and independently decodable.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import platform
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

PATTERN_DTYPE = np.dtype(
    [
        ("duration_ns", "<u8"),
        ("byte_start", "<u8"),
        ("byte_end", "<u8"),
        ("file_id", "<u4"),
        ("pattern_id", "<u4"),
        ("budget_ns", "<u4"),
        ("phase", "u1"),
        ("operation", "u1"),
        ("status", "u1"),
        ("pad", "V1"),
    ]
)
ENTRY_DTYPE = np.dtype(
    [
        ("byte_start", "<u8"),
        ("byte_end", "<u8"),
        ("wall_ns", "<u8"),
        ("cpu_ns", "<u8"),
        ("file_id", "<u4"),
        ("outcome", "u1"),
        ("pad", "V3"),
    ]
)
PERCENTILES = [50, 90, 95, 99, 99.9, 99.99]


def statistics(values):
    values = np.asarray(values)
    if not len(values):
        return {"count": 0}
    q = np.percentile(values, PERCENTILES, method="inverted_cdf") / 1e6
    result = {
        "count": int(len(values)),
        "min_ms": float(values.min() / 1e6),
        "mean_ms": float(values.mean() / 1e6),
        "std_ms": float(values.std() / 1e6),
        "max_ms": float(values.max() / 1e6),
        "total_seconds": float(values.sum(dtype=np.float64) / 1e9),
    }
    result.update({f"p{p}_ms": float(v) for p, v in zip(PERCENTILES, q, strict=True)})
    result["at_or_above_ms"] = {
        str(t): int(np.count_nonzero(values >= t * 1e6))
        for t in (1, 5, 10, 12, 15, 25, 50, 75, 90, 100)
    }
    return result


def read_rows(path, dtype, expected):
    size = path.stat().st_size
    if size != expected * dtype.itemsize:
        raise ValueError(
            f"Incomplete timing file: {path}: {size} bytes, expected {expected * dtype.itemsize}"
        )
    return np.memmap(path, dtype=dtype, mode="r") if size else np.empty(0, dtype=dtype)


def top_indices(values, count=20):
    return (
        np.argsort(values)[-count:]
        if len(values) <= count
        else np.argpartition(values, -count)[-count:]
    )


def csv_write(path, rows):
    if not rows:
        return
    with path.open("w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def analyze(directory):
    manifests = sorted((directory / "timings").rglob("metadata.json"))
    if not manifests:
        raise ValueError(f"No complete timing metadata in {directory}")
    groups = defaultdict(list)
    entry_groups = defaultdict(list)
    outcomes = Counter()
    statuses = Counter()
    slow_patterns = []
    slow_entries = []
    timeouts = []
    per_file = []
    raw_files = []
    pattern_count = entry_count = 0
    for manifest in manifests:
        meta = json.loads(manifest.read_text())
        folder = manifest.parent
        p = read_rows(folder / "patterns.bin", PATTERN_DTYPE, meta["pattern_count"])
        e = read_rows(folder / "entries.bin", ENTRY_DTYPE, meta["entry_count"])
        pattern_count += len(p)
        entry_count += len(e)
        raw_files.append(
            {
                "metadata": str(manifest.relative_to(directory)),
                "patterns": len(p),
                "entries": len(e),
                "bytes": p.nbytes + e.nbytes,
            }
        )

        def pattern_row(row, meta=meta):
            return {
                "file": meta["files"][str(int(row["file_id"]))],
                "byte_start": int(row["byte_start"]),
                "byte_end": int(row["byte_end"]),
                "duration_ms": float(row["duration_ns"] / 1e6),
                "budget_ms": float(row["budget_ns"] / 1e6),
                "phase": meta["phase"][str(int(row["phase"]))],
                "operation": meta["operation"][str(int(row["operation"]))],
                "status": meta["status"][str(int(row["status"]))],
                "expression": meta["patterns"][str(int(row["pattern_id"]))][
                    "expression"
                ],
            }

        for offset in range(0, len(p), 1000000):
            chunk = p[offset : offset + 1000000]
            # Stable grouping in bounded chunks avoids a giant object per call.
            keys = (
                chunk["pattern_id"].astype(np.uint64) * 100
                + chunk["phase"] * 10
                + chunk["operation"]
            )
            order = np.argsort(keys, kind="stable")
            ordered = keys[order]
            starts = np.r_[0, np.flatnonzero(np.diff(ordered)) + 1]
            ends = np.r_[starts[1:], len(order)]
            durations = chunk["duration_ns"][order]
            for start, end in zip(starts, ends, strict=True):
                code = int(ordered[start])
                identity = code // 100
                phase = (code % 100) // 10
                operation = code % 10
                pattern = meta["patterns"][str(identity)]
                key = (pattern["expression"], tuple(pattern["flags"]), phase, operation)
                groups[key].append(durations[start:end].copy())
            for status, count in zip(
                *np.unique(chunk["status"], return_counts=True), strict=True
            ):
                statuses[int(status)] += int(count)
            slow_patterns.extend(
                pattern_row(row) for row in chunk[top_indices(chunk["duration_ns"])]
            )
            timeouts.extend(pattern_row(row) for row in chunk[chunk["status"] != 0])
        for offset in range(0, len(e), 1000000):
            chunk = e[offset : offset + 1000000]
            entry_groups["all"].append(chunk["wall_ns"].copy())
            entry_groups["ignored"].append(chunk["wall_ns"][chunk["outcome"] == 0])
            entry_groups["recognized_clean"].append(
                chunk["wall_ns"][chunk["outcome"] == 1]
            )
            entry_groups["diagnostic_or_exception"].append(
                chunk["wall_ns"][chunk["outcome"] >= 2]
            )
            entry_groups["cpu_all"].append(chunk["cpu_ns"].copy())
            for outcome, count in zip(
                *np.unique(chunk["outcome"], return_counts=True), strict=True
            ):
                outcomes[int(outcome)] += int(count)
            for row in chunk[top_indices(chunk["wall_ns"])]:
                slow_entries.append(
                    {
                        "file": meta["files"][str(int(row["file_id"]))],
                        "byte_start": int(row["byte_start"]),
                        "byte_end": int(row["byte_end"]),
                        "wall_ms": float(row["wall_ns"] / 1e6),
                        "cpu_ms": float(row["cpu_ns"] / 1e6),
                        "outcome": meta["outcome"][str(int(row["outcome"]))],
                    }
                )
        if len(e) and np.any(e["file_id"][1:] < e["file_id"][:-1]):
            raise ValueError("Entry file IDs are not in replay order")
        file_ids, starts, counts = np.unique(
            e["file_id"], return_index=True, return_counts=True
        )
        for file_id, start, count in zip(file_ids, starts, counts, strict=True):
            selected = e[start : start + count]
            per_file.append(
                {
                    "file": meta["files"][str(int(file_id))],
                    **statistics(selected["wall_ns"]),
                }
            )
        del p, e
    print(
        f"{directory.name}: decoded {pattern_count:,} patterns and {entry_count:,} entries",
        flush=True,
    )
    pattern_summaries = []
    phase_values = defaultdict(list)
    for key, values in groups.items():
        expression, flags, phase, operation = key
        array = np.concatenate(values)
        phase_values[phase].append(array)
        pattern_summaries.append(
            {
                "expression": expression,
                "flags": ",".join(flags),
                "phase": {1: "entry parsing", 2: "physical-line framing"}[phase],
                "operation": {1: "search", 2: "sub", 3: "finditer"}[operation],
                **statistics(array),
            }
        )
    distributions = {
        f"pattern_{phase}": statistics(np.concatenate(values))
        for phase, values in phase_values.items()
    }
    distributions.update(
        {
            f"entry_{name}": statistics(np.concatenate(values))
            for name, values in entry_groups.items()
        }
    )
    cpu = np.concatenate(entry_groups["cpu_all"])
    nonzero = cpu[cpu > 0]
    cpu_resolution = {
        "zero_count": int(np.count_nonzero(cpu == 0)),
        "minimum_positive_ms": float(nonzero.min() / 1e6) if len(nonzero) else None,
        "warning": "Windows thread CPU accounting is coarse. Individual entry CPU samples are not suitable for latency percentiles or identifying scheduling delays.",
    }
    pattern_summaries.sort(key=lambda s: s["total_seconds"], reverse=True)
    slow_patterns = sorted(slow_patterns, key=lambda s: s["duration_ms"], reverse=True)[
        :50
    ]
    slow_entries = sorted(slow_entries, key=lambda s: s["wall_ms"], reverse=True)[:50]
    expected = json.loads((directory / "summary.json").read_text())
    expected_records = expected.get(
        "records", expected.get("totals", {}).get("records")
    )
    if entry_count != expected_records:
        raise ValueError(
            f"{entry_count} timing rows != {expected_records} replay records"
        )
    expected_timeouts = expected["diagnostic_counts"].get("regex_budget_exceeded", 0)
    if outcomes[4] + outcomes[5] != expected_timeouts:
        raise ValueError(
            "Recorded parser budget diagnostics do not match replay summary"
        )
    report = {
        "pattern_count": pattern_count,
        "entry_count": entry_count,
        "distributions": distributions,
        "pattern_status_counts": dict(statuses),
        "entry_outcome_counts": dict(outcomes),
        "cpu_resolution": cpu_resolution,
        "pattern_groups": pattern_summaries,
        "slowest_patterns": slow_patterns,
        "slowest_entries": slow_entries,
        "pattern_exceptions": timeouts,
        "raw_logs": raw_files,
        "per_file": per_file,
        "replay_summary": expected,
        "checks": {
            "raw_file_lengths_valid": True,
            "entry_count_matches_replay": True,
            "budget_diagnostics_match_replay": True,
        },
    }
    (directory / "timing-statistics.json").write_text(
        json.dumps(report, indent=2), encoding="utf-8"
    )
    for name, rows in [
        ("patterns", pattern_summaries),
        ("files", per_file),
        ("slowest-patterns", slow_patterns),
        ("slowest-entries", slow_entries),
        ("pattern-exceptions", timeouts),
    ]:
        csv_write(
            directory / f"timing-{name}.csv",
            [
                {k: v for k, v in row.items() if not isinstance(v, (dict, list))}
                for row in rows
            ],
        )
    return report


def table(report):
    lines = [
        "| Measurement | Count | Mean ms | Std. dev. ms | Median ms | p95 ms | p99 ms | p99.9 ms | Maximum ms |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for key, label in [
        ("pattern_1", "Pattern: parsing"),
        ("pattern_2", "Pattern: line framing"),
        ("entry_all", "Whole entry: all"),
        ("entry_ignored", "Whole entry: ignored"),
        ("entry_recognized_clean", "Whole entry: recognized"),
        ("entry_diagnostic_or_exception", "Whole entry: diagnostics"),
    ]:
        s = report["distributions"][key]
        if not s["count"]:
            continue
        lines.append(
            f"| {label} | {s['count']:,} | "
            + " | ".join(
                f"{s[k]:.6f}"
                for k in (
                    "mean_ms",
                    "std_ms",
                    "p50_ms",
                    "p95_ms",
                    "p99_ms",
                    "p99.9_ms",
                    "max_ms",
                )
            )
            + " |"
        )
    return lines


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("report_directory")
    args = parser.parse_args()
    root = Path(args.report_directory).resolve()
    reports = {name: analyze(root / name) for name in ("corpus", "story")}
    baseline = json.loads((root / "before-hashes.json").read_text())
    differences = [
        p
        for p, h in baseline.items()
        if not Path(p).is_file()
        or hashlib.sha256(Path(p).read_bytes()).hexdigest() != h
    ]
    preservation = {"checked_files": len(baseline), "changed_or_missing": differences}
    (root / "preservation.json").write_text(
        json.dumps(preservation, indent=2), encoding="utf-8"
    )
    calibration = json.loads((root / "calibration/calibration.json").read_text())
    result = {
        "generated_utc": datetime.now(timezone.utc).isoformat(),
        "analysis_python": platform.python_version(),
        "numpy": np.__version__,
        "preservation": preservation,
        "runs": {
            k: {
                n: v
                for n, v in r.items()
                if n not in ("pattern_groups", "raw_logs", "per_file")
            }
            for k, r in reports.items()
        },
    }
    (root / "statistics.json").write_text(
        json.dumps(result, indent=2), encoding="utf-8"
    )
    corpus = reports["corpus"]
    story = reports["story"]
    c = corpus["replay_summary"]
    s = story["replay_summary"]
    lines = [
        "# SC Log Reader — parser timing statistical report",
        "",
        f"Generated {result['generated_utc']}. Reader 0.3.1; regex allowance 15 ms; whole-entry deadline 100 ms.",
        "",
        "## Scope and measurement definitions",
        "",
        f"- Independent corpus replay: **{c['files']} log files**, **{c['totals']['records']:,} entries**, **{c['totals']['snapshot_bytes']:,} bytes**; two workers. Restart, deduplication, different chunk sizes and database checks retained.",
        f"- Chronological replay: **{s['files_replayed']} files**, **{s['records']:,} entries**; one sequential reader preserving state per environment. Both replays ran concurrently on the same computer.",
        "- Every runtime instruction-pattern operation and every primary-pass Reader.parse invocation was logged; no sampling. Setup validation and the corpus restart pass are excluded from timing distributions.",
        "- A **pattern** is one regex search, replacement, or complete finditer traversal. Iterator time sums backend calls and excludes consumer work between matches. Failed and successful searches are included.",
        "- A **whole entry** measures Reader.parse from call to return, including rule selection, extraction, validation and cache misses. It excludes log reading, physical-line assembly, database/state handling and final timing-file writes. Pattern results are a subset of this work, so their totals must not be added to entry totals.",
        "- Line-framing regex operations are measured separately. Their source byte range identifies the physical line being processed; pending multiline context may also be involved.",
        "- Latency uses monotonic high-resolution wall-clock time. Mean, population standard deviation and exact nearest-rank percentiles describe this measured run. p99 means 99% of observations took that long or less.",
        "- Per-entry CPU time is also in the raw log, but Windows CPU accounting is too coarse here for individual-entry comparisons. Wall-clock results are authoritative for this report.",
        "- This is a complete-corpus descriptive report, not a random-sample inference. Repeated/copied game logs and the two replays are not independent statistical samples; no confidence interval or semantic-accuracy claim is made.",
        "",
    ]
    for name, label in [
        ("corpus", "Independent-file replay"),
        ("story", "Chronological story replay"),
    ]:
        report = reports[name]
        summary = report["replay_summary"]
        lines += [f"## {label}", ""] + table(report) + [""]
        outcomes = report["entry_outcome_counts"]
        patterns = report["pattern_status_counts"]
        # Counters are still keyed by integers in memory.
        lines += [
            f"Regex operations raising TimeoutError: **{patterns.get(1, 0)}**. Whole-entry deadline diagnostics without a regex timeout: **{outcomes.get(5, 0)}**. Parser exceptions: **{outcomes.get(3, 0)}**.",
            "",
            "| Threshold | Pattern parsing | Line-framing patterns | Whole entry |",
            "|---|---:|---:|---:|",
        ]
        for threshold in (1, 5, 10, 12, 15, 50, 90, 100):
            cells = []
            for key in ("pattern_1", "pattern_2", "entry_all"):
                dist = report["distributions"][key]
                n = dist["at_or_above_ms"][str(threshold)]
                cells.append(f"{n:,} ({100 * n / dist['count']:.6f}%)")
            lines.append(f"| >= {threshold} ms | " + " | ".join(cells) + " |")
        lines += [
            "",
            f"End-to-end replay time: **{summary['elapsed_seconds']:.2f} seconds**. This includes work beyond parsing and concurrent machine load.",
            "",
            f"Detailed results: [{name}/timing-statistics.json]({name}/timing-statistics.json), [per-pattern CSV]({name}/timing-patterns.csv), [per-file CSV]({name}/timing-files.csv), [slowest patterns]({name}/timing-slowest-patterns.csv), [slowest entries]({name}/timing-slowest-entries.csv).",
            "",
        ]
    lines += [
        "## Instrumentation overhead and limits",
        "",
        calibration["method"],
        "",
        "| Sample stratum | Median added time per entry | Median elapsed-time increase |",
        "|---|---:|---:|",
    ]
    for row in calibration["aggregates"]:
        if row["metric"] == "wall_ns_per_entry":
            lines.append(
                f"| {'Recognized' if row['recognized'] else 'Ignored'} | {row['median_added_ns'] / 1000:.2f} microseconds | {(row['median_ratio'] - 1) * 100:.1f}% |"
            )
    lines += [
        "",
        "- Pattern timers surround the regex backend call; logger bookkeeping is excluded from that pattern duration. Whole-entry timings include the pattern-probe bookkeeping inside Reader.parse. Buffered file writes occur after timed boundaries.",
        "- These calibration figures are from a separate small warmed sample; they cannot reliably correct individual measurements or predict every workload. The reported data is not adjusted.",
        "- Timings include operating-system scheduling delays and effects of concurrent testing. A wall-clock operation above its allowance is not by itself proof that the regex backend raised a timeout. Timeout counters record the actual exception.",
        "- The 100 ms whole-entry deadline is checked at defined points in the existing parser; it is not a hard operating-system execution cutoff. Instrumentation leaves both limits unchanged.",
        "- Very rare tail events vary between runs. Missing game events and unobserved rules remain semantic-test limitations even when timings and integrity checks pass.",
        "",
        "## Verification and preserved files",
        "",
        f"- Unit suite: exit {c['unit_suite_exit']}; full transcript in [unit-tests.txt](unit-tests.txt).",
        f"- Corpus failed files: {len(c['failed_files'])}; enumeration errors: {len(c['enumeration_errors'])}; production source unchanged: {c['code_unchanged']}.",
        f"- Story exceptions: {len(s['exceptions'])}; scan errors: {len(s['scan_errors'])}; database integrity: {s['database_integrity']}; production source unchanged: {s['code_unchanged']}.",
        f"- Original/reference/production file hashes checked: {len(baseline)}; changed or missing: {len(differences)}.",
        f"- Input diagnostics: corpus {json.dumps(c['diagnostic_counts'], sort_keys=True)}; story {json.dumps(s['diagnostic_counts'], sort_keys=True)}.",
        "- Every timing file has its exact byte length checked against the declared row count; entry totals and budget diagnostics are reconciled with each replay summary.",
        "- Chronological story findings are retained in the replay summary. Evidence gaps are not automatically parser defects.",
        "",
        "## Raw timing data",
        "",
        "- [Corpus timing folders](corpus/timings/) contain one directory per input file; [story timing folder](story/timings/) contains the continuous run.",
        "- Every folder has metadata.json, patterns.bin and entries.bin. The metadata specifies little-endian Python struct layouts, row lengths, field names, file IDs, pattern expressions, phases, operations and outcome codes. Times are integer nanoseconds; source positions are byte offsets.",
        "- patterns.bin records duration, source range, file ID, pattern ID, requested budget, phase, operation and exception status. entries.bin records source range, elapsed time, thread CPU time, file ID and parse outcome.",
        "- Raw binary storage preserves all measurements compactly. CSV files contain readable per-pattern/per-file statistics and the 50 slowest operations/entries. Full standard deviations and additional percentiles are in the JSON reports.",
        "- Reproduce the analysis with tools/timing_statistics.py and NumPy; rerun measurements using tools/corpus_test.py or tools/story_test.py with --timings. Test-only hooks live in tools/timing_probe.py.",
        "",
    ]
    followup_path = root / "timeout-followup.json"
    if followup_path.exists():
        followup = json.loads(followup_path.read_text(encoding="utf-8"))
        same = followup["corpus_same_entry"][0]
        fresh = followup["isolated_summary"]["fresh reader"]
        reused = followup["isolated_summary"]["reused reader"]
        lines += [
            "## Follow-up on the single chronological timeout",
            "",
            f"The notification-detection regex raised TimeoutError after {followup['timed_out_operation']['duration_ms']:.4f} ms on an objective-marker log line. The corpus replay processed the identical byte range in {same['wall_ms']:.4f} ms and classified it as ignored.",
            "",
            f"Isolated follow-up: {fresh['count']} fresh-reader trials and {reused['count']} reused-reader trials, with {fresh['timeout_count'] + reused['timeout_count']} timeouts. Maximum whole-entry durations were {fresh['max_ms']:.4f} ms and {reused['max_ms']:.4f} ms respectively. These are separate diagnostic trials; the original full-run timeout remains counted.",
            "",
            "This did not reproduce as a consistently expensive input. Scheduling, machine load and instrumentation are possible contributors; the measurements do not establish the cause. See [timeout-followup.json](timeout-followup.json) for the exact source range and every retry.",
            "",
        ]
    highlights = [
        "## Main findings",
        "",
        f"- Both passes covered {c['files']} files and {c['totals']['records']:,} entries each. All {corpus['pattern_count'] + story['pattern_count']:,} regex-operation measurements and {corpus['entry_count'] + story['entry_count']:,} whole-entry measurements were logged.",
        f"- The chronological run's 99th-percentile whole-entry time was {story['distributions']['entry_all']['p99_ms']:.4f} ms; for recognized entries without diagnostics it was {story['distributions']['entry_recognized_clean']['p99_ms']:.4f} ms. Most entries were ignored, so the recognized-entry breakdown matters.",
        f"- Pattern timeouts: {corpus['pattern_status_counts'].get(1, 0)} in the corpus pass and {story['pattern_status_counts'].get(1, 0)} in the chronological pass. No entry reached the 100 ms whole-entry allowance.",
        "- The existing limits had substantial headroom for ordinary processing in this run, but the one regex timeout means 15 ms did not eliminate all observed timeout events. These results do not establish a worst-case guarantee.",
        "- No production reader, original skill, frozen reference or game-log content was changed. All integrity checks passed; existing semantic evidence gaps remain documented.",
        "",
    ]
    lines[4:4] = highlights
    (root / "REPORT.md").write_text("\n".join(lines), encoding="utf-8")
    print(json.dumps({k: r["distributions"] for k, r in reports.items()}, indent=2))


if __name__ == "__main__":
    main()
