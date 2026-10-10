# SC_LogReader Movement Ledger Reconciliation - 2026-06-27

## Context

Recent June 2026 PTU and LIVE Star Citizen logs were reviewed against the intended `sc_log_reader` mission:

- collect movement across areas
- collect movement in economy
- collect movement in work / missions
- collect movement in reputation
- collect movement in inventory and item ownership

Here, movement means information about the relation between the player and the world: entering or leaving areas, accepting or completing missions or objectives, rewards, purchases, sales, money movement, item movement, blueprint gains, fines, and reputation-affecting events.

## Log quality findings

The logs are good enough for a confidence-based movement ledger, not a perfect authoritative audit trail.

Area and mission/work signals are the strongest. Economy signals are usable but noisy. Inventory signals are abundant but need classification. Reputation signals are limited mostly to CrimeStat/fines when present.

The largest confirmed noise source is economy notifications. One real transaction or reward can produce several lines:

- backend request
- backend response
- HUD notification
- bare quoted notification text
- notification lifecycle updates

The skill should treat these lines as evidence and reconcile them into one movement entry where possible.

## Implemented in this pass

### Shop / economy reconciliation

The parser now recognizes both June 2026 shop dialects:

- `CEntityComponentShopUIProvider`
- `CEntityComponentShoppingProvider`

This matters because newer `ShoppingProvider` purchases can appear as:

- `SendStandardItemBuyRequest`
- `RmShopFlowResponse` with only `playerId` and `result[Success]`
- HUD `Transaction Complete`

The logic layer now:

- resolves old ShopUI confirmations by exact shop/kiosk/type match
- resolves ShoppingProvider confirmations by recent same-player pending request when shop/kiosk/type is missing
- writes one confirmed `shop_buy` / `shop_sell` event-log entry
- suppresses nearby `Transaction Complete` entries when they only confirm a trade already recorded

Real-log smoke result after the fix:

- PTU current: `shop_buy: 8`, `transaction_complete: 0`
- LIVE Jun 20 sample: `shop_buy: 7`, `transaction_complete: 0`, `reward_earned: 9`

### Movement metadata

`EventLogEntry` now has movement reconciliation metadata:

- `movement_category`
- `movement_verb`
- `confidence`
- `fingerprint`
- `source_events`

Current mapped categories:

- `area`
- `economy`
- `work`
- `inventory`
- `reputation`

This does not replace existing `event_type` values, so existing event queries remain compatible.

### Reward notification de-noising

Reward notifications now extract common HUD context when available:

- `notification_id`
- `mission_id`
- `objective_id`

Duplicate reward notifications are suppressed using reward fingerprints, so repeated HUD lifecycle lines are less likely to create duplicate reward entries.

### Reward bundle reconciliation follow-up

Implemented 2026-06-28 in `StateLogic`:

- groups nearby `reward_earned` and `blueprint_received` components into one canonical `mission_reward` entry
- uses direct non-zero `mission_id` when present
- falls back to a recently completed contract when CIG logs zeroed reward MissionIds
- keeps component entries for compatibility while adding bundle metadata under `data.money`, `data.items`, and `data.blueprints`
- flushes bundles before the next unrelated event, preserving EventLog append order for restart dedup watermarks

### Regression tests added

Added tests covering real June-style snippets:

- ShoppingProvider purchase request + response
- ShoppingProvider purchase writes one trade and suppresses HUD confirmation
- ShopUIProvider purchase keeps exact-match high confidence
- noisy reward notification stack writes one reward movement

## Current reward support status

The skill can distinguish these reward forms as separate entries:

### aUEC / money reward

Parsed as:

- `event_type`: `reward_earned`
- `movement_category`: `economy`
- `movement_verb`: `rewarded`
- `amount_auec`: positive value

Known patterns:

- `Awarded 500 aUEC`
- `You've earned: 15,000`

### Blueprint reward

Parsed as:

- `event_type`: `blueprint_received`
- `movement_category`: `inventory`
- `movement_verb`: `received`
- `item_name`: blueprint name

Known pattern:

- `Received Blueprint: <name>`

### Item reward

Partially parsed as:

- `event_type`: `reward_earned`
- `movement_category`: `economy`
- `movement_verb`: `rewarded`
- `item_name`: item name

Known pattern:

- `You've earned: <item name>`

This is still weaker than money and blueprint rewards. If CIG logs item rewards through a different notification format, the current parser may miss or misclassify them.

## Reward bundles follow-up status

Status 2026-06-28: the canonical `mission_reward` entry is now implemented.

Current behavior:

- money reward -> component `reward_earned` entry plus bundled `data.money.amount_auec`
- blueprint reward -> component `blueprint_received` entry plus bundled `data.blueprints[]`
- item reward -> component `reward_earned` entry plus bundled `data.items[]` when the known item pattern appears
- bundle confidence is `high` with a direct non-zero reward `mission_id`, `medium` when attached to a recent `contract_complete`, and `low` for timestamp-only grouping

Remaining work:

- live-log validation against more reward variants
- decide whether downstream consumers should prefer `mission_reward` bundles or legacy component rows
- update SC_Accountant import logic if it should consume bundles instead of `reward_earned` components

## Verification from this pass

Commands run:

```powershell
python -m pytest skills\sc_log_reader\tests -q
python -m compileall -q skills\sc_log_reader\parser.py skills\sc_log_reader\logic.py skills\sc_log_reader\release_version\parser.py skills\sc_log_reader\release_version\logic.py skills\sc_log_reader\tests\test_movement_reconciliation.py
python -m ruff check skills\sc_log_reader\parser.py skills\sc_log_reader\logic.py skills\sc_log_reader\release_version\parser.py skills\sc_log_reader\release_version\logic.py skills\sc_log_reader\tests\test_movement_reconciliation.py
```

Results:

- `39 passed`
- compile checks passed
- Ruff passed; only warning was `.ruff_cache` write access denied

## Files changed in this pass

Source skill:

- `event_log.py`
- `logic.py`
- `parser.py`
- `tests/test_movement_reconciliation.py`

Release copy synced:

- `release_version/event_log.py`
- `release_version/logic.py`
- `release_version/parser.py`
