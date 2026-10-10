"""Factory functions for SC_Accountant test data.

Separated from conftest.py so they can be imported by test modules.
conftest.py is auto-loaded by pytest and not importable as a regular module.

Author: Mallachi
"""

from __future__ import annotations

import os
import sys
from datetime import datetime, timedelta, timezone

# Add skill directory to sys.path for local imports
_skill_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _skill_dir not in sys.path:
    sys.path.insert(0, _skill_dir)

from models import (  # noqa: E402
    AccountBalance,
    Asset,
    Position,
    Transaction,
)


def _format_auec(amount: float) -> str:
    """Simple test formatter matching the production pattern."""
    return f"{amount:,.0f} aUEC"


def _ts(days_ago: int = 0, hours_ago: int = 0) -> str:
    """Generate an ISO timestamp relative to now."""
    dt = datetime.now(tz=timezone.utc) - timedelta(days=days_ago, hours=hours_ago)
    return dt.isoformat()


def make_transaction(
    *,
    id: str = "t1",
    category: str = "commodity_sale",
    transaction_type: str = "income",
    amount: float = 1000.0,
    description: str = "Test transaction",
    location: str = "Lorville",
    days_ago: int = 0,
    hours_ago: int = 0,
    linked_asset_id: str | None = None,
    activity: str | None = None,
    tags: list[str] | None = None,
    session_id: str | None = None,
    source: str = "manual",
) -> Transaction:
    """Factory for Transaction instances with sensible defaults."""
    return Transaction(
        id=id,
        timestamp=_ts(days_ago, hours_ago),
        category=category,
        transaction_type=transaction_type,
        amount=amount,
        description=description,
        location=location,
        tags=tags or [],
        source=source,
        linked_asset_id=linked_asset_id,
        activity=activity,
        session_id=session_id,
    )


def make_asset(
    *,
    id: str = "a1",
    asset_type: str = "ship",
    name: str = "Prospector",
    status: str = "active",
    purchase_price: float = 2_100_000.0,
    estimated_market_value: float = 0.0,
    location: str = "Lorville",
    parent_asset_id: str | None = None,
) -> Asset:
    """Factory for Asset instances with sensible defaults."""
    return Asset(
        id=id,
        created_at=_ts(),
        asset_type=asset_type,
        name=name,
        status=status,
        purchase_price=purchase_price,
        purchase_date=_ts(),
        estimated_market_value=estimated_market_value or purchase_price,
        location=location,
        parent_asset_id=parent_asset_id,
    )


def make_position(
    *,
    id: str = "p1",
    commodity_name: str = "Laranite",
    quantity: float = 100.0,
    buy_price_per_unit: float = 30.0,
    buy_total: float = 3000.0,
    status: str = "open",
) -> Position:
    """Factory for Position instances."""
    return Position(
        id=id,
        opened_at=_ts(),
        status=status,
        commodity_name=commodity_name,
        quantity=quantity,
        buy_price_per_unit=buy_price_per_unit,
        buy_total=buy_total,
        buy_location="New Babbage",
    )


def make_balance(
    *,
    current_balance: float = 500_000.0,
) -> AccountBalance:
    """Factory for AccountBalance instances."""
    return AccountBalance(
        current_balance=current_balance,
        last_updated=_ts(),
        total_lifetime_income=current_balance,
        total_lifetime_expenses=0.0,
    )


def make_diverse_transactions() -> list[Transaction]:
    """Create a diverse set of transactions covering all statement classes.

    Returns 10 transactions across revenue, COGS, opex, and capex categories
    with multiple activities for testing income statements and cash flow.
    """
    return [
        # Revenue — trading
        make_transaction(
            id="t01",
            category="commodity_sale",
            transaction_type="income",
            amount=50_000.0,
            description="Sold laranite",
            days_ago=5,
            activity="trading",
        ),
        make_transaction(
            id="t02",
            category="item_sale",
            transaction_type="income",
            amount=8_000.0,
            description="Sold weapon",
            days_ago=4,
            activity="trading",
        ),
        # Revenue — bounty hunting
        make_transaction(
            id="t04",
            category="bounty_reward",
            transaction_type="income",
            amount=15_000.0,
            description="Bounty on pirate",
            days_ago=2,
            activity="bounty_hunting",
        ),
        # Revenue — missions
        make_transaction(
            id="t05",
            category="mission_reward",
            transaction_type="income",
            amount=10_000.0,
            description="Delivery mission",
            days_ago=1,
            activity="missions",
        ),
        # COGS — trading
        make_transaction(
            id="t06",
            category="commodity_purchase",
            transaction_type="expense",
            amount=30_000.0,
            description="Bought laranite",
            days_ago=6,
            activity="trading",
        ),
        # OpEx — general
        make_transaction(
            id="t08",
            category="fuel",
            transaction_type="expense",
            amount=1_500.0,
            description="Hydrogen fuel",
            days_ago=4,
        ),
        make_transaction(
            id="t09",
            category="repairs",
            transaction_type="expense",
            amount=3_000.0,
            description="Ship repairs",
            days_ago=2,
        ),
        # CAPEX
        make_transaction(
            id="t10",
            category="ship_purchase",
            transaction_type="expense",
            amount=2_100_000.0,
            description="Bought Prospector",
            days_ago=7,
        ),
    ]
