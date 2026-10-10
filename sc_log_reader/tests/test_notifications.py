import copy
import tempfile
import unittest
from pathlib import Path

from sc_log_reader.notifications import NotificationPolicy
from sc_log_reader.reader import Record
from sc_log_reader.service import Service


def row(kind="restricted_area", subject="entered", env="LIVE", generation="g1"):
    return {
        "event_type": kind,
        "environment": env,
        "generation": generation,
        "data": {"action": subject, "mission_id": subject, "mission_name": subject},
        "source_occurrences": ["source-" + subject],
        "status": "observed",
    }


class NotificationTests(unittest.TestCase):
    def test_location_uses_location_not_player_from_real_kaboos_event(self):
        event = row("location_arrived")
        event["data"] = {
            "location": "Nyx_Kaboos",
            "player_name": "Mallachi",
            "location_name": "Kaboos",
        }
        p = NotificationPolicy()
        p.offer(event, now=0, catching_up=False)
        text = p.flush(now=0)[0]["text"]
        self.assertEqual(text, "Player location reported: Kaboos")

    def test_event_detail_has_a_role_and_never_falls_back_to_player(self):
        cases = [
            (
                "location_arrived",
                {"player_name": "Mallachi"},
                "Player location reported",
            ),
            (
                "location_departed",
                {"player_name": "Mallachi", "location_name": "Levski"},
                "Player departure reported from location: Levski",
            ),
            (
                "location_change",
                {"player_name": "Mallachi", "location": "NewCode"},
                "Player location code unresolved: NewCode",
            ),
            (
                "session_start",
                {"player_name": "Mallachi"},
                "Session started for player: Mallachi",
            ),
            ("user_login", {"player_name": "Mallachi"}, "Player logged in: Mallachi"),
            ("join_pu", {"player_name": "Mallachi"}, "Player joined the universe"),
            (
                "mission_accepted",
                {
                    "mission_id": "uuid",
                    "mission_name": "Delivery",
                    "player_name": "Mallachi",
                },
                "Mission accepted: Delivery",
            ),
            (
                "ship_entered",
                {"ship_name": "Prospector", "player_name": "Mallachi"},
                "Player boarded ship: Prospector",
            ),
            ("ship_entered", {"player_name": "Mallachi"}, "Player boarded ship"),
            (
                "ship_exited",
                {"ship_name": "Prospector"},
                "Player left ship: Prospector",
            ),
            (
                "injury",
                {"body_part": "left_arm", "player_name": "Mallachi"},
                "Player injury observed: left_arm",
            ),
        ]
        for kind, data, expected in cases:
            with self.subTest(kind=kind):
                event = row(kind)
                event["data"] = data
                p = NotificationPolicy()
                p.offer(event, now=0, catching_up=False)
                self.assertEqual(p.flush(now=0)[0]["text"], expected)

    def test_thousand_repeats_and_active_summary(self):
        p = NotificationPolicy()
        p.offer(row(), now=0, catching_up=False)
        self.assertEqual(len(p.flush(now=0)), 1)
        for i in range(1, 1000):
            p.offer(row(), now=i * 0.059, catching_up=False)
            self.assertEqual(p.flush(now=i * 0.059), [])
        self.assertEqual(p.stats["suppressed"], 999)
        summary = p.flush(now=60)
        self.assertEqual(len(summary), 1)
        self.assertEqual(summary[0]["repeat_count"], 999)
        self.assertEqual(p.flush(now=60), [])
        self.assertEqual(p.stats["tracked_keys"], 1)

    def test_quiet_closes_without_recovery_or_stale_summary(self):
        p = NotificationPolicy()
        p.offer(row(), now=0, catching_up=False)
        p.flush(now=0)
        p.offer(row(), now=1, catching_up=False)
        self.assertEqual(p.flush(now=31), [])
        self.assertEqual(p.stats["tracked_keys"], 0)
        p.offer(row(), now=31, catching_up=False)
        self.assertEqual(len(p.flush(now=31)), 1)

    def test_key_queue_and_environment_bounds(self):
        p = NotificationPolicy()
        for i in range(257):
            p.offer(row("mission_accepted", str(i)), now=0, catching_up=False)
        self.assertEqual(p.stats["tracked_keys"], 256)
        self.assertEqual(p.stats["pending"], 100)
        self.assertEqual(p.stats["key_evicted"], 1)
        self.assertEqual(p.stats["queue_dropped"], 157)
        self.assertEqual(p.flush(now=0)[0]["source_occurrences"], ["source-0"])
        for i in range(6):
            p.offer(row(env=str(i)), now=1, catching_up=False)
        self.assertEqual(p.stats["environments"], 5)
        self.assertGreater(p.stats["environment_evicted"], 0)

    def test_rate_bound_survives_rapid_flush_and_key_churn(self):
        p = NotificationPolicy()
        delivered = []
        for i in range(1000):
            p.offer(row("mission_accepted", str(i)), now=0, catching_up=False)
            delivered += p.flush(now=0)
        self.assertEqual(len(delivered), 3)
        self.assertEqual(p.stats["rate_dropped"], 997)
        p.offer(row("mission_complete", "fresh"), now=5, catching_up=False)
        self.assertEqual(len(p.flush(now=5)), 1)

    def test_expiry_and_catchup_reset_pending_and_repeat_context(self):
        p = NotificationPolicy()
        p.offer(row(), now=0, catching_up=False)
        self.assertEqual(p.flush(now=10), [])
        self.assertEqual(p.stats["expired"], 1)
        p.offer(row(), now=11, catching_up=False)
        p.offer(row(), now=12, catching_up=True)
        self.assertEqual(p.flush(now=60), [])
        self.assertEqual(p.stats["tracked_keys"], 0)
        p.offer(row(), now=61, catching_up=False)
        self.assertEqual(len(p.flush(now=61)), 1)

    def test_generation_boundary_clears_old_presentation(self):
        p = NotificationPolicy()
        p.offer(row(), now=0, catching_up=False)
        p.offer(row(generation="g2"), now=1, catching_up=False)
        output = p.flush(now=1)
        self.assertEqual(len(output), 1)
        self.assertEqual(output[0]["generation"], "g2")
        self.assertEqual(p.stats["context_dropped"], 1)

    def test_literal_templates_categories_unknown_money_and_input_unchanged(self):
        p = NotificationPolicy(enabled_categories={"mission", "money"})
        hostile = row(
            "mission_accepted", "$(Remove-Item *)\n<script>run</script>" * 100
        )
        before = copy.deepcopy(hostile)
        p.offer(hostile, now=0, catching_up=False)
        p.offer(row(), now=0, catching_up=False)
        p.offer(row("invented_command"), now=0, catching_up=False)
        money = row("shop_buy")
        money["status"] = "confirmed"
        p.offer(money, now=0, catching_up=False)
        output = p.flush(now=0)
        self.assertEqual(hostile, before)
        self.assertEqual(len(output), 2)
        self.assertLessEqual(len(output[0]["text"]), 512)
        self.assertNotIn("\n", output[0]["text"])
        self.assertIn("unknown", output[1]["text"])
        self.assertEqual(p.stats["disabled"], 1)
        self.assertEqual(p.stats["unknown"], 1)
        self.assertTrue(all("command" not in item for item in output))

    def test_clock_rollback_resets_and_invalid_clock_rejected(self):
        p = NotificationPolicy()
        p.offer(row(), now=20, catching_up=False)
        self.assertEqual(p.flush(now=19), [])
        self.assertEqual(p.stats["clock_resets"], 1)
        for bad in (float("nan"), float("inf"), True):
            with self.assertRaises(ValueError):
                p.flush(now=bad)

    def test_delivery_failure_is_counted_without_retry(self):
        p = NotificationPolicy()
        p.offer(row(), now=0, catching_up=False)
        message = p.flush(now=0)[0]
        p.delivery_failed(message)
        self.assertEqual(p.stats["delivery_failed"], 1)
        self.assertEqual(p.flush(now=0), [])

    def test_oscillating_clock_cannot_replenish_rate_tokens(self):
        p = NotificationPolicy()
        output = []
        for i in range(100):
            p.offer(row("mission_accepted", str(i)), now=20, catching_up=False)
            output += p.flush(now=20)
            p.flush(now=19)
        self.assertEqual(len(output), 3)

    def test_different_known_amounts_do_not_claim_same_repeat(self):
        p = NotificationPolicy()
        for amount in (500, 600):
            event = row("reward_earned")
            event["amount_auec"] = amount
            p.offer(event, now=0, catching_up=False)
        output = p.flush(now=0)
        self.assertEqual(len(output), 2)
        self.assertIn("500 aUEC", output[0]["text"])
        self.assertIn("600 aUEC", output[1]["text"])

    def test_confirmed_signed_debits_remain_known_and_unknown_remains_unknown(self):
        p = NotificationPolicy()
        for kind, amount in (
            ("shop_buy", -265.0),
            ("money_sent", -50.0),
            ("fined", -100.0),
        ):
            event = row(kind)
            event.update(status="confirmed", amount_auec=amount)
            p.offer(event, now=0, catching_up=False)
        output = p.flush(now=0)
        self.assertEqual(len(output), 3)
        for message, amount in zip(output, (-265.0, -50.0, -100.0), strict=True):
            self.assertIn(str(amount) + " aUEC", message["text"])
            self.assertNotIn("unknown", message["text"])
        for i, amount in enumerate((None, float("nan"), float("inf"), True)):
            event = row("shop_buy", str(i))
            event.update(status="confirmed", amount_auec=amount)
            p.offer(event, now=5 + i * 5, catching_up=False)
            self.assertIn("unknown", p.flush(now=5 + i * 5)[0]["text"])

    def test_committed_evidence_and_ledger_independent_of_policy_and_failure(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        service = Service(Path(tmp.name) / "runtime")
        self.addCleanup(service.close)

        def evidence():
            state = service.state("LIVE")
            state.pop("reader_health")  # Read-time age is deliberately dynamic.
            return service.events("LIVE"), service.ledger("LIVE"), state

        lines = [
            "<2026-09-15T12:00:00Z> User Login Success Handle[Mallachi]",
            '<2026-09-15T12:00:01Z> <SHUDEvent> Added notification "Contract Accepted: Delivery:" [13] to queue. MissionId: [m1]',
            '<2026-09-15T12:00:02Z> <SHUDEvent> Added notification "Awarded 500 aUEC:" [14] to queue.',
        ]
        rows = []
        for i, line in enumerate(lines):
            rows += service.ingest(
                Record(line, i * 1000, i * 1000 + len(line)),
                "LIVE",
                "source-generation",
            )
        before = evidence()
        self.assertTrue(rows)
        self.assertTrue(all(r["generation"] == "source-generation" for r in rows))
        for categories in (set(), {"session", "mission", "money"}):
            p = NotificationPolicy(enabled_categories=categories)
            for r in rows * 10:
                p.offer(r, now=0, catching_up=False)
            for message in p.flush(now=0):
                p.delivery_failed(message)
            self.assertEqual(before, evidence())

    def test_exact_pending_cap_and_reference_bounds(self):
        p = NotificationPolicy()
        for i in range(101):
            p.offer(row("mission_accepted", str(i)), now=0, catching_up=False)
        self.assertEqual(p.stats["pending"], 100)
        self.assertEqual(p.stats["queue_dropped"], 1)
        p = NotificationPolicy()
        for i in range(100):
            event = row()
            event["source_occurrences"] = [str(i) + "x" * 1000]
            p.offer(event, now=i * 0.5, catching_up=False)
            p.flush(now=i * 0.5)
        summary = p.flush(now=60)[0]
        self.assertEqual(summary["repeat_count"], 99)
        self.assertLessEqual(len(summary["source_occurrences"]), 8)
        self.assertTrue(
            any(ref.startswith("99x") for ref in summary["source_occurrences"])
        )
        self.assertTrue(all(len(ref) <= 128 for ref in summary["source_occurrences"]))

    def test_catchup_clears_only_affected_environment(self):
        p = NotificationPolicy()
        p.offer(row(), now=0, catching_up=False)
        p.offer(row(env="PTU"), now=0, catching_up=False)
        p.offer(row(), now=0, catching_up=True)
        output = p.flush(now=0)
        self.assertEqual([item["environment"] for item in output], ["PTU"])
        self.assertEqual(p.stats["context_dropped"], 1)

    def test_invalid_configuration_and_envelopes_are_bounded(self):
        for options in (
            {"max_keys": 257},
            {"max_pending": 101},
            {"max_environments": 6},
            {"delivery_burst": 4},
            {"quiet_interval": 0},
            {"queue_expiry": float("nan")},
            {"enabled_categories": {"invented"}},
        ):
            with self.assertRaises(ValueError):
                NotificationPolicy(**options)
        p = NotificationPolicy()
        for event in (None, {}, row(generation="x" * 129)):
            p.offer(event, now=0, catching_up=False)
        self.assertEqual(p.stats["invalid"], 3)
        self.assertEqual(p.stats["pending"], 0)


if __name__ == "__main__":
    unittest.main()
