"""Hand-authored synthetic fixtures; these do not qualify a retail game build."""

import copy
import json
import re
import tempfile
import unittest
from pathlib import Path

from sc_log_reader.reader import Instructions, Reader, Record, bundled_bytes
from sc_log_reader.service import Service, ToolInterface

NOTIFICATIONS = [
    ("armistice_zone", "Entering Armistice Zone"),
    ("bleeding", "Bleeding"),
    ("blueprint_received", "Received Blueprint: Citadel Core Base:"),
    (
        "channel_change",
        "You joined channel '@vehicle_NameAEGS_Avenger_Titan : Mallachi'",
    ),
    ("contract_accepted", "Contract Accepted: Delivery:"),
    ("contract_available", "Contract Available: Delivery:"),
    ("contract_complete", "Contract Complete: Delivery:"),
    ("contract_failed", "Contract Failed: Delivery:"),
    ("contract_withdrawn", "Contract Withdrawn: Delivery:"),
    ("contract_shared", "Contract Shared: Delivery:"),
    ("crimestat_increased", "CrimeStat Rating Increased"),
    ("emergency_services", "Emergency Services Are En Route"),
    ("entered_monitored_space", "Entered Monitored Space"),
    ("exited_monitored_space", "Exited Monitored Space"),
    ("fined", "Fined 1,000 UEC"),
    ("fuel_low", "Low Fuel"),
    ("hangar_queue", "Joined hangar queue"),
    ("hangar_ready", "Hangar Request Completed"),
    ("incapacitated", "Incapacitated"),
    ("incoming_call", "Incoming call: Alice"),
    ("injury", "Minor Injury Detected - Left Arm - Tier 1"),
    ("journal_entry", "Journal Entry Added: A new entry:"),
    ("jurisdiction_change", "Entered Crusader Jurisdiction"),
    ("money_sent", "You sent Alice:\n1,500 aUEC:"),
    ("monitored_space_down", "Monitored Space Down"),
    ("monitored_space_restored", "Monitored Space Restored"),
    ("objective_complete", "Objective Complete: Deliver package:"),
    ("objective_new", "New Objective: Pick up package:"),
    ("objective_withdrawn", "Objective Withdrawn: Pick up package:"),
    ("party_invite", "Alice\nParty Invite Received"),
    ("party_left", "You have left the party."),
    ("party_member_joined", "Alice has joined the party."),
    ("qt_calibration_complete_group", "Quantum Travel Calibration Complete By Alice:"),
    ("quantum_calibration_complete", "Quantum Travel Calibration Complete:"),
    ("quantum_calibration_started", "Quantum Travel Calibration Started By Alice:"),
    ("refinery_complete", "Refinery Work Order complete at ARC-L1:"),
    ("restricted_area", "Leaving Restricted Area"),
    ("reward_earned", "Awarded 500 aUEC:"),
    ("transaction_complete", "Transaction Complete:"),
    ("vehicle_impounded", "Vehicle Impounded: Obstructing landing pad:"),
]
RECORDS = [
    (
        "attachment_received",
        "AttachmentReceived Status[persistent] Player[Mallachi] Port[weapon] Attachment[Medpen, pen, 123] Elapsed[0.5]",
    ),
    (
        "cargo_transfer",
        "FreightElevatorUIProvider::FillUnstowRequest FreightElevatorKiosk_Cargo[22] Entities: 2 Location: 33 RequestId: 1",
    ),
    (
        "commodity_buy",
        "CommodityUIProvider SendCommodityBuyRequest playerId[p] shopId[s] price[500] quantity[100 cSCU]",
    ),
    (
        "commodity_sell",
        "CommodityUIProvider SendCommoditySellRequest playerId[p] shopId[s] amount[500] quantity[1]",
    ),
    (
        "fatal_collision",
        "<FatalCollision> Fatal Collision occured for vehicle AEGS_Avenger_Titan PlayerPilot: 1 Zone: Stanton",
    ),
    (
        "insurance_claim",
        "CWallet::ProcessClaimToNextStep New Insurance Claim Request entitlementURN: urn:ship, requestId: 1",
    ),
    (
        "insurance_claim_complete",
        "CWallet::RmMulticastOnProcessClaimCallback entitlementURN: urn:ship, result: 0",
    ),
    (
        "inventory_location_update",
        "<Update Inventory Location> Player[Mallachi] Landing [0] -> [123] Location [0] -> [123]",
    ),
    ("join_pu", "<Join PU> shard[eu-1] address[server:1]"),
    (
        "location_change",
        "RequestLocationInventory Player[Mallachi] Location[RR_CRU_LEO]",
    ),
    (
        "med_bed_heal",
        "<MED BED HEAL> Perform surgery event Success leftArm: true rightLeg: false",
    ),
    (
        "personal_inventory_data",
        "RequestOrCreatePersonalInventoryData Player[Mallachi] inventoryID[1:Location:123]",
    ),
    (
        "qt_arrived",
        "AEGS_Avenger_Titan[123]|CSCItemNavigation::OnQuantumDriveArrived Quantum Drive has arrived at final destination",
    ),
    ("quantum_route_set", "Player Selected Quantum Target"),
    (
        "refinery_submitted",
        "MiningShopUIProvider::OnRefineryRequest playerId[p] shopId[s]",
    ),
    ("session_start", "AccountLoginCharacterStatus_Character name Mallachi geid 123"),
    (
        "shop_buy",
        "ShoppingProvider SendStandardItemBuyRequest playerId[p] client_price[265] quantity[1] currencyType[UEC]",
    ),
    (
        "shop_sell",
        "ShopUIProvider SendShopSellRequest playerId[p] client_price[265] quantity[1] currencyType[UEC]",
    ),
    (
        "shop_transaction_result",
        "ShoppingProvider RmShopFlowResponse playerId[p] result[Success]",
    ),
    ("user_login", "User Login Success Handle[Mallachi]"),
]


class RecipeTests(unittest.TestCase):
    def test_compatibility_matrix_has_exact_bundle_and_tool_inventory(self):
        matrix = (Path(__file__).parents[1] / "docs/COMPATIBILITY.md").read_text()
        instructions = Instructions.load(bundled_bytes())
        recipes = {r["id"] for r in instructions.data["rules"]}
        self.assertEqual(len(recipes), 60)
        self.assertEqual(set(re.findall(r"\| `([^`]+\.v\d+)` \|", matrix)), recipes)
        with tempfile.TemporaryDirectory() as directory:
            service = Service(Path(directory) / "runtime")
            try:
                names = {name for name, _ in ToolInterface(service).get_tools()}
                self.assertEqual(len(names), 7)
                self.assertEqual(set(re.findall(r"\| `(get_\w+)` \|", matrix)), names)
            finally:
                service.close()

    def test_hand_authored_normalized_fields(self):
        expected = {
            "armistice_zone": {"action": "entered"},
            "restricted_area": {"action": "exited"},
            "injury": {"body_part": "Left Arm", "severity": "Minor", "tier": 1},
            "reward_earned": {"amount": "500", "currency": "aUEC"},
            "fined": {"amount": "1000", "currency": "UEC"},
            "money_sent": {"recipient": "Alice", "amount": "1500", "currency": "aUEC"},
            "contract_accepted": {"mission_id": "m1", "mission_name": "Delivery"},
            "objective_new": {"mission_id": "m1", "objective": "Pick up package"},
            "session_start": {"player_name": "Mallachi", "player_geid": "123"},
            "join_pu": {"shard": "eu-1"},
            "med_bed_heal": {"healed_parts": {"leftArm": True}},
            "shop_buy": {
                "price": 265.0,
                "quantity": 1,
                "currency_type": "UEC",
                "source_provider": "shopping",
            },
            "shop_sell": {
                "price": 265.0,
                "quantity": 1,
                "currency_type": "UEC",
                "source_provider": "shop_ui",
            },
            "shop_transaction_result": {
                "result": "Success",
                "player_id": "p",
                "source_provider": "shopping",
            },
            "commodity_buy": {
                "price": 500.0,
                "quantity_cscu": 100.0,
                "quantity_unit": "cSCU",
            },
            "cargo_transfer": {"request_id": 1},
        }
        reader = Reader(Instructions.load(bundled_bytes()))
        cases = dict(RECORDS)
        cases.update({kind: notification(text) for kind, text in NOTIFICATIONS})
        for kind, fields in expected.items():
            with self.subTest(kind=kind):
                event = reader.parse(stamped(cases[kind]))
                self.assertEqual(event.errors, [])
                self.assertEqual({key: event.fields.get(key) for key in fields}, fields)
                self.assertFalse(event.game_build_verified)

    def test_hand_authored_cases_are_recognized_and_extract_required_fields(self):
        reader = Reader(Instructions.load(bundled_bytes()))
        fixtures = RECORDS + [
            (
                kind,
                '<SHUDEvent> Added notification "'
                + text
                + '" [13] to queue. MissionId: [m1] ObjectiveId: [o1]',
            )
            for kind, text in NOTIFICATIONS
        ]
        for kind, text in fixtures:
            with self.subTest(event=kind):
                event = reader.parse("<2026-09-15T12:00:00Z> " + text)
                self.assertIsNotNone(event)
                self.assertEqual(event.event_type, kind)
                self.assertEqual(event.errors, [])


def notification(text, mission="m1"):
    return f'<SHUDEvent> Added notification "{text}" [13] to queue. MissionId: [{mission}] ObjectiveId: [o1]'


def stamped(text, seconds=0):
    minutes, seconds = divmod(seconds, 60)
    return f"<2026-09-15T12:{minutes:02d}:{seconds:02d}Z> {text}"


def buy(currency="UEC", item="Medpen"):
    currency_field = f" currencyType[{currency}]" if currency else ""
    return f"ShoppingProvider SendStandardItemBuyRequest playerId[p] client_price[265] quantity[2] itemName[{item}]{currency_field}"


RESPONSE = (
    "ShoppingProvider RmShopFlowResponse playerId[p] result[Success] type[Buying]"
)


class SemanticContractTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.service = Service(self.root / "runtime")
        self.addCleanup(lambda: self.service.close())
        self.offset = 0

    def send(self, text, seconds=0):
        record = Record(stamped(text, seconds), self.offset, self.offset + 500)
        self.offset += 500
        return self.service.ingest(record, "LIVE", "g1")

    def tool(self, name, **parameters):
        return ToolInterface(self.service).call(
            name, {"environment": "LIVE", **parameters}
        )

    def ledger(self):
        return self.tool("get_trade_ledger", time_range="all")

    def restart(self):
        self.service.close()
        self.service = Service(self.root / "runtime")

    def test_persisted_requests_ambiguous_and_expired_never_change_confirmed_ledger(
        self,
    ):
        for scenario in ("requested", "ambiguous", "expired"):
            with self.subTest(scenario=scenario):
                baseline = self.ledger()
                request = self.send(buy(), 0)
                self.assertEqual(request[0]["status"], "requested")
                self.assertIsNone(request[0].get("amount_auec"))
                if scenario == "ambiguous":
                    self.send(buy(item="Other"), 1)
                    result = self.send(RESPONSE, 2)[0]
                    self.assertEqual(result["status"], "ambiguous")
                    self.assertIsNone(result.get("amount_auec"))
                elif scenario == "expired":
                    result = self.send(RESPONSE, 121)[0]
                    self.assertEqual(result["status"], "unresolved")
                    self.assertIsNone(result.get("amount_auec"))
                self.assertEqual(self.ledger(), baseline)
                self.restart()
                self.assertEqual(self.ledger(), baseline)
                self.assertEqual(self.tool("get_trade_entries", time_range="all"), [])
                # Each scenario has a fresh session; retain the existing reset suites.
                self.send("User Login Success Handle[Mallachi]", 122)

    def test_unknown_currency_unique_success_counts_trade_but_has_null_money(self):
        for currency in (None, "NovelCredits"):
            with self.subTest(currency=currency):
                before = self.ledger()
                self.send(buy(currency), 0)
                result = self.send(RESPONSE, 1)[0]
                self.assertEqual(result["event_type"], "shop_buy")
                self.assertEqual(result["status"], "confirmed")
                self.assertIsNone(result.get("amount_auec"))
                self.assertEqual(len(result["source_occurrences"]), 2)
                self.restart()
                after = self.ledger()
                self.assertEqual(after["entries"], before["entries"] + 1)
                self.assertEqual(
                    after["unknown_amount_entries"],
                    before["unknown_amount_entries"] + 1,
                )
                for key in ("income_auec", "spending_auec", "net_cash_flow_auec"):
                    self.assertEqual(after[key], before[key])
                entries = self.tool(
                    "get_trade_entries", time_range="all", sort_by="time"
                )
                self.assertEqual(len(entries), after["entries"])
                self.assertTrue(
                    all(
                        row["status"] == "confirmed" and row.get("amount_auec") is None
                        for row in entries
                    )
                )

    def test_known_currency_books_total_price_once_without_quantity_multiplier(self):
        self.send(buy(), 0)
        result = self.send(RESPONSE, 1)[0]
        self.assertEqual(result["amount_auec"], -265.0)
        self.assertEqual(result["data"]["quantity"], 2)
        self.restart()
        self.assertEqual(self.ledger()["spending_auec"], 265.0)
        self.assertEqual(self.ledger()["entries"], 1)

    def test_orphan_mission_unknown_location_and_health_remain_evidence(self):
        self.send("User Login Success Handle[Mallachi]")
        self.send(notification("New Objective: Pick up package:", "orphan"), 1)
        missions = self.tool("get_active_missions")
        self.assertEqual(missions["missions"], [])
        self.assertEqual(missions["reconstruction"]["status"], "partial")
        self.assertEqual(
            missions["reconstruction"]["orphan_objectives"][0]["mission_id"], "orphan"
        )
        self.send("RequestLocationInventory Player[Mallachi] Location[RR_CRU_LEO]", 2)
        result = self.send(
            "RequestLocationInventory Player[Mallachi] Location[UNSEEN_CODE]", 3
        )[0]
        self.assertEqual(result["status"], "unresolved")
        for seconds, kind in ((4, "Bleeding"), (5, "Incapacitated")):
            self.send(notification(kind), seconds)
        state = self.tool("get_current_game_state")
        self.assertIsNone(state["location_name"])
        self.assertEqual(state["location_status"], "unknown")
        self.assertEqual(state["last_known_location"]["code"], "RR_CRU_LEO")
        for key in ("bleeding", "incapacitated"):
            self.assertIsNone(state[key])
            self.assertIs(state["observations"][key]["value"], True)

    def test_foreign_same_model_exit_and_quantum_are_not_ownership(self):
        self.send("User Login Success Handle[Mallachi]")
        self.send(
            notification(
                "You joined channel '@vehicle_NameAEGS_Avenger_Titan : Other'"
            ),
            1,
        )
        state = self.tool("get_current_game_state")
        self.assertFalse(state["own_ship"])
        self.assertTrue(state["aboard_ship"])
        self.assertEqual(
            self.send(
                notification(
                    "You left channel '@vehicle_NameAEGS_Avenger_Titan : Mallachi'"
                ),
                2,
            ),
            [],
        )
        self.assertTrue(self.tool("get_current_game_state")["aboard_ship"])
        result = self.send(dict(RECORDS)["qt_arrived"], 3)[0]
        self.assertEqual(result["attribution"], "possible_player_ship")
        self.assertFalse(self.tool("get_current_game_state")["own_ship"])

    def test_commodity_cargo_requests_and_generic_complete_do_not_confirm_inventory(
        self,
    ):
        baseline = self.ledger()
        for kind in ("commodity_buy", "commodity_sell", "cargo_transfer"):
            result = self.send(dict(RECORDS)[kind])[0]
            self.assertEqual(result["status"], "requested")
            self.assertIsNone(result.get("amount_auec"))
        result = self.send(notification("Transaction Complete:"), 1)[0]
        self.assertEqual(result["status"], "observed")
        self.restart()
        self.assertEqual(self.ledger(), baseline)
        self.assertEqual(self.tool("get_trade_entries", time_range="all"), [])

    def test_exact_objective_withdrawal_and_invalid_mission_do_not_invent_state(self):
        self.send(notification("Contract Accepted: Delivery:"))
        self.send(notification("New Objective: Pick up package:"), 1)
        self.send(notification("Objective Withdrawn: Other package:"), 2)
        self.assertEqual(
            self.tool("get_active_missions")["missions"][0]["objective"],
            "Pick up package",
        )
        self.send(notification("Objective Withdrawn: Pick up package:"), 3)
        self.assertIsNone(self.tool("get_active_missions")["missions"][0]["objective"])
        self.assertEqual(
            self.send(
                notification(
                    "Contract Accepted: Invented:",
                    "00000000-0000-0000-0000-000000000000",
                ),
                4,
            ),
            [],
        )
        self.assertEqual(
            [
                mission["mission_id"]
                for mission in self.tool("get_active_missions")["missions"]
            ],
            ["m1"],
        )
        events = self.tool("get_recent_game_events", event_type="contract_accepted")
        self.assertEqual([row["event_type"] for row in events], ["mission_accepted"])

    def test_output_only_notifications_preserve_domain_state_and_remain_recent_observations(
        self,
    ):
        kinds = {
            "contract_available",
            "contract_shared",
            "crimestat_increased",
            "emergency_services",
            "fuel_low",
            "hangar_queue",
            "hangar_ready",
            "incoming_call",
            "journal_entry",
            "party_invite",
            "party_left",
            "party_member_joined",
            "qt_calibration_complete_group",
            "quantum_calibration_complete",
            "quantum_calibration_started",
            "refinery_complete",
            "transaction_complete",
            "vehicle_impounded",
        }
        self.send("User Login Success Handle[Mallachi]")
        before = self.tool("get_current_game_state")
        fields = (
            "active_missions",
            "injuries",
            "location_name",
            "ship",
            "aboard_ship",
            "monitored",
            "jurisdiction",
            "observations",
        )
        for seconds, (kind, text) in enumerate(NOTIFICATIONS, 1):
            if kind not in kinds:
                continue
            with self.subTest(kind=kind):
                result = self.send(notification(text), seconds)[0]
                self.assertEqual(result["event_type"], kind)
                self.assertEqual(result["status"], "observed")
                state = self.tool("get_current_game_state")
                self.assertEqual(
                    {key: state[key] for key in fields},
                    {key: before[key] for key in fields},
                )
                self.assertEqual(
                    self.tool("get_recent_game_events", count=1)[0], result
                )

    def test_missing_shop_required_field_produces_diagnostic_without_handler_or_trade(
        self,
    ):
        before = self.ledger()
        self.assertEqual(
            self.send(
                "ShoppingProvider SendStandardItemBuyRequest playerId[p] quantity[1] currencyType[UEC]"
            ),
            [],
        )
        self.assertEqual(self.tool("get_recent_game_events"), [])
        self.assertEqual(self.ledger(), before)
        self.assertIn("missing:price", self.service.diagnostics("LIVE")[0]["errors"])

    def test_json_only_wording_change_preserves_normalization_handler_and_tools(self):
        data = json.loads(bundled_bytes())
        # Future raw wording, authored here; no claim this occurs in a retail log.
        data = json.loads(
            json.dumps(data)
            .replace("ShoppingProvider", "MarketProvider")
            .replace("SendStandardItemBuyRequest", "RequestPurchase")
            .replace("RmShopFlowResponse", "PurchaseResponse")
            .replace("client_price", "totalCredits")
        )
        response_rule = next(
            rule for rule in data["rules"] if rule["event"] == "shop_transaction_result"
        )
        response_rule["read"].append(
            {
                "op": "choose",
                "cases": [
                    {
                        "when": {
                            "contains": "result[Accepted]",
                            "source": "record.text",
                        },
                        "steps": [{"op": "constant", "fields": {"result": "Success"}}],
                    }
                ],
            }
        )
        candidate = Instructions.load(json.dumps(data).encode())
        original = Instructions.load(bundled_bytes())
        lines = [stamped(buy()), stamped(RESPONSE, 1)]
        changed = [
            line.replace("ShoppingProvider", "MarketProvider")
            .replace("SendStandardItemBuyRequest", "RequestPurchase")
            .replace("RmShopFlowResponse", "PurchaseResponse")
            .replace("client_price", "totalCredits")
            .replace("result[Success]", "result[Accepted]")
            for line in lines
        ]
        for old, new in zip(lines, changed, strict=True):
            expected = Reader(original).parse(old)
            actual = Reader(candidate).parse(new)
            self.assertEqual(actual.errors, [])
            self.assertEqual(actual.fields, expected.fields)
            self.assertEqual(actual.event_type, expected.event_type)
        services = [
            Service(self.root / name, instructions=instructions)
            for name, instructions in (("original", original), ("candidate", candidate))
        ]
        try:
            outputs = []
            for service, records in zip(services, (lines, changed), strict=True):
                outputs.append(
                    [
                        service.ingest(
                            Record(line, index * 500, (index + 1) * 500), "LIVE", "g1"
                        )
                        for index, line in enumerate(records)
                    ]
                )
            self.assertEqual(outputs[0], outputs[1])
            self.assertEqual(outputs[0][1][0]["status"], "confirmed")
            self.assertEqual(outputs[0][1][0]["amount_auec"], -265.0)
            for tool in (
                "get_recent_game_events",
                "get_trade_entries",
                "get_trade_ledger",
            ):
                parameters = (
                    {"environment": "LIVE", "time_range": "all"}
                    if "trade" in tool
                    else {"environment": "LIVE"}
                )
                self.assertEqual(
                    ToolInterface(services[0]).call(tool, parameters),
                    ToolInterface(services[1]).call(tool, parameters),
                )
            # Historical public evidence excludes runtime freshness counters.
            for service in services:
                state = service.state("LIVE")
                state.pop("reader_health")
                if service is services[0]:
                    baseline = copy.deepcopy(state)
                else:
                    self.assertEqual(state, baseline)
            for raw in ("Failed", "Unknown"):
                event = Reader(candidate).parse(
                    changed[1].replace("result[Accepted]", f"result[{raw}]")
                )
                self.assertEqual(event.fields["result"], raw)
                self.assertNotEqual(event.fields["result"], "Success")
        finally:
            for service in services:
                service.close()


if __name__ == "__main__":
    unittest.main()
