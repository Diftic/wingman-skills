import copy
import json
import tempfile
import time
import unittest
from datetime import UTC, datetime
from pathlib import Path

from sc_log_reader.reader import (
    Event,
    InstructionError,
    Instructions,
    Reader,
    bundled_bytes,
)
from sc_log_reader.service import Service, Tailer
from sc_log_reader.state import State


class ResilienceTests(unittest.TestCase):
    def test_direct_parse_cannot_treat_unclosed_notification_as_complete(self):
        e = Reader(Instructions.load(bundled_bytes())).parse(
            '<SHUDEvent> Added notification "Awarded 500 aUEC'
        )
        self.assertIn("incomplete_record", e.errors)

    def test_pathological_regex_times_out_without_state_event(self):
        d = json.loads(bundled_bytes())
        d["rules"][0]["match"] = {"regex": "(a+)+$", "source": "record.text"}
        r = Reader(Instructions.load(json.dumps(d).encode()))
        start = time.monotonic()
        e = r.parse("a" * 20000 + "!")
        self.assertEqual(e.event_type, "diagnostic")
        self.assertIn("regex_budget_exceeded", e.errors)
        self.assertLess(time.monotonic() - start, 1)

    def test_compile_expansion_is_rejected(self):
        d = json.loads(bundled_bytes())
        d["rules"][0]["match"] = {"regex": "a{999999999}", "source": "record.text"}
        with self.assertRaises(InstructionError):
            Instructions.load(json.dumps(d).encode())

    def test_conflicting_duplicate_field_is_not_silently_chosen(self):
        e = Reader(Instructions.load(bundled_bytes())).parse(
            '<SHUDEvent> Added notification "Contract Accepted: A:" MissionId[m1] MissionId[m2]'
        )
        self.assertIn("conflicting_aliases:mission_id", e.errors)

    def test_duplicate_reward_notification_does_not_double_book(self):
        state = State(Instructions.load(bundled_bytes()).data["lookups"])
        e = Event(
            "reward_earned",
            {"amount": "500", "currency": "aUEC", "notification_id": "13"},
            datetime(2026, 9, 15, tzinfo=UTC),
        )
        self.assertTrue(state.apply(e, "a", "g"))
        self.assertEqual(state.apply(e, "b", "g"), [])
        e = copy.deepcopy(e)
        e.source_timestamp = e.source_timestamp.replace(second=1)
        self.assertTrue(state.apply(e, "c", "g"))

    def test_fixed_money_contract_requires_recipient_and_text_types(self):
        state = State(Instructions.load(bundled_bytes()).data["lookups"])
        rows = state.apply(
            Event("money_sent", {"amount": "500", "currency": "aUEC"}), "1", "g"
        )
        self.assertFalse(any(r.get("amount_auec") is not None for r in rows))
        state.apply(
            Event("contract_accepted", {"mission_id": "m1", "mission_name": 42}),
            "2",
            "g",
        )
        self.assertFalse(state.data["active_missions"])

    def test_replacement_file_creates_new_generation(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            path = root / "Game.log"
            path.write_bytes(b"User Login Success Handle[A]\n")
            service = Service(root / "runtime")
            try:
                tail = Tailer(service, {"LIVE": path})
                tail.poll()
                first = service.stream("LIVE")["generation"]
                path.rename(root / "old.log")
                path.write_bytes(b"User Login Success Handle[B]\n")
                tail.poll()
                self.assertNotEqual(service.stream("LIVE")["generation"], first)
                self.assertEqual(service.state("LIVE")["player_name"], "B")
            finally:
                service.close()

    def test_truncation_inside_uncommitted_fragment_drops_old_bytes(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            path = root / "Game.log"
            path.write_bytes(b"User Login Success Handle[A]\n" + b"x" * 200)
            service = Service(root / "runtime")
            try:
                tail = Tailer(service, {"LIVE": path})
                tail.poll()
                path.write_bytes(
                    b"User Login Success Handle[A]\nUser Login Success Handle[B]\n"
                )
                tail.poll()
                tail.poll()
                self.assertEqual(service.state("LIVE")["player_name"], "B")
            finally:
                service.close()


if __name__ == "__main__":
    unittest.main()
