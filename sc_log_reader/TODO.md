# SC_LogReader TODO

## Current Status: v4.8.3.4 - qualified against Star Citizen 4.8.3

Versioning now mirrors the SC patch (was v1.0.0 under independent SemVer).
Within-patch updates append a dotted suffix: `4.8.2.1`, `4.8.2.2`, ...
Rebaselined to `4.8.2.0` for the live test pass against Star Citizen 4.8.2.

499 automated tests across all layers.
Reverted notification pipeline to `wingman.process()` for full personality reactions.
Throttle cap raised to 10. If chat locks up, adjust throttling first before rearchitecting.
Phase 1 PASSED. Phase 2 in progress (live testing 2026-04-12).

---

## Completed

### 2026-07-09 - Crash-safe atomic writes (audit finding NEW-A)
- [x] New leaf module `atomic_io.py` (`atomic_write_text`): temp file in the
  same directory, flush + `os.fsync`, then `os.replace`; temp cleaned up and
  original preserved on failure
- [x] Routed `EventLog.trim`, `_save_stack_state` (main.py), and the
  `_flush_file_output` writers in logic.py and parser.py through it
- [x] Added `tests/test_atomic_io.py`; suite green at 76 passed
- [x] VERSION 4.8.3.2 -> 4.8.3.3; `atomic_io.py` added to installer manifest

### Layer 3 - parser.py
- [x] Create `LogParser` class
- [x] Implement log file tailing
- [x] Implement event classification (`_classify_event`)
- [x] Implement data extraction (`_extract_event_data`)
- [x] Implement `StateStore` for atomic states
- [x] Implement subscription/callback system
- [x] Implement optional JSON file output
- [x] Add standalone entry point

### Layer 2 - logic.py
- [x] Create `StateLogic` class
- [x] Implement subscription to Layer 3
- [x] Implement `Rule` class for state combinations
- [x] Implement default rules (armistice, ship, location)
- [x] Implement mission tracking
- [x] Implement subscription/callback system for Layer 1
- [x] Implement optional JSON file output
- [x] Add standalone entry point

### Layer 1 - main.py
- [x] Create `SC_LogReader` skill class
- [x] Implement subscription to Layer 2
- [x] Implement AI tools (get_recent_events, get_current_state, get_active_missions)
- [x] Implement notification batching
- [x] Implement duplicate detection

### Configuration
- [x] Create `default_config.yaml`
- [x] Define notification toggles
- [x] Define debug file output toggle

---

## In Progress

### Testing
- [x] Test Layer 3 standalone with live Game.log
- [x] Test Layer 2 standalone with Layer 3
- [x] Test full stack integration with WingmanAI
- [x] Verify contract_failed parsing with real log data
- [x] Automated pytest suite (367 tests) — v0.1.8
- [x] 6-phase manual test checklists — v0.1.8
- [x] Phase 1: Dev startup without game (manual) — PASSED 2026-02-06
- [ ] Phase 2: Dev full test with game (manual)
- [ ] Phase 3: Live startup without game (manual)
- [ ] Phase 4: Live full test with game (manual)
- [ ] Phase 5: Beta test with testers
- [ ] Phase 6: Release

### Log donation feature

- [x] Run TESTER.md Smoke 5 (skill integration with live Worker) manually
      and verify the donor UI end-to-end against the deployed
      `sc-log-donate.lars-erik-vaagen.workers.dev` -- DONE 2026-05-14,
      full upload cycle verified, files land in R2
- [ ] Run TESTER.md Smoke 6 (failure injection with bad worker_url) and
      verify the UI surfaces `result.top_level_error` cleanly
- [ ] Add `donate_logs` to the skill prompt block so the LLM mentions it
      naturally when users ask about contributing / improving the skill
- [x] (Polish) Silent retry exhaustion in `Uploader._put_file`: add a
      final `logger.warning("gave up after N attempts")` and avoid the
      "retrying" log on the last attempt -- done 2026-07-07 (v4.8.3.0)
- [x] (Polish) `Uploader._put_file` reads whole file with `fh.read()`;
      consider streaming for >50 MB log files (rare) -- done 2026-07-07,
      now streams the open file object to httpx (v4.8.3.0)
- [x] (Polish) Silent `continue` in `Uploader.upload` when Worker returns
      an unknown sha256; add a `logger.debug` for observability -- done
      2026-07-07 (v4.8.3.0)
- [ ] (Polish) Drop the `rows.results ?? []` fallback in `src/db.ts` of
      `sc-log-donate` (D1 result type is never undefined)
- [ ] (Polish) `upload` method docstring undersells the caller contract
      (close client, progress_cb behavior on early returns)
- [ ] (Polish) Worker `lookupExistingHashes` has no guard for D1's
      100-binding cap; only matters if a single upload exceeds 100 files
- [ ] (Polish) Extract the duplicate `json` helper in
      `sc-log-donate/src/handlers/*.ts` into a shared `_response.ts`
- [ ] (Polish) Em-dash audit across plan + DEVLOG: confirm no `--`
      sneaked in during manual edits (project hard rule)

### Donor UI security hardening (2026-07-07, v4.8.3.0)
- [x] Per-session token (X-Donor-Session) + Host-header check on the
      local donor server
- [x] Static file containment fix (resolved.parent check, blocks Windows
      drive-relative traversal)
- [x] Upload scoped to the previewed sha256 set, not a blind re-scan
- [x] Dedup-store matching by sha256 only (dropped renamed fallback)
- [x] Live-only scanning scope (`scanner._INSTALL_NAMES = ("Live",)`)
- [x] Version-freshness check surfaces `LiveLogUnavailableError` as a
      distinct preview error instead of "no logs found"
- [x] Client-side 1 MB minimum / 50 MB maximum / 50-file caps mirroring the
      Worker, surfaced in the preview JSON and UI (1 MB floor added same
      day as an addendum, both bounds inclusive at the boundary)
- [x] `already_uploaded_count` wired through from the scanner instead of
      hardcoded 0
- [x] Donor state DB relocated under the skill's own generated_files dir,
      with one-time migration from the old AppData path
- [x] Consent copy single-sourced from `ui_dialog.CONSENT_BODY`, served
      via `/api/preview`, rendered client-side
- [x] `tests/test_donor_server.py` added (FastAPI TestClient coverage)
- [ ] Manually re-run TESTER.md Smoke 5/6 against the deployed Worker to
      confirm the sha256-restricted upload and Live-only scope behave
      correctly against real SC installs (automated tests only cover
      synthetic fixtures)

### Notes / verified during 2026-05-14 live test
- Wingman skill framework caches modules in `sys.modules`; the
  `WingmanAiCore` background process must be killed (not just the UI
  restarted) for code changes to a reinstalled skill to load. install.bat
  next-steps + troubleshooting blocks both call this out.
- Notification toggles gate verbose Wingman speech ONLY. All events are
  always written to `sc_logreader_eventlog_<env>.jsonl` and accessible via
  the AI tool queries (`get_recent_game_events`, etc.). This is by design.

### Code Quality
- [ ] Full sweep of all code against the 14 Rules of Coding (CLAUDE.md)
  - KISS: identify and simplify unnecessary complexity
  - DRY: find and consolidate duplicated logic
  - YAGNI: remove speculative/unused code
  - SoC: verify clean layer boundaries
  - Clean Code & Readability: naming, structure, clarity
  - Comments: ensure comments explain "why", not "what"
  - No premature optimization
  - Consistent standards: style, formatting, conventions
  - SOLID principles: check class responsibilities
  - Unit testing: coverage gaps, edge cases
  - Code review: peer-review readiness
  - Error handling: graceful, specific, no bare excepts
  - Version control: clean commit history
  - Dead code: remove unused variables, imports, obsolete comments

### Log Sample Corpus
- [x] 180+ Game.log samples collected from multiple players (Mallachi, Xul, JaymMatthew, Amiscus, Teddybear) and builds (11010425 through 11494258), covering Jan–Mar 2026. Stored at `C:\Users\larse\PycharmProjects\SC-Log-Samples\`. Available for pattern testing, parser validation, and regression coverage.

### Performance Analysis (2026-03-22)
- [x] Confirmed no code-level lag sources — all Python-side processing is lightweight background work
- [x] Confirmed `ship_exited` is tracked correctly (not just `ship_entered`)
- [ ] Add config hint guidance noting that `notify_location_arrived` + `notify_jurisdiction_change` together in heavy-travel sessions can consume the 10-message notification budget quickly
- [ ] Consider whether `notify_fuel_low` (fires every ~2 minutes while low) should have its own cooldown separate from the global duplicate detection

### Refinement
- [x] Fixed ship channel detection and name cleanup
- [x] Add location name translation (internal codes → human readable) - v0.1.4
- [x] Add notification throttling (pause after 5 auto-messages without user input) - v0.1.3
- [x] Jurisdiction extraction - v0.1.5
- [x] Event/state formal separation - v0.1.5
- [x] Monitored space state tracking (`in_monitored_space`) - v0.1.5
- [x] Restricted area state tracking (`in_restricted_area`) - v0.1.5
- [x] Objective complete/withdrawn data extraction + state clearing - v0.1.5
- [x] Star system tracking (`star_system` state key derived from location codes) - v0.1.15
- [x] Expand location mapping dictionary with more codes from testers — v0.1.18
- [ ] Quantum target `LOCRRS` code mapping (investigation in progress)

### Quantum Target Code Investigation (2026-02-07)

**Source**: `quantum_route_set` event — "Player has selected point LOCRRS2L1 as their destination"

**Pattern discovered**: `LOCRRS{orbit}L{lagrange}` — Lagrange point codes use orbital position numbering:

| LOCRRS# | Planet | Orbital Position | Note |
|---------|--------|-----------------|------|
| LOCRRS1 | Hurston | 1st from sun | |
| LOCRRS2 | Crusader | 2nd from sun | |
| LOCRRS3 | ArcCorp | 3rd from sun | |
| LOCRRS4 | microTech | 4th from sun | |

**Example**: `LOCRRS2L1` = Crusader Lagrange 1 = **CRU-L1**

**Important**: This numbering differs from `Stanton*` game codes!
- `Stanton2` = ArcCorp, `Stanton3` = Crusader (game internal)
- `LOCRRS2` = Crusader, `LOCRRS3` = ArcCorp (actual orbital order)

**Status**: Investigating whether the same `LOCRRS` scheme applies to orbital stations and other Stanton destinations. Awaiting further findings before implementation.
- [x] Update main.py notification map for new event types - v0.1.6
- [x] Category-based notification toggles (11 categories) - v0.1.6
- [x] Raw event forwarding for events without derived counterparts - v0.1.6
- [x] State change notification forwarding — removed v0.1.24 (state events are implementation detail, derived events carry all meaningful context)
- [x] Per-event notification toggles replacing category system (37 individual toggles, all off by default) — v0.1.24
- [ ] Update logic.py with derived events for new event types (monitored space, jurisdiction, restricted area, etc.)
- [x] **Hangar entry/exit detection via armistice sequencing** — v0.1.14, improved v0.1.15
  - `in_armistice=True` + `hangar_ready` = **Hangar access granted** → exit armistice → **Entered hangar**
  - `in_armistice=False` + `hangar_ready` = **Takeoff permit granted** → enter armistice → **Exited hangar**
  - After exiting hangar, next armistice exit = normal "Left armistice zone" (flag consumed)
  - `_pending_hangar` changed from `bool` to `str | None` (`"hangar_access"` / `"takeoff_permit"` / `None`)

### Known Game.log Limitations
- **Mission objective text missing or malformed (KNOWN GAME ISSUE, verified 2026-07-11)** — Two game-side defects in SC 4.8.x break objective-name capture; per user decision, NO parser changes until CIG stabilizes (see SC 4.8 holding pattern):
  1. **Empty objective titles**: some missions emit `"New Objective: : "` with no title at all; the matching `CMissionLogEntry::UpdateActiveObjective` line shows `uiDisplay[Text=]` or `Text=<= UNINITIALIZED => <EM4>[BP]</EM4>`. The title never reaches Game.log, so no parser can recover it (observed on PTU, mission `NorthRock_SOO2`; LIVE 4.8.1 missions in the same session logged titles correctly).
  2. **Multi-line "Objective Complete" notifications**: the game embeds a newline after the title, so the closing `: "` lands on the next log line. Our per-line regex (parser.py `_extract_event_data`, objective_complete) therefore never matches and `objective_complete` events carry empty data on ALL channels; the title itself IS present on the first line.
  - **Expect this to vary mission-to-mission**: what appears in the logs is most likely directly linked to how "complete" each mission is in its design phase (localization/uiDisplay wired up or not). Active full-alpha game; per-mission log quality is not a stable contract. Re-verify per mission rather than assuming a global regression.
  - Future fallback if we ever harden this: `<ObjectiveUpserted>` lines are single-line and reliable on both channels (mission_id, objective_id, state INPROGRESS/COMPLETED); titles, when the game has them, appear in `UpdateActiveObjective` uiDisplay Text (sometimes with unresolved `~mission(...)` placeholders).
- ~~**`qt_arrived` / `fatal_collision` fire for other players' ships**~~ (Resolved v4.8.3.2). `OnQuantumDriveArrived` and `<FatalCollision>` are logged for every ship in replication range, and both own and foreign arrivals read `NOT AUTH`, so AUTH cannot discriminate. Now gated on the `ship` state (player must be aboard) plus a model-token match against the arriving/colliding entity class; `fatal_collision` also requires `PlayerPilot: 1`. Fails open when aboard but the entity class is underivable, so genuine own-ship events are never lost.
- Hauling contract details (cargo type, quantity, SCU) are **not present** in Game.log — only the contract name and objective text appear in notification lines. Verified 2026-02-06.
- **Hangar entry not distinguishable from open space** — Hangars are not armistice zones, so entering a hangar via elevator triggers "Left armistice zone" — same as flying into open space. No Game.log data currently differentiates hangar entry from true armistice exit. This also makes the landing/takeoff permit logic unreliable (requesting a ship at a terminal while on foot triggers "Landing permit granted"). Needs a future Game.log signal or heuristic (e.g., armistice exit shortly after hangar_ready without ship channel = hangar entry, not departure).
- ~~**ATC communication fires on console use**~~ — Resolved v0.1.20. Controlled testing proved `AImodule_ATC` fires exclusively on ship departure from station airspace. The false positives were from `AImodule_Cargo` (terminal/console interactions), not `AImodule_ATC`. Now used as `station_departed` event.
- **`station_departed` may break in next LIVE patch** — PTU (going live ~2026-03-19) changed `AImodule_ATC` tag to `<Connection Flow>` in `DoEstablishCommunicationCommon` lines. The new `<Connection Flow>` tag also fires on terminal use (confirmed: calling ship from station terminal), so it cannot replace `AImodule_ATC` as a departure filter without additional filtering. Need to capture PTU departure logs to find the new reliable departure signal. Current LIVE filter (`AImodule_ATC` + `DoEstablishCommunicationCommon`) is correct for LIVE.
- **Contract notifications partially broken (2026-02-06 server patch)** — Contract events were working correctly prior to the patch. Monitor future server patches for when CIG restores proper contract logging. Our parsing is correct — the game-side data is incomplete.

---

## Event Types Implemented

### Contracts/Missions
- [x] `contract_accepted`
- [x] `contract_complete`
- [x] `contract_failed`
- [x] `contract_shared` - v0.1.5
- [x] `contract_available` - v0.1.5
- [x] `objective_new`
- [x] `objective_complete` (with data extraction) - v0.1.5
- [x] `objective_withdrawn` - v0.1.5

### Location/Zones
- [x] `location_change`
- [x] `entered_monitored_space`
- [x] `exited_monitored_space`
- [x] `monitored_space_down` - v0.1.5
- [x] `monitored_space_restored` - v0.1.5
- [x] `jurisdiction_change` (with data extraction) - v0.1.5
- [x] `armistice_zone`
- [x] `restricted_area` - v0.1.5 (replaces private_property)
- [x] `journal_entry` - v0.1.5

### Ships
- [x] `channel_change` (ship enter/exit via channel)
- [x] `hangar_ready`
- [x] `hangar_queue` - v0.1.5
- [x] `quantum_route_set`
- [x] `quantum_calibration_started` - v0.1.5
- [x] `quantum_calibration_complete` - v0.1.5

### Health
- [x] `injury`
- [x] `med_bed_heal`
- [x] `emergency_services` - v0.1.5

### Social
- [x] `party_invite` - v0.1.5
- [x] `incoming_call` - v0.1.5

### Economy
- [x] `reward_earned` (aUEC + item rewards) - item variant fixed v0.1.32, CIG format change fixed v0.1.34
- [x] `blueprint_received` - v0.1.35 (blueprint reward from mission, written to event log with `item_name`)
- [x] `refinery_complete` - v0.1.5
- [x] `refinery_submitted` - v0.1.32 (ore submitted to refinery kiosk)
- [x] `shop_buy` - v0.1.32 (confirmed item purchase, written to event log) — tested v0.1.34 ✓
- [x] `shop_sell` - v0.1.32 (confirmed item sale, written to event log) — tested v0.1.34 ✓
- [x] `commodity_buy` - v0.1.32 (commodity purchase, written to event log) — tested v0.1.34 ✓
- [x] `commodity_sell` - v0.1.32 (commodity sale, written to event log)

### Inventory / Cargo
- [x] `cargo_transfer` - v0.1.32 (freight elevator unstow)
- [x] `attachment_received` - v0.1.32 (item equipped to player, cosmetic ports filtered, expanded v0.1.33)

### Known Game.log Gaps
- `commodity_buy` / `commodity_sell` — `item_name` is always null. CIG logs only `resourceGUID`, never the commodity name, in either buy request or post-purchase lines. Resolution pending: GUID→name lookup table from SCBridge.app game data extraction (arranged 2026-04-12).

### ATC / Comms
- [ ] ~~`station_departed`~~ — Disabled. `AImodule_ATC` tag removed in PTU; replacement `<Connection Flow>` fires on terminal use. Awaiting reliable log signal from CIG.

### Session
- [x] `session_start`
- [x] `join_pu`
- [x] `user_login` - v0.1.23 (User Login Success - Handle[X])

## States Tracked

| State Key | Type | Source Event(s) |
|-----------|------|----------------|
| `player_name` | string | `session_start`, `user_login`, `location_change` (fallback) |
| `player_geid` | string | `session_start` |
| `server` | string | `join_pu` |
| `location` | string | `location_change` |
| `location_name` | string | `location_change` |
| `star_system` | string | `location_change` |
| `ship` | string\|None | `channel_change` |
| `ship_owner` | string\|None | `channel_change` |
| `own_ship` | bool\|None | `channel_change` (derived: `ship_owner` == `player_name`) |
| `in_armistice` | bool | `armistice_zone` |
| `in_monitored_space` | bool | `entered/exited_monitored_space`, `monitored_space_down/restored` |
| `in_restricted_area` | bool | `restricted_area` |
| `jurisdiction` | string | `jurisdiction_change` |
| ~~`quantum_destination`~~ | ~~string~~ | Removed v0.1.15 — destination names unreliable |
| `current_objective` | string\|None | `objective_new`, `objective_complete`, `objective_withdrawn` |
| `injury_{body_part}` | string\|None | `injury`, `med_bed_heal` |
| `last_contract_accepted` | string | `contract_accepted` |
| `last_contract_accepted_id` | string | `contract_accepted` |
| `last_contract_completed` | string | `contract_complete` |
| `last_contract_completed_id` | string | `contract_complete` |
| `last_contract_failed` | string | `contract_failed` |
| `last_contract_failed_id` | string | `contract_failed` |
| ~~`atc_available`~~ | ~~bool~~ | Removed v0.1.20 — replaced by `station_departed` event |
| ~~`atc_location`~~ | ~~string\|None~~ | Removed v0.1.20 — replaced by `station_departed` event |

---

## Verified Log Patterns

### contract_failed (2026-01-31)
```
<2026-01-31T14:22:24.060Z> [Notice] <SHUDEvent_OnNotification> Added notification "Contract Failed: Alliance Aid: Ship Under Attack: " [13] to queue. New queue size: 1, MissionId: [4f83b8fb-d323-4726-9e6c-ba5a4a145170], ObjectiveId: [] [Team_CoreGameplayFeatures][Missions][Comms]
```
- Regex: `r'"Contract Failed:\s*(.+?):\s*"'`
- Extracts full mission name including colons

### injury (2026-02-01)
```
<2026-02-01T00:04:01.582Z> [Notice] <SHUDEvent_OnNotification> Added notification "Minor Injury Detected - Left arm - Tier 3 Treatment Required : " [120] to queue...
```
- Severity regex: `r"(\w+)\s+Injury Detected"` → "Minor"
- Body part regex: `r"Injury Detected\s*-\s*([^-]+)\s*-"` → "Left arm"
- Tier regex: `r"Tier\s*(\d+)"` → 3

### med_bed_heal (2026-02-01)
```
<2026-02-01T00:38:30.008Z> [Notice] <MED BED HEAL> ... head: true torso: false leftArm: true rightArm: false leftLeg: false rightLeg: false ...
```
- Pattern: `f"{part}: true"` for each body part

### location_change (2026-02-01)
```
<2026-01-31T14:06:04.669Z> [Notice] <RequestLocationInventory> Player[Mallachi] requested inventory for Location[RR_CRU_LEO] ...
```
- Regex: `r"Location\[([^\]]+)\]"` → "RR_CRU_LEO"

### channel_change / ship detection (2026-02-01)
```
<2026-01-31T21:04:20.865Z> [Notice] <SHUDEvent_OnNotification> Added notification "You have joined channel '@vehicle_NameMISC_Hull_C : Mallachi'.
```
- Raw channel: `@vehicle_NameMISC_Hull_C : Mallachi`
- Cleaned: `Hull C`
- Only matches SHUDEvent lines to avoid duplicates

---

## Research

### Deep Log Analysis — PTU Log Backups
- [x] **Research Pass 1 COMPLETE** — 157 PTU log files analyzed (2026-01-09 → 2026-03-21)

#### ✅ CONFIRMED NEW EVENTS — Ready to Implement

**`fuel_low`** — SHUDEvent notification, fires repeatedly ~every 2 min while fuel stays low
```
[Notice] <SHUDEvent_OnNotification> Added notification "Low Fuel: To refuel, park at a pad or hangar and use your Landing mobi-app from the pilot's seat."
```
- Regex: `r'"Low Fuel: '` on SHUDEvent lines — **needs throttle/dedup (fires every ~2 min)**

**`crimestat_increased`** — Two SHUDEvent notifications fire together
```
"CrimeStat Rating Increased: "
"CrimeStat: You've gained a CrimeStat level by committing an infraction in monitored space. Your current CrimeStat level is displayed on your HUD."
```
- Regex: `r'"CrimeStat Rating Increased: '` on SHUDEvent lines

**`party_member_joined`** — SHUDEvent notification per member, multiple can fire in quick succession
```
"{username} has joined the party.: "
```
- Regex: `r'"(.+) has joined the party\.: '` — captures player name

**`party_left`** (you left the party) — distinct from invite/accept
```
"You have left the party."
```
- Regex: `r'"You have left the party\.'` on SHUDEvent lines

**`transaction_complete`** — fires for BOTH shop buys AND cargo sells (indistinguishable from this line alone)
```
"Transaction Complete: "
```
- Regex: `r'"Transaction Complete: '` on SHUDEvent lines

**`shop_buy`** / **`shop_sell`** (detail level) — fires before `Transaction Complete`, has full item/price context
```
[Notice] <CEntityComponentShopUIProvider::SendShopBuyRequest> Sending SShopBuyRequest - playerId[...] shopName[SCShop_...] itemName[BEHR_LaserCannon_S2] quantity[4] client_price[133600.000000]
[Notice] <CEntityComponentShopUIProvider::RmShopFlowResponse> ... result[Success] type[Buying]
[Notice] <CEntityComponentShopUIProvider::SendShopSellRequest> Sending SShopSellRequest - ... itemName[Harvestable_Trophy_1H_vlkJuvenileFang] quantity[8] client_price[6000.000000]
[Notice] <CEntityComponentShopUIProvider::RmShopFlowResponse> ... result[Success] type[Selling]
```
- Buy regex: `r'SendShopBuyRequest.*shopName\[([^\]]+)\].*itemName\[([^\]]+)\].*quantity\[(\d+)\].*client_price\[([\d.]+)\]'`
- Sell regex: `r'SendShopSellRequest.*shopName\[([^\]]+)\].*itemName\[([^\]]+)\].*quantity\[(\d+)\].*client_price\[([\d.]+)\]'`
- Confirm with `RmShopFlowResponse.*result\[Success\] type\[(Buying|Selling)\]`

**`bleeding`** — SHUDEvent, fires when player starts bleeding
```
"Bleeding: You are bleeding and will continue to lose health over time. Use a coagulant like Hemozal to reduce the effects."
```
- Regex: `r'"Bleeding: '` on SHUDEvent lines

**`vehicle_impounded`** — SHUDEvent, includes reason
```
"Vehicle Impounded: Parking Violation: "
"Vehicle Impounded: Trespassing (Second Degree): "
```
- Regex: `r'"Vehicle Impounded: (.+?): '` — captures reason

**`restricted_area_impound`** (new variant — vehicles at risk) + **`leaving_restricted_area`**
```
"Restricted Area - Vehicles Will Be Impounded: "
"Leaving Restricted Area: "
```
- Note: distinct from existing `restricted_area` parser event (proximity sensor)

**`qt_calibration_complete_group`** — ✅ implemented v0.1.27

#### ⚠️ PTU FORMAT CHANGE — ATC / Station Departure

**Current LIVE filter** (`station_departed`): `<AImodule_ATC>` tag + `DoEstablishCommunicationCommon`

**PTU format**: tag changed to `<Connection Flow>`, partner name still contains `AImodule_ATC`
```
[Notice] <Connection Flow> CSCCommsComponent::DoEstablishCommunicationCommon: Update bubble created ... to track their communication partner AImodule_ATC_8854427285388 [...]
```
- **New PTU filter**: line contains `<Connection Flow>` + `DoEstablishCommunicationCommon` + `AImodule_ATC` in partner name
- Exclude: `ATC_DataManager-001` (different channel, not a departure signal)
- When this goes LIVE (~2026-03-19 scheduled), `station_departed` parser needs update

#### ❌ NOT FOUND in Logs

| Event | Status |
|-------|--------|
| `player_death` | No log signal found — no notification, no dedicated line. Respawn inferred only from `Medbay_Respawn_Gel_Canister_Housing` placement (unreliable). |
| `shields_down` | Not in Game.log — HUD-only UI element |
| `hull_critical` | Not in Game.log — HUD-only UI element |
| `target_lock` | Not in Game.log — HUD-only UI element |
| `system_change` (Stanton↔Pyro) | No "arrived in system" notification. `[STAMINA] RoomName: jumppoint_nyx_castra` fires at jump point rest stop area only. System derivation from `location_change` remains best approach. |
| `component_damage` | Not in Game.log — no notification |
| `fuel_type_detail` | Fuel type (H2 vs QT) not available from `Low Fuel` notification — generic warning only |

- [ ] **Research Pass 2** — deeper investigation needed for: jump transit system detection (Pyro entry), cargo sell via trade kiosk (`SendShopSellRequest` vs trade console path), `party_member_left` (vs `You have left the party`)

---

## Future Enhancements

### Priority 1: High-Value Events for Gamers

#### Combat & Flight
- [ ] `shields_down` - Shield depletion warning
  - Pattern: **NOT IN GAME.LOG** — HUD-only, no log signal found across 157 PTU log files
- [ ] `hull_critical` - Hull damage threshold
  - Pattern: **NOT IN GAME.LOG** — HUD-only, no log signal found
- [ ] `target_lock` - Missile/weapon lock warnings
  - Pattern: **NOT IN GAME.LOG** — HUD-only, no log signal found
- [x] `fuel_low` - Low fuel warning — v0.1.27
- [x] `bleeding` - Player bleeding — v0.1.27
- [x] `crimestat_increased` - CrimeStat rating went up — v0.1.27
- [x] `vehicle_impounded` - Vehicle impounded (extracts reason) — v0.1.27

#### Economy & Trade
- [x] `shop_sell` - v0.1.32 (event log, single source of truth)
- [x] `shop_buy` - v0.1.32 (event log, single source of truth)
- [x] `commodity_buy` / `commodity_sell` - v0.1.32 (event log)

#### Social & Party
- [x] `party_member_joined` - Party member connection — v0.1.27
- [x] `party_left` - You left the party — v0.1.27

### Priority 2: Roleplay-Focused Events

#### World State
- [ ] `jumppoint_enter` - Entering jump point
  - Pattern: TBD (Stanton↔Pyro transitions)
  - Useful for: System transition announcements
- [ ] `system_change` - Arrived in new system
  - Pattern: TBD
  - Useful for: Location awareness, lore references
- [ ] `weather_warning` - Environmental hazard
  - Pattern: TBD
  - Useful for: Immersive warnings

#### Law & Crime
- [ ] `crime_stat_gained` - Criminal rating increased
  - Pattern: TBD
  - Useful for: Law status awareness
- [ ] `crime_stat_cleared` - Criminal rating cleared
  - Pattern: TBD
  - Useful for: Status updates
- [ ] `bounty_placed` - Bounty on player
  - Pattern: TBD
  - Useful for: Threat awareness

#### Death & Recovery
- [ ] `player_death` - Player died
  - Pattern: TBD
  - Useful for: Session tracking, respawn prompts
- [ ] `respawn_location` - Respawn point
  - Pattern: TBD
  - Useful for: Recovery navigation

### Priority 3: Quality of Life

#### Ship Management
- [ ] `fuel_low` - Low fuel warning
  - Pattern: TBD
  - Useful for: Refuel reminders
- [ ] `component_damage` - Ship component damaged
  - Pattern: TBD
  - Useful for: Repair priorities
- [ ] `power_warning` - Power distribution issues
  - Pattern: TBD
  - Useful for: System management

#### Inventory & Items
- [ ] `item_received` - Item added to inventory
  - Pattern: TBD
  - Useful for: Loot tracking
- [x] `item_equipped` - Equipment change — covered by `attachment_received` v0.1.32
- [x] `cargo_transfer` - Freight elevator unstow — v0.1.32

### Infrastructure Improvements

- [x] **Event log** - `sc_logreader_eventlog_{env}.jsonl` — v0.1.32
  - Single source of truth for all game events (raw + derived + confirmed trades)
  - `EventLogEntry`: timestamp, event_type, location, player_name, data, amount_auec, item_name
  - `EventLog.query(event_type, start, end, limit)` API for sibling skills
  - 30-day trim on startup per environment
  - `TradeLedger` retired from write path — event log is the only destination
- [ ] **Continuous text log** - Parser writes human-readable log file that grows perpetually
  - Part of the same debug_file_output feature as JSON files
  - Appends each parsed event with timestamp
  - Useful for: Long-term session analysis and debugging
- [ ] Ship cargo capacity lookup (from ship_data.py)
- [x] Location code → human-readable translation table (location_names.py)
- [ ] Jurisdiction data extraction improvements
