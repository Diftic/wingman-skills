# SC_LogReader — Event Storage Checklist

Events currently stored are marked. Use this to decide what to add.

---

## Currently Stored

### Trade Ledger (persistent JSONL — always on)
- [x] `item_purchase` — shop_buy confirmed via shop_transaction_result
- [x] `item_sale` — shop_sell confirmed via shop_transaction_result
- [x] `commodity_purchase` — commodity_buy (immediate write)
- [x] `commodity_sale` — commodity_sell (immediate write)

---

## Not Currently Stored

### Session
- [x] `user_login` — player ID and handle seen
- [x] `session_start` — new game session detected
- [x] `join_pu` — joined persistent universe

### Travel
- [ ] `location_arrived` — arrived at a named location (derived)
- [ ] `qt_arrived` — quantum travel jump completed
- [ ] `quantum_route_set` — QT destination set
- [ ] `quantum_calibration_started`
- [ ] `quantum_calibration_complete`
- [ ] `qt_calibration_complete_group` — group QT calibration complete

### Ships & Hangars
- [ ] `ship_entered` — player boarded a ship (derived)
- [ ] `ship_exited` — player left a ship (derived)
- [ ] `hangar_access` — hangar access granted (derived)
- [ ] `hangar_queue` — queued for hangar access
- [ ] `insurance_claim` — ship insurance claim filed
- [ ] `insurance_claim_complete` — insurance claim resolved
- [ ] `fatal_collision` — ship destroyed by collision

### Zones
- [ ] `zone_entered_armistice` — entered armistice zone (derived)
- [ ] `zone_left_armistice` — left armistice zone (derived)
- [ ] `entered_monitored_space`
- [ ] `exited_monitored_space`
- [ ] `monitored_space_down`
- [ ] `monitored_space_restored`
- [ ] `jurisdiction_change`
- [ ] `restricted_area` — entered a restricted area
- [ ] `armistice_zone` — raw armistice event (suppressed — derived used instead)

### Missions & Contracts
- [ ] `mission_accepted` — contract accepted (derived)
- [ ] `mission_complete` — contract completed (derived)
- [ ] `mission_failed` — contract failed (derived)
- [ ] `mission_objective_new` — new objective added (derived)
- [ ] `objective_complete` — objective completed
- [ ] `objective_withdrawn` — objective removed
- [ ] `contract_shared` — contract shared with party
- [ ] `contract_available` — contract became available

### Health & Combat
- [ ] `injury` — player injured (severity + location)
- [ ] `med_bed_heal` — healed at med bed
- [ ] `health_injury_reminder` — escalating injury reminder (derived, timer-based)
- [ ] `incapacitated` — player incapacitated
- [ ] `bleeding` — bleeding status
- [ ] `emergency_services` — called emergency services

### Crime & Economy
- [ ] `crimestat_increased` — crime stat went up
- [ ] `vehicle_impounded` — ship/vehicle impounded
- [ ] `fined` — received a fine
- [ ] `transaction_complete` — generic aUEC transaction
- [ ] `money_sent` — aUEC sent to another player
- [ ] `reward_earned` — reward received

### Social
- [ ] `party_invite` — received party invite
- [ ] `party_member_joined` — someone joined party
- [ ] `party_left` — someone left party
- [ ] `incoming_call` — incoming comm call

### Miscellaneous
- [ ] `fuel_low` — ship fuel low warning
- [x] `refinery_complete` — refinery job finished
- [x] `blueprint_received` — blueprint added to inventory (should add to blueprint list)
- [ ] `journal_entry` — in-game journal entry added
- [ ] `channel_change` — comm channel switched (suppressed — no derived output currently)

---

## Notes
- **Ledger** = persistent JSONL append (`trade_ledger.jsonl`) — survives restarts
- **Debug file output** = rolling JSON snapshot (last 100 derived events) — optional, off by default, CLI/devkit only
- **Session state file** = runtime state snapshot on shutdown — not event history
- Raw events in `_HAS_DERIVED_EVENT` (shop_buy/sell, commodity_buy/sell, contract_accepted/complete/failed, objective_new, hangar_ready, location_change) are **suppressed at raw level** — only their derived counterparts fire
