# SC_Accountant — Live Test Checklist

**Version:** 4.7.2 (qualified against Star Citizen 4.7.2)
**Author:** Mallachi

---

## 1. Skill Activation & Setup

- [x] Skill activates without errors in Wingman log
- [x] Dashboard auto-opens in browser (port 7863)
- [x] Balance header shows correct aUEC value
- [x] Status indicator shows "Connected"
- [x] Period selector (today/week/month/quarter/year/all) works

---

## 2. Voice Tools — Core Accounting

### record_transaction
- [x] Record an expense: "Record a 500 aUEC fuel expense at Lorville"
- [x] Record income: "Record 10,000 aUEC mission reward"
- [x] Verify balance updates after each
- [x] Verify dashboard refreshes after voice command (SSE)

### get_balance
- [x] "What's my balance?" — returns current balance + lifetime totals

### sync_trade_log
- [ ] "Sync my trade log" — syncs from SC_LogReader (requires SC_LogReader active)
- [ ] Verify new transactions appear on Ledger tab
- [ ] Verify "no SC_LogReader" message if sibling skill not loaded

---

## 3. Voice Tools — Trade Orders & Sessions

### create_trade_order
- [ ] "Create a buy order for 100 SCU of Laranite at 28 aUEC"
- [ ] "Create a sell order for Quantanium"

### list_trade_orders
- [ ] "Show my open trade orders"

### start_trading_session / get_session_status
- [ ] "Start a trading session"
- [ ] "How's my session going?" — shows session P&L
- [ ] Make some trades, verify session tracks them

### set_budget
- [ ] "Set a monthly trading budget of 100,000 aUEC"

---

## 4. Voice Tools — Planned Orders

### create_planned_order
- [ ] "I plan to buy 200 SCU of Agricium"
- [ ] "I plan to sell my Prospector" (should validate asset exists)
- [ ] Invalid sale order (item not owned) — should be rejected

### list_planned_orders
- [ ] "Show my planned orders"
- [ ] Verify fulfillment progress updates when matching trades come in

### Auto-fulfillment
- [ ] Buy a commodity that matches an open purchase order
- [ ] Verify order status moves to partial/fulfilled
- [ ] Verify over-fulfillment is capped at ordered quantity

---

## 5. Voice Tools — Market Intelligence

### get_best_trades
- [ ] "What are the best trades right now?"
- [ ] "Best trades in Stanton?" (system filter)
- [ ] "Best trades at Lorville?" (location filter)

### get_commodity_prices
- [ ] "What's the price of Laranite?"

### refresh_market_data
- [ ] "Refresh market data" — triggers full UEX refresh

---

## 6. Voice Tools — Opportunities (Futures)

### list_opportunities
- [ ] "Show available opportunities"
- [ ] Verify opportunities have been auto-generated (if futures_auto_generate = true)

### accept_opportunity
- [ ] "Accept that Laranite opportunity" — creates linked trade order

### dismiss_opportunity
- [ ] "Dismiss that opportunity" — marks it dismissed

### Min Profit per SCU filter
- [ ] Set "Minimum Profit per SCU" to 100 in settings
- [ ] Refresh market data
- [ ] Verify no opportunities with margin < 100 aUEC/SCU are generated

---

## 7. Voice Tools — Positions & Portfolio

### list_positions
- [ ] "Show my open positions"

### get_portfolio_summary
- [ ] "How's my portfolio?"

### close_position
- [ ] "Close my Laranite position at 30 aUEC per SCU"
- [ ] Verify realized P&L is calculated

### Auto-tracking
- [ ] Buy a commodity — verify position auto-opens (if position_auto_track = true)
- [ ] Sell that commodity — verify position auto-closes via FIFO

---

## 8. Voice Tools — Fleet & Assets

### register_asset (via voice)
- [ ] "Register my Prospector, it cost 2.1 million"
- [ ] If UEXCorp loaded: verify price auto-populates when not specified

### update_asset
- [ ] "Update my Prospector's location to Port Olisar"

### list_fleet
- [ ] "Show my fleet"

### get_fleet_summary
- [ ] "Give me a fleet summary" — total value, count by type

---

## 9. Voice Tools — Financial Statements

### get_income_statement
- [ ] "Show my income statement" / "Show my P&L"
- [ ] Verify REVENUE / COGS / OPEX / CAPEX breakdown

### get_balance_sheet
- [ ] "Show my balance sheet"
- [ ] Verify assets + cash + liabilities

### get_cash_flow
- [ ] "Show my cash flow"
- [ ] Verify operating vs investing breakdown

---

## 10. Voice Tools — Planning & Forecasting

### get_break_even
- [ ] "When will my Prospector break even?" (needs asset registered)

### get_activity_roi
- [ ] "Compare my activity ROI this month"
- [ ] Verify per-activity margin breakdown (trading, mining, etc.)

### what_if
- [ ] "What if I buy a MOLE for 5 million and earn 200k per session?"
- [ ] Verify payback period / projected ROI output

---

## 11. Voice Tools — Credits (Loans)

### create_credit
- [ ] "I lent 50,000 aUEC to PlayerX"
- [ ] "I borrowed 20,000 aUEC from PlayerY"

### record_payment
- [ ] "PlayerX paid back 10,000 aUEC"

### list_credits
- [ ] "Show my outstanding credits"

### get_credit_summary
- [ ] "Summarize my receivables and payables"

---

## 12. Voice Tools — Group Sessions

### start_group_session
- [ ] "Start a group session"

### stop_group_session
- [ ] "Stop the group session" — verify split summary

---

## 13. Voice Tools — Dashboard Control

### open_accounting_window
- [ ] "Open the accounting dashboard"

### close_accounting_window
- [ ] "Close the accounting dashboard"

---

## 14. Voice Tools — Hauling / Inventory / Production

### Hauling
- [ ] Record a haul via voice
- [ ] "Show my hauls"
- [ ] "Hauling summary"

### Inventory (stub)
- [ ] "Show my inventory"

### Production (stub)
- [ ] "Show production summary"

---

## 15. Dashboard — Balance Sheet Tab

- [ ] Summary cards display (Cash, Assets, Liabilities, Net Worth)
- [ ] Values update after transactions

---

## 16. Dashboard — Operations Tab

- [ ] Income Statement table renders (Revenue, COGS, Gross Margin, OPEX, Net)
- [ ] CAPEX breakdown section
- [ ] Cash Flow Summary section
- [ ] Period selector changes data

---

## 17. Dashboard — Ledger Tab

- [ ] Transactions table loads with pagination
- [ ] Column filters work (type, category, description, etc.)
- [ ] Click row to edit — pre-filled edit modal opens
- [ ] Edit a transaction — save, verify changes persist
- [ ] "+ Add Transaction" button — create modal works
- [ ] Category dropdown populated
- [ ] Delete transaction from edit modal

---

## 18. Dashboard — My Assets Tab

- [ ] Fleet table loads
- [ ] "+ Add Asset" button — create modal works
- [ ] Click row to edit — edit modal with pre-filled fields
- [ ] "Delete Asset" button in edit modal (with confirmation)
- [ ] Asset status badges (active/sold/destroyed)

---

## 19. Dashboard — Orders Tab

- [ ] Summary cards (purchase orders, sales orders, fulfilled, planned value)
- [ ] Orders table with progress bars (fulfilled/ordered)
- [ ] BUY/SELL badges
- [ ] "+ Create Order" modal — purchase and sale types
- [ ] Click row to edit — fulfillment history visible
- [ ] Cancel / Delete actions work

---

## 20. Dashboard — Banking Tab

- [ ] Loans table loads
- [ ] "+ New Loan" modal — lent/borrowed, interest rate, compounding period
- [ ] Click row to edit loan details
- [ ] "Record Payment" button — payment modal
- [ ] Interest accrual displays correctly
- [ ] Loan auto-settles when fully repaid

---

## 21. Dashboard — Portfolio Tab

- [ ] Open positions table loads
- [ ] Unrealized P&L column
- [ ] "+ Record Purchase" button — purchase modal
- [ ] "+ Record Sale" button — sale modal with FIFO closure
- [ ] Balance updates after purchase/sale

---

## 22. Dashboard — Opportunities Tab

- [ ] Opportunities table loads
- [ ] System dropdown filter
- [ ] Location dropdown (filtered by system)
- [ ] Ship dropdown (cargo capacity affects adjusted profit)
- [ ] "My System" option auto-detects current location
- [ ] "Refresh" button triggers market refresh
- [ ] Available SCU / Effective SCU columns display
- [ ] Est. Profit reflects ship cargo cap

---

## 23. Dashboard — Group Events Tab

- [ ] "Start Group Session" button
- [ ] Add players with names
- [ ] Percentage mode: set % per player, warning if != 100%
- [ ] Flat rate mode: set aUEC per player, shows unallocated remainder
- [ ] "Equal Split" button adapts to current mode
- [ ] "Group Buy" / "Group Sell" buttons in status bar
- [ ] Transaction table with 7 columns (matching Ledger)
- [ ] Column filters work
- [ ] Click row to edit transaction
- [ ] "Stop Session" — shows split summary
- [ ] Session history: past sessions listed when no session active
- [ ] Click past session to view detail + transactions

---

## 24. Dashboard — Statistics Tab

- [ ] Statistics page loads with data

---

## 25. Dashboard — About Tab

- [ ] About page loads with skill info

---

## 26. Cross-Cutting Concerns

### SSE Live Refresh
- [ ] Use a voice tool — dashboard refreshes without manual reload
- [ ] Open multiple browser tabs — all refresh on tool call

### Trade Announcements
- [ ] Enable "announce_trade_opportunities" in settings
- [ ] Travel to a trading location in-game
- [ ] Verify TTS announces top trades on arrival
- [ ] Verify no repeat announcement at same location

### Date Formatting
- [ ] All dates show `YYYY:MM:DD - HH:MM` consistently across tabs

### Complexity Tiers
- [ ] Set to "casual" — AI should only suggest basic tools
- [ ] Set to "industrial" — AI should suggest full toolset

### Sibling Skills
- [ ] With SC_LogReader: auto-sync works, location detection works
- [ ] Without SC_LogReader: manual entry works, sync tool shows clear message
- [ ] With UEXCorp: ship prices auto-populate on register_asset
- [ ] Without UEXCorp: falls back to manual price entry
