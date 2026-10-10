import json
import tempfile
import unittest
from datetime import UTC, datetime, timedelta
from pathlib import Path

from sc_log_reader.reader import Event, Instructions, Reader, Record, bundled_bytes
from sc_log_reader.service import Service, ToolInterface
from sc_log_reader.state import State

T = datetime(2026, 9, 16, 12, tzinfo=UTC)


class ImprovementTests(unittest.TestCase):
    def setUp(self):
        self.instructions = Instructions.load(bundled_bytes())
        self.state = State(self.instructions.data["lookups"])
        self.n = 0
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)

    def send(self, kind, fields=None, seconds=0):
        self.n += 1
        return self.state.apply(
            Event(
                kind,
                fields or {},
                T + timedelta(seconds=seconds),
                instruction_version="test-definitions",
            ),
            str(self.n),
            "g",
        )

    def service(self):
        s = Service(Path(self.tmp.name) / "runtime")
        self.addCleanup(s.close)
        return s

    def test_health_observation_does_not_become_current_through_unrelated_event(self):
        self.send("bleeding")
        self.send("incapacitated", seconds=1)
        self.send("attachment_received", {"item_name": "Medpen"}, 100)
        p = self.state.public()
        self.assertIsNone(p["bleeding"])
        self.assertIsNone(p["incapacitated"])
        self.assertEqual(p["observations"]["bleeding"]["value"], True)
        self.assertEqual(p["observations"]["bleeding"]["timestamp"], T.isoformat())
        self.assertEqual(p["observations"]["bleeding"]["certainty"], "last_observed")
        self.assertEqual(
            p["observations"]["bleeding"]["instruction_version"], "test-definitions"
        )

    def test_changed_shard_invalidates_world_claims_and_preserves_last_known_location(
        self,
    ):
        self.send("user_login", {"player_name": "A"})
        self.send("join_pu", {"shard": "one"})
        self.send(
            "location_change", {"player_name": "A", "location": "Stanton4_NewBabbage"}
        )
        self.send(
            "channel_change", {"action": "joined", "ship_name": "Titan", "owner": "A"}
        )
        self.send("armistice_zone", {"action": "entered"})
        self.send("bleeding")
        self.send("join_pu", {"shard": "two"}, 10)
        p = self.state.public()
        for key in ("ship", "aboard_ship", "armistice", "bleeding", "location_name"):
            self.assertIsNone(p[key], key)
        self.assertEqual(p["location_status"], "unknown")
        self.assertEqual(p["last_known_location"]["name"], "New Babbage")
        self.assertEqual(p["observations"]["armistice"]["certainty"], "invalidated")

    def test_ambiguous_trade_cannot_become_money_when_older_request_expires(self):
        common = dict(
            player_id="p",
            source_provider="shop",
            shop_id="s",
            kiosk_id="k",
            quantity=1,
            currency_type="UEC",
        )
        self.send("shop_buy", dict(common, price=10), 0)
        self.send("shop_buy", dict(common, price=20), 10)
        response = dict(
            player_id="p",
            source_provider="shop",
            shop_id="s",
            kiosk_id="k",
            result="Success",
        )
        self.assertEqual(
            self.send("shop_transaction_result", response, 11)[0]["status"], "ambiguous"
        )
        rows = self.send("shop_transaction_result", response, 121)
        self.assertFalse(
            any(r.get("status") == "confirmed" or "amount_auec" in r for r in rows)
        )

    def test_expired_inventory_candidate_does_not_block_new_location_guid(self):
        self.send("user_login", {"player_name": "A"})
        self.send(
            "inventory_location_update",
            {"player_name": "A", "loc_from": "0", "loc_to": "111"},
        )
        self.send(
            "location_change",
            {"player_name": "A", "location": "Stanton4_NewBabbage"},
            1,
        )
        self.send(
            "location_change", {"player_name": "A", "location": "RR_CRU_LEO"}, 100
        )
        self.send(
            "personal_inventory_data", {"player_name": "A", "location_guid": "222"}, 101
        )
        self.assertEqual(self.state.data["location_guid"], "222")
        rows = self.send(
            "inventory_location_update",
            {"player_name": "A", "loc_from": "222", "loc_to": "333"},
            102,
        )
        self.assertEqual(rows[0]["event_type"], "location_departed")

    def test_orphan_objective_is_retained_without_inventing_a_mission(self):
        self.send("objective_new", {"mission_id": "m1", "objective": "Carry box"})
        p = self.state.public()
        self.assertEqual(p["active_missions"], {})
        self.assertEqual(p["mission_reconstruction"]["status"], "partial")
        self.assertEqual(
            p["mission_reconstruction"]["orphan_objectives"][0]["objective"],
            "Carry box",
        )

    def test_contract_withdrawal_removes_only_matching_mission_without_failure_or_reward(
        self,
    ):
        for mid in ("m1", "m2"):
            self.send("contract_accepted", {"mission_id": mid, "mission_name": mid})
        rows = self.send(
            "contract_withdrawn", {"mission_id": "m1", "mission_name": "m1"}
        )
        self.assertEqual(set(self.state.data["active_missions"]), {"m2"})
        self.assertEqual(rows[0]["event_type"], "mission_withdrawn")
        self.assertNotIn("amount_auec", rows[0])
        self.assertEqual(self.state.data["_recent_completions"], [])

    def test_observed_notification_variants_parse(self):
        reader = Reader(self.instructions)
        for kind, label in [
            ("refinery_complete", "A Refinery Work Order has been Completed at Levski"),
            ("emergency_services", "Standby, Local Emergency Services Are En Route"),
            ("contract_withdrawn", "Contract Withdrawn: Delivery:"),
        ]:
            with self.subTest(kind=kind):
                e = reader.parse(
                    f'<2026-09-16T12:00:00Z> <SHUDEvent> Added notification "{label}" [1] to queue. MissionId: [m1]'
                )
                self.assertIsNotNone(e)
                self.assertEqual(e.event_type, kind)
                self.assertEqual(e.errors, [])

    def test_state_and_missions_include_reader_freshness(self):
        s = self.service()
        s.worker_errors["monitor"] = {"error": "paused"}
        state = ToolInterface(s).call("get_current_game_state", {})
        self.assertIn("monitor", state["reader_health"]["worker_errors"])
        missions = ToolInterface(s).call("get_active_missions", {})
        self.assertEqual(missions["missions"], [])
        self.assertEqual(missions["reconstruction"]["status"], "partial")
        self.assertIn("monitor", missions["reader_health"]["worker_errors"])

    def test_legacy_event_filters_include_unresolved_and_attached_outputs(self):
        s = self.service()

        def ingest(kind, fields, n):
            s.reader.parse = lambda *a, **kw: Event(kind, fields, T)
            s.ingest(Record(str(n), n, n + 1), "LIVE", "g")

        ingest("user_login", {"player_name": "A"}, 1)
        ingest("location_change", {"player_name": "A", "location": "UNKNOWN"}, 2)
        ingest("location_change", {"player_name": "A", "location": "RR_CRU_LEO"}, 3)
        rows = ToolInterface(s).call(
            "get_recent_game_events", {"event_type": "location_change"}
        )
        self.assertEqual(
            {r["event_type"] for r in rows}, {"location_arrived", "location_change"}
        )
        ingest("objective_new", {"mission_id": "m", "objective": "Box"}, 4)
        rows = ToolInterface(s).call(
            "get_recent_game_events", {"event_type": "objective_new"}
        )
        self.assertEqual(rows[0]["event_type"], "objective_new")

    def test_unknown_notification_samples_are_bounded_local_and_survive_restart(self):
        s = self.service()
        for n in range(110):
            text = f'<SHUDEvent> Added notification "Novel game message {n}" [{n}] to queue.'
            s.ingest(Record(text, n * 100, n * 100 + 99), "LIVE", "g")
        s.close()
        s = self.service()
        samples = s.health("LIVE")["unrecognized_samples"]
        self.assertGreater(len(samples), 0)
        self.assertLessEqual(len(samples), 100)
        self.assertIn("Novel game message", samples[0]["sample"])
        self.assertEqual(samples[0]["instruction_version"], self.instructions.version)
        self.assertIsNone(samples[0]["rule_id"])
        self.assertLessEqual(len(samples[0]["sample"]), 2048)

    def test_error_diagnostics_identify_rule_and_definition_version(self):
        s = self.service()
        s.reader.parse = lambda *a, **kw: Event(
            "shop_buy", {}, T, ["missing:price"], "shop_buy.v1", "broken-definitions"
        )
        s.ingest(Record("bad", 0, 3), "LIVE", "g")
        d = s.diagnostics("LIVE")[0]
        self.assertEqual(d["rule_id"], "shop_buy.v1")
        self.assertEqual(d["instruction_version"], "broken-definitions")

    def test_engine_two_definitions_remain_usable_for_rollback(self):
        data = json.loads(bundled_bytes())
        data["engine_version"] = 2
        data["minimum_reader_version"] = "0.2.0"
        data["rules"] = [r for r in data["rules"] if r["event"] != "contract_withdrawn"]
        old = Instructions.load(json.dumps(data).encode())
        self.assertEqual(
            Reader(old).parse("User Login Success Handle[A]").fields["player_name"], "A"
        )

    def test_old_snapshot_has_unknown_provenance_not_current_health(self):
        old = {
            "bleeding": True,
            "ship": "Titan",
            "generation": "g",
            "location_name": "New Babbage",
        }
        restored = State(self.instructions.data["lookups"], old).public()
        self.assertIsNone(restored["bleeding"])
        evidence = restored["observations"]["bleeding"]
        self.assertEqual(evidence["value"], True)
        self.assertIsNone(evidence["timestamp"])
        self.assertEqual(evidence["certainty"], "unknown_time")
        self.assertIsNone(evidence["instruction_version"])

    def test_definition_change_invalidates_claims_without_rebooking_history(self):
        s = self.service()
        s.reader.parse = lambda *a, **kw: Event(
            "armistice_zone", {"action": "entered"}, T
        )
        s.ingest(Record("zone", 0, 4), "LIVE", "g")
        s.close()
        data = json.loads(bundled_bytes())
        data["revision"] += 1
        new = Service(
            Path(self.tmp.name) / "runtime",
            instructions=Instructions.load(json.dumps(data).encode()),
        )
        self.addCleanup(new.close)
        p = new.state("LIVE")
        self.assertIsNone(p["armistice"])
        self.assertEqual(
            p["observations"]["armistice"]["reason"], "instructions_changed"
        )
        self.assertEqual(len(new.events("LIVE")), 1)

    def test_deliberately_ignored_records_are_not_counted_as_unknown(self):
        s = self.service()
        s.ingest(Record("UpdateNotificationItem dummy", 0, 28), "LIVE", "g")
        h = s.health("LIVE")
        self.assertEqual(h["counts"]["ignored"], 1)
        self.assertEqual(h["counts"]["unrecognized"], 0)
        self.assertEqual(h["unrecognized_samples"], [])

    def test_repeated_observations_refresh_only_the_relevant_evidence(self):
        self.send("user_login", {"player_name": "A"})
        for second in (1, 10):
            self.send(
                "location_change",
                {"player_name": "A", "location": "RR_CRU_LEO"},
                second,
            )
            self.send(
                "channel_change",
                {"action": "joined", "ship_name": "Titan", "owner": "A"},
                second,
            )
            self.send("entered_monitored_space", seconds=second)
        p = self.state.public()
        for field in ("location_name", "ship", "monitored"):
            self.assertEqual(
                p["observations"][field]["timestamp"],
                (T + timedelta(seconds=10)).isoformat(),
                field,
            )
        self.assertEqual(p["observations"]["player_name"]["timestamp"], T.isoformat())

    def test_session_reset_does_not_invent_recovery_evidence_or_lose_login_evidence(
        self,
    ):
        self.send("user_login", {"player_name": "A"})
        self.send("injury", {"body_part": "head", "severity": "Minor"})
        self.send("user_login", {"player_name": "A"}, 10)
        p = self.state.public()
        self.assertEqual(
            p["observations"]["player_name"]["timestamp"],
            (T + timedelta(seconds=10)).isoformat(),
        )
        self.assertNotIn("injuries", p["observations"])

    def test_observed_archive_notifications_keep_their_exact_payload(self):
        fixtures = json.loads(
            (Path(__file__).parent / "fixtures/review_notifications.json").read_text()
        )
        reader = Reader(self.instructions)
        for fixture in fixtures:
            event = reader.parse(fixture["text"])
            self.assertEqual(event.event_type, fixture["event_type"])
            self.assertEqual(event.errors, [])
            if event.event_type == "contract_withdrawn":
                self.assertEqual(event.fields["mission_name"], "A Call to Arms")
                self.assertEqual(
                    event.fields["mission_id"], "06484da0-92e1-4f7c-9d5f-bd491b9fe326"
                )

    def test_repeated_accepted_inventory_guid_refreshes_evidence(self):
        self.send("user_login", {"player_name": "A"})
        self.send("location_change", {"player_name": "A", "location": "RR_CRU_LEO"})
        for second in (1, 2):
            self.send(
                "personal_inventory_data",
                {"player_name": "A", "location_guid": "123"},
                second,
            )
        self.assertEqual(
            self.state.public()["observations"]["location_guid"]["timestamp"],
            (T + timedelta(seconds=2)).isoformat(),
        )
