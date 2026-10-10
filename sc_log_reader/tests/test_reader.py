import copy
import json
import unittest

from sc_log_reader.reader import (
    InstructionError,
    Instructions,
    Reader,
    RecordAssembler,
    bundled_bytes,
)


def notification(text, tail="MissionId: [m1], ObjectiveId: [o1]"):
    return (
        '<2026-09-15T12:00:00Z> [Notice] <SHUDEvent_OnNotification> Added notification "'
        + text
        + '" [13] to queue. '
        + tail
    )


class ReaderTests(unittest.TestCase):
    def setUp(self):
        self.reader = Reader(Instructions.load(bundled_bytes()))

    def test_mission_spacing_alias_and_missing_terminal_colon(self):
        e = self.reader.parse(
            notification("Contract Accepted : Delivery: Priority", "MissionID : [m1]")
        )
        self.assertEqual(e.event_type, "contract_accepted")
        self.assertEqual(e.fields["mission_name"], "Delivery: Priority")
        self.assertEqual(e.fields["mission_id"], "m1")
        self.assertEqual(e.source_timestamp.utcoffset().total_seconds(), 0)
        self.assertFalse(e.errors)

    def test_objective_text_cannot_impersonate_contract_failure(self):
        e = self.reader.parse(
            notification("New Objective: Investigate Contract Failed: message: ")
        )
        self.assertEqual(e.event_type, "objective_new")

    def test_missing_mission_id_is_incomplete(self):
        e = self.reader.parse(notification("Contract Accepted: Delivery:", ""))
        self.assertIn("missing:mission_id", e.errors)

    def test_missing_timestamp_stays_unknown(self):
        e = self.reader.parse("User Login Success Handle[Mallachi]")
        self.assertIsNone(e.source_timestamp)

    def test_multiline_reward_waits_for_closing_quote(self):
        a = RecordAssembler()
        first = "<2026-09-15T12:00:00Z> <SHUDEvent> Added notification \"You've earned: 30\n"
        self.assertEqual(a.feed(first.encode()), [])
        records = a.feed(b'rewards: " [13] to queue.\n')
        self.assertEqual(len(records), 1)
        e = self.reader.parse(records[0].text)
        self.assertEqual(e.fields["quantity"], "30")
        self.assertEqual(e.fields["item_name"], "rewards")
        self.assertNotIn("amount", e.fields)

    def test_unclosed_notification_is_not_promoted_at_next_record(self):
        a = RecordAssembler()
        a.feed(
            b'<2026-09-15T12:00:00Z> <SHUDEvent> Added notification "Awarded 500 aUEC\n'
        )
        records = a.feed(b"<2026-09-15T12:00:01Z> User Login Success Handle[A]\n")
        self.assertFalse(records[0].complete)
        self.assertTrue(records[1].complete)
        self.assertTrue(self.reader.parse(records[0].text, complete=False).errors)

    def test_unitless_reward_never_becomes_money(self):
        e = self.reader.parse(notification("You've earned: 15,000: "))
        self.assertEqual(e.fields["unresolved_number"], "15000")
        self.assertNotIn("amount", e.fields)

    def test_conflicting_matches_rejected(self):
        d = json.loads(bundled_bytes())
        other = copy.deepcopy(next(r for r in d["rules"] if r["event"] == "user_login"))
        other["id"] = "conflict"
        other["event"] = "session_start"
        d["rules"].append(other)
        e = Reader(Instructions.load(json.dumps(d).encode())).parse(
            "User Login Success Handle[A]"
        )
        self.assertEqual(e.event_type, "diagnostic")
        self.assertIn("ambiguous_rules", e.errors)

    def test_invalid_and_executable_instructions_are_rejected(self):
        for mutation in ("op", "pattern", "format", "unknown"):
            with self.subTest(mutation=mutation):
                d = json.loads(bundled_bytes())
                if mutation == "op":
                    d["rules"][0]["read"] = [{"op": "eval", "code": "print(1)"}]
                elif mutation == "pattern":
                    d["rules"][0]["match"] = {"regex": "[", "source": "record.text"}
                elif mutation == "format":
                    d["format_version"] = 999
                else:
                    d["execute"] = "anything"
                with self.assertRaises(InstructionError):
                    Instructions.load(json.dumps(d).encode())

    def test_money_transfer_assembles_recipient_and_amount(self):
        e = self.reader.parse(notification("You sent Mallachi:\n1,500 aUEC: "))
        self.assertEqual(e.event_type, "money_sent")
        self.assertEqual(e.fields["recipient"], "Mallachi")
        self.assertEqual(e.fields["amount"], "1500")

    def test_duplicate_json_keys_rejected(self):
        with self.assertRaises(InstructionError):
            Instructions.load(b'{"format_version":1,"format_version":2}')

    def test_update_notification_is_ignored(self):
        self.assertIsNone(
            self.reader.parse(
                notification("Awarded 500 aUEC: ") + " UpdateNotificationItem"
            )
        )


if __name__ == "__main__":
    unittest.main()
