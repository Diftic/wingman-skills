# Core update requests for ShipBit

Changes the Star Citizen log pipeline needs **in Wingman Core** (ShipBit
`develop`), found while maintaining the live reader rules. Hand this to ShipBit
together with the next push. The rules file
(`Diftic/wingman-ai` `main`, `skills/sc_log_reader/updates/instructions.json`)
cannot do these on its own: Core validates a fixed schema and a fixed event list.

Core paths below are relative to the `wingman-ai` repository.

| # | Area | Status |
|---|---|---|
| 1 | `sc_game_events`: one switch per event type | Merged: ShipBit/wingman-ai#473, 16 Oct (3.2.9) |
| 2 | Item display names (translation table) | Merged: ShipBit/wingman-ai#473, 16 Oct (3.2.9) |
| 3 | Shop display names | Requested |
| 4 | Missions the game logs without a name are dropped | Requested |
| 5 | `sc_game_events` reads the wrong detail fields | Requested |
| 6 | Shop purchases: double reaction, failures never corrected | Merged: ShipBit/wingman-ai#473, 16 Oct (3.2.9); failed trades still not mentioned |
| 7 | New notification: Entering/Leaving Private Property | Requested |
| 8 | `qt_arrived` / `fatal_collision` need an internal ship class | Merged: ShipBit/wingman-ai#473, 16 Oct (3.2.9) |
| 9 | Bundled rules copy is revision 4 | Done by ShipBit in #472: develop bundles revision 10 |
| 10 | Shop UI purchases have no currency | Solved in rules revision 10 (released, bundled in 3.2.9) |
| 11 | `sc_game_events` passes the environment as the generation | Minor |
| 12 | Departures never detected (game renamed the inventory line) | Merged: ShipBit/wingman-ai#473, 16 Oct (3.2.9) |
| 13 | A contract keeps only its last objective | Merged: ShipBit/wingman-ai#473, 16 Oct (3.2.9) |
| 14 | Item names stay current without a Wingman release | Merged: ShipBit/wingman-ai#473, 16 Oct (3.2.9) |
| 15 | Routine pacing (#472) silences arrivals; make the gap a setting | Draft PR ShipBit/wingman-ai#476 |

---

## 1. `sc_game_events`: one switch per event type (ready)

Branch `feat/sc-game-events-event-switches` (from `upstream/develop`), commit
`371f989b`. Brings back the SC Log Reader settings menu, one switch per type of
event under one master per category, which the port into Core reduced to seven
category switches.

- `skills/sc_game_events/notifications.py`: `NOTIFICATION_OPTIONS` and
  `enabled_notification_events` restored verbatim from SC Log Reader 0.5.
- `skills/sc_game_events/main.py`: builds the policy from the allowed event
  types instead of categories.
- `skills/sc_game_events/default_config.yaml`: 7 masters + 53 type switches.
- **No migration needed:** the masters keep the `react_<category>` ids that
  `migration_324_to_325.py` saves; the new switches default to on.
- Tests: `tests/star_citizen/test_sc_game_events.py`, two new; all 16 skill and
  migration tests pass.

## 2. Item display names (translation table)

**Problem.** The game logs purchases with the item's class name and GUID only,
never its in-game name:

```
... itemClassGUID[b9867b9a-ad7c-4d02-b74c-88b9f0431d8b] itemName[Food_burrito_01_a] ...
```

So Core, SC Accountant and the Wingman all show `Food_burrito_01_a` instead of
"Dak Galbi Chicken Burrito". The "Transaction Complete" notification carries
no name either. Seen on builds 11010425 to 12913470 (all builds sampled).

**Why the rules file cannot fix it.** `services/sc_gamelog/reader.py`
(`Instructions.load`) accepts exactly five lookup tables
(`ship_manufacturer_prefixes`, `ship_manufacturer_names`, `cosmetic_ports`,
`locations`, `system_prefixes`) and rejects any other key, and the whole file is
capped at 512 KB. A rules file with an item table would be rejected by every
client.

**Built (branch `feat/sc-gamelog-item-names`, commit `ba278dae`, on top of item 1):**
- `services/sc_gamelog/data/item_names.json` (~570 KB, game build 12913470):
  `by_guid` and `by_class` -> in-game name. Bundled with the rest of
  `services/` by `WingmanAiCore.spec`; no spec change.
- `services/sc_gamelog/item_names.py`: lookup by GUID, exact class, one key with
  a manufacturer prefix (`SASU_<class>`), then the base item without its colour
  variant (`..._01_01_07` -> `..._01`); unknown items get a tidied class name
  ("ESPR Ballistic Cannon Barrel S3"), never the raw code.
- `services/sc_gamelog/state.py`: `shop_buy` / `shop_sell` get
  `item_display_name`; `item_name` stays the class name, so SC Accountant's
  ledgers keep matching. The pending request keeps it, so the confirmed
  purchase carries it too.
- `skills/sc_game_events/notifications.py`: shop reactions and the
  `recent_events` tool use `item_display_name`.
- Tests: `tests/star_citizen/test_item_names.py` (5).

**Regenerating each patch.** `tools/build_item_names.py` in the SC Log Reader
repository: extract `Data/Localization/english/global.ini` from `Data.p4k`
with unp4k, then
`python build_item_names.py --global-ini global.ini --sc-bridge <sc-bridge extraction_pipeline_v1> --build <build> --out item_names.json`.
Optional `--logs Game.log ...` reports coverage of the items bought.

**Coverage.** Hotfix 12913470 logs: 52 of 58 bought items named; the 6 left are
5 ship-weapon barrels sold at 1 aUEC and `crlf_consumable_steroid_01`, whose
localization key does not follow its class name. Exact mapping for those needs
the item records of the current patch (`Game2.dcb`); unforge 3.13 cannot read
the current DataCore format, StarBreaker can.

**Verified in-game (2026-10-13, Wingman 3.2.8, game build 12913470)** through the
skill-side copy of the lookup on local branch `live/skill-item-names`
(`0dc63400`): the installed Core is a frozen PyInstaller build, so Core-side
changes in `services/` only take effect in a rebuilt Core. Reactions named
purchases with their in-game names.

**Not yet:** `commodity_*` and `reward_earned` item names, and SC Accountant
showing the display name in its dashboard (it stores the event, so the name is
available to it).

## 3. Shop display names

Shops come through as internal names, e.g. `SCShop_TammanyAndSons_Lorville`,
`SCShop_lt_a_casaba_small_base_a-001`, `SCShop_BurritoBar_Food_RestStop`. Same
mechanism as item 2: a name table in Core, or a tidied fallback.

## 4. Missions the game logs without a name are dropped

The game sometimes writes contract notifications with an empty name but a valid
mission ID (5 accepted and 1 completed in build 12881860 logs):

```
Added notification "Contract Accepted:  : " [3] to queue. ... MissionId: [dbc1ea42-2204-4096-ac04-fc688a6efc61]
```

The rule correctly refuses to invent a name. But `services/sc_gamelog/state.py`
requires `mission_name` for `contract_accepted` / `contract_complete` /
`contract_failed` / `contract_withdrawn`, so the mission never enters
`active_missions`, its objectives become orphans, there is no reaction, and SC
Accountant never opens the operation.

**Proposal.** Accept these with `mission_id` alone and a neutral placeholder
name (e.g. "Unnamed contract"), marked as such.

## 5. `sc_game_events` reads the wrong detail fields

`_DETAIL_FIELDS` in `skills/sc_game_events/notifications.py` names fields the
rules never produce, so the Wingman gets the event without its detail:

| Event | Skill reads | Rules give | Suggested `_DETAIL_FIELDS` |
|---|---|---|---|
| `party_member_joined` | `player` | `player_name` | `("player_name",)` |
| `reward_earned` | `mission_name` | `amount`, `item_name`, `mission_id` | `("mission_name", "item_name")`; item rewards currently read "amount unknown" |
| `vehicle_impounded` | `vehicle` | `reason` | `("vehicle", "reason")` |
| `med_bed_heal` | `body_part` | `healed_parts` (dict) | render the healed keys |
| `commodity_buy` / `_sell` | `item_name` | `resource_guid`, `shop_name` | add `"shop_name"` (and the item display name, item 2) |
| `session_start` | `player_name` | `player_geid` | use the session's player name from state |

## 6. Shop purchases: double reaction, failures never corrected

- A purchase arrives first as `shop_buy` status `requested`, then again as
  `shop_buy` status `confirmed`. The policy keys on status and amount, so these
  are two different events and the Wingman can react twice to one purchase.
- If the trade fails, the outcome arrives as `shop_transaction_result`, which the
  skill has no template for, so a "you bought X" line is never corrected.

**Proposal.** React to `confirmed` (and `failed`) only, not to `requested`.

**Done for the reaction** in `skills/sc_game_events/main.py` (`_on_event`), commit
`aa962a58` on `feat/sc-gamelog-item-names`, with a test; verified in-game: `shop_buy` / `shop_sell` with status `requested` are
skipped, so the Wingman speaks once, about the confirmed trade with its name and
amount. Failed trades are still not mentioned.

## 7. New notification: Entering/Leaving Private Property

Unmatched SHUD notifications in build 12881860 logs:

```
Added notification "Entering Private Property: " [47] to queue.
Added notification "Leaving Private Property: " [2] to queue.
```

A zone notification in the safety family. A rule for it needs a new event type,
and `services/sc_gamelog/reader.py` only accepts the event types in its
built-in `EVENTS` list; `sc_game_events` would also need a template and switch.

**Proposal.** Add `private_property` (fields: `action` entered/exited) to
`EVENTS`, to the state (like `restricted_area`), and to `sc_game_events`. The
rule then ships in the live rules file.

## 8. `qt_arrived` / `fatal_collision` need an internal ship class

`state.py` passes these only when the ship class is known, and
`reader.py` `_legacy_fields` sets `ship_class` only when the `channel_change`
text starts with an internal manufacturer prefix. Ships logged by display name
never set it, so both events are dropped for them.

Seen live on hotfix 12913470: `channel_change` joined
`'RSI Constellation Mk V Centaurus'` (display name), then
`qt_arrived` with `entity_class` `RSI_Constellation_Mk5_Centaurus`, dropped.
**Proposal:** also accept the arrival when the entity class, with
manufacturer prefix and underscores normalised, matches the boarded ship's
display name, or map display names to classes with the item-name table
(item 2).

Note: the game only logs `Player Selected Quantum Target` for a destination
picked on the star map. A jump to a mission marker left no quantum line at all
(Everus Harbor -> HUR-L4, 13 Oct), so that travel cannot be reported.

**Done** in `services/sc_gamelog/state.py`, commit `58adf0a2`, tests in
`tests/star_citizen/test_travel_and_objectives.py`. Without an internal class, the arrival counts when the class matches the
boarded ship's display name after the manufacturer, with `Mk` and Roman
numerals normalised. Replayed: the 17:03 Constellation arrival is kept.

## 9. Bundled rules copy is revision 4

`services/sc_gamelog/data/instructions.json` ships revision 4 (0.3.0). The live
file is at revision 10 (0.3.6, released 2026-10-13 as `aa13a66c`; 3.2.8 still bundles 4), with identical rules to revision 9 apart from
the shop currency fix, plus 2 locations (`RR_P3_LEO`, `RR_P3_LEO_CLINIC`) and
the `maintainer` block. Users who cannot reach GitHub run on revision 4.
**Request:** copy the live file into the bundle at each Core release.

## 10. Shop UI purchases have no currency (solved in the rules)

`CEntityComponentShopUIProvider::SendShopBuyRequest` (armour, weapon and medical
kiosks) never logs a currency, unlike
`CEntityComponentShoppingProvider::SendStandardItemBuyRequest`, which logs
`currencyType[UEC]`. Unchanged since build 11010425. `state.py` sets
`amount_auec` only for UEC/aUEC, so these purchases were confirmed but had no
amount, and SC Accountant left them "unresolved" (34 of 38 purchases in the
first hotfix 12913470 session).

**Solved in rules revision 10:** the Shop UI branch sets `currency_type: aUEC`,
except shops matching Klescher/Prison/Merit. Replayed: 38 of 38 confirmed with
an amount. No Core change needed. Purchases already in SC Accountant's
"unresolved" list from earlier sessions stay there.

## 11. `sc_game_events` passes the environment as the generation (minor)

`skills/sc_game_events/main.py` `_on_event` passes `event.environment` as both
`environment` and `generation` to `NotificationPolicy.offer`, so the policy's
reset on a new Game.log never fires. `GameEvent` does not expose a generation;
either expose it or drop the argument. The 30-second quiet interval covers most
of the effect.

## 12. Departures never detected (game renamed the inventory line)

`location_departed` needs the location's inventory ID (`location_guid`), which
`state.py` takes from `personal_inventory_data` shortly after an arrival. That
rule matches `RequestOrCreatePersonalInventoryData`, which the game last wrote
in January (build 11010425). Since at least build 12660092 (29 Sep) it writes:

```
<Request Personal Inventory Data> Inventory data Request[0] sent for Player[Mallachi] [Team_CoreGameplayFeatures][Inventory]
```

with no location ID. So `location_guid` is never set and no departure has been
reported in any build Core has shipped with. The rules cannot fix this alone:
the new line carries no ID.

The ID is still in the log. The arrival comes with an inventory move in the
same second or within ~20 s, e.g. on 13 Oct:

```
19:42:17 Update Inventory Location  3141311038 -> 4243852663
19:42:17 location_change            RR_HUR_L4  (arrived at HUR-L4)
```

**Proposal:** in `state.py`, adopt the pending `_inventory_candidate`
(`loc_to`) as `location_guid` when `location_change` arrives within the
existing window, instead of waiting for `personal_inventory_data`. The next
move with `loc_from` equal to it is then the departure.

**Done** in `services/sc_gamelog/state.py`, commit `58adf0a2`, tests in
`tests/star_citizen/test_travel_and_objectives.py`. The id is adopted on arrival, or from the move logged up to 15 s after it.
A move out of it counts as a departure only aboard a ship: at 17:10 the pilot
walked from Everus Harbor's inventory into another and back. Replayed on
12913470: departures from Lorville (17:00) and Everus Harbor (19:07) at
takeoff, none on foot.

## 13. A contract keeps only its last objective

`state.py` stores one `objective` per active mission. A contract that hands out
several at once keeps only the last: "RSI Disc. Month: Courier Run (Exp. E)"
logged six New Objective notifications in the same second (collect and deliver
three cargo types), and the `missions` answer shows one of them.

**Proposal:** keep a short list of open objectives per mission (new adds,
complete/withdrawn removes), capped like the rest of the state.

**Done** in `services/sc_gamelog/state.py`, commit `58adf0a2`, tests in
`tests/star_citizen/test_travel_and_objectives.py`. Missions keep `objectives` (capped at 16); `objective` stays the latest open
one. The `sc_game_events` missions answer lists them: all six for the courier
run.

## 14. Item names stay current without a Wingman release

Item names (item 2) change with every Star Citizen patch, far more often than
Wingman ships. On 15 Oct a 3.2.8 user saw `SHLD_BEHR_S03_7CA_SCItem`: shops sell
ship components with an `_SCItem` suffix the localization does not use (fixed
in `e912de09`).

**Built** (commit `5a629173`): `services/sc_gamelog/item_names.py` keeps the
table current the way `rules.py` keeps the rules: the higher revision of the
bundled `data/item_names.json` and the last valid download wins at start, and
`service.py` checks
`https://raw.githubusercontent.com/Diftic/wingman-ai/main/skills/sc_log_reader/updates/item_names.json`
alongside the rules every half hour. A download replaces the running table only
when it validates (format 1, revision, maps of strings, at most 4 MB and 100,000
entries each) and carries a higher revision. Unreachable, missing (404) or
invalid changes nothing.

Kept out of the rules file on purpose: the table is ~570 KB (rules cap 512 KB),
and an older Core rejects a rules file with a lookup it does not know, which
would stop its rule updates.

The table carries its fixes as data: `strip_suffixes` (`["_SCItem"]`) is read
from it. The bundled table is revision 1. `build_item_names.py --revision N`
writes the next one. Tests: `tests/star_citizen/test_item_names.py` (newer
revision replaces and is cached; older, wrong format, not JSON, 404 and offline
change nothing; suffixes from the table). The test fixture keeps the download
offline.

**For the release:** the URL must serve a table before 3.2.9 users can update;
until then they keep the bundled revision 1.

## 15. Routine pacing silences arrivals; the gap should be a setting

ShipBit's #472 (16 Oct) gives zones, travel, the hangar and the login one spoken
line per ten minutes per group. Its "travel" group held the quantum steps and
arriving at and leaving a place, so a trip (route, takeoff, jump, arrival) kept
only its first line: the arrivals players asked for were silenced again.

**Proposed in draft ShipBit/wingman-ai#476** (`e37bdab1`): arrivals and
departures are not paced (the quantum steps keep their own group), and the gap
is the slider "Minutes between routine lines" (`routine_gap_minutes`), 2 to 20
minutes, default 5. Ten minutes reads as harsh, and players differ on how
chatty they want it. No migration (new property, merged by id).
