"""Tests for SC_LogReader event-log import policy."""

from __future__ import annotations

import asyncio
import importlib.util
import json
import logging
import os
import sys
from pathlib import Path

_skill_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _skill_dir not in sys.path:
    sys.path.insert(0, _skill_dir)

from assets import AssetManager  # noqa: E402
from factories import _format_auec  # noqa: E402
from guid_resolver import GuidResolver  # noqa: E402
from store import AccountantStore  # noqa: E402


def _load_skill_main():
    """Load skills/sc_accountant/main.py by explicit file path.

    A plain ``from main import ...`` is not safe here: the repository also
    has an unrelated top-level ``main.py`` at its root (the app entry point),
    and depending on process cwd / PYTHONPATH ordering, a bare ``import main``
    can resolve to (and cache in sys.modules under) that file instead of this
    skill's own main.py, dragging in an unrelated heavy import chain.
    Loading by file path sidesteps sys.path/sys.modules name resolution
    entirely, so this works regardless of invocation directory.
    """
    module_name = "sc_accountant_main_under_test"
    if module_name in sys.modules:
        return sys.modules[module_name]
    spec = importlib.util.spec_from_file_location(
        module_name, os.path.join(_skill_dir, "main.py")
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


_main = _load_skill_main()
SC_Accountant = _main.SC_Accountant
_is_live_economy_logreader_event_log = _main._is_live_economy_logreader_event_log
_logreader_event_log_env = _main._logreader_event_log_env


def _write_event(path: Path, event: dict) -> None:
    path.write_text(json.dumps(event) + "\n", encoding="utf-8")


def _write_events(path: Path, events: list[dict]) -> None:
    path.write_text(
        "\n".join(json.dumps(e) for e in events) + "\n", encoding="utf-8"
    )


def _append_event(path: Path, event: dict) -> None:
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(event) + "\n")


def _shop_event(
    *,
    timestamp: str,
    event_type: str,
    price: float,
    item_name: str,
    shop_name: str,
) -> dict:
    return {
        "timestamp": timestamp,
        "event_type": event_type,
        "location": shop_name,
        "data": {
            "price": price,
            "item_name": item_name,
            "quantity": 1,
            "quantity_unit": "units",
            "shop_name": shop_name,
        },
    }


def _accountant(
    store: AccountantStore,
    guid_resolver: GuidResolver | None = None,
) -> SC_Accountant:
    accountant = SC_Accountant.__new__(SC_Accountant)
    accountant._store = store
    accountant._guid_resolver = guid_resolver
    accountant._market = None
    accountant._positions = None
    accountant._futures = None
    accountant._assets = AssetManager(store, _format_auec)
    return accountant


def _mission_reward_event(
    *,
    timestamp: str,
    first_seen: str,
    last_seen: str,
    mission_id: str,
    mission_name: str,
    amount_auec: float,
    blueprints: list[str] | None = None,
) -> dict:
    return {
        "timestamp": timestamp,
        "event_type": "mission_reward",
        "location": "Area18",
        "player_name": "TestPilot",
        "data": {
            "mission_id": mission_id,
            "mission_name": mission_name,
            "money": {"amount_auec": amount_auec} if amount_auec else {},
            "items": [],
            "blueprints": blueprints or [],
            "notification_ids": [],
            "objective_ids": [],
            "correlation": "mission_id",
            "first_seen": first_seen,
            "last_seen": last_seen,
            "component_count": 1,
        },
        "amount_auec": amount_auec if amount_auec else None,
        "movement_category": "economy",
        "movement_verb": "rewarded",
        "confidence": "high",
        "fingerprint": (
            f"mission_reward|{mission_id}|{first_seen}|{amount_auec}|"
            f"{','.join(blueprints or [])}"
        ),
        "source_events": ["reward_earned"],
    }


def _reward_earned_event(
    *,
    timestamp: str,
    amount: str,
    mission_id: str = "",
    mission_name: str = "",
    notification_id: str = "",
) -> dict:
    return {
        "timestamp": timestamp,
        "event_type": "reward_earned",
        "location": "Area18",
        "player_name": "TestPilot",
        "data": {
            "amount": amount,
            "item_name": None,
            "mission_id": mission_id,
            "mission_name": mission_name,
            "notification_id": notification_id,
        },
        "amount_auec": float(amount),
        "item_name": None,
        "movement_category": "economy",
        "movement_verb": "rewarded",
        "confidence": "high",
        "fingerprint": f"reward_earned|{notification_id or timestamp}|{amount}",
        "source_events": ["reward_earned"],
    }


def _fined_event(*, timestamp: str, amount: str) -> dict:
    return {
        "timestamp": timestamp,
        "event_type": "fined",
        "location": "Area18",
        "player_name": "TestPilot",
        "data": {"amount": amount},
        "amount_auec": -float(amount),
        "movement_category": "reputation",
        "movement_verb": "fined",
        "confidence": "medium",
        "fingerprint": f"fined|{timestamp}",
        "source_events": ["fined"],
    }


def _money_sent_event(*, timestamp: str, amount: str, recipient: str) -> dict:
    return {
        "timestamp": timestamp,
        "event_type": "money_sent",
        "location": "Area18",
        "player_name": "TestPilot",
        "data": {"recipient": recipient, "amount": amount},
        "amount_auec": -float(amount),
        "movement_category": "economy",
        "movement_verb": "sent",
        "confidence": "medium",
        "fingerprint": f"money_sent|{timestamp}",
        "source_events": ["money_sent"],
    }


def _commodity_buy_event(
    *, timestamp: str, price: float, quantity: float, resource_guid: str
) -> dict:
    return {
        "timestamp": timestamp,
        "event_type": "commodity_buy",
        "location": "Area18",
        "player_name": "TestPilot",
        "data": {
            "transaction": "purchase",
            "category": "commodity",
            "item_name": None,
            "item_guid": resource_guid,
            "price": price,
            "quantity": quantity,
            "quantity_unit": "scu",
            "player_id": "player-1",
            "shop_id": "",
            "kiosk_id": "kiosk-1",
            "shop_name": "",
            "source_provider": "",
            "currency_type": "",
            "confirmation_match": "",
            "confirmation_result": "",
            "confirmation_source_provider": "",
        },
        "amount_auec": -price,
        "item_name": None,
        "movement_category": "economy",
        "movement_verb": "bought",
        "confidence": "medium",
        "fingerprint": (
            f"trade|commodity_buy|player-1||kiosk-1|{resource_guid}|{price}|"
            f"{quantity}|{timestamp}"
        ),
        "source_events": ["commodity_buy"],
    }


def _blueprint_received_event(*, timestamp: str, blueprint_name: str) -> dict:
    return {
        "timestamp": timestamp,
        "event_type": "blueprint_received",
        "location": "Area18",
        "player_name": "TestPilot",
        "data": {"blueprint_name": blueprint_name},
        "item_name": blueprint_name,
        "movement_category": "inventory",
        "movement_verb": "received",
        "confidence": "high",
        "fingerprint": f"blueprint_received|{timestamp}|{blueprint_name}",
        "source_events": ["blueprint_received"],
    }


def test_logreader_env_filter_treats_live_and_hotfix_as_live_economy() -> None:
    assert _logreader_event_log_env(Path("sc_logreader_eventlog_LIVE.jsonl")) == "LIVE"
    assert _logreader_event_log_env(Path("sc_logreader_eventlog_hotfix.jsonl")) == "HOTFIX"

    assert _is_live_economy_logreader_event_log(
        Path("sc_logreader_eventlog_LIVE.jsonl")
    )
    assert _is_live_economy_logreader_event_log(
        Path("sc_logreader_eventlog_HOTFIX.jsonl")
    )
    assert not _is_live_economy_logreader_event_log(
        Path("sc_logreader_eventlog_PTU.jsonl")
    )
    assert not _is_live_economy_logreader_event_log(
        Path("sc_logreader_eventlog_EPTU.jsonl")
    )
    assert not _is_live_economy_logreader_event_log(
        Path("sc_logreader_eventlog_TECH-PREVIEW.jsonl")
    )


def test_sync_imports_live_and_hotfix_but_ignores_ptu(tmp_path, monkeypatch) -> None:
    log_dir = tmp_path / "logreader"
    log_dir.mkdir()
    store = AccountantStore(tmp_path / "accountant")

    _write_event(
        log_dir / "sc_logreader_eventlog_LIVE.jsonl",
        _shop_event(
            timestamp="2026-06-28T10:00:00+00:00",
            event_type="shop_buy",
            price=100.0,
            item_name="Live MedPen",
            shop_name="Live Shop",
        ),
    )
    _write_event(
        log_dir / "sc_logreader_eventlog_HOTFIX.jsonl",
        _shop_event(
            timestamp="2026-06-28T10:10:00+00:00",
            event_type="shop_sell",
            price=40.0,
            item_name="Hotfix Salvage Tool",
            shop_name="Hotfix Shop",
        ),
    )
    _write_event(
        log_dir / "sc_logreader_eventlog_PTU.jsonl",
        _shop_event(
            timestamp="2026-06-28T10:20:00+00:00",
            event_type="shop_buy",
            price=999.0,
            item_name="PTU Test Item",
            shop_name="PTU Shop",
        ),
    )

    import services.file as file_service

    monkeypatch.setattr(file_service, "get_generated_files_dir", lambda _: str(log_dir))

    accountant = _accountant(store)
    log_names = {p.name for p in accountant._get_logreader_event_logs()}
    assert log_names == {
        "sc_logreader_eventlog_LIVE.jsonl",
        "sc_logreader_eventlog_HOTFIX.jsonl",
    }

    imported = asyncio.run(accountant._sync_from_logreader())

    assert imported == 2
    transactions = store.query_transactions(limit=10)
    descriptions = {txn.description for txn in transactions}
    assert descriptions == {
        "Item Purchase: Live MedPen",
        "Item Sale: Hotfix Salvage Tool",
    }
    assert all("PTU" not in txn.description for txn in transactions)

    balance = store.get_balance()
    assert balance.current_balance == -60.0
    assert balance.total_lifetime_expenses == 100.0
    assert balance.total_lifetime_income == 40.0

    cursor = store.get_sync_cursor()
    assert cursor["last_ts"] == "2026-06-28T10:10:00+00:00"


def _setup(
    tmp_path,
    monkeypatch,
    guid_resolver: GuidResolver | None = None,
) -> tuple[Path, AccountantStore, SC_Accountant]:
    """Common fixture setup: log dir, store, and a wired-up accountant."""
    log_dir = tmp_path / "logreader"
    log_dir.mkdir()
    store = AccountantStore(tmp_path / "accountant")
    accountant = _accountant(store, guid_resolver=guid_resolver)

    import services.file as file_service

    monkeypatch.setattr(file_service, "get_generated_files_dir", lambda _: str(log_dir))

    return log_dir, store, accountant


def test_sync_imports_canonical_mission_reward_bundle(tmp_path, monkeypatch) -> None:
    log_dir, store, accountant = _setup(tmp_path, monkeypatch)

    ts = "2026-06-30T10:00:00+00:00"
    _write_event(
        log_dir / "sc_logreader_eventlog_LIVE.jsonl",
        _mission_reward_event(
            timestamp=ts,
            first_seen=ts,
            last_seen=ts,
            mission_id="mission-1",
            mission_name="Delivery Run",
            amount_auec=5000.0,
            blueprints=["Cutter Schematic"],
        ),
    )

    imported = asyncio.run(accountant._sync_from_logreader())
    assert imported == 1

    txns = store.query_transactions(limit=10)
    assert len(txns) == 1
    txn = txns[0]
    assert txn.category == "mission_reward"
    assert txn.amount == 5000.0
    assert txn.description == "Mission Reward: Delivery Run"
    assert "component_reward" not in txn.tags

    balance = store.get_balance()
    assert balance.current_balance == 5000.0

    blueprints = store.query_assets(asset_type="blueprint", status=None, limit=10)
    assert any(a.name == "Cutter Schematic" for a in blueprints)


def test_bundle_suppresses_component_reward_when_component_written_first(
    tmp_path, monkeypatch
) -> None:
    log_dir, store, accountant = _setup(tmp_path, monkeypatch)

    ts = "2026-06-30T11:00:00+00:00"
    _write_events(
        log_dir / "sc_logreader_eventlog_LIVE.jsonl",
        [
            _reward_earned_event(
                timestamp=ts,
                amount="3000",
                mission_id="mission-2",
                mission_name="Bounty",
                notification_id="notif-2",
            ),
            _mission_reward_event(
                timestamp=ts,
                first_seen=ts,
                last_seen=ts,
                mission_id="mission-2",
                mission_name="Bounty",
                amount_auec=3000.0,
            ),
        ],
    )

    imported = asyncio.run(accountant._sync_from_logreader())
    assert imported == 1

    txns = store.query_transactions(limit=10)
    assert len(txns) == 1
    assert txns[0].category == "mission_reward"
    assert txns[0].amount == 3000.0
    assert "component_reward" not in txns[0].tags

    balance = store.get_balance()
    assert balance.current_balance == 3000.0


def test_bundle_suppresses_component_reward_when_bundle_written_first(
    tmp_path, monkeypatch
) -> None:
    log_dir, store, accountant = _setup(tmp_path, monkeypatch)

    ts = "2026-06-30T12:00:00+00:00"
    _write_events(
        log_dir / "sc_logreader_eventlog_LIVE.jsonl",
        [
            _mission_reward_event(
                timestamp=ts,
                first_seen=ts,
                last_seen=ts,
                mission_id="mission-3",
                mission_name="Salvage Job",
                amount_auec=7500.0,
            ),
            _reward_earned_event(
                timestamp=ts,
                amount="7500",
                mission_id="mission-3",
                mission_name="Salvage Job",
                notification_id="notif-3",
            ),
        ],
    )

    imported = asyncio.run(accountant._sync_from_logreader())
    assert imported == 1

    txns = store.query_transactions(limit=10)
    assert len(txns) == 1
    assert txns[0].amount == 7500.0

    balance = store.get_balance()
    assert balance.current_balance == 7500.0


def test_bundle_supersedes_component_reward_imported_in_earlier_sync(
    tmp_path, monkeypatch
) -> None:
    """The bundle can arrive on a later sync pass than its component."""
    log_dir, store, accountant = _setup(tmp_path, monkeypatch)
    log_path = log_dir / "sc_logreader_eventlog_LIVE.jsonl"

    ts = "2026-06-30T13:00:00+00:00"
    _write_event(
        log_path,
        _reward_earned_event(
            timestamp=ts,
            amount="4200",
            mission_id="mission-4",
            mission_name="Cargo Run",
            notification_id="notif-4",
        ),
    )

    imported_first = asyncio.run(accountant._sync_from_logreader())
    assert imported_first == 1

    txns_after_first = store.query_transactions(limit=10)
    assert len(txns_after_first) == 1
    assert "component_reward" in txns_after_first[0].tags

    balance = store.get_balance()
    assert balance.current_balance == 4200.0

    # SC_LogReader later flushes the canonical bundle for the same reward.
    _append_event(
        log_path,
        _mission_reward_event(
            timestamp=ts,
            first_seen=ts,
            last_seen=ts,
            mission_id="mission-4",
            mission_name="Cargo Run",
            amount_auec=4200.0,
        ),
    )

    imported_second = asyncio.run(accountant._sync_from_logreader())
    assert imported_second == 1

    txns_after_second = store.query_transactions(limit=10)
    assert len(txns_after_second) == 1
    assert txns_after_second[0].category == "mission_reward"
    assert "component_reward" not in txns_after_second[0].tags
    assert txns_after_second[0].amount == 4200.0

    balance = store.get_balance()
    assert balance.current_balance == 4200.0


def test_fingerprint_dedup_prevents_reimport_after_cursor_reset(
    tmp_path, monkeypatch
) -> None:
    log_dir, store, accountant = _setup(tmp_path, monkeypatch)
    log_path = log_dir / "sc_logreader_eventlog_LIVE.jsonl"

    _write_event(
        log_path,
        _commodity_buy_event(
            timestamp="2026-06-30T14:00:00+00:00",
            price=2500.0,
            quantity=50.0,
            resource_guid="11111111-2222-3333-4444-555555555555",
        ),
    )

    imported_first = asyncio.run(accountant._sync_from_logreader())
    assert imported_first == 1

    txns = store.query_transactions(limit=10)
    assert len(txns) == 1
    assert txns[0].source_fingerprint

    # Simulate a cursor reset (e.g. after manual troubleshooting): the event
    # already on disk must not be re-imported because its fingerprint is
    # already recorded on the existing transaction.
    store.save_sync_cursor("", 0)

    imported_second = asyncio.run(accountant._sync_from_logreader())
    assert imported_second == 0

    txns_after = store.query_transactions(limit=10)
    assert len(txns_after) == 1


def test_fined_imported_as_expense(tmp_path, monkeypatch) -> None:
    log_dir, store, accountant = _setup(tmp_path, monkeypatch)

    _write_event(
        log_dir / "sc_logreader_eventlog_LIVE.jsonl",
        _fined_event(timestamp="2026-06-30T15:00:00+00:00", amount="5000"),
    )

    imported = asyncio.run(accountant._sync_from_logreader())
    assert imported == 1

    txns = store.query_transactions(limit=10)
    assert len(txns) == 1
    txn = txns[0]
    assert txn.category == "fines"
    assert txn.transaction_type == "expense"
    assert txn.amount == 5000.0

    balance = store.get_balance()
    assert balance.current_balance == -5000.0
    assert balance.total_lifetime_expenses == 5000.0


def test_money_sent_imported_as_outgoing_transfer(tmp_path, monkeypatch) -> None:
    log_dir, store, accountant = _setup(tmp_path, monkeypatch)

    _write_event(
        log_dir / "sc_logreader_eventlog_LIVE.jsonl",
        _money_sent_event(
            timestamp="2026-06-30T16:00:00+00:00", amount="1000", recipient="Wingman"
        ),
    )

    imported = asyncio.run(accountant._sync_from_logreader())
    assert imported == 1

    txns = store.query_transactions(limit=10)
    assert len(txns) == 1
    txn = txns[0]
    assert txn.category == "money_transfer_sent"
    assert txn.transaction_type == "expense"
    assert txn.amount == 1000.0
    assert "Wingman" in txn.description

    balance = store.get_balance()
    assert balance.current_balance == -1000.0


def test_unknown_commodity_guid_handled_gracefully(tmp_path, monkeypatch, caplog) -> None:
    guid_resolver = GuidResolver(tmp_path / "guid_map.json")
    log_dir, store, accountant = _setup(tmp_path, monkeypatch, guid_resolver=guid_resolver)

    unknown_guid = "deadbeef-0000-0000-0000-000000000000"
    _write_event(
        log_dir / "sc_logreader_eventlog_LIVE.jsonl",
        _commodity_buy_event(
            timestamp="2026-06-30T17:00:00+00:00",
            price=800.0,
            quantity=20.0,
            resource_guid=unknown_guid,
        ),
    )

    with caplog.at_level(logging.WARNING):
        imported = asyncio.run(accountant._sync_from_logreader())

    assert imported == 1
    txns = store.query_transactions(limit=10)
    assert len(txns) == 1
    assert txns[0].item_name.startswith("Unknown (")
    assert unknown_guid in guid_resolver.get_unknown_guids()
    assert any("unknown commodity GUID" in r.message for r in caplog.records)


def test_bundle_does_not_supersede_different_missions_component_reward(
    tmp_path, monkeypatch
) -> None:
    """A mission_reward bundle for mission A must not delete a reward_earned
    component transaction for a DIFFERENT mission B that merely falls inside
    the bundle's time window. Cross-mission over-suppression on time alone
    would silently lose B's money.
    """
    log_dir, store, accountant = _setup(tmp_path, monkeypatch)
    log_path = log_dir / "sc_logreader_eventlog_LIVE.jsonl"

    ts = "2026-06-30T19:00:00+00:00"
    _write_event(
        log_path,
        _reward_earned_event(
            timestamp=ts,
            amount="2000",
            mission_id="mission-B",
            mission_name="Bounty B",
            notification_id="notif-B",
        ),
    )

    imported_first = asyncio.run(accountant._sync_from_logreader())
    assert imported_first == 1

    txns_after_first = store.query_transactions(limit=10)
    assert len(txns_after_first) == 1
    assert txns_after_first[0].source_mission_id == "mission-B"

    # A bundle for an UNRELATED mission (A) whose window happens to cover
    # B's timestamp must not touch B's transaction.
    _append_event(
        log_path,
        _mission_reward_event(
            timestamp=ts,
            first_seen=ts,
            last_seen=ts,
            mission_id="mission-A",
            mission_name="Delivery A",
            amount_auec=5000.0,
        ),
    )

    imported_second = asyncio.run(accountant._sync_from_logreader())
    assert imported_second == 1

    txns_after_second = store.query_transactions(limit=10)
    assert len(txns_after_second) == 2

    mission_b_txn = next(
        t for t in txns_after_second if t.source_mission_id == "mission-B"
    )
    assert mission_b_txn.amount == 2000.0
    assert "component_reward" in mission_b_txn.tags

    mission_a_txn = next(
        t for t in txns_after_second if t.source_mission_id == "mission-A"
    )
    assert mission_a_txn.amount == 5000.0

    balance = store.get_balance()
    assert balance.current_balance == 2000.0 + 5000.0


def test_mission_id_less_reward_and_bundle_both_import(tmp_path, monkeypatch) -> None:
    """Rewards with no mission_id never absorb/supersede on time alone.

    This is a deliberate tradeoff: without a positive mission_id match, we
    prefer under-suppression (both rows import, a rare possible double-count)
    over cross-mission over-suppression (silently deleting real money). Both
    the component and the bundle land as separate transactions here.
    """
    log_dir, store, accountant = _setup(tmp_path, monkeypatch)

    ts = "2026-06-30T18:00:00+00:00"
    _write_events(
        log_dir / "sc_logreader_eventlog_LIVE.jsonl",
        [
            _reward_earned_event(
                timestamp=ts,
                amount="1500",
                mission_id="",
                mission_name="",
                notification_id="notif-idless",
            ),
            _mission_reward_event(
                timestamp=ts,
                first_seen=ts,
                last_seen=ts,
                mission_id="",
                mission_name="",
                amount_auec=1500.0,
            ),
        ],
    )

    imported = asyncio.run(accountant._sync_from_logreader())
    assert imported == 2

    txns = store.query_transactions(limit=10)
    assert len(txns) == 2
    assert sorted(t.amount for t in txns) == [1500.0, 1500.0]
    assert all(t.source_mission_id is None for t in txns)


def test_blueprint_events_do_not_crash_when_assets_manager_missing(
    tmp_path, monkeypatch
) -> None:
    """When self._assets is None (asset manager unavailable), blueprint
    registration must be skipped, not crash, and the sync watermark must
    still advance and save.
    """
    log_dir, store, accountant = _setup(tmp_path, monkeypatch)
    accountant._assets = None

    ts1 = "2026-06-30T20:00:00+00:00"
    ts2 = "2026-06-30T20:05:00+00:00"
    _write_events(
        log_dir / "sc_logreader_eventlog_LIVE.jsonl",
        [
            _blueprint_received_event(
                timestamp=ts1, blueprint_name="Cutter Schematic"
            ),
            _mission_reward_event(
                timestamp=ts2,
                first_seen=ts2,
                last_seen=ts2,
                mission_id="mission-5",
                mission_name="Rescue Run",
                amount_auec=1000.0,
                blueprints=["Freelancer Schematic"],
            ),
        ],
    )

    imported = asyncio.run(accountant._sync_from_logreader())
    assert imported == 1  # only the mission_reward money transaction

    blueprints = store.query_assets(asset_type="blueprint", status=None, limit=10)
    assert blueprints == []  # nothing registered without an asset manager

    cursor = store.get_sync_cursor()
    assert cursor["last_ts"] == ts2


def test_recency_resolved_mission_id_from_producer_counts_reward_once(
    tmp_path, monkeypatch
) -> None:
    """Models the fixed SC_LogReader producer behavior directly.

    When a reward_earned component's mission_id is resolved by recent
    contract-complete correlation rather than embedded in the raw
    notification line, SC_LogReader now stamps that SAME resolved mission_id
    on both the component and its mission_reward bundle (see sc_log_reader
    DEVLOG 2026-07-07: reward_earned entries now carry the resolved
    mission_id). With agreement guaranteed by the producer, the accountant's
    mission_id-scoped supersession counts the reward exactly once: the
    component is absorbed and only the bundle's amount lands on the balance.
    This is the scenario the earlier bundle-suppression fixtures already
    exercised incidentally; this test makes it explicit and ties it to the
    producer guarantee.
    """
    log_dir, store, accountant = _setup(tmp_path, monkeypatch)
    log_path = log_dir / "sc_logreader_eventlog_LIVE.jsonl"

    ts = "2026-06-30T21:00:00+00:00"
    _write_events(
        log_path,
        [
            _reward_earned_event(
                timestamp=ts,
                amount="3500",
                mission_id="mission-recency-6",
                mission_name="Legal Claim",
                notification_id="notif-6",
            ),
            _mission_reward_event(
                timestamp=ts,
                first_seen=ts,
                last_seen=ts,
                mission_id="mission-recency-6",
                mission_name="Legal Claim",
                amount_auec=3500.0,
            ),
        ],
    )

    imported = asyncio.run(accountant._sync_from_logreader())
    assert imported == 1

    txns = store.query_transactions(limit=10)
    assert len(txns) == 1
    assert txns[0].category == "mission_reward"
    assert txns[0].amount == 3500.0
    assert txns[0].source_mission_id == "mission-recency-6"
    assert "component_reward" not in txns[0].tags

    balance = store.get_balance()
    assert balance.current_balance == 3500.0