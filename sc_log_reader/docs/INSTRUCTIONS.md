# Authoring and distributing instructions

Engine 0.5.0 ships as `sc_log_reader`. The bundled revision 4 retains its original bytes (SHA-256 `5f4afbc7d64d20587e14518dc19493329427bcac14f204bb2eefa844f6757c3f`); the publishing file is separately maintained at revision 7. Reader operations share the 100 ms parse deadline and have at most 50 ms each, including one shared finditer allowance. Wingman checks and stages valid updates automatically, shows a native pop-up, and activates at the next eligible process startup. Instruction Recovery schedules rollback and blocks rejected revisions. Manual approval tools below remain available for standalone use, independently of this automatic host policy.

An activating standalone watch holds the runtime's exclusive OS lease before instruction selection and database initialization until successful database close. It cannot overlap another watch or host on that runtime; short status/check/review actions retain their separate scope. Host instruction decisions remain process-pinned. Final archive comparisons are complete; local paced/recovery qualification is complete; final artifacts are prepared for controller binding/review.

## What a JSON update can change

Recognition patterns, notification labels, explicit bracket-field aliases, capture groups, normalization, lookup names and excluded cosmetic ports. Existing state event types are fixed in Python; inventing a new event or changing the meaning of a state transition requires an engine release.

The source of truth is `src/sc_log_reader/data/instructions.json`. It contains all recipes and lookups in a single file. No `git` executable or MCP server is required on a user's machine.

## Package contract

Required keys:

- `package_id`: `sc_log_reader` or the historical `sc_log_reader_2`. Published JSON retains its original identifier and bytes. A new publication using the canonical identifier requires `minimum_reader_version` of at least `0.5.0` for older clients.
- `format_version`: `1`; `engine_version`: `3` for the current event vocabulary, including contract withdrawal. Engine 2 remains supported; engine 1 uses a compatibility adapter.
- `minimum_reader_version`: optional `major.minor.patch` requirement; current bundle requires `0.3.0`. Unsupported minimum versions produce `reader_upgrade_required` without becoming approval candidates.
- `revision`: positive monotonically increasing integer. Never change published bytes while reusing a revision.
- `version`, `release_notes`: user-facing labels; they do not establish compatibility.
- `verified_game_builds`: exact build strings established by replay/game qualification. Do not populate from a version label alone.
- `framing`: bounded record-start, timestamp and notification patterns. Timestamp and notification expressions each have one capture. Optional `notification_continuation` recognizes explicit continuation lines within 250 ms; a nearby timestamp alone never joins records. Optional `game_build` captures the build ID from the first 64 KiB of the live file header. Current notification framing uses the queue terminator, preserving internal quotation marks.
- `ignore_records`, `lookups`, `rules`: recognition and extraction definitions.

Rules contain `id`, `event`, `match`, `read` and `required`. Unknown keys, operations, input sources, events, bad capture indexes, duplicate JSON keys and incompatible versions are rejected. Conditions support `all`, `any`, `not`, literal `contains` and `regex`.

Input sources are `record.text`, `notification.text` and already-extracted `fields.NAME`. All matching rules are considered: two matches are ambiguous, even if they have the same event type. Make alternatives disjoint or put them inside one rule.

## Supported read operations

| Operation | Behavior |
|---|---|
| `capture` | Extract declared numbered regex groups into fields |
| `bracket_fields` | Extract a named bracket field or explicit aliases; conflicting values invalidate the record |
| `constant` | Assign a bounded scalar JSON literal |
| `normalize` | `trim`, `lower`, `remove_commas`, `int`, `float`, or `regex_replace` |
| `choose` | First matching local extraction alternative |
| `collect_true_fields` | Extract explicitly true flags from a declared list |
| `exclude_values` | Ignore a known excluded value from a lookup table |
| `quantity_with_unit` | Extract a number only with an explicitly accepted unit |
| `notification_payload` | Extract the label's payload; remove one trailing legacy colon |

`regex_replace` uses **literal replacement text only**. Backslash replacement expressions such as `\1` or `\g<name>` are rejected. Use `capture` for group extraction. There is no arbitrary expression language, looping, code import or function lookup.

For contract 2, a ship channel recipe supplies `ship_name`, optional internal `ship_class`, optional `owner`, and `action` (`joined` or `left`). Manufacturer recognition and entity-suffix normalization belong in JSON recipes. The old manufacturer lookup lists are retained for contract-1 compatibility; changing those lists alone does not change contract-2 recognition patterns. Keep display labels separate from internal entity classes to avoid false quantum attribution.

Example alias change (inside a `bracket_fields` operation):

```json
"fields": {
  "mission_id": ["MissionId", "MissionID"]
}
```

## Limits and errors

- Package: 512 KiB; record: 64 KiB; 128 rules; bounded condition and operation nesting.
- Regex: 2,048-character patterns, restricted repeat bounds/complexity, **50 ms per matching operation** and a **100 ms cooperative Reader.parse deadline** shared by recognition, extraction, normalization and final validation. Each operation receives at most the remaining entry time; lazy iterators retain one operation allowance while consumed. Late results are rejected. Framing and game-build header scans use separate per-operation allowances outside Reader.parse; package validation also occurs outside the parse deadline. These are cooperative safeguards: OS scheduling and non-interruptible work may overshoot. Timeout diagnostics retain `regex_budget_exceeded` and bounded reason/stage/rule details; they do not authorize state changes or money.
- Incomplete quoted notifications wait up to five seconds while monitoring. A new timestamped record that does not satisfy the explicit continuation rule flushes the previous incomplete notification as a diagnostic. They cannot book money or mutate game state.
- Missing required fields, conflicting aliases, conversion failures and timeouts produce local diagnostics. Missing source timestamps remain unknown; wall-clock observation time is stored separately.
- Handler applies additional fixed requirements, so deleting a JSON `required` field does not authorize a state transition or money booking.

These limits constrain the interpreter. They do not prove that a syntactically valid recipe describes the game accurately.

## Update storage and recovery

Under the configured runtime directory:

```text
instructions/
  manifest.json
  update.lock
  objects/<SHA256>.json
events.sqlite3
```

The manifest references complete content-addressed files. Downloads pass schema and basic engine-owned historical smoke checks before storage. Wingman stages automatically; optional standalone approval must name the currently reviewed digest. Manifest writes use a temporary file and atomic replacement; an OS lock coordinates concurrent update/recovery operations. Startup revalidates the staged digest, schema and smoke checks, keeps the prior file, and falls back to usable local definitions if a staged/active file is damaged. A corrupt manifest falls back to the bundle and reports an error. No usable fallback is an explicit startup error.

Startup preserves bundled bytes in content-addressed storage so a later engine upgrade can still roll back to that bundle. If an older installation never preserved its old bundle, rollback explicitly reports selection of the current bundled fallback. Reapproving active content does not replace the previous digest. Activation clears a consumed candidate. Skip is bound to the reviewed digest, cancels that digest's pending approval, and does not suppress later revisions.

The local `review-updates --state-dir PATH` window reviews already downloaded candidates and offers Update next startup, Later, Skip and Roll back. It does not expose network approval endpoints or AI approval tools. Later changes no manifest state. A Wingman button opening this window with its exact configured runtime directory remains integration work.

The live engine is immutable for its lifetime. Checking, approving and querying status do not hot-reload it. Rollback is also staged for next startup. A definitions change clears short-lived trade/location/reward correlation windows; it does not replay historical transactions into the ledger again.

Publisher trust comes from the **configured HTTPS GitHub URL and repository control**. SHA-256 detects byte changes and binds approval; it is not a publisher signature. Redirects, credentials, non-HTTPS sources and URL query parameters are rejected. No logs are sent to GitHub; requests only fetch the instruction file. Signed releases could be added later if the deployment threat model requires them.

## Release procedure

1. Add a representative fixture and expected event/fields for the changed game output.
2. Make the JSON change, increment the revision and describe the change.
3. Run instruction validation, the full tests and replay against representative logs for the intended build. Inspect diagnostics and monetary effects.
4. Publish the complete file at the configured URL. This project does not publish automatically.
5. Users review, approve and restart. Retain the previous published file for comparison and recovery.
