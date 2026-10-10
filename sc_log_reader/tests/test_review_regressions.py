import json
import sqlite3
import tempfile
import unittest
from pathlib import Path

from sc_log_reader.reader import InstructionError, Instructions, bundled_bytes
from sc_log_reader.service import Service, Tailer


class ReviewRegressions(unittest.TestCase):
    def test_invalid_replacement_group_rejected_at_load(self):
        d = json.loads(bundled_bytes())
        d["rules"][0]["read"] = [
            {"op": "constant", "fields": {"value": "A"}},
            {
                "op": "normalize",
                "field": "value",
                "steps": [
                    {"regex_replace": {"pattern": "A", "replacement": r"\g<missing>"}}
                ],
            },
        ]
        with self.assertRaises(InstructionError):
            Instructions.load(json.dumps(d).encode())

    def test_restart_keeps_discarding_an_oversized_physical_line(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            log = root / "Game.log"
            log.write_bytes(
                b"x" * (256 * 1024) + b"User Login Success Handle[FakePlayer]\n"
            )
            service = Service(root / "runtime")
            Tailer(service, {"LIVE": log}).poll()
            self.assertIsNone(service.state("LIVE")["player_name"])
            service.close()
            service = Service(root / "runtime")
            try:
                Tailer(service, {"LIVE": log}).poll()
                self.assertIsNone(service.state("LIVE")["player_name"])
            finally:
                service.close()

    def test_temporary_database_failure_retries_uncommitted_records(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            log = root / "Game.log"
            log.write_text(
                "".join(
                    "User Login Success Handle[" + name + "]\n"
                    for name in ("A", "B", "C")
                )
            )
            service = Service(root / "runtime")
            try:
                tail = Tailer(service, {"LIVE": log})
                real = service._ingest_in_transaction
                calls = 0

                def transient(*args, **kwargs):
                    nonlocal calls
                    calls += 1
                    if calls == 2:
                        raise sqlite3.OperationalError("database is locked")
                    return real(*args, **kwargs)

                service._ingest_in_transaction = transient
                tail.poll()
                self.assertTrue(tail.errors)
                self.assertEqual(service.stream("LIVE")["offset"], 0)
                self.assertEqual(service.events("LIVE"), [])
                self.assertEqual(service.health_counts, {})
                service._ingest_in_transaction = real
                tail.poll()
                self.assertEqual(service.state("LIVE")["player_name"], "C")
                self.assertEqual(len(service.events("LIVE")), 3)
            finally:
                service.close()


if __name__ == "__main__":
    unittest.main()
