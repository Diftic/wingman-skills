# Architecture and behavior decisions

This page describes the 0.4.0 candidate implementation. Reader assembles/interprets log records using JSON; Handler interprets normalized events and persists state/evidence; Orchestrator owns settings, lifecycle and Wingman integration. T1–T8 and final standalone ownership are accepted. Reader uses a nominal 50 ms per operation and one shared 100 ms parse deadline; finditer shares the operation allowance. These cooperative deadlines are not hard realtime guarantees. Local archive/paced/recovery qualification is complete and final artifacts are prepared for controller binding/review. Actual host/native settings action/frozen runtime remain unqualified under [the release gates](PLAN.md).

```text
Game.log (read-only)
  -> bounded byte/notification assembly
  -> JSON recognition + extraction (Reader)
  -> fixed evidence/state rules (Handler)
  -> atomic local journal + snapshot
  -> settings, lifecycle and read-only tools (Orchestrator)
```

## State and history

Every recognized input is identified by environment, file generation and byte range. Journal rows and the resulting state snapshot commit in the same SQLite transaction. A watcher checkpoint advances only after ingestion succeeds; retries start at the durable checkpoint and skip already-committed occurrences. Byte fragments, incomplete notifications and oversized-line discard state survive restart correctly.

The watcher separates LIVE/PTU/EPTU/HOTFIX/TECH-PREVIEW. A file replacement or detected truncation starts a new generation and clears prior state. File identity, a prefix hash and bytes around the checkpoint are used to detect rewrites. This is a bounded heuristic, not a complete file-content history. One monitoring service per runtime directory is the supported arrangement; the approval CLI may run alongside it.

An activating standalone watch acquires the runtime's exclusive OS lease before instruction selection and database initialization and holds it until its database has closed. Partial initialization closes any opened database before releasing ownership; failed close retains the claim for retry. This excludes watch/host and watch/watch overlap, in either admission order. Host leases remain process-lived across unload; standalone ownership ends at successful Service close. Non-activating replay/explicit-instruction paths and short status/check/review APIs retain their separate scope.

Recognized domain history has no automatic deletion policy. Diagnostic-only evidence and unknown samples use explicitly bounded support tables, with committed lifetime reason totals separate from retained causes/stages. Runtime databases and downloaded definitions belong in a dedicated writable directory. Ledger queries aggregate in SQL. Tailer retains bounded pending work and commits ordered batches with resumable checkpoints; time budgets are cooperative between records and cannot preempt a single parse/commit. Missing optional environments do not stop healthy ones.

`get_reader_health` exposes operational counters, source timestamp/age, build ID, unread bytes, pending records and worker errors. Support diagnostics include persistent lifetime reason totals and bounded sanitized unknown samples; deliberately ignored records are distinguished from unrecognized records. Process-local counters reset on restart and do not measure recall. The default environment follows the newest recognized source timestamp, which does not prove the currently running game. Generation/session resets clear prior context.

## Observations and outcomes

- **Missions:** keyed by nonzero mission ID; accepted/completed/failed events require names. Objective changes affect a known mission. Availability/sharing does not mean acceptance.
- **Health:** recognized injuries normalize to six body parts. Healing clears only explicit true flags. A missing event never means recovery.
- **Location:** named inventory requests must match the known player. Nearby personal-inventory evidence establishes a location GUID; departure requires leaving that same nonzero GUID. Repeated known-location evidence refreshes the linking window without repeating announcements. Unmapped own-player locations clear current name/GUID/system and retain separate last-known history. Inventory evidence does not by itself prove physical travel.
- **Ships:** channel evidence establishes an aboard/model/owner observation. Exact model agreement alone remains `possible_player_ship`; it is excluded from proactive reactions. Unknown or mismatching model events do not become player events.
- **Trades:** a shop request needs a unique compatible response within 120 source-time seconds. Failure, missing identity or multiple candidates cannot book money. Currency must be explicit. Commodity requests have no proven completion route in this build, so remain requests.
- **Rewards:** explicit UEC/aUEC can become money; item quantities and unresolved bare numbers cannot. Repeated notification identity/time/content within the bounded session window is deduplicated. Nearby mission completion can be a possible association, not an asserted one. Reward components are not also booked as aggregate bundles.
- **Other movement/events:** remain observations or requests. An attachment is not automatically a purchase; an insurance callback code is not assumed to mean success.

The cash-flow ledger includes confirmed shop trades. General reward and transfer events remain available in event history. Inventory cost basis, reward-bundle UI and full old-skill parity are later work.

## Compatibility boundaries

The current package uses format 1, engine/event contract 3 and minimum reader 0.3.0. Contract-2 packages remain supported; contract-1 packages use a reader-side adapter. Channel recipes emit `ship_name`, optional `ship_class`, `owner` and `action`; fixed state consumes these fields without parsing channel wording. Boundary validation rejects incorrect consumed-field types, nonfinite numeric values and malformed healing maps. The old design draft's prose/operator wishlist is not executable.

All 60 mapped public event types have hand-authored synthetic fixtures. Final archive profiles retain exact baseline domain outputs across 174 files and 12,187,071 records each, with diagnostic compaction reported separately. This does not establish every branch or qualify a game build. Actual Wingman lifecycle and complete scenario/build qualification remain open.

The adapter targets the inspected Diftic development 3.1.2 source contract documented in `integrations/wingman_target/CONTRACT.md`. Optional master-disabled notifications use bounded literal public GUI transport and category/rate/repeat/catch-up suppression. They do not use the host command pipeline. Transport completion does not prove visible frontend rendering. Actual Wingman GUI/heartbeat, native settings review action and frozen runtime remain external qualification gates; public 2.x/general API 3 support is not claimed.

Unexpected monitor exceptions are reported in reader health and retried, then paused after three consecutive failures with a visible notice. Input diagnostics are committed and progress continues; I/O/database failures retry from the last durable checkpoint. Unload requests cooperative stop and allows two seconds for tasks, then cancels their awaits. A still-running poll retains its database until the worker exits. This bounds the adapter's wait; it cannot forcibly terminate a stuck Python thread.
