# SC_Accountant — Corporate Accounting for Star Citizen

**Author:** Mallachi
**Version:** 4.8.3.1 (qualified against Star Citizen 4.8.3)
**Platform:** Wingman AI

A full business accounting system for Star Citizen, built as a Wingman AI skill.
Three-statement financial model (Income Statement, Balance Sheet, Cash Flow) with
fleet management, trade intelligence, and a standalone web dashboard.

---

## Table of Contents

- [Installation](#installation)
- [Configuration](#configuration)
- [Wingman AI Voice Module](#wingman-ai-voice-module)
- [Web Dashboard Module](#web-dashboard-module)
- [Limitations](#limitations)
- [Optional Integrations](#optional-integrations)

---

## Installation

1. Add the `sc_accountant` skill folder to your Wingman AI `skills/` directory.
2. Assign the skill to a wingman in the Wingman AI configuration panel.
3. The skill auto-activates — no additional setup required.

### Dependencies

The core accounting tools work out of the box with Wingman AI's bundled
dependencies (`fastapi`, `uvicorn` are already included). No extra packages
are needed.

---

## Configuration

All settings are available in the Wingman AI skill configuration panel:

| Setting | Default | Description |
|---------|---------|-------------|
| **Starting Balance** | `0` | Your current aUEC balance. Set once on first use. |
| **Auto-Sync Interval** | `30s` | How often to import trades from SC_LogReader. Set to `0` to disable. Only applies if SC_LogReader is installed. |
| **Currency Format** | `Full` | `Full` = `1,234,567 aUEC`. `Short` = `1.2M aUEC`. |
| **Complexity Tier** | `Engaged` | Controls which tools the AI suggests (see below). |
| **Auto-Generate Opportunities** | `true` | Generate trade opportunities when market data refreshes. |
| **Min Opportunity Profit** | `1,000` | Minimum profit threshold for generated opportunities. |
| **Auto-Track Positions** | `true` | Automatically open/close positions on commodity trades. |

### Complexity Tiers

- **Casual** — Basic income/expense tracking. Record transactions, check your
  balance, view a simple P&L. Ideal for players who just want to know where their
  money went.
- **Engaged** — Adds fleet management, trade positions, planning tools (break-even,
  ROI), credits/debts, and hauling. Good for traders and mission runners.
- **Industrial** — Full feature set including what-if scenario modeling and all
  dashboard tabs. For org leaders and industrial players.

---

## Wingman AI Voice Module

The voice module provides 23 AI tools accessible through natural speech via your
Wingman AI assistant. Talk to your wingman to manage finances hands-free while
playing.

### Voice Commands by Category

#### Financial Reports

| Say something like... | What happens |
|----------------------|--------------|
| "How much profit did I make today?" | Generates an Income Statement (Revenue, COGS, Gross Margin, OpEx, Net Profit) |
| "What's my balance sheet?" | Shows Assets, Liabilities, and Equity overview |

#### Core Accounting

| Say something like... | What happens |
|----------------------|--------------|
| "What's my balance?" | Reports current aUEC balance and lifetime totals |
| "Set my balance to 500,000" | Manually sets the balance (for corrections or initial setup) |
| "Record 500 aUEC for fuel" | Records a manual transaction with category auto-detection |
| "Show me my last 5 purchases" | Queries transaction history with filters |
| "Sync my trade log" | Manually triggers import from SC_LogReader |

#### Fleet & Assets

| Say something like... | What happens |
|----------------------|--------------|
| "Register my Prospector, purchased for 2.1 million" | Adds a ship to the asset registry (price auto-populated if UEXCorp is installed) |
| "Update the price of my Avenger to 1.5 million" | Updates asset fields (name, price, location, notes) |
| "I sold my Aurora for 200,000" | Records asset sale with realized profit/loss |

#### Market Intelligence

| Say something like... | What happens |
|----------------------|--------------|
| "What should I trade?" | Shows top profitable trade routes from UEX market data |
| "What's the price of laranite?" | Looks up buy/sell prices across terminals |

#### Planning & Analysis

| Say something like... | What happens |
|----------------------|--------------|
| "When will my Prospector break even?" | Break-even analysis based on recorded income vs. purchase price |
| "What's the most profitable activity?" | Compares ROI across gameplay activities (trading, bounties, missions, etc.) |
| "What if I buy a size 2 shield for 80,000?" | Scenario modeling — upgrade payback, ship purchase projections |

#### Group Sessions

| Say something like... | What happens |
|----------------------|--------------|
| "Start a group session with Jake and Tom" | Begins tracking transactions for split calculation |
| "Stop the group session" | Ends session and calculates per-player splits |

#### Planned Orders

| Say something like... | What happens |
|----------------------|--------------|
| "I want to buy 4 Prospectors" | Creates a purchase order with quantity tracking |
| "Show my open orders" | Lists orders with fulfillment progress (e.g. 3/4 delivered) |

#### Dashboard Control

| Say something like... | What happens |
|----------------------|--------------|
| "Open my accounting window" | Opens the web dashboard in your default browser |
| "Close the accounting window" | Closes the dashboard |

### Transaction Categories

When recording transactions manually, the AI auto-detects the category from
context. The full list:

| Group | Categories |
|-------|-----------|
| **Trading** | `commodity_purchase`, `commodity_sale`, `item_purchase`, `item_sale` |
| **P2P** | `player_trade_buy`, `player_trade_sell` |
| **Income** | `mission_reward`, `bounty_reward`, `salvage_income`, `other_income` |
| **Expenses** | `fuel`, `repairs`, `insurance`, `ammunition`, `medical`, `fines`, `hangar_fees`, `other_expense` |
| **Operating** | `crew_payment`, `org_contribution`, `rental` |
| **Capital** | `ship_purchase`, `component_purchase`, `capital_investment` |

---

## Web Dashboard Module

A standalone single-page web application served on `localhost:7863`. Opens in your
default browser when activated via voice command or automatically on skill load.

The dashboard provides full read/write access to all accounting data through an
interactive dark-themed interface with auto-refresh (5-second polling).

### Tabs

#### Balance Sheet
- Assets, Liabilities, and Equity breakdown
- Current balance, fleet value, open positions, receivables
- Payables, outstanding debts

#### Operations (Income Statement)
- Revenue, Cost of Goods Sold, Gross Margin
- Operating Expenses, Net Profit
- Per-activity margin breakdown (trading, bounties, missions, etc.)
- Period selector: Today, Week, Month, Quarter, Year, All Time

#### Ledger
- Full transaction history with sortable, filterable columns
- Per-column text filters (date, type, category, amount, description, notes, location)
- Click any row to edit: update description, notes, category, amount, location
- Pagination for large datasets

#### My Assets (Fleet)
- Registered ships, vehicles, components, and equipment
- Purchase price, estimated market value, status
- Click to edit any asset field
- Delete assets with confirmation
- Summary cards: total fleet value, ship count, active assets

#### Orders
- Purchase and sales order management
- Progress bars showing fulfillment status (e.g. 3/4 delivered)
- BUY/SELL badges for visual distinction
- Create new orders via modal form
- Edit orders, view fulfillment history, cancel or delete

#### Banking (Credits & Debts)
- Receivables (money owed to you) and payables (money you owe)
- Payment tracking with status transitions (outstanding, partial, settled)
- Record payments, write off bad debts
- Create new credits/debts via modal form

#### Portfolio (Trade Positions)
- Open and closed commodity positions
- FIFO cost basis tracking
- Unrealized P&L updated from live market prices
- Position history with realized gains/losses

#### Opportunities (Trade Futures)
- Auto-generated trade opportunities from UEX market data
- Estimated profit, route, margin percentage
- Accept, dismiss, or let opportunities auto-expire
- Location-aware filtering (shows nearby opportunities when location is available)

#### Group Events
- Active group session management with player list
- Split calculator: percentage mode or flat-rate mode
- "Equal Split" button for even distribution
- Session transaction log with per-column filtering
- Historical session browser — click past sessions to view detail

#### Statistics
- Charts and visualizations powered by Chart.js
- Income/expense trends over time

#### About
- Skill version and credit information

### Dashboard API

The dashboard exposes REST endpoints on `localhost:7863` for programmatic access:

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/summary` | Balance, income, expenses, transaction count |
| GET | `/api/income-statement` | Full income statement for period |
| GET | `/api/balance-sheet` | Balance sheet snapshot |
| GET | `/api/transactions` | Paginated, filtered transaction list |
| POST | `/api/transactions` | Create a new transaction |
| PUT | `/api/transactions/{id}` | Update an existing transaction |
| GET | `/api/fleet` | All registered assets |
| POST | `/api/fleet` | Register a new asset |
| PUT | `/api/fleet/{id}` | Update an asset |
| DELETE | `/api/fleet/{id}` | Delete an asset |
| GET | `/api/positions` | Trade positions (open/closed) |
| GET | `/api/opportunities` | Trade opportunities |
| GET | `/api/credits` | Credits and debts |
| GET | `/api/best-trades` | Top trade routes from UEX |
| GET | `/api/planned-orders` | Planned purchase/sale orders |
| POST | `/api/planned-orders` | Create a planned order |
| PUT | `/api/planned-orders/{id}` | Update a planned order |
| DELETE | `/api/planned-orders/{id}` | Delete a planned order |
| GET | `/api/group-session` | Active group session or history |
| POST | `/api/group-session` | Start a new group session |
| PUT | `/api/group-session` | Update session (players, split mode) |
| DELETE | `/api/group-session` | Stop the active session |
| GET | `/api/group-session/{id}` | Detail view of a specific past session |

---

## Limitations

### General
- **Single-player data only** — Each wingman instance maintains its own ledger.
  There is no multi-user database or cloud sync.
- **No real aUEC verification** — The system trusts what you tell it. Balances are
  tracked locally and cannot be verified against the game server.
- **Manual entry required without SC_LogReader** — Without the SC_LogReader sibling
  skill, all transactions must be recorded by voice or through the dashboard.

### Auto-Sync (SC_LogReader)
- Only captures **commodity and item trades** (buy/sell). Mission rewards, bounties,
  fines, fuel costs, and other non-trade events are not in the game log and must be
  recorded manually.
- Sync uses a line-number cursor — if the SC_LogReader ledger file is deleted or
  truncated, the cursor must be manually reset or duplicates may occur.

### Market Data
- Commodity prices are sourced from **UEX (uexcorp.space)** and cached locally.
  Prices may be up to 24 hours stale between refresh cycles.
- UEX data depends on community reporting — low-traffic terminals may have
  inaccurate or outdated prices.
- Trade route suggestions exclude out-of-stock and full-inventory terminals, but
  stock levels can change between the last UEX update and your actual trade.

### Web Dashboard
- Runs on `localhost:7863` — accessible only on the local machine.
- Requires an active Wingman AI session. The dashboard stops when the wingman
  unloads or Wingman AI closes.
- Chart.js is loaded from CDN (`cdn.jsdelivr.net`) — an internet connection is
  needed for charts to render. Core tables and data display work offline.

### Positions & Portfolio
- FIFO cost basis only — no support for LIFO, average cost, or specific
  identification methods.
- Unrealized P&L depends on UEX market prices, which may not reflect actual
  in-game terminal prices at the moment of sale.

### Planned Orders
- Auto-fulfillment uses case-insensitive substring matching (e.g. "Quantanium"
  matches "Quantanium (Raw)"). This may cause false matches on items with
  similar names.
- Sale orders can only be created for items already in the asset registry, open
  positions, or inventory.

### Inventory & Production
- These modules are **stubs** — basic tracking is available but full functionality
  is pending CIG's inventory system rework in Star Citizen.

---

## Optional Integrations

All integrations are optional. The skill works fully standalone via manual voice
entry and the web dashboard.

| Sibling Skill | What It Adds |
|---------------|-------------|
| **SC_LogReader** | Automatic trade capture from the game log. Commodity and item purchases/sales are imported without manual entry. |
| **UEXCorp** | Automatic ship purchase price lookup when registering fleet assets. Three-stage fuzzy name matching. |

To enable an integration, simply assign the sibling skill to the **same wingman**
as SC_Accountant. Detection is automatic at runtime.

---

## Data Storage

All data is stored locally in the Wingman AI generated files directory:

| File | Format | Contents |
|------|--------|----------|
| `transactions.jsonl` | JSONL (append-only) | All financial transactions |
| `balance.json` | JSON | Current balance and lifetime totals |
| `assets.json` | JSON | Fleet/equipment registry |
| `trade_orders.json` | JSON | Open/completed trade orders |
| `sessions.json` | JSON | Trading session history |
| `budgets.json` | JSON | Budget definitions and tracking |
| `opportunities.json` | JSON | Generated trade opportunities |
| `positions.json` | JSON | Commodity trade positions |
| `credits.json` | JSON | Receivables and payables |
| `hauls.json` | JSON | Cargo transport records |
| `inventory.json` | JSON | Warehouse inventory |
| `production_runs.json` | JSON | Production/crafting logs |
| `planned_orders.json` | JSON | Purchase and sale orders |
| `group_sessions.json` | JSON | Group session history |
| `guid_map.json` | JSON | Commodity GUID-to-name cache |
| `market_cache.db` | SQLite | UEX market data cache |
| `sync_cursor.json` | JSON | SC_LogReader sync position |
