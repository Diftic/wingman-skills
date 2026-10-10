"""Paired, warmed Reader.parse overhead check on a stratified real-log sample."""

import argparse
import hashlib
import json
import statistics
import time
from pathlib import Path

from timing_probe import TimingProbe

from sc_log_reader.reader import Instructions, Reader, RecordAssembler, bundled_bytes


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    out = Path(args.output)
    out.mkdir(parents=True, exist_ok=False)
    files = json.loads(Path(args.manifest).read_text())["files"]
    instructions = Instructions.load(bundled_bytes())
    reader = Reader(instructions)
    pools = {False: [], True: []}
    provenance = []
    # Stratify by result, spreading the sample across eight corpus positions.
    for i in sorted({round(j * (len(files) - 1) / 7) for j in range(8)}):
        path = Path(files[i]["path"])
        data = path.open("rb").read(4 * 1024 * 1024)
        assembler = RecordAssembler(instructions)
        records = assembler.feed(data)  # do not manufacture EOF for truncated input
        selected = {False: 0, True: 0}
        for record in records:
            recognized = reader.parse(record.text, complete=record.complete) is not None
            if selected[recognized] < 125:
                pools[recognized].append(record)
                selected[recognized] += 1
            if min(selected.values()) >= 125:
                break
        provenance.append(
            {
                "path": str(path),
                "prefix_bytes": len(data),
                "prefix_sha256": hashlib.sha256(data).hexdigest(),
                "selected_ignored": selected[False],
                "selected_recognized": selected[True],
            }
        )
    results = []
    for recognized, records in pools.items():
        for repeat in range(6):
            for instrumented in [False, True] if repeat % 2 == 0 else [True, False]:
                probe = (
                    TimingProbe(out / f"{int(recognized)}-{repeat}")
                    if instrumented
                    else None
                )
                try:
                    if probe:
                        probe.set_file(1, "mixed calibration sample")
                    reader = Reader(instructions)
                    for record in records:
                        reader.parse(record.text, complete=record.complete)
                    cpu = time.thread_time_ns()
                    wall = time.perf_counter_ns()
                    for record in records:
                        if probe:
                            probe.set_record(record.start, record.end)
                        reader.parse(record.text, complete=record.complete)
                    wall = time.perf_counter_ns() - wall
                    cpu = time.thread_time_ns() - cpu
                    results.append(
                        {
                            "recognized": recognized,
                            "repeat": repeat,
                            "instrumented": instrumented,
                            "records": len(records),
                            "wall_ns_per_entry": wall / len(records),
                            "cpu_ns_per_entry": cpu / len(records),
                        }
                    )
                finally:
                    if probe:
                        probe.close()
    aggregates = []
    for recognized in pools:
        for metric in ("wall_ns_per_entry", "cpu_ns_per_entry"):
            ratios = []
            deltas = []
            for repeat in range(6):
                pair = {
                    r["instrumented"]: r[metric]
                    for r in results
                    if r["recognized"] == recognized and r["repeat"] == repeat
                }
                ratios.append(pair[True] / pair[False])
                deltas.append(pair[True] - pair[False])
            aggregates.append(
                {
                    "recognized": recognized,
                    "metric": metric,
                    "median_ratio": statistics.median(ratios),
                    "median_added_ns": statistics.median(deltas),
                    "pair_ratios": ratios,
                }
            )
    report = {
        "method": "Eight file positions; up to 125 ignored and 125 recognized records per file; six paired warmed passes; AB/BA alternation. Separate equal-sized strata are not the corpus mixture. Disk logging included. No correction applied to measured results.",
        "sample_provenance": provenance,
        "results": results,
        "aggregates": aggregates,
    }
    (out / "calibration.json").write_text(
        json.dumps(report, indent=2), encoding="utf-8"
    )
    print(json.dumps(aggregates, indent=2))


if __name__ == "__main__":
    main()
