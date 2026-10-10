# SC Log Reader 2 — revised complete-skill plan

**Revised:** 18 September 2026. **Status:** accepted 0.4.0 implementation and completed local qualification: final corpus/story domain comparisons, seven load profiles and six corrected recovery cases. Reader nominal operation/parse budgets are 50/100 ms. Local final artifacts are prepared for controller binding/review. Actual Wingman, native settings action, frozen runtime, public 2.x and game-build qualification remain external gates. [Release evidence](../reports/release-0.4.0-20260918/REPORT.md) defines the qualified workload scope and preserves failed/superseded runs.

This document supersedes the forward-looking scope of [the first implementation plan](superpowers/plans/2026-09-15-first-implementation.md). That plan and its results remain historical evidence. [The implementation sequence](superpowers/plans/2026-09-17-complete-skill.md) turns this specification into reviewable tasks.

## 1. Goal and scope

Deliver an independently maintainable, installable Wingman skill that reads Star Citizen logs, preserves useful observations and confirmed outcomes, answers game-state/history questions, and optionally makes controlled announcements. Most changes to already-supported game-log wording should be deliverable as one reviewed JSON update, independently of a Wingman release.

“Stable” means that the reader engine, state contract and Wingman interface change deliberately and infrequently. It does not mean they can never require code updates. A new state meaning, unsupported parsing operation or host API change still needs an engine/adapter release. There is no promise to cover every future game event.

### First complete release

- The existing 60 supported event recipes, their evidence/state rules and seven read-only tools, with a published compatibility matrix.
- Reliable incremental monitoring, restart recovery, file-generation handling and visible catch-up status under ordinary and burst input.
- One data-only instruction JSON, automatic discovery, explicit human approval, activation at startup, and rollback.
- A verified adapter and installer path for one explicitly recorded Wingman release/API. A local legacy adapter test is not that verification.
- Optional, restricted, per-category announcements with flood suppression and no historical announcement storm.
- Resource/error visibility, local diagnostic support, documented recovery and a qualified release package.

### Explicit later extensions

Inventory cost-basis/profit accounting, donation/upload workflows, full old-skill UI parity, configurable injury reminders and reward-bundle presentation remain separately scoped extensions. Confirmed cash flow is already the ledger's meaning. The first release must disclose these omissions rather than imply that missing log evidence can support them. Any later reminder uses dated injury evidence and never assumes recovery; reward grouping must never book the same reward twice. No automatic log upload is planned.

## 2. What is implemented and what is still unverified

| Area | Current evidence | Remaining release work |
|---|---|---|
| Reader | Fixed interpreter, 60 recipes, bounded assembly, shared deadlines/fast paths; stated local ordinary/sustained/peak/archive workloads qualified | Arbitrary recognized/pathological workload and complete scenario/build qualification |
| Handler | Missions, objectives, injuries, locations, ships, zones, sessions, requests/confirmed money and per-field provenance; final archive domain output matches baseline | Qualify complete scenarios per event/build; keep unsupported semantics explicit |
| Persistence | Bounded batches/checkpoints, domain dedup, bounded support/lifetime totals; local resource/burst/recovery checks passed | Domain history has no automatic retention policy; externally deleted unread bytes are unrecoverable |
| Orchestrator/host | Inspected development 3.1.2 contract, off-loop prepare/tools, owned deferred shutdown, staged registration/native layouts and host-double tests | Actual Wingman GUI/heartbeat/settings/install, native review action and frozen runtime |
| Updates/ownership | Exact-digest manual approval, process-start exclusion fences, pinned host decisions, host lifetime lease, standalone watch lease through database close, fallback/rollback and local review launcher | Authorized publication/pipeline; actual host native review action/frozen launcher qualification |
| Notifications | Optional master-disabled literal sink/category/rate/repeat/catch-up fences; local host-double delivery checks passed | Actual visible GUI rendering and host heartbeat unqualified |
| Qualification | Final 174-file corpus/story, 12,187,071 records each, exact domain comparisons; full/focused suites; seven load and six recovery cases passed | Controller final artifact binding/review and actual Wingman/game sessions |

The bundle is revision 4, version `0.3.0-evidence-state`, engine/event contract 3, minimum reader 0.3.0. `verified_game_builds` is empty. This is intentional: archive success alone does not qualify a game build.

## 3. Evidence that changes the plan

Sources: [timing report](../reports/timing-statistics-20260916/REPORT.md), [rate report](../reports/log-entry-rates-20260917/REPORT.md), and [timeout follow-up](../reports/timing-statistics-20260916/timeout-followup.json).

- Both timing replays covered 174 files and 12,187,071 entries each. The recorded source suite passed 140 tests, including four timing-probe tests. These are past verified results, not tests rerun for this planning edit.
- Chronological parsing averaged 0.0287 ms per entry; p99 was 0.1129 ms, or 0.1959 ms for recognized entries without diagnostics. One regex timed out at 17.4153 ms; the longest whole parse was 23.3555 ms. The isolated timeout failed to recur in 200 retries; its cause remains unknown.
- The pattern-count review found 11.24 regex operations and 8.50 distinct patterns per recognized clean entry on average, with a maximum of 58 operations. The overall 1.14-operation average is dominated by ignored lines. Pattern operations are not the total number of rule predicates evaluated.
- Deduplicating the archive gave 107 unique files and 10,380,345 timestamped entries. Outside one extreme file, nonempty seconds had median 6 entries, p95 56, p99 156 and peak 4,101. Those are observed archive distributions, not gameplay-only or exact disk-write rates.
- The extreme file is `D:\Roberts Space Industries\StarCitizen\LIVE\logbackups\Game Build(12545750) 31 Aug 26 (22 08 34).log`, SHA-256 `24780b2af990dfd73d4e10cbf986ac354e7e696ad88ba270fca9ecd3fdaece67`. Keep it. It has 7,391,186 timestamped entries over 1,505.678 seconds, averaging 4,908.9/s, with peak timestamp buckets of 111,918/s and 20,621/100 ms.
- That peak contains repeated restricted-area notification listings. The user's recollection of Orison instance collisions, relocation notices and a disconnect is a valuable investigation lead, not a verified causal reconstruction. This review has not counted logins or established the relocation/disconnection sequence.
- The peak second's previously measured parser durations total about 3.014 seconds. That identifies possible backlog pressure; it is not measured live throughput. Framing, database work, polling delays and host behavior are outside those parse timers.
- Instrumentation added about 11% for ignored entries and 30% for recognized entries in a small calibration. Performance release gates therefore use an uninstrumented run plus a separate diagnostic timing run.

**Revised priority:** correctness under bounded execution, ordered catch-up and responsive operation take precedence over adding more event recipes or claiming full compatibility.

## 4. Architecture to retain

```text
Game.log, read-only
  -> bounded record assembly and incremental monitoring
  -> Reader + one validated JSON package                 [Tier 3]
  -> normalized Event / diagnostic / ignored disposition
  -> fixed State rules                                  [Tier 2]
  -> durable observations, outcomes, snapshot, checkpoint
  -> read-only tools + optional bounded announcements    [Tier 1]

GitHub JSON -> validate -> show candidate -> human approval
            -> stage exact bytes -> next startup -> fallback available
```

Use the tier names above consistently; the original conversation contained a numbering typo. State and host layers must not parse changing game wording. JSON owns labels, aliases, extraction and lookup data within the fixed contract. The host owns presentation and user settings.

No MCP server or local Git client is required for this design. A future shared Wingman skill registry can advertise the approved publisher endpoint without changing the user's approval requirement. It must not authorize arbitrary developers' executable code or silently switch publishers.

## 5. Reader execution and optimization

### Proposed limits

- Pattern-operation allowance: **50 ms**.
- Whole `Reader.parse` allowance: **100 ms**, shared by every rule check and extraction operation.
- At each regex operation, pass `min(pattern_allowance, remaining_entry_time)`; fail immediately when no time remains.
- Consume lazy regex iterators within the same operation allowance. Check the entry deadline between yielded matches and before returning a successful event. Checking only iterator creation is insufficient.
- Compilation/cache access, literal-condition loops, extraction and validation are included in the cooperative parser deadline. The deadline cannot forcibly interrupt arbitrary Python/OS work; do not market it as a hard real-time cutoff.
- Record assembly, header-build detection and instruction validation have their own bounded execution contexts. They must not be accidentally documented as included in the 100 ms parse timer. Audit the existing literal 10 ms header calls when consolidating runtime pattern policy.
- Timeouts emit a bounded diagnostic with stage, rule/operation identifier, instructions version and source range. Preserve the existing `regex_budget_exceeded` compatibility marker while distinguishing pattern exhaustion from entry-budget exhaustion in diagnostic detail.

### Remove proven redundant work first

Bracket extraction currently calls `search()` and then `finditer()` on the same expression/input, using the initial search to compile/cache. Compile/cache without matching, then iterate once. Preserve conflicting-alias detection and all matches.

### Conservative fast paths second

Derive necessary literal preconditions from the installed JSON. Skip a rule only when its required condition is provably false. `any`/`not` and expressions without a provable precondition stay on the general path. Continue detecting ambiguous matches; never introduce first-match-wins behavior.

Do not hard-code “ignore any line containing Leaving Restricted Area,” skip whole byte ranges during floods, or sample the raw input. Notification-list lines and real `Added notification` events must remain distinguishable. A fast path must preserve both semantic outputs and diagnostic behavior across the whole corpus, including future valid JSON changes that make a formerly irrelevant line meaningful.

## 6. Ordered monitoring, backlog and persistence

- Preserve physical record order within each environment/generation. Do not globally sort by source timestamps; the archive has 16,395 backward timestamp steps.
- Keep the source file as the backlog store. Hold at most one 256 KiB source chunk plus the 64 KiB assembly limit per environment, with bounded decoded-object overhead; do not create an unlimited in-memory queue.
- Process bounded batches, initially **up to 128 records**, with a **200 ms cooperative poll budget checked between records/batches**, and round-robin service across environments. These are proposed tuning defaults. A single admitted parse may use its remaining allowance; blocked I/O can exceed the wall-clock target and must be observable.
- Yield between batches so tools, stopping and the next environment get service. The present four-round/200 ms loop checks only between chunks and the host then waits 250 ms; measure the complete path before tuning either value.
- Define read, assembled and durably committed offsets separately. Never checkpoint past unprocessed queued records or an incomplete record. After interruption, replay from the safe checkpoint and use occurrence identity to prevent repeated state/money effects.
- Add a batch-ingest transaction path only with fault-injection tests: ordered observations/outcomes, snapshot and supplied checkpoint commit together. Failed transactions publish no announcements and leave the checkpoint retryable. Health counts must not silently count rolled-back events as committed.
- A malformed input becomes a diagnostic and does not block later input. Database/I/O failures do not silently discard records; expose the error, retry safely, and visibly pause after the existing consecutive-worker-failure policy is exhausted.
- Add monotonic-clock input/processing rates, read/committed bytes behind, pending bytes, oldest-pending observation age where known, and tool/poll responsiveness. Unknown source time stays unknown. “Caught up” does not mean the game is currently running.

## 7. State and event completeness

Maintain a 60-recipe matrix covering: normalized fields, state/outcome effects, public visibility, positive and negative fixtures, real-log evidence, and qualification status. New public event meanings require a versioned state contract.

- **Session/environment:** keep LIVE/PTU/EPTU/HOTFIX/TECH-PREVIEW separate. Character, shard, generation and instruction changes invalidate only the claims/correlations defined by their contract. Repeated login-like text is not proof of a new session without the appropriate event.
- **Missions/objectives:** preserve explicit acceptance and terminal outcomes; retain orphan evidence without inventing acceptance. Lists remain explicitly partial. Multiple-objective support needs its own evidence and migration if added.
- **Health:** preserve injury/healing evidence and timestamps. Silence, login and unrelated observations never prove recovery. Unknown current bleeding/incapacitation remains unknown.
- **Location/ships/quantum:** distinguish logged inventory locations, aboard-ship evidence, last known locations and confirmed ownership. A matching display/model label does not justify player attribution. No quantum destination, arrival time or physical location is fabricated.
- **Trade/rewards:** preserve requested, confirmed, unresolved and ambiguous states; explicit currency and unique correlation govern money. No amount/recipient guessing, no duplicate booking, and no expiry that turns ambiguity into certainty. Cargo/commodity completion remains unproven where the logs lack confirmation.
- **Spam episodes:** repeated warnings may be grouped for presentation. That does not establish a causal bug diagnosis, player relocation, disconnect or recovery. Preserve the underlying state transitions and source references.

The existing 87 incomplete-record and six missing-request-ID diagnostics are not a demand to weaken validation. Improvements need exact observed variants and expected meanings. Unknown notification samples remain bounded, local and untrusted.

## 8. Announcements and complete user experience

Keep reactions disabled until a restricted host presentation API is verified. The eventual path formats literal, bounded text from canonical events and calls a notification/TTS sink that cannot invoke commands or tools. Game text never enters Wingman's normal command/execution pipeline.

Proposed initial policy, independently testable with a fake clock:

- User explicitly enables announcements and chooses categories. Keep read-only tools usable with announcements off.
- Commit events before creating announcements. Session/state/ledger processing never depends on announcement delivery.
- For repeatable nonfinancial warnings, key suppression by environment, generation, event type, subject and action. Announce the first eligible warning, count repetitions, and permit at most one repeat summary per **60 seconds**. **30 seconds** without the same warning closes that notification group; it is not proof the game problem is resolved.
- Bound repeat tracking to **256 keys per environment** and delivery queues to **100 messages**. Overflow coalesces/drops presentation items with a visible suppression count; it never discards state/history or changes financial deduplication. Never present a partially delivered queue as complete.
- History reconstructed on startup is silent. Events processed while catching up do not later become a burst of stale announcements. Expose catch-up status and allow an explicit history summary through read-only tools.
- Injury reminders and reward-bundle narration remain later features with separately defined evidence and repetition rules.

The normal user flow is: configure game/runtime path -> reader status -> ask questions/optionally enable categories -> review a discovered update -> Update at next startup / Later / Skip -> visible scheduled/active/rollback version.

## 9. Updates, publishing and packaging

Preserve one complete distributable JSON. The engine and a known-good bundle ship with the installer; downloaded content is stored separately in the writable runtime directory.

1. A maintainer adds positive/negative provenance-bearing fixtures for a game change, updates JSON, increments its revision and writes release notes.
2. Validation and behavioral release checks run on that exact candidate digest. A reviewed candidate must include compatibility, representative corpus differences, resource checks and money/state invariants.
3. Publish those exact bytes to a controlled direct HTTPS GitHub JSON endpoint. No publishing account/repository is configured yet; endpoint selection is a release prerequisite, not permission to publish now.
4. Existing startup/six-hour checks discover/download a bounded candidate. Network failures preserve the active engine; publisher changes invalidate pending approvals.
5. The user sees version, notes, compatibility/build evidence, publisher, installed version and rollback availability. Approval binds the exact digest and publisher generation. AI tools cannot approve.
6. Stage exact bytes, keep the running version immutable and activate with fallback only at an eligible next host-process startup. Implemented process-pinned host decisions and exclusion fences preserve this boundary across unload/reprepare/module recreation; failed snapshots can conservatively require an extra restart. Standalone startup has separate wording and long-lived watch ownership through database close. Activation does not replay old money.

HTTPS plus repository control establishes the current publisher trust boundary. SHA-256 identifies approved bytes; it is not a publisher signature. Signing is a separate deployment enhancement if maintainers require it, not a claim about the current package.

Pin and document the tested Wingman version/commit and runtime dependencies before adapter/installer qualification. The existing legacy constructor/API tests remain useful. References to public API 3 in old documents are integration work to verify against the selected release, not a statement that current upstream compatibility has been checked today.

## 10. Storage, health and support

- Do not retain every raw spam line in a second database. Keep state-relevant observations/outcomes, bounded diagnostic samples and repeat counters.
- Add size/health visibility for the database, diagnostic storage and downloaded objects. Start with an explicit **1 GiB history-size warning**, not silent deletion. Default automatic pruning of historical transactions is off. Exports and destructive cleanup require user-selected scope.
- Compact redundant diagnostic samples by rule/reason/version and time window while preserving counts and first/last provenance. Counters, sample text and cardinality must all be bounded against hostile input. This must not merge genuine financial transactions or replace journal replay identity.
- Prune only unreferenced update objects under a verified local retention policy; always retain active, previous, approved/staged and bundled fallback objects. Do not prune automatically in this planning pass.
- On disk-full/write failure, pause visibly without advancing the durable checkpoint or allocating an unlimited memory spool. Report that unprocessed source bytes can be lost if the game rotates/removes its log before recovery.
- Diagnostics exports are optional, local and reviewed/redacted before any sharing. Never upload player names, text or logs automatically.

## 11. Qualification and acceptance gates

All thresholds below are **proposed release targets**, not current verified guarantees. Record machine/runtime/build and test settings. Hardware-dependent failures produce a qualified support statement or further work; do not silently loosen thresholds to make a report pass.

| Gate | Required evidence |
|---|---|
| Functional regressions | Existing source tests plus new deadline, batching, recovery and presentation tests; installed-wheel/import checks; unchanged original/reference hashes |
| Semantic equivalence | Independent full corpus plus chronological history replay; inspect every event/state/ledger delta; no unexplained loss or money changes; maintain unsupported/unknown matrix |
| Parser budget | Deterministic tests of remaining-time propagation for search, replacement and consumed iterators; one shared deadline; timeout diagnostics recover on the next entry |
| Typical monitored load | File-writer harness at 6, 56 and 156 entries/s, at least five minutes each; input captured with a monotonic writer clock; p95 committed-event visibility <=1 s and no steadily growing backlog |
| Burst recovery | Reproducible 4,101-entry and 111,918-entry timestamp-group payloads, offered as explicit synthetic append schedules; exact outcomes/order after drain; target <=30 s catch-up after a single peak append on the reference machine |
| Sustained flood | Preserve/replay the full 487,705,181-byte stress log; also a 4,909-entry/s, 25-minute scheduled writer test; backlog must settle rather than grow indefinitely at the sustained rate; distinguish inference from actual live writes |
| Host/resource behavior | Fake-host heartbeat p99 delay <100 ms, read-only tool p95 <=1 s; transient ingestion RSS growth <=128 MiB above warmed baseline without growth proportional to source size; unload waits <=2 s while outstanding workers retain safe storage ownership |
| Recovery | Stop/restart/rotation mid-burst, disk-full, database error, malformed line, network outage and corrupt update; checkpoint correctness and no repeated money/outcomes |
| Updates | Changed bytes after review, incompatible versions, skip/cancel, publisher switch, offline start, corrupt staged/active content, bundled fallback and rollback; no unapproved activation |
| Real host/game | Isolated Wingman install of the selected version; settings/tools/update-review button/TTS lifecycle; representative live game sessions with user-approved observation and explicit build qualification |

Use wall time for latency. Per-entry Windows thread CPU values observed in the timing run were too coarse to support microsecond latency conclusions. Use process CPU over longer intervals for resource reporting. Tests must measure file writing, tailing, parsing, persistence and host delivery separately; parser speed alone does not establish end-to-end capacity.

Do not include this user's private full logs in a public package. Keep the full stress log local, with hash/path recorded; produce permission-appropriate minimized fixtures for distributable tests.

## 12. Delivery order and decisions

1. Correct deadline coverage and redundant extraction, then compare 15 ms versus proposed 50 ms without changing the total parser allowance.
2. Add conservative equivalent fast paths if profiling confirms they reduce the spam/ignored path.
3. Bound monitored work, integrate safe batch commits and expose backlog/latency accurately.
4. Run paced and full-stress qualification; resolve demonstrated throughput/recovery problems before claiming readiness.
5. Close semantic evidence gaps and create the event/tool compatibility matrix.
6. Add bounded presentation policy and local resource/support controls.
7. Integrate the selected real Wingman API, review UI and installer; qualify updates and runtime lifecycle.
8. Ship a qualified core release, then consider the explicitly deferred features independently.

Existing decisions remain: independent project folder; untouched original skill; no silent update activation; single JSON for supported interpretation changes; fixed state semantics; preserve the extreme logfile. This plan authorizes no source edits, installation, publication or game/Wingman launch by itself.
