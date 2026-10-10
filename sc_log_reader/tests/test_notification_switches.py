import re
import tempfile
import unittest
from pathlib import Path

from sc_log_reader import notifications as n


def event(kind, action="entered"):
    return {
        "event_type": kind, "environment": "LIVE", "generation": "test",
        "data": {"action": action}, "status": "observed",
        "source_occurrences": [],
    }


class NotificationSwitchTests(unittest.TestCase):
    def test_settings_panel_exposes_every_supported_switch_once(self):
        root = Path(__file__).resolve().parents[1]
        text = (root / "integrations/wingman_target/default_config.yaml").read_text()
        ids = re.findall(r"\bid:\s*(notify_\w+)", text)
        self.assertCountEqual(ids, ["notify_game_events", *n.NOTIFICATION_OPTIONS,
                                   *("notify_" + category for category in n._CATEGORIES)])

    def test_disabling_injury_announcements_keeps_recorded_injury_state(self):
        from sc_log_reader.reader import Record
        from sc_log_reader.service import Service

        with tempfile.TemporaryDirectory() as tmp:
            service = Service(Path(tmp) / "runtime")
            try:
                line = ('<2026-09-26T11:29:09Z> <SHUDEvent> Added notification '
                        '"Minor Injury Detected - Torso - Tier 3 Treatment Required : " [13] to queue.')
                rows = service.ingest(Record(line, 0, len(line)), "LIVE", "test")
                self.assertEqual([r["event_type"] for r in rows], ["injury"])
                self.assertEqual(self.messages({"notify_injury": False}, rows), [])
                self.assertEqual(service.state("LIVE")["injuries"]["torso"]["tier"], 3)
                self.assertEqual(service.events("LIVE")[0]["event_type"], "injury")
            finally:
                service.close()

    def messages(self, settings, rows):
        policy = n.NotificationPolicy(enabled_events=n.enabled_notification_events(settings))
        result = []
        for index, row in enumerate(rows):
            policy.offer(row, now=index * 40, catching_up=False)
            result.extend(policy.flush(now=index * 40))
        return result

    def test_armistice_switch_controls_both_directions_without_muting_health(self):
        rows = [event("armistice_zone", "entered"), event("armistice_zone", "exited"),
                event("injury"), event("restricted_area")]
        self.assertEqual(len(self.messages({}, rows)), 4)
        texts = [m["text"] for m in self.messages({"notify_armistice_zone": False}, rows)]
        self.assertEqual(texts, ["Player injury observed", "Player restricted-area status reported: entered"])

    def test_mission_types_are_independent(self):
        messages = self.messages({"notify_mission_accepted": False},
                                 [event("mission_accepted"), event("mission_complete")])
        self.assertEqual([m["text"] for m in messages], ["Mission complete observed"])

    def test_paired_ship_changes_share_a_switch(self):
        self.assertEqual(self.messages({"notify_ship_boarding": False},
                         [event("ship_entered"), event("ship_exited")]), [])

    def test_previously_omitted_types_can_be_enabled_and_disabled(self):
        for kind in ("hangar_ready", "quantum_route_set", "bleeding", "incapacitated",
                     "jurisdiction_change", "contract_shared", "fuel_low", "insurance_claim"):
            with self.subTest(kind=kind):
                self.assertEqual(len(self.messages({}, [event(kind)])), 1)
                self.assertEqual(self.messages({"notify_" + kind: False}, [event(kind)]), [])

    def test_all_announcable_events_have_exactly_one_working_switch(self):
        mapped = []
        for option, kinds in n.NOTIFICATION_OPTIONS.items():
            mapped.extend(kinds)
            enabled = n.enabled_notification_events({option: False})
            self.assertEqual(set(n._TEMPLATES) - set(enabled), set(kinds), option)
        self.assertCountEqual(mapped, n._TEMPLATES)

    def test_saved_category_master_stays_off_even_with_new_individual_defaults(self):
        settings = {"notify_health": False, "notify_injury": True}
        self.assertEqual(self.messages(settings, [event("injury")]), [])
        self.assertEqual(self.messages(settings, [event("med_bed_heal")]), [])
        settings.update(notify_health=True, notify_med_bed_heal=False)
        self.assertEqual(len(self.messages(settings, [event("injury")])), 1)
        self.assertEqual(self.messages(settings, [event("med_bed_heal")]), [])

    def test_old_direction_switches_are_respected_when_combined_switch_missing(self):
        self.assertEqual(self.messages({"notify_zone_left_armistice": False},
                         [event("armistice_zone", "entered"), event("armistice_zone", "exited")]), [])
        self.assertEqual(len(self.messages({"notify_zone_left_armistice": False,
                                          "notify_armistice_zone": True}, [event("armistice_zone")])), 1)

    def test_raw_inventory_and_channels_remain_silent(self):
        self.assertEqual(self.messages({}, [event("attachment_received"), event("channel_change"),
                                           event("personal_inventory_data")]), [])

    def test_restored_types_keep_distinct_subjects_separate(self):
        policy = n.NotificationPolicy()
        for index, jurisdiction in enumerate(("Ungoverned", "People's Alliance")):
            row = event("jurisdiction_change")
            row["data"] = {"jurisdiction": jurisdiction}
            policy.offer(row, now=index * 5, catching_up=False)
            messages = policy.flush(now=index * 5)
            self.assertEqual([m["text"] for m in messages], ["Jurisdiction reported: " + jurisdiction])

    def test_restored_request_and_result_wording_does_not_claim_success(self):
        messages = self.messages({}, [event("cargo_transfer"), event("insurance_claim"),
                                      event("insurance_claim_complete")])
        self.assertEqual([m["text"] for m in messages], ["Cargo transfer requested",
                         "Insurance claim requested", "Insurance claim result observed"])

    def test_unknown_event_filter_is_rejected(self):
        with self.assertRaises(ValueError):
            n.NotificationPolicy(enabled_events={"invented"})


if __name__ == "__main__":
    unittest.main()
