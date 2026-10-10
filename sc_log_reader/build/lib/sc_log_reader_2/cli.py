"""Standalone development/replay and human-controlled update commands."""

from __future__ import annotations

import argparse
import json
import tempfile
import time
from pathlib import Path

from .reader import MAX_PACKAGE_BYTES, Instructions, RecordAssembler, bundled_bytes
from .service import Service, Tailer
from .updates import UpdateManager, digest


def _load(path):
    with Path(path).open("rb") as stream:
        return Instructions.load(stream.read(MAX_PACKAGE_BYTES + 1))


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="SC Log Reader 2: independent reader and instruction updates"
    )
    sub = parser.add_subparsers(dest="command", required=True)
    validate = sub.add_parser("validate")
    validate.add_argument("instructions")
    replay = sub.add_parser("replay")
    replay.add_argument("log")
    replay.add_argument("--instructions")
    replay.add_argument("--environment", default="LIVE")
    replay.add_argument("--game-build")
    watch = sub.add_parser("watch")
    watch.add_argument("log")
    watch.add_argument("--state-dir", required=True)
    watch.add_argument("--environment", default="LIVE")
    watch.add_argument("--url")
    for name in ("check", "status", "approve", "skip", "rollback", "review-updates"):
        command = sub.add_parser(name)
        command.add_argument(
            "--state-dir",
            required=True,
            help="Same runtime directory configured in the skill",
        )
        if name == "check":
            command.add_argument("--url", required=True)
        if name in ("approve", "skip"):
            command.add_argument(
                "--digest",
                required=True,
                help="Exact SHA-256 displayed by check/status; confirms this specific file",
            )
    args = parser.parse_args(argv)
    try:
        if args.command == "review-updates":
            from .review_ui import show_review

            show_review(args.state_dir)
            return 0
        if args.command == "validate":
            inst = _load(args.instructions)
            result = {
                "valid": True,
                "version": inst.version,
                "revision": inst.revision,
                "rules": len(inst.data["rules"]),
                "sha256": digest(inst.raw),
                "verified_game_builds": inst.data["verified_game_builds"],
            }
        elif args.command == "replay":
            instructions = (
                _load(args.instructions)
                if args.instructions
                else Instructions.load(bundled_bytes())
            )
            # A replay never activates staged updates or writes beside Game.log.
            with tempfile.TemporaryDirectory(prefix="sc-reader-replay-") as directory:
                service = Service(directory, instructions=instructions)
                try:
                    assembler = RecordAssembler(instructions)
                    counts = {}
                    record_count = 0
                    with Path(args.log).open("rb") as stream:
                        while chunk := stream.read(256 * 1024):
                            for record in assembler.feed(chunk):
                                record_count += 1
                                for row in service.ingest(
                                    record, args.environment, "replay", args.game_build
                                ):
                                    counts[row["event_type"]] = (
                                        counts.get(row["event_type"], 0) + 1
                                    )
                    for record in assembler.finish():
                        record_count += 1
                        for row in service.ingest(
                            record, args.environment, "replay", args.game_build
                        ):
                            counts[row["event_type"]] = (
                                counts.get(row["event_type"], 0) + 1
                            )
                    result = {
                        "records": record_count,
                        "event_counts": counts,
                        "state": service.state(args.environment),
                        "recent_events": service.events(args.environment),
                        "diagnostics": service.diagnostics(args.environment),
                        "instruction_version": instructions.version,
                    }
                finally:
                    service.close()
        elif args.command == "watch":
            service = Service(
                args.state_dir, update_url=args.url, activate_updates=True
            )
            try:
                tail = Tailer(service, {args.environment: args.log})
                next_check = 0
                while True:
                    for row in tail.poll():
                        print(json.dumps(row), flush=True)
                    if args.url and time.monotonic() >= next_check:
                        try:
                            print(
                                json.dumps(
                                    {"instruction_update": service.updates.check()}
                                ),
                                flush=True,
                            )
                        except ValueError as exc:
                            print(json.dumps({"update_error": str(exc)}), flush=True)
                        next_check = time.monotonic() + 6 * 3600
                    time.sleep(0.25)
            except KeyboardInterrupt:
                return 0
            finally:
                service.close()
        else:
            updates = UpdateManager(
                Path(args.state_dir) / "instructions", getattr(args, "url", None)
            )
            if args.command == "check":
                result = updates.check()
            elif args.command == "status":
                result = updates.status()
            elif args.command == "approve":
                result = updates.approve(args.digest)
            elif args.command == "skip":
                result = updates.skip(args.digest)
            else:
                result = updates.rollback()
        print(json.dumps(result, indent=2))
        return 0
    except (OSError, ValueError) as exc:
        print(json.dumps({"error": str(exc)}))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
