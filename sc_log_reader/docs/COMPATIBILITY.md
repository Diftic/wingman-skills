# SC Log Reader 2 compatibility and evidence matrix

0.4.0 is a local candidate, with T1–T8 and the standalone lifetime ownership correction accepted. Reader/Handler/Orchestrator responsibilities are defined in ARCHITECTURE.md; nominal operation/parse budgets are 50/100 ms. Final corpus/story domain comparisons are complete; local paced/recovery qualification is complete and final local artifacts are prepared for controller binding/review. The inspected Diftic 3.1.2 source contract has isolated cp311 adapter/native-dependency checks; actual Wingman GUI, native settings button and frozen runtime are unqualified. No additional game build is declared verified by this version bump.

Baseline: normalized event contract 3, engine 3 bundle revision 4, 60 recipes and seven read-only tools. Raw Reader wording may change through approved JSON recipes while preserving fixed Handler meaning. Changes to normalized fields, state meaning or tool responses require compatibility review. T5 makes no runtime semantic change.

## Coverage notation and canonical values

Every recipe has synthetic recognition coverage in tests/test_recipe_matrix.py::RecipeTests.test_hand_authored_cases_are_recognized_and_extract_required_fields. That checks recognition and parse errors, not field accuracy or retail qualification. Reader required fields and fixed Handler guards are separate. Observation-only means a recent-event row with no domain mutation; timestamps, deduplication and persistence bookkeeping still apply. personal_inventory_data can update evidence with no notification row.

Table test labels refer to test_state.py, test_improvements.py, test_hardening.py, test_real_notifications.py, test_reader.py, test_service.py and the interface/update suites. The recipe table preserves the audited baseline gaps; the representative T5 table below identifies the selected assertions that now close parts of those gaps. Synthetic recognition only means incomplete field/state/negative coverage, except where the T5 table adds specific expectations. T5 coverage does not imply every recipe now has exact field and tool tests.

Canonical zones use entered/exited; channels joined/left; shop successful result Success; optional transaction kind Buying/Selling. Healing keys are head, torso, leftArm, rightArm, leftLeg, rightLeg; only boolean true clears a part. Injury raw body labels map to those keys. Shop money requires case-sensitive UEC/aUEC; notification currency accepts those case-insensitively. Notification amounts can be numeric strings with commas stripped; shop price is float, quantity integer, cargo request ID integer. Fixed numeric guards reject negatives, nonfinite values and booleans. Identity guards require nonzero text. Missing Reader-required evidence is diagnostic; Handler evidence guards independently withhold effects.

## Recipe inventory

| Recipe | Reader required | Canonical handler guards | State/output effect | Existing semantic tests | Provenance / remaining gap |
|---|---|---|---|---|---|
| `armistice_zone.v1` | action | entered/exited | armistice evidence | improvements repeated observation | none; exact fields/state/tool and negatives needed |
| `attachment_received.v1` | port, entity_id | typed contract fields | observation-only output; no domain mutation | synthetic recognition only | none; exact fields/state/tool and negatives needed |
| `bleeding.v1` | none | one-way observation | public current null; evidence retained | improvements health not current | none; exact fields/state/tool and negatives needed |
| `blueprint_received.v1` | blueprint_name | blueprint_name text; item only | item observation | state rewards; reader synthetic | none; exact fields/state/tool and negatives needed |
| `cargo_transfer.v1` | request_id | request fields only | requested movement; no confirmed inventory | state cargo_and_commodity_requests_remain_requests | none; exact fields/state/tool and negatives needed |
| `channel_change.v2` | action, channel_raw | joined/left; ship_name; owner/class optional | ship_entered/exited; owner-matched leave; class not ownership | real notifications foreign exit/general channels/display names | channel/apostrophe/millisecond_channel; foreign and same-model attribution assertions needed |
| `commodity_buy.v1` | price, quantity_cscu, quantity_unit | request fields only | requested commodity; no money/inventory | state cargo_and_commodity_requests_remain_requests | none; exact fields/state/tool and negatives needed |
| `commodity_sell.v1` | price, quantity | request fields only | requested commodity; no money/inventory | state cargo_and_commodity_requests_remain_requests | none; exact fields/state/tool and negatives needed |
| `contract_accepted.v1` | mission_name, mission_id | nonzero mission_id; mission_name | mission_accepted; add observed mission | state mission lifecycle/zero ID/fixed requirements | none; exact fields/state/tool and negatives needed |
| `contract_available.v1` | mission_name, mission_id | nonzero mission_id | observation only | synthetic recognition only | none; exact fields/state/tool and negatives needed |
| `contract_complete.v1` | mission_name, mission_id | nonzero mission_id; mission_name | mission_complete; remove; timestamped temporal reward candidate | state lifecycle | none; exact fields/state/tool and negatives needed |
| `contract_failed.v1` | mission_name, mission_id | nonzero mission_id; mission_name | mission_failed; remove matching | state lifecycle; reader impersonation | none; exact fields/state/tool and negatives needed |
| `contract_shared.v1` | mission_name, mission_id | nonzero mission_id | observation only | synthetic recognition only | none; exact fields/state/tool and negatives needed |
| `crimestat_increased.v1` | none | typed contract fields | observation-only output; no domain mutation | synthetic recognition only | none; exact fields/state/tool and negatives needed |
| `emergency_services.v1` | none | typed contract fields | observation-only output; no domain mutation | synthetic recognition only | none; exact fields/state/tool and negatives needed |
| `entered_monitored_space.v1` | none | event identity | monitored true | synthetic recognition only | none; exact fields/state/tool and negatives needed |
| `exited_monitored_space.v1` | none | event identity | monitored false | synthetic recognition only | none; exact fields/state/tool and negatives needed |
| `fatal_collision.v1` | player_pilot | vehicle/class matches ship_class; numeric pilot=1; aboard | possible_player_ship only | state ship attribution | none; exact fields/state/tool and negatives needed |
| `fined.v1` | amount, currency | amount>=0; currency uec/auec case-insensitive; no item/quantity | debit confirmed else unresolved | state exclusive rewards | none; exact fields/state/tool and negatives needed |
| `fuel_low.v1` | none | typed contract fields | observation-only output; no domain mutation | synthetic recognition only | none; exact fields/state/tool and negatives needed |
| `hangar_queue.v1` | none | typed contract fields | observation-only output; no domain mutation | synthetic recognition only | none; exact fields/state/tool and negatives needed |
| `hangar_ready.v1` | none | typed contract fields | observation-only output; no domain mutation | synthetic recognition only | none; exact fields/state/tool and negatives needed |
| `incapacitated.v1` | none | one-way observation | public current null; evidence retained | improvements health not current | none; exact fields/state/tool and negatives needed |
| `incoming_call.v1` | none | typed contract fields | observation-only output; no domain mutation | synthetic recognition only | none; exact fields/state/tool and negatives needed |
| `injury.v1` | body_part, severity | body canonical head/torso/leftArm/rightArm/leftLeg/rightLeg; severity | injury map | state selective heal | none; exact fields/state/tool and negatives needed |
| `insurance_claim.v1` | urn | request fields only | requested movement | synthetic recognition only | none; exact fields/state/tool and negatives needed |
| `insurance_claim_complete.v1` | urn, result | typed contract fields | observation-only output; no domain mutation | synthetic recognition only | none; exact fields/state/tool and negatives needed |
| `inventory_location_update.v1` | loc_from, loc_to | own name; loc_from/to text; 0 absent | departure only matched GUID; 75s candidate | state departure; hardening repeated GUID | none; exact fields/state/tool and negatives needed |
| `join_pu.v1` | shard | nonempty shard | shard; changed shard invalidates world | improvements shard change | none; exact fields/state/tool and negatives needed |
| `journal_entry.v1` | subject | typed contract fields | observation-only output; no domain mutation | synthetic recognition only | none; exact fields/state/tool and negatives needed |
| `jurisdiction_change.v1` | jurisdiction | jurisdiction text | jurisdiction evidence | synthetic recognition only | none; exact fields/state/tool and negatives needed |
| `location_change.v1` | location | own player_name; location lookup key | arrived or unresolved unknown; preserve last known | state foreign location; hardening unknown location | none; exact fields/state/tool and negatives needed |
| `med_bed_heal.v1` | healed_parts | canonical healed_parts keys; bool true only | clears explicit parts | state selective heal; hardening wrong typed field | none; exact fields/state/tool and negatives needed |
| `monitored_space_down.v1` | none | event identity | monitored false | synthetic recognition only | none; exact fields/state/tool and negatives needed |
| `monitored_space_restored.v1` | none | event identity | monitored true | synthetic recognition only | none; exact fields/state/tool and negatives needed |
| `objective_complete.v1` | objective, mission_id | nonzero mission_id; objective | clears only exact matching objective; orphan evidence | real objective clearing | objective; per-field and orphan negatives needed |
| `objective_new.v1` | objective, mission_id | nonzero mission_id; objective | mission_objective_new or orphan; never invent mission | improvements orphan; state lifecycle | none; exact fields/state/tool and negatives needed |
| `objective_withdrawn.v1` | objective, mission_id | nonzero mission_id; objective | clears only exact matching objective; orphan evidence | state lifecycle; exact withdrawal branch gap | none; exact fields/state/tool and negatives needed |
| `party_invite.v1` | from_player | typed contract fields | observation-only output; no domain mutation | synthetic recognition only | none; exact fields/state/tool and negatives needed |
| `party_left.v1` | none | typed contract fields | observation-only output; no domain mutation | synthetic recognition only | none; exact fields/state/tool and negatives needed |
| `party_member_joined.v1` | player_name | typed contract fields | observation-only output; no domain mutation | synthetic recognition only | none; exact fields/state/tool and negatives needed |
| `personal_inventory_data.v1` | location_guid | own name; nonzero GUID; timestamp <=15s arrival | GUID evidence; no output | state confirmed GUID; improvements expired candidate | none; exact fields/state/tool and negatives needed |
| `qt_arrived.v1` | none | entity_class matches ship_class; aboard | possible_player_ship only | state ship_class_does_not_prove_ownership | none; exact fields/state/tool and negatives needed |
| `qt_calibration_complete_group.v1` | player | typed contract fields | observation-only output; no domain mutation | synthetic recognition only | none; exact fields/state/tool and negatives needed |
| `quantum_calibration_complete.v1` | none | typed contract fields | observation-only output; no domain mutation | synthetic recognition only | none; exact fields/state/tool and negatives needed |
| `quantum_calibration_started.v1` | none | typed contract fields | observation-only output; no domain mutation | synthetic recognition only | none; exact fields/state/tool and negatives needed |
| `quantum_route_set.v1` | none | typed contract fields | observation-only output; no domain mutation | synthetic recognition only | none; exact fields/state/tool and negatives needed |
| `refinery_complete.v1` | none | typed contract fields | observation-only output; no domain mutation | synthetic recognition only | none; exact fields/state/tool and negatives needed |
| `refinery_submitted.v1` | player_id | request fields only | requested movement | synthetic recognition only | none; exact fields/state/tool and negatives needed |
| `restricted_area.v1` | action | entered/exited | restricted evidence | improvements repeated observation | none; exact fields/state/tool and negatives needed |
| `reward_earned.v2` | none | exclusive amount+uec/auec OR item(+quantity); mixed unresolved | money confirmed or item observed; explicit/temporal association | state exclusive/dedup; real rewards; hardening quoted reward | reward/singular_reward/millisecond_reward/quoted_reward; currency/mixed grouping negatives needed |
| `session_start.v1` | player_geid | nonempty geid; optional name | identity; repeated character resets | hardening nonreset freshness | none; exact fields/state/tool and negatives needed |
| `shop_buy.v1` | price, quantity | nonnegative price; positive quantity; timestamp/nonzero player/provider for pending; currency_type UEC/aUEC for cash | requested then eligible pending; no cash until confirmed | state unique/ambiguous/missing currency/expiry | none; exact fields/state/tool and negatives needed |
| `shop_sell.v1` | price, quantity | same shop_buy guard; price is total, no quantity multiplier | requested then eligible pending | state shop tests | none; exact fields/state/tool and negatives needed |
| `shop_transaction_result.v1` | result | Success; Buying/Selling if present; player/provider exact; optional shop/kiosk match; <=120s unique unambiguous request | confirmed/failed/ambiguous/unresolved; unique Success is confirmed even without known currency; only explicit UEC/aUEC produces amount_auec | state shop; improvements ambiguity survives expiry; hardening nil identity | none; exact fields/state/tool and negatives needed |
| `transaction_complete.v1` | none | typed contract fields | observation-only output; no domain mutation | synthetic recognition only | none; exact fields/state/tool and negatives needed |
| `user_login.v1` | player_name | nonempty name; fresh session | reset name/world | service rotation; improvements session reset | none; exact fields/state/tool and negatives needed |
| `vehicle_impounded.v1` | reason | typed contract fields | observation-only output; no domain mutation | synthetic recognition only | none; exact fields/state/tool and negatives needed |
| `money_sent.v1` | recipient, amount, currency | nonzero recipient; amount>=0; explicit currency; no item/quantity | debit confirmed else unresolved | reader transfer; resilience fixed recipient/types | none; exact fields/state/tool and negatives needed |
| `contract_withdrawn.v1` | mission_name, mission_id | nonzero mission_id; mission_name | mission_withdrawn; remove matching | improvements withdrawal | none; exact fields/state/tool and negatives needed |

## Representative T5 contract tests

All tests below are in tests/test_recipe_matrix.py. Their hand-authored synthetic inputs do not constitute real-log provenance.

| Test | Independent expectation | Negative / limit |
|---|---|---|
| test_hand_authored_normalized_fields | Exact selected fields for armistice/restricted action, injury, reward/fine/transfer, mission/objective, identity/shard, healing, shop buy/sell/result, commodity buy, cargo | Verified build false; notification money strings, true-only heal map and integer request ID intentional; other fields need expectations. |
| test_persisted_requests_ambiguous_and_expired_never_change_confirmed_ledger | Requested, ambiguous, unresolved expired response and unchanged persisted ledger after restart | Null money and no confirmed trade rows for all three scenarios. |
| test_unknown_currency_unique_success_counts_trade_but_has_null_money | Missing/novel currency success confirmed; persisted trade counts and unknown amount counts increment, with two source occurrences | Income, spending and net totals unchanged; absence of currency does not mean no transaction. |
| test_known_currency_books_total_price_once_without_quantity_multiplier | Successful UEC price 265 books once despite quantity two, including after restart | No multiplication by quantity. |
| test_orphan_mission_unknown_location_and_health_remain_evidence | Orphan separate, partial missions; unknown current location retains last known; historical health true | Empty missions does not prove completeness; public bleeding/incapacitated null. |
| test_foreign_same_model_exit_and_quantum_are_not_ownership | Foreign channel means aboard true and own false; same model quantum only possible_player_ship | Mismatched owner exit cannot clear current ship; entity ownership unknown. |
| test_commodity_cargo_requests_and_generic_complete_do_not_confirm_inventory | Commodity buy/sell and cargo requested; generic complete observed | No confirmed trade rows or persisted ledger changes; inventory confirmation unsupported. |
| test_exact_objective_withdrawal_and_invalid_mission_do_not_invent_state | Exact withdrawal clears objective; accepted-event alias resolves | Different objective does not clear; zero mission ID adds no mission. |
| test_output_only_notifications_preserve_domain_state_and_remain_recent_observations | Eighteen output-only notifications retain observed rows without domain mutation | Timestamp bookkeeping still changes; remaining raw output-only recipes lack exact semantic tests. |
| test_missing_shop_required_field_produces_diagnostic_without_handler_or_trade | Missing price diagnostic | No Handler row or ledger change; other missing-field combinations incomplete. |
| test_json_only_wording_change_preserves_normalization_handler_and_tools | Temporary JSON changes provider/request/response/price wording; existing float normalization plus choose/constant maps explicit Accepted to Success; equivalent normalized fields, public evidence, persisted status/amount/source linkage and recent/trade/ledger tools | Failed/Unknown are never normalized to Success. Candidate bytes never replace bundled/publisher JSON; no retail wording claim. |
| test_compatibility_matrix_has_exact_bundle_and_tool_inventory | All 60 recipe IDs and seven tool names present | Inventory drift guard alone is not accuracy. |

## Public tool inventory

| Tool | Evidence/inputs | Meaning/state effects | Existing tests | Remaining assertions |
|---|---|---|---|---|
| `get_current_game_state` | optional environment; otherwise newest recognized source timestamp | last-observed state, observations, reader_health; current bleeding/incapacitated null | interfaces lifecycle; improvements freshness/health; hardening environment time | each state recipe output; unknown location/health and reset evidence |
| `get_active_missions` | optional environment; observed IDs | missions, partial reconstruction, orphans, reader_health | improvements orphan/withdrawal/freshness; state lifecycle | empty is not complete mission inventory; exact lifecycle outputs |
| `get_recent_game_events` | environment,count 1..50,event_type | observed/requested/unresolved/confirmed; contract/objective/location aliases | improvements legacy filters; service dedup | all output-only recipes, alias/count/evidence expectations |
| `get_trade_entries` | environment,time_range,category,limit,sort_by | confirmed trade rows, including unknown amount/currency; requests excluded | service category before limit; state shop cases | ambiguous/expired requests add no confirmed trade entries; uniquely successful missing-currency transaction remains present with absent amount_auec; sort/time/bounds |
| `get_trade_ledger` | environment,time_range,category | confirmed trade counts include unknown amounts; monetary sums include only known amounts; no inventory cost-basis profit | hardening ledger aggregation | ambiguous/expired/request cases leave ledger unchanged; unique missing-currency success increments entries and unknown_amount_entries, leaves monetary totals unchanged; time/category boundaries |
| `get_reader_update_status` | status only; no approval tool | manual approval and next-startup activation | service cannot approve; updates digest/activation/rollback; update improvements publisher generations | exact seven-name surface; status read side-effect free |
| `get_reader_health` | optional environment | diagnostics/freshness/backlog/unknown inputs; no proof game active | hardening health/header; improvements unknown samples; T1-T4 cases | structured failures with outputs; live host delivery remains unqualified |

## Real evidence and build qualification

tests/fixtures/real_notifications/provenance.json records eight exact sources, byte offsets and lengths: channel, apostrophe, millisecond_channel, objective, reward, singular_reward, millisecond_reward and quoted_reward. They cover only channel_change, objective_complete and reward_earned. Existing real notification and hardening tests assert byte assembly, channel fields, objective clearing, quoted items and money/item exclusivity. Archive filename build numbers provide source context, never complete build qualification.

The shipping bundle intentionally retains verified_game_builds=[]. None of the 60 recipes or seven tools has complete retail-build qualification. Real-fixture rows still lack variants, prerequisites and negatives. Synthetic tests cannot prove a running build emits all records; corpus replay without exceptions is not accuracy. T5 adds no observed fixture, runtime correction or claim about relocation loops, logout or recovery causes.

## Retained sequence contracts

Login/character resets, shard transitions, replacement/truncation generations, instruction activation/rollback and missing/older/out-of-order timestamp suites remain unchanged. Sources: test_state.py, test_improvements.py, test_hardening.py, test_service.py, test_updates.py, test_update_improvements.py and T1-T4 batch/recovery/scheduling suites. Generation resets/bookkeeping precede field validation. Engine-1 adapters cover legacy compatibility; future recipes use engine 3.

Updates remain manual approval and next-startup activation with fallback. Status/health are reads, and no AI approval or game action tool exists. Test runtimes are isolated. The user-selected updates/instructions.json remains at the bundled baseline; changed-wording tests use candidate bytes only.

## First-release omissions and prerequisites

Complete mission inventory, continuous/current health, entity-ID ownership, confirmed commodity/cargo inventory, inventory cost-basis profit, reminders and definitive reward grouping are unsupported. Empty missions mean partial reconstruction; one-way health cannot prove ongoing status/recovery; unknown location retains last-known evidence without inventing current location; cargo/commodity requests cannot prove inventory/payment.

Cost basis needs confirmed item identity, quantity, currency, acquisition/disposal linkage and inventory reconciliation, including transfers and nonpurchase acquisition. Reminders need explicit schedules, lifecycle and cancellation/completion rules. Definitive reward grouping needs explicit mission/reward IDs; a completion within ten seconds is only possible temporal association. No logout/recovery/relocation detection is inferred from recollection.
