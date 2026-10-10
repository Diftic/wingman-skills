"""Tests for SC_Accountant data models, classification maps, and enums.

Author: Mallachi
"""

from __future__ import annotations

import os
import sys


_skill_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _skill_dir not in sys.path:
    sys.path.insert(0, _skill_dir)

from models import (  # noqa: E402
    ALL_CATEGORIES,
    CATEGORY_ACTIVITY,
    CATEGORY_CLASSIFICATION,
    CATEGORY_LABELS,
    EXPENSE_CATEGORIES,
    INCOME_CATEGORIES,
    Activity,
    Asset,
    StatementClass,
    Transaction,
)


# ------------------------------------------------------------------
# Classification map completeness
# ------------------------------------------------------------------


class TestClassificationMaps:
    """Every category must map to a StatementClass and Activity."""

    def test_every_category_has_classification(self):
        for cat in ALL_CATEGORIES:
            assert cat in CATEGORY_CLASSIFICATION, (
                f"Category '{cat}' missing from CATEGORY_CLASSIFICATION"
            )

    def test_every_category_has_activity(self):
        for cat in ALL_CATEGORIES:
            assert cat in CATEGORY_ACTIVITY, (
                f"Category '{cat}' missing from CATEGORY_ACTIVITY"
            )

    def test_every_category_has_label(self):
        for cat in ALL_CATEGORIES:
            assert cat in CATEGORY_LABELS, (
                f"Category '{cat}' missing from CATEGORY_LABELS"
            )

    def test_classification_values_are_valid_enums(self):
        for cat, cls in CATEGORY_CLASSIFICATION.items():
            assert isinstance(cls, StatementClass), (
                f"Category '{cat}' maps to {cls}, not a StatementClass"
            )

    def test_activity_values_are_valid_enums(self):
        for cat, act in CATEGORY_ACTIVITY.items():
            assert isinstance(act, Activity), (
                f"Category '{cat}' maps to {act}, not an Activity"
            )

    def test_income_categories_are_revenue(self):
        """Income categories should classify as REVENUE."""
        for cat in INCOME_CATEGORIES:
            cls = CATEGORY_CLASSIFICATION.get(cat)
            assert cls == StatementClass.REVENUE, (
                f"Income category '{cat}' classified as {cls}, expected REVENUE"
            )

    def test_capex_categories_exist(self):
        assert "ship_purchase" in ALL_CATEGORIES
        assert "component_purchase" in ALL_CATEGORIES

    def test_capex_categories_in_expense_set(self):
        assert "ship_purchase" in EXPENSE_CATEGORIES
        assert "component_purchase" in EXPENSE_CATEGORIES

    def test_ship_purchase_is_capex(self):
        assert CATEGORY_CLASSIFICATION["ship_purchase"] == StatementClass.CAPEX

    def test_component_purchase_is_capex(self):
        assert CATEGORY_CLASSIFICATION["component_purchase"] == StatementClass.CAPEX

    def test_trading_activity_mapping(self):
        trading_cats = [
            "commodity_sale",
            "commodity_purchase",
            "player_trade_buy",
            "player_trade_sell",
            "item_sale",
        ]
        for cat in trading_cats:
            assert CATEGORY_ACTIVITY[cat] == Activity.TRADING, (
                f"'{cat}' should map to TRADING"
            )



# ------------------------------------------------------------------
# Enum values
# ------------------------------------------------------------------


class TestEnums:
    def test_statement_class_values(self):
        assert StatementClass.REVENUE.value == "revenue"
        assert StatementClass.COGS.value == "cogs"
        assert StatementClass.OPEX.value == "opex"
        assert StatementClass.CAPEX.value == "capex"

    def test_activity_values(self):
        assert Activity.TRADING.value == "trading"
        assert Activity.BOUNTY_HUNTING.value == "bounty_hunting"
        assert Activity.MISSIONS.value == "missions"
        assert Activity.SALVAGE.value == "salvage"
        assert Activity.HAULING.value == "hauling"
        assert Activity.GENERAL.value == "general"


# ------------------------------------------------------------------
# Transaction from_dict
# ------------------------------------------------------------------


class TestTransactionFromDict:
    def test_round_trip(self):
        txn = Transaction(
            id="abc",
            timestamp="2026-01-01T00:00:00+00:00",
            category="fuel",
            transaction_type="expense",
            amount=500.0,
            description="Fuel",
            location="Lorville",
            linked_asset_id="ship1",
            activity="general",
        )
        data = txn.to_dict()
        restored = Transaction.from_dict(data)
        assert restored.id == txn.id
        assert restored.linked_asset_id == "ship1"
        assert restored.activity == "general"
        assert restored.amount == 500.0

    def test_missing_new_fields_default_to_none(self):
        """Old data without linked_asset_id and activity should load fine."""
        data = {
            "id": "old1",
            "timestamp": "2026-01-01T00:00:00+00:00",
            "category": "fuel",
            "transaction_type": "expense",
            "amount": 500.0,
            "description": "Fuel",
            "location": "Lorville",
        }
        txn = Transaction.from_dict(data)
        assert txn.linked_asset_id is None
        assert txn.activity is None
        assert txn.tags == []
        assert txn.source == "manual"

    def test_preserves_existing_values(self):
        data = {
            "id": "x",
            "timestamp": "2026-01-01T00:00:00+00:00",
            "category": "fuel",
            "transaction_type": "expense",
            "amount": 100.0,
            "description": "Test",
            "location": "Area18",
            "linked_asset_id": "ship99",
            "activity": "mining",
            "tags": ["test"],
        }
        txn = Transaction.from_dict(data)
        assert txn.linked_asset_id == "ship99"
        assert txn.activity == "mining"
        assert txn.tags == ["test"]


# ------------------------------------------------------------------
# Asset from_dict
# ------------------------------------------------------------------


class TestAssetFromDict:
    def test_minimal_fields(self):
        data = {
            "id": "a1",
            "created_at": "2026-01-01T00:00:00+00:00",
            "asset_type": "ship",
            "name": "Prospector",
            "status": "active",
        }
        asset = Asset.from_dict(data)
        assert asset.id == "a1"
        assert asset.purchase_price == 0.0
        assert asset.parent_asset_id is None
        assert asset.notes == ""
        assert asset.sold_at is None
        assert asset.sold_price == 0.0
        assert asset.destroyed_at is None

    def test_full_round_trip(self):
        asset = Asset(
            id="a2",
            created_at="2026-01-01T00:00:00+00:00",
            asset_type="component",
            name="Lancet MH1",
            status="active",
            purchase_price=80_000.0,
            estimated_market_value=85_000.0,
            location="Port Olisar",
            parent_asset_id="ship1",
            notes="Mining head upgrade",
        )
        data = asset.to_dict()
        restored = Asset.from_dict(data)
        assert restored.id == asset.id
        assert restored.parent_asset_id == "ship1"
        assert restored.purchase_price == 80_000.0
        assert restored.notes == "Mining head upgrade"


