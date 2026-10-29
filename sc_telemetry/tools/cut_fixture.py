"""Cut a time window out of a probe recording (frames_<date>.jsonl) into a small test fixture.

Usage:
    python cut_fixture.py <recording.jsonl> <out.jsonl> <HH:MM:SS start> <HH:MM:SS end> [--every N]

Times are local wall-clock times on the recording's date. `--every N` keeps every Nth frame (default 1), but always
keeps frames that carry game events, so thinned fixtures still contain every seat change.
"""
import argparse
import json
import time
from pathlib import Path


def _epoch(date: str, clock: str) -> float:
    return time.mktime(time.strptime(f"{date} {clock}", "%Y-%m-%d %H:%M:%S"))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("recording", type=Path)
    parser.add_argument("out", type=Path)
    parser.add_argument("start")
    parser.add_argument("end")
    parser.add_argument("--every", type=int, default=1)
    parser.add_argument("--date", help="YYYY-MM-DD, when the file name does not end in the date")
    args = parser.parse_args()

    date = args.date or args.recording.stem.split("_")[-1]
    start, end = _epoch(date, args.start), _epoch(date, args.end)
    kept = seen = 0
    with args.recording.open(encoding="utf-8") as source, args.out.open("w", encoding="utf-8") as out:
        for line in source:
            row = json.loads(line)
            if row["t"] < start:
                continue
            if row["t"] > end:
                break
            seen += 1
            if seen % args.every == 0 or "events" in row["frame"]:
                out.write(json.dumps(row, separators=(",", ":")) + "\n")
                kept += 1
    print(f"{args.out.name}: {kept} of {seen} frames")


if __name__ == "__main__":
    main()
