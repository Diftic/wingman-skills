# Factory Assistant architecture

Factory Assistant uses the SC Log Reader terms, with one change for many games:
**one Orchestrator for all games, and one Reader + Handler for each game.**

| Part | Folder | Job |
|---|---|---|
| Orchestrator (one) | `main.py`, `factory_orchestrator/` | Wingman tools, settings, lifecycle, map popup, refresh loop, game registry |
| Shared | `factory_shared/` | The contract (`contract.py`), the per-save journal (notes, jobs, goals, production setups), storage, helpers |
| GameHandler (per game) | `factory_games/<game>/game.py` | The only game module that the Orchestrator talks to. Implements `GameHandler` |
| Handler (per game) | `factory_games/<game>/handler/` | Planning, solver, audit, logistics, reports for that game |
| Reader (per game) | `factory_games/<game>/reader/` | Find the active save, parse the save, item/recipe catalog, game data |

```text
Wingman
  |  4 game-neutral tools: get_factory_context, show_factory_map,
  |                        update_factory_plan, calculate_factory_plan
  v
main.py (Orchestrator) --registry--> factory_games/<game>/game.py (GameHandler)
                                         |
                                         v
                                     handler/  -->  reader/
                     (all of them may use factory_shared/)
```

## The contract (`factory_shared/contract.py`)

The Orchestrator gives each GameHandler a `HandlerContext` with callbacks:
`generated_dir`, `setting(id)`, `diag(text)`, `show_map(image)`,
`max_response_items()`, `allow_plan_writes()`. A game never imports Wingman.

A GameHandler supplies:

| Member | Use |
|---|---|
| `game_id`, `display_name`, `setting_ids` | Identity, `game` setting value, game-specific settings to validate |
| `prompt()` | Game-specific LLM text (for example: in Satisfactory, "stage" = Project Assembly phase) |
| `active_save()` | Cheap check for automatic game selection |
| `context()`, `show_map()`, `update_journal()`, `calculate()` | The four tools |
| `auto_refresh_once()` | Called every 5 seconds; the game decides if a new save needs an audit |
| `capabilities()` | Which plan options the game supports |

## Game selection

Setting `game`: `auto` (default) or a game id. In `auto`, the game with the most
recently confirmed active save answers. If no game has a save, the first
registered game answers (so the player gets "load a save first"). The refresh
loop runs for all games in `auto`, or for the selected game only.

## Update frequency

Data updates each time the game writes a save. The autosave interval in the
game settings controls the update frequency. The `game` setting hint and the
skill prompt tell the player this. The skill description stays one line long
so it fits the Skills list.

## Rules (checked by `tests/test_layer_boundaries.py`)

1. `main.py` and `factory_orchestrator/` never import `factory_games`. They reach a game only through `factory_orchestrator/registry.py` (import by path at runtime).
2. Only `main.py` imports Wingman (`api`, `skills`, `wingmen`, `services`).
3. `factory_shared/` imports no game and no Orchestrator code.
4. Game code imports only its own game and `factory_shared/`.
5. A Reader imports only its own Reader (never the Handler or `game.py`).
6. The Wingman tools have no game name in them.

## Add a new game

1. Make `factory_games/<game>/reader/` (save + catalog) and `handler/` (logic).
2. Make `factory_games/<game>/game.py` with a `GameHandler` subclass.
3. Add one line to `GAMES` in `factory_orchestrator/registry.py`.
4. Add the game to the `game` setting options and its own settings (prefix `<game>_`) in `default_config.yaml`.
5. Run the tests. The layer test also loads every registered game.

## Games

| Game | Reader | Handler | Status |
|---|---|---|---|
| Satisfactory | Active save from the game log; full save parse (Node parser); Docs catalog | Planning, solver, audit, map | Complete (from Satisfactory Assistant 0.9.1) |
| Dyson Sphere Program | Newest `.dsv` in the Documents save folder; short read (header, galaxy seed, production and power statistics); catalog JSON from `tools/extract_catalog.py` | Production report, shortages, power, research speed, lookup, journal | Short reader. No map or planning yet. Reads 0.10.33 and newer |

## Module map (from Satisfactory Assistant 0.9.1)

| Old | New |
|---|---|
| `main.py` tool logic | `factory_games/satisfactory/game.py` (`SatisfactoryHandler`) |
| `satisfactory_adapter` | `factory_games/satisfactory/handler/pipeline` |
| `_solver`, `_plan_models`, `_logistics`, `_construction`, `_extraction`, `_actuals`, `_scenarios`, `_master_plan`, `_reports`, `_reference` | `factory_games/satisfactory/handler/<same name>` |
| `satisfactory_map` | `factory_games/satisfactory/handler/locate` |
| `_active_save`, `_save_parser`, `_mirror`, `_install`, `_docs`, `_dataset`, `_progression`, `_models`, `data/`, `tools/save_parser/` | `factory_games/satisfactory/reader/<same name>` |
| `satisfactory_workspace`, `_store` | `factory_shared/workspace`, `factory_shared/store` |
| journal part of `update_satisfactory_plan`, rate parsing, config coercion | `factory_shared/journal`, `factory_shared/coerce` |
| `satisfactory_map_overlay`, `_overlay_win32` | `factory_orchestrator/map_overlay`, `overlay_win32` |

Tool renames: `get_satisfactory_context` → `get_factory_context`,
`show_satisfactory_map` → `show_factory_map`, `update_satisfactory_plan` →
`update_factory_plan`, `calculate_satisfactory_plan` → `calculate_factory_plan`
(`phase` → `stage`, `include_alternates` → `allow_recipes`).

## Known limits

- `factory_shared/store.py` also holds the plan tables that Satisfactory uses. Another game can use them or ignore them.
- Per-save data is in this skill's own generated-files folder. Notes and plans from Satisfactory Assistant are not copied automatically.
