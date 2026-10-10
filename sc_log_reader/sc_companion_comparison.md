# SC_LogReader ↔ SC-Companion Cross-Reference

Comparison of Game.log parsing between:
- **SC_LogReader** (`skills/sc_log_reader/`) — Python/WingmanAI
- **SC-Companion** (`C:/Users/larse/PycharmProjects/sc-companion/`) — Go/Wails

Use the checkboxes to track what you decide to implement.

---

## 1. Add to SC_LogReader (SC-Companion has it, SC_LogReader doesn't)

### Quantum Travel
- [x] **`qt_arrived`** — "Quantum Drive has arrived at final destination"
  - Parser: `"Quantum Drive has arrived at final destination" in line` (not SHUDEvent)
  - Data: none
  - Notes: Clean in-world signal. Good immersion trigger (copilot reacts to jump landing).

### Economy / Law
- [X] **`fined`** — "Fined X UEC" SHUDEvent
  - Parser: `"Fined" in line` in SHUDEvent block
  - Regex: `r'"Fined\s+([\d,]+)\s+UEC'` → `amount`
  - Data: `amount` (string, may contain commas)

- [x] **`transaction_complete`** — "Transaction Complete" SHUDEvent
  - Parser: `"Transaction Complete:" in line` in SHUDEvent block
  - Data: none (fires for both buy and sell — no distinction at this log level)
  - Notes: sc_log_reader already handles underlying `shop_buy`/`shop_sell` with confirmation. This is the visible player notification on top of that. Useful if you want to react to the UI feedback moment specifically.

### Health / Status
- [X] **`incapacitated`** — "Incapacitated:" SHUDEvent
  - Parser: `"Incapacitated:" in line` in SHUDEvent block
  - Data: none
  - Notes: Distinct from `injury` — player is downed, not just hurt.

### Social / Economy
- [X] **`money_sent`** — "You sent PlayerName:" SHUDEvent (multi-line)
  - Parser: matches `Added notification "You sent ([^:]*?):\s*$` then accumulates next line for amount
  - Data: `recipient`, `amount` (aUEC)
  - Notes: Requires multi-line accumulation — the amount appears on the next log line (`\d+ aUEC`). More complex than other events. The tailer struct in sc-companion has a `pendingNotification` field specifically for this.

### Game Events
- [X] **`blueprint_received`** — "Received Blueprint: name:" SHUDEvent
  - Parser: `"Received Blueprint:" in line` in SHUDEvent block
  - Regex: `r'"Received Blueprint:\s*(.+?):'` → `name`
  - Notes: 4.7+ content.

- [x] **`fatal_collision`** — `<FatalCollision>` internal log (not SHUDEvent)
  - Parser: `"<FatalCollision>" in line` outside SHUDEvent block
  - Regex: `r'<FatalCollision> Fatal Collision occured for vehicle (\S+).*Zone:\s*([^,\]]+)'` → `vehicle`, `zone`
  - Notes: Non-SHUDEvent source. Vehicle name in log format (e.g., `AEGS_Gladius_...`), not cleaned.

### Insurance
- [x] **`insurance_claim`** — `CWallet::ProcessClaimToNextStep` internal log
  - Parser: `"CWallet::ProcessClaimToNextStep" in line` outside SHUDEvent block
  - Regex: `r'New Insurance Claim Request - entitlementURN: ([^,]+), requestId\s*:\s*(\d+)'` → `urn`, `request_id`

- [x] **`insurance_claim_complete`** — `CWallet::RmMulticastOnProcessClaimCallback` internal log
  - Parser: `"CWallet::RmMulticastOnProcessClaimCallback" in line`
  - Regex: `r'Claim Complete - entitlementURN: ([^,]+), result:\s*(\d+)'` → `urn`, `result`
  - Notes: `result` value 1 = success (unverified — needs log confirmation).

---

## 2. Bugs / Pattern Mismatches to Investigate

### In SC-Companion — likely broken patterns

- [ ] **`rewards_earned` capitalisation** — sc-companion matches `"You've Earned:\s*(\d+)\s+Rewards"` (capital E, capital R).
  - SC_LogReader verified sample (TODO): `"You've earned: 15,000 rewards"` — all lowercase.
  - **Action**: Verify against a real Game.log. sc-companion's pattern likely never fires. sc_log_reader's `"You've earned:"` is probably correct.

- [ ] **`refinery_complete` pattern** — sc-companion matches `"A Refinery Work Order has been Completed at"`.
  - SC_LogReader verified sample (TODO): `"Refinery Work Order(s) Completed at CRU-L1"`.
  - sc-companion's specific phrase `"has been Completed"` is NOT in the actual notification text.
  - **Action**: Verify against a real Game.log. sc_log_reader's broader `"Refinery Work Order"` match is more robust.

### Patterns that differ — investigation needed

- [x] **`player_login` / `session_start` log line** — INVESTIGATED (test logs confirmed).
  - `AccountLoginCharacterStatus_Character` format: `Character: createdAt ... geid 201990621533 ... name Mallachi - state STATE_CURRENT` — sc_log_reader's `name\s+(\S+)` and `geid\s+(\S+)` regexes are correct.
  - sc-companion's `nickname="X" playerGEID=Y` is a DIFFERENT log line from a different module. Both may exist; sc_log_reader's line fires first. **No changes needed.**

- [x] **`join_pu` vs `server_joined` log line** — INVESTIGATED (test logs confirmed).
  - Two separate log lines appear at the same timestamp:
    1. `[+] [CIG] {Join PU} [0] id[...] status[1] port[64369]` — sc_log_reader matches this (shard = `[0]` or `[1]`, the index)
    2. `[Notice] <Join PU> address[34.38.171.216] port[64369] shard[pub_euw1b_11135423_170] locationId[...]` — sc-companion matches this (gets real shard name)
  - sc_log_reader is extracting the join index `[0]`/`[1]` as shard, NOT the actual shard name. **Fix**: match the second `<Join PU>` line to capture the real shard ID.
  - **Fix applied (v0.1.28)**: sc_log_reader now matches `<Join PU>` address line to extract real shard name. `{Join PU}` line kept as fallback.

---

## 3. SC_LogReader Advantages (for reference — sc-companion lacks these)

These are already implemented in SC_LogReader. Listed here for awareness if sc-companion needs parity.

| Feature | SC_LogReader | SC-Companion |
|---------|-------------|-------------|
| Contract MissionId extraction | ✅ | ❌ |
| `contract_shared`, `contract_available` | ✅ | ❌ |
| Objectives (new / complete / withdrawn) | ✅ | ❌ |
| Hangar sequencing (access / permit / entered / exited) | ✅ | ❌ |
| QT calibration (started / complete / group) | ✅ | ❌ |
| Trade tracking (shop buy/sell/confirm, commodity buy/sell) | ✅ | ❌ |
| Med bed heal (body part tracking) | ✅ | ❌ |
| Emergency services | ✅ | ❌ |
| Party invite / incoming call | ✅ | ❌ |
| Bleeding / fuel low / vehicle impounded | ✅ (v0.1.27) | ❌ |
| Party member joined / left | ✅ (v0.1.27) | ❌ |
| Journal entries | ✅ | ❌ |
| Monitored space down / restored | ✅ | ❌ |
| Restricted area | ✅ | ❌ |
| User login (from "User Login Success" line) | ✅ | ❌ |
| Ship channel filtering (heuristic — not all channels) | ✅ `_is_ship_channel()` | ❌ fires on ALL channels |
| Ship name cleaning (manufacturer codes → readable) | ✅ `Avenger Titan` | ❌ `AEGS_Avenger_Titan` |
| State tracking (location, ship, armistice, etc.) | ✅ | ❌ |
| Session catch-up replay from last login | ✅ | ❌ tails from EOF only |
| Multi-environment monitoring (LIVE/PTU/EPTU) | ✅ | ❌ single path |
| Layer 2 derived events (location_arrived, zone_entered_hangar, etc.) | ✅ | ❌ |

---

## 4. Already Implemented in Both (for completeness)

| Event | SC_LogReader | SC-Companion | Notes |
|-------|-------------|-------------|-------|
| Contract accepted / complete / failed | ✅ | ✅ | sc_log_reader also extracts MissionId |
| Ship boarded / exited | ✅ `channel_change` | ✅ `ship_boarded/exited` | sc-companion name cleaning is incomplete |
| Location change | ✅ | ✅ | sc_log_reader adds human-readable name + star system |
| Quantum route set | ✅ | ✅ `qt_target_selected` | sc-companion extracts destination (LOCRRS codes — unreliable) |
| Jurisdiction entered | ✅ | ✅ | sc_log_reader suppresses "UEE" (noisy) |
| Armistice entered / exited | ✅ | ✅ | sc_log_reader has hangar sequencing on top |
| Monitored space entered / exited | ✅ | ✅ | |
| CrimeStat increased | ✅ (v0.1.27) | ✅ | |
| Injury | ✅ | ✅ | sc-companion uses fixed severity enum; sc_log_reader flexible |
| Vehicle impounded | ✅ (v0.1.27) | ✅ | Same pattern, both extract reason |
| Refinery complete | ✅ | ⚠️ pattern likely broken | sc-companion's specific phrase doesn't match actual notification |
| Reward earned | ✅ | ⚠️ capitalisation likely wrong | sc-companion may never match |
