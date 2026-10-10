# Factory Assistant Tester Notes

## Install

Run `install.bat`. It copies the release files to:

```text
%AppData%\ShipBit\WingmanAI\custom_skills\factory_assistant
```

After installing, fully close and relaunch Wingman AI.

The skill works with any Wingman profile that has FactoryAssistant enabled.
Its Satisfactory behavior is built into the skill, so no Apex prompt or other
profile-specific instructions are required.
On startup it audits the first active save it can detect, then watches
Satisfactory's `SaveGames` tree and refreshes the mirror whenever a `.sav` is
created or changed. Set the desired refresh cadence with Satisfactory's own
autosave interval.

`install.bat` also installs the optional save parser dependency with `npm ci`
when Node.js/npm are available. Planning works without it, but `mode: audit`,
actuals comparison, and `locate` need that parser. If npm is missing during
install, install Node.js/npm and run this from the installed parser folder:

```text
npm ci --omit=dev --ignore-scripts
```

## Profile Setup

Enable `FactoryAssistant` in the Skills settings of any Wingman profile. Leave `game` on `auto` (the skill uses the game with the most recently loaded save) or select the game.

Recommended custom properties:

- `satisfactory_install_dir`: leave blank for automatic game detection, or choose the Satisfactory installation folder.
- `allow_plan_writes`: `true`.
- `max_response_items`: `12` by default.
- `map_overlay_enabled`: `true`.
- `map_overlay_display`: `1` for the primary monitor.
- `map_overlay_size`: `520` pixels by default.
- `map_overlay_duration_seconds`: `15`, or `0` to keep it open until hidden.
- `map_overlay_position`: top-left, top-centre, or top-right.

## Quickstart

Load a save, ask the wingman which save is active, note a plan item or two,
then ask for a Project Assembly stage plan. The tools cover context, notes,
planning, and the standalone map popup:

- `get_factory_context` - compact active-save summary, or a targeted
  `lookup` query.
- `update_factory_plan` - add/complete notes, todos, and production
  flows; also reports plan status.
- `calculate_factory_plan` - compute (and persist) a Project Assembly
  stage plan for a given `stage` (Satisfactory phase 1-5), or run `mode: audit` to check the save
  for deficits and blocked items.
- `show_factory_map` - locate something and open its schematic map in a
  top-centre popup, reopen the last map, or hide the popup.

`calculate_factory_plan` also accepts `scope: master` to build and
persist all five Project Assembly phases in one call, reporting how each
module carries forward between phases and what future phases will need.
Use `pin_recipes` and `ban_recipes` (semicolon-separated recipe names) to
force or exclude specific recipes on either scope.

For a single stage plan, `include_construction: true` attaches a
dependency-ordered construction bill of materials with per-task
commissioning checks; `create_build_todos: true` (needs
`include_construction`, `persist`, and plan writes allowed) also files a
journal build todo per task, capped at 20. `pace_scenarios` takes up to
four semicolon-separated pace multipliers (e.g. `"1.0;2.0;3.0"`) and
returns an unpersisted side-by-side comparison of windows, machines,
power, and raw totals instead of a normal plan.

Run `mode: audit` with a `stage` (Satisfactory phase 1-5) to compare the mirrored factory
against that phase's latest stored master-plan revision: the response
gets a bounded "Plan vs actual" section listing build-more lines,
unplanned production, and surplus. Phase 0 or no stored plan for that
phase keeps the classic audit unchanged. `get_factory_context` takes
a `locate` query (item, recipe, or resource name) to find it on the
factory mirror: up to 5 coordinate matches plus a rendered schematic map
PNG for the top hit and opens it in the skill's own top-centre popup.
`show_factory_map` is the preferred location entry point and is independent
of the HUD skill. Location maps need a mirror; the automatic watcher normally
keeps it ready. If startup could not
detect a save or the automatic audit failed, the response explains how to run
one manually.

## Smoke Test

1. Start Satisfactory and load a save.
2. Ask the wingman: `Which Satisfactory save is active?`
3. Add a small plan: `Remember that the steel plant needs 240 iron ore per minute and 240 coal per minute.`
4. Ask: `What Satisfactory plans are blocked or missing inputs?`
5. Ask: `Plan Project Assembly phase 1.`
6. Ask: `Audit my Satisfactory save.`

The skill should only use the newest Satisfactory log to identify the active save.

## Dyson Sphere Program (first version)

1. Start Dyson Sphere Program and load or start a game. Let it autosave once (or save manually).
2. Ask: `What am I short of?` or `How is my power?`
3. Ask: `Give me a full production report.` (audit)
4. Ask: `What is the recipe for processors?`

The skill reads the newest save in your Documents\Dyson Sphere Program\Save folder (also when
Documents is in OneDrive). Set `dsp_save_dir` only if it cannot find the folder. Saves from game
versions before 0.10.33 cannot be read. The map and production planning are not available yet.
