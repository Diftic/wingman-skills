"""Tests for SC_Accountant three-statement report engine.

Author: Mallachi
"""

from __future__ import annotations

import os
import sys


_skill_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _skill_dir not in sys.path:
    sys.path.insert(0, _skill_dir)

from factories import (  # noqa: E402
    make_asset,
    make_balance,
    make_diverse_transactions,
    make_position,
    make_transaction,
)
from statements import (  # noqa: E402
    generate_asset_pnl,
    generate_balance_sheet,
    generate_cash_flow,
    generate_income_statement,
)


# ------------------------------------------------------------------
# Income Statement
# ------------------------------------------------------------------


class TestIncomeStatement:
    def test_diverse_transactions(self):
        txns = make_diverse_transactions()
        stmt = generate_income_statement(txns, "test_period")

        assert stmt["period"] == "test_period"
        assert stmt["transaction_count"] == 8

        # Revenue = 50k + 8k + 15k + 10k = 83k
        assert stmt["revenue"] == 83_000.0

        # COGS = 30k (commodity_purchase)
        assert stmt["cogs"] == 30_000.0

        # Gross margin = 83k - 30k = 53k
        assert stmt["gross_margin"] == 53_000.0

        # OpEx = 1.5k (fuel) + 3k (repairs) = 4.5k
        assert stmt["opex"] == 4_500.0

        # Net operating profit = 53k - 4.5k = 48.5k
        assert stmt["net_operating_profit"] == 48_500.0

        # CAPEX = 2.1M (ship_purchase)
        assert stmt["capex"] == 2_100_000.0

    def test_activity_margins_present(self):
        txns = make_diverse_transactions()
        stmt = generate_income_statement(txns)
        margins = stmt["activity_margins"]

        activity_names = [m["activity"] for m in margins]
        assert "trading" in activity_names
        assert "bounty_hunting" in activity_names
        assert "missions" in activity_names

    def test_trading_activity_margin(self):
        txns = make_diverse_transactions()
        stmt = generate_income_statement(txns)
        margins = stmt["activity_margins"]

        trading = next(m for m in margins if m["activity"] == "trading")
        # Revenue: 50k + 8k = 58k, Costs: 30k
        assert trading["revenue"] == 58_000.0
        assert trading["costs"] == 30_000.0
        assert trading["margin"] == 28_000.0

    def test_empty_transactions(self):
        stmt = generate_income_statement([])
        assert stmt["revenue"] == 0.0
        assert stmt["cogs"] == 0.0
        assert stmt["gross_margin"] == 0.0
        assert stmt["opex"] == 0.0
        assert stmt["net_operating_profit"] == 0.0
        assert stmt["capex"] == 0.0
        assert stmt["transaction_count"] == 0
        assert stmt["gross_margin_pct"] == 0.0
        assert stmt["net_margin_pct"] == 0.0
        assert stmt["activity_margins"] == []

    def test_single_revenue_transaction(self):
        txns = [
            make_transaction(
                category="bounty_reward", transaction_type="income", amount=5000.0
            )
        ]
        stmt = generate_income_statement(txns)
        assert stmt["revenue"] == 5000.0
        assert stmt["cogs"] == 0.0
        assert stmt["gross_margin"] == 5000.0
        assert stmt["gross_margin_pct"] == 100.0

    def test_category_breakdowns_sorted_descending(self):
        txns = [
            make_transaction(
                id="t1",
                category="commodity_sale",
                transaction_type="income",
                amount=1000.0,
            ),
            make_transaction(
                id="t2",
                category="bounty_reward",
                transaction_type="income",
                amount=5000.0,
            ),
        ]
        stmt = generate_income_statement(txns)
        cats = list(stmt["revenue_by_category"].values())
        assert cats == sorted(cats, reverse=True)

    def test_margin_sorted_descending(self):
        txns = make_diverse_transactions()
        stmt = generate_income_statement(txns)
        margins = [m["margin"] for m in stmt["activity_margins"]]
        assert margins == sorted(margins, reverse=True)


# ------------------------------------------------------------------
# Balance Sheet
# ------------------------------------------------------------------


class TestBalanceSheet:
    def test_cash_only(self):
        bs = generate_balance_sheet(
            balance=make_balance(current_balance=100_000.0),
            assets=[],
            open_positions=[],
        )
        assert bs["assets"]["cash"] == 100_000.0
        assert bs["assets"]["ships"] == 0.0
        assert bs["assets"]["total"] == 100_000.0
        assert bs["equity"]["net_worth"] == 100_000.0

    def test_ships_and_components(self):
        assets = [
            make_asset(
                id="s1", asset_type="ship", name="Prospector", purchase_price=2_000_000
            ),
            make_asset(
                id="c1",
                asset_type="component",
                name="Lancet MH1",
                purchase_price=80_000,
            ),
            make_asset(
                id="v1", asset_type="vehicle", name="Cyclone", purchase_price=50_000
            ),
        ]
        bs = generate_balance_sheet(
            balance=make_balance(current_balance=100_000),
            assets=assets,
            open_positions=[],
        )
        assert bs["assets"]["ships"] == 2_000_000.0
        assert bs["assets"]["ships_count"] == 1
        assert bs["assets"]["components"] == 80_000.0
        assert bs["assets"]["vehicles"] == 50_000.0
        assert bs["assets"]["total"] == 2_230_000.0

    def test_cargo_from_positions(self):
        positions = [
            make_position(
                id="p1",
                commodity_name="Laranite",
                quantity=100.0,
                buy_total=3000.0,
            ),
        ]
        # Position cargo value uses current_market_price * quantity
        # Default current_market_price=0 in our factory, so set it explicitly
        positions[0].current_market_price = 35.0

        bs = generate_balance_sheet(
            balance=make_balance(current_balance=0),
            assets=[],
            open_positions=positions,
        )
        assert bs["assets"]["cargo"] == 3500.0  # 35 * 100

    def test_sold_assets_excluded(self):
        assets = [
            make_asset(id="s1", status="active", purchase_price=1_000_000),
            make_asset(id="s2", status="sold", purchase_price=500_000),
        ]
        bs = generate_balance_sheet(
            balance=make_balance(current_balance=0),
            assets=assets,
            open_positions=[],
        )
        assert bs["assets"]["ships"] == 1_000_000.0  # Only active
        assert bs["assets"]["ships_count"] == 1

    def test_empty_everything(self):
        bs = generate_balance_sheet(
            balance=make_balance(current_balance=0),
            assets=[],
            open_positions=[],
        )
        assert bs["assets"]["total"] == 0.0
        assert bs["equity"]["net_worth"] == 0.0


# ------------------------------------------------------------------
# Cash Flow
# ------------------------------------------------------------------


class TestCashFlow:
    def test_diverse_transactions(self):
        txns = make_diverse_transactions()
        cf = generate_cash_flow(txns, "test")

        assert cf["period"] == "test"

        # Operating inflows = all revenue = 83k
        assert cf["operating"]["inflows"] == 83_000.0

        # Operating outflows = COGS (30k) + OpEx (4.5k) = 34.5k
        assert cf["operating"]["outflows"] == 34_500.0

        # Operating net = 83k - 34.5k = 48.5k
        assert cf["operating"]["net"] == 48_500.0

        # Investing outflows = CAPEX = 2.1M
        assert cf["investing"]["outflows"] == 2_100_000.0

        # Investing inflows = 0 (no asset sales)
        assert cf["investing"]["inflows"] == 0.0

        # Net cash change = 48.5k - 2.1M = -2,051,500
        assert cf["net_cash_change"] == -2_051_500.0

    def test_empty_transactions(self):
        cf = generate_cash_flow([])
        assert cf["operating"]["inflows"] == 0.0
        assert cf["operating"]["outflows"] == 0.0
        assert cf["operating"]["net"] == 0.0
        assert cf["investing"]["outflows"] == 0.0
        assert cf["investing"]["inflows"] == 0.0
        assert cf["net_cash_change"] == 0.0

    def test_revenue_only(self):
        txns = [
            make_transaction(
                category="mission_reward", transaction_type="income", amount=5000
            ),
        ]
        cf = generate_cash_flow(txns)
        assert cf["operating"]["inflows"] == 5000.0
        assert cf["operating"]["outflows"] == 0.0
        assert cf["operating"]["net"] == 5000.0
        assert cf["net_cash_change"] == 5000.0


# ------------------------------------------------------------------
# Asset P&L
# ------------------------------------------------------------------


class TestAssetPnl:
    def test_profitable_asset(self):
        asset = make_asset(id="ship1", purchase_price=500_000)
        txns = [
            make_transaction(
                id="t1",
                category="commodity_sale",
                transaction_type="income",
                amount=100_000,
                linked_asset_id="ship1",
            ),
            make_transaction(
                id="t2",
                category="fuel",
                transaction_type="expense",
                amount=5_000,
                linked_asset_id="ship1",
            ),
        ]
        pnl = generate_asset_pnl(asset, txns)
        assert pnl["asset_id"] == "ship1"
        assert pnl["revenue"] == 100_000.0
        assert pnl["costs"] == 5_000.0
        assert pnl["net_profit"] == 95_000.0
        assert pnl["margin_pct"] == 95.0
        assert pnl["roi_pct"] == 19.0  # 95k / 500k * 100
        assert pnl["transaction_count"] == 2

    def test_no_transactions(self):
        asset = make_asset(id="ship1", purchase_price=1_000_000)
        pnl = generate_asset_pnl(asset, [])
        assert pnl["revenue"] == 0.0
        assert pnl["costs"] == 0.0
        assert pnl["net_profit"] == 0.0
        assert pnl["margin_pct"] == 0.0
        assert pnl["roi_pct"] == 0.0
        assert pnl["transaction_count"] == 0

    def test_zero_purchase_price(self):
        """Asset with zero purchase price shouldn't divide by zero."""
        asset = make_asset(id="free", purchase_price=0.0)
        txns = [
            make_transaction(
                id="t1",
                category="mission_reward",
                transaction_type="income",
                amount=10_000,
            ),
        ]
        pnl = generate_asset_pnl(asset, txns)
        assert pnl["roi_pct"] == 0.0  # Protected from division by zero
