# Satisfactory Assistant Skill Project Plan

## Producer Summary

Build `SatisfactoryAssistant` as an on-demand Wingman AI skill that helps Satisfactory players plan, track, and maintain factories for the currently active game save. The core product promise is strict save isolation: the skill must only inspect or modify files associated with the active save, and the active save must be determined from the newest Satisfactory log file found in configured or common game folders.

This plan is the implementation handoff for Claude. Codex will review, test, and provide feedback after implementation.

## Product Goals

- Help players maintain per-save factory plans, todo lists, notes, production targets, and change logs.
- Track factory inputs, outputs, production rates, recipes, machines, bottlenecks, and dependencies as first-class planning data.
- Avoid token bloat by exposing a small tool surface and returning compact summaries.
- Never mix data between saves.
- Work without parsing binary `.sav` files in the MVP.
- Leave room for future save parsing or external planner imports without making MVP depend on them.

## Non-Goals For MVP

- Do not implement binary `.sav` parsing.
- Do not add network dependencies.
- Do not auto-monitor logs in the background.
- Do not expose broad filesystem tools.
- Do not read every save folder to infer player history.
- Do not auto-activate the skill.

## Skill vs MCP Decision

This is acceptable as a Wingman skill because it is meant to be a locally installed game assistant tied to Wingman configuration and generated files. The actual data operations are filesystem-oriented, which could fit an MCP server, so the skill must stay conservative:

- `auto_activate: false`
- no more than 2 AI-callable tools for MVP
- no raw file dumps in tool responses
- all config values retrieved just-in-time
- no background polling unless a later product decision explicitly requires it

## Expected Skill Files

Create these files during implementation:

```text
skills/satisfactory_assistant/
|-- main.py
|-- default_config.yaml
|-- logo.png
|-- active_save.py
|-- workspace.py
|-- models.py
|-- tests/
    |-- test_active_save.py
    |-- test_workspace.py
```

Keep helper modules small. If the implementation can stay clear with fewer modules, prefer fewer files.

## Configuration

`default_config.yaml`:

- `module: skills.satisfactory_assistant.main`
- `name: SatisfactoryAssistant`
- `display_name: Satisfactory Assistant`
- `author: ShipBit`
- `auto_activate: false`
- `discoverable_by_default: false`
- tags:
  - `Game`
  - `Satisfactory`
  - `Planning`

Suggested custom properties:

- `satisfactory_saved_dir`
  - type: `string`
  - default: `""`
  - hint: optional path to the Satisfactory `Saved` directory. If empty, auto-detect common locations.
- `max_log_bytes`
  - type: `number`
  - default: `1048576`
  - hint: read only the tail of each log up to this many bytes.
- `max_response_items`
  - type: `number`
  - default: `12`
  - hint: cap list items returned to the AI.
- `allow_plan_writes`
  - type: `boolean`
  - default: `true`
  - hint: allow the assistant to write per-save planning notes.

Do not cache these values in `validate()`.

## Discovery Metadata

Use concise discovery text. Example:

```yaml
description:
  en: Help Satisfactory players plan and maintain factories, todos, notes, and production goals for the currently active save only.
discovery_keywords:
  - satisfactory
  - factory planning
  - production plan
  - active save
  - factory notes
  - game save planning
```

## Prompt Guidance

Add a short `prompt` section in `default_config.yaml`:

```yaml
prompt: |
  You can help with Satisfactory factory planning for the active save only.
  Use the skill tools when the player asks about save-specific plans, notes, todos,
  production goals, factory layouts, material inputs, item outputs, recipes,
  machine counts, bottlenecks, or maintenance work.
  Never claim access to other saves. If the tool says no active save is confirmed,
  ask the player to start or load a Satisfactory save first.
```

## Crafting Planning Model

Satisfactory is a crafting and logistics simulator. The skill must treat material flow as core planning data, not just free-form notes.

### User Inputs To Capture

Capture these input types when the player provides them:

- desired output item and rate, e.g. `Heavy Modular Frame 10/min`
- source inputs and rates, e.g. `Iron Ore 240/min`, `Coal 120/min`
- intermediate items, e.g. `Steel Beam`, `Encased Industrial Beam`
- recipe names or alternate recipes, e.g. `Solid Steel Ingot`, `Steel Rod`
- machine type and count, e.g. `4 Constructors`, `8 Foundries`
- clock speed or shard assumptions, e.g. `150%`, `no overclocking`
- belt, pipe, train, truck, drone, or power constraints
- factory area or location label, e.g. `Rocky Desert steel plant`
- dependency links, e.g. `uses ingots from Main Smelter`
- status, e.g. planned, building, blocked, balanced, or needs audit

Inputs may arrive as natural language. The implementation should store the exact player wording in `details` and extract concise structured fields where obvious. Do not hallucinate exact recipes or rates if the user did not provide them.

### Outputs The Skill Should Produce

The context tool should produce compact, player-useful outputs:

- active save identity
- tracked production lines with target outputs
- required or known input materials
- known machine and recipe assumptions
- open bottlenecks or missing inputs
- current todos grouped by factory area when possible
- recent production changes
- short "next actions" derived from open todos and blocked flows

The skill should not output raw databases or full logs. It should summarize the active save's planning state in the smallest useful form.

### Production Flow Record

Represent production planning as a `production_flow` record in the per-save workspace.

Fields:

- `id`: short stable id, e.g. `flow_20260617_153012_ab12`
- `created_at`: ISO timestamp
- `updated_at`: ISO timestamp
- `title`: short player-facing name, e.g. `Steel beam expansion`
- `area`: optional factory area or location label
- `recipe`: optional recipe or alternate recipe name
- `machines`: optional concise text, e.g. `8 Foundries at 100%`
- `inputs`: list of compact material-rate strings, e.g. `["Iron Ore 240/min", "Coal 240/min"]`
- `outputs`: list of compact material-rate strings, e.g. `["Steel Ingot 360/min"]`
- `constraints`: optional concise text for belts, pipes, power, space, or logistics limits
- `status`: `planned`, `building`, `blocked`, `balanced`, `done`, or `archived`
- `details`: original player wording or extra notes

Do not require all fields. A partially known flow is still valuable as long as it is scoped to the active save.

## Low-Token Tool Surface

Expose two tools in MVP.

### Tool 1: `get_satisfactory_context`

Purpose: Return the active save identity and a compact summary of that save's planning workspace.

Signature sketch:

```python
@tool(
    description=(
        "Get compact Satisfactory planning context for the active save. "
        "WHEN TO USE: user asks about current factory plans, todos, notes, "
        "production goals, or which save is active."
    ),
    wait_response=True,
)
async def get_satisfactory_context(self, focus: str = "") -> str:
    ...
```

Behavior:

- Resolve the active save from the newest log file.
- If no active save can be confirmed from logs, return a short explanation and do not inspect saves.
- Return:
  - active save name
  - active save file path or relative path if found
  - log file used for detection
  - last modified time
  - summary of per-save notes
  - top open todos, capped
  - known production goals, capped
  - tracked production flows with inputs and outputs, capped
  - blocked or imbalanced flows, capped
  - recent changes, capped
- If `focus` is provided, filter locally before returning.

Target return size: under 800 tokens.

### Tool 2: `update_satisfactory_plan`

Purpose: Add or update planning records for the active save.

Signature sketch:

```python
@tool(
    description=(
        "Update Satisfactory planning notes for the active save. "
        "WHEN TO USE: user asks to remember, add, update, complete, or remove "
        "a current-save todo, note, factory area, or production goal."
    ),
    wait_response=True,
)
async def update_satisfactory_plan(
    self,
    action: Literal[
        "add_note",
        "add_todo",
        "complete_todo",
        "add_goal",
        "add_flow",
        "update_flow",
        "archive_item",
    ],
    title: str,
    details: str = "",
    item_id: str = "",
    inputs: str = "",
    outputs: str = "",
) -> str:
    ...
```

Behavior:

- Resolve active save first.
- Refuse writes if no active save is confirmed.
- Refuse writes if `allow_plan_writes` is false.
- Write only inside the generated per-save workspace.
- For `add_flow` or `update_flow`, parse `inputs` and `outputs` as semicolon-separated material-rate strings. Example: `Iron Ore 240/min; Coal 240/min`.
- Preserve the original natural-language plan in `details`.
- Return a concise status line plus item id when relevant.

Target return size: under 200 tokens.

## Active Save Detection

The resolver is the critical component.

### Common Roots

Implementation should support:

- configured `satisfactory_saved_dir`
- Windows common path: `%LOCALAPPDATA%/FactoryGame/Saved`
- Linux or Proton best-effort paths only if easy and non-invasive
- custom path expansion with environment variables and `~`

The expected structure is generally:

```text
Saved/
|-- Logs/
|   |-- FactoryGame.log
|   |-- *.log
|-- SaveGames/
    |-- <account-or-profile>/
        |-- *.sav
```

Claude must verify exact current Satisfactory paths and log patterns during implementation. If paths differ, update tests and comments accordingly.

### Latest Log Rule

The active save must be established from the newest log file in the Satisfactory game folders.

Algorithm:

1. Build candidate `Saved` roots from config and common locations.
2. For each root, collect log candidates under `Logs/*.log`.
3. Select the newest log by `mtime`.
4. Read only the tail of the selected log, capped by `max_log_bytes`.
5. Scan from bottom to top for a save-load or save-open line that references a `.sav` path or save name.
6. Resolve the referenced save against the matching `SaveGames` directory.
7. If a referenced save file cannot be found, keep the active save identity from the log but mark `save_file_found=false`.
8. If no active save can be extracted from the newest log, return `No active save confirmed` and do not fall back to scanning all saves.

The "no fallback to newest `.sav`" rule protects the user's requirement. A newer save file is not proof that it is the active save unless the newest log confirms it.

### Parser Pattern Strategy

Do not hard-code one fragile log format. Implement a small list of regex patterns and tests:

- absolute or relative paths ending in `.sav`
- quoted save names near load/save keywords
- lines containing likely keywords such as `LoadGame`, `SaveGame`, `save`, `session`, or `FactoryGame`

Keep parsing pure and unit-testable:

```python
def extract_active_save_reference(log_tail: str) -> ActiveSaveReference | None:
    ...
```

If exact patterns are unknown, start broad but conservative:

- accept `.sav` paths as strong evidence
- accept named save references only when the line also includes load/open/session wording
- ignore autosave/write-only lines unless no better load line exists and the line clearly identifies the current session

## Save Isolation Contract

Every read or write must pass through the active-save guard.

Allowed read scope:

- the selected newest log file tail
- the active `.sav` file metadata only, not binary contents for MVP
- the generated per-save workspace for that active save

Allowed write scope:

- only the generated per-save workspace for the active save

Never write into the Satisfactory install, log, or save directories.

Never read other save workspaces after resolving the active save.

Use `Path.resolve()` containment checks before all file operations. On Windows, compare normalized lowercase resolved strings.

## Per-Save Workspace

Store planning files under:

```text
self.get_generated_files_dir()/saves/<safe_save_key>/
```

`safe_save_key` should be stable and collision-resistant:

```text
slug(save_name) + "-" + short_sha256(active_save_path_or_identity)
```

Suggested files:

```text
manifest.json
notes.jsonl
todos.jsonl
goals.jsonl
flows.jsonl
changes.jsonl
```

Use JSON Lines for append-friendly history and simple recovery. Compact summaries are generated from these files.

### Record Schemas

Common fields:

- `id`: short stable id, e.g. `todo_20260617_153012_ab12`
- `created_at`: ISO timestamp
- `updated_at`: ISO timestamp
- `title`: short text
- `details`: optional text
- `status`: `open`, `done`, or `archived`

Goal-specific fields can be added later:

- `target_rate`
- `item`
- `location`
- `inputs`
- `outputs`

Flow records are for crafting and logistics planning. They should use the production flow schema above and live in `flows.jsonl`.

Keep schema permissive but summaries strict.

## Error Handling

Return user-actionable messages:

- "No Satisfactory log folder found. Configure Satisfactory Saved directory."
- "Newest log found, but no active save reference was detected."
- "Active save detected from log, but save file was not found. Planning workspace is still available for this identity."
- "Plan writes are disabled in skill settings."

Log server-only diagnostic detail with `Printr`, never bare `print()`.

Use:

```python
self.printr.print("message", color=LogType.SYSTEM, server_only=True)
```

For any client-visible message, use `await self.printr.print_async(...)`.

## Implementation Phases

### Phase 1: Scaffold

- Create `main.py`, `default_config.yaml`, and `logo.png`.
- Implement class `SatisfactoryAssistant(Skill)`.
- Implement `validate()` with just-in-time config validation only.
- Implement `prepare()` and `unload()` as minimal pass-through methods.

Acceptance:

- Skill loads with no Satisfactory installation present.
- No API/interface files are changed.
- No new dependencies.

### Phase 2: Active Save Resolver

- Implement root discovery.
- Implement newest log selection.
- Implement log tail reading.
- Implement active save extraction.
- Implement save path resolution.
- Unit test with temp fixtures.

Acceptance:

- Latest log wins over older logs.
- Resolver refuses to inspect saves when latest log has no active save.
- Resolver resolves `.sav` references from log fixtures.
- Resolver handles missing game folder gracefully.

### Phase 3: Per-Save Workspace

- Implement safe save key generation.
- Implement workspace creation under generated files.
- Implement JSONL append and summary reads.
- Implement containment checks.

Acceptance:

- Workspaces are separate for separate active saves.
- Path traversal attempts fail.
- Writes never target game save or log directories.

### Phase 4: Tools

- Implement `get_satisfactory_context`.
- Implement `update_satisfactory_plan`.
- Keep tool descriptions concise.
- Cap return sizes with `max_response_items`.

Acceptance:

- Tool responses are compact.
- Tool output references only active save data.
- Write tool returns item ids.
- No raw JSONL dumps are returned.

### Phase 5: Testing And Feedback

Codex should test Claude's implementation with:

- `python -m pytest skills/satisfactory_assistant/tests`
- targeted import check for the skill module
- manual fixture call for both tools if easy
- grep for banned `print(`
- grep for unsafe broad filesystem reads

Do not start Core for API regeneration because this plan does not require Core API changes.

## Test Fixtures To Create

Use temp directories shaped like:

```text
tmp/FactoryGame/Saved/
|-- Logs/
|   |-- FactoryGame-old.log
|   |-- FactoryGame.log
|-- SaveGames/
    |-- 123456789/
        |-- Desert_Main.sav
        |-- Oil_Expansion.sav
```

Cases:

1. Newest log references `Oil_Expansion.sav`; resolver returns that save.
2. Older log references `Desert_Main.sav`; ignored because it is not newest.
3. Newest log has no save reference; resolver returns no active save and does not inspect `SaveGames`.
4. Log references a missing save; resolver returns active identity with `save_file_found=false`.
5. Malicious workspace item id or title cannot escape workspace.
6. `allow_plan_writes=false` prevents writes.
7. `max_response_items=2` caps summaries.
8. `add_flow` stores semicolon-separated inputs and outputs as lists.
9. `get_satisfactory_context` includes capped flow summaries with output targets and required inputs.
10. A flow added in one active save never appears when a different active save is resolved.

## Code Quality Guardrails

- Follow `skills/AGENTS.md` and `skills/README.md`.
- Never use bare `print()`.
- Retrieve custom properties just-in-time.
- Avoid `Optional` in new Pydantic models; this skill should not need new Pydantic models.
- Keep all new code cross-platform.
- Guard any Windows-specific behavior.
- Do not change `api/interface.py`, `api/enums.py`, or FastAPI endpoints.
- Do not add dependencies for MVP.
- Use type hints.
- Keep comments sparse and useful.
- Use local helpers for pure parsing so tests are fast.

## Token Budget

Estimated active schema cost:

- 2 tools
- small parameter sets
- concise descriptions

Target: under roughly 250 schema tokens while active.

Tool return caps:

- context tool: under 800 tokens
- update tool: under 200 tokens

Do not return:

- raw logs
- raw JSONL
- full todo databases
- complete save folder inventories

## Future Enhancements

Only after MVP is stable:

- Import planner exports from tools such as Satisfactory Calculator or interactive map exports.
- Parse `.sav` with a dedicated, reviewed dependency or optional external helper.
- Detect factory locations or train routes from parsed save data.
- Add production rate calculators using a small embedded recipe dataset.
- Add optional proactive session detection hook if token and runtime costs are justified.

Future enhancements must preserve save isolation and low-token returns.

## Claude Handoff Checklist

Before coding:

- Read root `AGENTS.md` instructions from the conversation.
- Read `skills/AGENTS.md`.
- Read relevant sections of `skills/README.md`.
- Inspect at least one modern `@tool` skill.

During coding:

- Implement resolver first.
- Add tests before exposing tools.
- Keep all writes inside generated per-save workspace.
- Do not implement `.sav` parsing.

Before handing back:

- Run unit tests.
- Run import check.
- Confirm no bare `print()`.
- List any unresolved Satisfactory log pattern assumptions.

## Definition Of Done

The MVP is done when a player can say:

- "Which Satisfactory save am I in?"
- "Remember that I need to upgrade the steel line to 240 beams per minute."
- "The steel plant should output 360 steel ingots per minute from 240 iron ore and 240 coal."
- "What inputs do I need for my heavy modular frame line?"
- "Which production lines are blocked or missing materials?"
- "What are my open factory todos?"
- "Mark the steel line upgrade done."

And the skill:

- uses the newest log to identify the active save
- refuses to proceed if no active save is confirmed
- stores and retrieves only data scoped to that active save
- treats item inputs, item outputs, rates, recipes, machines, and constraints as structured planning data where possible
- returns concise summaries
- passes tests
- follows Wingman skill conventions
