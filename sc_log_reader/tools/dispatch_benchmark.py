"""Uninstrumented, alternating warm Reader and SQLite Service comparisons.

Imports the frozen after-T1 package under an alias in the same process. Reads
bounded real-log prefixes; never modifies source logs or launches a host.
"""

import argparse
import hashlib
import importlib
import importlib.util
import json
import statistics
import sys
import time
from dataclasses import asdict
from pathlib import Path

from sc_log_reader import reader as current
from sc_log_reader.service import Service


def load_baseline(root):
    name = "dispatch_baseline"
    spec = importlib.util.spec_from_file_location(
        name, root / "__init__.py", submodule_search_locations=[str(root)]
    )
    package = importlib.util.module_from_spec(spec)
    sys.modules[name] = package
    spec.loader.exec_module(package)
    return importlib.import_module(name + ".reader"), importlib.import_module(
        name + ".service"
    )


def sample(manifest, baseline, instructions):
    files = json.loads(manifest.read_text())["files"]
    strata = {"unrecognized": [], "recognized": [], "mixed": []}
    provenance = []
    reader = baseline.Reader(instructions)
    for index in sorted({round(j * (len(files) - 1) / 7) for j in range(8)}):
        path = Path(files[index]["path"])
        with path.open("rb") as stream:
            data = stream.read(4 * 1024 * 1024)
        assembler = baseline.RecordAssembler(instructions)
        # No finish(): the byte cap is not the actual end of the source file.
        records = assembler.feed(data)
        counts = {"unrecognized": 0, "recognized": 0}
        strata["mixed"].extend(records[:200])
        for record in records:
            event = reader.parse(record.text, complete=record.complete)
            kind = "unrecognized" if event is None else "recognized"
            limit = 125 if kind == "unrecognized" else 40
            if counts[kind] < limit:
                strata[kind].append(record)
                counts[kind] += 1
            if counts == {"unrecognized": 125, "recognized": 40}:
                break
        provenance.append(
            {
                "path": str(path),
                "prefix_bytes": len(data),
                "prefix_sha256": hashlib.sha256(data).hexdigest(),
                **counts,
            }
        )
    # Assign unique synthetic offsets because the samples combine source files.
    return {
        kind: [
            current.Record(
                r.text, i * 100000, i * 100000 + len(r.text.encode()), r.complete
            )
            for i, r in enumerate(records)
        ]
        for kind, records in strata.items()
    }, provenance


def signature(reader, records):
    result = []
    for record in records:
        event = reader.parse(record.text, complete=record.complete)
        result.append(
            [asdict(event) if event is not None else None, reader.last_disposition]
        )
    return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--baseline", type=Path, required=True, help="Frozen package directory"
    )
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--pairs", type=int, default=6)
    parser.add_argument("--reader-loops", type=int, default=12)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=False)
    baseline, old_service = load_baseline(args.baseline.resolve())
    raw = current.bundled_bytes()
    assert raw == (args.baseline / "data/instructions.json").read_bytes()
    packages = {
        "baseline": baseline.Instructions.load(raw),
        "optimized": current.Instructions.load(raw),
    }
    readers = {"baseline": baseline.Reader, "optimized": current.Reader}
    services = {"baseline": old_service.Service, "optimized": Service}
    strata, provenance = sample(args.manifest, baseline, packages["baseline"])
    (args.output / "sample.json").write_text(
        json.dumps(
            {
                name: [asdict(record) for record in records]
                for name, records in strata.items()
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    rows = []
    for kind, records in strata.items():
        expected = signature(readers["baseline"](packages["baseline"]), records)
        assert (
            signature(readers["optimized"](packages["optimized"]), records) == expected
        ), kind
        for layer in ("reader", "service"):
            for repeat in range(args.pairs):
                signatures = {}
                for variant in (
                    ("baseline", "optimized")
                    if repeat % 2 == 0
                    else ("optimized", "baseline")
                ):
                    service = None
                    reader = readers[variant](packages[variant])
                    for record in records:
                        reader.parse(record.text, complete=record.complete)
                    if layer == "service":
                        service = services[variant](
                            args.output / f"{kind}-{repeat}-{variant}",
                            instructions=packages[variant],
                        )
                        service.reader = reader
                        # Warm SQLite and the real ingestion path before measurement.
                        for record in records[:32]:
                            service.ingest(record, "LIVE", "warm")
                    try:
                        cpu, wall = time.thread_time_ns(), time.perf_counter_ns()
                        if service is None:
                            for _ in range(args.reader_loops):
                                for record in records:
                                    reader.parse(record.text, complete=record.complete)
                            count = len(records) * args.reader_loops
                        else:
                            for record in records:
                                service.ingest(record, "LIVE", "measured")
                            count = len(records)
                        wall, cpu = (
                            time.perf_counter_ns() - wall,
                            time.thread_time_ns() - cpu,
                        )
                        rows.append(
                            {
                                "stratum": kind,
                                "layer": layer,
                                "repeat": repeat,
                                "variant": variant,
                                "records": count,
                                "wall_ns_per_record": wall / count,
                                "cpu_ns_per_record": cpu / count,
                            }
                        )
                        if service is not None:
                            signatures[variant] = {
                                "counts": service.health_counts,
                                "events": service.events("LIVE", limit=None),
                                "snapshot": service._snapshot("LIVE"),
                                "observations": service.db.execute(
                                    "SELECT occurrence,environment,generation,byte_start,byte_end,event_type,errors,fields,source_timestamp,instruction_version,rule_id FROM observations ORDER BY occurrence"
                                ).fetchall(),
                            }
                    finally:
                        if service is not None:
                            service.close()
                if layer == "service":
                    assert signatures["baseline"] == signatures["optimized"], (
                        kind,
                        repeat,
                    )
    aggregates = []
    for kind in strata:
        for layer in ("reader", "service"):
            for metric in ("wall_ns_per_record", "cpu_ns_per_record"):
                selected = [
                    row
                    for row in rows
                    if row["stratum"] == kind and row["layer"] == layer
                ]
                ratios = []
                for repeat in range(args.pairs):
                    pair = {
                        row["variant"]: row[metric]
                        for row in selected
                        if row["repeat"] == repeat
                    }
                    ratios.append(pair["optimized"] / pair["baseline"])
                aggregates.append(
                    {
                        "stratum": kind,
                        "layer": layer,
                        "metric": metric,
                        "baseline_median": statistics.median(
                            row[metric]
                            for row in selected
                            if row["variant"] == "baseline"
                        ),
                        "optimized_median": statistics.median(
                            row[metric]
                            for row in selected
                            if row["variant"] == "optimized"
                        ),
                        "median_paired_ratio": statistics.median(ratios),
                        "pair_ratios": ratios,
                    }
                )
    result = {
        "method": "Same-process snapshot imports; uninstrumented warmed Reader and SQLite Service.ingest; alternating AB/BA pairs. Setup and sample/semantic checks outside timers. Service warmup uses distinct generation. Synthetic unique offsets prevent accidental duplicate bypass. Wall and calling-thread CPU measured separately. This is sampled pipeline performance, not live Wingman/host performance or corpus-wide timing.",
        "python": sys.version,
        "instruction_sha256": hashlib.sha256(raw).hexdigest(),
        "baseline_reader_sha256": hashlib.sha256(
            (args.baseline / "reader.py").read_bytes()
        ).hexdigest(),
        "optimized_reader_sha256": hashlib.sha256(
            Path(current.__file__).read_bytes()
        ).hexdigest(),
        "records_per_stratum": {kind: len(records) for kind, records in strata.items()},
        "semantic_equivalence": "Exact sampled Reader events/dispositions and Service observations/events/state/counts; only DB wall observed_at/updated columns excluded.",
        "provenance": provenance,
        "aggregates": aggregates,
        "runs": rows,
    }
    (args.output / "report.json").write_text(
        json.dumps(result, indent=2), encoding="utf-8"
    )
    print(json.dumps(aggregates, indent=2))


if __name__ == "__main__":
    main()
