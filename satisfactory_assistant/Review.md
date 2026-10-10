# Satisfactory Assistant Full Review

Review date: 2026-06-17

Scope reviewed: `main.py`, `satisfactory_active_save.py`, `satisfactory_workspace.py`, `satisfactory_models.py`, `default_config.yaml`, `DEVLOG.md`, `TODO.md`, `PROJECT_PLAN.md`, and all tests.

## Findings

### Medium: Default context output can still exceed the low-token target

`satisfactory_workspace.py:39-41` and `satisfactory_workspace.py:264-300` now cap individual titles/material strings, which fixes the single-field blowup from the prior review. The full context response can still become large at the default settings, though, because `main.py:210-215` renders up to `max_response_items` per section and blocked flows are duplicated in both `Production flows` and `Blocked / missing inputs`.

Targeted default-config probe with 12 blocked flows, each using capped titles and capped material lists:

```text
24 rendered flow lines
17,999 characters
~4,499 rough tokens before headers/todos/goals/notes/changes
```

This misses the project plan's target return size of under 800 tokens and the skill docs' requirement for hard list limits. Fix by enforcing a global output budget in `get_satisfactory_context`, de-duplicating or shortening the blocked-flow section, and/or lowering per-flow material caps. Add a regression test that formats the actual context text with default `max_response_items` and asserts a hard character budget.

### Medium: `update_satisfactory_plan` still echoes unbounded titles in tool responses

The summary boundary is capped, but write-tool responses still include the raw submitted title at `main.py:315` and `main.py:320`. A long natural-language title from the user or model can produce a long tool response immediately, before the capped context path is involved.

Examples:

- `add_flow` returns `Added production flow '<full title>' (...) ...`
- `add_note` / `add_todo` / `add_goal` return `Added <kind> '<full title>' (...) ...`

This is another tool-return token risk. Keep the stored title unchanged, but clip the title in the acknowledgement string to a small display limit and add a regression test that calls the write path or helper formatting with an oversized title.

### Low: The source now contains a non-ASCII ellipsis despite the repo's ASCII-default rule

`satisfactory_workspace.py:46` uses a Unicode ellipsis as the truncation marker. Python handles it correctly and the runtime cap is 80 characters, but the file displays as mojibake (`â€¦`) in PowerShell line output. The project instructions default to ASCII for edits unless there is a clear reason. Prefer an ASCII marker such as `...` here; it avoids terminal/display ambiguity and keeps truncation tests simple.

## Resolved Since Prior Review

- Status-focused context is fixed. `summary(..., focus="blocked")` now returns blocked flows, and balanced/missing focus paths have tests.
- Single-field token blowups in summaries are partially fixed with title/material count and length caps.
- Travel URL parsing is now delimiter-based and ignores unknown intervening query tokens.
- Large logs continue to stream line-by-line, so middle-only save switches are not skipped.
- `resolve_save_file` continues to handle `OSError` gracefully.
- Active-save source-type priority remains fixed; newest recognized log evidence wins.
- Workspace containment remains Windows-case-insensitive only on Windows.

## Verification

- `python -m pytest skills/satisfactory_assistant/tests -q`: 42 passed, 1 skipped.
- `python -m compileall -q skills/satisfactory_assistant`: passed.
- `python -m ruff check skills/satisfactory_assistant`: passed.
- Import check passed: `skills.satisfactory_assistant.main` imports and exposes `SatisfactoryAssistant`.
- Bare `print(` scan found no bare implementation prints; implementation logging uses `self.printr.print(..., server_only=True)`.
- Filesystem scan found no recursive broad reads. Runtime access is still limited to `Logs/*.log`, literal `SaveGames/<profile>/<save>.sav` checks, and the generated per-save workspace.
- Targeted probes passed for status-focused blocked flow lookup, delimiter parsing with unknown travel tokens, invalid configured paths, and single-field truncation.
- Targeted context-size probe confirmed the remaining output-budget finding.

## Test Gaps

- Manual Wingman runtime tool calls are still not done because they need live `config`, `settings`, and `wingman` objects.
- Multiplayer, dedicated-server logs, Epic profile folder naming, and Linux/Proton paths remain unverified.
- The POSIX-only containment test is skipped on Windows, as expected.

## Positive Notes

- The skill remains on-demand with `auto_activate: false`.
- Tool count remains two, which is appropriate for token budget.
- Resolver never falls back to newest `.sav`; it still relies on the newest log.
- Per-save writes stay under `get_generated_files_dir()/saves/<safe_save_key>/`.
- Production flows model structured inputs, outputs, and status.
- No new dependencies or Core API/interface changes were introduced.

## Next Pass Checklist

- Add a global context output budget and avoid duplicating full blocked-flow lines.
- Clip write-tool acknowledgement titles while preserving stored titles.
- Replace the Unicode ellipsis marker with ASCII `...` or document why non-ASCII is required.
- Add tests for formatted context length and write acknowledgement length.
- Re-run pytest, compileall, ruff, import check, and bare-print scan.
- Run both tools inside a live Wingman session before packaging.
