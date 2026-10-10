"""Tests for SC_Accountant asset manager.

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


@pytest.fixture
def manager(store, format_fn):
    return AssetManager(store=store, format_fn=format_fn)


class TestRegisterAsset:
    def test_register_ship(self, manager, store):
        asset, txn = manager.register_asset(
            asset_type="ship",
            name="Prospector",
            purchase_price=2_100_000.0,
            location="Lorville",
        )
        assert asset.id is not None
        assert asset.name == "Prospector"
        assert asset.asset_type == "ship"
        assert asset.status == "active"
        assert asset.purchase_price == 2_100_000.0

        # CAPEX transaction should be created
        assert txn is not None
        assert txn.category == "ship_purchase"
        assert txn.amount == 2_100_000.0
        assert txn.linked_asset_id == asset.id

        # Verify persisted
        assert store.get_asset(asset.id) is not None

    def test_register_component_with_parent(self, manager, store):
        # First register a ship
        ship, _ = manager.register_asset(
            asset_type="ship", name="Prospector", purchase_price=2_000_000
        )
        # Then register a component linked to it
        comp, txn = manager.register_asset(
            asset_type="component",
            name="Lancet MH1",
            purchase_price=80_000,
            parent_asset_id=ship.id,
        )
        assert comp.parent_asset_id == ship.id
        assert txn.category == "component_purchase"

    def test_register_zero_price_no_transaction(self, manager):
        asset, txn = manager.register_asset(
            asset_type="equipment",
            name="Free Item",
            purchase_price=0.0,
        )
        assert asset.id is not None
        assert txn is None  # No transaction for free items


class TestSellAsset:
    def test_sell_with_profit(self, manager, store):
        asset, _ = manager.register_asset(
            asset_type="ship",
            name="Avenger Titan",
            purchase_price=500_000,
        )
        sold, txn, msg = manager.sell_asset(asset.id, sell_price=600_000)

        assert sold.status == "sold"
        assert sold.sold_price == 600_000.0
        assert "profit" in msg.lower()
        assert txn is not None
        assert txn.amount == 600_000.0

    def test_sell_with_loss(self, manager):
        asset, _ = manager.register_asset(
            asset_type="ship",
            name="Mustang Alpha",
            purchase_price=300_000,
        )
        sold, txn, msg = manager.sell_asset(asset.id, sell_price=200_000)
        assert "loss" in msg.lower()

    def test_sell_nonexistent(self, manager):
        asset, txn, msg = manager.sell_asset("doesnt_exist", sell_price=100_000)
        assert asset is None
        assert txn is None
        assert "not found" in msg.lower()

    def test_sell_already_sold(self, manager):
        asset, _ = manager.register_asset(
            asset_type="ship",
            name="Aurora",
            purchase_price=100_000,
        )
        manager.sell_asset(asset.id, sell_price=120_000)

        # Try to sell again
        result, txn, msg = manager.sell_asset(asset.id, sell_price=130_000)
        assert result is not None
        assert txn is None
        assert "already" in msg.lower()


class TestUpdateAsset:
    def test_update_market_value(self, manager, store):
        asset, _ = manager.register_asset(
            asset_type="ship",
            name="Prospector",
            purchase_price=2_000_000,
        )
        updated, changes = manager.update_asset(
            asset.id, estimated_market_value=2_500_000
        )
        assert updated is not None
        assert updated.estimated_market_value == 2_500_000.0
        assert len(changes) == 1
        assert "market_value" in changes[0]

    def test_update_nonexistent(self, manager):
        result, changes = manager.update_asset("doesnt_exist", name="Nope")
        assert result is None
        assert changes == []

    def test_update_name(self, manager):
        asset, _ = manager.register_asset(
            asset_type="ship", name="Avenger", purchase_price=500_000
        )
        updated, changes = manager.update_asset(asset.id, name="Avenger Titan")
        assert updated.name == "Avenger Titan"
        assert any("name" in c for c in changes)

    def test_update_purchase_price_updates_market_value_when_tracking(self, manager):
        asset, _ = manager.register_asset(
            asset_type="ship", name="Aurora", purchase_price=100_000
        )
        # Market value starts equal to purchase price
        assert asset.estimated_market_value == 100_000

        updated, changes = manager.update_asset(asset.id, purchase_price=150_000)
        assert updated.purchase_price == 150_000
        # Market value should follow since it was tracking purchase price
        assert updated.estimated_market_value == 150_000

    def test_update_no_changes(self, manager):
        asset, _ = manager.register_asset(
            asset_type="ship", name="Prospector", purchase_price=2_000_000
        )
        updated, changes = manager.update_asset(asset.id, name="Prospector")
        assert changes == []

    def test_update_multiple_fields(self, manager):
        asset, _ = manager.register_asset(
            asset_type="ship", name="Freelancer", purchase_price=1_000_000
        )
        updated, changes = manager.update_asset(
            asset.id,
            name="Freelancer MAX",
            location="Lorville",
            notes="Upgraded cargo hold",
        )
        assert updated.name == "Freelancer MAX"
        assert updated.location == "Lorville"
        assert updated.notes == "Upgraded cargo hold"
        assert len(changes) == 3

    def test_update_asset_type_validates(self, manager):
        asset, _ = manager.register_asset(
            asset_type="ship", name="Aurora", purchase_price=100_000
        )
        # Valid type change
        updated, changes = manager.update_asset(asset.id, asset_type="vehicle")
        assert updated.asset_type == "vehicle"

        # Invalid type is ignored
        updated, changes = manager.update_asset(asset.id, asset_type="invalid_type")
        assert updated.asset_type == "vehicle"
        assert changes == []


class TestListAssets:
    def test_list_by_type(self, manager):
        manager.register_asset(asset_type="ship", name="Ship1", purchase_price=100)
        manager.register_asset(asset_type="component", name="Comp1", purchase_price=50)

        ships = manager.list_assets(asset_type="ship")
        assert len(ships) == 1
        assert ships[0].name == "Ship1"

    def test_list_active_only(self, manager):
        asset, _ = manager.register_asset(
            asset_type="ship", name="ToSell", purchase_price=100
        )
        manager.register_asset(asset_type="ship", name="ToKeep", purchase_price=200)
        manager.sell_asset(asset.id, sell_price=50)

        active = manager.list_assets(status="active")
        assert len(active) == 1
        assert active[0].name == "ToKeep"


class TestFleetSummary:
    def test_fleet_summary(self, manager):
        manager.register_asset(
            asset_type="ship", name="Ship1", purchase_price=1_000_000
        )
        manager.register_asset(asset_type="ship", name="Ship2", purchase_price=500_000)
        manager.register_asset(
            asset_type="component", name="Comp1", purchase_price=80_000
        )

        summary = manager.get_fleet_summary()
        assert summary["total_count"] == 3
        assert summary["total_value"] == 1_580_000.0
        assert "ship" in summary["by_type"]
        assert summary["by_type"]["ship"]["count"] == 2

    def test_fleet_summary_empty(self, manager):
        summary = manager.get_fleet_summary()
        assert summary["total_count"] == 0
        assert summary["total_value"] == 0.0
        assert summary["top_assets"] == []
