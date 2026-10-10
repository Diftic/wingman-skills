"""Tests for SC_Accountant persistence layer (AccountantStore).

Covers: transactions (JSONL), trade orders, budgets, trading sessions,
account balance, sync cursor, opportunities, positions, hauls, and assets.

Author: Mallachi
"""

from __future__ import annotations

import json
import os
import sys

import pytest

_skill_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _skill_dir not in sys.path:
    sys.path.insert(0, _skill_dir)

from factories import _ts, make_asset, make_position, make_transaction  # noqa: E402
from models import (  # noqa: E402
    AccountBalance,
    Budget,
    Haul,
    Opportunity,
    TradeOrder,
    TradingSession,
)
from store import AccountantStore  # noqa: E402


# ---------------------------------------------------------------------------
# Inline factories for models not covered in factories.py
# ---------------------------------------------------------------------------


def make_trade_order(
    *,
    id: str = "o1",
    status: str = "open",
    order_type: str = "buy",
    item_name: str = "Laranite",
    quantity: float = 100.0,
) -> TradeOrder:
    return TradeOrder(
        id=id,
        created_at=_ts(),
        status=status,
        order_type=order_type,
        item_name=item_name,
        quantity=quantity,
    )


def make_budget(
    *,
    id: str = "b1",
    category: str = "fuel",
    period_type: str = "monthly",
    allocated_amount: float = 50_000.0,
) -> Budget:
    return Budget(
        id=id,
        category=category,
        period_type=period_type,
        period_start="2026-04-01",
        period_end="2026-04-30",
        allocated_amount=allocated_amount,
    )


def make_session(
    *,
    id: str = "s1",
    starting_balance: float = 500_000.0,
    ended_at: str | None = None,
) -> TradingSession:
    return TradingSession(
        id=id,
        started_at=_ts(),
        starting_balance=starting_balance,
        ended_at=ended_at,
    )


def make_opportunity(
    *,
    id: str = "opp1",
    status: str = "available",
    commodity_name: str = "Laranite",
    score: int = 80,
    estimated_profit: float = 50_000.0,
) -> Opportunity:
    return Opportunity(
        id=id,
        created_at=_ts(),
        status=status,
        commodity_name=commodity_name,
        commodity_id=1,
        commodity_code="LAR",
        buy_terminal="TDD Lorville",
        buy_terminal_id=10,
        buy_location="Hurston",
        buy_price=25.0,
        sell_terminal="TDD Area18",
        sell_terminal_id=20,
        sell_location="ArcCorp",
        sell_price=35.0,
        margin_per_scu=10.0,
        available_scu=500.0,
        estimated_profit=estimated_profit,
        score=score,
    )


def make_haul(
    *,
    id: str = "h1",
    status: str = "in_transit",
    origin: str = "Lorville",
    destination: str = "Area18",
) -> Haul:
    return Haul(
        id=id,
        started_at=_ts(),
        status=status,
        origin=origin,
        destination=destination,
        cargo_description="Laranite 100 SCU",
    )


# ---------------------------------------------------------------------------
# Transactions
# ---------------------------------------------------------------------------


class TestTransactionAppendAndQuery:
    def test_empty_store_returns_no_transactions(self, store):
        assert store.query_transactions() == []

    def test_append_and_query_all(self, store):
        txn = make_transaction(id="t1")
        store.append_transaction(txn)
        results = store.query_transactions()
        assert len(results) == 1
        assert results[0].id == "t1"

    def test_query_returns_most_recent_first(self, store):
        store.append_transaction(make_transaction(id="t_old", days_ago=5))
        store.append_transaction(make_transaction(id="t_new", days_ago=0))
        results = store.query_transactions()
        assert results[0].id == "t_new"
        assert results[1].id == "t_old"

    def test_query_filter_by_category(self, store):
        store.append_transaction(make_transaction(id="t1", category="commodity_sale"))
        store.append_transaction(make_transaction(id="t2", category="fuel"))
        results = store.query_transactions(category="fuel")
        assert len(results) == 1
        assert results[0].id == "t2"

    def test_query_filter_by_location(self, store):
        store.append_transaction(make_transaction(id="t1", location="Lorville"))
        store.append_transaction(make_transaction(id="t2", location="Area18"))
        results = store.query_transactions(location="lorville")
        assert len(results) == 1
        assert results[0].id == "t1"

    def test_query_filter_by_source(self, store):
        store.append_transaction(make_transaction(id="t1", source="auto_log"))
        store.append_transaction(make_transaction(id="t2", source="manual"))
        results = store.query_transactions(source="auto_log")
        assert len(results) == 1
        assert results[0].id == "t1"

    def test_query_filter_by_session_id(self, store):
        store.append_transaction(make_transaction(id="t1", session_id="sess-1"))
        store.append_transaction(make_transaction(id="t2", session_id=None))
        results = store.query_transactions(session_id="sess-1")
        assert len(results) == 1
        assert results[0].id == "t1"

    def test_query_filter_by_linked_asset_id(self, store):
        store.append_transaction(make_transaction(id="t1", linked_asset_id="asset-99"))
        store.append_transaction(make_transaction(id="t2", linked_asset_id=None))
        results = store.query_transactions(linked_asset_id="asset-99")
        assert len(results) == 1
        assert results[0].id == "t1"

    def test_query_filter_by_tags(self, store):
        store.append_transaction(make_transaction(id="t1", tags=["hauling", "session"]))
        store.append_transaction(make_transaction(id="t2", tags=["bounty"]))
        results = store.query_transactions(tags=["hauling"])
        assert len(results) == 1
        assert results[0].id == "t1"

    def test_query_limit(self, store):
        for i in range(5):
            store.append_transaction(make_transaction(id=f"t{i}"))
        results = store.query_transactions(limit=3)
        assert len(results) == 3

    def test_malformed_jsonl_line_is_skipped(self, store, tmp_path):
        # Write one valid and one malformed line
        txn_path = tmp_path / "transactions.jsonl"
        with open(txn_path, "w") as f:
            f.write("{not valid json}\n")
            f.write(json.dumps(make_transaction(id="t_good").to_dict()) + "\n")
        results = store.query_transactions()
        assert len(results) == 1
        assert results[0].id == "t_good"


class TestTransactionUpdateAndDelete:
    def test_update_transaction_changes_field(self, store):
        txn = make_transaction(id="t1", description="original")
        store.append_transaction(txn)
        updated = store.update_transaction("t1", {"description": "updated"})
        assert updated is not None
        assert updated.description == "updated"
        # Persisted
        results = store.query_transactions()
        assert results[0].description == "updated"

    def test_update_transaction_not_found_returns_none(self, store):
        result = store.update_transaction("missing", {"description": "x"})
        assert result is None

    def test_delete_transaction_removes_it(self, store):
        store.append_transaction(make_transaction(id="t1"))
        store.append_transaction(make_transaction(id="t2"))
        deleted = store.delete_transaction("t1")
        assert deleted is not None
        assert deleted.id == "t1"
        remaining = store.query_transactions()
        assert all(t.id != "t1" for t in remaining)

    def test_delete_transaction_not_found_returns_none(self, store):
        result = store.delete_transaction("missing")
        assert result is None


# ---------------------------------------------------------------------------
# Trade Orders
# ---------------------------------------------------------------------------


class TestTradeOrders:
    def test_save_and_query_new_order(self, store):
        store.save_trade_order(make_trade_order(id="o1", status="open"))
        results = store.query_trade_orders()
        assert len(results) == 1
        assert results[0].id == "o1"

    def test_save_updates_existing_order(self, store):
        order = make_trade_order(id="o1", status="open")
        store.save_trade_order(order)
        order.status = "completed"
        store.save_trade_order(order)
        results = store.query_trade_orders()
        assert len(results) == 1
        assert results[0].status == "completed"

    def test_query_filter_by_status(self, store):
        store.save_trade_order(make_trade_order(id="o1", status="open"))
        store.save_trade_order(make_trade_order(id="o2", status="cancelled"))
        results = store.query_trade_orders(status="open")
        assert len(results) == 1
        assert results[0].id == "o1"

    def test_get_trade_order_found(self, store):
        store.save_trade_order(make_trade_order(id="o1"))
        result = store.get_trade_order("o1")
        assert result is not None
        assert result.id == "o1"

    def test_get_trade_order_not_found(self, store):
        assert store.get_trade_order("missing") is None


# ---------------------------------------------------------------------------
# Budgets
# ---------------------------------------------------------------------------


class TestBudgets:
    def test_save_and_query_budget(self, store):
        store.save_budget(make_budget(id="b1", category="fuel"))
        results = store.get_budgets()
        assert len(results) == 1
        assert results[0].id == "b1"

    def test_save_updates_existing_budget(self, store):
        budget = make_budget(id="b1", allocated_amount=50_000.0)
        store.save_budget(budget)
        budget.allocated_amount = 75_000.0
        store.save_budget(budget)
        results = store.get_budgets()
        assert len(results) == 1
        assert results[0].allocated_amount == 75_000.0

    def test_query_filter_by_period_type(self, store):
        store.save_budget(make_budget(id="b1", period_type="monthly"))
        store.save_budget(make_budget(id="b2", period_type="weekly"))
        results = store.get_budgets(period_type="monthly")
        assert len(results) == 1
        assert results[0].id == "b1"

    def test_query_filter_by_category(self, store):
        store.save_budget(make_budget(id="b1", category="fuel"))
        store.save_budget(make_budget(id="b2", category="repairs"))
        results = store.get_budgets(category="repairs")
        assert len(results) == 1
        assert results[0].id == "b2"

    def test_delete_budget(self, store):
        store.save_budget(make_budget(id="b1"))
        deleted = store.delete_budget("b1")
        assert deleted is True
        assert store.get_budgets() == []

    def test_delete_budget_not_found(self, store):
        assert store.delete_budget("missing") is False


# ---------------------------------------------------------------------------
# Trading Sessions
# ---------------------------------------------------------------------------


class TestTradingSessions:
    def test_save_and_get_session(self, store):
        store.save_session(make_session(id="s1"))
        result = store.get_session("s1")
        assert result is not None
        assert result.id == "s1"

    def test_get_session_not_found(self, store):
        assert store.get_session("missing") is None

    def test_get_active_session_returns_open_session(self, store):
        store.save_session(make_session(id="s1", ended_at=None))
        result = store.get_active_session()
        assert result is not None
        assert result.id == "s1"

    def test_get_active_session_none_when_all_closed(self, store):
        store.save_session(make_session(id="s1", ended_at="2026-04-01T10:00:00"))
        assert store.get_active_session() is None

    def test_get_active_session_empty_store(self, store):
        assert store.get_active_session() is None

    def test_save_updates_existing_session(self, store):
        session = make_session(id="s1", ended_at=None)
        store.save_session(session)
        session.ended_at = "2026-04-12T15:00:00"
        store.save_session(session)
        result = store.get_session("s1")
        assert result.ended_at == "2026-04-12T15:00:00"
        assert store.get_active_session() is None


# ---------------------------------------------------------------------------
# Account Balance
# ---------------------------------------------------------------------------


class TestAccountBalance:
    def test_get_balance_default_when_missing(self, store):
        balance = store.get_balance()
        assert balance.current_balance == 0.0

    def test_save_and_get_balance(self, store):
        store.save_balance(AccountBalance(current_balance=1_000_000.0, last_updated=_ts()))
        balance = store.get_balance()
        assert balance.current_balance == 1_000_000.0

    def test_save_overwrites_previous_balance(self, store):
        store.save_balance(AccountBalance(current_balance=500_000.0))
        store.save_balance(AccountBalance(current_balance=750_000.0))
        assert store.get_balance().current_balance == 750_000.0


# ---------------------------------------------------------------------------
# Sync Cursor
# ---------------------------------------------------------------------------


class TestSyncCursor:
    def test_get_cursor_default_when_missing(self, store):
        cursor = store.get_sync_cursor()
        assert cursor == {"last_ts": "", "count_at_ts": 0}

    def test_save_and_get_cursor(self, store):
        store.save_sync_cursor("2026-04-12T10:00:00", 3)
        cursor = store.get_sync_cursor()
        assert cursor["last_ts"] == "2026-04-12T10:00:00"
        assert cursor["count_at_ts"] == 3

    def test_cursor_migration_from_old_line_format(self, store, tmp_path):
        # Simulate old format with "last_line" key
        cursor_path = tmp_path / "sync_cursor.json"
        with open(cursor_path, "w") as f:
            json.dump({"last_line": 42}, f)
        cursor = store.get_sync_cursor()
        assert cursor == {"last_ts": "", "count_at_ts": 0}


# ---------------------------------------------------------------------------
# Opportunities
# ---------------------------------------------------------------------------


class TestOpportunities:
    def test_save_and_get_opportunity(self, store):
        store.save_opportunity(make_opportunity(id="opp1"))
        result = store.get_opportunity("opp1")
        assert result is not None
        assert result.id == "opp1"

    def test_get_opportunity_not_found(self, store):
        assert store.get_opportunity("missing") is None

    def test_save_updates_existing_opportunity(self, store):
        opp = make_opportunity(id="opp1", status="available")
        store.save_opportunity(opp)
        opp.status = "accepted"
        store.save_opportunity(opp)
        results = store.query_opportunities()
        assert len(results) == 1
        assert results[0].status == "accepted"

    def test_bulk_save_opportunities(self, store):
        opps = [
            make_opportunity(id="opp1", commodity_name="Laranite"),
            make_opportunity(id="opp2", commodity_name="Agricium"),
        ]
        store.bulk_save_opportunities(opps)
        assert len(store.query_opportunities()) == 2

    def test_bulk_save_updates_existing(self, store):
        store.save_opportunity(make_opportunity(id="opp1", score=50))
        updated = make_opportunity(id="opp1", score=90)
        store.bulk_save_opportunities([updated])
        result = store.get_opportunity("opp1")
        assert result.score == 90

    def test_query_filter_by_status(self, store):
        store.save_opportunity(make_opportunity(id="opp1", status="available"))
        store.save_opportunity(make_opportunity(id="opp2", status="expired"))
        results = store.query_opportunities(status="available")
        assert len(results) == 1
        assert results[0].id == "opp1"

    def test_query_filter_by_commodity_name(self, store):
        store.save_opportunity(make_opportunity(id="opp1", commodity_name="Laranite"))
        store.save_opportunity(make_opportunity(id="opp2", commodity_name="Agricium"))
        results = store.query_opportunities(commodity_name="laranite")
        assert len(results) == 1
        assert results[0].id == "opp1"

    def test_query_available_sorted_by_score_desc(self, store):
        store.save_opportunity(make_opportunity(id="opp1", score=40))
        store.save_opportunity(make_opportunity(id="opp2", score=90))
        store.save_opportunity(make_opportunity(id="opp3", score=60))
        results = store.query_opportunities(status="available")
        assert results[0].id == "opp2"
        assert results[1].id == "opp3"

    def test_delete_expired_opportunities(self, store):
        old_ts = "2026-01-01T00:00:00"
        new_ts = _ts()
        expired_old = make_opportunity(id="opp1", status="expired")
        expired_old.created_at = old_ts
        expired_new = make_opportunity(id="opp2", status="expired")
        expired_new.created_at = new_ts
        active = make_opportunity(id="opp3", status="available")
        active.created_at = old_ts
        store.save_opportunity(expired_old)
        store.save_opportunity(expired_new)
        store.save_opportunity(active)

        removed = store.delete_expired_opportunities("2026-02-01T00:00:00")
        assert removed == 1
        remaining = store.query_opportunities()
        ids = {o.id for o in remaining}
        assert "opp1" not in ids
        assert "opp2" in ids
        assert "opp3" in ids


# ---------------------------------------------------------------------------
# Positions
# ---------------------------------------------------------------------------


class TestPositions:
    def test_save_and_get_position(self, store):
        store.save_position(make_position(id="p1"))
        result = store.get_position("p1")
        assert result is not None
        assert result.id == "p1"

    def test_get_position_not_found(self, store):
        assert store.get_position("missing") is None

    def test_save_updates_existing_position(self, store):
        pos = make_position(id="p1", status="open")
        store.save_position(pos)
        pos.status = "closed"
        store.save_position(pos)
        results = store.query_positions()
        assert len(results) == 1
        assert results[0].status == "closed"

    def test_query_filter_by_status(self, store):
        store.save_position(make_position(id="p1", status="open"))
        store.save_position(make_position(id="p2", status="closed"))
        results = store.query_positions(status="open")
        assert len(results) == 1
        assert results[0].id == "p1"

    def test_query_filter_by_commodity_name(self, store):
        store.save_position(make_position(id="p1", commodity_name="Laranite"))
        store.save_position(make_position(id="p2", commodity_name="Agricium"))
        results = store.query_positions(commodity_name="laranite")
        assert len(results) == 1
        assert results[0].id == "p1"


# ---------------------------------------------------------------------------
# Hauls
# ---------------------------------------------------------------------------


class TestHauls:
    def test_save_and_get_haul(self, store):
        store.save_haul(make_haul(id="h1"))
        result = store.get_haul("h1")
        assert result is not None
        assert result.id == "h1"

    def test_get_haul_not_found(self, store):
        assert store.get_haul("missing") is None

    def test_save_updates_existing_haul(self, store):
        haul = make_haul(id="h1", status="in_transit")
        store.save_haul(haul)
        haul.status = "delivered"
        store.save_haul(haul)
        results = store.query_hauls()
        assert len(results) == 1
        assert results[0].status == "delivered"

    def test_query_filter_by_status(self, store):
        store.save_haul(make_haul(id="h1", status="in_transit"))
        store.save_haul(make_haul(id="h2", status="delivered"))
        results = store.query_hauls(status="in_transit")
        assert len(results) == 1
        assert results[0].id == "h1"


# ---------------------------------------------------------------------------
# Assets
# ---------------------------------------------------------------------------


class TestAssets:
    def test_save_and_get_asset(self, store):
        store.save_asset(make_asset(id="a1"))
        result = store.get_asset("a1")
        assert result is not None
        assert result.id == "a1"

    def test_get_asset_not_found(self, store):
        assert store.get_asset("missing") is None

    def test_save_updates_existing_asset(self, store):
        asset = make_asset(id="a1", status="active")
        store.save_asset(asset)
        asset.status = "sold"
        store.save_asset(asset)
        results = store.query_assets()
        assert len(results) == 1
        assert results[0].status == "sold"

    def test_query_filter_by_type(self, store):
        store.save_asset(make_asset(id="a1", asset_type="ship"))
        store.save_asset(make_asset(id="a2", asset_type="component"))
        results = store.query_assets(asset_type="ship")
        assert len(results) == 1
        assert results[0].id == "a1"

    def test_query_filter_by_status(self, store):
        store.save_asset(make_asset(id="a1", status="active"))
        store.save_asset(make_asset(id="a2", status="sold"))
        results = store.query_assets(status="active")
        assert len(results) == 1
        assert results[0].id == "a1"

    def test_query_filter_by_parent_asset_id(self, store):
        store.save_asset(make_asset(id="a1", parent_asset_id=None))
        store.save_asset(make_asset(id="a2", parent_asset_id="a1"))
        results = store.query_assets(parent_asset_id="a1")
        assert len(results) == 1
        assert results[0].id == "a2"

    def test_delete_asset(self, store):
        store.save_asset(make_asset(id="a1"))
        deleted = store.delete_asset("a1")
        assert deleted is not None
        assert deleted.id == "a1"
        assert store.get_asset("a1") is None

    def test_delete_asset_not_found(self, store):
        assert store.delete_asset("missing") is None


# ---------------------------------------------------------------------------
# Persistence — data survives store reload
# ---------------------------------------------------------------------------


class TestPersistence:
    def test_transactions_persist_across_reload(self, tmp_path):
        store1 = AccountantStore(tmp_path)
        store1.append_transaction(make_transaction(id="t1"))
        store2 = AccountantStore(tmp_path)
        results = store2.query_transactions()
        assert len(results) == 1
        assert results[0].id == "t1"

    def test_assets_persist_across_reload(self, tmp_path):
        store1 = AccountantStore(tmp_path)
        store1.save_asset(make_asset(id="a1", name="Prospector"))
        store2 = AccountantStore(tmp_path)
        result = store2.get_asset("a1")
        assert result is not None
        assert result.name == "Prospector"

    def test_balance_persists_across_reload(self, tmp_path):
        store1 = AccountantStore(tmp_path)
        store1.save_balance(AccountBalance(current_balance=1_234_567.0))
        store2 = AccountantStore(tmp_path)
        assert store2.get_balance().current_balance == 1_234_567.0

    def test_base_dir_created_on_init(self, tmp_path):
        new_dir = tmp_path / "nested" / "store"
        AccountantStore(new_dir)
        assert new_dir.exists()
