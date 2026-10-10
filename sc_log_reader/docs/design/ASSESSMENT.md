# SC Log Reader: single-file instruction mapping

Date: 2026-09-15. Scope: current dirty working tree, not upstream or release_version.

## Conclusion

The current event surface can be mapped to a finite proposed instruction vocabulary. This supports a single JSON package for message recognition, field extraction, aliases and lookup tables. It does not establish parser equivalence, eliminate all future engine updates, or qualify any Star Citizen build.

The important prerequisite is moving state decisions currently embedded in parser.py into Tier 2, while retaining a compatibility facade for existing callers. This is more than moving regex strings into a file, but does not require redesigning every existing gameplay feature.

Artifacts:

- `reader-instructions.draft.json`: complete event-by-event design mapping and proposed operators. DESIGN ONLY; do not install it or rename it into a runtime configuration.
- `source-inventory.json`: line references, source hashes, original extraction/state branches, all nested conditionals in the central parsing path and ownership assignment for every LogParser method.
- `verification.json`: structural checks and focused probes of the current parser, added after independent verification.

## Coverage counts

- classifier return sites: **60**
- classifier event types: **59**
- public event types: **59**
- internal markers: **1**
- mapped event definitions: **60**
- extraction blocks: **45**
- state blocks: **20**
- traced conditionals: **226**
- parser methods accounted for: **39**
- unmapped current output fields: **0**
- proposed operator families: **12**
- tier2 handler groups: **10**
- regex expressions compiled: **89**

Counting: classifier return sites include two reward_earned alternatives. _money_sent_partial is an internal marker. money_sent is synthesized in _process_line. Therefore public events are classifier event types minus the internal marker plus synthesized money_sent. Nested conditional counts measure source traceability, not test coverage.

## Proposed architecture and compatibility

1. Tier 3 fixed engine assembles records and interprets the finite JSON vocabulary. It owns file offsets, rotation detection, byte buffering, timestamps, parsing limits and diagnostics.
2. The downloaded JSON owns patterns, captures, enumerations, unit declarations and lookup tables. It cannot name Python functions or evaluate expressions. All record/regex operations need fixed resource limits; data-only is not a guarantee against a pathological pattern.
3. Tier 2 owns game state, ownership qualification, correlation, deduplication, confidence and ledger commits. Apply a complete event's related state changes before deriving notifications; avoid callbacks observing half-updated ship/owner state.
4. Preserve Tier 1 event names, data shapes, config keys and notification behavior using an adapter. Also preserve parser-facing subscribe_state/get_state/save_state/load_state/clear_state access until callers migrate. Tier 2 currently calls back into the parser for state; moving only _update_state is insufficient.
5. Startup replay and live tailing must use the same definitions. _scan_log_startup currently hardcodes two recognition strings independently of live parsing; leaving those unchanged would defeat JSON-only updates for login changes.

Unknown or incomplete candidates must not clear known state or become money. Track last known value plus validity/provenance when needed. Do not transform an unparseable timestamp into current time. Timeouts should use monotonic elapsed time live and a controlled clock during replay.

## What needs fixed engine logic

| Area | JSON contribution | Fixed engine / Tier 2 responsibility |
|---|---|---|
| Record assembly | Start/continuation patterns and format variants | Partial bytes, complete records, bounded buffers, rotation/session boundaries, final-record latency |
| Rewards | Recognize amount/quantity/item/unit variants | Currency meaning, legacy policy, mutually exclusive values, mission association and bundle dedup |
| Item trades | Provider aliases, keys, typed request/result fields | Correlation by environment/session/player/request occurrence; ambiguous matches remain unresolved |
| Commodity trades | Numeric fields and explicit unit metadata | Unit conversion and request-versus-confirmed accounting; current immediate booking is a policy to review |
| Ship events | Raw channel/entity/pilot fields, manufacturer tables | Determine ship occupancy/owner; qualify replicated arrivals/collisions before notifying |
| Location departure | Location.from/to plus personal inventory GUID | Name/GUID correlation, 60s/15s windows, zero exclusion, departure-before-clear and re-arrival |
| Session reset | Login/session recognition and identity fields | Reset scoped state correctly; current GEID dedup must not equate every same-character login with the same session |
| State effects | Validated event contract | Mission transitions, injury healing, zone transitions, snapshots and confidence |

Ship limitation: current _event_belongs_to_player_ship uses model-token overlap and accepts missing class while aboard. Two ships of the same model cannot be distinguished from those fields alone. The map preserves evidence for a decision; it does not solve that information gap.

## Complete event mapping

Required fields below are proposed gating requirements, not descriptions of current permissive behavior. Existing fields not extracted by Tier 3 are explicitly assigned to Tier 2. New candidate fields expose evidence previously hidden by the parser. Empty required lists describe event-only cases, not permission to skip common record validation.

| Event | Current extracted fields | Proposed read operations | Tier 2 | Required before state effect | Source extraction |
|---|---|---|---|---|---|
| `_money_sent_partial` | recipient | capture, normalize | passthrough | recipient | parser.py:1255 |
| `armistice_zone` | action | choose | zones | action | parser.py:1046 |
| `attachment_received` | elapsed, entity_id, item_full_name, item_short_name, player_name, port | bracket_fields, capture, exclude_values, normalize | movement | port, entity_id | parser.py:1325 |
| `bleeding` | none | match only | passthrough | none beyond envelope | event-only |
| `blueprint_received` | blueprint_name, mission_id, notification_id, objective_id | capture, normalize, notification_context | rewards | blueprint_name | parser.py:1138 |
| `cargo_transfer` | entity_count, kiosk_id, kiosk_type, location_id, request_id | capture, normalize | movement | request_id | parser.py:1292 |
| `channel_change` | action, channel, channel_owner, channel_raw | capture, choose | ships | action, channel_raw | parser.py:1005 |
| `commodity_buy` | kiosk_id, player_id, price, quantity_cscu, resource_guid, shop_id, shop_name | bracket_fields, normalize, quantity_with_unit | trades | price, quantity_cscu, quantity_unit | parser.py:1169 |
| `commodity_sell` | kiosk_id, player_id, price, quantity, resource_guid, shop_id, shop_name | bracket_fields, normalize | trades | price, quantity | parser.py:1190 |
| `contract_accepted` | mission_id, mission_name | bracket_fields, notification_payload | missions | mission_name, mission_id | parser.py:864 |
| `contract_available` | mission_id, mission_name | bracket_fields, notification_payload | missions | mission_name, mission_id | parser.py:883 |
| `contract_complete` | mission_id, mission_name | bracket_fields, notification_payload | missions | mission_name, mission_id | parser.py:864 |
| `contract_failed` | mission_id, mission_name | bracket_fields, notification_payload | missions | mission_name, mission_id | parser.py:864 |
| `contract_shared` | mission_id, mission_name | bracket_fields, notification_payload | missions | mission_name, mission_id | parser.py:883 |
| `crimestat_increased` | none | match only | passthrough | none beyond envelope | event-only |
| `emergency_services` | none | match only | passthrough | none beyond envelope | event-only |
| `entered_monitored_space` | monitored | constant | zones | none beyond envelope | parser.py:1034 |
| `exited_monitored_space` | monitored | constant | zones | none beyond envelope | parser.py:1034 |
| `fatal_collision` | vehicle, zone | capture, normalize | ships | player_pilot | parser.py:1261 |
| `fined` | amount | capture, normalize | rewards | amount, currency | parser.py:1249 |
| `fuel_low` | none | match only | passthrough | none beyond envelope | event-only |
| `hangar_queue` | action | constant | passthrough | none beyond envelope | parser.py:1061 |
| `hangar_ready` | action | constant | passthrough | none beyond envelope | parser.py:1058 |
| `incapacitated` | none | match only | passthrough | none beyond envelope | event-only |
| `incoming_call` | caller | capture, normalize | passthrough | none beyond envelope | parser.py:1088 |
| `injury` | body_part, severity, tier | capture, normalize | health | body_part, severity | parser.py:920 |
| `insurance_claim` | request_id, urn | capture, normalize | movement | urn | parser.py:1272 |
| `insurance_claim_complete` | result, urn | capture, normalize | movement | urn, result | parser.py:1281 |
| `inventory_location_update` | departed_location_code, departed_location_name, is_departure, landing_from, landing_to, loc_from, loc_to, player_name | bracket_fields, capture | locations | loc_from, loc_to | parser.py:953 |
| `join_pu` | server_address, shard | bracket_fields | session | shard | parser.py:855 |
| `journal_entry` | subject | bracket_fields, notification_payload | passthrough | subject | parser.py:1082 |
| `jurisdiction_change` | jurisdiction | capture, normalize | zones | jurisdiction | parser.py:1028 |
| `location_change` | location, player_name | bracket_fields | locations | location | parser.py:941 |
| `med_bed_heal` | healed_parts | collect_true_fields | health | healed_parts | parser.py:933 |
| `money_sent` | recipient, amount | capture, normalize, sequence | rewards | recipient, amount, currency | parser.py:507 (assembly) |
| `monitored_space_down` | monitored | constant | zones | none beyond envelope | parser.py:1034 |
| `monitored_space_restored` | monitored | constant | zones | none beyond envelope | parser.py:1034 |
| `objective_complete` | mission_id, objective | bracket_fields, notification_payload | missions | objective, mission_id | parser.py:904 |
| `objective_new` | mission_id, objective | bracket_fields, notification_payload | missions | objective, mission_id | parser.py:896 |
| `objective_withdrawn` | mission_id, objective | bracket_fields, notification_payload | missions | objective, mission_id | parser.py:912 |
| `party_invite` | from_player | capture, normalize | passthrough | from_player | parser.py:1076 |
| `party_left` | none | match only | passthrough | none beyond envelope | event-only |
| `party_member_joined` | player_name | capture | passthrough | player_name | parser.py:1213 |
| `personal_inventory_data` | location_guid, player_name | bracket_fields, capture | locations | location_guid | parser.py:989 |
| `qt_arrived` | none | capture, normalize | ships | none beyond envelope | event-only |
| `qt_calibration_complete_group` | player | capture, normalize | passthrough | player | parser.py:1219 |
| `quantum_calibration_complete` | none | match only | passthrough | none beyond envelope | parser.py:1072 |
| `quantum_calibration_started` | player | capture, normalize | passthrough | none beyond envelope | parser.py:1064 |
| `quantum_route_set` | none | match only | passthrough | none beyond envelope | parser.py:1000 |
| `refinery_complete` | location | capture, normalize | passthrough | none beyond envelope | parser.py:1096 |
| `refinery_submitted` | currency_type, kiosk_id, player_id, shop_id, shop_name | bracket_fields | movement | player_id | parser.py:1312 |
| `restricted_area` | action | choose | zones | action | parser.py:1052 |
| `reward_earned` | amount, item_name, mission_id, notification_id, objective_id, quantity | choose, notification_context | rewards | none beyond envelope | parser.py:1102 |
| `session_start` | player_geid, player_name | capture | session | player_geid | parser.py:847 |
| `shop_buy` | currency_type, item_guid, item_name, kiosk_id, player_id, price, quantity, shop_id, shop_name, source_provider | bracket_fields, choose, normalize | trades | price, quantity | parser.py:1147 |
| `shop_sell` | currency_type, item_guid, item_name, kiosk_id, player_id, price, quantity, shop_id, shop_name, source_provider | bracket_fields, choose, normalize | trades | price, quantity | parser.py:1147 |
| `shop_transaction_result` | kiosk_id, kiosk_state, player_id, result, shop_id, shop_name, source_provider, transaction_type | bracket_fields, choose | trades | result | parser.py:1229 |
| `transaction_complete` | mission_id, notification_id, objective_id | notification_context | rewards | none beyond envelope | parser.py:1135 |
| `user_login` | player_name | bracket_fields | session | player_name | parser.py:841 |
| `vehicle_impounded` | reason | notification_payload | passthrough | reason | parser.py:1207 |

## Explicit exceptions and deliberate omissions

- `_money_sent_partial` never reaches Tier 2; it becomes `money_sent` only after bounded assembly with its recipient preserved.
- `qt_arrived` previously returned an empty data object after a stateful ownership check. The candidate now carries entity evidence so Tier 2 can perform that check before public delivery.
- `fatal_collision` must retain both the PlayerPilot guard and ship qualification. Matching the text alone is insufficient.
- `inventory_location_update` moves is_departure and resolved departed location fields to Tier 2; raw Landing fields remain available but cannot trigger departure.
- `channel_change` moves channel cleanup, manufacturer recognition and owner interpretation into the Tier 2 ship handler; manufacturer lists remain data.
- `reward_earned` has four meaningful shapes: explicit currency, unitless legacy number, physical quantity with item/unit, and named item. The current unitless-number assumption is NOT applied to arbitrary future builds.
- `restricted_area` currently defaults any non-Leaving wording to entered. The draft intentionally leaves unfamiliar wording unresolved; exact new labels need real fixtures.
- Notification fields are parsed from complete records. Existing extraction is quote/line sensitive and often loses MissionId/ObjectiveId on wrapped notifications.
- `UpdateNotificationItem` remains a globally rejected duplicate source. Specific group calibration and journal labels must not collide with general calibration/jurisdiction rules. Draft emits ambiguity diagnostics rather than accepting first-match collisions.
- Attachment cosmetic port exclusion is data. Missing port must not bypass it. Attachment is not proof of purchase or consumption.
- Quantum destination extraction stays intentionally absent; no claimed reliable destination source is introduced.
- ATC `station_departed` and player-death tracking remain disabled/unimplemented, not accidentally counted as supported events. No unverified signal is reinstated.
- Location lookup and system-prefix tables are included in the draft so adding names need not require Python. Their case handling, display fallback and invalid-location sentinel still need a defined fixed policy; dynamically learned GUIDs belong to local state, not the downloaded file.
- Current notification toggle/format maps and ledger routing are in main.py/logic.py. An entirely new public event type still needs those consumers updated unless a later explicit generic contract is designed.

## Update handling

Download one complete JSON file from a trusted release endpoint. Compare instruction versions independently of the game and Wingman versions. Notify the user, validate and stage only the approved version, and select it before monitoring at the next Wingman startup. Retain the prior complete file and an installer-bundled baseline. No code, state files or user settings are overwritten by a rules update. A format- or engine-version mismatch must reject activation. Proposed changes in data interpretation still require review even when the file contains no code.

The candidate should carry actual build evidence from FileVersion (the donor scanner already has a leaf parsing helper); unknown builds are not automatically verified or automatically unusable. Multiple known formats can coexist in one JSON with explicit discriminators. Do not guess supported build ranges or use a generic numeric notification ID as a semantic event identifier.

## How to establish that the design works

1. Capture known behavior with complete old/new log excerpts per event, plus expected negatives. Existing tests are starting evidence, not comprehensive coverage of all mapped events.
2. Implement only record assembly + proposed operators in an isolated pilot after approval. This assessment does not implement that engine.
3. Compare current and candidate event streams over fixed, deduplicated logs by build. Record misses, false events, field/unit errors and changed semantics separately.
4. Test line chunk boundaries, CRLF/LF, physical/escaped newlines, incomplete last record, whitespace, punctuation, field ordering, unknown enum/unit, duplicate sources and malformed numeric values.
5. Replay sequences: overlapping requests, repeated IDs after new sessions, reordered confirmations, reward bursts, interrupted transfers, respawn, same-location re-arrival and foreign/same-model ship events. Use event time plus an explicit replay clock; isolate learned maps per run.
6. Verify ledger totals and exact state transitions, not just parse counts. Run corpus fixtures as the release gate for every JSON update; record gaps openly.
7. Test update rejection, startup selection, rollback, missing network and an unavailable/corrupt rule file with monitoring disabled until a valid fallback is selected.

## Limits of this assessment

All current event names, top-level extraction/state branches, nested conditions in the core parsing path and LogParser methods are accounted for structurally. Proposed patterns/operators are not a tested interpreter, and stricter notification labels require corpus validation. No percentage reduction in future maintenance is claimed. No live logs were read, no Wingman process was started/restarted, no updater was implemented and no runtime skill files were edited.

## Verification performed

- Source hashes for parser.py, logic.py, main.py and location_names.py still match the inventory.
- Independently checked every classifier return site, extraction/state block, parser method and event-table row against the AST.
- All 89 draft regular expressions compile; all step operators belong to the 12 declared families. This is syntax/structure validation, not parser equivalence or a formal runtime schema.
- Four existing regression test files: **29 passed**, with 22 existing Pydantic deprecation warnings. These test the current code. The initial sandbox attempt failed on temporary-directory permissions; a fresh approved temporary directory passed.
- Eight focused current-parser probes recorded in verification.json; synthetic changes are explicitly labelled.
- No full corpus replay or live Wingman verification was performed.
