# SC_Accountant Evaluation Against SC_LogReader Data

Date: 2026-06-28
Scope: evaluate how well the current `SC_Accountant` fulfills the narrowed
mission when using data read from `SC_LogReader`.

Mission under evaluation:

- Collect and present player-local economic data like a compact ERP system.
- Stay limited to the player's own local economy.
- Exclude sales orders, buy orders, loans, and markets.
- Preserve larger market/order/banking functions for the future SCBridge
  accountant.

## Executive Summary

Current fit: 6/10.

`SC_Accountant` is already useful as an automated local transaction ledger for
observable game-log activity. It can import item purchases/sales, commodity
purchases/sales, money reward components, blueprint rewards, and owned ship
entry events. It can then present that data through ledger, statements, balance,
assets, and dashboard views.

It is not yet ERP-grade against the narrowed mission because the accountant
imports only a subset of the data `SC_LogReader` now writes, relies on market
and portfolio side effects that belong in SCBridge, and still has data-integrity
gaps around commodity GUID names, import deduplication, and incomplete event
coverage.

The best target for the local accountant is a verified local activity ledger:
transactions, balance changes, owned assets, rewards, penalties, and local
financial reports. It should not try to infer a complete wallet, inventory, or
market position from `Game.log` alone.

## Follow-up Implementation Note

After this evaluation, the import policy was updated so `SC_Accountant` imports
only `sc_logreader_eventlog_LIVE.jsonl` and
`sc_logreader_eventlog_HOTFIX.jsonl`. `PTU`, `EPTU`, `TECH-PREVIEW`, and
other test-environment logs are ignored. LIVE and HOTFIX share one
timestamp/count cursor and one local ledger, matching the way the game
treats those economies.

## What SC_LogReader Provides

Strong economic signals:

- Confirmed item shop purchases and sales:
  - `shop_buy`
  - `shop_sell`
  - confirmed through `shop_transaction_result`
  - amount, quantity, shop/kiosk, item GUID/name, player ID
- Commodity purchases and sales:
  - `commodity_buy`
  - `commodity_sell`
  - amount, quantity, shop/kiosk, resource GUID, player ID
- Mission/reward money:
  - legacy component row: `reward_earned`
  - canonical bundled row: `mission_reward`
  - amount, mission context when correlated, items, blueprints, confidence
- Blueprint rewards:
  - `blueprint_received`
  - blueprint name and notification context
- Owned ship entry:
  - `own_ship_entered`
  - ship name inferred from ship channel ownership

Partial or contextual economic signals:

- `fined`: amount can be parsed as negative aUEC.
- `money_sent`: amount and recipient can be parsed as outgoing transfer.
- `insurance_claim` / `insurance_claim_complete`: asset lifecycle context but no
  reliable cost in the current parser.
- `cargo_transfer`: movement context, entity count, location, and kiosk context,
  but no itemized value.
- `refinery_submitted` / `refinery_complete`: work context, but currently not
  enough cost/output data for financial accounting.
- `attachment_received`: inventory/equipment context, but no price.
- `location_arrived`, `ship_entered`, `ship_exited`, `jurisdiction_change`, and
  other area/work events: useful for context, not direct accounting entries.

Known unavailable or unreliable data from `Game.log`:

- Verified current wallet balance.
- Most fuel, repair, ammo, medical, insurance, hangar, and restock expenses.
- Complete bounty/combat mission payouts when CIG does not emit a money reward
  notification.
- Full cargo inventory contents and valuation.
- True market prices, demand, stock, or opportunity data.
- Loans, receivables, payables, buy orders, and sales orders.
- Complete ownership history for ships unless the player enters them or reports
  them manually.

## What SC_Accountant Currently Imports

Current import path:

- Reads every `sc_logreader_eventlog_*.jsonl` file from the `SC_LogReader`
  generated files directory.
- Sorts candidate entries by timestamp.
- Uses a timestamp/count cursor.
- Converts selected events into `Transaction` rows.
- Updates balance immediately for imported transactions.
- Creates blueprint assets from `blueprint_received`.
- Creates zero-value ship assets from `own_ship_entered`.
- Opens/closes portfolio positions and checks opportunity fulfillment for
  commodity trades.

Converted into transactions:

- `shop_buy` -> `item_purchase`
- `shop_sell` -> `item_sale`
- `commodity_buy` -> `commodity_purchase`
- `commodity_sell` -> `commodity_sale`
- `reward_earned` -> `mission_reward`

Imported as assets:

- `blueprint_received` -> zero-value `Asset(asset_type="blueprint")`
- `own_ship_entered` -> zero-value `Asset(asset_type="ship")`

Ignored despite useful local accounting value:

- `mission_reward` canonical bundles
- `fined`
- `money_sent`
- `insurance_claim`
- `insurance_claim_complete`
- `cargo_transfer`
- `refinery_submitted`
- `refinery_complete`
- `attachment_received`
- most work/area context events

## Main Fit Problems

### 1. Canonical reward bundles are not consumed

`SC_LogReader` now writes canonical `mission_reward` bundle entries. These group
money rewards, item rewards, blueprint rewards, mission name, mission ID,
notification IDs, and confidence into one richer event.

`SC_Accountant` still imports the older `reward_earned` component rows. It gets
money, and it separately registers blueprints, but it misses the cleaner mission
bundle as the accounting source of truth.

Impact:

- Mission reward descriptions are weaker.
- Item rewards are not represented well.
- Reward confidence/correlation is lost.
- Future reward variants will be harder to account for correctly.

Recommendation:

- Prefer `mission_reward` as the import source.
- Use `data.money.amount_auec` or top-level `amount_auec` for the transaction.
- Register bundled blueprints from `data.blueprints`.
- Record item rewards as non-financial local asset/inventory notes only if the
  local skill keeps such a concept.
- Avoid double-importing the component `reward_earned` rows when the bundle is
  present.

### 2. Star Citizen environment handling

Status: addressed for future imports on 2026-06-28.

The accountant now imports only `LIVE` and `HOTFIX` event logs and ignores
PTU, EPTU, TECH-PREVIEW, and other test environments. LIVE and HOTFIX are
treated as one economy with one local ledger and one timestamp/count cursor.

Impact:

- Existing ledgers that already imported PTU entries before this change may need
  cleanup or reset.
- Future imports should no longer let PTU/test credits advance the LIVE/HOTFIX
  sync cursor or affect reports.

Recommendation:

- If historical PTU pollution exists, provide a cleanup path or manual reset.
- Consider storing source environment on imported transactions later for audit
  visibility, even though LIVE/HOTFIX are treated as one economy.

### 3. Commodity identity depends on weak GUID resolution

`SC_LogReader` commodity trades expose a resource GUID, not a reliable commodity
name. `GuidResolver` currently has only a stub built-in map. The market layer can
list commodity names, but the current `_update_guid_map_from_market()` only logs
that names exist and does not add GUID mappings.

Impact:

- Commodity purchases and sales may show as `Unknown (<guid>...)`.
- Positions and reports can fragment by unknown GUID label.
- If markets are stripped from local accountant, commodity name quality gets
  worse unless a non-market mapping source replaces it.

Recommendation:

- Keep a local GUID/name mapping file independent of market features.
- Log unknown commodity GUIDs for later mapping.
- Consider feeding the mapping from SCBridge later, but do not make local
  accounting depend on live market features.

### 4. Import deduplication is too coarse

The accountant dedupes auto imports by:

`timestamp:category:amount`

Impact:

- Two same-second transactions with the same category and amount can collapse
  into one.
- The `SC_LogReader` event fingerprint is ignored even though it is a better
  import key.
- Delayed canonical bundle rows are a future risk if the accountant starts
  consuming `mission_reward`, because bundle rows can be appended after their
  component rows.

Recommendation:

- Store the `SC_LogReader` event fingerprint on imported transactions, likely in
  tags, notes, or a dedicated source reference field.
- Deduplicate by event fingerprint when present.
- Consider an append-position cursor per event-log file instead of only a
  timestamp/count cursor.

### 5. Useful local expense events are ignored

`SC_LogReader` can parse `fined` and `money_sent` with negative `amount_auec`.
The accountant currently ignores them.

Impact:

- Local balance and expenses miss observable outgoing aUEC movements.
- The ledger under-reports reputation/law costs and player transfers.

Recommendation:

- Import `fined` as an expense category such as `fines`.
- Import `money_sent` as a player transfer or other expense until a better
  category exists.
- Use top-level `amount_auec` as the canonical signed value where present.

### 6. Market and portfolio side effects exceed the narrowed mission

On imported commodity trades, the accountant currently:

- refreshes market data for the commodity,
- opens/closes portfolio positions,
- checks opportunity fulfillment.

These are useful in the larger SCBridge accountant but conflict with the local
mission if markets and investment positions are out of scope.

Impact:

- The local accountant behaves like a trader/market assistant, not just a
  player-local ERP ledger.
- Reports include concepts like market value and unrealized P&L that are not
  local observed economy facts.

Recommendation:

- Keep the transaction import.
- Remove or disable market refresh, positions, opportunities, and market-valued
  reporting from the local skill.
- Preserve those modules for SCBridge.

## Scorecard

Data capture from SC_LogReader: 7/10

- Strong for observed purchases, sales, rewards, blueprints, and ship entry.
- Weak for unlogged expenses, wallet verification, inventory valuation, and
  full mission payouts.

Current accountant import coverage: 5/10

- Good for core trade and money reward components.
- Misses canonical reward bundles, fines, money sent, environment separation,
  and stronger fingerprints.

ERP-style local presentation: 6/10

- Ledger, balance, statements, assets, and dashboard are a solid base.
- Current UI still includes Portfolio and Opportunities, which are SCBridge
  concepts under the narrowed mission.
- There is no import-quality/audit view showing ignored events, unknown GUIDs,
  confidence, or SC environment.

Data integrity: 5/10

- Persistent store and cursor are useful.
- Environment mixing, coarse dedupe, unknown commodity names, and market side
  effects reduce trustworthiness.

Mission alignment after removing SCBridge scope: 6/10 today, 8/10 possible

- The local skill can become strong as a personal local ledger and financial
  dashboard.
- It cannot become a complete ERP from `Game.log` alone because the game does
  not emit every economic fact.

## Recommended Local Accountant Target

The best local mission is:

> A player-local financial ledger and reporting dashboard that automatically
> imports observable `SC_LogReader` economic events, lets the user manually fill
> gaps, and clearly labels imported, manual, inferred, and unknown data.

This should include:

- Transactions.
- Current balance as locally tracked, not verified wallet truth.
- Income statement.
- Balance sheet limited to cash plus user/imported assets.
- Cash flow.
- Asset registry.
- Blueprint registry.
- Unknown GUID review.
- Import audit by event type and confidence.
- Manual entry for game-log gaps.

This should exclude from the local skill:

- Market prices.
- Trade opportunities.
- Futures.
- Portfolio/positions with market valuation.
- Buy orders and sales orders.
- Loans, receivables, payables, debts.
- Group/corporate accounting.

## Priority Fix List

1. Add `mission_reward` bundle import and suppress duplicate component imports.
2. Add environment awareness for `LIVE`/`PTU`/`HOTFIX` event logs.
3. Deduplicate by `SC_LogReader` event fingerprint.
4. Import `fined` and `money_sent` as local expenses/transfers.
5. Replace market-dependent commodity naming with a local GUID map.
6. Remove or disable market refresh, positions, opportunities, and market-value
   reporting from the local accountant.
7. Add an import audit view/report:
   - imported transactions by event type,
   - ignored but finance-relevant events,
   - unknown commodity GUIDs,
   - low/medium confidence imports,
   - active SC environment.
8. Add focused sync tests for:
   - canonical `mission_reward`,
   - duplicate reward components,
   - environment separation,
   - fines and money sent,
   - unknown commodity GUID handling,
   - no market side effects in local-only mode.

