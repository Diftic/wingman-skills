# Satisfactory Assistant Progressive Factory Plan

Status: Proposed  
Created: 2026-06-24  
Scope: `skills/satisfactory_assistant/`

This plan combines the current journal foundation in [`PROJECT_PLAN.md`](PROJECT_PLAN.md), the audit and target architecture in [`codexsatisfactoryreview.md`](../../codexsatisfactoryreview.md), and the installed Docs and solver research in [`claudesatisfactoryreview.md`](../../claudesatisfactoryreview.md).

For post-MVP work, this document supersedes the future-enhancement sections of `PROJECT_PLAN.md`. The original remains the historical contract for the implemented journal.

## 1. Product outcome

Evolve the save-scoped journal into a deterministic planner for one factory that expands through all five Project Assembly phases.

The planner works backward from the final Space Elevator delivery and builds forward through the player's available technology. The current production benchmark is always the upcoming Project Assembly phase. Earlier capacity must be reused, expanded, upgraded, reconfigured, or retired explicitly rather than treating every phase as an unrelated factory.

The end state is a connected factory capable of producing every component required for Project Assembly Phase 5 within the selected completion window.

Retain the existing:

- Active-save resolver and newest-log contract.
- Per-save isolation and filesystem containment.
- On-demand activation and compact responses.
- Just-in-time configuration handling.
- Cross-platform defensive behavior.
- Release packaging structure.

## 2. Progression and scale contract

### 2.1 Terms

- **Project Assembly phase**: one of the five Space Elevator delivery stages.
- **HUB tier gate**: a capability boundary that controls which recipes, buildings, logistics, extraction, and power technologies may be used.
- **Production gate checkpoint**: the recalculation and build decision made when a HUB tier gate opens.
- **Stage plan**: the factory design used to complete one Project Assembly phase.
- **Master plan**: the connected Phase 1 through Phase 5 expansion plan.

HUB tiers are not production-scale measurements. A higher HUB tier does not imply a fixed throughput increase. It only opens a capability gate. Production scale is derived exclusively from the upcoming Project Assembly demand and selected pace.

Each planned process and transport option records its minimum required HUB tier or milestone. A stage plan must not use an option whose gate is closed. When a HUB tier gate opens, create a production gate checkpoint and recalculate the implementation choices for the same Project Assembly demand. The checkpoint may recommend upgrades, but must justify them through capacity, power, logistics, or reuse benefits. Opening a gate never increases target throughput by itself.

### 2.2 Project Assembly pace

| Project Assembly phase | Baseline production window | Slowest allowed window | Formula |
| ---: | ---: | ---: | ---: |
| 1 | 1 hour | 3 hours | `1 hour * pace_multiplier` |
| 2 | 2 hours | 6 hours | `2 hours * pace_multiplier` |
| 3 | 4 hours | 12 hours | `4 hours * pace_multiplier` |
| 4 | 8 hours | 24 hours | `8 hours * pace_multiplier` |
| 5 | 16 hours | 48 hours | `16 hours * pace_multiplier` |

`pace_multiplier` is configurable from `1.0` through `3.0`:

- `1.0` is the baseline target.
- Higher values trade completion speed for a smaller factory, lower throughput, and lower power demand.
- `3.0` is the maximum approved slowdown.
- Default to `1.0`.
- Never change the multiplier silently.
- The planner may recommend a slower feasible scenario, but never above `3.0`.
- Support a global multiplier first; add per-phase overrides for later scenarios.

The window initially measures steady-state production after the stage expansion is commissioned. Construction time is planned and reported separately.

### 2.3 Demand derivation

Read Project Assembly parts and quantities from installed game data. Do not hard-code them in prompts or solver code.

For each required part:

```text
required_rate_per_minute = required_delivery_quantity
                           / (phase_window_hours * 60)
```

All parts required by the upcoming phase form one demand set and are solved together. Project parts are finite delivery batches; their supporting factory modules are continuous capacity that can be retained for later phases.

### 2.4 Stage rules

- Use only technology whose HUB tier and milestone gates are open before planned production begins.
- Do not use technology unlocked by completing the upcoming Project Assembly phase to complete that phase.
- Default to standard recipes; alternates require confirmed unlock state or explicit approval.
- Prefer reuse and expansion over teardown.
- Reserve resources, logistics corridors, space, and power headroom for later phases where practical.
- After delivery, identify what remains active, becomes a stockpile line, is repurposed, or is retired.
- Use the final Phase 5 dependency envelope to inform early expansion decisions without forcing final scale during early phases.

## 3. Locked engineering decisions

| Topic | Decision |
| --- | --- |
| Product structure | Extend the existing skill in place. |
| Planning structure | One master plan with five revisioned stage plans. |
| Scale driver | Upcoming Project Assembly quantities and pace only. |
| HUB tiers | Capability stage gates only, never scale multipliers. |
| End goal | Sustainable production of every Phase 5 delivery component. |
| Skill vs MCP | Keep a Wingman skill because active-save scope and generated files require runtime access. |
| Activation | Keep `auto_activate: false`. |
| Tool count | Maximum three AI-callable tools. |
| Game data | Parse installed localized Docs JSON into a normalized, versioned dataset. |
| Solver | Pure deterministic domain layer using dependency expansion and linear programming. |
| Recipe availability | Standard by default; alternates require evidence or opt-in. |
| Persistence | Per-save SQLite with JSON and Markdown exports. |
| Legacy data | Import JSONL idempotently and preserve source files. |
| Save parsing | Optional later adapter, not a calculator dependency. |
| Dependencies | Add none; verify NumPy and SciPy in the packaged runtime. |
| Platforms | Windows, macOS, and Linux with guarded discovery. |
| Core API | No Core API/interface changes planned. |
| Delivery ownership | Codex owns planning and QC; Claude owns implementation. |
| Handover log | `DEVLOG.md` is the authoritative work-package and gate log. |

## 4. Planning method

### 4.1 Design backward, build forward

First establish the final Phase 5 dependency envelope. Then determine which parts can and should exist at each earlier capability gate.

Early stages should:

- Avoid consuming resources required by later chains without a reservation decision.
- Leave room for parallel machine blocks and upgraded logistics.
- Prefer reusable intermediate capacity.
- Record future miner, belt, pipe, machine, and power upgrade points.
- Avoid temporary complexity whose teardown cost exceeds its short-term value.

### 4.2 Incremental stage calculation

For every Project Assembly phase, calculate:

1. Required delivery quantities and configured window.
2. Derived rates for all required parts.
3. The HUB tier and milestone capability snapshot.
4. Inputs and capacity already supplied by the prior stage.
5. Incremental machines, extraction, logistics, and power.
6. Upgrades or reconfiguration of existing modules.
7. Construction materials and dependency-ordered build steps.
8. Commissioning checks and post-delivery transition.

### 4.3 Capacity classification

Distinguish delivery quantity, derived rate, permanent capacity, temporary phase capacity, construction/future stockpiles, reuse, expansion, upgrades, reconfiguration, idle capacity, and decommissioning.

### 4.4 Production gate checkpoints

Each HUB tier transition creates a checkpoint within the active Project Assembly stage:

1. Record the newly opened capabilities.
2. Recalculate the current phase using the unchanged delivery rates.
3. Compare the existing design with newly available machines, recipes, extraction, logistics, and power.
4. Emit only upgrades or construction that materially improve feasibility, reuse, or the selected optimization objectives.
5. Preserve the prior checkpoint as revision history.

A checkpoint changes the allowed solution space, not the production target.

### 4.5 Feasibility before optimization

First prove the stage can meet its targets with open capability gates. Then optimize reuse, resources, power, or machine count. Return diagnostics instead of inventing data or silently extending the deadline.

## 5. Target architecture

```text
Upcoming Project Assembly phase + pace multiplier
                         |
                         v
              Progression demand builder
                         |
                         v
HUB/milestone gates --> Candidate dependency graph <-- Normalized game data
                         |
Previous stage plan -----+----> Balance and LP solver
                         |              |
                         |              v
                         |      Validated stage graph
                         |              |
                         +----> Incremental expansion diff
                                        |
                     +------------------+------------------+
                     |                  |                  |
                     v                  v                  v
             Resources/power      Build sequence      Diagnostics
                     |                  |                  |
                     +------------------+------------------+
                                        |
                                        v
                              Per-save SQLite store
                                        |
                                        v
                             Summary + plan artifact
```

### 5.1 Pure modules

| Module | Responsibility |
| --- | --- |
| `satisfactory_install.py` | Configured, Steam, Epic, and platform install discovery. |
| `satisfactory_docs.py` | Docs decoding and Unreal value parsing. |
| `satisfactory_dataset.py` | Normalized entities, indexes, cache, signatures, and validation. |
| `satisfactory_plan_models.py` | Typed progression, quantities, plans, graphs, and diagnostics. |
| `satisfactory_progression.py` | Phase demands, capability gates, and stage transitions. |
| `satisfactory_solver.py` | Candidate expansion, balances, LP, machines, clocks, and power. |
| `satisfactory_store.py` | SQLite schema, migrations, revisions, and JSONL import. |
| `satisfactory_reports.py` | Compact responses and detailed artifacts. |

These modules must not import Wingman runtime classes. The existing adapter remains responsible for tools, active-save checks, configuration, and logging.

## 6. Installed game-data pipeline

### 6.1 Discovery

Use this order:

1. Explicit configured install or Docs directory.
2. Steam library discovery.
3. Epic metadata and guarded known paths.
4. Guarded platform fallbacks.

Support `<install>/CommunityResources/Docs/<locale>.json`. Default to `en-US.json`, permit an override, and detect encoding from the BOM. Missing or invalid Docs data disables calculation and lookup while leaving journal operations available.

### 6.2 Normalized data

Include:

- Items, fluids, and raw resources.
- Recipes, ingredients, products, duration, buildings, and alternate markers.
- Manufacturer power and clock curves.
- Extractor rates and power.
- Belt and pipe capacities.
- Schematics, HUB tiers, milestones, and unlock relationships.
- Project Assembly phases, required parts, and quantities.
- Construction recipes and costs for later phases.

Use stable Unreal class IDs internally. Localized names are labels and aliases only.

Parser rules:

- Parse `mIngredients` and `mProduct` structurally.
- Calculate base rate as `amount / duration_seconds * 60`.
- Normalize stored fluid amounts.
- Accept automatable recipes only when `mProducedIn` resolves to a supported building.
- Derive supported manufacturers from data and apply reviewed exclusions.
- Build explicit capability snapshots for HUB tier and milestone gates.

Amendment 2026-07-01 (verified against the installed Docs during
SSP-P1-W02 planning): the current Docs export contains no Project
Assembly or game-phase data (no FGGamePhase group, no phase schematics).
Phase delivery quantities therefore cannot be read from installed game
data as sections 2.3 and 6.2 assume. Resolution, approved by the user on
2026-07-01: bundle a reviewed, provenance-tagged phase-quantities data
file in the skill, validated at load against Docs item classes and
versioned per game patch. Tracked in the SSP-P1-W02 DEVLOG entry;
implementation lands with the capability/progression packets.

### 6.3 Cache and validation

Cache the installation-wide dataset using schema version, Docs path, locale, size, high-resolution modification time, and SHA-256 when metadata changes. Record provenance, parse time, version when available, counts, and warnings. Replace caches atomically.

Reject or diagnose duplicate IDs, unknown references, invalid units, non-positive durations, unsupported producers, broken unlock relationships, and phases with missing delivery quantities.

Amendment 2026-07-01 (approved by the user, evidence in the
SSP-P1-W04 DEVLOG entry): the on-disk dataset cache is replaced by
in-process memoization keyed by the Docs file signature. Measured full
parse time is 58 ms and SHA-256 of the file is 8 ms on the reference
machine, so a disk cache adds serialization, atomicity, and corruption
handling with no measurable benefit. Signature validation and provenance
recording are retained as specified above.

## 7. Typed model

Primary entities:

- `FactoryMasterPlan`
- `StagePlan`
- `ProjectAssemblyPhase`
- `PhaseDemandSet`
- `DemandTarget`
- `PacePolicy`
- `CapabilityGateSnapshot`
- `ProductionGateCheckpoint`
- `RecipePolicy`
- `ConstraintSet`
- `ProcessNode`
- `ResourceSource`
- `TransportLink`
- `BufferNode`
- `SinkNode`
- `PowerPlan`
- `ItemFlow`
- `BuildTask`
- `StageTransition`
- `Assumption`
- `Diagnostic`
- `DataProvenance`

Every stage records its phase, window, multiplier, delivery quantities, rates, capability gates, gate checkpoints, recipes, graph, resources, machines, logistics, power, reuse, additions, upgrades, temporary capacity, transition, and solver provenance.

Every flow edge records item/fluid ID, required rate, supplied rate, unit, source, destination, capacity when modeled, stage, and scenario. Relationships must never exist only in display text.

Compare consecutive stages using stable logical node identities and classify modules as reused, expanded, upgraded, reconfigured, idle, or decommissioned.

## 8. Solver design

### 8.1 Pipeline

1. Load phase and pace multiplier.
2. Resolve delivery quantities and derive multi-target rates.
3. Load capability gates available before production.
4. Filter recipes and buildings by gates and recipe policy.
5. Load prior-stage capacity and future reservations.
6. Build the reachable candidate graph.
7. Diagnose unavailable producers before optimization.
8. Form item and fluid conservation constraints.
9. Solve recipe run rates and raw imports.
10. Calculate exact machine equivalents.
11. Apply integer-machine and clock policy.
12. Recalculate capacity and power.
13. Validate extraction, logistics, and power constraints when enabled.
14. Diff against the previous stage.
15. Emit stage, transition, artifacts, and diagnostics.

### 8.2 Balance model

Use recipe runs per minute as continuous variables:

```text
sum(produced) + raw_import - sum(consumed) >= external_demand
```

Use equality when exact conservation is required. Surplus requires an explicit stockpile, future reservation, overflow, or sink.

The graph builder limits and explains the LP problem, detects missing producers, and provides stable result ordering.

### 8.3 Optimization priorities

Use lexicographic priorities:

1. Meet every phase target within the selected window.
2. Obey HUB tier and milestone gates.
3. Reuse prior-stage capacity and avoid teardown.
4. Respect resource, logistics, and power constraints.
5. Minimize raw resources using explicit weights.
6. Minimize incremental power.
7. Minimize incremental machine equivalents.
8. Use stable recipe-ID ordering as the final tie-break.

Use uniform resource weights initially. Never use hidden scarcity weights.

### 8.4 Machines and diagnostics

Store exact machine equivalents and an actionable integer schedule. Default to `ceil(exact)`, underclock the group or final machine, respect clock limits, then recalculate capacity and power.

Build infeasibility explanations from graph reachability, closed gates, unavailable recipes, invalid data, constraint residuals, and capacity checks. Never silently select locked technology or a slower pace.

## 9. Persistence

Use one SQLite database per save workspace with foreign keys and transactions. Persist master plans, stages, pace policies, capability snapshots, targets, recipe policies, nodes, edges, transitions, solver runs, provenance, diagnostics, journal records, and revision history.

Solver runs are immutable. Recalculation creates a revision.

Base workspace identity on stable logical evidence such as Saved root, profile when known, and save/session name. File existence must not change the key.

Import existing JSONL once, transactionally and idempotently. Record source hashes, preserve unknown fields as migration metadata, and leave original files untouched.

## 10. AI-callable tools

Keep exactly three tools after calculator introduction:

1. `get_satisfactory_context`: active save, plans, stages, transitions, diagnostics, journal context, and bounded game-data lookup.
2. `calculate_satisfactory_plan`: calculate a stage, master plan, pace scenario, or later an audit.
3. `update_satisfactory_plan`: assumptions, constraints, pace policy, recipe pins/bans, notes, todos, build progress, and archives.

The calculator uses typed fields for phase, pace multiplier, availability mode, pins/bans, prior plan, and persistence. It must not accept an opaque natural-language blob as its only input.

Response limits:

- Context/query: 2,800 characters.
- Calculation: 3,200 characters plus artifact path.
- Update acknowledgement: 400 characters.
- Lookup: at most five matches.

Measure generated schemas before accepting tool changes and keep `auto_activate: false`.

## 11. Implementation governance and handover

### 11.1 Role ownership

| Role | Responsibilities | Boundaries |
| --- | --- | --- |
| Codex | Inspect the current repository, define work packages, specify acceptance criteria and tests, review Claude's raw changes, run independent verification, classify findings, and decide the QC gate. | Does not write production code unless the user explicitly changes the delivery model. |
| Claude | Implement the approved work package, add or update tests, maintain source/release parity where required, document deviations, and prepare the implementation handover. | Does not expand scope, change locked architecture, or approve its own work. |
| User | Resolve product decisions, approve material scope changes, accept deferred risk, authorize release work, and decide when the next package begins. | Final authority for product scope and acceptance. |

Codex may edit this plan and QC documentation. Claude may update implementation documentation and the handover log as part of an approved package.

### 11.2 Work packages

Break each roadmap phase into bounded work packages. Use IDs in this form:

```text
SSP-P<roadmap-phase>-W<two-digit-sequence>
```

Example: `SSP-P1-W02` is the second package in roadmap Phase 1.

Codex creates an implementation packet before Claude starts. It must contain:

- Work-package ID and objective.
- In-scope and explicitly out-of-scope behavior.
- Relevant plan sections and locked decisions.
- Expected files or module boundaries.
- Data contracts and migration/configuration effects.
- Acceptance criteria.
- Required automated and manual verification.
- Cross-platform, token, persistence, and release-parity concerns.
- Baseline commit or revision and known unrelated working-tree changes.
- Known risks, assumptions, and blocking questions.

The package must be small enough that its acceptance criteria can be verified independently. Do not hand Claude an entire roadmap phase when it contains multiple separable behaviors.

### 11.3 Gate workflow

| Gate | Owner | Required exit evidence | Next state |
| --- | --- | --- | --- |
| G0 - Planning ready | Codex | Complete implementation packet, no unresolved blocking product decision, test strategy defined, baseline recorded. | `READY_FOR_CLAUDE` |
| G1 - Implementation ready | Claude | Scoped implementation, tests, exact commands/results, changed-file list, deviations, risks, and completed handover entry. | `READY_FOR_CODEX_QC` |
| G2 - Quality control | Codex | Raw diff inspected, acceptance criteria traced to evidence, independent checks run, findings recorded, gate decision issued. | `QC_PASSED`, `CHANGES_REQUESTED`, or `BLOCKED` |
| G3 - User acceptance | User | QC result reviewed; deferred risks and release scope explicitly accepted. | `ACCEPTED` or returned to an earlier gate |

If Codex requests changes, ownership returns to Claude under the same work-package ID with an incremented implementation attempt. The G1-G2 loop continues until the package passes, is blocked, or is superseded.

Passing G2 does not authorize commits, releases, or pull requests by itself. Follow the repository approval and PR rules after G3.

### 11.4 Status vocabulary

Use only:

- `PLANNED`
- `READY_FOR_CLAUDE`
- `IN_PROGRESS`
- `READY_FOR_CODEX_QC`
- `CHANGES_REQUESTED`
- `QC_PASSED`
- `BLOCKED`
- `ACCEPTED`
- `SUPERSEDED`

Every ownership transfer requires a status change and a log update. Neither agent may self-approve the gate it owns.

### 11.5 Codex QC bar

Codex reviews repository evidence, not only Claude's summary. G2 passes only when:

- Every acceptance criterion is mapped to code, a test, or explicit manual evidence.
- Required tests, lint, compilation, and targeted checks pass.
- No unresolved critical or high finding remains.
- Medium findings are fixed or explicitly accepted by the user as tracked debt.
- Changes stay within the approved scope and preserve unrelated work.
- Cross-platform guards, config behavior, logging, token budgets, persistence safety, and source/release parity are checked where relevant.
- The handover entry is complete and reproducible.

QC findings use `Critical`, `High`, `Medium`, or `Low` severity and include file/line evidence, impact, and the required correction. Codex records the gate decision in the same work-package entry.

### 11.6 Authoritative handover log

All implementation and review handovers live in [`DEVLOG.md`](DEVLOG.md). It is the single authoritative execution log; do not create parallel Claude, Codex, or session-specific handover files.

The log is a development artifact, not runtime application logging. Runtime output must continue to use `Printr`.

Each work package receives one newest-first `DEVLOG.md` entry containing:

- Work-package ID, roadmap phase, title, owner, status, and attempt.
- Baseline revision and known pre-existing changes.
- Implementation packet summary and plan references.
- Claude implementation summary and changed files.
- Exact verification commands and results.
- Deviations, decisions, known limitations, and unresolved risks.
- Codex QC findings and independent verification.
- Gate decision, next owner, and next action.

Claude creates or updates the implementation portion before setting `READY_FOR_CODEX_QC`. Codex appends QC evidence and the gate decision. Once `ACCEPTED` or `SUPERSEDED`, the entry is historical and must not be rewritten except to correct a factual logging error.

### 11.7 Handover handling

- The receiving agent reads this plan, the active `DEVLOG.md` entry, referenced files, and repository instructions before acting.
- Handover messages identify the work-package ID and status; durable details belong in `DEVLOG.md`, not only in chat.
- Claude pauses and returns ownership to Codex if implementation requires a material scope or architecture change.
- Codex independently reconstructs the result from the repository and commands; it does not accept unverified claims.
- Failed checks and partial work are logged honestly. Do not mark a gate ready because a session is ending.
- A blocked package records the blocker, evidence, work already completed, and the exact condition required to resume.
- The next work package does not start until the current package reaches `ACCEPTED` or the user explicitly authorizes parallel work.

## 12. Delivery roadmap

Deliver every roadmap phase through one or more bounded work packages using G0 through G3. A roadmap phase is complete only when all required packages are `ACCEPTED`. Do not combine separable parser, model, persistence, solver, and adapter changes merely to reduce the number of handovers.

### Phase 0: Correct the journal contract

- Return bounded details.
- Represent area, recipe, machines, and constraints until typed plans replace legacy flows.
- Separate workflow and calculated status.
- Enforce record types and explicit clearing.
- Stabilize workspace identity.
- Tighten discovery claims.
- Directly test both current tools.

Acceptance: all documented fields round-trip, malformed records do not crash, workspace identity remains stable, and token limits hold.

### Phase 1: Docs and progression dataset

- Cross-platform install discovery.
- BOM-aware localized Docs reader and Unreal structure parser.
- Normalized items, fluids, recipes, buildings, power, extraction, logistics, schematics, HUB gates, and Project Assembly phases.
- Capability snapshot builder.
- Versioned cache and bounded lookup.

Acceptance: fixtures resolve phase delivery sets and capability gates; optional real-install parsing passes; missing data leaves the journal functional.

### Phase 2: Typed master-plan store

- Typed quantities, progression, policies, nodes, edges, transitions, and diagnostics.
- Per-save SQLite and migrations.
- Idempotent JSONL import.
- Master-plan, stage, scenario, revision, and solver-run persistence.
- Markdown and JSON exports.

Acceptance: invalid units and references are rejected, changes are atomic, and existing journal data survives migration.

### Phase 3: Phase 1 deterministic planner

- Phase 1 multi-target demand.
- Pace multiplier `1.0` through `3.0`.
- Capability-gated standard and explicitly permitted recipes.
- Graph expansion, material balance, shared intermediates, coproducts, and loops.
- Resources, machines, clocks, and power.
- Compact summary and artifact.

Acceptance: fixture factories balance, meet the selected window, use only open gates, and produce deterministic results or actionable failures.

This is the first milestone that may be called a factory planner.

### Phase 4: Five-stage master plan

- Phase 2 through Phase 5 demands.
- Gate snapshots per stage.
- Production gate checkpoints for each HUB tier transition.
- Backward final-demand envelope.
- Carry-forward capacity and expansion diffs.
- Temporary capacity, stockpiles, and transitions.
- Future resource and expansion reservations.

Acceptance: every stage uses only available capabilities, each HUB tier transition produces a checkpoint without changing target rates, selected windows are met or explained, module identities remain stable, and the plan culminates in all Phase 5 components.

### Phase 5: Resource, logistics, and recipe constraints

- Alternate pins, bans, and unlocks.
- Lexicographic optimization.
- Extractor tier, purity, and clock calculations.
- Resource reservations.
- Belt, pipe, and power capacity checks.
- Overflow and byproduct policies.

Acceptance: no locked recipe is selected by default and no resource or capacity is silently overcommitted.

### Phase 6: Construction and commissioning

- Construction bill of materials and prerequisite gates.
- Dependency-ordered build stages and power-first staging.
- Startup checks and build progress linked to plan nodes.

Acceptance: each stage explains what to build, what to bring, and how to verify it. Construction time remains separate from the production window.

### Phase 7: Scenario comparison

- Pace scenarios from `1.0` through `3.0`.
- Scenario branching and explicit objectives.
- Comparisons for reuse, resources, power, machines, and complexity.

Acceptance: differences are reproducible and traceable; no scenario exceeds `3.0`.

### Phase 8: Actual factory adapters

- Optional reviewed `.sav` or third-party import adapters.
- Actual gates, alternates, machines, clocks, and reservations.
- Actual-versus-planned audit.

Acceptance: imports are provenance-tagged and manual planning remains available when they fail.

### Phase 9: Logistics networks and layout

- Areas, coordinates, floors, footprints, and expansion reservations.
- Typed belt, pipe, train, truck, and drone links.
- Station and route-capacity checks.
- Optional graph and map artifacts.

Acceptance: modules and connections can be assigned without known footprint or throughput conflicts.

## 13. First implementation slice

1. Codex creates the first bounded Phase 0 implementation packet and opens its `DEVLOG.md` entry.
2. Claude completes the approved Phase 0 corrections and hands the package to Codex.
3. Codex completes QC and obtains user acceptance before the next package.
4. Parse a tiny Docs fixture containing Phase 1 delivery data and dependencies.
5. Build the capability snapshot for open HUB gates.
6. Derive all Phase 1 rates at `pace_multiplier=1.0`.
7. Build and solve the gated dependency graph.
8. Re-run at `pace_multiplier=3.0` and verify scale reduction.
9. Validate balance, machines, clocks, and power.
10. Persist the stage transactionally.
11. Return a compact summary and artifact.
12. Repeat with an optional installed Docs file.

Do not include save parsing, layout, vehicle routing, or automatic alternate optimization in this slice.

## 14. Testing and verification

Use small CI fixtures for encoding, Unreal parsing, fluids, manufacturers, alternates, gate mappings, phase quantities, cache invalidation, multi-target demand at several pace values, shared intermediates, cycles, locked recipes, infeasibility, rounding, power, stage reuse, database migration, stable identities, and response budgets.

Solver invariants:

- Delivery rate equals quantity divided by configured minutes.
- Production minus consumption satisfies every target.
- No closed-gate technology or disallowed recipe is used.
- No negative flow, machine count, clock, or import exists.
- Rounded schedules remain valid and power matches final clocks.
- Reuse does not exceed prior-stage capacity.
- Results are stable under input ordering.
- Numeric residuals remain below tolerance.

Run:

```text
python -m pytest skills/satisfactory_assistant/tests -q -p no:cacheprovider
python -m ruff check skills/satisfactory_assistant
python -m compileall -q skills/satisfactory_assistant
```

Also verify no bare `print()`, no unsafe broad filesystem access, bounded responses, source/release parity, and SciPy import in the packaged runtime.

## 15. Definition of done

### First usable planner

A player can select the upcoming Project Assembly phase and pace multiplier, then receive a reproducible plan that derives all delivery rates, obeys HUB capability gates, balances the connected graph, calculates resources, machines, clocks, and power, explains failures, persists to the active save, and returns a compact summary plus artifact.

### Progressive master planner

- Phases 1 through 5 form one revisioned expansion plan.
- Each stage meets its selected window or explains why it cannot.
- HUB tiers act only as capability gates.
- Every opened HUB tier produces a revisioned production gate checkpoint without scaling demand.
- Earlier capacity is reused, upgraded, reconfigured, or retired explicitly.
- The final stage produces every Phase 5 component.
- Pace and recipe scenarios are reproducible.
- Optional imported state never becomes a calculator dependency.

## 16. Guardrails

- Do not rewrite the working active-save resolver without evidence.
- Do not mix Wingman imports into data, progression, model, solver, store, or report modules.
- Do not calculate from free-text flow strings.
- Do not store graph relationships only in descriptions.
- Do not call a plan balanced unless validated.
- Do not use HUB tier as a scale factor.
- Do not use technology behind a closed gate.
- Do not select locked alternates silently.
- Do not change pace silently or exceed `3.0`.
- Do not introduce a fourth lookup tool.
- Do not make `.sav` parsing mandatory.
- Do not alter Core API files for this feature.
- Do not update release copies until source tests pass.
- Do not delete or rewrite legacy files during migration.
