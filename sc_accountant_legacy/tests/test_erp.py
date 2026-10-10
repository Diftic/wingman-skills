"""Behavioural acceptance for the personal ERP, using only temporary databases."""

from decimal import Decimal
import importlib.util

import pytest


def engine(tmp_path):
    assert importlib.util.find_spec("erp") is not None, (
        "Personal ERP engine is not implemented"
    )
    from erp import ERP

    return ERP(tmp_path / "erp.sqlite3")


def data(e, section="overview"):
    return e.view(section)["data"]


def lot(e, quantity="100", amount="100000", **more):
    return e.command(
        "buy_stock",
        dict(
            item_id="gold",
            item_name="Gold",
            quantity=quantity,
            amount=amount,
            unit="SCU",
            location="Area 18",
            **more,
        ),
    )["id"]


def test_partial_sale_retains_unsold_cost_and_replays_after_restart(tmp_path):
    e = engine(tmp_path)
    e.command("reconcile_wallet", {"amount": "200000"})
    op = e.command("start_operation", {"name": "Trade run", "activity": "trading"})[
        "id"
    ]
    stock = lot(e, operation_id=op)
    sale = e.command(
        "sell_stock",
        {"lot_id": stock, "quantity": "50", "amount": "70000", "operation_id": op},
    )
    s = data(e)
    assert Decimal(s["balance"]) == 170000
    assert Decimal(s["realized_profit"]) == 20000
    assert Decimal(s["inventory_cost"]) == 50000
    assert Decimal(data(e, "operations")[0]["realized_profit"]) == 20000
    e.close()
    e = engine(tmp_path)
    assert Decimal(data(e)["inventory_cost"]) == 50000
    e.command("reverse_entry", {"entry_id": sale["entry_id"], "reason": "Wrong sale"})
    assert Decimal(data(e)["balance"]) == 100000
    assert Decimal(data(e)["inventory_cost"]) == 100000
    assert Decimal(data(e)["realized_profit"]) == 0
    e.close()


def test_unknown_cost_never_becomes_free_profit(tmp_path):
    e = engine(tmp_path)
    lid = lot(e, amount=None, quantity="10")
    e.command("sell_stock", {"lot_id": lid, "quantity": "5", "amount": "500"})
    s = data(e)
    assert s["profit_complete"] is False
    assert Decimal(s["realized_profit"]) == 0
    assert Decimal(s["unknown_cost_quantity"]) == 5
    assert data(e, "attention")
    e.close()


def test_reservation_transfer_and_failed_sale_are_atomic(tmp_path):
    e = engine(tmp_path)
    lid = lot(e, quantity="10", amount="100")
    e.command("reserve_stock", {"lot_id": lid, "quantity": "8"})
    before = data(e)
    with pytest.raises(ValueError):
        e.command("sell_stock", {"lot_id": lid, "quantity": "3", "amount": "50"})
    assert data(e)["balance"] == before["balance"]
    e.command("reserve_stock", {"lot_id": lid, "quantity": "0"})
    e.command("transfer_stock", {"lot_id": lid, "quantity": "4", "destination": "Ship"})
    rows = data(e, "inventory")
    assert sum(Decimal(x["quantity"]) for x in rows) == 10
    assert sum(Decimal(x["cost"]) for x in rows) == 100
    assert {x["location"] for x in rows} == {"Area 18", "Ship"}
    e.close()


def test_production_completion_and_collection_are_distinct(tmp_path):
    e = engine(tmp_path)
    lid = lot(e, quantity="10", amount="100")
    job = e.command(
        "start_production",
        {"name": "Refine", "inputs": [{"lot_id": lid, "quantity": "10"}], "fee": "20"},
    )["id"]
    assert Decimal(data(e)["inventory_cost"]) == 120
    assert not data(e, "inventory")
    with pytest.raises(ValueError):
        e.command(
            "collect_production",
            {
                "production_id": job,
                "item_id": "refined",
                "item_name": "Refined Gold",
                "quantity": "8",
                "unit": "SCU",
                "location": "Refinery",
            },
        )
    e.command("complete_production", {"production_id": job})
    e.command(
        "collect_production",
        {
            "production_id": job,
            "item_id": "refined",
            "item_name": "Refined Gold",
            "quantity": "8",
            "unit": "SCU",
            "location": "Refinery",
        },
    )
    assert Decimal(data(e, "inventory")[0]["cost"]) == 120
    assert data(e, "production")[0]["status"] == "collected"
    with pytest.raises(ValueError):
        e.command(
            "collect_production",
            {"production_id": job, "item_id": "refined", "quantity": "8"},
        )
    e.close()


def page(events, after=0, cursor=None, source="reader-A"):
    return {
        "contract_version": 1,
        "source_id": source,
        "after": after,
        "next_cursor": cursor if cursor is not None else len(events),
        "has_more": False,
        "events": events,
        "health": {},
    }


def event(i, kind, status, **more):
    return {
        "id": f"reader-A:{i}",
        "sequence": i,
        "environment": "LIVE",
        "event_type": kind,
        "status": status,
        "timestamp": "2026-09-18T10:00:00+00:00",
        "source_occurrences": [f"source-{i}"],
        "data": {},
        **more,
    }


def test_feed_requests_never_post_money_and_confirmations_are_idempotent(tmp_path):
    e = engine(tmp_path)
    request = event(
        1,
        "shop_buy",
        "requested",
        data={"price": 100, "quantity": 2, "item_name": "Ammo"},
    )
    confirmed = event(
        2,
        "shop_buy",
        "confirmed",
        amount_auec=-100,
        source_occurrences=["source-1", "source-2"],
        data={"price": 100, "quantity": 2, "item_name": "Ammo"},
    )
    e.ingest_page(page([request]))
    assert Decimal(data(e)["balance"]) == 0
    e.ingest_page(page([confirmed], after=1, cursor=2))
    assert Decimal(data(e)["balance"]) == -100
    e.ingest_page(page([request, confirmed], cursor=2))
    assert Decimal(data(e)["balance"]) == -100
    assert data(e, "feed")["cursor"] == 2
    assert not [x for x in data(e, "attention") if x["id"] == "reader-A:1"]
    e.close()


def test_feed_filters_test_economy_and_rejects_source_switch(tmp_path):
    e = engine(tmp_path)
    e.ingest_page(
        page(
            [
                event(
                    1, "reward_earned", "confirmed", amount_auec=50, environment="PTU"
                ),
                event(2, "reward_earned", "confirmed", amount_auec=80),
            ]
        )
    )
    assert Decimal(data(e)["balance"]) == 80
    with pytest.raises(ValueError):
        e.ingest_page(page([], after=2, cursor=2, source="replacement"))
    assert data(e, "feed")["source_id"] == "reader-A"
    e.close()


def test_feed_invalid_money_rolls_back_cursor_and_earlier_rows(tmp_path):
    e = engine(tmp_path)
    with pytest.raises(ValueError):
        e.ingest_page(
            page(
                [
                    event(1, "reward_earned", "confirmed", amount_auec=50),
                    event(2, "reward_earned", "confirmed", amount_auec="NaN"),
                ]
            )
        )
    assert Decimal(data(e)["balance"]) == 0
    assert data(e, "feed")["cursor"] == 0
    e.close()


def test_manual_confirmation_then_reader_confirmation_does_not_double_post(tmp_path):
    e = engine(tmp_path)
    req = event(
        1,
        "commodity_buy",
        "requested",
        data={"price": 100, "quantity_cscu": 100, "resource_guid": "gold"},
    )
    e.ingest_page(page([req]))
    e.command(
        "resolve_event",
        {
            "event_id": req["id"],
            "decision": "confirm",
            "amount": "100",
            "direction": "expense",
        },
    )
    conf = event(
        2,
        "commodity_buy",
        "confirmed",
        amount_auec=-100,
        source_occurrences=["source-1", "source-2"],
    )
    e.ingest_page(page([conf], after=1, cursor=2))
    assert Decimal(data(e)["balance"]) == -100
    e.close()


def test_mode_change_preserves_records_and_old_mode_names(tmp_path):
    e = engine(tmp_path)
    lot(e)
    e.command("set_mode", {"mode": "industrial"})
    assert e.view()["mode"] == "advanced"
    e.command("set_mode", {"mode": "simple"})
    assert len(data(e, "inventory")) == 1
    assert e.view()["mode"] == "simple"
    e.close()


def test_reconciliation_not_income_and_plan_affordability(tmp_path):
    e = engine(tmp_path)
    e.command("reconcile_wallet", {"amount": "1000", "notes": "Observed wallet"})
    e.command(
        "set_plan",
        {"name": "Ship fund", "target": "2000", "reserve": "200", "committed": "100"},
    )
    assert Decimal(data(e)["available_funds"]) == 700
    assert Decimal(data(e)["realized_profit"]) == 0
    assert Decimal(data(e, "plans")[0]["shortfall"]) == 1300
    e.close()


@pytest.mark.parametrize("value", ["NaN", "Infinity", "-1", True])
def test_invalid_money_rejected_without_records(tmp_path, value):
    e = engine(tmp_path)
    with pytest.raises(ValueError):
        e.command("record_cash", {"amount": value, "direction": "income"})
    assert not data(e, "journal")
    e.close()


def test_new_period_preserves_old_history_without_reimporting_it(tmp_path):
    e = engine(tmp_path)
    e.ingest_page(page([event(1, "reward_earned", "confirmed", amount_auec=100)]))
    e.command("new_period", {"name": "After wipe"})
    assert Decimal(data(e)["balance"]) == 0
    assert data(e, "feed")["cursor"] == 1
    assert len(e.view("journal", all_periods=True)["data"]) == 1
    e.close()


def test_asset_registration_existing_does_not_spend_cash(tmp_path):
    e = engine(tmp_path)
    e.command("register_asset", {"name": "Prospector", "purchase_price": "2000000"})
    assert Decimal(data(e)["balance"]) == 0
    e.command(
        "register_asset",
        {"name": "New ship", "purchase_price": "100", "acquired_now": True},
    )
    assert Decimal(data(e)["balance"]) == -100
    assert Decimal(data(e)["realized_profit"]) == 0
    e.close()


def test_reversal_refuses_to_change_stock_already_used(tmp_path):
    e = engine(tmp_path)
    buy = e.command(
        "buy_stock",
        {
            "item_id": "gold",
            "quantity": "10",
            "amount": "100",
            "unit": "SCU",
            "location": "A",
        },
    )
    e.command("sell_stock", {"lot_id": buy["id"], "quantity": "1", "amount": "20"})
    with pytest.raises(ValueError):
        e.command(
            "reverse_entry", {"entry_id": buy["entry_id"], "reason": "Wrong purchase"}
        )
    assert Decimal(data(e)["inventory_cost"]) == 90
    e.close()


def test_recorded_sale_can_allocate_stock_without_double_cash(tmp_path):
    e = engine(tmp_path)
    lid = lot(e, quantity="10", amount="100")
    e.ingest_page(page([event(1, "commodity_sell", "confirmed", amount_auec=70)]))
    entry = data(e, "journal")[0]
    assert data(e)["profit_complete"] is False
    allocation = e.command(
        "allocate_sale",
        {"entry_id": entry["id"], "inputs": [{"lot_id": lid, "quantity": "5"}]},
    )
    assert Decimal(data(e)["balance"]) == -30
    assert Decimal(data(e)["realized_profit"]) == 20
    assert Decimal(data(e)["inventory_cost"]) == 50
    assert data(e)["profit_complete"] is True
    with pytest.raises(ValueError):
        e.command(
            "allocate_sale",
            {"entry_id": entry["id"], "inputs": [{"lot_id": lid, "quantity": "1"}]},
        )
    with pytest.raises(ValueError):
        e.command("reverse_entry", {"entry_id": entry["id"], "reason": "Undo"})
    e.command(
        "reverse_entry",
        {"entry_id": allocation["entry_id"], "reason": "Wrong allocation"},
    )
    assert data(e)["profit_complete"] is False
    assert Decimal(data(e)["inventory_cost"]) == 100
    e.close()


def test_unknown_remaining_and_sold_costs_correct_independently(tmp_path):
    e = engine(tmp_path)
    lid = lot(e, quantity="10", amount=None)
    sale = e.command("sell_stock", {"lot_id": lid, "quantity": "5", "amount": "70"})
    e.command("set_stock_cost", {"lot_id": lid, "amount": "50"})
    e.command("resolve_cost", {"entry_id": sale["entry_id"], "amount": "50"})
    assert Decimal(data(e)["realized_profit"]) == 20
    assert Decimal(data(e)["inventory_cost"]) == 50
    assert data(e)["profit_complete"] is True
    e.close()


def test_link_entry_changes_operation_metrics_without_reposting(tmp_path):
    e = engine(tmp_path)
    entry = e.command("record_cash", {"amount": "100", "direction": "income"})
    op = e.command("start_operation", {"name": "Salvage"})["id"]
    e.command("assign_entry", {"entry_id": entry["entry_id"], "operation_id": op})
    assert Decimal(data(e, "operations")[0]["realized_profit"]) == 100
    assert Decimal(data(e)["balance"]) == 100
    e.close()


def test_cash_posted_unallocated_confirmation_is_not_posted_twice(tmp_path):
    e = engine(tmp_path)
    first = event(1, "commodity_sell", "confirmed", amount_auec=100)
    again = event(
        2,
        "commodity_sell",
        "confirmed",
        amount_auec=100,
        source_occurrences=["source-1", "source-2"],
    )
    e.ingest_page(page([first]))
    e.ingest_page(page([again], after=1, cursor=2))
    assert Decimal(data(e)["balance"]) == 100
    e.close()


def test_cross_account_page_is_rejected_atomically(tmp_path):
    e = engine(tmp_path)
    e.ingest_page(
        page([event(1, "user_login", "observed", data={"player_name": "Alice"})])
    )
    with pytest.raises(ValueError):
        e.ingest_page(
            page(
                [
                    event(2, "user_login", "observed", data={"player_name": "Bob"}),
                    event(3, "reward_earned", "confirmed", amount_auec=100),
                ],
                after=1,
                cursor=3,
            )
        )
    assert Decimal(data(e)["balance"]) == 0
    assert data(e, "feed")["cursor"] == 1
    e.close()


def test_context_only_status_cannot_be_confirmed_as_cash(tmp_path):
    e = engine(tmp_path)
    e.ingest_page(page([event(1, "refinery_complete", "observed")]))
    with pytest.raises(ValueError):
        e.command(
            "resolve_event",
            {
                "event_id": "reader-A:1",
                "decision": "confirm",
                "amount": 100,
                "direction": "income",
            },
        )
    assert Decimal(data(e)["balance"]) == 0
    e.close()


def test_legacy_import_preserves_balance_and_never_duplicates(tmp_path):
    import json

    old = tmp_path / "old"
    old.mkdir()
    (old / "transactions.jsonl").write_text(
        json.dumps(
            {
                "id": "old-1",
                "amount": 10,
                "transaction_type": "income",
                "description": "Reward",
            }
        )
        + "\n"
    )
    (old / "balance.json").write_text(json.dumps({"current_balance": 100}))
    e = engine(tmp_path)
    e.command("import_legacy", {"path": str(old), "confirmed": True})
    assert Decimal(data(e)["balance"]) == 100
    assert (
        e.command("import_legacy", {"path": str(old), "confirmed": True})[
            "already_imported"
        ]
        is True
    )
    assert Decimal(data(e)["balance"]) == 100
    e.close()


def test_conflicting_confirmation_cannot_be_posted_a_second_time(tmp_path):
    e = engine(tmp_path)
    e.ingest_page(page([event(1, "shop_buy", "requested")]))
    e.command(
        "resolve_event",
        {
            "event_id": "reader-A:1",
            "decision": "confirm",
            "amount": 100,
            "direction": "expense",
        },
    )
    e.ingest_page(
        page(
            [
                event(
                    2,
                    "shop_buy",
                    "confirmed",
                    amount_auec=-120,
                    source_occurrences=["source-1", "source-2"],
                )
            ],
            after=1,
            cursor=2,
        )
    )
    with pytest.raises(ValueError):
        e.command(
            "resolve_event",
            {
                "event_id": "reader-A:2",
                "decision": "confirm",
                "amount": 120,
                "direction": "expense",
            },
        )
    assert Decimal(data(e)["balance"]) == -100
    e.close()


def test_feed_cursor_cannot_skip_unprovided_events(tmp_path):
    e = engine(tmp_path)
    with pytest.raises(ValueError):
        e.ingest_page(page([], cursor=20))
    with pytest.raises(ValueError):
        e.ingest_page(
            page([event(1, "reward_earned", "confirmed", amount_auec=20)], cursor=20)
        )
    assert data(e, "feed")["cursor"] == 0
    e.close()


def test_planning_explicit_assumptions_and_capacity(tmp_path):
    e = engine(tmp_path)
    e.command("reconcile_wallet", {"amount": "1000"})
    e.command(
        "set_plan",
        {
            "name": "Mining ship",
            "target": "2000",
            "reserve": "200",
            "committed": "100",
            "income_per_hour": "100",
            "cost_per_hour": "30",
            "hours_per_week": "5",
            "required_quantity": "100",
            "available_quantity": "20",
            "capacity_per_trip": "30",
        },
    )
    plan = data(e, "plans")[0]
    assert Decimal(plan["expected_hours"]) == Decimal("18.57")
    assert Decimal(plan["estimated_weeks"]) == Decimal("3.71")
    assert plan["trips_needed"] == 4
    assert Decimal(plan["resource_shortfall"]) == 80
    e.close()


def test_asset_profit_and_break_even_use_explicit_links(tmp_path):
    e = engine(tmp_path)
    asset = e.command(
        "register_asset", {"name": "Prospector", "purchase_price": "1000"}
    )["id"]
    e.command(
        "record_cash", {"amount": "300", "direction": "income", "asset_id": asset}
    )
    e.command(
        "record_cash", {"amount": "100", "direction": "expense", "asset_id": asset}
    )
    row = data(e, "assets")[0]
    assert Decimal(row["realized_profit"]) == 200
    assert Decimal(row["remaining_to_break_even"]) == 800
    e.close()


def test_financial_reports_exclude_wallet_adjustment_from_income(tmp_path):
    e = engine(tmp_path)
    e.command("reconcile_wallet", {"amount": "1000"})
    stock = lot(e, quantity="10", amount="100")
    e.command("sell_stock", {"lot_id": stock, "quantity": "5", "amount": "70"})
    reports = data(e, "reports")
    assert reports["income_statement"]["realized_profit"] == "20.00"
    assert reports["cash_flow"]["net"] == "-30.00"
    assert reports["cash_flow"]["adjustments"] == "1000.00"
    assert reports["balance_sheet"]["total_known_assets"] == "1020.00"
    e.close()


def test_unknown_timestamp_after_new_period_needs_review(tmp_path):
    e = engine(tmp_path)
    e.command("new_period", {"name": "New economy"})
    e.ingest_page(
        page([event(1, "reward_earned", "confirmed", amount_auec=50, timestamp=None)])
    )
    assert Decimal(data(e)["balance"]) == 0
    assert data(e, "attention")
    e.close()


def test_journal_operation_filter_is_not_ignored(tmp_path):
    e = engine(tmp_path)
    op = e.command("start_operation", {"name": "Mining"})["id"]
    e.command("record_cash", {"amount": 100, "direction": "income", "operation_id": op})
    e.command("record_cash", {"amount": 50, "direction": "income"})
    assert len(e.view("journal", operation_id=op)["data"]) == 1
    e.close()


def test_legacy_sold_assets_stay_sold_and_history_cannot_be_reversed(tmp_path):
    import json

    old = tmp_path / "legacy-assets"
    old.mkdir()
    (old / "assets.json").write_text(
        json.dumps(
            [
                {
                    "id": "old-ship",
                    "name": "Aurora",
                    "status": "sold",
                    "purchase_price": 100,
                }
            ]
        )
    )
    e = engine(tmp_path)
    e.command("import_legacy", {"path": str(old), "confirmed": True})
    assert data(e, "assets")[0]["status"] == "sold"
    assert data(e, "reports")["balance_sheet"]["assets_at_recorded_cost"] == "0.00"
    with pytest.raises(ValueError):
        e.command(
            "reverse_entry",
            {
                "entry_id": data(e, "journal")[0]["id"],
                "reason": "Keep imported history",
            },
        )
    e.close()


def test_reversed_wallet_adjustment_does_not_become_cashflow(tmp_path):
    e = engine(tmp_path)
    entry = e.command("reconcile_wallet", {"amount": 100})
    e.command(
        "reverse_entry", {"entry_id": entry["entry_id"], "reason": "Incorrect reading"}
    )
    assert data(e)["cash_flow"] == "0.00"
    assert data(e, "reports")["cash_flow"]["net"] == "0.00"
    e.close()


def test_unsupported_database_is_not_changed(tmp_path):
    from erp import ERP
    import sqlite3
    import json

    path = tmp_path / "future.sqlite3"
    with sqlite3.connect(path) as db:
        db.execute("CREATE TABLE settings(key TEXT PRIMARY KEY,value TEXT)")
        db.execute("INSERT INTO settings VALUES('schema',?)", (json.dumps(99),))
    before = path.read_bytes()
    with pytest.raises(ValueError, match="Unsupported"):
        ERP(path)
    assert path.read_bytes() == before


def test_asset_cost_resolution_keeps_asset_attribution(tmp_path):
    e = engine(tmp_path)
    asset = e.command("register_asset", {"name": "Unknown ship"})
    op = e.command("start_operation", {"name": "Fleet sale"})
    sale = e.command(
        "update_asset", {"asset_id": asset["id"], "status": "sold", "sale_amount": 1000}
    )
    e.command(
        "assign_entry",
        {
            "entry_id": sale["entry_id"],
            "operation_id": op["id"],
            "asset_id": asset["id"],
        },
    )
    correction = e.command(
        "resolve_cost", {"entry_id": sale["entry_id"], "amount": 700}
    )
    row = next(x for x in data(e, "journal") if x["id"] == correction["entry_id"])
    assert row["asset_id"] == asset["id"]
    assert data(e, "assets")[0]["realized_profit"] == "300.00"
    assert data(e, "assets")[0]["profit_complete"] is True
    e.command(
        "reverse_entry", {"entry_id": correction["entry_id"], "reason": "Wrong cost"}
    )
    assert data(e, "assets")[0]["profit_complete"] is False
    e.close()
