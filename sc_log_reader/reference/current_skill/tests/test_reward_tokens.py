from __future__ import annotations

from pathlib import Path

from event_log import EventLog
from logic import StateLogic
from parser import LogParser


# SC 4.9.0 physical reward token notification. The text spans several physical
# lines, so the first line the parser sees is truncated with no closing quote.
TOKEN_REWARD = '<2026-07-16T18:09:01.251Z> [Notice] <SHUDEvent_OnNotification> Added notification "You\'ve earned: 30 rewards'
# Legacy pre-2026-02 money notification (bare number, no unit word).
LEGACY_MONEY_REWARD = '<2026-06-20T11:35:32.196Z> [Notice] <SHUDEvent_OnNotification> Added notification "You\'ve earned: 15,000: " [13] to queue. New queue size: 1, MissionId: [00000000-0000-0000-0000-000000000000], ObjectiveId: [] [Team_CoreGameplayFeatures][Missions][Comms]'
# aUEC award via the SHUDEvent notification "Awarded N aUEC" format.
REWARD_ADDED = '<2026-06-20T11:35:32.196Z> [Notice] <SHUDEvent_OnNotification> Added notification "Awarded 500 aUEC: " [14] to queue. New queue size: 1, MissionId: [00000000-0000-0000-0000-000000000000], ObjectiveId: [] [Team_CoreGameplayFeatures][Missions][Comms]'
# Non-numeric named item reward.
ITEM_REWARD = '<2026-06-20T11:35:33.100Z> [Notice] <SHUDEvent_OnNotification> Added notification "You\'ve earned: ASD Secure Drive: " [15] to queue. New queue size: 1, MissionId: [00000000-0000-0000-0000-000000000000], ObjectiveId: [] [Team_CoreGameplayFeatures][Missions][Comms]'
LOCATION_CHANGE = '<2026-07-16T18:09:15.000Z> [Notice] <RequestLocationInventory> Player[Mallachi] requested inventory for Location[RR_CRU_LEO] [Team_Inventory][Persistence]'


def _stack(tmp_path: Path) -> tuple[LogParser, StateLogic, EventLog]:
    parser = LogParser(tmp_path / "Game.log")
    logic = StateLogic(parser)
    event_log = EventLog(tmp_path / "event_log.jsonl")
    logic.set_event_log(event_log)
    logic.start()
    return parser, logic, event_log


def test_parser_classifies_physical_token_reward_as_quantity(tmp_path: Path) -> None:
    parser = LogParser(tmp_path / "Game.log")

    event = parser._parse_line(TOKEN_REWARD)

    assert event is not None
    assert event.event_type == "reward_earned"
    assert event.data["quantity"] == "30"
    assert event.data["item_name"] == "rewards"
    assert "amount" not in event.data


def test_token_reward_books_no_money_and_keeps_count_in_bundle(tmp_path: Path) -> None:
    parser, logic, event_log = _stack(tmp_path)
    try:
        for line in (TOKEN_REWARD, LOCATION_CHANGE):
            parser._process_line(line)

        components = event_log.query(event_type="reward_earned", limit=10)
        bundles = event_log.query(event_type="mission_reward", limit=10)

        assert len(components) == 1
        component = components[0]
        assert component.amount_auec is None
        assert component.item_name == "rewards"
        assert component.confidence == "high"

        assert len(bundles) == 1
        bundle = bundles[0]
        assert bundle.data["money"] == {}
        assert bundle.data["items"] == ["30x rewards"]
    finally:
        logic.stop()


def test_awarded_auec_still_books_money(tmp_path: Path) -> None:
    parser, logic, event_log = _stack(tmp_path)
    try:
        for line in (REWARD_ADDED, LOCATION_CHANGE):
            parser._process_line(line)

        components = event_log.query(event_type="reward_earned", limit=10)

        assert len(components) == 1
        assert components[0].amount_auec == 500.0
    finally:
        logic.stop()


def test_legacy_bare_number_reward_still_books_money(tmp_path: Path) -> None:
    parser = LogParser(tmp_path / "Game.log")

    event = parser._parse_line(LEGACY_MONEY_REWARD)

    assert event is not None
    assert event.event_type == "reward_earned"
    assert event.data["amount"] == "15000"
    assert "quantity" not in event.data
    assert "item_name" not in event.data


def test_non_numeric_item_reward_still_books_item_name(tmp_path: Path) -> None:
    parser = LogParser(tmp_path / "Game.log")

    event = parser._parse_line(ITEM_REWARD)

    assert event is not None
    assert event.event_type == "reward_earned"
    assert event.data["item_name"] == "ASD Secure Drive"
    assert "quantity" not in event.data
    assert "amount" not in event.data
