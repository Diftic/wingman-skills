"""
SC_Accountant — Demo Data Seed Script

Generates realistic demo data representing ~100 hours of Star Citizen gameplay.
Run once, then delete. Writes directly to the SC_Accountant data directory.

Usage: python skills/sc_accountant/seed_demo.py

Author: Mallachi
"""

from __future__ import annotations

import json
import random
import uuid
from datetime import datetime, timedelta
from pathlib import Path

DATA_DIR = Path.home() / "AppData/Roaming/ShipBit/WingmanAI/generated_files/SC_Accountant"

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

random.seed(42)  # Reproducible


def uid() -> str:
    return uuid.uuid4().hex[:12]


def ts(dt: datetime) -> str:
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


def jitter(base: float, pct: float = 0.15) -> float:
    return round(base * random.uniform(1 - pct, 1 + pct), 2)


# ---------------------------------------------------------------------------
# Reference data
# ---------------------------------------------------------------------------

LOCATIONS = [
    "Lorville", "Area18", "New Babbage", "Orison",
    "Port Tressler", "Everus Harbor", "Baijini Point", "Seraphim Station",
    "CRU-L1", "HUR-L1", "ARC-L1", "MIC-L1",
    "Bezdek", "Loveridge", "Humboldt Mines", "HDMS-Edmond",
    "Shubin SAL-2", "Shubin SAL-5",
]

COMMODITIES = {
    "Laranite":       {"buy": 2750, "sell": 3100, "scu_range": (8, 48)},
    "Quantanium (Raw)": {"buy": 0, "sell": 4400, "scu_range": (4, 32)},  # mining only
    "Agricium":       {"buy": 2450, "sell": 2780, "scu_range": (8, 64)},
    "Titanium":       {"buy": 810, "sell": 920, "scu_range": (16, 96)},
    "Gold":           {"buy": 610, "sell": 690, "scu_range": (16, 96)},
    "Diamond":        {"buy": 680, "sell": 780, "scu_range": (8, 48)},
    "Beryl":          {"buy": 430, "sell": 510, "scu_range": (16, 96)},
    "Corundum":       {"buy": 260, "sell": 320, "scu_range": (32, 128)},
    "Fluorine":       {"buy": 280, "sell": 340, "scu_range": (32, 128)},
    "Astatine":       {"buy": 900, "sell": 1060, "scu_range": (8, 48)},
    "Stims":          {"buy": 340, "sell": 410, "scu_range": (8, 48)},
    "Medical Supplies": {"buy": 180, "sell": 220, "scu_range": (16, 64)},
    "Processed Food":  {"buy": 140, "sell": 170, "scu_range": (32, 128)},
    "Scrap":          {"buy": 150, "sell": 190, "scu_range": (16, 64)},
    "Waste":          {"buy": 50, "sell": 85, "scu_range": (32, 128)},
    "Hydrogen":       {"buy": 105, "sell": 130, "scu_range": (32, 128)},
}

SHIPS = [
    {"name": "Constellation Andromeda", "type": "ship", "model": "RSI Constellation Andromeda", "price": 3_952_000, "location": "Lorville"},
    {"name": "Prospector", "type": "ship", "model": "MISC Prospector", "price": 2_061_000, "location": "New Babbage"},
    {"name": "Cutlass Black", "type": "ship", "model": "Drake Cutlass Black", "price": 1_385_300, "location": "Area18"},
    {"name": "C2 Hercules", "type": "ship", "model": "Crusader C2 Hercules", "price": 6_175_800, "location": "Orison"},
    {"name": "Vulture", "type": "ship", "model": "Drake Vulture", "price": 1_617_500, "location": "Everus Harbor"},
]

PLAYER_NAMES = [
    "xDarkWolf", "CaptainVex", "NovaStar77", "ZephyrBlade",
    "SilverHawk", "IronClad99", "NebulaRider", "StormBreaker",
    "Frostbyte", "AceTrader", "LunarDrift", "SpaceCowboy42",
    "QuantumLeap", "VoidRunner", "StellarFox",
]

ORG_NAME = "Stanton Industrial Collective"

BOUNTY_TARGETS = [
    "HRT Group Bounty", "VHRT Bounty", "ERT Bounty",
    "MRT Contract", "HRT Bounty", "VHRT Group Bounty",
]

MISSION_TYPES = [
    "Delivery Mission", "Investigation Mission", "Bunker Clearance",
    "Cargo Retrieval", "Escort Mission", "Data Runner",
    "Satellite Repair", "Missing Person",
]


# ---------------------------------------------------------------------------
# Data generation
# ---------------------------------------------------------------------------

def generate_all():
    # Timeline: 100 hours spread over ~30 days
    start = datetime(2026, 2, 5, 14, 0, 0)
    now = datetime(2026, 3, 7, 18, 30, 0)

    transactions = []
    assets = []
    loans = []
    positions = []
    planned_orders = []
    balance = {"current_balance": 0.0, "last_updated": "", "total_lifetime_income": 0.0, "total_lifetime_expenses": 0.0}

    cursor = start
    txn_id = 0

    def add_txn(category, txn_type, amount, description, location, dt, **kwargs):
        nonlocal txn_id, balance
        txn_id += 1
        t = {
            "id": f"txn-{txn_id:04d}",
            "timestamp": ts(dt),
            "category": category,
            "transaction_type": txn_type,
            "amount": round(amount, 2),
            "description": description,
            "location": location,
            "notes": kwargs.get("notes", ""),
            "tags": kwargs.get("tags", []),
            "source": kwargs.get("source", "auto_log"),
            "trade_order_id": None,
            "session_id": None,
            "item_name": kwargs.get("item_name"),
            "item_guid": None,
            "quantity": kwargs.get("quantity"),
            "quantity_unit": kwargs.get("quantity_unit"),
            "shop_name": kwargs.get("shop_name"),
            "player_id": None,
            "linked_asset_id": kwargs.get("linked_asset_id"),
            "activity": kwargs.get("activity"),
            "group_session_id": None,
        }
        transactions.append(t)
        if txn_type == "income":
            balance["current_balance"] += amount
            balance["total_lifetime_income"] += amount
        else:
            balance["current_balance"] -= amount
            balance["total_lifetime_expenses"] += amount
        return t["id"]

    # --- Starting balance ---
    balance["current_balance"] = 18_500_000  # Starting cash (accumulated before tracking)

    # --- Ship purchases (spread over first 2 weeks) ---
    for i, ship in enumerate(SHIPS):
        dt = start + timedelta(days=i * 3, hours=random.randint(1, 8))
        aid = uid()
        assets.append({
            "id": aid,
            "created_at": ts(dt),
            "asset_type": ship["type"],
            "name": ship["name"],
            "status": "active",
            "purchase_price": ship["price"],
            "purchase_date": ts(dt),
            "estimated_market_value": jitter(ship["price"], 0.05),
            "location": ship["location"],
            "ship_model": ship["model"],
            "parent_asset_id": None,
            "notes": "",
            "sold_at": None,
            "sold_price": 0.0,
            "destroyed_at": None,
            "insurance_claim_amount": 0.0,
            "purchase_transaction_id": f"txn-{txn_id + 1:04d}",
        })
        add_txn("ship_purchase", "expense", ship["price"], ship["name"],
                ship["location"], dt, item_name=ship["name"],
                linked_asset_id=aid, activity="general")

    # --- Main gameplay loop: ~1200 transactions over 100 hours ---
    # Simulate play sessions of 2-5 hours each
    session_start = start + timedelta(days=1)
    hours_played = 0

    while hours_played < 100 and cursor < now:
        session_length = random.uniform(2.0, 5.0)
        session_end_time = cursor + timedelta(hours=session_length)

        while cursor < session_end_time and hours_played < 100:
            loc = random.choice(LOCATIONS)
            event = random.random()

            if event < 0.45:
                # Commodity trade (buy then sell)
                commodity = random.choice([c for c in COMMODITIES if COMMODITIES[c]["buy"] > 0])
                info = COMMODITIES[commodity]
                qty = random.randint(*info["scu_range"])
                buy_price = jitter(info["buy"]) * qty
                sell_loc = random.choice([l for l in LOCATIONS if l != loc])

                add_txn("commodity_purchase", "expense", buy_price, commodity,
                        loc, cursor, item_name=commodity, quantity=qty,
                        quantity_unit="scu", activity="trading")

                cursor += timedelta(minutes=random.randint(3, 8))

                sell_price = jitter(info["sell"]) * qty
                add_txn("commodity_sale", "income", sell_price, commodity,
                        sell_loc, cursor, item_name=commodity, quantity=qty,
                        quantity_unit="scu", activity="trading")

            elif event < 0.60:
                # Mining run (no buy, just sell refined ore)
                ore = random.choice(["Quantanium (Raw)", "Gold", "Laranite", "Agricium"])
                qty = random.randint(4, 24)
                info = COMMODITIES[ore]
                sell_price = jitter(info["sell"]) * qty

                # Refinery fee
                fee = round(sell_price * random.uniform(0.05, 0.12), 2)
                add_txn("refinery_fee", "expense", fee, f"Refinery fee — {ore}",
                        random.choice(["CRU-L1", "HUR-L1", "ARC-L1"]), cursor,
                        activity="mining")

                cursor += timedelta(minutes=random.randint(15, 40))

                add_txn("mining_income", "income", sell_price, ore,
                        random.choice(LOCATIONS[:4]), cursor, item_name=ore,
                        quantity=qty, quantity_unit="scu", activity="mining")

            elif event < 0.72:
                # Bounty hunting
                target = random.choice(BOUNTY_TARGETS)
                reward = jitter(random.choice([15000, 25000, 45000, 75000, 100000]))
                add_txn("bounty_reward", "income", reward, target,
                        loc, cursor, activity="bounty_hunting")

                # Ammo cost
                if random.random() < 0.6:
                    ammo_cost = jitter(random.choice([500, 1200, 2500]))
                    add_txn("ammunition", "expense", ammo_cost, "Ammunition restock",
                            loc, cursor + timedelta(minutes=1), activity="bounty_hunting")

            elif event < 0.82:
                # Mission
                mission = random.choice(MISSION_TYPES)
                reward = jitter(random.choice([8000, 15000, 22000, 35000, 50000]))
                add_txn("mission_reward", "income", reward, mission,
                        loc, cursor, activity="missions")

            elif event < 0.88:
                # Salvage
                value = jitter(random.choice([12000, 25000, 40000, 60000]))
                add_txn("salvage_income", "income", value, "Salvage operation",
                        loc, cursor, activity="salvage")

            elif event < 0.92:
                # Fuel
                cost = jitter(random.choice([350, 800, 1500, 2800]))
                add_txn("fuel", "expense", cost, "Hydrogen refuel",
                        loc, cursor, activity="general")

            elif event < 0.95:
                # Repairs
                cost = jitter(random.choice([500, 2000, 5000, 12000]))
                add_txn("repairs", "expense", cost, "Ship repair",
                        loc, cursor, activity="general")

            elif event < 0.97:
                # Medical
                cost = jitter(random.choice([500, 1500, 4500]))
                add_txn("medical", "expense", cost, "Medical treatment",
                        loc, cursor, activity="general")

            elif event < 0.985:
                # Fines
                cost = jitter(random.choice([2000, 5000, 10000]))
                add_txn("fines", "expense", cost, "CrimeStat fine",
                        loc, cursor, activity="general")

            else:
                # Insurance claim
                cost = jitter(random.choice([1000, 3000, 8000]))
                add_txn("insurance", "expense", cost, "Insurance premium",
                        loc, cursor, activity="general")

            cursor += timedelta(minutes=random.randint(3, 7))
            hours_played += random.uniform(0.05, 0.12)

        # Gap between sessions (6-36 hours)
        cursor += timedelta(hours=random.uniform(6, 36))

    # --- Loans (15 lent out, 1 borrowed) ---
    loan_base = start + timedelta(days=5)
    for i in range(15):
        dt = loan_base + timedelta(days=random.randint(0, 25), hours=random.randint(0, 12))
        player = PLAYER_NAMES[i % len(PLAYER_NAMES)]
        principal = random.choice([5000, 10000, 15000, 20000, 25000, 50000, 75000, 100000])
        rate = random.choice([2.0, 3.0, 5.0, 7.5, 10.0])
        period = random.choice(["day", "week", "month"])
        status = random.choice(["active", "active", "active", "settled"])
        remaining = principal if status == "active" else 0.0

        payments = []
        if status == "settled":
            payments.append({
                "date": ts(dt + timedelta(days=random.randint(3, 15))),
                "amount": principal,
                "interest_portion": round(principal * rate / 100, 2),
                "principal_portion": principal,
                "notes": "Full repayment",
                "forgiven": False,
            })

        loans.append({
            "id": uid(),
            "created_at": ts(dt),
            "loan_type": "lent",
            "status": status,
            "counterparty": player,
            "principal": principal,
            "remaining_principal": remaining,
            "interest_rate": rate,
            "interest_period": period,
            "start_date": ts(dt),
            "last_interest_date": ts(dt),
            "total_interest_accrued": round(principal * rate / 100 * random.uniform(0.5, 3), 2) if status == "active" else round(principal * rate / 100, 2),
            "payments": payments,
            "notes": "",
        })

    # 1 borrowed from org
    org_dt = start + timedelta(days=8)
    loans.append({
        "id": uid(),
        "created_at": ts(org_dt),
        "loan_type": "borrowed",
        "status": "active",
        "counterparty": ORG_NAME,
        "principal": 500_000,
        "remaining_principal": 350_000,
        "interest_rate": 3.0,
        "interest_period": "month",
        "start_date": ts(org_dt),
        "last_interest_date": ts(org_dt + timedelta(days=20)),
        "total_interest_accrued": 15000.0,
        "payments": [
            {
                "date": ts(org_dt + timedelta(days=14)),
                "amount": 150_000,
                "interest_portion": 7500.0,
                "principal_portion": 150_000,
                "notes": "First installment",
                "forgiven": False,
            }
        ],
        "notes": "Fleet expansion loan from org treasury",
    })

    # --- Open positions (commodities currently held) ---
    held_commodities = ["Laranite", "Agricium", "Astatine", "Diamond"]
    for comm in held_commodities:
        info = COMMODITIES[comm]
        qty = random.randint(8, 48)
        buy_price = jitter(info["buy"])
        market_price = jitter(info["sell"], 0.10)
        positions.append({
            "id": uid(),
            "opened_at": ts(now - timedelta(hours=random.randint(2, 48))),
            "status": "open",
            "commodity_name": comm,
            "commodity_id": None,
            "quantity": qty,
            "quantity_unit": "scu",
            "buy_price_per_unit": buy_price,
            "buy_total": round(buy_price * qty, 2),
            "buy_location": random.choice(LOCATIONS[:4]),
            "buy_transaction_id": None,
            "current_market_price": market_price,
            "unrealized_pnl": round((market_price - buy_price) * qty, 2),
            "last_price_update": ts(now),
            "sell_price_per_unit": 0.0,
            "sell_total": 0.0,
            "sell_location": "",
            "sell_transaction_id": None,
            "closed_at": None,
            "realized_pnl": 0.0,
            "notes": "",
        })

    # --- Planned orders ---
    # Purchase orders
    po_items = [
        ("Laranite", 100, "scu", 2750, "CRU-L1", "open", 0),
        ("Titanium", 200, "scu", 810, "Lorville", "partial", 80),
        ("Medical Supplies", 64, "scu", 180, "Orison", "open", 0),
        ("Aegis Sabre", 1, "units", 2_750_000, "Area18", "open", 0),
        ("Size 3 Cannons", 4, "units", 12_500, "New Babbage", "partial", 2),
    ]
    for item_name, qty, unit, price, loc, status, fulfilled in po_items:
        fulfillments = []
        if fulfilled > 0:
            fulfillments.append({
                "transaction_id": f"txn-{random.randint(100, txn_id):04d}",
                "quantity": fulfilled,
                "amount": round(price * fulfilled, 2),
                "date": ts(now - timedelta(days=random.randint(1, 5))),
            })
        planned_orders.append({
            "id": uid(),
            "created_at": ts(now - timedelta(days=random.randint(3, 15))),
            "order_type": "purchase",
            "status": status,
            "item_name": item_name,
            "ordered_quantity": qty,
            "fulfilled_quantity": fulfilled,
            "quantity_unit": unit,
            "target_price_per_unit": price,
            "target_location": loc,
            "linked_asset_id": None,
            "fulfillments": fulfillments,
            "notes": "",
            "fulfilled_at": None,
            "cancelled_at": None,
        })

    # Sales orders
    so_items = [
        ("Laranite", 50, "scu", 3100, "Port Tressler", "partial", 20),
        ("Gold", 80, "scu", 690, "Area18", "open", 0),
        ("Agricium", 40, "scu", 2780, "New Babbage", "fulfilled", 40),
    ]
    for item_name, qty, unit, price, loc, status, fulfilled in so_items:
        fulfillments = []
        if fulfilled > 0:
            fulfillments.append({
                "transaction_id": f"txn-{random.randint(100, txn_id):04d}",
                "quantity": fulfilled,
                "amount": round(price * fulfilled, 2),
                "date": ts(now - timedelta(days=random.randint(1, 5))),
            })
        po = {
            "id": uid(),
            "created_at": ts(now - timedelta(days=random.randint(3, 15))),
            "order_type": "sale",
            "status": status,
            "item_name": item_name,
            "ordered_quantity": qty,
            "fulfilled_quantity": fulfilled,
            "quantity_unit": unit,
            "target_price_per_unit": price,
            "target_location": loc,
            "linked_asset_id": None,
            "fulfillments": fulfillments,
            "notes": "",
            "fulfilled_at": ts(now - timedelta(days=1)) if status == "fulfilled" else None,
            "cancelled_at": None,
        }
        planned_orders.append(po)

    # --- Finalize balance ---
    balance["last_updated"] = ts(now)

    # --- Write files ---
    DATA_DIR.mkdir(parents=True, exist_ok=True)

    # Transactions (JSONL)
    with open(DATA_DIR / "transactions.jsonl", "w") as f:
        for t in transactions:
            f.write(json.dumps(t) + "\n")

    # JSON files
    def write_json(filename, data):
        with open(DATA_DIR / filename, "w") as f:
            json.dump(data, f, indent=2)

    write_json("balance.json", balance)
    write_json("assets.json", assets)
    write_json("loans.json", loans)
    write_json("positions.json", positions)
    write_json("planned_orders.json", planned_orders)

    # Summary
    print(f"Seed complete!")
    print(f"  Transactions:    {len(transactions)}")
    print(f"  Assets (ships):  {len(assets)}")
    print(f"  Loans:           {len(loans)}")
    print(f"  Open positions:  {len(positions)}")
    print(f"  Planned orders:  {len(planned_orders)}")
    print(f"  Final balance:   {balance['current_balance']:,.0f} aUEC")
    print(f"  Data dir:        {DATA_DIR}")


if __name__ == "__main__":
    generate_all()
