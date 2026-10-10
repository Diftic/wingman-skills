import unittest
from datetime import UTC, datetime, timedelta

from sc_log_reader.reader import Event, Instructions, bundled_bytes
from sc_log_reader.state import State

T = datetime(2026, 9, 15, 12, tzinfo=UTC)


class StateTests(unittest.TestCase):
    def setUp(self):
        self.state = State(Instructions.load(bundled_bytes()).data["lookups"])
        self.n = 0

    def send(
        self, kind, data=None, seconds=0, errors=None, occurrence=None, generation="g1"
    ):
        self.n += 1
        return self.state.apply(
            Event(kind, data or {}, T + timedelta(seconds=seconds), errors or []),
            occurrence or str(self.n),
            generation,
        )

    def test_mission_lifecycle_and_incomplete_data(self):
        self.send("contract_accepted", {"mission_id": "m1", "mission_name": "Delivery"})
        self.send("objective_new", {"mission_id": "m1", "objective": "Pickup"})
        self.assertEqual(
            self.state.data["active_missions"]["m1"]["objective"], "Pickup"
        )
        self.send(
            "contract_failed", {"mission_id": "m1"}, errors=["missing:mission_name"]
        )
        self.assertIn("m1", self.state.data["active_missions"])
        self.send("contract_complete", {"mission_id": "m1", "mission_name": "Delivery"})
        self.assertNotIn("m1", self.state.data["active_missions"])

    def test_json_cannot_relax_fixed_state_requirements(self):
        self.send("contract_accepted", {"mission_id": "m1"})
        self.assertEqual(self.state.data["active_missions"], {})

    def test_zero_mission_id_is_not_identity(self):
        self.send(
            "contract_accepted",
            {
                "mission_id": "00000000-0000-0000-0000-000000000000",
                "mission_name": "Unknown",
            },
        )
        self.assertFalse(self.state.data["active_missions"])

    def test_heal_only_clears_explicitly_healed_body_parts(self):
        self.send("injury", {"body_part": "Left Arm", "severity": "Minor", "tier": 1})
        self.send("injury", {"body_part": "Right Leg", "severity": "Major", "tier": 2})
        self.send(
            "med_bed_heal", {"healed_parts": {"leftArm": True, "rightLeg": False}}
        )
        self.assertNotIn("leftArm", self.state.data["injuries"])
        self.assertIn("rightLeg", self.state.data["injuries"])

    def test_confirmed_inventory_guid_drives_one_departure(self):
        self.send("user_login", {"player_name": "Mallachi"})
        self.send(
            "inventory_location_update",
            {"player_name": "Mallachi", "loc_from": "0", "loc_to": "3170699229"},
            1,
        )
        self.send(
            "location_change",
            {"player_name": "Mallachi", "location": "Stanton4_NewBabbage"},
            20,
        )
        self.send(
            "personal_inventory_data",
            {"player_name": "Mallachi", "location_guid": "3170699229"},
            21,
        )
        output = self.send(
            "inventory_location_update",
            {"player_name": "Mallachi", "loc_from": "3170699229", "loc_to": "99"},
            100,
        )
        self.assertIn("location_departed", [e["event_type"] for e in output])
        self.assertEqual(self.state.data["location_status"], "departed")
        output = self.send(
            "inventory_location_update",
            {
                "player_name": "Mallachi",
                "loc_from": "99",
                "loc_to": "100",
                "landing_from": "3170699229",
            },
            101,
        )
        self.assertNotIn("location_departed", [e["event_type"] for e in output])

    def test_other_player_location_does_not_change_ours(self):
        self.send("user_login", {"player_name": "Mallachi"})
        self.send("location_change", {"player_name": "Other", "location": "RR_CRU_LEO"})
        self.assertIsNone(self.state.data["location_name"])

    def test_ship_class_does_not_prove_ownership(self):
        self.send("user_login", {"player_name": "Mallachi"})
        self.send(
            "channel_change",
            {
                "action": "joined",
                "ship_name": "AEGS Avenger Titan",
                "ship_class": "AEGS_Avenger_Titan",
                "owner": "Mallachi",
            },
        )
        self.assertTrue(self.state.data["own_ship"])
        output = self.send("qt_arrived", {"entity_class": "AEGS_Avenger_Titan"})
        self.assertEqual(output[0]["attribution"], "possible_player_ship")
        self.assertFalse(self.send("qt_arrived", {"entity_class": "MISC_Prospector"}))
        self.assertFalse(self.send("qt_arrived", {}))

    def test_shop_request_is_not_money_until_unique_confirmation(self):
        request = {
            "player_id": "p1",
            "shop_id": "s1",
            "kiosk_id": "k1",
            "source_provider": "shopping",
            "item_name": "Medpen",
            "price": 265.0,
            "quantity": 1,
            "currency_type": "UEC",
        }
        output = self.send("shop_buy", request)
        self.assertFalse(any(e.get("amount_auec") is not None for e in output))
        output = self.send(
            "shop_transaction_result",
            {
                "player_id": "p1",
                "shop_id": "s1",
                "kiosk_id": "k1",
                "source_provider": "shopping",
                "result": "Success",
            },
            1,
        )
        self.assertEqual(output[0]["amount_auec"], -265.0)
        self.assertEqual(output[0]["source_occurrences"], ["1", "2"])

    def test_two_pending_requests_make_partial_confirmation_ambiguous(self):
        for item in ("A", "B"):
            self.send(
                "shop_buy",
                {
                    "player_id": "p1",
                    "source_provider": "shopping",
                    "item_name": item,
                    "price": 10.0,
                    "quantity": 1,
                    "currency_type": "UEC",
                },
            )
        output = self.send(
            "shop_transaction_result",
            {"player_id": "p1", "source_provider": "shopping", "result": "Success"},
            1,
        )
        self.assertFalse(any(e.get("amount_auec") is not None for e in output))

    def test_missing_currency_and_negative_price_do_not_book_money(self):
        for fields in ({"price": 10.0}, {"price": -1.0, "currency_type": "UEC"}):
            self.send(
                "shop_buy",
                {
                    "player_id": "p1",
                    "source_provider": "shopping",
                    "item_name": "A",
                    "quantity": 1,
                    **fields,
                },
            )
            output = self.send(
                "shop_transaction_result",
                {"player_id": "p1", "source_provider": "shopping", "result": "Success"},
                1,
            )
            self.assertFalse(any(e.get("amount_auec") is not None for e in output))

    def test_late_confirmation_and_new_session_cannot_confirm_old_request(self):
        self.send(
            "shop_buy",
            {
                "player_id": "p1",
                "source_provider": "shopping",
                "price": 10.0,
                "quantity": 1,
                "currency_type": "UEC",
            },
        )
        output = self.send(
            "shop_transaction_result",
            {"player_id": "p1", "source_provider": "shopping", "result": "Success"},
            121,
        )
        self.assertFalse(any(e.get("amount_auec") is not None for e in output))
        self.send("contract_accepted", {"mission_id": "m1", "mission_name": "A"})
        self.send(
            "session_start",
            {"player_geid": "same", "player_name": "Mallachi"},
            generation="g2",
        )
        self.assertFalse(self.state.data["active_missions"])

    def test_rewards_are_exclusive_and_occurrence_deduplicated(self):
        self.assertIsNone(
            self.send("reward_earned", {"quantity": "30", "item_name": "rewards"})[
                0
            ].get("amount_auec")
        )
        self.assertIsNone(
            self.send("reward_earned", {"unresolved_number": "15000"})[0].get(
                "amount_auec"
            )
        )
        output = self.send(
            "reward_earned", {"amount": "500", "currency": "aUEC"}, occurrence="money"
        )
        self.assertEqual(output[0]["amount_auec"], 500.0)
        self.assertEqual(
            self.send(
                "reward_earned",
                {"amount": "500", "currency": "aUEC"},
                occurrence="money",
            ),
            [],
        )
        self.assertIsNone(
            self.send(
                "reward_earned",
                {"amount": "500", "currency": "aUEC", "item_name": "rewards"},
            )[0].get("amount_auec")
        )

    def test_cargo_and_commodity_requests_remain_requests(self):
        for kind, data in [
            ("cargo_transfer", {"request_id": 1}),
            (
                "commodity_buy",
                {"price": 5, "quantity_cscu": 100, "quantity_unit": "cSCU"},
            ),
        ]:
            e = self.send(kind, data)[0]
            self.assertEqual(e["status"], "requested")
            self.assertIsNone(e.get("amount_auec"))


if __name__ == "__main__":
    unittest.main()
