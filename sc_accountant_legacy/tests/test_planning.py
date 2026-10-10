"""Tests for SC_Accountant planning & forecasting engine.

Author: Mallachi
"""

from __future__ import annotations

import os
import sys

import pytest

_skill_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _skill_dir not in sys.path:
    sys.path.insert(0, _skill_dir)

from factories import make_asset, make_transaction  # noqa: E402
from planning import PlanningEngine  # noqa: E402


@pytest.fixture
def engine(store, format_fn):
    return PlanningEngine(store=store, format_fn=format_fn)


# ------------------------------------------------------------------
# Break-Even Analysis
# ------------------------------------------------------------------


class TestBreakEven:
    def test_profitable_asset(self, engine):
        asset = make_asset(id="s1", purchase_price=100_000)
        txns = [
            make_transaction(
                id="t1",
                category="commodity_sale",
                transaction_type="income",
                amount=60_000,
                days_ago=10,
            ),
            make_transaction(
                id="t2",
                category="fuel",
                transaction_type="expense",
                amount=5_000,
                days_ago=5,
            ),
        ]
        result = engine.break_even_analysis(asset, txns)

        assert result["asset_name"] == "Prospector"
        assert result["purchase_price"] == 100_000.0
        assert result["total_revenue"] == 60_000.0
        assert result["total_costs"] == 5_000.0
        assert result["net_profit_to_date"] == 55_000.0
        assert result["remaining_to_break_even"] == 45_000.0
        assert result["already_paid_off"] is False
        assert result["avg_daily_profit"] > 0
        assert result["est_days_to_break_even"] is not None
        assert result["est_break_even_date"] is not None

    def test_already_paid_off(self, engine):
        asset = make_asset(id="s1", purchase_price=50_000)
        txns = [
            make_transaction(
                id="t1",
                category="commodity_sale",
                transaction_type="income",
                amount=80_000,
                days_ago=5,
            ),
        ]
        result = engine.break_even_analysis(asset, txns)
        assert result["already_paid_off"] is True
        assert result["remaining_to_break_even"] == 0.0
        assert result["roi_pct"] == 160.0  # (80k - 0) / 50k * 100 (no costs)

    def test_no_transactions(self, engine):
        asset = make_asset(id="s1", purchase_price=100_000)
        result = engine.break_even_analysis(asset, [])
        assert result["net_profit_to_date"] == 0.0
        assert result["avg_daily_profit"] == 0.0
        assert result["est_days_to_break_even"] is None
        assert result["est_break_even_date"] is None
        assert result["already_paid_off"] is False

    def test_negative_profit(self, engine):
        """When costs exceed revenue, no break-even estimate."""
        asset = make_asset(id="s1", purchase_price=100_000)
        txns = [
            make_transaction(
                id="t1",
                category="fuel",
                transaction_type="expense",
                amount=10_000,
                days_ago=5,
            ),
        ]
        result = engine.break_even_analysis(asset, txns)
        assert result["net_profit_to_date"] == -10_000.0
        assert result["est_days_to_break_even"] is None

    def test_single_transaction(self, engine):
        """Single transaction → days_span clamped to 1."""
        asset = make_asset(id="s1", purchase_price=10_000)
        txns = [
            make_transaction(
                id="t1",
                category="commodity_sale",
                transaction_type="income",
                amount=5_000,
                days_ago=0,
            ),
        ]
        result = engine.break_even_analysis(asset, txns)
        assert result["avg_daily_profit"] == 5_000.0  # 5k / max(0, 1) = 5k


# ------------------------------------------------------------------
# Activity ROI Comparison
# ------------------------------------------------------------------


class TestActivityRoi:
    def test_multiple_activities(self, engine):
        txns = [
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
            make_transaction(
                id="t3",
                category="bounty_reward",
                transaction_type="income",
                amount=25_000,
                activity="bounty_hunting",
            ),
        ]
        result = engine.activity_roi_comparison(txns)

        assert len(result) == 2
        # Sorted by net_profit descending
        assert result[0]["activity"] == "bounty_hunting"  # 25k net
        assert result[1]["activity"] == "trading"  # 20k net

    def test_empty_transactions(self, engine):
        result = engine.activity_roi_comparison([])
        assert result == []

    def test_skip_zero_activity(self, engine):
        """Activities with zero revenue and zero costs are skipped."""
        txns = [
            make_transaction(
                id="t1",
                category="commodity_sale",
                transaction_type="income",
                amount=10_000,
                activity="trading",
            ),
        ]
        result = engine.activity_roi_comparison(txns)
        # Only trading should appear (it has revenue)
        assert len(result) == 1
        assert result[0]["activity"] == "trading"


# ------------------------------------------------------------------
# What-If Scenarios
# ------------------------------------------------------------------


class TestWhatIf:
    def test_trade_scenario(self, engine):
        result = engine.what_if_scenario(
            "trade",
            {
                "buy_price": 10.0,
                "sell_price": 15.0,
                "quantity": 100.0,
                "fuel_cost": 50.0,
                "other_costs": 0.0,
            },
        )
        assert result["scenario"] == "trade"
        assert result["total_revenue"] == 1500.0
        assert result["total_cost"] == 1050.0  # (10*100) + 50
        assert result["profit"] == 450.0
        assert result["margin_pct"] == 30.0
        assert result["roi_pct"] == pytest.approx(42.9, abs=0.1)

    def test_trade_zero_revenue(self, engine):
        result = engine.what_if_scenario(
            "trade",
            {"buy_price": 10.0, "sell_price": 0.0, "quantity": 100.0},
        )
        assert result["margin_pct"] == 0.0

    def test_upgrade_scenario(self, engine):
        txns = [
            make_transaction(
                id="t1",
                category="commodity_sale",
                transaction_type="income",
                amount=10_000,
                days_ago=10,
                activity="trading",
            ),
            make_transaction(
                id="t2",
                category="commodity_sale",
                transaction_type="income",
                amount=10_000,
                days_ago=0,
                activity="trading",
            ),
        ]
        result = engine.what_if_scenario(
            "upgrade",
            {"cost": 50_000, "improvement_pct": 20, "activity": "trading"},
            transactions=txns,
        )
        assert result["scenario"] == "upgrade"
        assert result["cost"] == 50_000.0
        assert result["improvement_pct"] == 20
        assert result["current_daily_revenue"] > 0
        assert result["added_daily_revenue"] > 0

    def test_upgrade_no_data(self, engine):
        result = engine.what_if_scenario(
            "upgrade",
            {"cost": 50_000, "improvement_pct": 20, "activity": "trading"},
            transactions=[],
        )
        assert result["current_daily_revenue"] == 0.0
        assert result["payback_days"] is None

    def test_ship_purchase_no_activity_data(self, engine):
        result = engine.what_if_scenario(
            "ship_purchase",
            {"price": 2_000_000, "activity": "trading"},
            transactions=[],
        )
        assert "error" in result

    def test_unknown_scenario(self, engine):
        result = engine.what_if_scenario("imaginary", {})
        assert "error" in result
        assert "imaginary" in result["error"]
        assert "supported" in result
