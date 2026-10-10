"""Integration tests for SC_Accountant — cross-module flows.

Uses real AccountantStore(tmp_path) for end-to-end verification.

Author: Mallachi
"""

from __future__ import annotations

import os
import sys

import pytest

_skill_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _skill_dir not in sys.path:
    sys.path.insert(0, _skill_dir)

from assets import AssetManager  # noqa: E402
from factories import (  # noqa: E402
    make_balance,
    make_position,
    make_transaction,
)
from planning import PlanningEngine  # noqa: E402
from statements import (  # noqa: E402
    generate_balance_sheet,
    generate_cash_flow,
    generate_income_statement,
)


@pytest.fixture
def assets(store, format_fn):
    return AssetManager(store=store, format_fn=format_fn)


@pytest.fixture
def planning(store, format_fn):
    return PlanningEngine(store=store, format_fn=format_fn)


# ------------------------------------------------------------------
# Full Asset Lifecycle
# ------------------------------------------------------------------


class TestAssetLifecycle:
    def test_register_earn_sell(self, assets, store, planning):
        """Register ship → record linked transactions → break-even → sell."""
        # 1. Register a ship
        ship, purchase_txn = assets.register_asset(
            asset_type="ship",
            name="Prospector",
            purchase_price=2_000_000,
            location="Lorville",
        )
        assert ship.status == "active"

        # 2. Record linked revenue and cost transactions
        revenue_txn = make_transaction(
            id="rev1",
            category="commodity_sale",
            transaction_type="income",
            amount=100_000,
            linked_asset_id=ship.id,
            activity="trading",
            days_ago=10,
        )
        cost_txn = make_transaction(
            id="cost1",
            category="fuel",
            transaction_type="expense",
            amount=5_000,
            linked_asset_id=ship.id,
            days_ago=5,
        )
        store.append_transaction(revenue_txn)
        store.append_transaction(cost_txn)

        # 3. Verify break-even
        linked_txns = store.query_transactions(
            linked_asset_id=ship.id,
            limit=1000,
        )
        be = planning.break_even_analysis(ship, linked_txns)
        assert be["net_profit_to_date"] == 95_000.0
        assert be["already_paid_off"] is False

        # 4. Sell the ship
        sold, sale_txn, msg = assets.sell_asset(ship.id, sell_price=2_200_000)
        assert sold.status == "sold"
        assert "profit" in msg.lower()

    def test_purchase_creates_capex_in_income_statement(self, assets, store):
        """Registering an asset creates a CAPEX transaction visible in reports."""
        assets.register_asset(
            asset_type="ship",
            name="Cutlass Black",
            purchase_price=1_500_000,
        )

        txns = store.query_transactions(limit=1000)
        stmt = generate_income_statement(txns)

        assert stmt["capex"] == 1_500_000.0
        assert stmt["revenue"] == 0.0
        assert stmt["net_operating_profit"] == 0.0


# ------------------------------------------------------------------
# Activity ROI Accuracy
# ------------------------------------------------------------------


class TestActivityRoiAccuracy:
    def test_multiple_activities_in_income_statement(self, store):
        """Per-activity margins in income statement match individual totals."""
        txns = [
            # Trading: 50k revenue, 30k cost
            make_transaction(
                id="t1",
                category="commodity_sale",
                transaction_type="income",
                amount=50_000,
                activity="trading",
            ),
            make_transaction(
                id="t2",
                category="commodity_purchase",
                transaction_type="expense",
                amount=30_000,
                activity="trading",
            ),
            # Bounty: 15k revenue, 0 cost
            make_transaction(
                id="t5",
                category="bounty_reward",
                transaction_type="income",
                amount=15_000,
                activity="bounty_hunting",
            ),
        ]

        stmt = generate_income_statement(txns)
        margins = stmt["activity_margins"]
        activity_map = {m["activity"]: m for m in margins}

        assert activity_map["trading"]["revenue"] == 50_000.0
        assert activity_map["trading"]["costs"] == 30_000.0
        assert activity_map["trading"]["margin"] == 20_000.0

        assert activity_map["bounty_hunting"]["revenue"] == 15_000.0
        assert activity_map["bounty_hunting"]["costs"] == 0.0
        assert activity_map["bounty_hunting"]["margin"] == 15_000.0


# ------------------------------------------------------------------
# Balance Sheet Completeness
# ------------------------------------------------------------------


class TestBalanceSheetCompleteness:
    def test_all_components(self, assets, store):
        """Balance sheet includes all asset types."""
        # Cash
        store.save_balance(make_balance(current_balance=200_000))

        # Ships
        assets.register_asset(
            asset_type="ship",
            name="Prospector",
            purchase_price=2_000_000,
        )
        assets.register_asset(
            asset_type="component",
            name="Lancet MH1",
            purchase_price=80_000,
        )

        # Open positions (cargo)
        position = make_position(
            id="p1",
            commodity_name="Laranite",
            quantity=100,
            buy_total=3000,
        )
        position.current_market_price = 35.0
        store.save_position(position)

        # Generate balance sheet
        all_assets = store.query_assets(status="active", limit=500)
        positions = store.query_positions(status="open", limit=500)
        balance = store.get_balance()

        bs = generate_balance_sheet(
            balance=balance,
            assets=all_assets,
            open_positions=positions,
        )

        assert bs["assets"]["cash"] == 200_000.0
        assert bs["assets"]["ships"] == 2_000_000.0
        assert bs["assets"]["ships_count"] == 1
        assert bs["assets"]["components"] == 80_000.0
        assert bs["assets"]["cargo"] == 3_500.0

        expected_total_assets = 200_000 + 2_000_000 + 80_000 + 3_500
        assert bs["assets"]["total"] == expected_total_assets
        assert bs["equity"]["net_worth"] == expected_total_assets
