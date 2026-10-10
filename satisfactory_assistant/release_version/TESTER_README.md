# Satisfactory Assistant Tester Notes

## Install

Run `install.bat`. It copies the release files to:

```text
%AppData%\ShipBit\WingmanAI\custom_skills\satisfactory_assistant
```

After installing, fully close and relaunch Wingman AI.

`install.bat` also installs the optional save parser dependency with `npm ci`
when Node.js/npm are available. Planning works without it, but `mode: audit`,
actuals comparison, and `locate` need that parser. If npm is missing during
install, install Node.js/npm and run this from the installed parser folder:

```text
npm ci --omit=dev --ignore-scripts
```

## Profile Setup

Your current Satisfactory config directory is:

```text
C:\Users\larse\AppData\Roaming\ShipBit\WingmanAI\3_1_1\configs\Satisfactory
```

In that profile, enable the `SatisfactoryAssistant` skill.

Recommended custom properties:

- `satisfactory_saved_dir`: leave blank for auto-detect, or set to `C:/Users/<you>/AppData/Local/FactoryGame/Saved`.
- `allow_plan_writes`: `true`.
- `max_response_items`: keep low while testing, such as `4` or `5`.

## Quickstart

Load a save, ask the wingman which save is active, note a plan item or two,
then ask for a Project Assembly stage plan. The three tools cover context,
notes, and planning:

- `get_satisfactory_context` - compact active-save summary, or a targeted
  `lookup` query.
- `update_satisfactory_plan` - add/complete notes, todos, and production
  flows; also reports plan status.
- `calculate_satisfactory_plan` - compute (and persist) a Project Assembly
  stage plan for a given `phase`, or run `mode: audit` to check the save
  for deficits and blocked items.

`calculate_satisfactory_plan` also accepts `scope: master` to build and
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

Run `mode: audit` with a `phase` (1-5) to compare the mirrored factory
against that phase's latest stored master-plan revision: the response
gets a bounded "Plan vs actual" section listing build-more lines,
unplanned production, and surplus. Phase 0 or no stored plan for that
phase keeps the classic audit unchanged. `get_satisfactory_context` takes
a `locate` query (item, recipe, or resource name) to find it on the
factory mirror: up to 5 coordinate matches plus a rendered schematic map
PNG for the top hit, with a display hint for the HUD. `locate` needs a
prior audit to have built the mirror; without one, the response explains
how to run one.

## Smoke Test

1. Start Satisfactory and load a save.
2. Ask the wingman: `Which Satisfactory save is active?`
3. Add a small plan: `Remember that the steel plant needs 240 iron ore per minute and 240 coal per minute.`
4. Ask: `What Satisfactory plans are blocked or missing inputs?`
5. Ask: `Plan Project Assembly phase 1.`
6. Ask: `Audit my Satisfactory save.`

The skill should only use the newest Satisfactory log to identify the active save.
