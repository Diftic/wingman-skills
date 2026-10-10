# Satisfactory Assistant - Devlog

Authoritative implementation, handover, and quality-control log for
[`SatisfactorySkillPlan.md`](SatisfactorySkillPlan.md).

Codex owns planning and QC. Claude owns implementation. The user owns final
scope and acceptance decisions. Durable handover evidence lives here rather
than only in agent chat.

## Handover protocol

- Use one entry per work package and keep entries newest first.
- Codex creates the entry and implementation packet at G0.
- Claude updates the implementation sections before G1 handover.
- Codex appends independent QC evidence and the G2 decision.
- Record G3 acceptance after the user's decision.
- Use only the statuses defined in `SatisfactorySkillPlan.md`.
- Increment the attempt number for every Claude-to-Codex review cycle.
- Record exact commands and results; do not write only tests passed.
- Record pre-existing dirty files so unrelated work is not attributed to the package.
- Do not rewrite accepted or superseded entries except to correct factual logging errors.

### Required work-package entry

Use the heading `YYYY-MM-DD - SSP-P<phase>-W<sequence> - <title>`, followed by:

- Roadmap phase, owner, status, attempt, baseline revision, pre-existing changes, and plan references.
- `Implementation packet (Codex)`: objective, scope, exclusions, expected files, acceptance criteria, verification, risks, and assumptions.
- `Implementation result (Claude)`: summary, changed files, tests, exact commands/results, deviations, decisions, and known limitations.
- `Quality control (Codex)`: diff reviewed, acceptance evidence, independent commands/results, findings, and residual risk.
- `Gate decision`: decision, next owner, next action, and user acceptance.

## Active work-package handovers

Replace the placeholder below with the newest work-package entry. Keep completed entries below active ones in newest-first order.

Governance note 2026-07-01: the user delegated G3 acceptance and pipeline
flow control for the remaining roadmap ("no need to loop me in, just keep
going until all is done"). From SSP-P2-W01 onward, acceptances are
recorded as `ACCEPTED (delegated)` with Fable 5 QC evidence; material
product decisions and plan amendments continue to be logged with
rationale. Non-overlapping packets may run in parallel.

## 2026-07-09 - Maintenance - Two behavior-preserving performance fixes

Scope: performance-only, no behavior change; audit finding #11.

- `satisfactory_workspace.py` `summary()` opened the SQLite store roughly ten
  times per call (once per section read plus once per kind for `counts`), and
  every open re-ran the legacy JSONL import hash check. It now opens the store
  once and reuses it for all reads including `counts`, closing it in a
  `finally`. Added `_read_open(store, kind)` (reads a kind from an already-open
  store); `_read` and the new `_summary_from` are both built on it, so
  `_open_store`'s "callers own and must close the store" contract and public
  `_read` behavior are unchanged.
- `satisfactory_mirror.py` `store_mirror_artifacts()` appended the new
  observation and then always read back and rewrote the whole
  `observations.jsonl` through a deque cap. It now rewrites only when the
  appended history exceeds the cap (`max(50, window_saves * 4)`); at or under
  the cap the append is the only write. Health is still computed from the same
  capped window, so the returned dict is unchanged.
- Tests: added `test_store_mirror_leaves_file_untouched_under_cap` and
  `test_store_mirror_caps_file_over_limit` in `tests/test_mirror.py` to pin the
  new no-rewrite-under-cap and cap-over-limit contract. Full suite:
  `python -m pytest tests/ -q` -> 449 passed, 1 skipped.

## 2026-07-01 - SSP-P2-W01 - Per-save SQLite store foundation

- Roadmap phase: Phase 2 - Typed master-plan store (first packet)
- Owner: complete
- Status: `ACCEPTED` (delegated)
- Attempt: 1
- Dispatched: 2026-07-01, agent `p2w01-impl`, in parallel with
  SSP-P1-W04 (zero file overlap: this packet creates only new files and
  touches nothing W04 touches)
- Baseline revision: `15d0e64`, dirty working tree; SSP-P1-W01..W03
  `ACCEPTED`, SSP-P1-W04 in progress
- Plan references: `SatisfactorySkillPlan.md` sections 9 (persistence),
  12 (Phase 2), 16 (guardrails: do not delete or rewrite legacy files
  during migration)
- Retires: deferred finding F-W03-3 (non-atomic JSONL rewrites) once the
  workspace adapter swap lands in SSP-P2-W02

### Implementation packet (Fable 5)

Objective:

- Create the per-save SQLite persistence foundation: schema v1 with a
  migration scaffold, transactional journal-record CRUD mirroring the
  current workspace semantics, and idempotent JSONL import that leaves
  legacy files untouched. The adapter swap (SaveWorkspace backed by this
  store) is the NEXT packet; this one is the pure store plus tests only.

In scope:

- New pure module
  `skills/satisfactory_assistant/satisfactory_store.py` (stdlib
  `sqlite3`, `json`, `hashlib`, `datetime`, `pathlib` only; no Wingman
  imports):
  - `STORE_SCHEMA_VERSION = 1` and DDL:
    - `meta(key TEXT PRIMARY KEY, value TEXT NOT NULL)` holding
      `schema_version`, `created_at`.
    - `records(id TEXT PRIMARY KEY, kind TEXT NOT NULL CHECK(kind IN
      ('notes','todos','goals','flows','changes')), title TEXT NOT
      NULL, details TEXT NOT NULL DEFAULT '', status TEXT NOT NULL,
      created_at TEXT NOT NULL, updated_at TEXT NOT NULL, extra TEXT
      NOT NULL DEFAULT '{}')` where `extra` is a JSON object carrying
      flow metadata (inputs, outputs, area, recipe, machines,
      constraints) and any unknown legacy fields (guardrail: preserve
      unknown fields as migration metadata).
    - `import_sources(source_path TEXT PRIMARY KEY, sha256 TEXT NOT
      NULL, imported_at TEXT NOT NULL, record_count INTEGER NOT NULL)`.
    - Indexes: `records(kind, status)` and `records(kind, created_at)`.
  - `class SaveStore` as a context manager over one SQLite file:
    - `SaveStore.open(db_path: Path) -> SaveStore`: creates parent dir,
      opens with `PRAGMA foreign_keys=ON`, creates schema when absent,
      reads `schema_version`, applies stepwise migrations from a
      `_MIGRATIONS: dict[int, str]` scaffold (empty beyond v1 today),
      and raises `StoreError` (new exception, subclass of
      RuntimeError) when the DB reports a NEWER version than supported
      (never downgrade silently).
    - `add_record(kind, record_id, title, details, status, now,
      extra: dict | None = None)` and `get_record(record_id)`,
      `set_status(kind, record_id, status, now) -> bool`,
      `update_flow(record_id, now, **fields) -> bool` mirroring the
      current workspace update semantics (None means leave unchanged,
      explicit clear list resets fields), and
      `list_records(kind, status: str | None = None, limit: int | None
      = None, newest_first: bool = True)`.
    - Every write runs inside a transaction (`with self._conn:`); a
      failure mid-batch rolls back completely.
    - Unknown `kind` raises `StoreError` before touching the DB.
  - `import_jsonl(store, sources: dict[str, Path]) -> dict[str, int]`:
    - `sources` maps kind to a legacy JSONL file path.
    - Per file: if absent, skip; compute SHA-256; if `import_sources`
      already has this path with the same hash, skip (idempotent);
      parse line-by-line with the same tolerance as the current
      workspace reader (invalid JSON lines and non-dict values are
      skipped); INSERT OR IGNORE by record id so re-imports and
      overlapping sources never overwrite store records; unknown keys
      in a legacy record go into `extra`; one transaction per file;
      record the source row on success.
    - NEVER writes to, moves, or deletes the source files (guardrail).
- New `tests/test_store.py`:
  - Schema: fresh open creates v1; reopening is stable; a DB with
    `schema_version` set to 99 raises `StoreError`.
  - CRUD: add/get round-trip including extra JSON; set_status on
    missing id returns False; unknown kind raises before any write;
    update_flow changes only given fields and honors explicit clears;
    list_records ordering, status filter, and limit.
  - Transactionality: a batch insert where the Nth record violates the
    kind CHECK leaves zero of the batch persisted.
  - Import: fixture JSONL files (valid, invalid-JSON line, non-dict
    line, duplicate id across two files); first import counts correct;
    second import is a no-op (counts zero, hashes matched); source file
    modified (new sha) imports only new ids; existing store records
    never overwritten; unknown legacy fields land in extra; source
    files byte-identical after import.
  - Cross-platform: paths via tmp_path only, no locale/encoding
    assumptions beyond UTF-8.

Explicitly out of scope:

- Swapping `SaveWorkspace`/`main.py` to use the store (SSP-P2-W02).
- Plan-model tables (master plans, stages, nodes, edges, solver runs:
  SSP-P2-W03 with `satisfactory_plan_models.py`).
- Markdown/JSON exports.
- Deleting or rewriting any legacy JSONL file.
- `release_version/` sync (still deferred), config or tool changes.

Expected files:

```text
skills/satisfactory_assistant/satisfactory_store.py  (new)
skills/satisfactory_assistant/tests/test_store.py    (new)
```

Data contracts and migration/configuration effects:

- New SQLite file `planning.sqlite3` will live in the per-save
  workspace directory once W02 wires it in; this packet only takes a
  `db_path`. No config or tool-schema changes.

Acceptance criteria:

1. Schema v1 creates cleanly, reopens stably, and a newer-version DB
   raises `StoreError` with a clear message.
2. All writes are transactional; the CHECK-violation batch test proves
   full rollback.
3. JSONL import is idempotent by content hash, tolerant of the same
   malformed shapes the current reader tolerates, preserves unknown
   fields in `extra`, never overwrites existing records, and leaves
   source files byte-identical.
4. Store API semantics (status updates, flow field updates with
   explicit clears, list ordering/filter/limit) match the current
   workspace behavior closely enough that W02 can swap backends without
   changing `SaveWorkspace`'s public API.
5. All pre-existing tests pass unchanged.
6. `python -m pytest`, `python -m ruff check`, `python -m compileall`
   clean; no bare `print(`; no em-dashes; ASCII only.

Required verification:

```text
python -m pytest skills/satisfactory_assistant/tests -q -p no:cacheprovider
python -m ruff check skills/satisfactory_assistant
python -m compileall -q skills/satisfactory_assistant
```

Cross-platform, token, persistence, and release-parity concerns:

- stdlib sqlite3 is bundled on all target platforms. Keep default
  journal mode (no WAL sidecar files in the workspace). No token
  impact. Release parity deferred as before.

Known risks, assumptions, and blocking questions:

- Assumption: single writer (one Wingman process per save); no
  cross-process locking beyond SQLite defaults. Documented in the
  module docstring.
- Risk: legacy records with missing timestamps; import must default
  them (empty string or the import time, documented choice) rather
  than fail.
- No blocking questions (G3 delegated per the governance note above).

### Implementation result (Sonnet 5 agent, 2026-07-01)

- New `satisfactory_store.py`: schema v1 DDL with kind CHECK and the two
  indexes; `StoreError`; `SaveStore` context manager with stepwise
  `_MIGRATIONS` scaffold and newer-version refusal; transactional
  `add_record`/`get_record`/`set_status`/`update_flow`/`list_records`
  mirroring `SaveWorkspace` semantics (unknown kind raises before any
  write; clear-fields applied last; extra JSON flattened back to
  top-level on read for W02 interchangeability); `import_jsonl` with
  SHA-256 idempotency, workspace-equal parse tolerance, INSERT OR
  IGNORE, unknown-legacy-fields-to-extra, missing timestamps defaulted
  to import time (documented), sources never written.
- New `tests/test_store.py`: 28 tests per the packet list, including a
  whitebox rollback proof.
- Deviations, both accepted at QC: `list_records` orders by
  `created_at` (matches the index; `SaveWorkspace.summary()` re-sorts
  by `updated_at` itself); transactionality proven whitebox since the
  public API is single-record.

### Quality control (Fable 5, 2026-07-01)

- Independent verification: store tests 28 passed; full suite 175
  passed, 1 pre-existing skip (147 + 28: SSP-P1-W04's tests not yet
  present, confirming zero overlap); ruff clean on both files;
  compileall clean.
- Full line-by-line review of `satisfactory_store.py`: DDL, migration
  scaffold, transaction boundaries (`with self._conn:` wrapping every
  write including update_flow's read-modify-write), import idempotency
  and source-file immutability all match the packet.
- Minor observation (not a finding): a DB with a meta table but no
  schema_version row defaults to the current version; acceptable
  corrupted-meta edge, revisit if migrations ever grow teeth.

### Gate decision

- Decision: `QC_PASSED`; `ACCEPTED` under delegated G3 (governance note
  above).
- Next action: SSP-P2-W02 (workspace backend swap) drafted below;
  dispatch waits for SSP-P1-W04 to land because both touch `main.py`.

## 2026-07-01 - SSP-P2-W03 - Typed plan models and plan tables

- Roadmap phase: Phase 2 - Typed master-plan store
- Owner: complete
- Status: `ACCEPTED` (delegated)
- Attempt: 2
- Dispatched: 2026-07-01, agent `p2w03-impl`
- Plan references: sections 7 (typed model), 8.4 (machines and
  diagnostics fields), 9 (persistence: immutable solver runs,
  recalculation creates a revision), 12 (Phase 2), 16 (guardrails: no
  graph relationships in display text only)

### Implementation packet (Fable 5)

Objective:

- Give the Phase 3 solver a typed output home: frozen plan-model
  dataclasses with JSON payload round-trip, and store schema v2 with
  master-plan/stage/solver-run persistence and revision semantics,
  exercising the real v1-to-v2 migration path.

In scope:

- New pure module `satisfactory_plan_models.py` (stdlib only), frozen
  dataclasses with explicit field types, each with `to_payload()` and
  a module-level `<name>_from_payload()` (payloads are plain JSON-able
  dicts; unknown payload keys are ignored on read, never fatal):
  - `Diagnostic(severity, code, message, subject)` with severity in
    {"info", "warning", "error"}.
  - `DataProvenance(source, retrieved, note)`.
  - `PacePolicy(multiplier, window_hours)`.
  - `RecipePolicy(mode, pinned, banned, allowed_alternates)` with mode
    in {"standard", "extended"}; tuples of normalized recipe keys.
  - `ProcessNode(node_id, recipe_class, building_class, runs_per_min,
    machine_count_exact, machine_count, clock, power_mw)`.
  - `ResourceSource(node_id, item_class, rate_per_min, extractor_class,
    extractor_count)`.
  - `ItemFlow(item_class, rate_per_min, source_id, dest_id)` where ids
    reference ProcessNode/ResourceSource node_ids or the sentinels
    "external_demand" / "raw_import".
  - `PowerPlan(total_mw, by_building)` with by_building a tuple of
    (building_class, mw) pairs.
  - `StagePlan(phase, window_hours, pace_multiplier, demands, nodes,
    sources, flows, power, recipe_policy, diagnostics, assumptions,
    provenance, solver_run_id, revision, created_at)` where demands is
    a tuple of (item_class, quantity, rate_per_min) triples and
    assumptions a tuple of strings.
  - `StageTransition(from_phase, to_phase, reused_nodes,
    expanded_nodes, added_nodes, retired_nodes)` (tuples of node ids;
    minimal now, Phase 4 grows it).
  - `FactoryMasterPlan(plan_id, name, created_at, updated_at)`.
  - Round-trip invariant: `x_from_payload(x.to_payload()) == x` for
    every model (dataclass equality; tuples not lists after read).
- `satisfactory_store.py`: bump `STORE_SCHEMA_VERSION` to 2 and
  register the 1-to-2 migration in `_MIGRATIONS` (this is the first
  real use of the scaffold; a v1 database must migrate in place and
  keep all journal records). New tables:
  - `master_plans(plan_id TEXT PRIMARY KEY, name TEXT NOT NULL,
    created_at TEXT NOT NULL, updated_at TEXT NOT NULL)`.
  - `stage_plans(stage_key TEXT PRIMARY KEY, plan_id TEXT NOT NULL
    REFERENCES master_plans(plan_id), phase INTEGER NOT NULL,
    revision INTEGER NOT NULL, created_at TEXT NOT NULL, payload TEXT
    NOT NULL, UNIQUE(plan_id, phase, revision))` with `stage_key` =
    `"{plan_id}:{phase}:{revision}"`.
  - `solver_runs(run_id TEXT PRIMARY KEY, plan_id TEXT NOT NULL,
    phase INTEGER NOT NULL, created_at TEXT NOT NULL, status TEXT NOT
    NULL, payload TEXT NOT NULL)`; rows are immutable: no update or
    delete method exists for them.
  - Index `stage_plans(plan_id, phase, revision)`.
  - New `SaveStore` methods, all transactional and StoreError-guarded:
    `upsert_master_plan(plan)`, `get_master_plan(plan_id)`,
    `save_stage_plan(plan_id, stage_payload, phase, now) -> int`
    (assigns revision = latest existing revision for that plan/phase
    plus one, starting at 1; never overwrites a prior revision),
    `load_stage_plan(plan_id, phase, revision=None)` (None = latest),
    `list_stage_revisions(plan_id, phase)`,
    `record_solver_run(run_id, plan_id, phase, status, payload, now)`
    and `get_solver_run(run_id)` (attempting to record an existing
    run_id raises StoreError: immutability is enforced, not assumed).
- New `tests/test_plan_models.py`: round-trip equality for every
  model; unknown payload keys ignored; tuple coercion verified;
  invalid severity/mode raise ValueError at construction.
- New tests in `tests/test_store.py`... NO: do not modify existing
  test files. New `tests/test_store_plans.py`: v1-to-v2 migration test
  (build a v1 DB by copying the v1 DDL from a fixture string or by
  monkeypatching STORE_SCHEMA_VERSION is NOT acceptable; instead
  create a v1 database with raw sqlite3 executing the documented v1
  DDL and meta rows, then open with SaveStore and assert journal
  records survive and version reads 2); revision sequencing (save
  twice -> revisions 1 and 2, latest loads by default, explicit
  revision loads exactly); solver-run immutability (duplicate run_id
  raises); foreign-key behavior (stage for unknown plan_id fails);
  payload round-trip through the store.

Explicitly out of scope:

- Markdown/JSON file exports (next packet, with reports).
- Any solver logic, tool changes, `main.py`, workspace changes.
- `release_version/` sync (still deferred).

Expected files:

```text
skills/satisfactory_assistant/satisfactory_plan_models.py  (new)
skills/satisfactory_assistant/satisfactory_store.py        (extend, v2)
skills/satisfactory_assistant/tests/test_plan_models.py    (new)
skills/satisfactory_assistant/tests/test_store_plans.py    (new)
```

Acceptance criteria:

1. Every model round-trips payload-to-object with dataclass equality;
   unknown keys tolerated; invalid enums rejected at construction.
2. A genuine v1 database (raw DDL, not monkeypatched) opens under the
   new code, migrates to v2 in place, and keeps all journal records.
3. Revisions are append-only and sequence correctly; solver runs are
   immutable by enforcement.
4. All pre-existing tests pass unchanged (200 + new).
5. pytest, ruff, compileall clean; no bare print; no suppression
   comments; ASCII; no em-dashes.

Known risks, assumptions:

- The v1 DDL string used by the migration test must match what W01
  actually shipped; copy it from `_SCHEMA_SQL` at the v1 revision (it
  is unchanged on disk today), not from memory.
- StagePlan payloads are canonical JSON in one column by design at
  this phase; relational node/edge tables can follow when Phase 4
  transition diffs need cross-stage queries. The graph is still typed
  data (guardrail satisfied), just serialized.

### Implementation result (Sonnet 5 agent, 2026-07-01, attempt 1)

- New `satisfactory_plan_models.py` (11 frozen models, payload
  round-trips, enum guards, flow sentinels) and store schema v2 with
  the first real `_MIGRATIONS[1]` entry (same SQL as the fresh-create
  plan tables, so migrated and fresh DBs are structurally identical);
  new transactional plan-persistence methods with append-only revisions
  and enforced solver-run immutability; 45 new tests including a
  genuine raw-DDL v1 database migration test.
- Flagged, not edited: `test_store.py` pins the schema version literal
  (`== 1`) in two tests, structurally incompatible with this packet's
  required bump to 2.
- Reported a "pre-existing flaky" `test_focus_filters_before_truncation`
  failure that passed on re-runs.

### Quality control (Fable 5, 2026-07-01, attempt 1)

- Independent verification: 239 passed, 2 failed (exactly the two
  schema-literal tests), 1 pre-existing skip; ruff and compileall
  clean.
- RULING on the schema literals: same category as the W02 ruling. The
  tests' intent is "fresh open creates the current schema version and
  reopening is stable"; the `1` literals encoded the then-current
  version. Authorized correction: in `tests/test_store.py` ONLY, change
  the two assertions to track `STORE_SCHEMA_VERSION` with a single
  explicit pin (`assert int(version) == STORE_SCHEMA_VERSION == 2` in
  the create test; `assert int(version) == STORE_SCHEMA_VERSION` in the
  reopen test) and rename `test_open_creates_schema_v1` to
  `test_open_creates_current_schema`. Nothing else in that file.
- FINDING F-P2W03-1 (Medium, latent W02 regression surfaced by the PK
  constraint): the "flaky" test is a real defect.
  `SaveWorkspace._new_id` appends only 4 hex chars (16 bits) to a
  per-second timestamp; rapid same-second inserts collide at birthday
  rates, and since W02 the record id is a SQLite PRIMARY KEY, so a
  collision now raises `sqlite3.IntegrityError` instead of silently
  appending a duplicate JSONL line. Required correction: widen the
  suffix to 8 hex chars AND add a bounded retry (max 5, fresh id per
  attempt) in `add_item` on duplicate-id IntegrityError, re-raising
  when exhausted; add a deterministic regression test that forces a
  first-attempt collision (monkeypatched uuid) and asserts distinct
  ids and success. Do not touch the flaky test itself; it becomes
  reliable once the defect is fixed.

### Gate decision (attempt 1)

- Decision: `CHANGES_REQUESTED` (authorized schema-literal correction;
  F-P2W03-1 fix).
- Next owner: Sonnet 5 agent `p2w03-impl`, attempt 2.

### Implementation result attempt 2 (Sonnet 5 agent, 2026-07-01)

- Authorized test edits applied exactly (two assertions, one rename in
  `tests/test_store.py`).
- F-P2W03-1 fixed: `_new_id` suffix widened to 8 hex chars;
  `add_item` retries on duplicate-id `sqlite3.IntegrityError` up to
  `_MAX_ID_ATTEMPTS = 5` with fresh ids, re-raising on exhaustion;
  deterministic forced-collision regression test added via a
  monkeypatched uuid source.

### Quality control attempt 2 (Fable 5, 2026-07-01)

- Independent verification: 242 passed, 1 pre-existing skip; ruff and
  compileall clean; retry loop and 8-hex suffix confirmed on disk;
  formerly flaky `test_focus_filters_before_truncation` passed 5/5 in
  my own isolated loop (agent reported 10/10).

### Gate decision (attempt 2)

- Decision: `QC_PASSED`; `ACCEPTED` under delegated G3.
- Next action: SSP-P2-W04 (plan exports), the final Phase 2 packet,
  drafted and dispatched below.

## 2026-07-01 - SSP-P2-W04 - Plan artifact exports

- Roadmap phase: Phase 2 - Typed master-plan store (final packet)
- Owner: complete
- Status: `ACCEPTED` (delegated)
- Attempt: 1
- Dispatched: 2026-07-01, agent `p2w04-impl`
- Milestone: roadmap Phase 2 is COMPLETE (W01 store, W02 backend swap,
  W03 typed models and plan tables, W04 exports all `ACCEPTED`)
- Plan references: sections 12 (Phase 2 acceptance: "Markdown and JSON
  exports"), 5.1 (`satisfactory_reports.py`), 16 (guardrails)

### Implementation packet (Fable 5)

Objective:

- Pure report generation for persisted plans: deterministic Markdown
  and JSON artifacts for a `StagePlan`, written inside the per-save
  workspace, ready for the Phase 3 calculator to reference by path.

In scope:

- New pure module `satisfactory_reports.py` (stdlib plus
  `satisfactory_plan_models` imports only):
  - `stage_plan_to_json(stage: StagePlan) -> str`: pretty (2-space)
    canonical JSON of `stage.to_payload()` with sorted keys; parsing it
    back and running `stage_plan_from_payload` must reproduce an equal
    `StagePlan`.
  - `stage_plan_to_markdown(stage: StagePlan) -> str`: deterministic
    ASCII Markdown, no em-dashes, sections in fixed order: title line
    (phase, revision), summary (window hours, pace, solver run id,
    created at), Demands table (item, quantity, rate/min), Production
    table (node id, recipe, building, machines exact and integer,
    clock, power MW), Resource sources table, Flows summary (grouped:
    external demand satisfied, raw imports, internal edge count),
    Power (total MW, top building classes), Diagnostics (bulleted,
    severity-prefixed, "none" line when empty), Assumptions, Provenance
    footer. Numeric formatting: rates and MW to 3 decimals, clocks to
    4; no trailing whitespace on any line.
  - `master_plan_summary_markdown(plan: FactoryMasterPlan, stages:
    tuple[StagePlan, ...]) -> str`: one table row per stage (phase,
    revision, window, machines total, power total, diagnostics count).
  - `export_stage_artifacts(workspace_dir: Path, plan_id: str, stage:
    StagePlan) -> dict[str, str]`: writes
    `plans/<slug(plan_id)>/phase<phase>_rev<revision>.md` and `.json`
    under `workspace_dir`, creating directories; returns the two paths
    as strings. Reuse the existing slugify from
    `satisfactory_workspace` if importable without a cycle; otherwise
    implement a local `_slug` with identical behavior and a why-comment.
    Containment: resolve and verify both written paths stay under
    `workspace_dir` (resolved-parent check) before writing; raise
    ValueError otherwise. Writes are plain (artifacts are derived,
    regenerable data; atomicity not required, matching the mirror
    artifact precedent).
- New `tests/test_reports.py`:
  - Build a small fully-populated `StagePlan` fixture (2 demands, 2
    nodes, 1 source, 3 flows incl. sentinels, power, 1 warning
    diagnostic, 1 assumption, provenance).
  - JSON round-trip equality via `stage_plan_from_payload`.
  - Markdown determinism (two calls identical), section order, key
    content lines present, ASCII-only, no em-dash characters, no
    trailing whitespace.
  - Empty-collections stage renders with "none" lines, no crash.
  - Export writes both files inside the workspace; hostile plan_id
    (traversal attempt) is slugified and contained or rejected;
    returned paths exist and parse/read back correctly.
  - Master summary renders one row per stage.

Explicitly out of scope:

- Any solver logic, tool changes, `main.py`, store changes.
- HUD delivery of artifacts (future Phase 9 map/HUD work).
- `release_version/` sync (still deferred).

Expected files:

```text
skills/satisfactory_assistant/satisfactory_reports.py  (new)
skills/satisfactory_assistant/tests/test_reports.py    (new)
```

Acceptance criteria:

1. JSON artifact round-trips to an equal `StagePlan`.
2. Markdown is deterministic, ASCII, em-dash-free, fixed section
   order, correct numeric formatting.
3. Exports are contained in the workspace; hostile plan ids cannot
   escape; empty plans render gracefully.
4. All pre-existing tests pass unchanged (242 + new).
5. pytest, ruff, compileall clean; no bare print; no suppression
   comments.

### Implementation result (Sonnet 5 agent, 2026-07-01)

- New `satisfactory_reports.py` (deterministic Markdown and canonical
  JSON stage exports, master-plan summary, contained
  `export_stage_artifacts` with slugified plan ids and resolved-parent
  checks before any write) and `tests/test_reports.py` (16 tests).
- Judgment calls flagged and accepted: return-dict keys
  (`markdown_path`/`json_path`), top-5 building power listing,
  "(none)" fallbacks (which also guarantee no trailing whitespace).

### Quality control (Fable 5, 2026-07-01)

- Independent verification: 258 passed, 1 pre-existing skip; ruff and
  compileall clean; scripted ASCII/em-dash byte check on the module
  passed; containment path reviewed line-by-line (resolve before
  verify before write, both artifacts checked, Windows-aware
  fallback consistent with the workspace idiom).

### Gate decision

- Decision: `QC_PASSED`; `ACCEPTED` under delegated G3. Phase 2
  complete.
- Next action: SSP-P3-W01 (solver core), drafted and dispatched below.

## 2026-07-01 - SSP-P3-W01 - Solver core: gated graph and LP balance

- Roadmap phase: Phase 3 - Phase 1 deterministic planner (first packet)
- Owner: complete
- Status: `ACCEPTED` (delegated)
- Attempt: 1
- Dispatched: 2026-07-01, agent `p3w01-impl`; accepted 2026-07-02
- Plan references: sections 8.1 (pipeline steps 4 and 6-9), 8.2
  (balance model), 8.3 (uniform weights, stable tie-breaks), 12
  (Phase 3), 16 (guardrails); grounding facts in the root
  `claudesatisfactoryreview.md` section 5 (scipy 1.17.0 and numpy 2.3
  already in requirements.txt; `scipy.optimize.linprog(method="highs")`
  verified importable)

### Implementation packet (Fable 5)

Objective:

- The solver heart: given a Docs catalog, a capability snapshot, and a
  demand set, build the reachable gated candidate graph and solve the
  material balance LP, returning recipe run rates and raw-resource
  imports with actionable diagnostics. Machines/clocks/power are the
  NEXT packet; this one ends at runs-per-minute.

In scope:

- `satisfactory_docs.py` (approved extension): mark raw resources and
  automatable recipes as data:
  - `ItemDescriptor` gains `is_resource: bool = False`; the loader sets
    it True for rows parsed from the `FGResourceDescriptor` group.
  - `DocsCatalog.raw_resource_classes() -> frozenset[str]` (normalized
    keys of resource items).
  - `DocsCatalog.automatable_recipes() -> tuple[Recipe, ...]`: recipes
    whose `produced_in` resolves to at least one catalog building whose
    normalized key starts with `build_` and does not contain
    `workbench` or `workshop` (build-gun/manual crafting excluded).
    Computed once in the constructor, stable class-name ordering.
- New pure module `satisfactory_solver.py` (imports:
  `satisfactory_docs`, `satisfactory_progression` types, numpy, and
  `scipy.optimize.linprog` with `method="highs"`):
  - Frozen dataclasses: `RecipeRun(recipe_class, display_name,
    runs_per_min, building_class)`, `RawImport(item_class,
    display_name, rate_per_min)`, `SolveResult(status, runs, imports,
    satisfied_demands, diagnostics)` with status in
    {"optimal", "infeasible", "no_candidates"} and diagnostics a tuple
    of strings.
  - `solve_stage(catalog, allowed_recipes: frozenset[str], demands:
    tuple[tuple[str, float], ...]) -> SolveResult` where demands pairs
    are (item_class normalized, required rate/min):
    1. Candidate set: automatable recipes whose normalized key is in
       `allowed_recipes`.
    2. Reachability pre-check: walk backward from demand items through
       candidate recipes; any required item with no candidate producer
       and not in `raw_resource_classes()` produces an "unproducible"
       diagnostic naming the item and the closed-gate/no-recipe cause;
       if any demand item itself is unproducible, return "infeasible"
       without calling the LP.
    3. Variables: one runs-per-min per candidate recipe reachable from
       the demands, plus one import variable per raw resource that
       appears in the reachable graph. Deterministic variable ordering
       by normalized class key.
    4. Constraints, per item touched by the graph: production minus
       consumption plus raw import (raw items only) >= demand (0 for
       intermediates). Per-recipe item rates: `amount / duration * 60`
       with fluid amounts already normalized by the catalog helpers;
       building manufacturing_speed applied (clock is 1.0 in this
       packet).
    5. Objective: minimize sum of raw imports (uniform weights, plan
       8.3) plus `1e-6 *` sum of recipe runs as a stability term so
       zero-cost cycles cannot float and solutions are reproducible;
       document the epsilon.
    6. `linprog(method="highs")`; on infeasible LP, emit diagnostics
       listing the demand items and the raw resources involved;
       never invent data.
    7. Post-process: clamp values below 1e-6 to zero, build tuples
       sorted by class key, verify residuals (production plus imports
       minus consumption minus demand >= -1e-5 per item) and add an
       "internal residual" error diagnostic if violated.
  - Determinism: same inputs produce byte-identical results (test by
    running twice and comparing dataclasses).
- New `tests/test_solver.py`, fixture catalog in the established
  tiny-Docs-JSON style:
  - Linear chain (ore -> ingot -> plate): exact expected runs and ore
    import for a given plate demand (hand-computed values asserted).
  - Shared intermediate consumed by two demand items.
  - Byproduct: a recipe with two outputs where the secondary output
    partially satisfies another demand (surplus allowed).
  - Alternate recipe present but NOT in allowed_recipes: unused; when
    added to allowed_recipes and strictly better on raw usage, the
    solver picks it (raw import drops).
  - Infeasible: demand item whose only recipe is not allowed ->
    "infeasible", diagnostic names the item; empty allowed set ->
    "no_candidates".
  - Zero-demand returns optimal with empty runs.
  - Determinism double-run equality.
  - Gated real-install test (skip without Docs): build the real
    catalog, snapshot for upcoming phase 1 via
    `satisfactory_progression` (tiers 0-2), demand Smart Plating at
    50/60 per min; assert status optimal, a Smart Plating recipe run
    exists, every import is a true raw resource, and no recipe outside
    the snapshot's allowed set is used.

Explicitly out of scope:

- Machine counts, integer schedules, clocks, power (SSP-P3-W02).
- Extractor/miner modeling, belts, reservations (Phase 5).
- Tool changes, persistence wiring, reports wiring (SSP-P3-W03).
- Recipe pinning/banning beyond the allowed-set mechanism.
- `release_version/` sync (still deferred).

Expected files:

```text
skills/satisfactory_assistant/satisfactory_docs.py    (extend)
skills/satisfactory_assistant/satisfactory_solver.py  (new)
skills/satisfactory_assistant/tests/test_solver.py    (new)
```

Acceptance criteria:

1. Fixture chain solves to hand-computed exact values; residual checks
   hold; determinism double-run passes.
2. Gating is honored: disallowed recipes never appear in results;
   infeasibility names the blocking item; no silent alternates.
3. Real-install Phase 1 Smart Plating solve is optimal with only raw
   imports and allowed recipes.
4. All 258 pre-existing tests pass unchanged (the `ItemDescriptor`
   field addition must be backward-compatible: keyword default).
5. pytest, ruff, compileall clean; no bare print; no suppression
   comments; scipy imported lazily inside solve_stage so module import
   works without scipy (diagnostic error return if scipy is missing,
   never a crash at import time).

### Implementation result (Sonnet 5 agent, 2026-07-02)

- Docs extension exactly per packet (`is_resource` flag,
  `raw_resource_classes()`, `automatable_recipes()` computed once).
- New `satisfactory_solver.py`: reachability pre-check, deterministic
  variable ordering, uniform raw-import objective with documented
  stability epsilon, lazy scipy (cheap paths work without it, missing
  scipy degrades to a diagnostic), residual verification, clamping.
- New `tests/test_solver.py` (11 tests, all hand-computable fixture
  math plus a real-install Phase 1 Smart Plating solve:
  Desc_OreIron 19.375/min single import, zero diagnostics).
- Accepted deviation: no `satisfactory_progression` import in the
  solver module (signature needs only stdlib types; the import lives
  in the test where it is used).
- FINDING raised by the agent, upheld at QC (F-P3W01-1, see below).

### Quality control (Fable 5, 2026-07-02)

- Independent verification: 269 passed, 1 pre-existing skip; all 11
  solver tests pass individually including the real-install solve;
  ruff and compileall clean; LP construction reviewed line-by-line
  (objective, negated >= encoding, default nonnegative bounds, lazy
  import placement, residual check reuse of precomputed rates).
- Semantics note recorded for the next packet: given the coefficient
  definition (item rate per machine at 100 percent clock), the solved
  variable is machine-equivalents at 100 percent clock;
  `RecipeRun.runs_per_min` is therefore a misnomer to reconcile when
  machines land (the value IS `machine_count_exact`).
- F-P3W01-1 (Medium, planned-follow-up now load-bearing): capability
  snapshots include only EST_Milestone unlocks (documented limitation
  accepted in SSP-P1-W03), but real chains need EST_Custom starting
  recipes (Iron Rod via Schematic_StartingRecipes_C), EST_Tutorial
  unlocks (Reinforced Iron Plate via Schematic_Tutorial2_C), and base
  recipes with no unlocking schematic at all (Iron Screw). Every real
  capability-gated solve is infeasible without manual
  `extra_schematics` workarounds. Fix packeted as SSP-P3-W02 below.

### Gate decision

- Decision: `QC_PASSED`; `ACCEPTED` under delegated G3. The
  real-install test's `extra_schematics` workaround is accepted
  temporarily and removed by SSP-P3-W02.

## 2026-07-02 - SSP-P3-W02 - Capability snapshot completeness

- Roadmap phase: Phase 3 - Phase 1 deterministic planner
- Owner: complete
- Status: `ACCEPTED` (delegated)
- Attempt: 1
- Dispatched: 2026-07-02, agent `p3w02-impl`
- Plan references: sections 2.4 (stage rules), 6.2 (capability
  snapshots), 12 (Phase 3); resolves F-P3W01-1

### Implementation packet (Fable 5)

Objective:

- Make `build_capability_snapshot` complete enough that a plain
  phase-gated snapshot yields feasible real solves: include tutorial,
  starting-recipe, and base-recipe unlocks that every player has,
  while keeping alternates strictly opt-in and MAM/HardDrive research
  excluded by default.

In scope:

- `satisfactory_progression.py`, `build_capability_snapshot` only
  (signature unchanged):
  - Purchased schematics now include EST_Milestone, EST_Tutorial, and
    EST_Custom schematics whose `tech_tier` is within the available
    tiers (plus `extra_schematics` as before).
  - Allowed recipes additionally include every catalog automatable
    recipe with zero unlocking schematics
    (`recipe_unlocked_by(...) == ()`) that is not an alternate
    (`is_alternate_recipe` False): base recipes are always craftable.
  - EST_MAM and EST_HardDrive remain excluded by default; alternates
    remain opt-in via `include_alternates` (unchanged paths).
  - Update the docstring's scope note accordingly.
- `tests/test_progression.py`: append new tests only (existing tests
  untouched): in-tier EST_Tutorial and EST_Custom schematics included;
  above-tier EST_Custom excluded; base recipe (no unlocking schematic,
  not alternate) allowed; `recipe_alternate_`-prefixed recipe with no
  unlocking schematic still excluded; EST_MAM within tier still
  excluded.
- `tests/test_solver.py` (authorized modification of exactly one
  existing test, ruling logged here): remove the `extra_schematics`
  workaround from `test_real_install_phase1_smart_plating_solve`; the
  plain upcoming-phase-1 snapshot must now solve optimal with the same
  assertions.

Explicitly out of scope: everything else (machines/power is the next
packet; no docs, solver, store, tool, or release changes).

Expected files:

```text
skills/satisfactory_assistant/satisfactory_progression.py  (one function)
skills/satisfactory_assistant/tests/test_progression.py    (additions only)
skills/satisfactory_assistant/tests/test_solver.py         (one authorized edit)
```

Acceptance criteria:

1. Real-install Phase 1 Smart Plating solve is optimal with a plain
   snapshot (no extra_schematics).
2. Alternates and MAM/HardDrive research remain excluded by default;
   the new fixture tests prove each inclusion/exclusion rule.
3. All pre-existing tests pass unchanged (269 + new, minus nothing).
4. pytest, ruff, compileall clean; usual style rules.

### Implementation result (Sonnet 5 agent, 2026-07-02)

- Delivered without a completion report (agent idled); QC reconstructed
  from the repository. Implementation matches the packet exactly:
  EST_Tutorial and EST_Custom schematics counted within available
  tiers; base recipes (automatable, zero unlocking schematics, not
  alternate) always allowed; MAM/HardDrive still excluded; five new
  fixture tests; the authorized removal of the real-install test's
  `extra_schematics` workaround applied.

### Quality control (Fable 5, 2026-07-02)

- Independent verification: 274 passed, 1 pre-existing skip; ruff and
  compileall clean; the reworked function reviewed line-by-line; the
  real-install Phase 1 Smart Plating solve passes with a PLAIN
  upcoming-phase-1 snapshot (F-P3W01-1 resolved); `extra_schematics`
  occurrences in `test_solver.py`: zero.

### Gate decision

- Decision: `QC_PASSED`; `ACCEPTED` under delegated G3.
- Next action: SSP-P3-W03 (machines, clocks, power), dispatched below.

## 2026-07-02 - SSP-P3-W03 - Machine schedules, clocks, and power

- Roadmap phase: Phase 3 - Phase 1 deterministic planner
- Owner: complete
- Status: `ACCEPTED` (delegated)
- Attempt: 1
- Dispatched: 2026-07-02, agent `p3w03-impl`
- Plan references: sections 8.1 (steps 10-12), 8.4 (machines and
  diagnostics), 12 (Phase 3); reconciles the `runs_per_min` semantics
  note recorded in SSP-P3-W01 QC

### Implementation packet (Fable 5)

Objective:

- Turn solved machine-equivalents into an actionable integer machine
  schedule with group underclocking and a power budget, emitting the
  typed `ProcessNode` and `PowerPlan` models the store and reports
  already understand.

In scope:

- `satisfactory_docs.py` (approved extension): `Building` gains
  `power_consumption_exponent: float = 1.6` (keyword default, the
  game's standard overclock exponent), parsed from
  `mPowerConsumptionExponent` in the FGBuildable branch via the
  existing `_float` helper with 1.6 as fallback.
- `satisfactory_solver.py`:
  - Honesty rename (authorized API change, this module and its tests
    only): `RecipeRun.runs_per_min` becomes `machines_exact`; the
    docstring states it is machine-equivalents at 100 percent clock.
  - New frozen dataclass is NOT needed: reuse
    `satisfactory_plan_models.ProcessNode` and `PowerPlan`.
  - New `schedule_machines(catalog, result: SolveResult) ->
    tuple[tuple[ProcessNode, ...], PowerPlan, tuple[str, ...]]`
    (nodes, power, diagnostics):
    - Per RecipeRun: `machine_count = ceil(machines_exact)` (with a
      1e-9 nudge so 3.0000000001 does not become 4);
      `clock = machines_exact / machine_count` (group underclock,
      total throughput preserved exactly); clock floor 0.01 (game
      minimum): if the implied clock falls below it, reduce
      machine_count until clock >= 0.01 or machine_count == 1.
    - `runs_per_min` on the node = true recipe executions per minute
      = machines_exact * (60 / duration_seconds) * manufacturing_speed.
    - `power_mw = machine_count * building.power_consumption *
      clock ** building.power_consumption_exponent`, rounded to 3
      decimals; buildings with zero/unknown power contribute 0 and add
      one diagnostic naming the building.
    - `node_id` = `"node_" + normalized recipe key` (deterministic).
    - PowerPlan: total (3 decimals) plus by_building aggregation
      sorted by MW descending then class name.
  - Raw imports are untouched by scheduling (extractors are Phase 5).
- `tests/test_solver.py` (authorized edits: the rename's mechanical
  fallout on existing assertions, plus new tests appended):
  - Fractional case: machines_exact 2.5 -> 3 machines at clock
    0.833333..., power = 3 * base * clock^exponent (hand-computed
    against a fixture exponent of 1.6 and a non-1.6 fixture value to
    prove parsing).
  - Exact-integer case: clock 1.0, power = count * base.
  - Zero-power building yields the diagnostic.
  - PowerPlan aggregation across two building classes.
  - Real-install extension: schedule the Phase 1 solve; assert every
    node has integer machine_count >= 1, clock in (0, 1], node
    runs_per_min consistent with machines_exact within 1e-6, total
    power > 0; build a StagePlan from the nodes and PowerPlan and
    assert it round-trips through `stage_plan_from_payload`.

Explicitly out of scope: extractor/miner scheduling, belt checks,
overclocking above 1.0, shards, tool changes, persistence wiring,
`release_version/`.

Expected files:

```text
skills/satisfactory_assistant/satisfactory_docs.py    (one field + parse)
skills/satisfactory_assistant/satisfactory_solver.py  (rename + schedule_machines)
skills/satisfactory_assistant/tests/test_solver.py    (authorized rename fallout + new tests)
```

Acceptance criteria:

1. Hand-computed fractional and integer schedules match exactly,
   including the non-default exponent case.
2. Clock floor honored; throughput preserved (runs_per_min consistency
   assertion).
3. Real-install Phase 1 schedule is integral, clocked in (0, 1], has
   positive total power, and its StagePlan round-trips.
4. All pre-existing tests pass (mechanical rename fallout in
   test_solver.py only; every other test file byte-untouched).
5. pytest, ruff, compileall clean; usual style rules.

### Implementation result (Sonnet 5 agent, 2026-07-02)

- Docs `power_consumption_exponent` field parsed with 1.6 fallback;
  solver rename to `machines_exact` completed; `schedule_machines`
  emits `ProcessNode`/`PowerPlan` with ceil-plus-nudge integer counts,
  exact group underclock, clock floor loop, per-building exponent
  power, dedup-sorted zero-power diagnostics, and a mismatched-catalog
  ValueError guard. Five new tests including the real-install schedule
  (7 nodes, 7 machines, 16.662 MW, zero diagnostics) and a StagePlan
  round-trip. Judgment call accepted: aggregate power sums raw values
  and rounds once (avoids compounded rounding).

### Quality control (Fable 5, 2026-07-02)

- Independent verification: 279 passed, 1 pre-existing skip; ruff and
  compileall clean; rename confirmed on disk.
- Power math independently recomputed: the real-install per-node
  values match hand calculation with the REAL parsed exponent
  (4 x 0.6458^1.3219 = 2.244 MW smelter; constructor and assembler
  nodes likewise), proving the Docs exponent (1.3219) is used rather
  than the 1.6 default. Throughput-preservation assertion reviewed.

### Gate decision

- Decision: `QC_PASSED`; `ACCEPTED` under delegated G3.
- Next action: SSP-P3-W04, the calculator tool packet (first-usable-
  planner milestone), dispatched below.

## 2026-07-02 - SSP-P3-W04 - calculate_satisfactory_plan tool and audit fold-in

- Roadmap phase: Phase 3 - Phase 1 deterministic planner (final packet)
- Owner: complete
- Status: `ACCEPTED` (delegated)
- Attempt: 1
- Dispatched: 2026-07-02, agent `p3w04-impl`
- MILESTONE: the plan section 15 "first usable planner" definition of
  done is MET: a player can request a Project Assembly phase plan at a
  chosen pace and receive a reproducible, capability-gated, balanced,
  machine-scheduled, power-budgeted, persisted, bounded response with
  exported artifacts
- Plan references: sections 10 (tool surface and response limits), 8.1
  (pipeline), 12 (Phase 3), 15 (definition of done: first usable
  planner); implements the user's 2026-07-01 F-P8W01-2 decision (fold
  the audit tool into the calculator, restoring the 3-tool cap)

### Implementation packet (Fable 5)

Objective:

- Wire the accepted pipeline end to end behind one AI-callable tool:
  `calculate_satisfactory_plan` computes a stage plan for the active
  save (demand -> gates -> solve -> schedule -> persist -> export) and
  absorbs the factory-mirror audit as its `mode="audit"`, retiring the
  standalone `audit_satisfactory_factory` tool. Exactly three tools
  remain.

In scope:

- `satisfactory_reports.py` (extend): `format_plan_response(stage:
  StagePlan, artifact_paths: dict[str, str] | None,
  char_budget: int = 3200) -> str`: compact, deterministic, ASCII
  plan summary for the
  tool return: header (phase, window, pace, revision), demand lines,
  top production nodes (recipe, machines, clock, power; cap 10 with
  "+N more"), raw imports, total power, diagnostics (cap 5), artifact
  path line when given; hard character budget enforced by truncating
  node/demand lists first, never mid-line; always under `char_budget`.
- `main.py`:
  - Remove the `audit_satisfactory_factory` @tool method; move its
    body into a private `_run_factory_audit(result, ws) -> str` helper
    (same behavior, same messages, same artifacts).
  - New tool `calculate_satisfactory_plan` with typed params:
    `phase: int`, `pace_multiplier: float = 1.0`,
    `include_alternates: str = ""` (semicolon-separated recipe names),
    `persist: bool = True`, `mode: Literal["plan", "audit"] = "plan"`.
    Description covers both modes concisely (plan a Project Assembly
    stage; audit the current factory from the save). `wait_response=True`.
  - `mode="audit"`: resolve active save, run `_run_factory_audit`
    (docs/parser flow unchanged).
  - `mode="plan"` behavior, all just-in-time and OSError-guarded:
    1. Resolve active save (standard refusal messages).
    2. `discover_docs` + memoized `get_docs_catalog`; missing docs ->
       existing hint message with searched list.
    3. `load_project_assembly_phases()`; `validate_phases_against_docs`
       diagnostics folded into the response, not fatal unless a
       demanded part is missing.
    4. `derive_phase_demand(data, phase, pace_multiplier)`;
       `ValueError` (bad phase/pace) returned as the message verbatim.
    5. `build_capability_snapshot(catalog, data, phase,
       include_alternates=parsed tuple)`.
    6. `solve_stage`; non-optimal -> compact diagnostic response
       (status plus diagnostics, bounded), nothing persisted.
    7. `schedule_machines`; build the `StagePlan` (demands from the
       demand set, nodes, sources from imports as `ResourceSource`
       with extractor fields empty, flows: external demand and raw
       import edges only this packet, power, recipe policy standard
       plus listed alternates, diagnostics, assumptions: "clock 1.0
       baseline, extractors not modeled", provenance from
       DatasetInfo + bundled data provenance, created_at now).
    8. When `persist`: workspace store `upsert_master_plan` (plan_id
       "master", name = save name), `save_stage_plan` (gets revision),
       `record_solver_run` (run_id `run_<phase>_<revision>_<utcstamp>`,
       status optimal), `export_stage_artifacts`; response includes
       revision and artifact path. When not persisting, response says
       "not persisted".
    9. Return `format_plan_response(...)` (<= 3200 chars).
  - `validate()` unchanged (no new config); tool count in the module
    is exactly 3 after this change.
- Tests, new file `tests/test_plan_tool.py` following the
  `_PlanAssistantStub` adapter-test pattern from
  `test_config_coercion.py` (read it first; stub config/settings/
  wingman, monkeypatch module-level functions in `main` for the heavy
  pieces where needed):
  - Bad pace (0.5, 3.5) and bad phase (0, 6) return the ValueError
    message and persist nothing.
  - No active save -> standard refusal; docs missing -> hint message
    (monkeypatch discover_docs to return a none-result).
  - Happy path with the solver fixture catalog monkeypatched in:
    response contains phase header, demand line, node line, power
    total; length <= 3200; persist=True writes a stage revision
    (verify via SaveStore) and artifact files inside the workspace;
    persist=False leaves the store empty.
  - Second identical call persists revision 2 (append-only proven at
    the tool level).
  - mode="audit" dispatches to the audit helper (monkeypatch the
    helper, assert called and its string returned).
  - Tool count: introspect the class, exactly 3 @tool methods.
- `tests/test_mirror.py` and others: byte-untouched. If any existing
  test imports or calls `audit_satisfactory_factory` directly, STOP
  and report per the standing rule instead of editing it.

Explicitly out of scope:

- Context-tool enrichment and lookup exposure (SSP-P3-W05 candidate).
- Extractor/miner nodes, belts, pins/bans beyond include_alternates.
- Prompt/discovery-keyword updates in `default_config.yaml` (next
  packet, alongside context enrichment, to keep this one reviewable).
- `release_version/` sync (a dedicated release packet follows Phase 3).

Expected files:

```text
skills/satisfactory_assistant/satisfactory_reports.py  (extend)
skills/satisfactory_assistant/main.py                  (tool swap)
skills/satisfactory_assistant/tests/test_plan_tool.py  (new)
```

Acceptance criteria:

1. Exactly three @tool methods remain; the audit path is reachable via
   `calculate_satisfactory_plan(mode="audit")` and behaviorally
   unchanged.
2. Plan responses are deterministic, bounded (<= 3200 chars), and
   contain demands, nodes, imports, power, diagnostics, revision, and
   artifact path.
3. Persistence is append-only at the tool level (revision 2 on second
   call); persist=False leaves no store rows or artifacts.
4. Validation failures (pace, phase, no save, no docs) return
   actionable messages and never partially persist.
5. All pre-existing tests pass byte-unchanged; pytest, ruff,
   compileall clean; usual style rules; no new config properties.

### Implementation result (Sonnet 5 agent, 2026-07-02)

- `format_plan_response` with hard 3200-char budget and whole-line
  progressive truncation; `calculate_satisfactory_plan` implementing
  the nine-step plan pipeline plus `mode="audit"` via the preserved
  `_run_factory_audit` helper; standalone audit tool removed; exactly
  three @tool methods verified by decorator-attribute introspection;
  12 new adapter tests via the established stub pattern including
  append-only revisioning at the tool level and persist=False purity.
- Good practice noted: used timezone-aware utcnow replacement; fatal
  vs non-fatal Docs-validation diagnostics split by requested phase.

### Quality control (Fable 5, 2026-07-02)

- Independent verification: 291 passed, 1 pre-existing skip; ruff and
  compileall clean.
- Independent END-TO-END smoke against the real install, composing
  exactly what the tool composes (discovery -> memoized catalog ->
  bundled phases -> validation (0 diagnostics) -> phase 1 demand ->
  plain snapshot -> solve (optimal) -> schedule (7 nodes, 16.662 MW)
  -> format_plan_response): coherent bounded 556-char response.
- Polish noted for the next packet, not blocking: demand lines show
  item classes rather than display names (needs an optional name map
  into the formatter).
- Tracked debt reaffirmed: `main.py` is now well past the 500-line
  guidance (F-P8W01-5); an adapter-split refactor packet is warranted
  after Phase 3 wraps.

### Gate decision

- Decision: `QC_PASSED`; `ACCEPTED` under delegated G3. First usable
  planner milestone reached.
- Next action: SSP-P3-W05 (context enrichment, lookup exposure, config
  prompt modernization, F-W03-5 retirement), dispatched below; then a
  dedicated `release_version/` sync packet.

## 2026-07-02 - SSP-P4-W02 - Master-plan tool exposure

- Roadmap phase: Phase 4 - Five-stage master plan
- Owner: complete
- Status: `ACCEPTED` (delegated)
- Attempt: 1
- Dispatched: 2026-07-02, agent `p4w02-impl`
- Milestone: Phase 4 core is COMPLETE (master builder + tool
  exposure); mid-stage production-gate checkpoints remain a designed
  deferral pending player-tier input (see design decision above)
- Plan references: sections 10 (tool surface), 12 (Phase 4)
- Design decision logged: true production-gate checkpoints (plan 4.4)
  need actual player tier state (manual input or save-derived
  schematic purchases via the Phase 8 parser); deferred to a later
  packet with that design. In the meantime, append-only revisions
  under changed snapshots already provide checkpoint mechanics.

### Implementation packet (Fable 5)

Objective:

- Expose the accepted master-plan builder through the calculator tool:
  `scope="master"` builds all five stages, persists each as an
  append-only revision plus the solver runs, exports per-stage
  artifacts and one master summary artifact, and returns a bounded
  overview with transitions and reservations.

In scope:

- `satisfactory_adapter.py`: `run_master_calculation(...)` mirroring
  `run_plan_calculation`'s dependency style: calls
  `build_master_plan`, then per built stage (when persisting):
  `save_stage_plan` (stage rebuilt with its revision via
  `dataclasses.replace`), `record_solver_run`
  (`run_m<phase>_<revision>_<utcstamp>`), `export_stage_artifacts`;
  plus one master summary markdown artifact written via a new reports
  helper; returns the formatted response. `stopped_at_phase_N`
  results persist nothing and return the bounded diagnostic overview.
- `satisfactory_reports.py`:
  - `export_master_summary(workspace_dir, plan_id, result,
    display_names=None) -> str` writing
    `plans/<slug>/master_summary.md` (same containment idiom),
    containing the per-stage table (reuse
    `master_plan_summary_markdown`), a transitions section (per
    transition: counts per category plus up to 8 delta entries), and
    a reservations note.
  - `format_master_response(result, artifact_path, display_names=None,
    char_budget=3200) -> str`: header (status, pace), one line per
    stage (phase, nodes, machines, power), transition summary lines,
    diagnostics (cap 5), artifact line; whole-line truncation under
    the budget.
- `main.py`: `calculate_satisfactory_plan` gains
  `scope: Literal["stage", "master"] = "stage"`; master scope ignores
  `phase` (document in the docstring Args: phase is required only for
  stage scope; validate and say so when omitted... RESOLUTION: make
  `phase: int = 0` with validation: stage scope requires 1-5, master
  scope requires it omitted or 0). Description stays under 70 words.
  Audit mode unchanged.
- Tests: new `tests/test_master_tool.py` (stub pattern): master happy
  path persists 5 stage revisions + 5 solver runs + 6 artifacts and
  the response is bounded with all five stage lines; second call
  yields revisions 2 across all phases; persist=False leaves the
  store absent; stopped_at_phase path persists nothing and names the
  phase; stage scope behavior unchanged (regression: one existing-path
  test re-exercised here, not modified elsewhere); tool count still 3.

Explicitly out of scope: checkpoints (deferred, above), pins/bans,
scenario comparison (Phase 7), release re-sync (fold into the next
REL packet after Phase 4 completes).

Expected files:

```text
skills/satisfactory_assistant/satisfactory_adapter.py  (extend)
skills/satisfactory_assistant/satisfactory_reports.py  (extend)
skills/satisfactory_assistant/main.py                  (scope param)
skills/satisfactory_assistant/tests/test_master_tool.py (new)
```

Acceptance criteria:

1. Master scope: five persisted revisions, five solver runs, six
   artifacts, bounded response with stages + transitions; append-only
   proven on the second call.
2. Failure containment and persist=False purity hold.
3. Stage scope and audit mode behavior byte-unchanged (existing tests
   green, zero edits).
4. Usual battery clean; tool count 3; schema growth is the one scope
   param.

### Implementation result (Sonnet 5 agent, 2026-07-02)

- `run_master_calculation`, `export_master_summary`,
  `format_master_response`, and the `scope` param with early
  validation; 13 new tests; 323 passed total.
- Judgment calls, all accepted at QC: unused-but-symmetric
  `display_names` params (documented in docstrings); "six artifacts"
  read as 6 Markdown + 5 JSON sidecars (matches intent); master
  solver-run payloads built from StagePlan fields since the builder
  does not expose raw SolveResults (fine: the payload is provenance,
  not a contract).

### Quality control (Fable 5, 2026-07-02)

- Independent verification: 323 passed, 1 pre-existing skip; master
  tool tests 13/13 in isolation; ruff and compileall clean; scope
  wiring present; stage/audit paths byte-unchanged per zero edits to
  their tests.

### Gate decision

- Decision: `QC_PASSED`; `ACCEPTED` under delegated G3. Phase 4 core
  complete.
- Next action: Phase 5 begins with SSP-P5-W01 (extraction modeling),
  dispatched below.

## 2026-07-02 - SSP-P5-W01 - Extraction modeling for raw imports

- Roadmap phase: Phase 5 - Resource, logistics, and recipe constraints
- Owner: complete
- Status: `ACCEPTED` (delegated)
- Attempt: 1
- Dispatched: 2026-07-02, agent `p5w01-impl`
- Plan references: sections 12 (Phase 5: extractor tier, purity, and
  clock calculations), 16 (guardrails); the old YAGNI cut ("miner
  purity/tier from config default, not per-node") applies

### Implementation packet (Fable 5)

Objective:

- Stop treating raw imports as free: model the extractors that supply
  them (machine class, count, clock, power) using the catalog's
  already-parsed extractor data, under documented default assumptions
  (miner mark configurable per call, purity normal), and surface
  extraction machines and power in stage and master outputs.

Design decisions (locked):

- Purity assumption: normal (multiplier 1.0) for every solid node;
  per-node purity is Phase 8/9 territory (save-derived). Documented
  as an assumption string on every result that uses it.
- Extractor selection is data-driven from the catalog: for a raw item,
  candidate extractor buildings are those whose `allowed_resources`
  contain the item (or, when `allowed_resources` is empty, the
  conventional fallbacks by item form: Build_WaterPump for water,
  Build_OilPump for crude oil, `miner_mark` miner for solids; the
  fallback table lives in ONE module constant with a why-comment).
- `miner_mark` parameter: "mk1" | "mk2" | "mk3" mapping to
  Build_MinerMk1/2/3_C, default "mk2" (mid-game default, documented).
- Extractor count and clock mirror `schedule_machines` semantics:
  exact = required_rate / per-extractor rate (items_per_cycle /
  extract_cycle_time * 60 * purity), count = ceil with the same
  1e-9 nudge, group underclock, same 0.01 floor, power via the same
  exponent formula.
- Resource wells and geothermal stay out (already tracked TODO).

In scope:

- New pure module `satisfactory_extraction.py`:
  `plan_extraction(catalog, imports: tuple[RawImport, ...],
  miner_mark: str = "mk2") -> tuple[tuple[ResourceSource, ...],
  tuple[tuple[str, float], ...], tuple[str, ...]]` returning sources
  (extractor_class and extractor_count now filled, plus rate),
  power additions as (building_class, mw) pairs, and diagnostics
  (unknown extractor for item X; invalid miner_mark raises
  ValueError). ResourceSource's existing fields only; clock is
  implied by count vs rate and recorded in the diagnostics-free
  assumption line, NOT a new model field (no plan-model changes this
  packet).
- `satisfactory_adapter.py`: stage and master assembly call
  `plan_extraction` and: fill `StagePlan.sources` with the real
  entries, add extraction power pairs into the PowerPlan (rebuild via
  dataclasses.replace: total and by_building re-aggregated),
  append its diagnostics and the purity/miner assumptions to the
  stage's assumption tuple.
- `satisfactory_reports.py`: the Raw imports section lines gain
  " via N x <ExtractorClass>" when the matching source carries
  extractor data; master summary unchanged.
- Tests: new `tests/test_extraction.py` (fixture with miner cycle
  data, water pump, oil pump, an item with no candidate extractor ->
  diagnostic, invalid miner_mark -> ValueError, exact count/clock/
  power hand-computed, determinism); append-only additions to
  `tests/test_plan_tool.py` asserting the happy-path response now
  carries "via" extractor text and power total includes extraction;
  gated real-install test: phase 3 master build sources all carry
  extractor classes and counts, extraction power > 0, zero unknown-
  extractor diagnostics.

Explicitly out of scope: resource wells/geothermal, per-node purity,
belt/pipe checks, pins/bans and lexicographic objectives (P5-W02+),
config property exposure of miner_mark (function default only),
release re-sync.

Expected files:

```text
skills/satisfactory_assistant/satisfactory_extraction.py  (new)
skills/satisfactory_assistant/satisfactory_adapter.py     (extend)
skills/satisfactory_assistant/satisfactory_reports.py     (import lines)
skills/satisfactory_assistant/tests/test_extraction.py    (new)
skills/satisfactory_assistant/tests/test_plan_tool.py     (append only)
```

Acceptance criteria:

1. Hand-computed extractor counts, clocks, and power match exactly on
   fixtures (including the water/oil fallbacks).
2. Unknown-extractor items degrade to diagnostics, never crash;
   invalid miner_mark raises with a clear message.
3. Real-install phase 3 sources are fully resolved with positive
   extraction power and zero unknown-extractor diagnostics; stage and
   master totals include extraction power.
4. All pre-existing tests pass (append-only exceptions as listed);
   usual battery clean; no plan-model or tool-schema changes.

### Implementation result and QC (Fable 5 summary, 2026-07-02)

- `satisfactory_extraction.py` per packet (data-driven selection,
  single fallback table, mirrored schedule math with
  source-of-truth comments, deterministic outputs); adapter wires
  stage directly and post-processes master stages
  (`satisfactory_master_plan.py` untouched, respecting file scope);
  reports gain "via N x Extractor" text; 11 new tests.
- Real-install phase 3: iron 6 x MinerMk2, coal 3, copper 1, stone 1,
  oil 1 x OilPump; extraction adds 177.6 MW of the 1046.3 MW stage
  total; zero unknown-extractor diagnostics. Extractor counts, clocks,
  and power independently hand-verified at QC (6 x Mk2 at 0.9896 for
  712.5 iron/min; power matches the exponent formula).
- All four flagged judgment calls accepted, including removal of the
  now-false "extractors not modeled" assumption string.
- Independent battery: 334 passed, 1 pre-existing skip; ruff and
  compileall clean.

### Gate decision

- Decision: `QC_PASSED`; `ACCEPTED` under delegated G3.
- Next: SSP-P5-W02 (pins, bans, two-level lexicographic objective),
  dispatched below.

## 2026-07-02 - SSP-P5-W02 - Recipe pins, bans, and two-level objective

- Roadmap phase: Phase 5 - Resource, logistics, and recipe constraints
- Owner: complete
- Status: `ACCEPTED` (delegated)
- Attempt: 1
- Dispatched: 2026-07-02, agent `p5w02-impl`
- Plan references: sections 8.3 (lexicographic priorities 5 and 7),
  8.4, 10 (calculator typed pins/bans), 12 (Phase 5: "no locked recipe
  selected by default", "pins and bans")

### Implementation packet (Fable 5)

Objective:

- Recipe pinning and banning in the solver plus a two-level
  lexicographic objective (minimize raw imports, then among
  raw-optimal solutions minimize total machine-equivalents), exposed
  through typed calculator params.

Locked design:

- Ban semantics: banned recipe keys are removed from the candidate set
  before reachability; a demand item made unproducible by bans yields
  the standard infeasibility diagnostic naming the item AND the ban.
- Pin semantics: pinning recipe R (which must be in the allowed set,
  else a diagnostic + infeasible) bans every OTHER candidate recipe
  whose products include R's FIRST product (the primary-product
  convention, documented); the pin itself is exempt from alternates
  gating only if explicitly included via include_alternates (pins do
  not smuggle locked recipes: guardrail "no locked recipe selected by
  default").
- Two-level objective: solve level 1 as today (raw + epsilon); add
  constraint total_raw <= level1_optimum * (1 + 1e-9) + 1e-9; re-solve
  minimizing sum of recipe runs; fall back to the level-1 solution
  with a diagnostic if level 2 is infeasible (numerical safety).
  Deterministic as before.
- solve_stage signature: new keyword-only params pinned:
  frozenset[str] = frozenset(), banned: frozenset[str] = frozenset().

In scope:

- `satisfactory_solver.py`: the above; SolveResult unchanged.
- `main.py` + `satisfactory_adapter.py`: calculator params
  `pin_recipes: str = ""`, `ban_recipes: str = ""` (semicolon
  separated, normalized), threaded to solve_stage in stage scope and
  to build_master_plan... master threading requires touching
  `satisfactory_master_plan.py`: ALLOWED this packet (add
  pinned/banned pass-through params with defaults).
- Tests: new `tests/test_solver_policies.py` (fixture: ban forces the
  inefficient recipe; ban-to-infeasible names item and ban; pin
  selects the pinned recipe over a cheaper competitor; pin of a
  non-allowed recipe -> infeasible diagnostic; two-level: two
  raw-equivalent solutions exist and the fewer-machines one wins;
  determinism); append-only in `tests/test_plan_tool.py` (params
  reach the solver: one stub test with a ban changing the response).

Out of scope: reuse-aware level (P5-W03), belts/byproducts (P5-W04),
config exposure, release re-sync.

Expected files:

```text
skills/satisfactory_assistant/satisfactory_solver.py       (extend)
skills/satisfactory_assistant/satisfactory_master_plan.py  (pass-through)
skills/satisfactory_assistant/satisfactory_adapter.py      (thread params)
skills/satisfactory_assistant/main.py                      (two params)
skills/satisfactory_assistant/tests/test_solver_policies.py (new)
skills/satisfactory_assistant/tests/test_plan_tool.py      (append only)
```

Acceptance criteria:

1. Ban and pin fixture behaviors exact, including both infeasibility
   diagnostics; pins never smuggle alternates.
2. Two-level objective provably picks fewer machines among
   raw-optimal solutions and never degrades raw optimality (assert
   both raw totals equal and machines strictly fewer in the fixture).
3. Existing behavior unchanged when both sets are empty (existing
   tests green byte-unchanged, level 2 running is allowed as long as
   results stay identical on all existing fixtures and the
   real-install tests).
4. Usual battery clean; schema growth limited to the two params.

### Implementation result and QC (Fable 5 summary, 2026-07-02)

- Pins/bans and the two-level objective implemented per the locked
  design; 7 new tests; params threaded through master plan, adapter,
  and tool (description at 74 words).
- Exemplary self-QC by the implementer, recorded for the record: it
  detected that a git-stash baseline was invalid on this untracked
  tree, rebuilt a true baseline by hand-restoring originals, thereby
  caught a real self-introduced regression (level 2's zero raw weight
  let HiGHS leave a spurious 1.3e-6 water import that sized a phantom
  extractor), and fixed it by carrying the stability epsilon into the
  level-2 objective, documented inline.
- QC: 341 passed, 1 pre-existing skip; policy tests 6/6 in isolation;
  ruff and compileall clean. The epsilon deviation is accepted as
  necessary for acceptance criterion 3.

### Gate decision

- Decision: `QC_PASSED`; `ACCEPTED` under delegated G3.
- Next: SSP-P5-W03 (reuse-aware objective for master builds),
  dispatched below.

## 2026-07-02 - SSP-P5-W03 - Reuse-aware objective for master builds

- Roadmap phase: Phase 5 - Resource, logistics, and recipe constraints
- Owner: complete
- Status: `ACCEPTED` (delegated)
- Attempt: 1
- Dispatched: 2026-07-02, agent `p5w03-impl`
- Plan references: section 8.3 priority 3 (reuse prior-stage capacity
  and avoid teardown), 12 (Phase 5)

### Implementation packet (Fable 5)

Objective:

- Make consecutive master-plan stages prefer reusing prior-stage
  machines over building new ones, as a third objective level that
  never degrades raw optimality.

Locked design:

- `solve_stage` gains keyword-only `prior_capacity:
  dict[str, float] | None = None` (recipe key -> machines_exact from
  the previous stage). When provided, level 2's objective becomes
  "minimize NEW machine-equivalents": per candidate recipe with prior
  capacity p_i, an auxiliary variable n_i with constraints
  n_i >= x_i - p_i and n_i >= 0; recipes without prior capacity use
  x_i directly. Objective: sum of n_i (plus the established stability
  epsilons on raw and run variables). The level-2 raw cap constraint
  is unchanged, so raw optimality is preserved by construction.
- When `prior_capacity` is None, behavior is EXACTLY today's level 2
  (regression criterion as in P5-W02).
- `build_master_plan` threads each built stage's machines_exact per
  recipe (from its nodes) as the next stage's prior_capacity.
  Single-stage tool calls pass None (no behavior change).

In scope:

- `satisfactory_solver.py` (the auxiliary-variable level 2),
  `satisfactory_master_plan.py` (threading), new
  `tests/test_solver_reuse.py`:
  - Fixture where two raw-equivalent structures exist and prior
    capacity on the otherwise-losing recipe tips level 2 to reuse it
    (hand-computed: assert equal raw, and that the reused recipe
    keeps at least its prior machines while total NEW machines are
    strictly fewer than without prior_capacity).
  - prior_capacity=None equivalence: identical SolveResult to a call
    without the param on the policy fixture.
  - Master integration: two-phase fixture where phase 2 without
    reuse would flip recipes; with threading, the phase-1 recipe is
    retained (transition shows no retirement) and a why-comment
    explains the scenario arithmetic.
  - Real-install gated: five-phase master build still completes,
    still zero teardown warnings, and phase power/machine totals stay
    within 1 percent of the recorded P4-W01 numbers (they were
    already reuse-friendly; this asserts no accidental degradation).
- Determinism as always.

Out of scope: belts/byproducts (P5-W04), per-stage reservations as
constraints, tool params, release re-sync.

Expected files:

```text
skills/satisfactory_assistant/satisfactory_solver.py       (level 2)
skills/satisfactory_assistant/satisfactory_master_plan.py  (threading)
skills/satisfactory_assistant/tests/test_solver_reuse.py   (new)
```

Acceptance criteria:

1. Reuse fixture behaves exactly as hand-computed; raw optimality
   provably preserved.
2. None-equivalence and full-suite regression hold (before/after
   proof with a TRUE baseline: copy the two source files aside and
   diff-restore, do NOT rely on git stash on this untracked tree).
3. Real-install master build unchanged within tolerance, zero
   teardown warnings.
4. Usual battery clean.

### Implementation result and QC (Fable 5 summary, 2026-07-02)

- Reuse level implemented exactly per the locked design (aux
  variables only where prior capacity exists, weight folded onto x_i
  otherwise, epsilon rationale extended with a sound in-capacity
  floating argument); master threading via machines_exact per node;
  5 new tests including a counterfactual-proven master integration
  case; TRUE-baseline proof done correctly (hand-restored originals).
- Deviation upheld with CORRECTED ATTRIBUTION: the agent found phase 5
  live-rebuilding at 257 machines / 2012.021 MW vs the P4-W01
  recording (260 / 2067.724) and proved threaded == unthreaded on
  current code (so not caused by this packet), but attributed the
  delta to game-data drift. QC refuted that: the Docs file mtime is
  2026-05-31, unchanged since before this workstream. The true cause
  is the ACCEPTED P5-W01/P5-W02 changes landing after the P4-W01
  snapshot: level 2 legitimately trims machine slack among
  raw-optimal solutions on the largest phase, and extraction power
  reshaped totals. The redesigned test (threaded vs unthreaded
  equality on the identical catalog, phases 1-4 still matching the
  recording exactly) is accepted as the strictly stronger invariant.
- Battery: 346 passed, 1 pre-existing skip; ruff and compileall clean.

### Gate decision

- Decision: `QC_PASSED`; `ACCEPTED` under delegated G3.
- Next: SSP-P5-W04 (logistics capacity checks and byproduct
  policies), the Phase 5 closer, dispatched below.

## 2026-07-02 - SSP-P5-W04 - Logistics capacity checks and byproduct policies

- Roadmap phase: Phase 5 - Resource, logistics, and recipe
  constraints (final packet)
- Owner: complete
- Status: `ACCEPTED` (delegated)
- Attempt: 1
- Dispatched: 2026-07-02, agent `p5w04-impl`
- Milestone: roadmap Phase 5 is COMPLETE (extraction, pins/bans with
  the two-level objective, reuse-aware master builds, logistics
  capacity checks and explicit byproduct surpluses all `ACCEPTED`)
- Plan references: sections 6.2 (belt and pipe capacities), 8.2
  (surplus requires an explicit sink), 12 (Phase 5 acceptance: "no
  resource or capacity is silently overcommitted")

### Implementation packet (Fable 5)

Objective:

- Parse belt and pipe capacities from the Docs, check every
  production node's per-item line rates against the best
  capability-gated logistics tier, and make byproduct surpluses
  explicit instead of silent.

Locked design:

- Docs extension: parse `FGBuildableConveyorBelt` (field `mSpeed`,
  items/min is mSpeed/2 per the known Docs convention: VERIFY against
  real entries before trusting, report what the data shows) and
  pipelines (`FGBuildablePipeline`, `mFlowLimit` m3/min after unit
  normalization: same verify-first rule) into a new `Logistics`
  dataclass on the catalog: class_name, display_name, capacity,
  is_pipe. Catalog getters: `belts()`, `pipes()` sorted by capacity.
- Availability gating: a belt/pipe tier is available to a stage when
  its build recipe... building recipes are not recipes in FGRecipe
  with mProducedIn manufacturers, they are build-gun recipes: gating
  via schematic unlocked_recipes referencing e.g.
  Recipe_ConveyorBeltMk4_C. Check the real Docs: milestone unlocks DO
  list belt recipes. Gate: highest belt/pipe whose unlocking
  schematic is in the snapshot's purchased set, else the lowest tier
  with a diagnostic. VERIFY against real Docs and report.
- Checks (pure function `check_logistics(catalog, snapshot, nodes,
  sources) -> tuple[diagnostics, assumptions]`): for each ProcessNode
  and each input/output item rate (recompute per-item rates from the
  recipe as the solver does): lines_needed = ceil(rate /
  best_capacity); emit an info-style diagnostic line per node-item
  needing > 1 line ("node X: item Y needs N lines of Belt Mk-K") and
  a warning when even the best available tier requires more than 4
  parallel lines (arbitrary visibility threshold, documented).
  Extractor sources checked the same way.
- Byproducts: from the stage's solved node rates and demands, compute
  per-item surplus (production - consumption - demand); items with
  surplus > 1e-6 get one diagnostic each ("surplus: item X at
  R/min; route to sink or storage") and the stage gains the
  assumption "surpluses require sink or storage (unmodeled)".
- Wire both into stage and master assembly (adapter), surfacing in
  the Diagnostics sections already rendered; no tool-schema changes.

In scope:

- `satisfactory_docs.py` (Logistics parsing + getters),
  new `satisfactory_logistics.py` (checks + surplus), adapter wiring,
  new `tests/test_logistics.py` (fixture belts/pipes with verified
  real-shape fields, gating by snapshot, line-count math, surplus
  detection incl. the byproduct fixture from the solver tests,
  determinism), append-only response assertion in
  `tests/test_plan_tool.py`, gated real-install test (phase 3 build:
  belt tier resolves from the snapshot, no crash, diagnostics
  present-or-empty without error).

Out of scope: routing/topology, train/drone logistics, per-line belt
planning artifacts, Phase 6+ work, release re-sync (queued after this
packet as SSP-REL-W02).

Expected files:

```text
skills/satisfactory_assistant/satisfactory_docs.py       (Logistics)
skills/satisfactory_assistant/satisfactory_logistics.py  (new)
skills/satisfactory_assistant/satisfactory_adapter.py    (wiring)
skills/satisfactory_assistant/tests/test_logistics.py    (new)
skills/satisfactory_assistant/tests/test_plan_tool.py    (append only)
```

Acceptance criteria:

1. Belt/pipe capacities parse from verified real Docs shapes (report
   the actual field semantics found); gating follows the snapshot.
2. Line-count math exact on fixtures; surplus detection matches the
   solver's byproduct fixture arithmetic.
3. Real-install phase 3 runs clean with plausible belt diagnostics;
   nothing silently overcommitted (surpluses all surfaced).
4. Existing tests green byte-unchanged (append-only exception);
   usual battery clean.

### Implementation result and QC (Fable 5 summary, 2026-07-02)

- Logistics parsing verify-first CONFIRMED against real Docs
  (belt items/min = mSpeed/2 across all six tiers, pipe m3/min =
  mFlowLimit*60, both validated against in-game description text);
  exact-suffix NativeClass matching adopted after the real install
  exposed substring pollution from PipelineJunction/PipelinePump
  groups; cosmetic NoIndicator duplicates filtered; unlock gating via
  the confirmed Build_/Recipe_ naming convention and the existing
  schematic index. check_logistics with tier fallback, multi-line and
  >4-line diagnostics, and explicit byproduct surpluses wired into
  stage and master assembly; 16 new tests.
- Real-install phase 3: gated to Belt Mk4 and Pipe Mk2, 2 multi-line
  diagnostics, 1 surplus diagnostic, all well-formed.
- QC battery: 362 passed, 1 pre-existing skip; ruff and compileall
  clean. Phase 5 acceptance sentence satisfied: nothing silently
  overcommitted.

### Gate decision

- Decision: `QC_PASSED`; `ACCEPTED` under delegated G3. Phase 5
  complete.
- Next: SSP-REL-W02 (release re-sync for the Phase 4/5 modules),
  dispatched below; Phase 6 packet drafting follows.

## 2026-07-02 - SSP-REL-W02 - Release re-sync for Phase 4 and 5

- Roadmap phase: release engineering
- Owner: complete
- Status: `ACCEPTED` (delegated; QC verified 362/1 skip, parity 29/0
  mismatches per agent + spot-checked release files and installer
  manifest at version 0.3.0)
- Attempt: 1
- Dispatched: 2026-07-02, agent `relw02-impl`

### Implementation packet (Fable 5)

Objective:

- Bring `release_version/` up to the Phase 5 state: add the two new
  runtime modules to the manifests, bump to v0.3.0, regenerate, and
  verify parity.

In scope:

- `update_release.py` RELEASE_FILES: add `satisfactory_extraction.py`
  and `satisfactory_logistics.py`; rename the release-notes entry to
  `RELEASE_NOTES_v0.3.0.txt`.
- New root `RELEASE_NOTES_v0.3.0.txt` (delete the v0.2.0 root file):
  five-stage master plans (scope="master") with transitions and
  reuse-aware solving, recipe pins/bans, extraction modeling with
  power, belt/pipe capacity diagnostics, byproduct surplus reporting.
- `skill_installer_config.json`: version 0.3.0; files array gains the
  two modules and the new notes filename (drop the old one).
- `TESTER_README.md`: one short paragraph noting master scope and
  pins/bans params.
- Run the script; SHA parity check (expect 29 files); node_modules
  absent; compileall both trees; full suite unaffected.

Expected files: update_release.py, RELEASE_NOTES_v0.3.0.txt (new,
v0.2.0 deleted), skill_installer_config.json, TESTER_README.md,
release_version/** (regenerated).

Acceptance: parity 0 mismatches; suite 362/1 skip unchanged; battery
clean.

### Implementation result / QC / Gate

Per the status line above: implemented per packet, verified, accepted.
v0.3.0 is the current installable release; AppData untouched.

## 2026-07-02 - SSP-P6-W01 - Construction bills and commissioning order

- Roadmap phase: Phase 6 - Construction and commissioning
- Owner: complete
- Status: `ACCEPTED` (delegated)
- Attempt: 2
- Dispatched: 2026-07-02, agent `p6w01-impl`
- Plan references: sections 12 (Phase 6: construction bill of
  materials, dependency-ordered build stages, power-first staging),
  7 (BuildTask)

### Implementation packet (Fable 5)

Objective:

- For any stage plan, compute what to build, what materials to bring,
  and in what order: per-node construction bills from the already
  parsed build-gun recipes, aggregated stage BOM, and a
  dependency-ordered commissioning sequence (extractors first, then
  production nodes upstream-to-downstream).

Locked design:

- Build-recipe resolution reuses the P5-W04-confirmed convention:
  normalized building key "build_x" maps to recipe key "recipe_x";
  a building whose build recipe is missing gets a diagnostic and an
  empty materials list (never crash). Belt/pipe/foundation costs are
  OUT (lengths are layout, Phase 9); recorded as an assumption.
- Ordering: extractor sources first (order_index 0 group), then
  production nodes in topological order of the recipe graph
  (edges: node A precedes node B when A's recipe outputs an item B's
  recipe consumes; ties broken by node_id; cycles broken
  deterministically at the lexicographically smallest back-edge with
  a diagnostic noting the loop). Power-first is recorded as an
  assumption string (generators are unmodeled).
- New frozen `BuildTask` in `satisfactory_plan_models.py` (+payload
  round-trip, same conventions): task_id ("task_<order>_<node_id>"),
  order_index, node_id, building_class, count, materials
  (tuple[(item_class, quantity), ...], quantity = per-build cost x
  count), depends_on (tuple of node_ids).
- Pure module `satisfactory_construction.py`:
  `build_construction_plan(catalog, stage: StagePlan) ->
  (tuple[BuildTask, ...], tuple[(item_class, float), ...] stage BOM,
  diagnostics, assumptions)`.
- Surfacing: adapter appends a "Construction:" section to stage-scope
  responses ONLY when a new `include_construction: bool = False`
  calculator param is set (schema growth: one bool; keeps default
  responses unchanged); the full task list and BOM go into a third
  artifact `phase<k>_rev<r>_construction.md` via a new reports helper
  (same containment); master scope is untouched this packet.

In scope: the four files above plus tests: new
`tests/test_construction.py` (fixture: known build costs, hand-
computed BOM aggregation, topological order incl. a deliberate cycle
fixture and the extractors-first rule, missing-build-recipe
diagnostic, BuildTask payload round-trip, determinism) and
append-only `tests/test_plan_tool.py` (include_construction=True
response carries the section and writes the third artifact;
default response byte-unchanged), plus a gated real-install test
(phase 1 stage: 7 tasks + extractor tasks, BOM non-empty, every
material a real item, order respects the iron chain).

Out of scope: build progress tracking against todos (P6-W02),
generators/power buildings, belts in BOM, master-scope construction,
release re-sync.

Expected files:

```text
skills/satisfactory_assistant/satisfactory_plan_models.py   (BuildTask)
skills/satisfactory_assistant/satisfactory_construction.py  (new)
skills/satisfactory_assistant/satisfactory_reports.py       (artifact)
skills/satisfactory_assistant/satisfactory_adapter.py       (wiring)
skills/satisfactory_assistant/main.py                       (one bool param)
skills/satisfactory_assistant/tests/test_construction.py    (new)
skills/satisfactory_assistant/tests/test_plan_tool.py       (append only)
```

Acceptance criteria:

1. BOM and ordering exact on fixtures (cycle and extractor rules
   included); BuildTask round-trips.
2. Default responses byte-unchanged; the opt-in section and third
   artifact appear only when requested.
3. Real-install phase 1 construction plan is coherent (all materials
   resolve, iron-chain order sound).
4. Usual battery clean; schema growth one bool param.

### Implementation result and QC (Fable 5 summary, 2026-07-02)

- Attempt 1: BuildTask model, pure construction module (Kahn ordering,
  extractors first, deterministic cycle breaking), opt-in
  include_construction with byte-unchanged defaults, third artifact,
  15 tests. Verify-first caught the Smelter/Foundry legacy key
  collision (Recipe_SmelterMk1_C builds the Foundry): the product
  guard prevented silently wrong materials.
- F-P6W01-1 (Medium): guard alone left the Smelter with an empty BOM;
  QC verified Recipe_SmelterBasicMk1_C as the true build recipe and
  required a product-identity search fallback. Attempt 2 delivered it
  (keyed lookup with guard, then sole-product catalog scan,
  lexicographic pick, diagnostic only when both fail).
- Real-install phase 1 post-fix: 8 tasks, 9 BOM lines, ZERO
  diagnostics; the Smelter resolves to its real cost (5 Iron Rod +
  8 Wire), matching known game values.
- QC battery: 378 passed, 1 pre-existing skip; ruff and compileall
  clean; fallback confirmed on disk.

### Gate decision

- Decision: `QC_PASSED`; `ACCEPTED` under delegated G3.
- Next: SSP-P6-W02 (commissioning checks and build todos), the Phase 6
  closer, dispatched below.

## 2026-07-02 - SSP-P6-W02 - Commissioning checks and build todos

- Roadmap phase: Phase 6 - Construction and commissioning (final)
- Owner: complete
- Status: `ACCEPTED` (delegated)
- Attempt: 1
- Dispatched: 2026-07-02, agent `p6w02-impl`
- Milestone: roadmap Phase 6 is COMPLETE (construction bills,
  commissioning order, commissioning checks, build todos)
- Plan references: section 12 Phase 6 acceptance ("each stage explains
  what to build, what to bring, and how to verify it"; "build progress
  linked to plan nodes")

### Implementation packet (Fable 5)

Objective:

- Finish Phase 6: every construction task carries commissioning
  checks in the artifact, and construction can be turned into
  trackable journal todos linked to plan nodes.

Locked design:

- Commissioning checks are static, deterministic lines per task in
  the construction markdown (reports helper): inputs connected
  (list the recipe's input items), output routed (list outputs),
  clock set to the node's clock value, power available (node's
  power_mw). Extractor tasks: resource target and output belt/pipe.
  No new models; text only in the artifact.
- Build todos: new calculator param `create_build_todos: bool =
  False` (only meaningful with include_construction=True and
  persist=True and plan writes allowed): for each BuildTask (capped
  at 20, "+N more" diagnostic beyond), add a journal todo via the
  existing workspace API with title
  "Build {count} x {building display name} ({node_id})" and details
  naming the task_id and stage phase/revision. Respect
  allow_plan_writes (refusal message reused); duplicate-safe: a
  second identical call may create duplicate todos, DOCUMENT this as
  known behavior (dedup is journal-domain work, out of scope).
- Response gains one line when todos were created: "Created N build
  todos." Schema growth: the one bool.

In scope: satisfactory_reports.py (checks in
construction_plan_to_markdown), satisfactory_adapter.py (todo
creation), main.py (param), tests: test_construction.py append-only
(markdown contains the check lines), test_plan_tool.py append-only
(todos created when flags align; not created when
include_construction is False or allow_plan_writes is False; response
line present; cap respected with 25-task fixture).

Out of scope: todo-task dedup, master-scope todos, progress
percentage reporting, release re-sync (SSP-REL-W03 queued after
Phase 7).

Acceptance criteria:

1. Check lines deterministic and item-accurate on fixtures.
2. Todo creation gated on all three flags, capped, linked via task_id
   and node_id in details; journal write path respected.
3. Existing tests byte-unchanged (append-only exceptions); battery
   clean; schema growth one bool.

### Implementation result and QC (Fable 5 summary, 2026-07-02)

- Commissioning check lines per task type (recipe-accurate inputs/
  outputs, clock, power; belt-vs-pipe routing by Docs item form);
  catalog threaded into the two construction report functions (both
  call sites updated, none in tests). Build todos with the triple
  gate, 20-cap with overflow reporting, and reused refusal line;
  workspace and allow-plan-writes passed as lazy callables so
  existing duck-typed stubs are provably unaffected. 9 new tests.
- QC battery: 387 passed, 1 pre-existing skip; ruff and compileall
  clean.

### Gate decision

- Decision: `QC_PASSED`; `ACCEPTED` under delegated G3. Phase 6
  complete.
- Next: SSP-P7-W01 (pace scenario comparison), dispatched below.

## 2026-07-02 - SSP-P7-W01 - Pace scenario comparison

- Roadmap phase: Phase 7 - Scenario comparison
- Owner: complete
- Status: `ACCEPTED` (delegated)
- Attempt: 1
- Dispatched: 2026-07-02, agent `p7w01-impl`
- Milestone: roadmap Phase 7 is COMPLETE. Accepted deviations:
  window_text as one formatted string; master scenario rows exclude
  extraction/logistics post-processing (documented; scenarios are
  internally consistent since every row is treated identically).
  QC verified 405 passed, 1 pre-existing skip; real-install scenarios
  show exact one-third raw scaling at pace 3.0 and monotonic power.
- Plan references: sections 2.2 (pace bounds), 12 (Phase 7:
  reproducible, traceable differences; never above 3.0)

### Implementation packet (Fable 5)

Objective:

- Side-by-side pace scenarios: solve the same stage (or master plan)
  at up to four pace multipliers and return a reproducible comparison
  of windows, machines, power, and raw totals. Exploratory only:
  scenarios are never persisted.

Locked design:

- New pure module `satisfactory_scenarios.py`:
  `compare_pace_scenarios(catalog, data, paces: tuple[float, ...],
  phase: int | None = None, include_alternates=(), pinned=(),
  banned=()) -> ScenarioComparison` where phase None means master
  (five-phase totals per scenario) and 1-5 means that stage.
  Validation: 1 to 4 paces, each in [1.0, 3.0], deduplicated
  preserving order; ValueError otherwise. Each scenario row (frozen
  dataclass ScenarioRow): pace, window_hours (stage) or total window
  text (master), node_count, machine_count total, power_mw total,
  raw_imports tuple[(item_class, rate)], status. ScenarioComparison
  (frozen): rows plus shared diagnostics. Reuses build_master_plan /
  the stage pipeline pieces; deterministic.
- Tool exposure: `pace_scenarios: str = ""` on the calculator
  (semicolon-separated floats). When set: scenarios mode overrides
  persist (nothing persisted, say so in the response), works with
  scope stage (phase required) and master both; response via a new
  `format_scenarios_response` (reports): one block per scenario, a
  "delta vs first scenario" line each (machines, power as
  percentages), bounded 3200.
- Schema growth: the one string param.

In scope: the new module, reports formatter, adapter routing, main
param, tests: new `tests/test_scenarios.py` (validation cases, stage
rows exact on the fixture: pace 2.0 halves rates so machine counts
drop accordingly, hand-computed; master rows via the two-phase
fixture; determinism; dedup) and append-only `tests/test_plan_tool.py`
(scenarios response bounded, says not persisted, store untouched);
gated real-install test (phase 1 at 1.0/2.0/3.0: machine totals
non-increasing, power non-increasing, raw rate at 3.0 is one third of
1.0 within tolerance).

Out of scope: objective scenarios (alternate strategy comparison),
persistence/branching, release re-sync (SSP-REL-W03 after this).

Acceptance criteria:

1. Validation and hand-computed stage rows exact; master rows
   coherent; determinism holds.
2. Scenarios never touch the store; response bounded and says so.
3. Real-install monotonicity and one-third-rate checks pass.
4. Existing tests byte-unchanged (append-only exception); battery
   clean; schema growth one param.

### Implementation result / QC / Gate

Per the status line above: implemented per packet, verified, accepted.

## 2026-07-02 - SSP-REL-W03 - Release re-sync for Phase 6 and 7 (v0.4.0)

- Roadmap phase: release engineering
- Owner: complete
- Status: `ACCEPTED` (delegated; QC verified 405/1 skip, parity 31/0,
  installer at 0.4.0 with 28 files, both new modules in the release)
- Attempt: 1
- Dispatched: 2026-07-02, agent `relw03-impl`
- Scope: same mechanical pattern as SSP-REL-W02 (that entry is the
  precedent): RELEASE_FILES gains `satisfactory_construction.py` and
  `satisfactory_scenarios.py`; notes become
  `RELEASE_NOTES_v0.4.0.txt` (construction bills and commissioning
  checks with opt-in build todos; pace scenario comparison; delete the
  v0.3.0 root file); installer config version 0.4.0 with the files
  array updated; TESTER_README gains one paragraph on
  include_construction/create_build_todos/pace_scenarios; regenerate,
  SHA parity (expect 31 files), node_modules absent, compileall both
  trees, suite 405/1 skip unchanged.

### Implementation result / QC / Gate

Per the status line above: implemented per packet, verified, accepted.

## 2026-07-02 - SSP-P8-W02 - Actuals versus plan audit

- Roadmap phase: Phase 8 - Actual factory adapters (closer; W01 was
  the 2026-06-29 mirror slice)
- Owner: complete
- Status: `ACCEPTED` (delegated)
- Attempt: 2
- Dispatched: 2026-07-02, agent `p8w02-impl`
- Milestone: roadmap Phase 8 is COMPLETE (mirror + actuals-vs-plan
  audit reachable end-to-end via mode="audit" with a phase).
- Attempt-1 stop-and-report upheld as a packet spec error ("docstring
  text only" was unsatisfiable alongside phase threading); RULING
  (fifth of category): pinned dispatch test's stub extended to record
  phase, main.py threading authorized. Attempt 2 delivered exactly
  that; QC verified 422 passed / 1 pre-existing skip, ruff and
  compileall clean, no-phase path byte-identical.
- Plan references: section 12 Phase 8 ("actual-versus-planned audit";
  "imports are provenance-tagged and manual planning remains
  available when they fail")

### Implementation packet (Fable 5)

Objective:

- Close the loop between plan and reality: compare the save-derived
  mirror (what the player actually built) against the latest
  persisted stage plan and report capacity gaps, surpluses, and
  unplanned production, through the existing audit mode with zero
  tool-schema changes.

Locked design:

- New pure module `satisfactory_actuals.py`:
  `compare_actuals(mirror_machines: list[dict], stage_payload: dict)
  -> ActualsComparison` where mirror_machines are the mirror's
  machine dicts (fields: recipe.name, clock, confidence) and
  stage_payload is a stored StagePlan payload. Per normalized recipe
  key: planned capacity = node machine_count_exact; actual capacity =
  sum of machine clocks for machines whose recipe normalizes to that
  key (a machine at 0.5 clock is 0.5 machine-equivalents; unknown
  clock counts as 1.0 with a note). Rows (frozen ActualsRow): recipe
  key, planned_capacity, actual_capacity, delta, classification:
  "missing" (actual < planned - 1e-3), "matched" (within 1e-3),
  "surplus", or "unplanned" (actual with no planned node). Planned
  nodes with zero actuals classify "missing" with actual 0.
  ActualsComparison: rows sorted (missing first by largest shortfall,
  then unplanned, surplus, matched), totals, provenance strings
  (save name, plan phase/revision), diagnostics.
- Audit-mode integration (adapter `run_factory_audit_pipeline` /
  `_run_factory_audit` seam): after the mirror is built, if the
  calculator call carried a phase in 1-5 AND the workspace store has
  a stage for plan "master" at that phase, load the LATEST revision
  and append a bounded "Plan vs actual (phase N rev R):" section to
  the audit response via a new reports formatter
  `format_actuals_section(comparison, display_names=None,
  char_budget=1200)`: top 5 missing rows as "build X more <recipe>"
  lines with capacity numbers, up to 3 unplanned, up to 3 surplus,
  one matched-count summary line. No phase given or no stored plan:
  audit behaves exactly as today (byte-identical).
- The existing audit-mode phase validation must be relaxed
  accordingly: phase 0 (default) = classic audit; 1-5 = audit with
  comparison when available. Update the tool docstring Args entry for
  phase to say so (schema text change only, no new params).

In scope: the new module, reports formatter, adapter integration,
main.py docstring text, tests: new `tests/test_actuals.py` (synthetic
mirror dicts vs a hand-built stage payload covering all four
classifications, clock-sum math incl. unknown-clock note, sorting,
determinism, empty-mirror and empty-plan edges) and append-only
`tests/test_plan_tool.py` (audit with phase and a stored plan carries
the section, audit without phase is byte-identical to before,
audit with phase but no stored plan says so in one line).

Out of scope: purity decoding, resource wells (still tracked TODO),
schematic-purchase-derived gates (future), HUD delivery, release
re-sync (fold into SSP-REL-W04 after Phase 9).

Expected files:

```text
skills/satisfactory_assistant/satisfactory_actuals.py  (new)
skills/satisfactory_assistant/satisfactory_reports.py  (formatter)
skills/satisfactory_assistant/satisfactory_adapter.py  (integration)
skills/satisfactory_assistant/main.py                  (docstring text)
skills/satisfactory_assistant/tests/test_actuals.py    (new)
skills/satisfactory_assistant/tests/test_plan_tool.py  (append only)
```

Acceptance criteria:

1. Classification, clock-sum math, and ordering exact on fixtures.
2. Audit without a phase is byte-identical to current behavior;
   with a phase and stored plan the bounded section appears; with a
   phase and no plan a single explanatory line appears.
3. No tool-schema changes (docstring text only); battery clean;
   existing tests byte-unchanged (append-only exception).

### Implementation result / QC / Gate

Per the status lines above: accepted at attempt 2.

## 2026-07-02 - SSP-P9-W01 - Locate and schematic map artifact

- Roadmap phase: Phase 9 - Logistics networks and layout (map
  artifacts; the user-requested HUD map pinpoint groundwork from
  TODO.md)
- Owner: complete
- Status: `ACCEPTED` (delegated)
- Attempt: 1
- Dispatched: 2026-07-02, agent `p9w01-impl`
- QC evidence: 443 passed, 1 pre-existing skip; ruff and compileall
  clean; QC additionally ran the feature END TO END against the real
  copied save (113k objects -> mirror -> locate "iron ingot" -> two
  real Iron Ingot lines found at world coordinates -> deterministic
  1024x1024 pin map rendered, 15,244 bytes) and delivered the artifact
  to the user. Deferred remainder of Phase 9 (typed transport links,
  station capacity, areas) recorded as designed deferrals: they need
  layout data sources that do not exist yet.
- Plan references: section 12 Phase 9 ("optional graph and map
  artifacts"); TODO.md feature entry (2026-07-01)

### Implementation packet (Fable 5)

Objective:

- Answer "where is X" from the save-derived mirror with coordinates
  and a rendered schematic map artifact (pin on a coordinate grid),
  suitable for the HUD skill to display via its verified markdown
  image support.

Locked design:

- Base map: a GENERATED schematic grid, not a game/community map
  image (licensing-free; decision recorded against the TODO's open
  question). Rendering via Pillow (verified present: 12.1.1) behind a
  guarded import; absent Pillow degrades to text-only coordinates
  with a note.
- New pure module `satisfactory_map.py`:
  - `find_locations(mirror: dict, query: str, limit: int = 5) ->
    tuple[LocationHit, ...]` searching the mirror payload's inferred
    lines (primary output display name) and machines (recipe/resource
    name, type), case-insensitive, ranked exact/prefix/substring like
    the dataset lookups; LocationHit (frozen): label, kind
    ("line"/"machine"), x, y, z, machine_count (lines) or clock.
  - `render_map(hits, all_points, out_path: Path, highlight_index:
    int = 0) -> bool`: 1024x1024 PNG; world-cm coordinates scaled to
    fit all_points' bounding box with 5 percent margin and fixed
    aspect; faint dots for all machine points, small labeled markers
    for hits, a ring plus crosshair for the highlighted hit, axis
    labels in meters, north-up note, ASCII-only text. Deterministic
    for identical inputs (no timestamps in the image). Returns False
    (no file) when Pillow is unavailable.
- Tool integration: `get_satisfactory_context` gains `locate: str =
  ""`: reads the workspace's `mirror/latest_mirror.json` (read-only;
  absent mirror -> one line saying run the factory audit first),
  runs find_locations, appends a bounded "Locations:" section (top 5:
  label, kind, coordinates in meters, distance from origin), renders
  the map for the top hit to
  `mirror/location_<slug(query)>.png` inside the workspace
  (containment idiom), and appends the artifact path line. Schema
  growth: one string param.
- HUD delivery stays out of scope: the artifact path is the interface
  (the hud skill's markdown image rendering was verified 2026-07-01);
  note this in the response with a display hint line naming the
  artifact path in HUD markdown-image syntax (exclamation, brackets,
  path in parentheses; spelled out here to keep this log free of a
  literal link).

In scope: the new module, main.py/adapter wiring for the locate
param, tests: new `tests/test_map.py` (find_locations ranking/limit/
empty-query, render_map writes a deterministic PNG on a fixture
mirror (compare bytes across two renders), Pillow-absent degradation
via monkeypatched import failure, containment for hostile queries)
and append-only `tests/test_context_tool.py` (locate section renders
with a fixture mirror artifact; absent mirror explains; response
bounded).

Out of scope: typed transport links, station/route capacity, areas
(deferred with rationale: no layout data source until players assign
areas or a licensed base map lands), HUD posting itself, release
re-sync (SSP-REL-W04 after this packet as the roadmap finisher).

Expected files:

```text
skills/satisfactory_assistant/satisfactory_map.py        (new)
skills/satisfactory_assistant/satisfactory_adapter.py    (locate wiring)
skills/satisfactory_assistant/main.py                    (one param)
skills/satisfactory_assistant/tests/test_map.py          (new)
skills/satisfactory_assistant/tests/test_context_tool.py (append only)
```

Acceptance criteria:

1. find_locations ranking exact on fixtures; render_map deterministic
   PNG with all elements; Pillow-absent path degrades cleanly.
2. locate end-to-end: coordinates + artifact path in a bounded
   response; hostile query slugs contained; absent mirror explained.
3. Existing tests byte-unchanged (append-only exception); battery
   clean; schema growth one param.

### Implementation result / QC / Gate

Per the status lines above: accepted; real-save end-to-end verified.

## 2026-07-02 - SSP-REL-W04 - Release re-sync v0.5.0 (roadmap finisher)

- Roadmap phase: release engineering
- Owner: complete
- Status: `ACCEPTED` (delegated; QC verified 443/1 skip, parity 33/0,
  installer at 0.5.0 with 30 files, both new modules in the release)
- Attempt: 1
- Dispatched: 2026-07-02, agent `relw04-impl`
- ROADMAP COMPLETION NOTE: with this release, every implementable
  phase of `SatisfactorySkillPlan.md` (0 through 9) is delivered and
  accepted. Both section 15 definitions of done are MET: the first
  usable planner (2026-07-02, SSP-P3-W04) and the progressive master
  planner (five revisioned stages, capability gates only, reuse-aware
  expansion, every Phase 5 component producible, reproducible pace
  and recipe scenarios, optional save-derived actuals never required).
  Designed deferrals with unblocking conditions: mid-stage production
  gate checkpoints (need player tier state, save-derivable later),
  typed transport links / station capacity / areas (need layout data
  sources), miner purity and resource wells (mirror-side TODO),
  parser node_modules packaging decision. The live AppData install
  remains on the pre-planner version until the user chooses to
  install v0.5.0.
- Scope: same mechanical pattern as SSP-REL-W03 (precedent):
  RELEASE_FILES gains `satisfactory_actuals.py` and
  `satisfactory_map.py`; notes become `RELEASE_NOTES_v0.5.0.txt`
  (actuals-vs-plan audit via mode="audit" with a phase; locate with
  schematic map artifacts and HUD display hints; delete the v0.4.0
  root file); installer config version 0.5.0 with the files array
  updated; TESTER_README gains one paragraph on audit-with-phase and
  locate; regenerate, SHA parity (expect 33 files), node_modules
  absent, compileall both trees, suite 443/1 skip unchanged.

### Implementation result / QC / Gate

Pending.

## 2026-07-02 - SSP-P4-W01 - Master plan builder and stage transitions

- Roadmap phase: Phase 4 - Five-stage master plan (first packet)
- Owner: complete
- Status: `ACCEPTED` (delegated; joint suite gate passed 2026-07-02:
  310 passed, 1 pre-existing skip, alongside SSP-MNT-W01)
- Attempt: 1
- Dispatched: 2026-07-02, agent `p4w01-impl`, in parallel with
  SSP-MNT-W01 (zero file overlap: new pure module + new test file;
  MNT touches only main.py/satisfactory_adapter.py)
- Plan references: sections 2.3-2.4, 4.1-4.3 (design backward, build
  forward; capacity classification), 8.3 priority 3 (reuse), 12
  (Phase 4), 16 (guardrails)

### Implementation packet (Fable 5)

Objective:

- The pure five-stage engine: solve every Project Assembly phase under
  its own capability gates, classify module carry-forward between
  consecutive stages via stable node identities, and surface the
  backward final-demand envelope as informational reservations.

Design decisions (locked for this packet):

- Node identity across stages IS the recipe-keyed `node_id` from
  `schedule_machines` ("node_" + normalized recipe key): same recipe,
  same logical module. Area-level identity is Phase 9.
- Stages are solved independently (same recipe policy each stage);
  true reuse-aware objectives are Phase 5's lexicographic pass. A
  recipe present in stage N-1 but absent in stage N yields a
  "teardown warning" diagnostic on the transition (guardrail: prefer
  reuse; make violations visible, do not silently optimize them away).
- The final-demand envelope = per-recipe MAX machine_count across the
  current and all LATER stages; reported per stage as informational
  "future reservation" data, never as constraints.

In scope:

- New pure module `satisfactory_master_plan.py` (imports:
  progression, solver, plan models, docs types; no Wingman imports):
  - `build_master_plan(catalog, data, pace_multiplier=1.0,
    include_alternates=()) -> MasterPlanResult` where
    `MasterPlanResult` (frozen) carries `stages: tuple[StagePlan, ...]`
    (phases 1-5, revision 0 sentinel, solver_run_id ""),
    `transitions: tuple[StageTransition, ...]` (4 entries),
    `reservations: tuple[tuple[int, tuple[tuple[str, int], ...]], ...]`
    (phase -> (recipe key, future max machines) pairs), and
    `diagnostics: tuple[str, ...]` (aggregated, stage-prefixed).
    Per phase: snapshot -> demand -> solve_stage -> schedule_machines
    -> StagePlan (same assembly shape as the calculator tool's,
    including sources from imports). A non-optimal phase stops the
    build and returns what solved plus diagnostics naming the failing
    phase (status field on the result: "complete" or
    "stopped_at_phase_N").
  - `diff_stages(previous: StagePlan, current: StagePlan) ->
    StageTransition` classifying by node_id: reused (equal
    machine_count), expanded (count up), reduced (count down), added,
    retired; machine deltas encoded in the existing StageTransition
    tuple fields (reused_nodes, expanded_nodes, added_nodes,
    retired_nodes; reduced goes into expanded_nodes with a negative
    delta convention is NOT acceptable: put reduced ids in
    retired_nodes? NO: reduced is not retired. RESOLUTION: reduced
    node ids are appended to `expanded_nodes` entries as
    "node_x:-2"-style suffixed strings is ugly; instead encode every
    entry in all four tuples as "node_id:+delta" / "node_id:0" /
    "node_id:-delta" strings, documented in the function docstring;
    StageTransition's tuple[str, ...] fields permit this without a
    model change).
  - Teardown-warning diagnostics as designed above.
- New `tests/test_master_plan.py`:
  - Fixture Docs (two-phase bundled-data fixture allowed via a
    hand-built ProjectAssemblyData): shared chain expands (expanded
    with correct +delta), a phase-1-only recipe retires, a
    phase-2-only recipe is added, an unchanged node is reused with
    ":0"; reservations reflect the max across later stages;
    teardown warning fires when an allowed-set change flips a recipe.
  - Stopped-at-phase behavior: make phase 2 infeasible (part with no
    recipe), assert status "stopped_at_phase_2", stage 1 present,
    diagnostics name phase 2.
  - Determinism double-run.
  - Real-install gated test: full five-phase build at pace 1.0;
    assert status complete, five stages, four transitions, phase 2
    reuses or expands (never retires) every phase 1 node, total power
    strictly increases from phase 1 to phase 5, and zero
    teardown warnings with the standard policy.
- Update `TODO.md` status line for Phase 4 start (one line).

Explicitly out of scope: checkpoints (P4-W02), tool/persistence
wiring (P4-W02), reuse-aware objectives (Phase 5), release sync.

Expected files:

```text
skills/satisfactory_assistant/satisfactory_master_plan.py  (new)
skills/satisfactory_assistant/tests/test_master_plan.py    (new)
skills/satisfactory_assistant/TODO.md                      (one line)
```

Acceptance criteria:

1. Fixture transitions classify all five categories correctly with
   the documented delta encoding; reservations are exact.
2. Failure containment: an infeasible later phase preserves earlier
   stages and names the failure.
3. Real-install five-phase build completes with coherent transitions
   and monotonically increasing power.
4. All 302 pre-existing tests pass byte-unchanged; usual battery
   clean.

### Implementation result (Sonnet 5 agent, 2026-07-02)

- `satisfactory_master_plan.py` and 8 tests per packet, including the
  allowed-set-flip retirement scenario and failure containment.
  Real-install five-phase build: complete; nodes 7/17/28/53/68,
  machines 7/68/114/311/260, power 16.7/414.8/868.7/2906.6/2067.7 MW,
  transitions with zero retirements, zero teardown warnings, 4
  zero-power diagnostics (HadronCollider/Converter/QuantumEncoder,
  known unmodeled-power buildings).
- Deviation flagged, upheld at QC as a packet mis-specification: the
  "power strictly increases to phase 5" acceptance criterion is false
  against real data because baseline windows (1/2/4/8/16 h) grow
  faster than late-phase quantities, so per-minute rates legitimately
  drop into phase 5 (verified by the agent via demand-rate prints and
  independently sanity-checked: phase 5 has more nodes but a longer
  window). RULING: criterion redefined to what is invariant: node
  count strictly increases per phase, power always positive, phase 2
  never retires phase 1 nodes; the agent's test reflects this with an
  explanatory why-comment.
- Transient mid-run suite failures correctly attributed to the
  concurrent SSP-MNT-W01 refactor and re-verified clean afterward;
  good parallel-work hygiene.

### Quality control (Fable 5, 2026-07-02)

- Isolated verification: `test_master_plan.py` 8 passed; ruff clean on
  both new files; transition arithmetic cross-checked (per-phase
  category sums equal node counts); delta-encoding docstring present.
- Full-suite gate deferred until SSP-MNT-W01 lands (shared suite in
  motion); acceptance flips on that joint green run.

### Gate decision

- Decision: `QC_PASSED`; acceptance pending the joint suite gate.

## 2026-07-02 - SSP-MNT-W01 - main.py adapter split

- Roadmap phase: maintenance (tracked debt F-P8W01-5)
- Status: `ACCEPTED` (delegated)
- Attempt: 1
- Dispatched: 2026-07-02, agent `mntw01-impl`; baseline `main.py` at
  932 lines after SSP-P3-W05

### Implementation result (Sonnet 5 agent, 2026-07-02)

- New Wingman-free `satisfactory_adapter.py` (505 lines): pure
  helpers, `run_plan_calculation`, `run_factory_audit_pipeline`,
  lookup/plan-status builders, docs-missing formatter. `main.py` down
  to 520 lines: Skill class, three thin @tool wrappers, config
  accessors, delegating bound methods. Zero test edits; suite green.

### Quality control (Fable 5, 2026-07-02)

- Joint gate with SSP-P4-W01: 310 passed, 1 pre-existing skip; ruff
  and compileall clean; line counts verified (932 -> 520).
- RULING on the 500-line target: 520 accepted. The remaining overage
  is pinned by two behavior contracts the packet itself protects: the
  @tool docstring Args sections are parsed into the LLM-facing schema
  (byte-identical preservation required), and duck-typed test stubs
  make new self-method indirections an AttributeError (the attempted
  `_discover_docs` consolidation provably broke 13 tests and was
  correctly reverted). F-P8W01-5 is closed as satisfied: a 44 percent
  reduction with fidelity intact beats a numeric target hit by
  schema-visible trimming.
- Deviation accepted: `_lookup_lines`/`_plan_status_lines` stay as
  thin bound methods because tests bind them from the class object;
  monkeypatch targets (`main.discover_docs` etc.) kept resolvable at
  their contracted dotted paths.

### Gate decision

- Decision: `QC_PASSED`; `ACCEPTED` under delegated G3. F-P8W01-5
  closed.
- Next action: SSP-REL-W01 dispatched (packet below supersedes the
  earlier sketch).
- Objective: bring `main.py` back under the 500-line guidance by moving
  the plan-pipeline body of `calculate_satisfactory_plan` and the
  audit body into a new sibling `satisfactory_adapter.py` (functions
  taking explicit inputs: catalog, workspace, config values; NO
  Wingman imports so they stay unit-testable), leaving the three
  @tool methods in `main.py` as thin validated wrappers (tool schemas
  and all response strings byte-identical, proven by the existing
  adapter tests passing unchanged except import-path fallout, which
  requires a stop-and-report if any test hardcodes main-module
  internals).
- Acceptance: `main.py` <= 500 lines; all responses byte-identical
  (existing tool tests green unchanged); tool count still 3; usual
  verification battery.

## 2026-07-02 - SSP-REL-W01 - release_version sync

- Roadmap phase: release engineering (deferred since SSP-P8-W01)
- Status: `ACCEPTED` (delegated)
- Attempt: 2
- Dispatched: 2026-07-02, agent `relw01-impl`; SSP-MNT-W01 landed, the
  release ships the refactored layout

### Result and QC summary (Fable 5, 2026-07-02)

- Attempt 1: `update_release.py` modernized (24 runtime files, data/
  and tools/save_parser dirs with a node_modules ignore filter),
  release regenerated with 0 SHA mismatches, v0.2.0 release notes,
  refreshed TESTER_README, installer version bumped. Agent flagged the
  stale installer "files"/"dirs" arrays and the zero-byte stray files.
- Attempt 2 (authorized scope expansion): installer manifest arrays
  synced to the actual 24-file + 2-dir release (the attempt-1 "23" was
  the agent's own miscount, corrected in its report); 12 zero-byte
  shell-artifact strays deleted from the skill root only, each
  size-verified first; repo-root strays untouched per the skills-only
  boundary.
- Independent verification: 310 passed, 1 pre-existing skip; ruff and
  compileall clean; zero-byte count at skill root now 0; release data/
  and tools/save_parser contents confirmed correct.
- v0.2.0 is ready to install whenever the user chooses; the live
  AppData copy was not touched.
- Objective: modernize `update_release.py` and regenerate
  `release_version/` to match the accepted source tree.
- Scope sketch (full packet written at dispatch time):
  - `update_release.py`: extend `RELEASE_FILES` with every runtime
    module added since June 17 (install, docs, dataset, progression,
    solver, store, plan_models, reports, mirror, save_parser, adapter
    after MNT-W01), add directory support for `data/` and
    `tools/save_parser/` (script + package.json only, node_modules
    stays unbundled pending the parser packaging decision), keep the
    containment guard.
  - Regenerate the release folder; SHA-256 parity check per file
    against source; `python -m compileall` the release copy.
  - Bump `RELEASE_NOTES` (v0.2.0: planner milestone, three tools,
    SQLite store, save-derived mirror) and refresh `TESTER_README.md`
    tool descriptions.
  - NO git commit (user manages the skill release flow); the live
    AppData install is NOT touched (user decision when to update).

## 2026-07-02 - SSP-P3-W05 - Context enrichment and config modernization

- Roadmap phase: Phase 3 - Phase 1 deterministic planner (wrap-up)
- Owner: complete
- Status: `ACCEPTED` (delegated)
- Attempt: 2
- Dispatched: 2026-07-02, agent `p3w05-impl`
- Milestone: roadmap Phase 3 is COMPLETE (solver core, capability
  completeness, machine schedules and power, calculator tool with
  audit fold-in, context enrichment and config modernization all
  `ACCEPTED`)
- Plan references: section 10 item 1 (context: plans, stages,
  diagnostics, bounded game-data lookup), token budgets in section 10;
  retires tracked debt F-W03-5 (hard-coded Phase 4 quantities)

### Implementation packet (Fable 5)

Objective:

- Finish the Phase 3 tool surface: the context tool reports persisted
  plan state and answers bounded game-data lookups; the config prompt
  and reference stub stop hard-coding Phase 4 data now that bundled,
  validated data exists; plan responses show display names.

In scope:

- `main.py`, `get_satisfactory_context`:
  - New optional param `lookup: str = ""`: when set, append a bounded
    lookup section using `satisfactory_dataset.lookup_items` and
    `lookup_recipes` (cap 5 each, per plan section 10); docs missing
    -> one short "lookup unavailable" line; keep the whole response
    inside the existing `format_context` budget by passing the lookup
    lines as extra header/footer lines through the existing budget
    mechanism (do not bypass it).
  - Plan-status section: when the workspace store has stage revisions
    for plan "master", add up to 5 compact lines (phase, latest
    revision, machine total, power total) sourced via `SaveStore`
    (`list_stage_revisions` + `load_stage_plan` latest); absent store
    or no plans -> no section, no error.
  - Update the tool description minimally to mention lookups.
- `satisfactory_reference.py`: replace the hard-coded Phase 4 lines
  with data derived from `load_project_assembly_phases()` (same
  function name and signature, same compact output shape: only the
  data source changes; handles a missing/corrupt bundled file by
  returning no lines). If `tests/test_reference.py` asserts exact
  strings incompatible with data-driven output, STOP and report for a
  ruling; if it asserts content (part names/quantities), it should
  pass unchanged since the bundled data matches.
- `satisfactory_reports.py`: `format_plan_response` gains optional
  `display_names: dict[str, str] | None = None`; demand and import
  lines use the mapped name when present (class key normalized for
  the mapping lookup), class name otherwise. `main.py` passes the map
  built from the demand set and catalog.
- `default_config.yaml`:
  - Prompt: replace the hard-coded Phase 4 quantity sentences with a
    short paragraph saying the skill can calculate Project Assembly
    phase plans (machines, power, inputs) for the active save via its
    tools, that phase requirements come from verified bundled data,
    and keep the active-save-only and no-other-saves language intact.
  - `discovery_keywords`: add `plan factory`, `calculate plan`,
    `phase plan`, `power budget`, `machines needed`, `how many
    machines`.
  - No new custom properties; `api_version: 3` untouched.
- Tests: new `tests/test_context_tool.py` (stub pattern): lookup param
  renders capped results and the unavailable line; plan-status section
  appears after a persisted plan and is absent for a fresh workspace;
  response stays within budget. Additions to `tests/test_reports.py`
  are NOT allowed (leave that file); instead put the display-name
  formatter test in `tests/test_plan_tool.py` as an append-only
  addition. `tests/test_reference.py` must pass unchanged (or
  stop-and-report).

Explicitly out of scope: solver/store/progression changes, the
`main.py` size refactor (its own packet), `release_version/` sync
(next packet), HUD work.

Expected files:

```text
skills/satisfactory_assistant/main.py                     (context tool)
skills/satisfactory_assistant/satisfactory_reference.py   (data-driven)
skills/satisfactory_assistant/satisfactory_reports.py     (names param)
skills/satisfactory_assistant/default_config.yaml         (prompt/keywords)
skills/satisfactory_assistant/tests/test_context_tool.py  (new)
skills/satisfactory_assistant/tests/test_plan_tool.py     (append only)
```

Acceptance criteria:

1. Context tool answers lookups (capped 5+5) and shows persisted plan
   status, all inside the existing response budget.
2. No hard-coded phase quantities remain anywhere outside
   `data/project_assembly_phases.json` (grep evidence required):
   F-W03-5 retired.
3. Plan responses show display names when resolvable.
4. All pre-existing tests pass byte-unchanged except the explicitly
   allowed append-only files; pytest, ruff, compileall clean.
5. Tool count remains exactly 3; schema growth limited to the one new
   optional string param and description tweak.

### Implementation result (Sonnet 5 agent, 2026-07-02, attempt 1)

- Context tool: `lookup` param with capped item/recipe sections and an
  unavailable line; plan-status section reading `planning.sqlite3`
  read-only (guards on existence, never creates); both folded through
  `format_context`'s budget, not around it. Reference module now
  data-driven from the bundled phases (F-W03-5 retired);
  `test_reference.py` passes byte-unchanged. `format_plan_response`
  display-name mapping threaded through; config prompt and keywords
  modernized; 11 new tests.
- Correctly flagged, not edited: one pre-existing happy-path assertion
  (`"Desc_Plate_C" in result`) collides with the chartered
  display-name change.
- Correct rigor on criterion 2: identified ripgrep glob anchoring in
  the packet's own evidence command and reran with proper `**` globs
  (zero hits outside the two explicitly-allowed locations).

### Quality control (Fable 5, 2026-07-02, attempt 1)

- Independent verification: 301 passed, 1 failed (exactly the flagged
  assertion), 1 pre-existing skip; ruff clean.
- RULING (fourth of its category, same rationale): the assertion's
  intent is "the demand item appears in the response"; the raw class
  string is the formatting detail the packet changed. Authorized:
  replace that single assertion with the display-name equivalent plus
  a ruling reference comment. Option (b) (restricting display names to
  imports) rejected: it would trade user-facing quality to preserve a
  string literal.

### Gate decision (attempt 1)

- Decision: `CHANGES_REQUESTED` (the single authorized assertion
  update).
- Next owner: Sonnet 5 agent `p3w05-impl`, attempt 2.

### Quality control attempt 2 (Fable 5, 2026-07-02)

- The authorized single-line change is on disk with the ruling
  comment; independent verification: 302 passed, 1 pre-existing skip;
  ruff and compileall clean.

### Gate decision (attempt 2)

- Decision: `QC_PASSED`; `ACCEPTED` under delegated G3. Phase 3
  complete.
- Baseline recorded for SSP-MNT-W01: `main.py` is at 932 lines.

## 2026-07-01 - SSP-P2-W02 - Workspace backend swap to SQLite

- Roadmap phase: Phase 2 - Typed master-plan store
- Owner: complete
- Status: `ACCEPTED` (delegated)
- Attempt: 2
- Dispatched: 2026-07-01, agent `p2w02-impl`; SSP-P1-W04 `ACCEPTED`,
  `main.py` overlap cleared
- Milestone: deferred finding F-W03-3 (non-atomic JSONL rewrites, a
  standing data-loss risk since SSP-P0-W03) is RETIRED: all journal
  writes are now transactional SQLite
- Plan references: sections 9 (persistence), 12 (Phase 2), 16 (do not
  delete or rewrite legacy files during migration); retires F-W03-3

### Implementation packet (Fable 5)

Objective:

- Swap `SaveWorkspace`'s persistence backend from JSONL files to the
  accepted `SaveStore`, preserving `SaveWorkspace`'s public API exactly
  so `main.py`, `format_context`, the mirror artifacts, and all existing
  workspace tests keep working, and wiring one-time idempotent legacy
  import on workspace open.

In scope:

- `satisfactory_workspace.py`: `SaveWorkspace` keeps its constructor,
  `ensure()`, `add_item`, `set_status_for_kind`, `update_flow`,
  `summary`, and containment guards; internally it opens
  `planning.sqlite3` in the workspace dir via `SaveStore` and, on first
  open per workspace, runs `import_jsonl` over the five legacy files
  (never modifying them). JSONL append writes stop; reads come from the
  store. Record id generation, prefixes, and summary shaping stay
  byte-compatible. Mirror artifacts and containment logic unchanged.
- `main.py`: only if an adapter seam requires it (constructor call
  sites should not change); no tool schema changes.
- Tests: all existing `test_workspace.py` and `test_config_coercion.py`
  behavioral tests must pass UNCHANGED (they are the compatibility
  contract); add store-backed tests: legacy JSONL auto-import happens
  once and is idempotent across reopens; new records persist across
  reopen; legacy files byte-identical after import and never appended
  to again; a workspace with no legacy files works fresh.
- Store lifecycle: open per operation or held per SaveWorkspace
  instance with explicit close; document the choice (workspace objects
  are short-lived per tool call today, per `_workspace_for`).

Explicitly out of scope:

- Plan-model tables and typed models (SSP-P2-W03).
- Exports, revisions, solver-run persistence.
- Deleting/renaming legacy JSONL files.
- `release_version/` sync, config or tool-schema changes.

Acceptance criteria:

1. Every pre-existing workspace/coercion test passes without edits.
2. Legacy import is one-time and idempotent; legacy files are
   byte-identical afterward and never written again.
3. New records survive workspace reopen (real durability, not JSONL
   append).
4. Token budgets, summary output shape, and containment behavior are
   unchanged (existing tests prove it).
5. Full suite, ruff, compileall clean; no bare print; ASCII only.

Known risks:

- `test_workspace.py` may poke JSONL files directly in some tests; if a
  test asserts on raw file contents rather than behavior, the
  implementer must flag it (do NOT edit tests silently; report which
  tests constitute a storage-format assertion so QC can rule).

### Implementation result (Sonnet 5 agent, 2026-07-01, attempt 1)

- `satisfactory_workspace.py` internals swapped to `SaveStore` over
  `planning.sqlite3`; `_append`/`_rewrite` removed; `_open_store()`
  runs the hash-gated legacy import on every open (deviation, accepted:
  two pre-existing tests write legacy files after construction and
  expect the next read to see them; the content-hash gate keeps repeat
  imports free); store opened/closed per operation (documented:
  short-lived instances, Windows handle cleanup); public API and all
  module helpers unchanged; `main.py` needed no changes.
- New `tests/test_workspace_store.py`: 8 durability/idempotency/
  isolation tests.
- Flagged per the packet's stop-and-report rule, not edited:
  `test_workspace.py::test_malicious_title_stays_in_workspace` fails
  because it asserts `add_item` produces a `*.jsonl` file, a raw
  storage-format assertion the accepted design removes.

### Quality control (Fable 5, 2026-07-01, attempt 1)

- Independent verification: 199 passed, 1 failed (only the flagged
  test), 1 pre-existing skip; ruff and compileall clean; reviewed the
  reworked `SaveWorkspace` internals line-by-line: API preserved,
  ValueError semantics kept where tests demand them, lifecycle sound.
- RULING on the flagged test: its stated intent ("a title with
  traversal characters must not affect where data is written") is
  behavioral; its assertion mechanism (globbing for `*.jsonl`) is a
  storage-format detail that the accepted architecture deliberately
  eliminated. The repository's fix-the-code-not-the-tests rule guards
  against gaming failures, not against reviewer-authorized updates that
  preserve intent across an accepted architectural change. Authorized
  correction: replace that one test's assertions to (a) prove no file
  was created at or toward the traversal target, (b) prove every file
  created lives inside the workspace directory, (c) prove the hostile
  title round-trips as plain data in `summary()`. No other test may be
  touched.

### Gate decision (attempt 1)

- Decision: `CHANGES_REQUESTED` (apply the authorized test replacement
  above; nothing else).
- Next owner: Sonnet 5 agent `p2w02-impl`, attempt 2.

### Implementation result attempt 2 (Sonnet 5 agent, 2026-07-01)

- Applied the authorized replacement to exactly one test:
  `test_malicious_title_stays_in_workspace` now asserts no traversal
  escape (`tmp_path / "etc"` absent; every file under `ws.dir`
  contained by resolved-parent check), data landed inside the
  workspace, and the hostile title round-trips as inert data through
  `summary()`. No other file changed in this step.

### Quality control attempt 2 (Fable 5, 2026-07-01)

- Independent verification: 200 passed, 1 pre-existing skip; ruff and
  compileall clean. The replaced test is strictly stronger than the
  original (the original never checked the traversal target or the
  title round-trip).

### Gate decision (attempt 2)

- Decision: `QC_PASSED`; `ACCEPTED` under delegated G3.
- Next action: SSP-P2-W03 (typed plan models and plan tables) drafted
  and dispatched below.

## 2026-07-01 - SSP-P1-W04 - Memoized dataset loading and bounded lookup

## 2026-07-01 - SSP-P1-W04 - Memoized dataset loading and bounded lookup

- Roadmap phase: Phase 1 - Docs and progression dataset (final packet)
- Owner: complete
- Status: `ACCEPTED` (delegated)
- Attempt: 2
- Dispatched: 2026-07-01, agent `p1w04-impl`; section 6.3 amendment
  approved by the user on 2026-07-01
- Milestone: roadmap Phase 1 (Docs and progression dataset) is COMPLETE
  with this acceptance (W01 discovery, W02 schematics, W03 progression,
  W04 dataset layer all `ACCEPTED`)
- Baseline revision: `15d0e64`, dirty working tree; SSP-P1-W01 through
  W03 `ACCEPTED`
- Plan references: `SatisfactorySkillPlan.md` sections 6.3 (cache and
  validation, amended below), 10 (lookup response limits), 12 (Phase 1)

### Plan amendment (approved by the user 2026-07-01)

Section 6.3 specifies an atomic, versioned on-disk dataset cache. That
design assumed an expensive Docs parse. Measured on this machine
2026-07-01 against the live 10.6 MB Docs file: full normalized parse
including schematics takes 58 ms; SHA-256 of the whole file takes 8 ms.
Reading and deserializing a compact JSON cache would cost a comparable
amount, so a disk cache buys roughly nothing while adding serialization
round-trips for four dataclass families, atomic-write handling, cache
invalidation, and corruption recovery: a standing bug surface with no
measurable benefit. Amendment: replace the on-disk cache with in-process
memoization keyed by the Docs file signature, keeping section 6.3's
signature validation (size, high-resolution mtime, SHA-256 on metadata
change) and provenance recording. If a future game patch makes parsing
expensive, the disk cache can be revisited with evidence.

### Implementation packet (Fable 5)

Objective:

- Stop re-parsing the Docs file on every tool call via signature-checked
  in-process memoization with provenance, and provide the bounded lookup
  helpers the Phase 3 context tool will expose (at most five matches,
  per plan section 10).

In scope:

- New pure module
  `skills/satisfactory_assistant/satisfactory_dataset.py` (stdlib plus
  `satisfactory_docs` imports only):
  - Frozen dataclass `DatasetInfo`: `docs_path` (str), `size_bytes`
    (int), `mtime_ns` (int), `sha256` (str, hex), `parse_ms` (float),
    `loaded_at` (ISO string), `item_count`, `recipe_count`,
    `building_count`, `schematic_count` (ints).
  - `get_docs_catalog(docs_path: Path) -> tuple[DocsCatalog,
    DatasetInfo]` with a module-level memo (dict keyed by resolved path
    string, capped at 4 entries, oldest evicted):
    - Memo hit requires equal `size_bytes` and `mtime_ns`.
    - On metadata mismatch, compute SHA-256; if it equals the memoized
      hash, reuse the catalog and refresh the stored metadata (file was
      touched, not changed); otherwise re-parse via `load_docs_catalog`.
    - First load computes signature and parse time, stores both.
    - File read/stat errors propagate as the loader's existing
      exceptions; memo never masks them and never caches failures.
  - `clear_dataset_memo()` for tests.
  - Bounded lookup helpers (pure, no tool exposure in this packet):
    - `lookup_items(catalog, query, limit=5) -> tuple[dict, ...]`
    - `lookup_recipes(catalog, query, limit=5) -> tuple[dict, ...]`
    - Case-insensitive matching against display name and normalized
      class key; ranking: exact display-name match first, then prefix,
      then substring; alphabetical within a rank; `limit` clamped to
      1..5. Empty or whitespace query returns ().
    - Item result dict: `item`, `class`, `form`.
    - Recipe result dict: `recipe`, `class`, `duration_seconds`,
      `inputs_per_min` and `outputs_per_min` (item display name to rate
      at 100 percent clock, fluids in m3), `produced_in` (tuple),
      `alternate` (bool via `catalog.is_alternate_recipe`).
- `main.py`: in `audit_satisfactory_factory`, replace the direct
  `load_docs_catalog(docs_file)` call with
  `catalog, dataset_info = get_docs_catalog(docs_file)` (import per the
  existing sibling style). Emit one server-only diagnostic via
  `self._diag` when a parse actually happened (`parse_ms` present in
  this load), so cache behavior is observable in server logs. No tool
  schema changes, no new tools.
- New `tests/test_dataset.py`:
  - Memo hit: two loads of an unchanged fixture Docs file parse once
    (monkeypatch a counter around `load_docs_catalog`).
  - Invalidation: changing file content (size or mtime_ns + different
    sha) re-parses; equal-content touch (mtime changes, sha equal)
    does NOT re-parse and refreshes metadata.
  - Memo cap: fifth distinct path evicts the oldest.
  - Failure transparency: missing file raises through; a failed load is
    not memoized (subsequent valid load succeeds).
  - Lookup: ranking order (exact beats prefix beats substring), limit
    clamped to 5 even when asked for more, empty query returns (),
    alternate flag correct, fluid rates divided by 1000.
  - Gated real-install test: `get_docs_catalog` twice on the live Docs
    parses once and counts match a direct `load_docs_catalog`; lookup
    for "Steel Ingot" returns the item and at least one producing
    recipe within the cap.

Explicitly out of scope:

- On-disk cache (amended away, see above).
- Exposing lookup through any tool (Phase 3 folds it into
  `get_satisfactory_context` per plan section 10).
- Threading/multiprocessing concerns (Wingman skills run on one event
  loop; document the assumption in the module docstring).
- `release_version/` sync (still deferred), config changes, and any
  change to discovery, progression, mirror, or workspace modules.

Expected files:

```text
skills/satisfactory_assistant/satisfactory_dataset.py  (new)
skills/satisfactory_assistant/main.py                  (audit call site)
skills/satisfactory_assistant/tests/test_dataset.py    (new)
```

Data contracts and migration/configuration effects:

- New `DatasetInfo` dataclass and lookup result dict shapes as above; no
  persistence, config, or tool-schema changes. No migration.

Acceptance criteria:

1. Unchanged file: exactly one parse across repeated loads; observable
   via the test counter.
2. Content change re-parses; touch-only change does not; failures are
   never cached.
3. Lookup ranking, caps (hard maximum 5), empty-query, alternate flag,
   and fluid-unit behavior all hold.
4. Audit tool behavior is unchanged except for faster repeat calls and
   the one server-only diagnostic on real parses.
5. All pre-existing tests pass unchanged; gated real-install test passes
   on this machine, skips cleanly elsewhere.
6. `python -m pytest`, `python -m ruff check`, `python -m compileall`
   clean; no bare `print(`; no em-dashes; ASCII only.

Required verification:

```text
python -m pytest skills/satisfactory_assistant/tests -q -p no:cacheprovider
python -m ruff check skills/satisfactory_assistant
python -m compileall -q skills/satisfactory_assistant
```

Cross-platform, token, persistence, and release-parity concerns:

- Pure module; `mtime_ns` used for resolution (Windows FAT/exFAT mtime
  granularity is why sha backs up the metadata check). No token impact.
  No persistence. Release parity deferred as before.

Known risks, assumptions, and blocking questions:

- Assumption: single event loop, no concurrent first-load races worth
  guarding (documented in module docstring).
- Risk: memoized catalog is shared mutable-by-reference; DocsCatalog is
  effectively read-only by design, and all its dataclasses are frozen.
- Blocking: user approval of the section 6.3 amendment (this packet must
  not dispatch before that).

### Implementation result (Sonnet 5 agent, 2026-07-01, attempt 1)

- Delivered without a G1 handover report (agent idled); QC reconstructed
  the result from the repository per section 11.7.
- New `satisfactory_dataset.py`: signature-memoized `get_docs_catalog`
  (size/mtime_ns fast path, SHA-256 tiebreak with touch-only refresh,
  FIFO cap 4, failures never memoized, `parse_ms` set only on real
  parses), `DatasetInfo`, `clear_dataset_memo`, and ranked capped
  `lookup_items`/`lookup_recipes`.
- `main.py`: audit tool swapped to `get_docs_catalog` with a server-only
  parse diagnostic gated on `parse_ms`; `load_docs_catalog` import
  removed.
- New `tests/test_dataset.py`: 16 tests; full suite 191 passed,
  1 pre-existing skip.

### Quality control (Fable 5, 2026-07-01, attempt 1)

Independent verification:

- `python -m pytest skills/satisfactory_assistant/tests -q -p no:cacheprovider`
  -> 191 passed, 1 skipped
- `python -m ruff check skills/satisfactory_assistant` -> All checks passed
- `python -m compileall -q skills/satisfactory_assistant` -> passed
- Line-by-line review of `satisfactory_dataset.py` and the `main.py`
  call site: memo semantics, eviction, touch-refresh, diagnostic gating,
  and lookup ranking all match the packet.

Findings:

- F-P1W04-1 (Medium): `lookup_items` and `lookup_recipes` iterate
  `catalog._items` / `catalog._recipes`, private attributes of another
  module, suppressed with `# noqa: SLF001` comments. This violates the
  repository rule "no suppression comments" outright, couples the
  dataset module to `DocsCatalog` internals, and the noqa tags are dead
  weight besides (SLF is not in the project's ruff select). Required
  correction: add public read-only accessors to `DocsCatalog`
  (`all_items() -> tuple[ItemDescriptor, ...]` and `all_recipes() ->
  tuple[Recipe, ...]` returning the values), use them in the lookups,
  delete both noqa comments. Note: this adds `satisfactory_docs.py` to
  the packet's changed-file set, an approved expansion.

### Gate decision (attempt 1)

- Decision: `CHANGES_REQUESTED` (F-P1W04-1).
- Next owner: Sonnet 5 agent `p1w04-impl`, attempt 2.

### Implementation result attempt 2 (Sonnet 5 agent, 2026-07-01)

- `DocsCatalog.all_items()` / `all_recipes()` public accessors added
  beside the existing getters; both lookup loops switched to them; both
  `noqa: SLF001` comments deleted; one new accessor test.
- Agent flagged (correctly, without acting): pre-existing
  `# noqa: E402` on all sibling imports in `main.py` and pre-existing
  `# type: ignore[arg-type]` in the coercion helpers.

### Quality control attempt 2 (Fable 5, 2026-07-01)

- Independent verification: 192 passed, 1 pre-existing skip; ruff and
  compileall clean; zero `noqa` occurrences in
  `satisfactory_dataset.py`; accessors and call sites confirmed at
  `satisfactory_docs.py:174/181` and `satisfactory_dataset.py:200/238`.
- Ruling on the flagged pre-existing suppressions: the `noqa: E402`
  sibling-import tags are required by the Wingman skill loader pattern
  (sys.path bootstrap before sibling imports) and predate this
  workstream; the `type: ignore[arg-type]` tags in the coercion
  helpers likewise predate it. Both are accepted as established
  convention and recorded as tracked debt for a dedicated cleanup
  packet if ever worth the churn; they are not new suppressions and no
  new suppressions are permitted going forward.

### Gate decision (attempt 2)

- Decision: `QC_PASSED`; `ACCEPTED` under delegated G3.
- Next action: dispatch SSP-P2-W02 (workspace backend swap), which was
  queued behind this packet's `main.py` overlap.

## 2026-07-01 - SSP-P1-W03 - Project Assembly data and capability snapshots

- Roadmap phase: Phase 1 - Docs and progression dataset
- Owner: complete
- Status: `ACCEPTED`
- Attempt: 2
- Dispatched: 2026-07-01, agent `p1w03-impl`; SSP-P1-W02 `ACCEPTED`,
  W02 APIs landed exactly as this packet assumes
- Baseline revision: `15d0e64`, dirty working tree
- Plan references: `SatisfactorySkillPlan.md` sections 2.2 (pace), 2.3
  (demand derivation), 2.4 (stage rules), 5.1 (module table:
  `satisfactory_progression.py`), 6.2 including the approved 2026-07-01
  amendment (bundled phase data), 12 (Phase 1)

### Implementation packet (Fable 5)

Objective:

- Create the progression layer the Phase 3 planner will consume: bundled,
  provenance-tagged Project Assembly phase data validated against the
  player's Docs, phase demand derivation with the pace multiplier, and
  capability gate snapshots built from W02 schematic data.

Ground truth verified 2026-07-01:

- All 12 Space Elevator part descriptors exist in the installed Docs:
  `Desc_SpaceElevatorPart_1_C` Smart Plating through
  `Desc_SpaceElevatorPart_12_C` AI Expansion Server.
- Phase requirements from the official wiki
  (https://satisfactory.wiki.gg/wiki/Space_Elevator, retrieved
  2026-07-01), consistent with the Phase 4 quantities already shipped in
  this skill's config prompt:
  - Phase 1 "Distribution Platform", unlocks tiers 3-4:
    50 Smart Plating (part 1).
  - Phase 2 "Construction Dock", unlocks tiers 5-6: 1000 Smart Plating
    (1), 1000 Versatile Framework (2), 100 Automated Wiring (3).
  - Phase 3 "Main Body", unlocks tiers 7-8: 2500 Versatile Framework
    (2), 500 Modular Engine (4), 100 Adaptive Control Unit (5).
  - Phase 4 "Propulsion", unlocks tier 9: 500 Assembly Director System
    (7), 500 Magnetic Field Generator (6), 250 Thermal Propulsion Rocket
    (8), 100 Nuclear Pasta (9).
  - Phase 5 "Assembly", unlocks launch: 1000 Nuclear Pasta (9),
    1000 Biochemical Sculptor (10), 256 AI Expansion Server (12),
    200 Ballistic Warp Drive (11).
- Baseline production windows from plan section 2.2: 1/2/4/8/16 hours
  for phases 1-5; `pace_multiplier` valid range 1.0 through 3.0.
- Tier availability rule (plan 2.4, "do not use technology unlocked by
  completing the upcoming phase"): planning phase 1 allows tiers 0-2;
  phase 2 allows 0-4; phase 3 allows 0-6; phase 4 allows 0-8; phase 5
  allows 0-9. Derived from base tiers 0-2 plus each prior phase's
  unlocked tiers; must be data-driven from the bundled file, not
  hard-coded in logic.

In scope:

- New bundled data file
  `skills/satisfactory_assistant/data/project_assembly_phases.json`:
  - Top level: `schema_version` (1), `provenance` (source URL, retrieval
    date 2026-07-01, note that quantities are cross-checked in-game at
    G3), `base_tiers` ([0, 1, 2]), `phases` list.
  - Each phase: `phase` (1-5), `name`, `window_hours_baseline`
    (1/2/4/8/16), `unlocks_tiers` (list, empty for phase 5),
    `parts` list of {`item_class`, `display_name`, `quantity`} using the
    exact quantities and `Desc_SpaceElevatorPart_N_C` classes above.
- New pure module
  `skills/satisfactory_assistant/satisfactory_progression.py` (no
  Wingman imports, stdlib only):
  - Frozen dataclasses: `PhasePart` (item_class, display_name,
    quantity), `PhaseDefinition` (phase, name, window_hours_baseline,
    unlocks_tiers, parts), `PhaseDemand` (item_class, display_name,
    quantity, required_rate_per_minute), `PhaseDemandSet` (phase, name,
    pace_multiplier, window_hours, demands tuple), `CapabilitySnapshot`
    (upcoming_phase, max_tier, purchased_schematics frozenset,
    allowed_recipes frozenset).
  - `load_project_assembly_phases(path: Path | None = None) ->
    tuple[PhaseDefinition, ...]`: defaults to the bundled file next to
    the module; structural validation raises `ValueError` with a clear
    message on: phases not exactly 1-5 each once, non-positive
    quantities, empty parts, unknown schema_version. OSError-guarded
    read.
  - `validate_phases_against_docs(phases, catalog) -> tuple[str, ...]`:
    returns human-readable diagnostics (empty tuple when clean); every
    `item_class` must resolve via `catalog.item(...)`. Diagnostics, not
    exceptions: a patch mismatch must degrade, not crash.
  - `derive_phase_demand(phases, phase: int, pace_multiplier: float =
    1.0) -> PhaseDemandSet`: `window_hours = baseline *
    pace_multiplier`; `required_rate_per_minute = quantity /
    (window_hours * 60)`. Raise `ValueError` for unknown phase or
    pace outside 1.0-3.0 inclusive (never silently clamp, per plan 2.2).
  - `available_tiers_for_phase(phases, upcoming_phase: int, base_tiers)
    -> frozenset[int]`: base tiers plus `unlocks_tiers` of all phases
    strictly below `upcoming_phase`.
  - `build_capability_snapshot(catalog, phases, upcoming_phase: int,
    extra_schematics: tuple[str, ...] = (), include_alternates:
    tuple[str, ...] = ()) -> CapabilitySnapshot`: purchased schematics =
    all EST_Milestone schematics whose tech_tier is in the available
    tiers, plus normalized `extra_schematics`; allowed_recipes = union
    of their `unlocked_recipes`, plus normalized `include_alternates`
    recipe keys; recipes flagged by `catalog.is_alternate_recipe` are
    EXCLUDED unless explicitly present in `include_alternates` (plan
    2.4: alternates require evidence or opt-in). Document the assumption
    that EST_Tutorial/EST_Custom/EST_MAM unlocks are out of scope until
    a later packet.
- New `tests/test_progression.py`:
  - Loader: bundled file loads; fixture with duplicate phase, missing
    phase, zero quantity, or bad schema_version raises ValueError.
  - Docs validation: fixture catalog missing one part class yields
    exactly one diagnostic naming that class; clean catalog yields none.
  - Demand math (exact assertions): phase 1 at pace 1.0 -> Smart
    Plating 50/60 per minute; phase 4 at pace 1.0 -> Assembly Director
    System 500/480 per minute; phase 4 at pace 3.0 -> one third of
    that; pace 0.9 and 3.1 raise; phase 6 raises.
  - Tiers: upcoming phase 1 -> {0,1,2}; phase 3 -> {0..6}; phase 5 ->
    {0..9}.
  - Snapshot: fixture catalog (W02-style) with a tier-2 milestone, a
    tier-5 milestone, and an EST_Alternate schematic; upcoming phase 1
    includes only the tier-2 milestone's recipes; upcoming phase 3
    includes both milestones' recipes; the alternate's recipe appears
    only when passed in `include_alternates`.
  - Real-install integration test (skip when no Docs): bundled file
    validates against the real catalog with zero diagnostics.
- `data/` is a new directory inside the skill; keep the JSON ASCII.

Explicitly out of scope:

- Solver, SQLite store, dataset caching, bounded lookup tool.
- Any change to `main.py`, tools, config, `satisfactory_reference.py`
  (rewiring the reference stub to this data file is a later packet),
  `satisfactory_docs.py` beyond what W02 already delivers, or
  `release_version/`.
- MAM/Tutorial/Custom schematic unlock semantics.

Expected files:

```text
skills/satisfactory_assistant/data/project_assembly_phases.json  (new)
skills/satisfactory_assistant/satisfactory_progression.py        (new)
skills/satisfactory_assistant/tests/test_progression.py          (new)
```

Data contracts and migration/configuration effects:

- New bundled data file and pure module; no persistence, config, or
  tool-schema changes. No migration.

Acceptance criteria:

1. Bundled JSON matches the verified quantities and class names above,
   with provenance fields present.
2. Loader validation raises on structural defects; Docs cross-validation
   returns diagnostics instead of raising.
3. Demand math is exact, pace bounds are enforced by raising, and the
   window scales linearly with pace.
4. Tier availability and snapshots implement the "upcoming phase" rule;
   alternates are opt-in only.
5. All pre-existing tests pass unchanged; real-install validation test
   passes on this machine and skips cleanly elsewhere.
6. `python -m pytest`, `python -m ruff check`, `python -m compileall`
   clean; no bare `print(`; no em-dashes; ASCII only.

Required verification:

```text
python -m pytest skills/satisfactory_assistant/tests -q -p no:cacheprovider
python -m ruff check skills/satisfactory_assistant
python -m compileall -q skills/satisfactory_assistant
```

Cross-platform, token, persistence, and release-parity concerns:

- Pure module + static data; no platform code, no token impact, no
  persistence. Release parity deferred as before.

Known risks, assumptions, and blocking questions:

- Assumption: wiki quantities match the installed game version; the
  provenance note and the user's in-game cross-check at G3 close this.
  A future game patch changing quantities requires a data-file update;
  the Docs validation will not catch quantity drift, only class drift.
- Assumption (W02 dependency): `Schematic`, `milestones_by_tier`,
  `schematics_of_type`, `is_alternate_recipe`, and normalized-key
  behavior land exactly as specced in SSP-P1-W02. If W02 QC changes
  those APIs, rebase this packet before dispatch.
- No blocking questions: the bundled-data amendment was approved by the
  user on 2026-07-01.

### Implementation result (Sonnet 5 agent, 2026-07-01, attempt 1)

- New `data/project_assembly_phases.json`: schema_version 1, provenance
  block, base_tiers, and all five phases with the exact verified
  quantities and `Desc_SpaceElevatorPart_N_C` classes.
- New `satisfactory_progression.py`: frozen dataclasses and the five
  spec'd functions; loader raises on structural defects, Docs validation
  returns diagnostics, demand math exact with strict pace bounds,
  tier rule implemented, alternates opt-in only.
- New `tests/test_progression.py`: 24 tests including the real-install
  validation (ran and passed, zero diagnostics).
- Deviation flagged by the agent: the packet spec'd no base_tiers
  parameter on `build_capability_snapshot`, so the agent added a private
  `_bundled_base_tiers()` that re-reads the bundled JSON at call time.

### Quality control (Fable 5, 2026-07-01, attempt 1)

Independent verification:

- `python -m pytest skills/satisfactory_assistant/tests -q -p no:cacheprovider`
  -> 145 passed, 1 skipped (pre-existing POSIX-only skip)
- `python -m ruff check skills/satisfactory_assistant` -> All checks passed
- `python -m compileall -q skills/satisfactory_assistant` -> passed
- `data/project_assembly_phases.json` compared field-by-field against the
  packet's verified ground-truth table: exact match, provenance present.
- Full line-by-line review of `satisfactory_progression.py`.

Findings:

- F-P1W03-1 (Medium): `build_capability_snapshot` calls
  `_bundled_base_tiers()`, which reads the bundled JSON from disk on
  every call regardless of the `phases` the caller passed. Consequences:
  a caller supplying fixture or override phase data still gets bundled
  base tiers (two data sources silently mixed in one computation); a
  missing or corrupt bundled file makes snapshot building raise even
  when the caller's phases are valid; and each solver-side snapshot call
  pays file IO. Root cause is a packet spec gap (the loader's return
  type dropped `base_tiers`), honestly flagged by the agent. Required
  correction (cheapest now, before any consumer exists): introduce a
  frozen `ProjectAssemblyData` dataclass carrying `base_tiers` and
  `phases`; `load_project_assembly_phases` returns it and validates
  `base_tiers` structurally (missing/invalid raises ValueError in the
  loader, where structural validation belongs); `derive_phase_demand`,
  `available_tiers_for_phase` (drop its `base_tiers` parameter), and
  `build_capability_snapshot` accept the data object; delete
  `_bundled_base_tiers`; update `validate_phases_against_docs` to accept
  either the data object or keep the phases tuple (implementer's choice,
  document it); update tests accordingly.
- No other findings; data file, demand math, gating, and tests are
  exactly per packet.

### Gate decision (attempt 1)

- Decision: `CHANGES_REQUESTED` (F-P1W03-1).
- Next owner: Sonnet 5 agent `p1w03-impl`, attempt 2 under this package
  ID.

### Implementation result attempt 2 (Sonnet 5 agent, 2026-07-01)

- Frozen `ProjectAssemblyData(base_tiers, phases)` added;
  `load_project_assembly_phases` returns it and structurally validates
  `base_tiers` in the loader; `_bundled_base_tiers` deleted;
  `validate_phases_against_docs`, `derive_phase_demand`,
  `available_tiers_for_phase` (base_tiers parameter removed), and
  `build_capability_snapshot` all consume the data object; snapshot
  building performs no file access.
- Tests updated to the new API plus two new loader tests
  (missing/non-list base_tiers raise ValueError); all prior behavioral
  assertions kept.

### Quality control attempt 2 (Fable 5, 2026-07-01)

- Independent re-verification:
  - `python -m pytest skills/satisfactory_assistant/tests -q -p no:cacheprovider`
    -> 147 passed, 1 skipped (pre-existing POSIX-only skip)
  - `python -m ruff check skills/satisfactory_assistant` -> All checks passed
  - `python -m compileall -q skills/satisfactory_assistant` -> passed
  - `_bundled_base_tiers` references in the module -> 0
  - Signatures and loader behavior reviewed line-by-line: correction
    applied exactly as required, F-P1W03-1 fixed.

### Gate decision (attempt 2)

- Decision: `QC_PASSED`.
- Next owner: User for G3 acceptance (packet asks for a quick in-game
  cross-check of the phase quantities against the Space Elevator screen
  when convenient; class-name validation against Docs is already
  automated and clean).
- Next action on acceptance: draft SSP-P1-W04 (versioned dataset cache
  and bounded lookup), the final Phase 1 packet.
- User acceptance: ACCEPTED on 2026-07-01 (in-game quantity cross-check
  to be done at the user's convenience; class validation automated).

## 2026-07-01 - SSP-P1-W02 - Schematic and HUB gate dataset

- Roadmap phase: Phase 1 - Docs and progression dataset
- Owner: complete
- Status: `ACCEPTED`
- Attempt: 1
- Dispatched: 2026-07-01, agent `p1w02-impl`
- Baseline revision: `15d0e64`, dirty working tree; SSP-P0-W01..W06,
  SSP-P8-W01, and SSP-P1-W01 all `ACCEPTED`
- Pre-existing changes: unrelated `skills/sc_*` and
  `services/config_manager.py` edits; `release_version/` intentionally
  stale (sync deferred; now spans W01 fix, discovery, and this packet)
- Plan references: `SatisfactorySkillPlan.md` sections 6.2 (normalized
  data), 12 (Phase 1), 16 (guardrails)

### Implementation packet (Fable 5)

Objective:

- Extend the Docs catalog with schematic data: HUB milestones, tech-tier
  gates, alternate-recipe unlock mapping, and schematic costs, so later
  packets can build capability snapshots and filter recipes by open gates.

Ground truth verified on this machine 2026-07-01 (live Docs via the new
discovery module):

- One `FGSchematic` NativeClass group, 574 entries.
- `mType` distribution: EST_Custom 93, EST_Tutorial 6,
  EST_ResourceSink 173, EST_MAM 120, EST_Milestone 42, EST_HardDrive 1,
  EST_Customization 30, EST_Alternate 109.
- Milestone `mTechTier` values cover 1 through 9.
- `mCost` uses the same `(ItemClass=...,Amount=N)` struct-strings as
  recipe ingredients: parse with the existing `parse_item_amounts`.
- `mUnlocks` is a list of dicts; entries with `Class` ==
  `BP_UnlockRecipe_C` carry `mRecipes` as a quoted-path list (parse with
  the existing quoted-path regex). Other unlock classes
  (`BP_UnlockInfoOnly_C`, etc.) are ignored for this packet.
- `mSchematicDependencies` entries with `Class` ==
  `BP_SchematicPurchasedDependency_C` carry `mSchematics` quoted paths.
- FINDING: no Project Assembly / game-phase data exists anywhere in this
  Docs version (no FGGamePhase group; 2 `GamePhase` strings total, both a
  victory dependency; no phase schematics). See blocking questions.

In scope:

- `satisfactory_docs.py` only (pure module), plus tests:
  - New frozen dataclass `Schematic`: `class_name`, `display_name`,
    `schematic_type` (raw `EST_*` string), `tech_tier` (int),
    `time_to_complete` (float), `cost` (tuple[ItemAmount, ...]),
    `unlocked_recipes` (tuple[str, ...], normalized keys),
    `dependency_schematics` (tuple[str, ...], normalized keys).
  - `load_docs_catalog` parses the FGSchematic group into the catalog.
  - `DocsCatalog` additions: `schematic(class_name)`, `schematic_count`,
    `milestones_by_tier(tier)`, `schematics_of_type(est_type)`,
    `recipe_unlocked_by(recipe_class)` returning the schematic keys that
    unlock the recipe, and `is_alternate_recipe(recipe_class)` (True when
    an unlocking schematic is EST_Alternate or EST_HardDrive, or the
    normalized recipe key starts with `recipe_alternate_`).
  - Constructor takes `schematics` as a keyword with a default empty dict
    so existing construction sites and tests keep working unchanged.
- New `tests/test_schematics.py` with a small fixture Docs JSON:
  - One EST_Milestone (tier 3) with a two-item cost, one
    `BP_UnlockRecipe_C` entry unlocking two recipes, and one
    `BP_UnlockInfoOnly_C` entry that must be ignored.
  - One EST_Alternate schematic unlocking a `Recipe_Alternate_*` recipe.
  - One EST_ResourceSink schematic (parsed, classified by type).
  - One schematic with a `BP_SchematicPurchasedDependency_C` dependency.
  - One malformed entry (missing mTechTier, empty mUnlocks) that must be
    skipped or defaulted without raising.
- One real-install integration test, skipped when `discover_docs()`
  yields nothing (mirror the existing skip pattern): tiers 1 through 9
  each have at least one milestone, at least 40 milestones and 100
  alternates total, and at least 90 percent of recipe-unlock references
  resolve against the catalog's parsed recipes.

Explicitly out of scope:

- Capability snapshot builder (planned SSP-P1-W03).
- Project Assembly phase demand data (blocked, see below).
- Dataset caching, bounded lookup tool exposure.
- Any change to `main.py`, tools, config, `satisfactory_reference.py`,
  or `release_version/`.

Expected files:

```text
skills/satisfactory_assistant/satisfactory_docs.py      (extend)
skills/satisfactory_assistant/tests/test_schematics.py  (new)
```

Data contracts and migration/configuration effects:

- New `Schematic` dataclass and catalog getters; no persistence, config,
  or tool-schema changes. No migration.

Acceptance criteria:

1. Fixture round-trip: type, tier, cost amounts, unlocked recipes, and
   dependencies parse exactly; non-recipe unlock entries are ignored.
2. `recipe_unlocked_by` and `is_alternate_recipe` behave per spec for
   milestone-unlocked, alternate-unlocked, and prefix-named alternates.
3. Malformed schematic entries never raise; they are skipped or given
   safe defaults.
4. All pre-existing tests pass unchanged (catalog stays
   backward-compatible; mirror path untouched).
5. Real-install integration test passes on this machine and skips
   cleanly without an install.
6. `python -m pytest`, `python -m ruff check`, `python -m compileall`
   all clean; no bare `print(`; no em-dashes; ASCII only.

Required verification:

```text
python -m pytest skills/satisfactory_assistant/tests -q -p no:cacheprovider
python -m ruff check skills/satisfactory_assistant
python -m compileall -q skills/satisfactory_assistant
```

Cross-platform, token, persistence, and release-parity concerns:

- Pure-module work; no platform-specific code. No token impact (no tool
  changes). No persistence impact. Release parity deferred as before.

Known risks, assumptions, and blocking questions:

- Assumption: `EST_*` type strings and unlock class names are stable per
  game patch; the integration test detects drift.
- Risk: 574 schematics inflate catalog memory slightly; dataclasses with
  tuples keep this small.
- RESOLVED 2026-07-01: the current Docs export contains no Project
  Assembly phase delivery quantities, falsifying plan sections 2.3 and
  6.2. The user approved the amendment: bundle a reviewed,
  provenance-tagged `project_assembly_phases.json` in the skill,
  validated at load against Docs item classes so a patch mismatch is
  detected, versioned per game patch. Lands with SSP-P1-W03+.

### Implementation result (Sonnet 5 agent, 2026-07-01)

- `satisfactory_docs.py` extended: frozen `Schematic` dataclass; pure
  parsers `_parse_unlocked_recipes` and `_parse_dependency_schematics`
  (class-filtered, quoted-path parsing, never raise); `FGSchematic`
  loader branch; `DocsCatalog` gains `schematics` kwarg (default empty,
  backward-compatible), `schematic()`, `schematic_count`,
  `milestones_by_tier()`, `schematics_of_type()`,
  `recipe_unlocked_by()` backed by a recipe-to-schematics index built
  once in the constructor, and `is_alternate_recipe()` (alternate or
  hard-drive schematic type, or `recipe_alternate_` prefix).
- New `tests/test_schematics.py`: 13 tests covering the fixture round
  trips, ignore rules, sorting, dependencies, malformed-entry safety,
  alternate classification, backward compatibility, and a gated
  real-install integration test.
- Changed files: `satisfactory_docs.py`, `tests/test_schematics.py`
  (new).
- Deviation (flagged by the agent, accepted at QC, see below): the
  90 percent recipe-resolve acceptance criterion was scoped to the five
  production schematic types instead of literally all schematics.

### Quality control (Fable 5, 2026-07-01)

Independent verification, not agent-reported numbers:

- `python -m pytest skills/satisfactory_assistant/tests -q -p no:cacheprovider`
  -> 121 passed, 1 skipped (pre-existing POSIX-only skip)
- `python -m ruff check skills/satisfactory_assistant` -> All checks passed
- `python -m compileall -q skills/satisfactory_assistant` -> passed
- Deviation claim reproduced against the live Docs: one
  `FGCustomizationRecipe` NativeClass group with 106 entries exists;
  EST_Custom/EST_ResourceSink unlock entries point into it (cosmetics),
  not into FGRecipe. Measured resolve rates: 907/1016 = 89.27 percent
  across all schematics; 411/411 = 100 percent across EST_Milestone,
  EST_Alternate, EST_MAM, EST_HardDrive, EST_Tutorial. Live counts:
  42 milestones (tiers 1-9 all populated), 109 alternates,
  574 schematics total.
- Line-by-line review of the new dataclass, parsers, index, catalog
  getters, and loader branch: matches the packet; index built once;
  stable orderings; no behavior change for existing consumers.

Findings:

- Deviation accepted: the criterion's intent was production-recipe
  gating; the original packet wording ("all schematics") was written
  without knowledge of the FGCustomizationRecipe group. Scoping the
  measurement to production types is more faithful to intent, and the
  agent flagged rather than silently absorbed it: correct handling.
  Follow-up noted for a later packet: decide whether
  FGCustomizationRecipe should ever be parsed (likely never needed for
  planning).
- No Critical/High/Medium/Low findings.

### Gate decision

- Decision: `QC_PASSED`.
- Next owner: User for G3 acceptance.
- Next action: on acceptance, dispatch SSP-P1-W03 (already `PLANNED`;
  its W02 API dependency landed exactly as assumed, no rebase needed).
- User acceptance: ACCEPTED on 2026-07-01, including the QC-accepted
  narrowing of the recipe-resolve criterion to production schematic
  types.

## 2026-07-01 - SSP-P1-W01 - Cross-platform install and Docs discovery

- Roadmap phase: Phase 1 - Docs and progression dataset
- Owner: complete
- Status: `ACCEPTED`
- Attempt: 1
- Baseline revision: `15d0e64`, dirty working tree
- Pre-existing changes: unrelated `skills/sc_*` and `services/config_manager.py`
  edits; untracked `skills/satisfactory_assistant/`; `release_version/` is stale
  relative to source since SSP-P8-W01
- Plan references: `SatisfactorySkillPlan.md` sections 5.1 (module table),
  6.1 (discovery order), 12 (Phase 1), 16 (guardrails)
- Sequencing constraint: resolved 2026-07-01. SSP-P8-W01 passed QC at
  attempt 2 (G3 user acceptance still pending) and the user directed the
  pipeline to continue with planning/QC on Fable 5 and coding on Sonnet 5,
  which is treated as the plan-11.7 authorization to proceed. The `main.py`
  Docs call sites this packet rewires are final as of SSP-P8-W01 attempt 2.

### Implementation packet (Codex, drafted by Claude)

Objective:

- Replace the hard-coded, Windows-only Docs lookup in
  `satisfactory_docs.discover_docs_file()` with a pure, cross-platform
  install-and-Docs discovery module `satisfactory_install.py`, implementing
  the plan section 6.1 discovery order with locale selection and structured
  diagnostics.

In scope:

- New pure module `skills/satisfactory_assistant/satisfactory_install.py`:
  - Discovery order, first hit wins:
    1. Explicit configured Docs file (`satisfactory_docs_file`).
    2. `SATISFACTORY_DOCS_FILE` environment variable (existing behavior,
       retained for compatibility).
    3. Explicit configured install directory (`satisfactory_install_dir`,
       new); resolve `CommunityResources/Docs/<locale>.json` beneath it.
    4. Steam library discovery: locate Steam root per platform, parse
       `steamapps/libraryfolders.vdf` with a minimal line-oriented `"path"`
       extractor (no VDF dependency), check each library for
       `steamapps/common/Satisfactory/CommunityResources/Docs/`.
    5. Epic best-effort: on Windows read
       `%PROGRAMDATA%/Epic/UnrealEngineLauncher/LauncherInstalled.dat`
       (JSON) and match a Satisfactory install location; guarded, optional.
    6. Guarded platform fallbacks: current known common paths on Windows;
       `~/.steam/steam`, `~/.local/share/Steam` on Linux;
       `~/Library/Application Support/Steam` on macOS.
  - Locale handling: request `satisfactory_docs_locale` (default `en-US`);
    if `<locale>.json` is absent but `en-US.json` exists, fall back to
    `en-US.json` and record the fallback in diagnostics.
  - Return a small frozen dataclass `DocsDiscovery` with: `docs_path`
    (resolved `Path` or `None`), `locale`, `source` (one of
    `configured_file`, `env`, `install_dir`, `steam`, `epic`, `fallback`),
    and `searched` (ordered list of human-readable locations tried, for the
    config-hint error message).
  - All filesystem access wrapped in `OSError` guards; deterministic
    candidate ordering; environment variable and `~` expansion on all
    configured paths.
- Migrate call sites: `main.py` (and `satisfactory_mirror.py` if it calls
  discovery directly) use `satisfactory_install`; delete
  `discover_docs_file()` and the hard-coded drive-letter list from
  `satisfactory_docs.py` entirely (no dead code).
- Config: add `satisfactory_install_dir` (string, default empty) and
  `satisfactory_docs_locale` (string, default `en-US`) to
  `default_config.yaml`, retrieved just-in-time; keep
  `satisfactory_docs_file` semantics unchanged.
- Tests: new `tests/test_install.py` using tmp-dir fixtures (fake
  `libraryfolders.vdf`, fake Epic manifest, fake Docs trees).

Explicitly out of scope:

- Docs content parsing changes (schematics, HUB gates, Project Assembly
  phases): later Phase 1 packets.
- Dataset normalization, caching, capability snapshots, bounded lookup.
- Any tool schema change (tool count and signatures unchanged).
- `release_version/` sync: deferred until source QC passes, consistent with
  the SSP-P8-W01 follow-up; track as an explicit post-G2 step.
- Resolving the SSP-P8-W01 third-tool question.
- Core API, interface, or endpoint changes.

Expected files:

```text
skills/satisfactory_assistant/satisfactory_install.py        (new)
skills/satisfactory_assistant/satisfactory_docs.py           (remove discovery)
skills/satisfactory_assistant/satisfactory_mirror.py         (call sites, if any)
skills/satisfactory_assistant/main.py                        (call sites, config reads)
skills/satisfactory_assistant/default_config.yaml            (2 new properties)
skills/satisfactory_assistant/tests/test_install.py          (new)
skills/satisfactory_assistant/tests/test_docs.py             (drop discovery tests if present)
```

Data contracts and migration/configuration effects:

- `DocsDiscovery` dataclass as described above; no persistence changes and
  no workspace schema changes.
- Two new optional config properties with empty/`en-US` defaults; existing
  installs keep working with no config edits.
- No migration required.

Acceptance criteria:

1. Discovery precedence is exactly the six-step order above; each step and
   each override-beats-autodetect case is covered by a unit test.
2. A fixture `libraryfolders.vdf` pointing at a library on a non-default
   path is honored; no hard-coded drive letters remain anywhere in the
   skill.
3. Requested non-default locale resolves when present; missing locale falls
   back to `en-US.json` and the fallback is visible in `DocsDiscovery`.
4. When nothing is found, `docs_path` is `None` and `searched` is non-empty;
   `main.py` surfaces a config hint built from it; journal tools remain
   fully functional (existing degradation behavior preserved).
5. `satisfactory_install.py` imports no Wingman runtime modules and no new
   third-party packages; filesystem errors (permission, broken symlink,
   unreadable vdf) do not raise.
6. Full test suite passes with no regression; on this machine the real
   install `D:/SteamLibrary/.../Satisfactory` is found via Steam library
   parsing, not via a fallback path.
7. Generated tool schemas are byte-identical before and after (no token
   budget impact).

Required verification:

```text
python -m pytest skills/satisfactory_assistant/tests -q -p no:cacheprovider
python -m ruff check skills/satisfactory_assistant
python -m compileall -q skills/satisfactory_assistant
rg "print\(" skills/satisfactory_assistant -g "*.py"   (only printr usages)
rg "SteamLibrary|Program Files" skills/satisfactory_assistant -g "*.py"   (fallback list only, no drive-letter Docs candidates)
```

Manual: run discovery on this machine and confirm source `steam` with the
`D:/SteamLibrary` Docs path; temporarily set a bogus
`satisfactory_docs_file` and confirm the override wins and fails with the
searched-locations hint.

Cross-platform, token, persistence, and release-parity concerns:

- Linux/macOS/Epic paths are guarded best-effort and untested on this
  machine (mirrors the existing Saved-dir resolver caveat); tests exercise
  them through fixtures only.
- No token impact (no tool changes). No persistence impact.
- Release parity intentionally deferred; `release_version/` divergence is
  already tracked under SSP-P8-W01 follow-ups.

Known risks, assumptions, and blocking questions:

- Assumption: Epic `LauncherInstalled.dat` format; unverifiable here (Steam
  install only). Keep the Epic step tolerant: any parse failure means skip.
- Assumption: one Docs directory per install; if multiple installs are
  found, first in deterministic order wins and the rest are recorded in
  `searched`.
- Risk: overlap with SSP-P8-W01 QC on `main.py` Docs call sites (see
  sequencing constraint above).
- Blocking questions: none.

### Implementation result (Sonnet 5 agent, 2026-07-01)

- New pure module `satisfactory_install.py`: frozen `DocsDiscovery`
  dataclass (docs_path, locale, source, searched) and `discover_docs()`
  implementing the six-step precedence. Steam step is vdf-driven (minimal
  line-oriented `"path"` regex, no VDF dependency); Epic step is
  Windows-only best-effort against `LauncherInstalled.dat` where any
  parse/read failure skips; guarded fallback checks the platform Steam
  root candidates directly without requiring a vdf. All filesystem access
  goes through OSError-guarded helpers; env var and `~` expansion on all
  configured paths; locale fallback to en-US recorded in `searched`.
- `satisfactory_docs.py`: `discover_docs_file()` and its hard-coded
  drive-letter candidates removed entirely (plus the now-unused `os`
  import).
- `main.py`: imports `discover_docs`, adds `_install_dir()` and
  `_docs_locale()` just-in-time accessors, registers both properties in
  `validate()`, and the audit tool's not-found message now includes a
  bounded "Searched: ..." hint (first 6 locations). No tool schema
  changes.
- `default_config.yaml`: added `satisfactory_install_dir` (default empty)
  and `satisfactory_docs_locale` (default `en-US`).
- New `tests/test_install.py`: 11 fixture-based tests covering precedence,
  vdf library on a non-default path, locale fallback and direct-locale
  use, nothing-found diagnostics, OSError tolerance, Epic manifest
  resolution, and the direct-root fallback.
- Documented deviation (accepted): step 4 is vdf-only and step 6 checks
  the same roots directly, making the two steps non-redundant.

### Quality control (Fable 5, 2026-07-01)

Independent verification, not agent-reported numbers:

- `python -m pytest skills/satisfactory_assistant/tests -q -p no:cacheprovider`
  -> 108 passed, 1 skipped
- `python -m ruff check skills/satisfactory_assistant` -> All checks passed
- `python -m compileall -q skills/satisfactory_assistant` -> passed
- `discover_docs_file` references remaining in source -> 0
- Real-machine discovery reproduced independently:
  `source=steam locale=en-US`,
  `D:\SteamLibrary\steamapps\common\Satisfactory\CommunityResources\Docs\en-US.json`
  resolved via `libraryfolders.vdf` parsing (acceptance criterion 6).
- Line-by-line review of `satisfactory_install.py`, the `main.py` call
  site and accessors, `default_config.yaml` additions, and all 11 tests;
  acceptance criteria 1 through 7 traced to code or tests.

Findings:

- F-P1W01-1 (Low, accepted): no direct test that a configured install dir
  beats Steam discovery; the linear precedence makes it true by
  construction and adjacent pairs are tested. Optional future test.
- No Critical/High/Medium findings.

### Gate decision

- Decision: `QC_PASSED`.
- Next owner: User for G3 acceptance.
- Next action: user accepts or returns the package; `release_version/`
  sync remains deferred until G3 outcomes for SSP-P8-W01 and this package
  are decided. Next planned packet: SSP-P1-W02 (schematics, HUB gates,
  and Project Assembly phase data in the normalized dataset).
- User acceptance: ACCEPTED on 2026-07-01.

## 2026-06-29 - SSP-P8-W01 - Save-derived factory mirror vertical slice

- Roadmap phase: Phase 8 - Actual factory adapters, with Phase 9 inference groundwork
- Owner: complete
- Status: `ACCEPTED`
- Attempt: 2
- Baseline revision: dirty working tree with untracked `skills/satisfactory_assistant/`; unrelated dirty files ignored
- Session timestamp: 2026-06-29 23:15:12 +02:00
- Product decision: target is a save-derived factory mirror, not true live telemetry. Autosaves are used as snapshots every 2 minutes. Expected rates from Docs are the primary truth; observed trend data is only an estimated health signal after repeated samples.

### Implementation packet / result (Codex direct)

Objective:

- Add the first usable vertical slice for a Satisfactory factory mirror: parse the active `.sav`, resolve Docs-backed expected rates, infer probable production lines, persist local artifacts, and expose a compact Wingman tool response.

Dependency audit and acquisition:

- Reviewed and used `@etothepii/satisfactory-file-parser@4.1.1` (MIT).
- Runtime dependency: `pako@2.1.0` (`MIT AND Zlib`), no dependencies.
- Static scans found no parser/pako network, server, process-execution, or file-write behavior in the runtime path. Hits were docs URLs and normal bundled JavaScript functions.
- Parser tarballs and assembled runtime remain quarantined under `.tmp/satisfactory-parser-audit/`; no third-party parser files were vendored into the skill directory yet.
- Added only a pinned local manifest for future install: `tools/save_parser/package.json`.

Changed files:

```text
skills/satisfactory_assistant/default_config.yaml
skills/satisfactory_assistant/main.py
skills/satisfactory_assistant/satisfactory_docs.py
skills/satisfactory_assistant/satisfactory_mirror.py
skills/satisfactory_assistant/satisfactory_save_parser.py
skills/satisfactory_assistant/tools/save_parser/extract_save_snapshot.cjs
skills/satisfactory_assistant/tools/save_parser/package.json
skills/satisfactory_assistant/tests/test_mirror.py
```

Implemented behavior:

- Added `audit_satisfactory_factory(focus="")` as the third and still compact skill tool. It parses only the active save's physical `.sav`, loads the Satisfactory Docs file, builds a local mirror artifact, and returns a bounded summary.
- Added Python subprocess wrapper for the Node parser with timeout, JSON validation, parser-runtime lookup, and no live-save writes.
- Added Docs catalog loader for items, resources, recipes, buildables, manufacturer speeds, extractor cycle/items-per-cycle, and single-resource extractor fallback from `mAllowedResources`.
- Added expected-rate mirror calculations:
  - machine recipe inputs/outputs per minute
  - clock speed and production boost handling
  - extractor outputs when resource is directly known or inferable from the extractor type
  - gross expected input/output totals
  - probable line clustering by proximity and input/output compatibility
- Added rolling estimated health:
  - no deviation alert until the configured rolling window is full
  - zero-output streak requires the configured consecutive-snapshot threshold
  - trends are labeled estimated, not live telemetry
- Added generated artifacts under the per-save workspace:
  - `mirror/latest_snapshot.json`
  - `mirror/latest_mirror.json`
  - `mirror/latest_health.json`
  - `mirror/observations.jsonl`

Configuration added:

- `satisfactory_docs_file`
- `satisfactory_parser_runtime_dir`
- `mirror_trend_window_saves` (default `5`)
- `mirror_zero_streak_saves` (default `3`)
- `mirror_deviation_threshold_percent` (default `25`)

Real-save smoke evidence:

- Save copy: `.tmp/satisfactory-parser-audit/samples/Nitric Acid is Outbound.sav`
- Docs: auto-detected from the installed Satisfactory Docs file.
- Parser result: `113,962` objects, `930` recipe machines, `172` extractors, `28` production buildables with no recipe.
- Mirror result after extractor fallback:
  - `1130` machine candidates
  - `47` inferred production lines
  - `135` unknown-rate machines
  - top expected gross outputs include Water, Screws, Crude Oil, Iron Ingot, Aluminum Scrap, and Fuel
  - first sample correctly reports no rolling deviations yet

Verification commands/results:

```text
python -m compileall skills\satisfactory_assistant
```

Result: passed.

```text
python -m pytest skills\satisfactory_assistant\tests
```

Result: `94 passed, 1 skipped`.

```text
node skills\satisfactory_assistant\tools\save_parser\extract_save_snapshot.cjs <copied save> --summary-only --pretty
```

Result: parsed copied real save with `0` parser warnings and expected summary counts.

Known limitations / tomorrow's starting points:

- Miner/resource-node purity and descriptor lookup is not decoded yet. Remaining unknown-rate machines are mostly `Build_MinerMk2`, `Build_FrackingExtractor`, `Build_MinerMk3`, plus the expected no-recipe production buildables.
- Geothermal and resource-well pressurizer math is not complete.
- The parser package is not formally bundled for distribution yet; the audited runtime lives in `.tmp` and the skill has a pinned manifest only.
- The new tool has not been manually invoked from a running Wingman instance.
- `focus` is currently echoed but not used to filter mirror artifacts.
- The source `release_version/` copy was not updated in this session.

### Quality control (Fable 5, per user direction 2026-07-01)

QC performed on the main session model at user request (planning/analysis on
Fable 5, coding delegated to Sonnet 5 subagents); Codex QC role executed here.

Independent verification:

- `python -m pytest skills/satisfactory_assistant/tests -q -p no:cacheprovider`
  -> 94 passed, 1 skipped
- `python -m compileall -q skills/satisfactory_assistant` -> passed
- `python -m ruff check skills/satisfactory_assistant` -> All checks passed
- Bare `print(` grep -> none outside printr usage
- Code reviewed line-by-line: `main.py` (audit tool adapter),
  `satisfactory_mirror.py`, `satisfactory_save_parser.py`,
  `tools/save_parser/extract_save_snapshot.cjs`, `default_config.yaml`,
  `tests/test_mirror.py` test names traced to claimed coverage
- Node script requires only `fs`/`path` plus the audited parser; no network,
  no file writes, warnings captured, bigint-safe JSON, exit code on failure
- Subprocess isolation confirmed: list-form command, timeout, JSON validation,
  no shell, no live-save writes

Findings:

- F-P8W01-1 (Medium): `audit_satisfactory_factory` parses the live `.sav` in
  place (`main.py` passes `result.save_file` directly). A concurrent autosave
  write can produce a torn read: at best a transient `SaveParserError`, at
  worst a partially-parsed snapshot recorded as a real observation, polluting
  the rolling health window. The parser docstring anticipates this ("caller
  may pass a copy"), and the smoke test used a copy. Required correction:
  copy the save into the per-save workspace mirror area (or a temp file
  contained there), parse the copy, and remove it afterward.
- F-P8W01-2 (Medium, product decision): the third tool slot is now consumed
  by `audit_satisfactory_factory`, while plan section 10 reserves the three
  tools as context/calculate/update and names "or later an audit" as a mode
  of `calculate_satisfactory_plan`. Recommendation: accept the standalone
  audit tool temporarily; when Phase 3 introduces
  `calculate_satisfactory_plan`, fold the audit in as its audit mode so the
  three-tool cap holds. Needs user acceptance at G3.
- F-P8W01-3 (Low): mirror artifacts (`latest_*.json`, `observations.jsonl`
  rewrite) are written non-atomically; same class as deferred F-W03-3.
  Track with the Phase 2 SQLite/store work.
- F-P8W01-4 (Low): `format_factory_audit` caps each section but has no hard
  global character budget like `format_context`; extreme item names could
  exceed the compact-response target. Consider a global cap later.
- F-P8W01-5 (Low): `main.py` is at 516 lines, marginally over the project's
  500-line guidance; the audit adapter is a natural extraction candidate in
  a later package.
- Already-logged limitations confirmed, not re-raised: unused `focus`,
  parser runtime under `.tmp` (packaging open), miner purity not decoded,
  `release_version/` stale.

Gate decision:

- Decision: `CHANGES_REQUESTED` (F-P8W01-1 must be fixed; F-P8W01-2 routed
  to user at G3; Lows tracked as backlog).
- Next owner: Sonnet 5 implementation agent for the F-P8W01-1 correction,
  attempt 2 under this package ID.

### Implementation result attempt 2 (Sonnet 5 agent, 2026-07-01)

- Added `copied_save(save_file, target_dir)` context manager to
  `satisfactory_save_parser.py`: mkstemp-reserved unique copy inside
  `target_dir`, `shutil.copy2`, OSError chained to `SaveParserError`,
  copy unlinked in `finally` (missing_ok).
- `audit_satisfactory_factory` now parses a private copy under the
  containment-guarded `ws.dir / "mirror"` and restores the real
  `saveName`/`fileName` into `snapshot["source"]` so the temp filename
  never leaks into mirror or audit output.
- New `tests/test_save_parser.py` with 4 tests: copy location and byte
  equality, cleanup on with-body exception, missing source raises
  `SaveParserError`, source untouched after exit.
- Changed files: `satisfactory_save_parser.py`, `main.py`,
  `tests/test_save_parser.py` (new). No deviations from the packet.

### Quality control attempt 2 (Fable 5)

- Independent re-verification, not agent-reported numbers:
  - `python -m pytest skills/satisfactory_assistant/tests -q -p no:cacheprovider`
    -> 98 passed, 1 skipped
  - `python -m ruff check skills/satisfactory_assistant` -> All checks passed
  - `python -m compileall -q skills/satisfactory_assistant` -> passed
- Line-by-line review of the new helper, the audit call site, and the new
  tests: matches the correction packet exactly; copy stays inside the
  per-save workspace; live save is never written; `copy2` preserves mtime
  so `fileMtime` in the snapshot source remains truthful.
- F-P8W01-1: fixed. F-P8W01-3/4/5 remain tracked backlog. F-P8W01-2
  remains a user decision.

Gate decision (attempt 2):

- Decision: `QC_PASSED`.
- Next owner: User for G3 acceptance.
- Next action: user decides F-P8W01-2 (keep standalone audit tool
  temporarily, fold into `calculate_satisfactory_plan` at Phase 3:
  recommended) and accepts or returns the package. `release_version/`
  sync stays deferred until after G3 per the packet.
- User acceptance: ACCEPTED on 2026-07-01. F-P8W01-2 decision: keep the
  standalone audit tool for now; fold it into
  `calculate_satisfactory_plan` when roadmap Phase 3 introduces the
  calculator.

## 2026-06-27 - SSP-P0-W06 - Wingman 3 skill API manifest compatibility

- Roadmap phase: Phase 0 - Correct the journal contract
- Owner: User for live test / G3 acceptance after Codex hotfix
- Status: `QC_PASSED`
- Attempt: 1
- Baseline revision: `15d0e64` plus accepted SSP-P0-W01 through W04 and
  QC-passed SSP-P0-W05 working tree
- Origin: Live Wingman 3.1.3 reported Satisfactory Assistant as not compatible.
  User asked Codex to check GitHub for a Wingman update.
- Pre-existing changes:
  - Same dirty tree as previous Satisfactory packets: unrelated `skills/sc_*`
    edits and untracked `skills/satisfactory_assistant/`.

### Implementation packet / result (Codex direct hotfix)

Findings:

- GitHub check: `ShipBit/wingman-ai` upstream `main` is `373daba` and reports
  `LOCAL_VERSION = "2.1.1"`; configured `origin/main` is `f4b0cf6` and also
  reports `LOCAL_VERSION = "2.1.1"`. The local checkout is `3.1.2`, while the
  installed Program Files Core is `3.1.3`; public GitHub was not a newer Core
  update path for this issue.
- Installed Wingman Core 3.1.3 includes `services/skill_catalog.py` with
  `SKILL_API_VERSION = 3` and `SUPPORTED_SKILL_API_VERSIONS = {3}`.
- `SkillCatalog` marks manifests without `api_version` as `LEGACY` with reason
  `missing api_version (pre-v3)`. `WingmanSkillManager.enable_skill()` then
  returns `Skill '<name>' is not compatible with this version of Wingman.`
- Satisfactory Assistant's `default_config.yaml` lacked `api_version`, so the
  catalog rejected it before import.

Change:

- Added `api_version: 3` immediately after the `module` line in:
  - `skills/satisfactory_assistant/default_config.yaml`
  - `skills/satisfactory_assistant/release_version/default_config.yaml`
  - live install:
    `C:\Users\larse\AppData\Roaming\ShipBit\WingmanAI\custom_skills\satisfactory_assistant\default_config.yaml`

Out of scope:

- No Python runtime code changes.
- No Core update, pull, reset, or working-tree merge.
- No tool-schema, workspace, active-save, or planner behavior changes.

### Quality control (Codex)

Independent verification:

- `python -m pytest skills\satisfactory_assistant\tests -q` -> 88 passed, 1 skipped
- `python -m compileall -q skills\satisfactory_assistant` -> passed
- `python -m ruff check skills\satisfactory_assistant` -> All checks passed
- Source/release SHA-256 parity for `main.py`, `satisfactory_workspace.py`,
  `satisfactory_active_save.py`, `satisfactory_models.py`,
  `satisfactory_reference.py`, and `default_config.yaml` -> all OK
- Live install/release SHA-256 parity for runtime files plus `default_config.yaml`,
  `skill_installer_config.json`, and `__init__.py` -> all OK
- `rg "print\(" skills\satisfactory_assistant -g "*.py"` -> only
  `self.printr.print(..., server_only=True)` in source and release `main.py`
- Tool count check -> 2 `@tool` decorators in source and 2 in release
- `api_version: 3` and `auto_activate: false` confirmed in source, release, and
  live installed manifests

Residual risk:

- A packaged-Core Python import probe could not be run outside Wingman's
  executable because `api.interface` is embedded in the PyInstaller archive, but
  the installed `SkillCatalog` source shows the exact failing gate and the live
  manifest now satisfies it.
- Wingman must be restarted/reloaded for the catalog scan to pick up the changed
  manifest.

### Gate decision

- Decision: `QC_PASSED`
- Next owner: User
- Next action: Restart/reload Wingman and live-test Satisfactory Assistant.
- User acceptance: Pending.

---
## 2026-06-26 - SSP-P0-W05 - Same-name save ambiguity diagnostic

- Roadmap phase: Phase 0 - Correct the journal contract
- Owner: User for G3 acceptance after Codex QC
- Status: `QC_PASSED`
- Attempt: 1
- Baseline revision: `15d0e64` (on top of accepted SSP-P0-W01 through SSP-P0-W04
  working tree)
- Origin: Deferred SSP-P0-W03 QC finding F-W03-2. User accepted W03/W04 and
  asked Codex to write up the W05 tasks.
- Pre-existing changes:
  - Same dirty tree as SSP-P0-W04: unrelated `skills/sc_*` edits, scratch/Claude
    artifacts, and the untracked `skills/satisfactory_assistant/` tree. This
    package should touch only the Satisfactory Assistant files listed below.
- Plan references:
  - `SatisfactorySkillPlan.md` section 9: "Base workspace identity on stable
    logical evidence such as Saved root, profile when known, and save/session
    name. File existence must not change the key."
  - `SatisfactorySkillPlan.md` section 12 Phase 0: "Stabilize workspace
    identity."
  - Phase 0 acceptance: "workspace identity remains stable."
  - SSP-P0-W03/W04 backlog finding F-W03-2: same-name saves under different
    profile directories can collide because `resolve_save_file()` returns the
    first profile match.

### Implementation packet (Codex)

Objective: prevent silent cross-profile save-file ambiguity. When the active log
identifies a `save_name` but `SaveGames` contains multiple matching
`<save_name>.sav` files under different profile locations, the resolver must not
pick one arbitrarily. It should preserve the active-save identity based on
`root` plus `save_name`, keep planning available from the active-log evidence,
and expose a concise ambiguity diagnostic so the user and assistant know the
physical `.sav` file was not uniquely resolved.

Important design constraint: do not add profile or `save_file` to the workspace
key. Active logs do not reliably identify the profile, and adding profile only
when a file is found would re-break the SSP-P0-W03 invariant that missing,
found, and later-created save files keep the same workspace identity.

Implementation tasks:

- Replace or wrap `resolve_save_file(root, save_name)` with a deterministic
  lookup result that can represent three states: no match, exactly one match,
  and multiple matches.
- Detect matches in both known layouts:
  - `SaveGames/<profile>/<save_name>.sav`
  - `SaveGames/<save_name>.sav`
- Sort matches deterministically before deciding whether the result is unique.
- Preserve existing behavior when exactly one save file matches:
  `save_file` is that resolved path and `save_file_found` is `True`.
- Preserve existing behavior when no save file matches:
  `save_file` is `None`, `save_file_found` is `False`, and no ambiguity warning
  is emitted.
- For multiple matches, do not choose a path:
  `save_file` is `None`, `save_file_found` is `False`, active-save `status`
  remains `STATUS_OK`, and an ambiguity signal is present on the internal active
  save result.
- Add compact internal model fields as needed, for example
  `save_file_ambiguity: str | None` and/or a bounded candidate summary. Keep any
  candidate data small and internal; do not add a new Core API field.
- Surface the ambiguity in `get_satisfactory_context()` with one concise,
  bounded line. Prefer count plus profile names or a short diagnostic over full
  path dumps. The message should make clear that planning is using active-log
  save identity only.
- Keep `update_satisfactory_plan()` usable in the ambiguous case. The active log
  still identifies the save name; only the physical `.sav` path is ambiguous.
- Preserve source/release parity for every changed runtime file.

Out of scope:

- No `.sav` parsing.
- No profile-dependent workspace key and no migration of workspace directories.
- No new AI-callable tool.
- No Core API/interface/endpoint changes.
- No installed Docs parser, recipe solver, SQLite persistence, JSONL locking, or
  atomic rewrite work.
- No automatic save renaming, merging, or profile selection UI.

Expected files:

- `skills/satisfactory_assistant/satisfactory_active_save.py`
- `skills/satisfactory_assistant/satisfactory_models.py` if the active-save
  result model gains internal diagnostic fields
- `skills/satisfactory_assistant/main.py` if context/status rendering changes
- Focused tests under `skills/satisfactory_assistant/tests/`, likely
  `test_active_save.py` plus an adapter/context test if needed
- Matching files under `skills/satisfactory_assistant/release_version/`
- This `DEVLOG.md`, updated with Claude's implementation result

Acceptance criteria:

- A regression test with two profile directories containing `Same.sav` proves the
  resolver does not return either path and exposes an ambiguity diagnostic.
- A regression test with exactly one profile match still returns that path and
  sets `save_file_found=True`.
- A regression test with no match remains unchanged.
- A context-facing test proves ambiguity is visible to the assistant/user and is
  bounded.
- A workspace-key test proves missing, found, and ambiguous active-save results
  for the same `root` plus `save_name` use the same workspace directory.
- Existing SSP-P0-W01 through SSP-P0-W04 tests continue to pass.
- Tool surface remains two tools, `auto_activate` remains `false`, and the
  source/release runtime files stay in parity.

Required verification:

- `python -m pytest skills\satisfactory_assistant\tests -q`
- `python -m compileall -q skills\satisfactory_assistant`
- `python -m ruff check skills\satisfactory_assistant`
- `rg "print\(" skills\satisfactory_assistant -g "*.py"` and confirm there is
  no bare `print()`; existing `self.printr.print(..., server_only=True)` calls
  are allowed.
- Source/release parity check for all changed runtime files.
- Confirm `default_config.yaml` still has `auto_activate: false`.
- Confirm the source and release skill still expose exactly two `@tool`
  decorators.

Risks and assumptions:

- The active log provides save/session evidence but not a reliable profile, so a
  diagnostic is safer than guessing.
- Internal dataclass fields should not require Core API regeneration. If the
  implementation unexpectedly changes `api/interface.py`, `api/enums.py`, or
  FastAPI endpoints, stop and tell the user Core must be restarted before any
  client work.
- Users with duplicate save names may need to rename saves or isolate configured
  Saved roots manually; W05 only prevents silent mis-resolution.

### Implementation result (Claude)

Implemented multi-match save-file detection with a bounded ambiguity diagnostic;
workspace identity is untouched and still keyed on `root` + `save_name`.

Approach:

- Added `find_save_files(root, save_name)` returning every matching `.sav` across
  both known layouts (`SaveGames/<profile>/<name>.sav` and `SaveGames/<name>.sav`),
  deterministically sorted by path so "unique vs multiple" never depends on
  filesystem iteration order. Filesystem errors degrade to an empty list.
- Rewrote `resolve_save_file()` to delegate to `find_save_files()` and return the
  path only when the match is unique; no match or multiple matches return `None`,
  so a caller can never silently pick one of several ambiguous files. Its
  `Path | None` signature and OSError-to-`None` behavior are preserved.
- Added `ambiguous_save_diagnostic()` building a compact note that names the
  containing profile directories (not full paths), capped at 4 with a `(+N more)`
  marker.
- `resolve_active_save()` now uses `find_save_files()`: exactly one match sets
  `save_file`/`save_file_found=True` as before; multiple matches leave
  `save_file=None`, `save_file_found=False`, `status=STATUS_OK`, and set the new
  internal `ActiveSaveResult.save_file_ambiguity` string.
- `get_satisfactory_context()` renders the optional save-file line through a new
  pure `_save_file_note()` helper. Ambiguity takes precedence over the plain
  not-found line and states that planning uses the active-log save identity only.
- `update_satisfactory_plan()` needs no change: it resolves the workspace from
  `root` + `save_name` (W03), which is unaffected by an ambiguous physical path,
  so planning stays usable.

Changed files:

- `skills/satisfactory_assistant/satisfactory_models.py` - added internal
  `save_file_ambiguity: str | None` field (not a Core API field).
- `skills/satisfactory_assistant/satisfactory_active_save.py` - added
  `find_save_files()` and `ambiguous_save_diagnostic()`, rewrote
  `resolve_save_file()` to require a unique match, updated `resolve_active_save()`.
- `skills/satisfactory_assistant/main.py` - added `_save_file_note()` and used it
  for the context header line.
- `skills/satisfactory_assistant/tests/test_active_save.py` - added W05 resolver
  tests (single/none/both-layout/sorted lookup, ambiguous no-pick flow, single
  match sets no ambiguity, bounded diagnostic).
- `skills/satisfactory_assistant/tests/test_config_coercion.py` - added W05 tests
  (workspace dir identical across missing/found/ambiguous; `_save_file_note`
  precedence, not-found, and resolved cases).
- `skills/satisfactory_assistant/release_version/{satisfactory_models.py,
  satisfactory_active_save.py,main.py}` - copied for source/release parity.

Command results:

- `python -m pytest skills\satisfactory_assistant\tests -q` -> 88 passed, 1 skipped
  (was 78 passed, 1 skipped; skip is the POSIX-only case test).
- `python -m compileall -q skills\satisfactory_assistant` -> clean.
- `python -m ruff check skills\satisfactory_assistant` -> All checks passed.
- `rg "print\(" skills\satisfactory_assistant -g "*.py"` filtered of `printr.print`
  -> no bare `print()`.
- `auto_activate: false` confirmed in source and release `default_config.yaml`.
- `@tool` decorator count is 2 in both source and release `main.py`.
- Source/release parity: `diff` reports no differences for all four runtime files.

Deviations and decisions:

- No new Core API field: `save_file_ambiguity` is an internal dataclass field on
  `ActiveSaveResult`; `api/interface.py`, `api/enums.py`, and FastAPI endpoints
  were not touched, so no Core restart is required.
- `resolve_save_file()` semantics changed from "first match" to "unique match
  only". This is the intended fix (no silent arbitrary pick) and existing tests
  still pass.

Known limitations:

- Users with genuinely duplicate save names across profiles must rename saves or
  isolate configured Saved roots; W05 only prevents silent mis-resolution.
- Live Wingman tool-call verification remains a manual gap (no app runtime used).

### Quality control (Codex)

Diff/content reviewed: `satisfactory_active_save.py`, `satisfactory_models.py`,
`main.py`, `tests/test_active_save.py`, `tests/test_config_coercion.py`, and
matching `release_version/` runtime copies. Because `skills/satisfactory_assistant/`
is untracked in this worktree, Codex reviewed file contents directly rather than
relying on `git diff`.

Acceptance evidence:

- Multiple same-name matches: `resolve_active_save()` now calls
  `find_save_files()`, leaves `save_file=None`, sets `save_file_found=False`,
  preserves `STATUS_OK`, and sets `save_file_ambiguity`. Covered by
  `test_resolve_ambiguous_save_does_not_pick_one`.
- Unique match: `resolve_save_file()` returns a path only when
  `find_save_files()` returns one match. Covered by
  `test_find_save_files_returns_single_match`,
  `test_resolve_single_match_sets_no_ambiguity`, and existing active-save tests.
- No match: no path and no ambiguity remains the behavior. Covered by
  `test_find_save_files_returns_no_match` and
  `test_resolve_missing_save_file_keeps_identity`.
- Both supported save layouts are scanned and sorted deterministically. Covered by
  `test_find_save_files_finds_both_layouts_and_sorts`.
- Context visibility: `_save_file_note()` emits one ambiguity line, gives it
  precedence over the not-found note, and states planning uses the active-log
  save name only. Covered by `test_save_file_note_prefers_ambiguity_over_not_found`.
- Workspace identity: missing, found, and ambiguous results for the same
  `root` + `save_name` resolve to the same workspace directory. Covered by
  `test_workspace_identity_stable_across_ambiguous_state`.
- No profile-dependent key, `.sav` parser, new tool, Core API field, SQLite, or
  Docs-parser work was introduced.

Independent verification:

- `python -m pytest skills\satisfactory_assistant\tests -q` -> 88 passed, 1 skipped
- `python -m compileall -q skills\satisfactory_assistant` -> passed
- `python -m ruff check skills\satisfactory_assistant` -> All checks passed
- `rg "print\(" skills\satisfactory_assistant -g "*.py"` -> only
  `self.printr.print(..., server_only=True)` in source and release `main.py`
- Source/release SHA-256 parity for `main.py`, `satisfactory_workspace.py`,
  `satisfactory_active_save.py`, `satisfactory_models.py`,
  `satisfactory_reference.py`, and `default_config.yaml` -> all OK
- Tool count check -> 2 `@tool` decorators in source and 2 in release
- `auto_activate: false` confirmed in source and release `default_config.yaml`
- `git status --short api\interface.py api\enums.py main.py` -> no output; no
  Core API/interface/endpoint files changed

Findings: none.

Residual risk:

- Live in-app Wingman verification remains manual, same as prior Phase 0
  packets.
- One older test (`test_resolve_full_flow_with_unresolvable_save`) still
  monkeypatches `resolve_save_file()`, while `resolve_active_save()` now uses
  `find_save_files()` directly. It still passes because the fixture has no save
  match, and the actual lookup-failure behavior is covered separately by
  `test_resolve_save_file_survives_oserror`; this is test hygiene, not a W05
  acceptance blocker.

### Gate decision

- Decision: `QC_PASSED`
- Next owner: User
- Next action: User G3 acceptance, or return to an earlier gate if a release
  blocker is identified.
- User acceptance: Pending.

---

## 2026-06-26 - SSP-P0-W04 - Skip non-object JSONL records

- Roadmap phase: Phase 0 - Correct the journal contract
- Owner: Codex after user G3 acceptance
- Status: `ACCEPTED`
- Attempt: 1
- Baseline revision: `15d0e64` (on top of SSP-P0-W03 working tree)
- Origin: SSP-P0-W03 QC finding #1 (Medium). User directed this single fix now
  at G3; QC findings #2-#5 are deferred to Codex packeting (see backlog below).
- Pre-existing changes:
  - Same dirty tree as SSP-P0-W03: unrelated `skills/sc_*` edits, scratch/Claude
    artifacts, and the untracked `skills/satisfactory_assistant/` tree. This
    package touches only the workspace module, its test, and the release copy.

### Implementation packet (Claude, from QC finding)

Objective: a syntactically valid JSONL line that is not a JSON object (e.g.
`[]`, `"text"`, `42`, `null`) must never crash workspace rendering or status
updates. `_read()` previously appended any `json.loads()` result, but
`summary()`, `_item_line()`, and `_flow_line()` assume dict records and call
`.get()`, so a stray non-object line would raise `AttributeError`.

In scope:

- Filter `SaveWorkspace._read()` to `isinstance(record, dict)` only.
- Add a regression test covering list/string/number/null lines mixed with a
  real record, asserting summary/context/status paths do not raise and only the
  dict record survives.
- Maintain source/release parity for the changed runtime file.

Out of scope:

- No identity, adoption, schema, locking, or save-file-lookup changes (those are
  the deferred findings below).

### Implementation result (Claude)

- `skills/satisfactory_assistant/satisfactory_workspace.py` - `_read()` now skips
  any parsed line that is not a dict, with a comment explaining why.
- `skills/satisfactory_assistant/tests/test_workspace.py` - added
  `test_non_object_json_lines_are_ignored`.
- `skills/satisfactory_assistant/release_version/satisfactory_workspace.py` -
  copied for parity.

Command results:

- `python -m pytest skills\satisfactory_assistant\tests -q` -> 78 passed, 1 skipped
  (was 77 passed, 1 skipped; skip is the POSIX-only case test).
- `python -m compileall -q skills\satisfactory_assistant` -> clean.
- `python -m ruff check skills\satisfactory_assistant` -> All checks passed.
- Source/release parity: `diff` of `satisfactory_workspace.py` and `main.py`
  against their `release_version/` copies reports no differences.

### Deferred SSP-P0-W03 QC findings (backlog for Codex to packet)

- F-W03-2 (Medium): same-name saves under different profiles can collide.
  `resolve_save_file()` returns the first profile match. The key cannot include
  profile (unknown when the save file is missing) without re-breaking the W03
  stable-identity invariant; the viable change is an ambiguity diagnostic in the
  save-file lookup path, which W03 excluded. Needs a design decision.
- F-W03-3 (Medium): JSONL rewrites (`_rewrite`, "w" mode) are not atomic and
  unlocked; a crash or overlapping tool call can truncate records. Roadmap
  defers durable persistence to the planned SQLite store; track as a real
  data-loss risk until then.
- F-W03-4 (Low): generated tool-parameter descriptions for `update_satisfactory_plan`
  are generic ("The <name>"); consider a `Literal` for status or a manual schema
  override.
- F-W03-5 (Low): hard-coded Phase 4 quantities in `default_config.yaml` and
  `satisfactory_reference.py` can go stale; superseded by the roadmap's
  installed-Docs parsing direction.

### Quality control (Codex)

Diff reviewed: `satisfactory_workspace.py`, `tests/test_workspace.py`, and
matching `release_version/satisfactory_workspace.py` for SSP-P0-W04.

Independent verification:

- `python -m pytest skills\satisfactory_assistant\tests -q` -> 78 passed, 1 skipped
- `python -m compileall -q skills\satisfactory_assistant` -> passed
- `python -m ruff check skills\satisfactory_assistant` -> All checks passed
- `rg "print\(" skills\satisfactory_assistant -g "*.py"` -> only `self.printr.print(..., server_only=True)` in source and release `main.py`
- SHA-256 source/release parity for `main.py`, `satisfactory_workspace.py`, `satisfactory_active_save.py`, `satisfactory_models.py`, `satisfactory_reference.py`, and `default_config.yaml` -> all OK
- Tool count check -> 2 tools in source and 2 tools in release
- `auto_activate` check -> `false` in source and release

Acceptance evidence:

- `_read()` now appends only parsed JSON dicts; syntactically valid non-object
  JSON values are ignored before any `.get()`-based summary, formatting, or
  status-update path can touch them.
- `test_non_object_json_lines_are_ignored` covers list, string, number, and
  null lines mixed with a real todo record, then exercises summary, status
  update, and context rendering paths.
- Source/release parity was maintained for the changed runtime file.

Findings:

- None.

Residual risk:

- Invalid JSON and non-object JSON are still silently skipped rather than
  surfaced as corruption diagnostics. This is acceptable for the current
  journal stage but should be revisited with the typed store / SQLite work.
- The Claude-authored packet section is accepted as a narrow corrective package
  from the prior Codex review finding and user direction; no restructuring is
  required before G3.

### Gate decision

- Decision: `ACCEPTED`
- Next owner: Codex
- Next action: Deferred findings F-W03-2..5 remain backlog for future Codex packets.
- User acceptance: accepted in chat on 2026-06-26.

---

## 2026-06-26 - SSP-P0-W03 - Stable workspace identity

- Roadmap phase: Phase 0 - Correct the journal contract
- Owner: Codex after user G3 acceptance
- Status: `ACCEPTED`
- Attempt: 1
- Baseline revision: `15d0e64`
- Baseline checks:
  - `python -m pytest skills\satisfactory_assistant\tests -q` -> 68 passed, 1 skipped
- Pre-existing changes:
  - The repo remains dirty with unrelated modified `skills/sc_*` files, untracked scratch/Claude artifacts, and the untracked `skills/satisfactory_assistant/` tree. This package must not touch unrelated files.
- Plan references:
  - `SatisfactorySkillPlan.md` section 9: "Base workspace identity on stable logical evidence such as Saved root, profile when known, and save/session name. File existence must not change the key."
  - `SatisfactorySkillPlan.md` section 12 Phase 0: "Stabilize workspace identity"
  - `codexsatisfactoryreview.md` finding F-17: workspace identity can change when a save file appears

### Implementation packet (Codex)

Objective: the same logical active save must always resolve to the same planning workspace whether the `.sav` file is currently found on disk or temporarily missing. Plans must not appear to disappear when `resolve_active_save()` changes from `save_file=None` to a concrete save path for the same `root` and `save_name`.

In scope:

- Keep the existing two-tool surface; do not add a third tool.
- Do not add new public config properties or Core API/interface changes.
- Replace the volatile `result.save_file` workspace identity in `main._workspace_for()` with a stable logical identity based on the active Saved root and save name.
- The stable identity must be identical for the same `root` and `save_name` regardless of `save_file`, `save_file_found`, or temporary filesystem errors during save lookup.
- Preserve collision resistance for different Saved roots and different save names.
- Add a small, safe legacy adoption path for existing path-hash workspaces: if the stable workspace is absent and the old `save_file`-based workspace exists, adopt its existing JSONL files under the stable key without deleting or rewriting unrelated workspaces.
- Do not merge automatically if both stable and legacy workspaces already contain data; prefer the stable workspace and leave the legacy directory untouched.
- Keep all writes inside `get_generated_files_dir()/saves/<safe_save_key>/` and preserve resolved-path containment checks.
- Maintain source/release parity after source tests pass.

Out of scope:

- Do not change active-save log parsing, newest-log selection, save-file lookup, or configured-directory semantics.
- Do not add profile discovery unless it is necessary for the stable identity fix. If profile cannot be known when the save file is missing, do not make profile a conditional key component.
- Do not migrate JSONL schema, split workflow/calculated status, add SQLite, parse Docs data, add solver work, or inspect `.sav` contents.
- Do not delete old legacy workspace directories.

Expected files:

- `skills/satisfactory_assistant/main.py`
- `skills/satisfactory_assistant/satisfactory_workspace.py` if a pure helper/adoption function is the cleanest boundary
- `skills/satisfactory_assistant/tests/test_workspace.py`
- `skills/satisfactory_assistant/tests/test_config_coercion.py` or a new focused adapter test module if direct `_workspace_for()` coverage is clearer
- Matching runtime files under `skills/satisfactory_assistant/release_version/`
- `skills/satisfactory_assistant/DEVLOG.md` implementation-result section

Data contract:

- Active save result A: `root=R`, `save_name=S`, `save_file=None`, `save_file_found=False`.
- Active save result B: `root=R`, `save_name=S`, `save_file=R/SaveGames/<profile>/S.sav`, `save_file_found=True`.
- A and B must produce the same workspace key and directory.
- Different roots or different save names must still produce different keys.
- Legacy path-key adoption must only run when a concrete `save_file` exists and the old path-key directory is inside the skill's `saves` root.

Acceptance criteria:

- Regression test proves missing-save and found-save results for the same logical save map to the same workspace key/directory.
- Regression test proves different roots or save names still disambiguate.
- Regression test proves a pre-existing legacy path-hash workspace is adopted when the stable workspace is absent.
- Regression test proves no automatic merge or overwrite occurs when both stable and legacy workspaces already exist.
- Existing SSP-P0-W01 and SSP-P0-W02 tests still pass.
- Tool count remains two and `auto_activate` remains `false`.
- No bare `print()` is introduced; runtime logging continues through `Printr`.
- Source and `release_version` copies match for changed runtime files.

Required verification:

- `python -m pytest skills\satisfactory_assistant\tests -q`
- `python -m compileall -q skills\satisfactory_assistant`
- `python -m ruff check skills\satisfactory_assistant`
- `rg "print\(" skills\satisfactory_assistant -g "*.py"`
- A targeted source/release parity check for changed runtime files.

Risks and assumptions:

- Root plus save name is the minimum stable evidence available in both found and missing-save states. This may collide if two profiles under the same Saved root use the same save name; avoid introducing a conditional profile component until profile evidence is available in both states.
- Legacy adoption should be conservative. It should preserve old directories rather than deleting them, because later typed persistence can handle richer migrations.
- Live Wingman tool calls remain a separate manual verification gap unless Claude has an app runtime available.

### Implementation result (Claude)

Implemented the stable workspace identity fix plus conservative legacy adoption.

Approach:

- `_workspace_for()` now derives the workspace key from stable logical evidence
  (`root` + `save_name`) via a new pure helper, never from the volatile
  `save_file` path. The same logical save resolves to the same workspace whether
  the `.sav` file is found, missing, or temporarily unreadable.
- The stable identity string reuses the historical missing-save form
  (`"<root>|<save_name>"`), so workspaces created before this change already map
  to the new key with no migration.
- When a concrete `save_file` exists, `_workspace_for()` calls
  `adopt_legacy_workspace()` to copy the old path-hash workspace's `*.jsonl`
  files under the stable key. Adoption is conservative: it never deletes or
  rewrites the legacy directory, never overwrites a stable workspace that
  already holds data (no automatic merge), never copies over an existing stable
  file, and stays inside the `saves` root via the existing `_is_within`
  containment checks.

Changed files:

- `skills/satisfactory_assistant/satisfactory_workspace.py` - added
  `stable_workspace_key()` and `adopt_legacy_workspace()` pure helpers.
- `skills/satisfactory_assistant/main.py` - rewrote `_workspace_for()` to use
  the stable key and legacy adoption; updated the workspace import block.
- `skills/satisfactory_assistant/tests/test_workspace.py` - added SSP-P0-W03
  helper coverage (stable-key stability, root/name disambiguation, missing save
  name, legacy adoption copy / no-merge / no-legacy cases).
- `skills/satisfactory_assistant/tests/test_config_coercion.py` - added direct
  `_workspace_for()` coverage proving missing-save and found-save results for
  one logical save share a directory, that different roots/names disambiguate,
  and that a found save adopts its pre-fix path-hash workspace.
- `skills/satisfactory_assistant/release_version/main.py` and
  `skills/satisfactory_assistant/release_version/satisfactory_workspace.py` -
  copied to restore source/release parity for the changed runtime files.

Command results:

- `python -m pytest skills\satisfactory_assistant\tests -q` -> 77 passed, 1 skipped
  (was 68 passed, 1 skipped; the skip is the POSIX-only case-sensitivity test).
- `python -m compileall -q skills\satisfactory_assistant` -> clean.
- `python -m ruff check skills\satisfactory_assistant` -> All checks passed.
- `rg "print\(" skills\satisfactory_assistant -g "*.py"` -> only the existing
  `self.printr.print(...)` Printr calls in source and release `main.py`; no bare
  `print()` introduced.
- Source/release parity: `diff` of `main.py` and `satisfactory_workspace.py`
  against their `release_version/` copies reports no differences.

Scope confirmations:

- Two-tool surface unchanged; `auto_activate` remains `false`.
- No new config properties or Core API/interface changes.
- No changes to active-save log parsing, save-file lookup, JSONL schema, Docs,
  solver, SQLite, or `.sav` parsing. No legacy directories deleted.
- Live Wingman tool-call verification remains a manual gap (no app runtime used).

### Quality control (Codex)

Diff reviewed: `main.py`, `satisfactory_workspace.py`, `tests/test_workspace.py`,
`tests/test_config_coercion.py`, and matching `release_version` runtime copies
for SSP-P0-W03.

Independent verification:

- `python -m pytest skills\satisfactory_assistant\tests -q` -> 77 passed, 1 skipped
- `python -m compileall -q skills\satisfactory_assistant` -> passed
- `python -m ruff check skills\satisfactory_assistant` -> All checks passed
- `rg "print\(" skills\satisfactory_assistant -g "*.py"` -> only `self.printr.print(..., server_only=True)` in source and release `main.py`
- SHA-256 source/release parity for `main.py`, `satisfactory_workspace.py`, `satisfactory_active_save.py`, `satisfactory_models.py`, `satisfactory_reference.py`, and `default_config.yaml` -> all OK
- Tool count check -> 2 tools in source and 2 tools in release
- `auto_activate` check -> `false` in source and release

Acceptance evidence:

- `_workspace_for()` now derives the workspace key from `stable_workspace_key(result.root, result.save_name)`, so `save_file=None` and a concrete `.sav` path for the same root/name share one workspace.
- `stable_workspace_key()` preserves the historical missing-save identity form while disambiguating different roots and save names.
- `adopt_legacy_workspace()` copies existing legacy path-key `*.jsonl` files only when the stable workspace has no JSONL data, keeps the old directory, and leaves both directories untouched instead of merging when stable data exists.
- Existing SSP-P0-W01 and SSP-P0-W02 tests still pass, and the test count increased from 68/1 to 77/1.
- Runtime behavior stayed inside the existing two-tool, on-demand skill surface with no Core API/config changes.

Findings:

- None.

Residual risk:

- Root plus save name is the best stable identity available in both found and missing-save states, but same-name saves under different profiles in one Saved root can still collide until profile evidence is available without requiring the `.sav` file.
- Legacy adoption is intentionally conservative and non-destructive; old legacy directories remain on disk.
- Live Wingman tool calls remain outside this package's automated QC environment and are still tracked as a separate manual verification gap.

### Gate decision

- Decision: `ACCEPTED`
- Next owner: Codex
- Next action: SSP-P0-W04 opened as the corrective package for the malformed JSONL finding; deferred findings remain backlog.
- User acceptance: accepted in chat on 2026-06-26.

---
## 2026-06-25 - SSP-P0-W02 - Record-type safe status actions

- Roadmap phase: Phase 0 - Correct the journal contract
- Owner: Codex after user G3 acceptance
- Status: `ACCEPTED`
- Attempt: 1
- Baseline revision: `15d0e64`
- Baseline checks:
  - `python -m pytest skills\satisfactory_assistant\tests -q` -> 60 passed, 1 skipped
- Pre-existing changes:
  - The repo remains dirty with unrelated modified `skills/sc_*` files, untracked scratch/Claude artifacts, and the untracked `skills/satisfactory_assistant/` tree. This package must not touch unrelated files.
- Plan references:
  - `SatisfactorySkillPlan.md` section 12 Phase 0: "Enforce record types and explicit clearing"
  - `codexsatisfactoryreview.md` finding F-20: `complete_todo` is not restricted to todos

### Implementation packet (Codex)

Objective: status-changing actions must only mutate the record types they are meant to affect. `complete_todo` must never mark a note, goal, flow, or change-log entry done. `archive_item` may remain generic, but it must resolve and update one explicit record kind instead of searching every JSONL file blindly.

In scope:

- Keep the existing two-tool surface; do not add a third tool.
- Do not add new public config properties or Core API/interface changes.
- Add a type-safe status update path in the pure workspace layer, such as `set_status_for_kind(kind, item_id, status, now)` or an equivalent helper.
- Preserve the existing `item_id` prefixes as the record-kind signal: `note_`, `todo_`, `goal_`, `flow_`, and `chg_`.
- `complete_todo` must require a `todo_` id and update only `todos.jsonl`.
- `archive_item` must infer kind from a supported id prefix and update only that kind's JSONL file.
- `archive_item` should support notes, todos, goals, and flows. Treat `chg_` change-log entries as append-only audit records and reject archiving them with a concise message.
- Unknown or mismatched prefixes must return a concise error and must not mutate any record.
- Keep change-log writes compact and accurate after successful status actions.
- Preserve backwards compatibility for existing records and IDs; do not migrate old JSONL files.
- Maintain source/release parity after source tests pass.

Out of scope:

- Do not split workflow status from calculated status in this package.
- Do not change `update_flow` status semantics beyond using the existing validated flow status path.
- Do not change workspace identity hashing, active-save resolution, discovery text, Docs parsing, solver work, SQLite storage, or live `.sav` parsing.
- Do not add broad item lookup, pagination, or any new AI-callable tool.

Expected files:

- `skills/satisfactory_assistant/main.py`
- `skills/satisfactory_assistant/satisfactory_workspace.py`
- `skills/satisfactory_assistant/tests/test_workspace.py`
- A focused adapter/helper test may be added if needed
- Matching runtime files under `skills/satisfactory_assistant/release_version/`
- `skills/satisfactory_assistant/DEVLOG.md` implementation-result section

Data contract:

- `complete_todo(todo_id)` changes only a todo record from `open` to `done`.
- `complete_todo(note_id|goal_id|flow_id|chg_id|unknown)` returns an error and does not mutate any record.
- `archive_item(note_id|todo_id|goal_id|flow_id)` changes only that matching record to `archived`.
- `archive_item(chg_id|unknown)` returns an error and does not mutate any record.
- Status actions must still return the existing short success/failure acknowledgements, adjusted only where needed for clarity.

Acceptance criteria:

- Regression test proves `complete_todo` cannot complete a non-todo record.
- Regression tests prove `archive_item` updates only the inferred kind and rejects change-log or unknown ids.
- Tests prove a malicious or mismatched id cannot cause a status change in another JSONL file.
- Existing SSP-P0-W01 metadata and clearing tests still pass.
- Tool count remains two and `auto_activate` remains `false`.
- No bare `print()` is introduced; runtime logging continues through `Printr`.
- Source and `release_version` copies match for changed runtime files.

Required verification:

- `python -m pytest skills\satisfactory_assistant\tests -q`
- `python -m compileall -q skills\satisfactory_assistant`
- `python -m ruff check skills\satisfactory_assistant`
- `rg "print\(" skills\satisfactory_assistant -g "*.py"`
- A targeted source/release parity check for changed runtime files.

Risks and assumptions:

- Prefix-based inference is acceptable for this JSONL journal stage because all generated IDs already include stable kind prefixes. A later typed store may replace this with explicit record tables.
- `archive_item` rejecting change-log IDs is intentional because changes are audit history.
- Live Wingman tool calls remain a separate manual verification gap unless Claude has an app runtime available.

### Implementation result (Claude)

Summary: status-changing actions are now record-type safe. The unsafe search-all
`set_status` (which let `complete_todo` mark any record kind done - F-20) is
replaced by a single-file `set_status_for_kind`, and `complete_todo` /
`archive_item` resolve exactly one JSONL file from the id prefix before mutating
anything. No third tool added; tool count stays two and `auto_activate` stays
`false`. Built test-first (TDD): wrote the failing workspace and adapter tests,
watched them fail (`ImportError: cannot import name 'kind_for_id'`), then
implemented.

Changed files (all inside the untracked `skills/satisfactory_assistant/` tree):

- `satisfactory_workspace.py`
  - New `_KIND_BY_PREFIX` (reverse of `_ID_PREFIX`) and module function `kind_for_id(item_id) -> str | None`, which maps an id's leading prefix (`note_/todo_/goal_/flow_/chg_`) to its kind and returns `None` for unknown/malformed/empty ids.
  - New `set_status_for_kind(kind, item_id, status, now)`: reads and rewrites only that one kind's JSONL file (raises `ValueError` on an unknown kind), so an id belonging to another kind cannot mutate a different file.
  - Replaced the old blind cross-kind `set_status` loop with a thin, type-safe wrapper that infers the kind via `kind_for_id` and delegates to `set_status_for_kind` (a mismatched/unknown id is now a no-op instead of a multi-file search). Existing callers/tests keep working because all minted ids carry the kind prefix.
- `main.py`
  - New pure helper `_resolve_status_target(action, item_id) -> (kind, error)`: `complete_todo` only accepts a `todo_` id (-> `todos`); `archive_item` accepts note/todo/goal/flow ids and rejects `chg_` audit ids and unknown prefixes with a concise message. Returns `(None, error)` so the adapter mutates nothing on rejection.
  - The `complete_todo` / `archive_item` branch now calls `_resolve_status_target` first, returns the error if any, then calls `ws.set_status_for_kind(kind, ...)`. Imports `kind_for_id` from the workspace.
- `tests/test_workspace.py` - 6 new tests: prefix->kind mapping; unknown/malformed id -> `None`; `set_status_for_kind` updates only its kind; a flow id handed to the todos file leaves the flow unchanged; unknown kind raises; generic `set_status` infers kind so a fabricated `todo_` id can't touch the goals file.
- `tests/test_config_coercion.py` - 2 new adapter tests: `complete_todo` accepts only `todo_` ids and rejects note/goal/flow/chg/unknown/empty; `archive_item` infers kind for note/todo/goal/flow and rejects `chg_`/unknown/empty.
- `release_version/` runtime copies regenerated via `update_release.py`.

Exact commands and results (run from `skills/satisfactory_assistant/`):

- `python -m pytest tests -q` -> **68 passed, 1 skipped** (baseline was 60/1; +8 new tests). Skip is the POSIX-only containment test on Windows.
- `python -m compileall -q .` -> passed (no output).
- `python -m ruff check .` -> **All checks passed!**
- `grep -rn "print(" . --include=*.py` -> only the two `self.printr.print(..., server_only=True)` lines (source + release). No bare `print()`.
- `@tool` count -> 2 in `main.py`; `auto_activate: false` in `default_config.yaml`.
- Source/release parity diff for `main.py`, `satisfactory_workspace.py`, `satisfactory_active_save.py`, `satisfactory_models.py`, `satisfactory_reference.py`, `default_config.yaml` -> all identical.
- End-to-end demo (skill module + workspace):
  - `complete_todo` on a goal id -> `(None, "complete_todo needs a todo id (todo_...), not 'goal_...'.")`; on a todo id -> `('todos', None)`.
  - `archive_item` on `chg_x` -> `(None, "archive_item needs a note, todo, goal, or flow id, not 'chg_x'.")`; on `flow_x` -> `('flows', None)`.
  - `set_status_for_kind("todos", goal_id, "archived")` -> `False`, goal status stays `open` (no cross-file mutation).

Deviations and decisions:

- Kept and hardened the generic `set_status` rather than deleting it: its body is replaced with prefix-safe delegation, so the unsafe search-all behavior is gone (no dead code) while existing tests that call it remain valid. The tool no longer relies on it - the adapter calls `set_status_for_kind` with an explicitly resolved kind.
- Record-type gating lives in the pure `_resolve_status_target` so it is unit-testable without a live Wingman runtime; the async tool is a thin caller. This is consistent with the skill's established pattern (`test_config_coercion.py` already `importorskip`s `main` and tests pure helpers).
- `archive_item` rejects `chg_` ids per the packet (change-log entries are append-only audit history).

Known limitations / risks:

- Prefix-based kind inference is intentional for this JSONL stage; a later typed store may replace it with explicit record tables.
- Not re-verified against a live Wingman tool call this pass (no app runtime); the gating decision and single-file mutation are covered by the pure adapter + workspace tests and the demo above.

### Quality control (Codex)

Diff reviewed: `main.py`, `satisfactory_workspace.py`, `tests/test_workspace.py`,
`tests/test_config_coercion.py`, and matching `release_version` runtime copies
for SSP-P0-W02.

Independent verification:

- `python -m pytest skills\satisfactory_assistant\tests -q` -> 68 passed, 1 skipped
- `python -m compileall -q skills\satisfactory_assistant` -> passed
- `python -m ruff check skills\satisfactory_assistant` -> All checks passed; ruff reported an access-denied cache write warning only
- `rg "print\(" skills\satisfactory_assistant -g "*.py"` -> only `self.printr.print(..., server_only=True)` in source and release `main.py`
- SHA-256 source/release parity for `main.py`, `satisfactory_workspace.py`, `satisfactory_active_save.py`, `satisfactory_models.py`, `satisfactory_reference.py`, and `default_config.yaml` -> all OK
- Tool count check -> 2 tools in source and release
- `auto_activate` check -> `false` in source and release

Acceptance evidence:

- `complete_todo` now resolves a single target kind and only accepts `todo_` ids before mutating.
- `archive_item` resolves notes, todos, goals, and flows by id prefix, rejects `chg_` audit records and unknown ids, and mutates only the inferred JSONL file.
- `set_status_for_kind()` updates one requested record kind only; tests cover cross-file no-mutation and unknown-kind rejection.
- The legacy `set_status()` path no longer scans every JSONL file; it infers kind from the id prefix and delegates to the single-kind helper.
- Existing SSP-P0-W01 metadata and clearing tests still pass, and source/release parity was maintained.

Findings:

- None.

Residual risk:

- Prefix-based status targeting is appropriate for the JSONL journal stage, but later typed persistence should replace it with explicit record tables.
- Live Wingman tool calls remain outside this package's automated QC environment and are still tracked as a separate manual verification gap.

### Gate decision

- Decision: `ACCEPTED`
- Next owner: Codex
- Next action: SSP-P0-W03 opened as the next Phase 0 package.
- User acceptance: accepted in chat on 2026-06-26.
---

## 2026-06-25 - SSP-P0-W01 - Flow metadata round-trip and explicit clearing

- Roadmap phase: Phase 0 - Correct the journal contract
- Owner: Codex after user G3 acceptance
- Status: `ACCEPTED`
- Attempt: 2
- Baseline revision: `15d0e64`
- Baseline checks:
  - `python -m pytest skills\satisfactory_assistant\tests -q` -> 48 passed, 1 skipped
  - `python -m compileall -q skills\satisfactory_assistant` -> passed
  - `python -m ruff check skills\satisfactory_assistant` -> passed; ruff reported an access-denied cache write warning only
  - `rg "print\(" skills\satisfactory_assistant -g "*.py"` -> only `self.printr.print(..., server_only=True)` in source and release copy
- Pre-existing changes:
  - `git status --short` already shows many modified `skills/sc_*` files, untracked scratch/Claude artifacts, and the untracked `skills/satisfactory_assistant/` tree. This package must not touch unrelated files.
- Plan references:
  - `SatisfactorySkillPlan.md` sections 3, 5.1, 11, and 12 Phase 0
  - `codexsatisfactoryreview.md` findings F-02 and F-19

### Implementation packet (Codex)

Objective: make the current JSONL journal honor the documented production-flow fields before the typed planner replaces legacy flows. A flow's `area`, `recipe`, `machines`, `constraints`, `inputs`, `outputs`, `status`, and `details` must survive add, update, summary, and context rendering, with a separate explicit way to clear optional fields.

In scope:

- Extend the existing two-tool surface only; do not add a new tool.
- Add optional `area`, `recipe`, `machines`, and `constraints` parameters to `update_satisfactory_plan`.
- Add an explicit `clear_fields` parameter for `update_flow`. Empty strings must continue to mean "leave unchanged"; clearing must be opt-in through this allowlisted parameter.
- Allow clearing only these fields: `details`, `area`, `recipe`, `machines`, `constraints`, `inputs`, and `outputs`.
- Store the new flow fields in `flows.jsonl` as compact strings. Store `inputs` and `outputs` as lists, as today.
- Include the new fields in `SaveWorkspace.summary()` and `format_context()` in a compact, bounded way.
- Treat malformed legacy records defensively: missing fields, non-list `inputs`/`outputs`, or non-string metadata must not crash summaries or formatting.
- Keep legacy JSONL backward compatible; do not migrate or rewrite old records unless an update targets a specific record.
- Maintain source/release parity after source tests pass.

Out of scope:

- No Docs parsing, recipe database, dependency graph, solver, SQLite store, `.sav` parser, install discovery, or live game-data lookup.
- No new config properties or Core API/interface changes.
- Do not split workflow status from calculated status in this package; that is a separate Phase 0 package.
- Do not change active-save resolver behavior or workspace identity hashing in this package.
- Do not broaden filesystem access or add background polling.

Expected files:

- `skills/satisfactory_assistant/main.py`
- `skills/satisfactory_assistant/satisfactory_workspace.py`
- `skills/satisfactory_assistant/tests/test_workspace.py`
- `skills/satisfactory_assistant/tests/test_config_coercion.py` or a new focused test module if tool-level adapter tests are clearer
- Matching files under `skills/satisfactory_assistant/release_version/` after source verification passes
- `skills/satisfactory_assistant/DEVLOG.md` implementation-result section

Data contract:

- `add_flow` persists `area`, `recipe`, `machines`, `constraints`, `inputs`, `outputs`, `status`, and `details`.
- `update_flow` updates only supplied non-empty fields, except fields named in `clear_fields`.
- `clear_fields` accepts comma or semicolon separators and rejects unknown field names with a short error.
- Clearing `inputs` or `outputs` sets the stored value to an empty list. Clearing string metadata sets it to an empty string or removes the key, but summaries must return an empty string either way.
- Existing records without the new keys remain readable.

Acceptance criteria:

- A production flow with all documented metadata round-trips through storage, `summary()`, and `format_context()`.
- `update_flow` can modify each new metadata field without changing omitted fields.
- `update_flow` can explicitly clear `details`, `area`, `recipe`, `machines`, `constraints`, `inputs`, and `outputs`.
- Unknown `clear_fields` values produce a concise error and do not mutate the flow.
- Malformed legacy records do not crash summary or context rendering.
- Context remains under the existing hard budget with metadata-heavy flows.
- Tool count remains two and `auto_activate` remains `false`.
- No bare `print()` is introduced; runtime logging continues through `Printr`.
- Source and `release_version` copies match for changed runtime files.

Required verification:

- `python -m pytest skills\satisfactory_assistant\tests -q`
- `python -m compileall -q skills\satisfactory_assistant`
- `python -m ruff check skills\satisfactory_assistant`
- `rg "print\(" skills\satisfactory_assistant -g "*.py"`
- A targeted source/release parity check for changed runtime files.

Risks and assumptions:

- Adding five optional tool parameters increases schema size. Keep descriptions concise and do not add a third tool in this package.
- This remains a Wingman skill, not MCP, under the locked plan decision because it uses Wingman config, generated files, and active-save scoped local state. If that product decision changes, pause before implementation.
- Existing release packaging is manual; do not create commits, PRs, or install artifacts for this package.

### Implementation result (Claude)

Summary: extended the existing two-tool surface so a production flow's documented
metadata (`area`, `recipe`, `machines`, `constraints`) round-trips through
storage, `summary()`, and `format_context()`, and added an explicit, allowlisted
`clear_fields` mechanism so optional fields can be reset without overloading the
"empty means leave unchanged" convention. No third tool was added; `auto_activate`
stays `false`. Built test-first (TDD): 10 new workspace tests written and watched
fail (import/`TypeError`/`ValueError` for missing features) before implementing.

Changed files (all inside the untracked `skills/satisfactory_assistant/` tree):

- `satisfactory_workspace.py`
  - New `CLEARABLE_FIELDS` allowlist (`details, area, recipe, machines, constraints, inputs, outputs`; deliberately excludes `title` and `status`) and `_FLOW_META_FIELDS`.
  - New `parse_clear_fields(raw)`: comma/semicolon separated, case-insensitive, raises `ValueError` naming unknown fields; empty input -> empty set.
  - New defensive coercers `_as_list` / `_as_str` used across `matches`, `shape_flow`, and `is_blocked` so non-list `inputs`/`outputs` (or `null`) and non-string metadata in legacy records cannot crash rendering. (The pre-existing `list(record.get("outputs", []))` crashed on an explicit `null`; now fixed.)
  - `update_flow` gains `area`, `recipe`, `machines`, `constraints`, and `clear_fields`. Non-empty strings update; empty strings still mean leave unchanged; clears are applied last (explicit clear wins over a set in the same call) and restricted to `CLEARABLE_FIELDS`.
  - `shape_flow` now returns the four metadata fields (clipped to `_META_MAX=80`); `_flow_line` renders them compactly (`@area` prefix plus an only-if-present `{recipe: ...; machines: ...; constraints: ...}` block).
  - `summary()` focus search now also matches the metadata fields.
- `main.py`
  - `update_satisfactory_plan` gains `area`, `recipe`, `machines`, `constraints`, `clear_fields` parameters with concrete docstring guidance. `add_flow` persists the four metadata strings; `update_flow` parses `clear_fields` (returning the concise `ValueError` text to the user on an unknown field, before any mutation). Tool count stays two.
- `tests/test_workspace.py`
  - 10 new tests: all-metadata persistence; metadata round-trip through `format_context`; per-field `update_flow` sets; empty-string-leaves-unchanged; clearing string metadata; clearing `inputs`/`outputs` to `[]`; `parse_clear_fields` separators and unknown-field rejection; malformed-legacy-record no-crash; context-within-budget with metadata-heavy flows.
- `release_version/` runtime copies regenerated via `update_release.py`.

Exact commands and results (run from `skills/satisfactory_assistant/`):

- `python -m pytest tests -q` -> **58 passed, 1 skipped** (baseline was 48 passed, 1 skipped; +10 new tests). Skip is the POSIX-only containment test on Windows.
- `python -m compileall -q .` -> passed (no output).
- `python -m ruff check .` -> **All checks passed!**
- `grep -rn "print(" . --include=*.py` -> only the two `self.printr.print(..., server_only=True)` lines (source + release). No bare `print()`.
- Source/release parity diff for `main.py`, `satisfactory_workspace.py`, `satisfactory_active_save.py`, `satisfactory_models.py`, `satisfactory_reference.py`, `default_config.yaml` -> all identical.
- `@tool` count -> 2 in both source and release `main.py`; `auto_activate: false` in both `default_config.yaml`.
- End-to-end demo: a fully-populated flow renders as
  `... Steel beam line @Northern Forest: Steel Beam 360/min (in: Iron Ore 240/min, Coal 240/min) [planned] {recipe: Steel Beam (Foundry); machines: Foundry x8; Constructor x4; constraints: power<=200MW}`;
  `clear_fields={"area","inputs"}` -> `area='' inputs=[]` with `recipe` untouched;
  `parse_clear_fields("inputs, title")` -> `ValueError: Cannot clear unknown field(s): title. Allowed: details, area, recipe, machines, constraints, inputs, outputs.`

Deviations and decisions:

- Clear-field validation lives once in `parse_clear_fields` (pure, unit-tested); `main.py` calls it and returns the message before invoking `update_flow`, so an unknown field never mutates the flow. `update_flow` also intersects `clear_fields` with `CLEARABLE_FIELDS` as defensive depth.
- Cleared string metadata is set to `""` (not key removal); summaries return `""` either way, as the packet allows.
- Tool-level behavior is exercised through the pure workspace layer plus the demo above rather than a new app-dependent async test, matching this skill's established pattern (`main.py` imports the Wingman app; `test_config_coercion.py` already `importorskip`s it and tests only pure helpers).

Known limitations:

- Metadata remains opaque compact strings; typed items/recipes/machine counts and calculated balanced/blocked states are explicitly out of scope here (later phases per the plan).
- Not re-verified against a live install this pass (no resolver/active-save changes in this package); the prior live check `status=ok, save=megatime, session=Mallachi, found=True` still stands for the unchanged resolver path.

### Quality control (Codex)

Diff reviewed: `main.py`, `satisfactory_workspace.py`, `tests/test_workspace.py`, and matching `release_version` runtime copies for SSP-P0-W01.

Independent verification:

- `python -m pytest skills\satisfactory_assistant\tests -q` -> 58 passed, 1 skipped
- `python -m compileall -q skills\satisfactory_assistant` -> passed
- `python -m ruff check skills\satisfactory_assistant` -> All checks passed
- `rg "print\(" skills\satisfactory_assistant -g "*.py"` -> only `self.printr.print(..., server_only=True)` in source and release `main.py`
- SHA-256 source/release parity for `main.py`, `satisfactory_workspace.py`, `satisfactory_active_save.py`, `satisfactory_models.py`, `satisfactory_reference.py`, and `default_config.yaml` -> all OK
- Tool count check -> 2 tools in source and release
- `auto_activate` check -> `false` in source and release

Acceptance evidence:

- `area`, `recipe`, `machines`, and `constraints` are accepted by the adapter, persisted on `add_flow`, updateable through `update_flow`, included in `summary()`, and rendered in `format_context()`.
- `clear_fields` parsing accepts comma/semicolon separators, rejects unknown names before adapter mutation, and clears string metadata plus `inputs`/`outputs` through the workspace path.
- Malformed legacy `inputs`/`outputs` and non-string metadata are coerced defensively in summaries and context formatting.
- Context budget tests cover metadata-heavy blocked flows and remain bounded.
- Source/release parity was maintained.

Findings:

- Medium - flow `details` do not round-trip through summary or context rendering. The work-package objective required `area`, `recipe`, `machines`, `constraints`, `inputs`, `outputs`, `status`, and `details` to survive add, update, summary, and context rendering. `SaveWorkspace.add_item()` stores `details`, and `update_flow()` can update or clear it, but `summary().shape_flow()` omits `details`, and `_flow_line()` renders no details. The new tests assert the four new metadata fields but do not assert `details` in summary or context. Impact: the player's original wording remains hidden from the compact planning context, so one documented flow field still fails the round-trip contract. Required correction: include a clipped `details` field in `shape_flow()`, render it compactly in `_flow_line()` only when present, and add tests proving details appear in `summary()` and `format_context()` and disappear after explicit `clear_fields={"details"}` while preserving the existing global context budget.

Residual risk:

- The added optional tool parameters increase schema size, but tool count remains two and the skill remains on-demand.
- `complete_todo` / `archive_item` record-type enforcement is still a later Phase 0 package, not part of SSP-P0-W01.

### Gate decision (attempt 1)

- Decision: `CHANGES_REQUESTED`
- Next owner: Claude
- Next action: fix the Medium finding above under the same package ID, increment the attempt number to 2 in this entry, update the Implementation result with exact changed files and command results, then return with `READY_FOR_CODEX_QC`.

### Implementation result (Claude) - attempt 2 (fix Medium: details round-trip)

Fixed the Medium QC finding: flow `details` now round-trips through `summary()`
and `format_context()`. Built test-first - added the failing assertions, watched
them fail with `KeyError: 'details'`, then implemented.

Changed files (all inside the untracked `skills/satisfactory_assistant/` tree):

- `satisfactory_workspace.py`
  - New `_DETAILS_MAX = 160` cap (Phase 0 plan requires bounded details).
  - `shape_flow()` now returns a clipped `details` field, so flow details are visible in `summary()["flows"]` / `["blocked_flows"]`.
  - `_flow_line()` appends `details: ...` to the only-if-present `{...}` metadata block, so details render in `format_context()` only when set, keeping quiet flows terse and honoring the existing global character budget.
- `tests/test_workspace.py`
  - `test_flow_details_round_trip_through_summary_and_context` - details appear in both `summary()` and `format_context()`.
  - `test_flow_details_are_bounded_in_summary` - a 400-char details string is clipped to <= 160 in the summary shape.
  - `test_update_flow_clears_string_metadata` strengthened to also assert `details == ""` after `clear_fields={"details"}`.
- `release_version/` runtime copies regenerated via `update_release.py`.

Exact commands and results (run from `skills/satisfactory_assistant/`):

- `python -m pytest tests -q` -> **60 passed, 1 skipped** (attempt 1 was 58/1; +2 details tests). Skip is the POSIX-only containment test on Windows.
- `python -m compileall -q .` -> passed (no output).
- `python -m ruff check .` -> **All checks passed!**
- `grep -rn "print(" . --include=*.py` -> only the two `self.printr.print(..., server_only=True)` lines (source + release). No bare `print()`.
- Source/release parity diff for `main.py`, `satisfactory_workspace.py`, `satisfactory_active_save.py`, `satisfactory_models.py`, `satisfactory_reference.py`, `default_config.yaml` -> all identical.
- End-to-end demo: a flow with details renders as
  `... Steel line: Steel Ingot 360/min [planned] {recipe: Solid Steel Ingot; details: use the alternate Solid Steel recipe}`;
  after `clear_fields={"details"}` -> `details='' (recipe still 'Solid Steel Ingot')`.

Deviations and decisions:

- Details are rendered inside the same compact `{...}` block as recipe/machines/constraints rather than as a separate line, keeping flow lines single-line and bounded. Details are clipped to 160 chars at the summary boundary; the global `format_context` budget still truncates sections, so metadata-heavy flows with details stay under the hard limit.
- Scope held to flow `details` (the package's documented flow contract). Surfacing `details` for notes/todos/goals is the broader F-03 finding and remains out of scope for this package.

### Quality control (Codex) - attempt 2

Diff reviewed: attempt-2 changes in `satisfactory_workspace.py`,
`tests/test_workspace.py`, matching `release_version` copy, and the updated
handover entry.

Independent verification:

- `python -m pytest skills\satisfactory_assistant\tests -q` -> 60 passed, 1 skipped
- `python -m compileall -q skills\satisfactory_assistant` -> passed
- `python -m ruff check skills\satisfactory_assistant` -> All checks passed; ruff reported an access-denied cache write warning only
- `rg "print\(" skills\satisfactory_assistant -g "*.py"` -> only `self.printr.print(..., server_only=True)` in source and release `main.py`
- SHA-256 source/release parity for `main.py`, `satisfactory_workspace.py`, `satisfactory_active_save.py`, `satisfactory_models.py`, `satisfactory_reference.py`, and `default_config.yaml` -> all OK
- Tool count check -> 2 tools in source and release
- `auto_activate` check -> `false` in source and release

Acceptance evidence:

- The attempt-1 Medium finding is fixed: `shape_flow()` now includes clipped flow `details`, `_flow_line()` renders details only when present, and tests cover summary/context round-trip plus the bounded summary shape.
- The strengthened clear test proves `clear_fields={"details"}` yields an empty summary value while preserving the explicit-clear contract.
- Existing metadata, clearing, malformed-record, context-budget, tool-count, on-demand activation, logging, and source/release parity criteria remain satisfied.

Findings:

- None.

Residual risk:

- Flow metadata remains compact free text until later typed-planner phases.
- Live Wingman tool calls remain outside this package's automated QC environment and are still tracked as a separate manual verification gap.

### Gate decision

- Decision: `QC_PASSED`
- Next owner: User
- User acceptance: ACCEPTED on 2026-06-25.
- Next action: SSP-P0-W02 opened as the next Phase 0 package.

---

## 2026-06-17 - Review pass 5 (global output budget, ack clip, ASCII)

### Medium - default context could still exceed the token target (FIXED)

Added a pure `format_context(header_lines, summary, char_budget=2800)` in
`satisfactory_workspace.py`. It (a) shows blocked flows only once - they are
removed from the "Production flows" section since they have their own
"Blocked / missing inputs" section - and (b) appends sections only while they
fit a hard global character budget (~700 tokens), then adds a single
"(more items not shown...)" note. `get_satisfactory_context` now builds header
lines and delegates rendering to it. Test added:
`test_format_context_stays_within_budget_and_dedupes` (12 blocked flows at
default caps -> <= 3000 chars, no duplicated ids), plus
`test_format_context_empty_workspace`.

### Medium - write-tool acks echoed unbounded titles (FIXED)

`update_satisfactory_plan` now clips the echoed title to 60 chars
(`_ACK_TITLE_MAX`) in the acknowledgement string while storing the full title
unchanged. Uses the shared `clip` helper.

### Low - non-ASCII ellipsis marker (FIXED)

`clip` now uses ASCII `"..."` instead of the Unicode ellipsis, matching the
repo's ASCII-default rule. `_clip` was renamed to public `clip` (shared by the
workspace summary and the write-ack path). Test added:
`test_clip_uses_ascii_marker_and_limit`. Confirmed no `â€¦` remains in any source.

### Verification (pass 5)

- `python -m pytest ... -q` -> **45 passed, 1 skipped**
- `ruff` / `compileall` -> passed; import OK; no bare `print(`; no Unicode ellipsis
- Live install re-check -> `status=ok, save=megatime, session=Mallachi, found=True`

---

## 2026-06-17 - Review pass 4 (status focus, field caps, delimiter parse)

### Medium - status-focused context hid the flows it should return (FIXED)

`matches()` now includes the record `status` in the searchable text, and adds a
`missing` alias that surfaces flows with an output target but no inputs. So
`focus="blocked"` returns blocked flows, `focus="balanced"` returns balanced
ones, etc. Tests added: `test_focus_blocked_returns_blocked_flows`,
`test_focus_balanced_returns_balanced_flow`,
`test_focus_missing_alias_surfaces_inputless_flows`.

### Medium - return size capped by count but not field length (FIXED)

Added hard per-field caps at the summary boundary: titles clipped to 80 chars,
each material-rate string to 48 chars, and at most 6 inputs/outputs per flow
(with a `(+N more)` marker). A single verbose title/material can no longer blow
the sub-800-token budget. Test added: `test_summary_caps_field_lengths`.

### Low - travel parser could absorb unknown tokens (FIXED)

`_parse_travel_tokens` now does true delimiter-based parsing: split the travel
string on `?`, then split each chunk on the first `=`. An unknown intervening
token (e.g. `?Foo=1` between `loadgame` and `sessionName`) is ignored instead of
being absorbed into the save name. Removed the now-unused `_TRAVEL_KEYS`. Test
added: `test_parser_ignores_unknown_intervening_token`. Verified the live log
still resolves `megatime` / `Mallachi`.

### Verification (pass 4)

- `python -m pytest ... -q` -> **42 passed, 1 skipped**
- `ruff` / `compileall` -> passed; import OK; no bare `print(`
- Live install re-check -> `status=ok, save=megatime, session=Mallachi, found=True`

---

## 2026-06-17 - Review pass 3 (streaming detection + save-lookup hardening)

### Medium - large logs could miss a middle-only switch (FIXED)

Removed head/tail sampling and the 8 MiB ceiling entirely. The newest log is now
streamed **line-by-line** (`extract_active_save_from_lines`, O(1) memory) so a
save switch is detected wherever it occurs, regardless of log size.
`extract_active_save_reference(text)` is kept as a thin wrapper over the line
stream for in-memory callers/tests.

- Consequence: the `max_log_bytes` custom property is now obsolete (streaming is
  both correct and memory-bounded) and has been **removed** from
  `default_config.yaml`, `validate()`, and the resolver signature.
  `resolve_active_save(configured_dir=...)` no longer takes `max_log_bytes`.
  Flagging for Codex/plan reconciliation since the property was in PROJECT_PLAN.
- Test added: `test_resolve_mid_log_switch_in_large_log` (newer `loadgame=`
  ~5000 lines deep, more filler after, no later backup -> still resolved).

### Low - resolve_save_file could raise on filesystem errors (FIXED)

Wrapped the `SaveGames` scan (is_dir / iterdir / is_file / resolve) in narrow
`OSError` handling; returns `None` so a permission error or a profile dir
removed mid-scan yields "active identity found, save file not found" instead of
bubbling out of the tool. Tests added: `test_resolve_save_file_survives_oserror`
(iterdir raises) and `test_resolve_full_flow_with_unresolvable_save`.

### Verification (pass 3)

- `python -m pytest ... -q` -> **37 passed, 1 skipped**
- `ruff` / `compileall` -> passed; import OK; no bare `print(`
- Live install re-check -> `status=ok, save=megatime, session=Mallachi, found=True`

---

## 2026-06-17 - Full review response (addressed updated Review.md)

Codex did a full code review (not just a re-check). All findings addressed.

### High - resolver could choose a stale save (FIXED)

The extractor previously prioritized source TYPE (any `loadgame=` first) over
chronology, so after a mid-session save switch it returned the old save (old
travel URL) instead of the new one (newer backup line). `extract_active_save_reference`
now does a single bottom-up pass and returns the newest recognized reference,
whether a travel URL or a backup line. When the newest reference is a backup
line (no session), session is back-filled from the most recent travel URL that
names the same save. Also switched `read_relevant_text` to read the WHOLE file
when within 8 MiB (head+tail only for pathologically large logs), so a
mid-session reload cannot be missed.
Tests added: `test_extract_newer_backup_beats_older_travel_url` (Codex's
reproducer), `test_extract_backfills_session_from_matching_travel_url`.

### Medium - focused context could miss matching records (FIXED)

`SaveWorkspace.summary` now takes a `focus` argument and filters across title,
details, inputs, and outputs BEFORE capping to `max_items`. `get_satisfactory_context`
passes `focus` through instead of filtering after truncation. Test added:
`test_focus_filters_before_truncation`, `test_focus_matches_flow_inputs_and_outputs`.

### Medium - containment fallback unsafe on case-sensitive FS (FIXED)

`_is_within` now applies the lowercased-string fallback ONLY on Windows
(`os.name == "nt"`); on POSIX it relies on case-sensitive `relative_to`, so a
case-different sibling (`.../Saves` vs `.../saves`) is not treated as contained.
Test added (POSIX-only, skipped on Windows):
`test_containment_rejects_case_only_sibling_on_posix`.

### Low - fixed

- `max_log_bytes` hint updated to describe head/tail-of-large-log behavior.
- Discovery keywords expanded: `recipe, inputs, outputs, materials, factory
  rates, bottleneck, machine count`.
- Helper modules renamed to avoid generic `sys.modules` collisions (another
  skill ships a top-level `models.py`): `models.py -> satisfactory_models.py`,
  `active_save.py -> satisfactory_active_save.py`,
  `workspace.py -> satisfactory_workspace.py`. (Relative imports are not an
  option: release loads skills via `spec_from_file_location` with no package
  context, so absolute top-level imports are required.)

### Remaining-risk item also addressed

- Log rotation/disappearance between `newest_log` and read is now caught:
  `resolve_active_save` returns `no_active_save` instead of letting an `OSError`
  escape.

### Verification (full review-response pass)

- `python -m pytest skills/satisfactory_assistant/tests -q` -> **35 passed, 1 skipped**
  (skip is the POSIX-only containment test on Windows)
- `ruff check` -> All checks passed
- `compileall` -> passed
- import check -> OK
- bare `print(` scan -> none
- Live install re-check -> `status=ok, save=megatime, session=Mallachi, found=True`

---

## 2026-06-17 - Review response (addressed Review.md findings)

Codex review in `Review.md` raised three findings; all addressed.

### High - active-save detection in long sessions (FIXED)

Replaced tail-only reading with a **head + tail** read (`active_save.py`,
`read_relevant_text`). The `loadgame=` travel URL is logged at session start
(top of file), so the head always covers it; the tail still catches recent
reloads and backups. The existing bottom-up extractor then picks the latest
reference. Small logs are read whole.

- Bonus: this also recovers `session_name` on the live install (previously
  `None` because the load line was outside the 1 MB tail). Re-check now returns
  `save=megatime, session=Mallachi`.
- Added regression test `test_resolve_loadgame_beyond_tail_no_backup_line`:
  load line at the top, >2x `max_bytes` of filler, no backup line, small
  `max_log_bytes` -> still resolves via the head.

### Medium - glob metacharacters in save names (FIXED)

`resolve_save_file` no longer globs the untrusted save name. It iterates profile
directories and checks `(profile / "<name>.sav").is_file()` directly, so names
like `Factory [1].sav` resolve correctly. Added test
`test_resolve_save_name_with_glob_metacharacters`.

### Low - config coercion bounds (FIXED)

Added `_coerce_int` (falls back to default on non-numeric, clamps to a minimum)
and `_coerce_bool` (parses strings explicitly, fixing `bool("false") is True`).
`max_log_bytes` clamps to >= 4096, `max_response_items` to >= 1. Added
`tests/test_config_coercion.py` (skips gracefully if the app isn't importable).

### Verification (review-response pass)

- `python -m pytest skills/satisfactory_assistant/tests -q` -> **31 passed**
- `ruff check` -> All checks passed
- Live install re-check -> `status=ok, save=megatime, session=Mallachi, found=True`

Product decisions from the review accepted as-is: keep the `status` param, keep
the "configured directory is an explicit override" behavior, keep multiplayer /
dedicated-server / Epic / Linux paths in TODO until tested.

---

## 2026-06-17 - MVP implementation (Phases 1-4 + tests)

Implemented the full MVP against `PROJECT_PLAN.md`, including the Crafting
Planning Model (production flows) added in the plan's second revision.

### Files delivered

```
skills/satisfactory_assistant/
|-- main.py                       SatisfactoryAssistant(Skill): 2 tools, just-in-time config
|-- default_config.yaml           auto_activate:false, custom props, prompt + discovery
|-- logo.png                      PLACEHOLDER (generated orange factory silhouette)
|-- satisfactory_models.py        pure dataclasses (ActiveSaveResult, ActiveSaveReference)
|-- satisfactory_active_save.py   pure resolver (no Wingman imports)
|-- satisfactory_workspace.py     pure per-save JSONL workspace + containment guards
|-- tests/
    |-- conftest.py               puts skill dir on sys.path
    |-- test_active_save.py       resolver tests
    |-- test_workspace.py         workspace + flow tests
    |-- test_config_coercion.py   config parsing tests
```

NOTE: helper modules were later renamed with a `satisfactory_` prefix (see the
full-review-response entry above) to avoid generic `sys.modules` collisions.

`models.py`, `active_save.py`, and `workspace.py` are intentionally free of any
Wingman imports so the resolver/workspace logic unit-tests fast without the app.
`main.py` is the thin Wingman-facing wrapper.

### Verification (evidence)

- `python -m pytest skills/satisfactory_assistant/tests -q` -> **26 passed**
- Import check: `skills.satisfactory_assistant.main` imports OK (decorators +
  `api.interface` / `api.enums` / `skills.skill_base` all resolve)
- `ruff check skills/satisfactory_assistant` -> **All checks passed**
- Bare `print(` scan -> none (only `self.printr`)
- **Live install test** (auto-detect, no configured dir): resolver returns
  `megatime`, finds
  `...\SaveGames\76561197976172126\megatime.sav`, from `FactoryGame.log`.

### Ground truth captured from a real install

Verified against `C:\Users\larse\AppData\Local\FactoryGame\Saved` (FactoryGame
4.x). Real layout and signals:

- Logs: `Logs\FactoryGame.log` (live, newest while running) and rotated
  `Logs\FactoryGame-backup-<date>.log`.
- Saves: `SaveGames\<steam-or-epic-id>\<SaveName>.sav`.
- **The load is recorded in an Unreal travel URL**, e.g.:
  `...?loadgame=megatime?sessionName=Mallachi?SessionDefinition=SessionDef_SinglePlayer`
  - `?` is the token delimiter; values are written **literally** (spaces
    allowed, never URL-encoded), e.g. `loadgame=Dessert life?sessionName=...`.
  - Save file name (`loadgame`) and in-game session name (`sessionName`) differ;
    autosaves are named after the **session** (`Mallachi_autosave_*`) while the
    file is `megatime.sav`.
- Secondary signal: the game's own (misspelled) line
  `LogGame: Succesfully saved a local backup with name: megatime-<date>.sav`.

### Key design decisions / deviations from the plan

1. **Resolver is built on the `loadgame=` / `sessionName=` travel-URL token**,
   not the plan's generic ".sav-path regex" strategy. Real load lines never
   contain a `.sav` path; they use this structured query token. Parsing is done
   by locating `loadgame=` and reading the value up to the next known travel key
   (robust to spaces) rather than a fragile regex. The misspelled local-backup
   line is the **secondary fallback** when no travel URL is in the tail.

2. **`satisfactory_saved_dir` is an explicit override**, not pooled with common
   locations. When set, only that directory is scanned (auto-detect skipped), so
   the skill never wanders into a different install. Auto-detect runs only when
   the config is empty. The plan's wording implied "config + common locations"
   together; this is stricter and deterministic.

3. **Added an optional `status` param to `update_satisfactory_plan`.** The
   plan's tool sketch added `inputs`/`outputs` for flows but exposed no way to
   set a flow's status (planned/building/blocked/balanced). Since the Definition
   of Done asks "which lines are blocked?", `status` (validated against
   `FLOW_STATUSES`) makes those states reachable via `add_flow`/`update_flow`.
   Cost ~10 schema tokens. Easy to drop if Codex wants the sketch verbatim.

### Production flows (Crafting Planning Model)

- Stored in `flows.jsonl` with `inputs`/`outputs` as lists, plus `status` from
  `planned / building / blocked / balanced / done / archived`.
- `add_flow` / `update_flow` actions; `inputs`/`outputs` arrive as
  semicolon-separated material-rate strings (`Iron Ore 240/min; Coal 240/min`)
  and are parsed into lists. Original wording is preserved in `details`.
- `get_satisfactory_context` renders compact flow lines
  (`title: outputs (in: inputs) [status]`) and a "Blocked / missing inputs"
  section. A flow is treated as blocked if `status == "blocked"` OR it has an
  output target but no known inputs ("missing materials").

### Behavior notes for the reviewer

- **Tail gap in long sessions:** the `loadgame=` line sits near the *top* of the
  log; in a 2 MB+ session it falls outside the default 1 MB tail. On the live
  test the resolver fell back to the backup line, so `save_name` was correct but
  `session_name` was `None`. Save-name detection stays robust via the backup
  fallback; session-name is best-effort. See TODO for the open question.
- No files created outside `skills/`. Nothing committed (skill release flow is
  user-managed).













