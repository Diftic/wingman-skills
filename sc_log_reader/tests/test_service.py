import tempfile
import unittest
from pathlib import Path

from sc_log_reader.reader import Record
from sc_log_reader.service import Service, Tailer, ToolInterface

LOGIN = b"<2026-09-15T12:00:00Z> User Login Success Handle[Mallachi]\n"
MISSION = b'<2026-09-15T12:00:01Z> <SHUDEvent> Added notification "Contract Accepted: Delivery:" [13] to queue. MissionId: [m1]\n'
REWARD = b'<2026-09-15T12:00:02Z> <SHUDEvent> Added notification "Awarded 500 aUEC:" [14] to queue.\n'


class ServiceTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.service = Service(self.root / "runtime")
        self.addCleanup(self.service.close)

    def test_occurrence_dedup_survives_service_restart(self):
        record = Record(REWARD.decode().strip(), 0, len(REWARD))
        self.service.ingest(record, "LIVE", "g1")
        self.service.close()
        other = Service(self.root / "runtime")
        self.addCleanup(other.close)
        self.assertEqual(other.ingest(record, "LIVE", "g1"), [])
        self.assertEqual(len(other.events("LIVE")), 1)
        self.assertEqual(other.events("LIVE")[0]["amount_auec"], 500.0)

    def test_environments_have_separate_state(self):
        self.service.ingest(Record(LOGIN.decode(), 0, len(LOGIN)), "LIVE", "g1")
        self.service.ingest(
            Record(MISSION.decode(), len(LOGIN), len(LOGIN) + len(MISSION)),
            "LIVE",
            "g1",
        )
        self.service.ingest(
            Record(LOGIN.decode().replace("Mallachi", "Other"), 0, 100), "PTU", "g1"
        )
        self.assertIn("m1", self.service.state("LIVE")["active_missions"])
        self.assertEqual(self.service.state("PTU")["active_missions"], {})

    def test_partial_notification_resumes_across_process_restart(self):
        path = self.root / "Game.log"
        path.write_bytes(LOGIN + MISSION[:65])
        tail = Tailer(self.service, {"LIVE": path})
        tail.poll()
        self.assertFalse(self.service.state("LIVE")["active_missions"])
        self.service.close()
        self.service = Service(self.root / "runtime")
        self.addCleanup(self.service.close)
        with path.open("ab") as f:
            f.write(MISSION[65:])
        Tailer(self.service, {"LIVE": path}).poll()
        self.assertIn("m1", self.service.state("LIVE")["active_missions"])
        self.assertEqual(len(self.service.events("LIVE")), 2)

    def test_tail_catches_up_silently_then_reports_only_new_events(self):
        path = self.root / "Game.log"
        path.write_bytes(LOGIN)
        tail = Tailer(self.service, {"LIVE": path})
        self.assertEqual(tail.poll(), [])
        with path.open("ab") as f:
            f.write(MISSION)
        output = tail.poll()
        self.assertEqual([e["event_type"] for e in output], ["mission_accepted"])
        self.assertEqual(tail.poll(), [])

    def test_rotation_and_same_file_truncation_reset_state(self):
        path = self.root / "Game.log"
        path.write_bytes(LOGIN + MISSION)
        tail = Tailer(self.service, {"LIVE": path})
        tail.poll()
        self.assertIn("m1", self.service.state("LIVE")["active_missions"])
        path.write_bytes(LOGIN.replace(b"Mallachi", b"Other"))
        tail.poll()
        self.assertFalse(self.service.state("LIVE")["active_missions"])
        self.assertEqual(self.service.state("LIVE")["player_name"], "Other")

    def test_unknown_and_incomplete_records_do_not_create_notifications(self):
        self.assertEqual(self.service.ingest(Record("unknown", 0, 7), "LIVE", "g1"), [])
        self.assertEqual(
            self.service.ingest(Record(REWARD.decode(), 8, 100, False), "LIVE", "g1"),
            [],
        )
        self.assertEqual(self.service.events("LIVE"), [])
        self.assertEqual(
            self.service.diagnostics("LIVE")[0]["errors"], ["incomplete_record"]
        )

    def test_tools_cannot_approve_updates(self):
        interface = ToolInterface(self.service)
        names = [name for name, schema in interface.get_tools()]
        self.assertIn("get_current_game_state", names)
        self.assertNotIn("approve_update", names)
        with self.assertRaises(ValueError):
            interface.call("approve_update", {})

    def test_trade_category_filter_applies_before_limit(self):
        buy = "<2026-09-15T12:00:00Z> ShoppingProvider SendStandardItemBuyRequest playerId[p] client_price[265] quantity[1] currencyType[UEC] itemName[Medpen]"
        done = "<2026-09-15T12:00:01Z> ShoppingProvider RmShopFlowResponse playerId[p] result[Success]"
        for i, text in enumerate([buy, done, REWARD.decode()]):
            self.service.ingest(Record(text, i * 500, (i + 1) * 500), "LIVE", "g1")
        result = ToolInterface(self.service).call(
            "get_trade_entries",
            {
                "environment": "LIVE",
                "category": "item",
                "limit": 1,
                "time_range": "all",
            },
        )
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["amount_auec"], -265.0)

    def test_closed_service_can_close_twice(self):
        self.service.close()
        self.service.close()


if __name__ == "__main__":
    unittest.main()
