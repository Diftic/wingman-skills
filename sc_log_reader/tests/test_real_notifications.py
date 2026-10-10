import unittest
from pathlib import Path

from sc_log_reader.reader import (
    Event,
    Instructions,
    Reader,
    RecordAssembler,
    bundled_bytes,
)
from sc_log_reader.state import State

FIXTURES = Path(__file__).parent / "fixtures/real_notifications"


class RealNotificationTests(unittest.TestCase):
    def setUp(self):
        self.instructions = Instructions.load(bundled_bytes())
        self.reader = Reader(self.instructions)
        self.state = State(self.instructions.data["lookups"])
        self.state.apply(Event("user_login", {"player_name": "Mallachi"}), "login", "g")

    def assembled(self, name, chunk=4093):
        raw = (FIXTURES / (name + ".log")).read_bytes()
        a = RecordAssembler(self.instructions)
        records = []
        for offset in range(0, len(raw), chunk):
            records += a.feed(raw[offset : offset + chunk])
        records += a.finish()
        self.assertEqual(len(records), 1)
        self.assertTrue(records[0].complete)
        self.assertEqual((records[0].start, records[0].end), (0, len(raw)))
        event = self.reader.parse(records[0].text, complete=records[0].complete)
        self.assertEqual(event.errors, [])
        return event

    def channel(self, action, label):
        return self.reader.parse(
            f"""<SHUDEvent> Added notification "You {action} channel '{label}'.: " [2] to queue."""
        )

    def test_timestamped_objective_clears_existing_objective(self):
        mid = "e85af2b6-c138-4592-aaac-d3c9f2d90af4"
        self.state.apply(
            Event(
                "contract_accepted",
                {
                    "mission_id": mid,
                    "mission_name": "Retrieve Additional Smuggler Intel",
                },
            ),
            "accept",
            "g",
        )
        self.state.apply(
            Event("objective_new", {"mission_id": mid, "objective": "Go to Location"}),
            "objective",
            "g",
        )
        event = self.assembled("objective")
        self.assertEqual(event.fields["mission_id"], mid)
        rows = self.state.apply(event, "complete", "g")
        self.assertEqual(rows[0]["event_type"], "objective_complete")
        self.assertIsNone(self.state.public()["active_missions"][mid]["objective"])

    def test_timestamped_reward_is_preserved_without_becoming_money(self):
        rows = self.state.apply(self.assembled("reward"), "reward", "g")
        self.assertEqual(rows[0]["event_type"], "reward_earned")
        self.assertEqual(rows[0]["data"]["quantity"], "30")
        self.assertIsNone(rows[0].get("amount_auec"))

    def test_original_channels_survive_byte_by_byte_input(self):
        for name, expected in [
            ("channel", "Anvil C8R Pisces Rescue : Mallachi"),
            ("apostrophe", "Grey's Basher : Mallachi"),
        ]:
            with self.subTest(name=name):
                self.assertEqual(
                    self.assembled(name, 1).fields["channel_raw"], expected
                )

    def test_millisecond_continuations_preserve_channel_and_reward(self):
        channel = self.assembled("millisecond_channel", 1)
        self.assertEqual(
            channel.fields["channel_raw"], "Anvil C8R Pisces Rescue : Mallachi"
        )
        reward = self.assembled("millisecond_reward", 1)
        self.assertEqual(reward.fields["quantity"], "30")

    def test_singular_item_reward_continuation(self):
        event = self.assembled("singular_reward", 1)
        self.assertEqual(event.fields["item_name"], "People's Alliance Hat")
        self.assertIsNone(event.fields.get("amount"))

    def test_apostrophe_capture_without_framing(self):
        event = self.reader.parse(
            """<SHUDEvent> Added notification "You have joined channel 'Grey's Basher : Mallachi'.: " [2] to queue."""
        )
        self.assertEqual(event.fields["channel_raw"], "Grey's Basher : Mallachi")

    def test_display_names_establish_ship_without_inventing_entity_class(self):
        for model in [
            "Anvil C8R Pisces Rescue",
            "Mirai Pulse",
            "C.O. Mustang Alpha",
            "Grey's Basher",
            "Argo MOLE Teach's Special",
        ]:
            with self.subTest(model=model):
                rows = self.state.apply(
                    self.channel("joined", model + " : Mallachi"),
                    model,
                    "g",
                )
                self.assertEqual(
                    rows[0]["event_type"] if rows else None, "ship_entered"
                )
                self.assertEqual(self.state.public()["ship"], model)
                self.assertTrue(self.state.public()["own_ship"])
                self.assertIsNone(self.state.public()["ship_class"])
                self.assertFalse(
                    self.state.apply(
                        Event("qt_arrived", {"entity_class": "ANVL_C8R_Pisces"}),
                        model + "-qt",
                        "g",
                    )
                )

    def test_other_owners_exit_cannot_clear_current_ship(self):
        self.state.apply(
            self.channel("joined", "@vehicle_NameAEGS_Avenger_Titan : Mallachi"),
            "join",
            "g",
        )
        rows = self.state.apply(
            self.channel("left", "@vehicle_NameAEGS_Avenger_Titan : Other"),
            "leave",
            "g",
        )
        self.assertEqual(rows, [])
        self.assertTrue(self.state.public()["aboard_ship"])

    def test_display_name_exit_clears_only_matching_ship(self):
        self.state.apply(
            self.channel("joined", "Anvil Asgard : Other"),
            "join",
            "g",
        )
        self.assertFalse(self.state.public()["own_ship"])
        rows = self.state.apply(
            self.channel("left", "Anvil Asgard : Other"),
            "leave",
            "g",
        )
        self.assertEqual(rows[0]["event_type"] if rows else None, "ship_exited")
        self.assertFalse(self.state.public()["aboard_ship"])

    def test_general_channels_and_manufacturer_substrings_are_not_ships(self):
        for name in [
            "Global Chat",
            "Party : Mallachi",
            "AnvilFans : Mallachi",
            "Anvil : Mallachi",
        ]:
            with self.subTest(name=name):
                self.assertEqual(
                    self.state.apply(
                        self.channel("joined", name),
                        name,
                        "g",
                    ),
                    [],
                )
                self.assertFalse(self.state.public()["aboard_ship"])

    def test_same_timestamp_new_record_is_not_swallowed(self):
        a = RecordAssembler(self.instructions)
        raw = (FIXTURES / "objective.log").read_bytes().splitlines()[0] + b"\n"
        self.assertEqual(a.feed(raw), [])
        rows = a.feed(b"<2026-07-16T16:46:04.931Z> User Login Success Handle[Other]\n")
        self.assertEqual(len(rows), 2)
        self.assertFalse(rows[0].complete)
        self.assertEqual(self.reader.parse(rows[1].text).fields["player_name"], "Other")

    def test_different_timestamp_metadata_does_not_complete_old_record(self):
        raw = (FIXTURES / "objective.log").read_bytes()
        first, rest = raw.split(b"\n", 1)
        a = RecordAssembler(self.instructions)
        rows = (
            a.feed(first + b"\n" + rest.replace(b"16:46:04.931", b"16:46:05.931"))
            + a.finish()
        )
        self.assertEqual(len(rows), 2)
        self.assertFalse(rows[0].complete)


if __name__ == "__main__":
    unittest.main()
