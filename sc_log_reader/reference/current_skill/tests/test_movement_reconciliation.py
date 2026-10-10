from __future__ import annotations

from pathlib import Path

from event_log import EventLog
from logic import StateLogic
from parser import LogParser


SHOPPING_BUY = '<2026-06-27T17:07:27.757Z> [Notice] <CEntityComponentShoppingProvider::SendStandardItemBuyRequest> Sending SShopBuyRequest - playerId[859757483277] shopId[859720285604] shopName[SCShop_SPGiftshop_Orison] kioskId[0] client_price[265.000000] itemClassGUID[7d50411f-088c-4c99-b85a-a6eaf95504c3] itemName[crlf_consumable_healing_01] quantity[1] currencyType[UEC] [Team_CoreGameplayFeatures][Shops][UI]'
SHOPPING_RESPONSE = '<2026-06-27T17:07:28.279Z> [Notice] <CEntityComponentShoppingProvider::RmShopFlowResponse> Shop Flow Response - playerId[859757483277] result[Success] [Team_CoreGameplayFeatures][Shops][UI]'
TRANSACTION_COMPLETE = '<2026-06-27T17:07:28.287Z> [Notice] <SHUDEvent_OnNotification> Added notification "Transaction Complete: " [3] to queue. New queue size: 1, MissionId: [00000000-0000-0000-0000-000000000000], ObjectiveId: [] [Team_CoreGameplayFeatures][Missions][Comms]'

SHOPUI_BUY = '<2026-06-27T17:14:51.734Z> [Notice] <CEntityComponentShopUIProvider::SendShopBuyRequest> Sending SShopBuyRequest - playerId[859757483277] shopId[859721423990] shopName[SCShop_Orison_KelTo] kioskId[859721423995] client_price[8463.000000] itemClassGUID[e15e874d-a0c1-4f91-939b-b04bf7a9e839] itemName[klwe_pistol_energy_01_mag] quantity[31]  [Team_CoreGameplayFeatures][Shops][UI]'
SHOPUI_RESPONSE = '<2026-06-27T17:14:52.246Z> [Notice] <CEntityComponentShopUIProvider::RmShopFlowResponse> Received ShopFlowResponse - playerId[859757483277] shopId[859721423990] shopName[SCShop_Orison_KelTo] kioskId[859721423995] kioskState[BuyRequestProcessing] result[Success] type[Buying] [Team_CoreGameplayFeatures][Shops][UI]'

MISSION_ID = '11111111-2222-3333-4444-555555555555'
CONTRACT_COMPLETE = f'<2026-06-20T11:35:30.000Z> [Notice] <SHUDEvent_OnNotification> Added notification "Contract Complete: Legal Claim: " [13] to queue. New queue size: 1, MissionId: [{MISSION_ID}], ObjectiveId: [] [Team_CoreGameplayFeatures][Missions][Comms]'
REWARD_ADDED = '<2026-06-20T11:35:32.196Z> [Notice] <SHUDEvent_OnNotification> Added notification "Awarded 500 aUEC: " [14] to queue. New queue size: 1, MissionId: [00000000-0000-0000-0000-000000000000], ObjectiveId: [] [Team_CoreGameplayFeatures][Missions][Comms]'
REWARD_BARE = '<2026-06-20T11:35:32.196Z>    "Awarded 500 aUEC: " [14]'
REWARD_NEXT = '<2026-06-20T11:35:32.198Z> [Notice] <UpdateNotificationItem> Notification "Awarded 500 aUEC: " [14], Action: Next [Team_CoreGameplayFeatures][Missions][Comms]'
ITEM_REWARD = '<2026-06-20T11:35:33.100Z> [Notice] <SHUDEvent_OnNotification> Added notification "You\'ve earned: ASD Secure Drive: " [15] to queue. New queue size: 1, MissionId: [00000000-0000-0000-0000-000000000000], ObjectiveId: [] [Team_CoreGameplayFeatures][Missions][Comms]'
BLUEPRINT_REWARD = '<2026-06-20T11:35:33.500Z> [Notice] <SHUDEvent_OnNotification> Added notification "Received Blueprint: Citadel Core Base: " [16] to queue. New queue size: 1, MissionId: [00000000-0000-0000-0000-000000000000], ObjectiveId: [] [Team_CoreGameplayFeatures][Missions][Comms]'
LOCATION_CHANGE = '<2026-06-20T11:35:45.000Z> [Notice] <RequestLocationInventory> Player[Mallachi] requested inventory for Location[RR_CRU_LEO] [Team_Inventory][Persistence]'


def _stack(tmp_path: Path) -> tuple[LogParser, StateLogic, EventLog]:
    parser = LogParser(tmp_path / "Game.log")
    logic = StateLogic(parser)
    event_log = EventLog(tmp_path / "event_log.jsonl")
    logic.set_event_log(event_log)
    logic.start()
    return parser, logic, event_log


def test_parser_recognizes_shopping_provider_purchase_and_response(tmp_path: Path) -> None:
    parser = LogParser(tmp_path / "Game.log")

    buy = parser._parse_line(SHOPPING_BUY)
    response = parser._parse_line(SHOPPING_RESPONSE)

    assert buy is not None
    assert buy.event_type == "shop_buy"
    assert buy.data["source_provider"] == "shopping"
    assert buy.data["item_name"] == "crlf_consumable_healing_01"
    assert buy.data["price"] == 265.0
    assert buy.data["quantity"] == 1
    assert buy.data["currency_type"] == "UEC"

    assert response is not None
    assert response.event_type == "shop_transaction_result"
    assert response.data["source_provider"] == "shopping"
    assert response.data["player_id"] == "859757483277"
    assert response.data["result"] == "Success"
    assert "transaction_type" not in response.data


def test_parser_adds_notification_context_to_blueprint_reward(tmp_path: Path) -> None:
    parser = LogParser(tmp_path / "Game.log")

    event = parser._parse_line(BLUEPRINT_REWARD)

    assert event is not None
    assert event.event_type == "blueprint_received"
    assert event.data["blueprint_name"] == "Citadel Core Base"
    assert event.data["notification_id"] == "16"
    assert event.data["mission_id"] == "00000000-0000-0000-0000-000000000000"
    assert event.data["objective_id"] == ""


def test_shopping_provider_purchase_writes_one_trade_and_suppresses_hud_confirmation(
    tmp_path: Path,
) -> None:
    parser, logic, event_log = _stack(tmp_path)
    try:
        for line in (SHOPPING_BUY, SHOPPING_RESPONSE, TRANSACTION_COMPLETE):
            parser._process_line(line)

        entries = event_log.query(limit=10)

        assert [entry.event_type for entry in entries] == ["shop_buy"]
        trade = entries[0]
        assert trade.amount_auec == -265.0
        assert trade.item_name == "crlf_consumable_healing_01"
        assert trade.movement_category == "economy"
        assert trade.movement_verb == "bought"
        assert trade.confidence == "medium"
        assert trade.data["source_provider"] == "shopping"
        assert trade.data["confirmation_match"] == "player_recent"
        assert trade.source_events == ["shop_buy", "shop_transaction_result"]
    finally:
        logic.stop()


def test_shopui_provider_purchase_keeps_exact_match_high_confidence(tmp_path: Path) -> None:
    parser, logic, event_log = _stack(tmp_path)
    try:
        for line in (SHOPUI_BUY, SHOPUI_RESPONSE):
            parser._process_line(line)

        entries = event_log.query(limit=10)

        assert [entry.event_type for entry in entries] == ["shop_buy"]
        trade = entries[0]
        assert trade.amount_auec == -8463.0
        assert trade.data["confirmation_match"] == "shop_kiosk"
        assert trade.confidence == "high"
        assert trade.movement_category == "economy"
        assert trade.movement_verb == "bought"
    finally:
        logic.stop()


def test_reward_notification_stack_writes_single_reward_movement(tmp_path: Path) -> None:
    parser, logic, event_log = _stack(tmp_path)
    try:
        for line in (REWARD_ADDED, REWARD_BARE, REWARD_NEXT, REWARD_ADDED):
            parser._process_line(line)

        entries = event_log.query(event_type="reward_earned", limit=10)

        assert [entry.event_type for entry in entries] == ["reward_earned"]
        reward = entries[0]
        assert reward.amount_auec == 500.0
        assert reward.movement_category == "economy"
        assert reward.movement_verb == "rewarded"
        assert reward.confidence == "high"
        assert reward.data["notification_id"] == "14"
        assert reward.fingerprint == "reward_earned|14|500"
    finally:
        logic.stop()


def test_reward_components_flush_to_one_mission_reward_bundle(tmp_path: Path) -> None:
    parser, logic, event_log = _stack(tmp_path)
    try:
        for line in (
            CONTRACT_COMPLETE,
            REWARD_ADDED,
            ITEM_REWARD,
            BLUEPRINT_REWARD,
            LOCATION_CHANGE,
        ):
            parser._process_line(line)

        bundles = event_log.query(event_type="mission_reward", limit=10)

        assert len(bundles) == 1
        bundle = bundles[0]
        assert bundle.amount_auec == 500.0
        assert bundle.movement_category == "economy"
        assert bundle.movement_verb == "rewarded"
        assert bundle.confidence == "medium"
        assert bundle.data["mission_id"] == MISSION_ID
        assert bundle.data["mission_name"] == "Legal Claim"
        assert bundle.data["money"] == {"amount_auec": 500.0}
        assert bundle.data["items"] == ["ASD Secure Drive"]
        assert bundle.data["blueprints"] == ["Citadel Core Base"]
        assert bundle.data["notification_ids"] == ["14", "15", "16"]
        assert bundle.data["correlation"] == "recent_contract_complete"
        assert bundle.data["component_count"] == 3
        assert bundle.source_events == [
            "contract_complete",
            "reward_earned",
            "blueprint_received",
        ]
    finally:
        logic.stop()


def test_reward_earned_entry_inherits_recency_resolved_mission_id(
    tmp_path: Path,
) -> None:
    """Tier-2: reward_earned's raw MissionId is the zero sentinel, but a
    contract_complete a few seconds earlier resolves the mission by recency.

    The WRITTEN reward_earned event-log entry must carry that SAME resolved
    mission_id, equal to the mission_reward bundle's, so a downstream
    consumer reconciling component against bundle (e.g. SC_Accountant) can
    match on mission_id instead of on time alone.
    """
    parser, logic, event_log = _stack(tmp_path)
    try:
        for line in (CONTRACT_COMPLETE, REWARD_ADDED, LOCATION_CHANGE):
            parser._process_line(line)

        components = event_log.query(event_type="reward_earned", limit=10)
        bundles = event_log.query(event_type="mission_reward", limit=10)

        assert len(components) == 1
        component = components[0]
        assert component.data["mission_id"] == MISSION_ID
        assert component.data["mission_name"] == "Legal Claim"

        assert len(bundles) == 1
        bundle = bundles[0]
        assert bundle.data["mission_id"] == MISSION_ID

        assert component.data["mission_id"] == bundle.data["mission_id"]
    finally:
        logic.stop()


def test_reward_earned_entry_stays_mission_id_less_without_recent_contract(
    tmp_path: Path,
) -> None:
    """Tier-3: no valid embedded mission_id and no recent contract_complete
    to correlate by recency. The reward_earned entry stays mission_id-less,
    and so does the bundle it feeds -- both empty is the accepted fallback.
    """
    parser, logic, event_log = _stack(tmp_path)
    try:
        for line in (REWARD_ADDED, LOCATION_CHANGE):
            parser._process_line(line)

        components = event_log.query(event_type="reward_earned", limit=10)
        bundles = event_log.query(event_type="mission_reward", limit=10)

        assert len(components) == 1
        assert components[0].data["mission_id"] == ""

        assert len(bundles) == 1
        assert bundles[0].data["mission_id"] == ""
        assert components[0].data["mission_id"] == bundles[0].data["mission_id"]
    finally:
        logic.stop()
