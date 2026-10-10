# SC_Accountant Current Scope Snapshot for SCBridge

Date: 2026-06-28
Purpose: preserve the current local `SC_Accountant` scope before reducing the
local skill to a smaller player-local ERP/accounting assistant. The larger
functions called out here are candidates for the future SCBridge accountant,
which is expected to become the full "big brother" implementation.

This is a scope log only. It records the current working tree and does not imply
that the local skill should keep every feature listed below.

## Snapshot Baseline

- Current runtime class: `SC_Accountant`
- Current source version: `4.8.0.0`
- Current Star Citizen target: `4.8.0`
- Current module description: solo-player accounting for Star Citizen tracking
  income, expenses, commodity and item trades, investment positions, trade
  opportunities, hauling runs, asset registry, and a standalone dashboard.
- Optional sibling integrations:
  - `SC_LogReader`: auto-imports local game-log events into the ledger.
  - `UEXCorp`: optional ship price lookup during asset registration.
  - UEX public market API: commodity prices, route data, terminal data, vehicle
    prices, and generated opportunities through `MarketData`.
- Existing worktree note: the accountant tree already contains uncommitted
  version/documentation changes from the prior 4.8.0 alignment work. This
  snapshot reflects the files as they are in the working tree on this date.

## Desired Local Skill Boundary

The narrowed local accountant should behave like a modern ERP-style personal
finance module, but restricted to the player's own local economy.

Keep local:

- Local transaction ledger.
- Manual income and expense recording.
- Commodity/item purchase and sale recording as local transactions.
- Auto-import from `SC_LogReader` where the data is directly observable from
  the player's own local game log.
- Current balance and lifetime income/expense totals.
- Income statement, balance sheet, cash-flow style reporting.
- Asset registry for player-owned ships, vehicles, components, equipment, and
  blueprint unlocks.
- Local-only planning and analytics based on owned data, such as break-even,
  activity ROI, and simple what-if calculations.
- Standalone local dashboard for ledger, assets, financial statements, and
  player-local analytics.

Remove from local / preserve for SCBridge:

- Sales orders.
- Buy orders.
- Loans, receivables, payables, debts, or banking workflows.
- Market-facing features, including external market prices, trade-route
  recommendations, futures/opportunities, and market-value P&L.
- Corporation, group, cross-player, shared-ledger, or cloud-backed accounting.

## Active Runtime Managers

Currently initialized in `prepare()`:

- `AccountantStore`: JSON/JSONL persistence and local data access.
- `GuidResolver`: GUID/name cache for game-log item/commodity resolution.
- `MarketData`: SQLite cache plus UEX API fetchers.
- `FuturesManager`: generated trade opportunities from market routes.
- `PositionManager`: commodity positions, FIFO closing, unrealized/realized P&L.
- `HaulManager`: cargo haul log with cost/revenue summary.
- `AssetManager`: fleet/equipment/blueprint registry and asset transactions.
- `PlanningEngine`: break-even, activity ROI, and what-if analysis.
- `AccountantServer` / `AccountantWindow`: FastAPI dashboard plus browser/window
  launcher when optional dependencies are available.

Dormant or incomplete manager references:

- `_credits`, `_inventory`, and `_production` are cleared on unload and have
  wrapper methods, but no active manager classes are imported or initialized in
  the current runtime.
- Historical docs mention Banking, Orders, Group Events, Inventory, and
  Production tabs. The current dashboard HTML exposes only Balance Sheet,
  Operations, Ledger, My Assets, Portfolio, Opportunities, Statistics, and
  About.

## Current Data Models

Local/core models:

- `Transaction`: ledger entry with category, type, amount, description,
  location, tags, source, trade/session linkage, item fields, asset linkage,
  and activity classification.
- `Budget`: category budget with period start/end and allocation.
- `TradingSession`: local session start/end, starting balance, notes.
- `AccountBalance`: current balance, lifetime income, lifetime expenses.
- `Asset`: player-owned ship/vehicle/component/equipment/blueprint record,
  purchase price, market estimate, location, status, sale data, insurance claim
  amount, and linked transaction.

SCBridge candidate models:

- `TradeOrder`: buy/sell order with target price/location and completion data.
- `Opportunity`: generated market trade route/future from UEX route data.
- `Position`: commodity investment position with current market price,
  unrealized P&L, FIFO close data, and realized P&L.
- `Haul`: cargo transport operational record. This is local-player data, but
  should be reviewed during the split because SCBridge may need the richer
  version for org-scale logistics.

## Current Store Surface

Core/local persistence:

- Transactions: append, query, update, delete.
- Balance: get/save current balance.
- Sync cursor: track imported `SC_LogReader` event position.
- Assets: save/query/get/delete.
- Budgets and sessions: save/query active or historical records.

SCBridge candidates:

- Trade orders: save/query/get.
- Opportunities: save/bulk save/query/get/delete expired.
- Positions: save/query/get.
- Hauls: save/query/get.

Historical README storage list also mentions `credits.json`, `inventory.json`,
`production_runs.json`, `planned_orders.json`, and `group_sessions.json`; these
are not represented by active manager classes in the current source snapshot.

## Current Voice Tool Surface

Decorated active `@tool` methods:

- `record_transaction`
- `record_commodity_purchase`
- `record_commodity_sale`
- `query_transactions`
- `get_balance`
- `sync_trade_log`
- `get_best_trades`
- `get_commodity_prices`
- `get_income_statement`
- `get_balance_sheet`
- `register_asset`
- `update_asset`
- `sell_asset`
- `delete_asset`
- `open_accounting_window`
- `close_accounting_window`
- `get_break_even`
- `get_activity_roi`
- `what_if`

Undecorated methods still present in `main.py`:

- Trade orders: `create_trade_order`, `complete_trade_order`,
  `cancel_trade_order`, `list_trade_orders`.
- Sessions: `start_trading_session`, `end_trading_session`,
  `get_session_status`.
- Budgets: `set_budget`, `check_budget`.
- Market refresh: `refresh_market_data`.
- Opportunities: `list_opportunities`, `accept_opportunity`,
  `dismiss_opportunity`.
- Positions: `list_positions`, `get_portfolio_summary`, `close_position`,
  `adjust_position`.
- Credits: `create_credit`, `record_payment`, `list_credits`,
  `get_credit_summary`, `write_off_credit`.
- Hauling: `log_haul`, `complete_haul`, `list_hauls`,
  `get_hauling_summary`.
- Inventory stubs: `report_inventory`, `get_inventory`.
- Production stubs: `log_production`, `get_production_summary`.
- Fleet list/summary: `list_fleet`, `get_fleet_summary`.
- Cash flow: `get_cash_flow`.

Important prompt/config drift:

- `default_config.yaml` advertises "20" voice tools but lists more than 20
  names.
- The prompt references `create_planned_order`, `list_planned_orders`,
  `start_group_session`, and `stop_group_session`, but the current source has
  `create_trade_order`, `list_trade_orders`, `start_trading_session`, and
  `end_trading_session`, and those are not decorated with `@tool`.
- Complexity-tier prompt text still references credit and hauling tools even
  though credit managers are not active.

## Current Dashboard Surface

Current tabs in `accountant_ui/static/index.html`:

- Balance Sheet
- Operations
- Ledger
- My Assets
- Portfolio
- Opportunities
- Statistics
- About

Current dashboard API endpoints:

- `GET /api/balance`
- `GET /api/network`
- `GET /api/transactions`
- `GET /api/income-statement`
- `GET /api/balance-sheet`
- `GET /api/cash-flow`
- `GET /api/fleet`
- `GET /api/fleet/summary`
- `GET /api/positions`
- `GET /api/opportunities`
- `POST /api/opportunities/refresh`
- `GET /api/locations`
- `GET /api/player-location`
- `GET /api/categories`
- `POST /api/transactions`
- `POST /api/fleet`
- `POST /api/balance`
- `POST /api/positions`
- `POST /api/sales`
- `PUT /api/transactions/{txn_id}`
- `DELETE /api/transactions/{txn_id}`
- `PUT /api/fleet/{asset_id}`
- `DELETE /api/fleet/{asset_id}`
- `PUT /api/positions/{pos_id}`
- `GET /api/statistics`
- `GET /api/ships`
- `POST /api/reset`
- `GET /api/version`
- Static routes: `/`, `/favicon.ico`, `/static/{filename:path}`

SCBridge candidate dashboard areas:

- Portfolio tab and `/api/positions`, if retaining only market-valued
  investment positions in SCBridge.
- Opportunities tab and `/api/opportunities`, including refresh, locations, and
  player-location filtering.
- UEX-backed ship/vehicle market valuation.
- Any future Orders, Banking, Group Events, Inventory, and Production tabs from
  historical docs.

## Current Market and External Data Features

`MarketData` currently handles:

- UEX commodity refresh.
- Terminal refresh.
- Terminal status refresh, including stock/full-inventory filtering.
- Price refresh by all commodities or a named commodity.
- Route refresh by all commodities or a named commodity.
- Vehicle price refresh and ship/vehicle price lookup.
- Commodity name index and terminal location listing.
- Best trade route lookup.

SCBridge preservation value:

- These functions are the natural base for the SCBridge accountant's market and
  trading intelligence.
- They should be removed or disabled from the narrowed local skill if the local
  boundary excludes markets.

## Current Auto-Sync Behavior

`SC_LogReader` event-log sync currently imports local observed events:

- `shop_buy` -> `item_purchase`
- `shop_sell` -> `item_sale`
- `commodity_buy` -> `commodity_purchase`
- `commodity_sell` -> `commodity_sale`
- `reward_earned` -> `mission_reward`
- `blueprint_received` -> asset registration with asset type `blueprint`

The sync also:

- Uses a sync cursor and fingerprint deduplication.
- Updates balance after imported transactions.
- Opens/closes positions for commodity purchases/sales when `PositionManager`
  is active.
- Checks opportunity fulfillment against imported trades when `FuturesManager`
  is active.

For the narrowed local skill, keep the direct local transaction/asset imports,
but remove the market position and opportunity fulfillment side effects if
positions/opportunities move to SCBridge.

## Candidate Split Plan

1. Freeze this file as the source-of-truth scope log for the current accountant.
2. Decide the local accountant boundary in terms of data files and dashboard
   tabs, not just voice tools.
3. Remove or disable SCBridge-bound features from the local prompt first so the
   AI stops suggesting them.
4. Remove dashboard tabs/endpoints for market, positions, opportunities, orders,
   credits, inventory, production, and group features as agreed.
5. Remove runtime managers and background loops that are only needed for market
   intelligence or SCBridge-scale accounting.
6. Keep local financial statements and assets working against existing user data.
7. Preserve reusable SCBridge modules before deletion or movement, especially
   `market_data.py`, `futures.py`, `positions.py`, trade-order store/model code,
   and any historical docs describing planned order, banking, inventory,
   production, and group-session behavior.

