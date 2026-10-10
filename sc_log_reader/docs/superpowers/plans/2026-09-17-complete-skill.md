# Complete SC Log Reader 2 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. The user approved execution on 17 September 2026. Progress and evidence live in `reports/implementation-20260917/LEDGER.md`. Use subagents only when separately authorized or required by applicable execution instructions.

**Goal:** Finish the independent skill as a qualified Wingman integration with bounded parsing/monitoring, evidence-preserving state, controlled announcements and manually approved single-JSON updates.

**Architecture:** Retain Reader/JSON -> State -> Service/host boundaries. Improve execution bounds and durable catch-up before expanding presentation. Keep data updates independent of executable releases and immutable during a running service lifetime.

**Tech Stack:** Python 3.11+, `regex`, SQLite, unittest, setuptools; existing local development environment; NumPy only for offline report analysis, never a required runtime dependency.

**Spec:** [Complete skill specification](../../PLAN.md). Read it together with this sequence. Current baseline is 0.3.1, instruction revision 4 / contract 3. The core code is already implemented; preserve it and extend incrementally.

## Global constraints

- Work only in the user-approved `D:\PycharmProjects\wingman-ai\skills\Sc_log_reader_2` or task-specific temporary directories.
- Preserve `reference/current_skill`, the original Wingman skill and game logs. No original-project edits, installs, publishing or launches without their own authorization.
- Instruction updates require manual user approval and activation at the next Wingman startup. Preserve a working fallback.
- Game text and downloaded JSON cannot authorize commands, imports, evaluation, tool calls or their own updates.
- Preserve physical ordering, provenance, ambiguity/unknown states, explicit currency and occurrence-based deduplication.
- Proposed defaults: 50 ms per pattern, 100 ms per parse, 128 records per batch, 200 ms cooperative poll budget, 256 notification keys/environment, 100 queued announcements, 60 s repeat-summary interval, 30 s quiet closure.
- “100 ms per parse” excludes file I/O, record assembly, state/database processing and host delivery; those stages get separate measurements and cooperative work limits.
- Default automatic pruning of historical transactions is off. The proposed 1 GiB threshold is a warning.
- The package is currently untracked inside a dirty Wingman Git checkout. Save reversible source snapshots/diffs and test reports per task; do not initialize Git or invent commits as a prerequisite.

## File responsibilities and dependencies

| File | Responsibility / intended change |
|---|---|
| `src/sc_log_reader_2/reader.py` | Deadline enforcement, compiled-pattern access, interpreter and safe candidate selection |
| `src/sc_log_reader_2/service.py` | Ordered ingest/batch transactions, tailer checkpoints, fairness, health and storage summaries |
| `src/sc_log_reader_2/state.py`, `contracts.py` | Stable event meanings and evidence; change only for demonstrated semantic gaps |
| `src/sc_log_reader_2/data/instructions.json` | Versioned game wording/aliases/recipes; no runtime scheduling or approval authority |
| `src/sc_log_reader_2/notifications.py` (new) | Pure bounded presentation policy, no host import or state mutation |
| `src/sc_log_reader_2/updates.py`, `review_ui.py`, `cli.py` | Existing update lifecycle; resource/support commands and real-host review integration |
| `src/sc_log_reader_2/main.py` | Host lifecycle/poll scheduling; retain existing host-double behavior |
| `integrations/wingman_target/` (new) | Recorded target contract, settings/registration template and packaging instructions for the selected real host |
| `tools/stream_test.py` (new) | Scheduled append writer, complete monitor path, independent oracle comparison and resource measurements |
| `tests/fixtures/stress/provenance.json` (new) | Full private-log location/hash plus minimally extracted/redacted fixture references |
| `docs/COMPATIBILITY.md` (new) | Event/tool coverage, parity decisions and measured target versions |

Dependencies: T1 -> T2 -> T3 -> T4. T5 uses the same fixture/oracle work. T6 follows T3 and T5; T7 follows T3. T8 integrates T1–T7. T9 is the complete release gate.

For each task: reproduce the missing behavior with a focused failing test, implement only that behavior, rerun affected tests and existing relevant regressions, then record the result/diff. No whole-corpus rerun is needed for a documentation-only edit; semantic or scheduling changes require the appropriate corpus/stream gate.

## T1. Shared execution deadline and single-pass bracket extraction

**Modify:** `reader.py`, `service.py` header-pattern calls, `docs/INSTRUCTIONS.md`.
**Tests:** create `tests/test_parser_budget.py`; retain `tests/test_resilience.py`, `test_reader.py`, `test_recipe_matrix.py`, `test_timing_probe.py`.
**Interfaces:** retain `Reader.parse(text, *, complete=True, game_build=None) -> Event | None` and all current event shapes. Add private budget/compiled-pattern helpers; no new public JSON operator is needed.

- [ ] Add a fake monotonic clock and recording pattern double. A conceptual core assertion is:

```python
started = 1.000
now = 1.090
remaining = 0.100 - (now - started)
assert abs(min(0.050, remaining) - 0.010) < 1e-9
```

Exercise this through actual reader search, replacement and iterator calls, including an iterator that advances the fake clock between yielded matches. Verify a late successful match cannot return a successful event after the entry deadline. Keep a real pathological-regex test as a coarse liveness check, not a millisecond-exact wall-clock assertion.

- [ ] Introduce a private compiled-pattern helper that validates/compiles without performing a search. Replace bracket `search` + `finditer` with one iteration; preserve duplicate-value/conflicting-alias behavior.
- [ ] Route every parse-time regex through the remaining-budget calculation; consume iterators under it; add deadline checkpoints to bounded non-regex loops and final return. Keep compilation restrictions and size limits.
- [ ] Preserve the generic timeout marker and add bounded reason/stage/rule detail. Confirm the next valid entry still processes and the failed record produces no state or money effect.
- [ ] Set the proposed pattern allowance to 0.050 only after the coverage tests fail for the old bypass and pass with the fix. Keep the parse deadline 0.100. Audit framing/validation/header callers and document their separate scopes.
- [ ] Run `.\.venv\Scripts\python.exe -B -m unittest discover -s tests -p test_parser_budget.py -v`, followed by the relevant existing suites. Record 15 ms versus 50 ms replay results in distinct new report folders, including benign timeout cases and pathological expressions; do not overwrite the baseline.

**Acceptance:** every timeout-taking parse operation receives at most the remaining allowance; no lost alias conflicts, no manufactured successful event after expiry, no unexplained corpus output changes. OS scheduling can still overshoot a cooperative deadline.

## T2. Conservative reduction of work on irrelevant lines

**Modify:** `reader.py`; create `tests/test_reader_dispatch.py`; use existing corpus tools.
**Consumes/produces:** unchanged Reader input/output and installed JSON. Candidate selection is an engine-private optimization derived anew for each validated instruction package.

- [ ] Create rule fixtures for required literal conditions under `all`, disjoint `any`, `not`, regex-only rules and two simultaneously matching rules. Candidate elimination must never change an expected diagnostic or ambiguity result.
- [ ] Implement only provable necessary preconditions: an `all` can contribute required positive record-text literals; `any` requires a condition common to every branch to eliminate the whole rule; `not` provides no positive-literal shortcut. Unknown forms use the complete interpreter.
- [ ] Add a test where an updated valid JSON recipe makes a previously ignored noise line meaningful. The optimized reader must emit it after startup selection of that package.
- [ ] Compare baseline and optimized normalized events, fields, errors and dispositions on the complete corpus and targeted spam/notification fixtures. For the extreme warning listings, prove that real notifications and interleaved session/mission/transaction records remain visible.
- [ ] Profile uninstrumented reader and full service separately. Keep the optimization only if it materially reduces measured work without semantic drift. Do not add a global game-wording blacklist or parallelize state application.

**Acceptance:** exact semantic equivalence except separately approved instruction corrections; ambiguity behavior preserved; measured improvement documented rather than assumed.

## T3. Fair monitor batches and atomic progress

**Modify:** `service.py`, `main.py`; create `tests/test_stream_scheduling.py`, `tests/test_batch_recovery.py`.
**New interface:**

```python
@dataclass(frozen=True)
class IngestBatchResult:
    consumed: int
    events: list[dict]

Service.ingest_batch(
    records: list[Record], environment: str, generation: str,
    game_build=None, *, deadline: float | None = None,
    checkpoints: list[dict] | None = None
) -> IngestBatchResult
```

Each optional `checkpoints[i]` has the existing `streams` metadata shape and is safe after processing `records[i]`, including the matching boundary hash. Validate equal list lengths. Check the monotonic deadline before each record inside the transaction and return the count actually consumed; commit only that prefix's final checkpoint. A zero-consumed result advances nothing. Tailer retains the remainder for the next batch. Existing `ingest(...)` remains compatible by calling the single-record path and returning its events. Extract a private ingest-within-transaction helper rather than nesting current per-record transaction contexts and accidentally committing early. Stage health deltas until commit succeeds.

- [ ] Add an ordered sequence with a trade request/confirmation and session boundary straddling batches. Assert identical events, ledger and state to individual ingest.
- [ ] Inject a failure after row insertion and before snapshot/checkpoint update. Assert transaction rollback, unchanged checkpoint, zero publishable output, and exactly-once outcomes after retry. Repeat with interruption immediately after a successful commit.
- [ ] Separate live read position, buffered/unprocessed records and safe durable checkpoint. Retain at most one input chunk plus bounded assembly per environment; resume from the first unprocessed byte after restart, not the assembler's farthest-read offset.
- [ ] Check the 200 ms work deadline between records/batches and process at most 128 records before yielding/committing a batch. Persist output before exposing it. Round-robin environments so a flooded LIVE stream does not starve PTU or tools.
- [ ] Test that an early budget exit within a chunk eventually processes every later record exactly once. Test an incomplete multiline record across both chunk and batch boundaries.
- [ ] Make host scheduling backlog-aware with bounded yields; measure before choosing idle/catch-up delays. Preserve cancellation ownership and the existing two-second unload wait; never close storage while an admitted worker owns it.
- [ ] Expose bytes read/committed/pending, monotonic rates and poll/tool latency. Test quiet files, late-written headers, source disappearance, rotation mid-batch, and two environments with one missing path.

**Acceptance:** no skipped queued bytes, reordered evidence, repeated outcomes, unbounded RAM backlog or starvation. Existing service/host/restart tests pass. All clock budgets are documented as cooperative.

## T4. End-to-end scheduled-stream and flood qualification

**Create:** `tools/stream_test.py`, `tests/test_stream_harness.py`, `tests/fixtures/stress/provenance.json`; store results under fresh `reports/stream-qualification-*` directories.
**Interface:**

```text
python tools/stream_test.py --profile typical|burst|sustained|recovery
  --output NEW_DIRECTORY --source-log OPTIONAL_PRIVATE_LOG
```

The tool writes only a temporary simulated `Game.log` under its output directory. It uses real `Tailer`/`Service`, a controllable writer schedule and an independent expected event/state oracle. The optional private source is read-only and verified against recorded size/hash. Results include offered versus achieved writer rate; an under-speed writer cannot establish reader capacity.

- [ ] Verify the harness itself with four known lines offered at known monotonic times, delayed ingestion, and a deliberately missed/duplicated line. It must detect missing outcomes, latency and counts independently of Tailer counters.
- [ ] Run 6, 56 and 156 entries/s for at least five minutes each; record writer append, committed event and notification-delivery times separately. Include ordinary noise and recognized records, not only tiny synthetic lines.
- [ ] Replay the observed 4,101- and 111,918-entry timestamp groups with explicitly labelled append schedules. Timestamps do not prove the original OS write schedule. Inject supported session/mission/confirmed-transaction sentinels before, within and after bursts and verify their exact ordering/outcomes.
- [ ] Run the full retained 487,705,181-byte stress archive plus a 4,909-entry/s, 25-minute scheduled input profile. Record backlog growth/drain, peak RSS, process CPU, database growth, poll latency, tool responsiveness and unknown/timeout counts.
- [ ] Run stop/restart, truncation/replacement, malformed-record and disk/database-error cases during a burst. No silent data loss or false successful catch-up is acceptable.
- [ ] Evaluate the targets in the spec: ordinary visibility p95 <=1 s, tool p95 <=1 s, host heartbeat p99 delay <100 ms, transient RSS <=128 MiB over warmed baseline, isolated peak drain <=30 s, and stable sustainable backlog at 4,909/s. Mark targets unmet when evidence says so; do not redefine “normal” to exclude a failing test.

**Acceptance:** complete reports distinguish parser capacity, monitored throughput, source timestamps, synthetic scheduling and actual host tests. Full logs remain private/local. This task may expose additional work; release remains gated until it is resolved or explicitly scoped out.

## T5. Semantic coverage and compatibility matrix

**Modify:** `tests/test_recipe_matrix.py`, real-log fixtures and provenance, `state.py`/`contracts.py` only for reproduced gaps; create `docs/COMPATIBILITY.md`.
**Interfaces:** current seven tool names and normalized event contract 3 remain the baseline. Any changed response/state meaning is recorded as a compatibility change, not silently shipped as wording-only JSON.

- [ ] Enumerate all 60 bundle recipes and seven `ToolInterface` tools into the matrix: evidence fields, state effects, positive/negative tests, real-build coverage and known gaps. Include output-only/observation-only events explicitly.
- [ ] Label at least these cases: foreign/same-model ship evidence, missing currency, ambiguous/expired trades, orphan objectives, unknown locations, partial mission reconstruction, unknown current bleeding/incapacitation, and commodity/cargo requests without confirmations.
- [ ] For any semantic correction, add exact observed provenance-bearing input and asserted event/field/state/ledger expectations before changing rules/code. Example invariant for an ambiguous trade:

```python
assert result['status'] == 'ambiguous'
assert result['amount_auec'] is None
assert ledger_after == ledger_before
```

- [ ] Retain sequence tests for logins/character changes, shards, file generations, instruction activation and out-of-order timestamps. Do not infer a relocation-loop cause or add logout/recovery detection solely from the user's recollection.
- [ ] Document first-release omissions and the evidence prerequisites for inventory cost basis, reminders and reward grouping. Do not populate `verified_game_builds` from archive filenames alone.

**Acceptance:** every supported public behavior has a matrix row; unsupported meanings are explicit; complete corpus/story deltas are explained without treating “no exception” as accuracy.

## T6. Bounded announcement policy

**Create:** `src/sc_log_reader_2/notifications.py`, `tests/test_notifications.py`; modify host configuration/adapter only after the sink contract is verified.
**New interface:**

```python
NotificationPolicy.offer(event: dict, *, now: float, catching_up: bool) -> None
NotificationPolicy.flush(*, now: float) -> list[dict]
```

The constructor accepts enabled categories and the spec's limits. Input is a committed canonical event envelope carrying environment, generation, event type and provenance; Service supplies generation from the known source context if it is absent from the public event row. `offer` adds eligible items to the internal bounded queue; `flush` drains eligible messages. Output messages contain category, plain text, source occurrence references and repeat count. The policy cannot mutate state or approve an update. A failed sink delivery is counted/reported, never retried through an unlimited queue.

- [ ] With a fake clock, offer 1,000 same-key restricted-area warnings within 60 seconds: one initial message, bounded tracking, suppressed count 999. Keep supplying repeats with gaps shorter than 30 seconds through the 60-second boundary and permit one summary. In a separate case, stop repeats for 30 seconds and close the group without asserting game recovery or queuing stale speech.
- [ ] Interleave distinct session, mission and monetary events. Assert persistent events/ledger are unchanged regardless of notification settings, suppression or sink failure.
- [ ] Exercise 257 keys and 101 pending messages. Verify bounded memory, deterministic eviction/coalescing, suppression reporting and no crash. Historical/catching-up input produces no queued stale speech.
- [ ] Use fixed templates and bounded escaped/literal fields. Assert strings resembling commands cannot reach a tool/command pipeline. Until T8 verifies a restricted host sink, keep the production reaction switch disabled.

**Acceptance:** a spam episode cannot create an announcement storm or alter evidence; enabled/disabled categories and catch-up behavior are predictable; restricted sink integration remains a separate gate.

## T7. Operational storage, diagnostics and support controls

**Modify:** `service.py`, `updates.py`, `cli.py`, `review_ui.py`; create `tests/test_resource_health.py`.
**Interfaces:** extend existing `get_reader_health` additively with size, rate, backlog and suppression fields; retain existing keys. Optional local exports operate through human-facing CLI/UI, never automatic upload.

- [ ] Simulate repetitive diagnostics with many distinct untrusted text values. Bound key cardinality and sample sizes while preserving total counts, first/last references and instruction/rule identity. Prove genuine financial occurrences are never merged by this policy.
- [ ] Report database/object/sample sizes and the 1 GiB history warning; default transaction-history pruning remains off. Test disk-full without actually filling the user's disk by injecting write failures; checkpoint must remain safe and the monitor visibly pause/retry.
- [ ] Provide an explicit local export/review path with player-text redaction. No network upload occurs. Corrupt/missing export paths report an error without touching game logs.
- [ ] If object cleanup is enabled, protect active/previous/staged/bundled digests and use confined paths. Test that failed cleanup leaves activation/rollback possible. Historical ledger cleanup remains user-scoped and separate.

**Acceptance:** support data and resource pressure are visible; no silent history loss, unbounded diagnostic storage or accidental deletion of rollback objects.

## T8. Selected Wingman host, updater UX and installer integration

**Modify:** `main.py`, `review_ui.py`, `updates.py`, `pyproject.toml`, integration settings/readmes; create `integrations/wingman_target/CONTRACT.md` and `tests/test_target_host_contract.py`.
**Consumes:** existing seven-tool API, UpdateManager digest/source approval methods, committed presentation messages from T6.
**Produces:** one documented, tested host adapter/package for an exact selected Wingman version. Actual host class/method names must come from that release's source; this plan does not invent an API-3 signature.

- [ ] Inspect the selected Wingman release's constructor, lifecycle, tools, configuration, literal notification/TTS and installer registration. Record exact version/commit/runtime and source locations in `CONTRACT.md`; build doubles from that evidence.
- [ ] Move slow service initialization/update-file/database work off the host loop while preserving prepare/unload ownership. Test unload during initial prepare, queued reads, failed cleanup, deferred cleanup and reprepare.
- [ ] Integrate the review button with the exact configured runtime path. Test Update next startup / Later / Skip / Cancel / Rollback, displayed digest changing during review, incompatible definitions and publisher changes. Approval never becomes a model tool. Verify the promised Wingman-startup activation boundary explicitly: constructing another Service during same-process skill reprepare must not silently activate a candidate promised for the next Wingman start. Derive the host-start identity/eligibility from the selected target lifecycle and test it; standalone explicitly requested service startup retains its documented behavior.
- [ ] Bind the optional notification policy only to the verified restricted sink. If the host has no such sink, keep reactions visibly unavailable and label the artifact a tools/update-only candidate; completing the first-release scope requires a safe sink or an explicit user-approved scope revision.
- [ ] Test a fresh isolated install, engine upgrade preserving user data/settings, offline start, approved-next-startup activation, corrupt files, rollback and uninstallation that preserves user-owned data by default. Include the `regex` dependency and bundled JSON in the packaged runtime.
- [ ] Select a maintainer-controlled raw GitHub endpoint and stage a local publishable candidate/release report. Actual publication and real Wingman installation/launch require their own authorization; do all locally reviewable preparation first.

**Acceptance:** host-double tests plus recorded real-host tests pass on the selected release; no claim of cross-version compatibility without evidence. Confirmed user-approved update behavior survives packaging.

## T9. Release gate and handoff

**Modify:** `README.md`, `docs/ARCHITECTURE.md`, `docs/INSTRUCTIONS.md`, `docs/COMPATIBILITY.md`, integration readmes and package version/release notes only after the accepted implementation is complete.

- [ ] Run the full source suite:

```powershell
.\.venv\Scripts\python.exe -B -m unittest discover -s tests -v
.\.venv\Scripts\python.exe -m build
```

- [ ] Install the produced wheel into a separate test environment and repeat import/package/fixture checks; confirm runtime JSON and dependencies are present. Use external temporary directories if Windows ACL cleanup prevents a reliable test run; report that limitation separately from product failures.
- [ ] Run complete independent and chronological replays into new directories:

```powershell
.\.venv\Scripts\python.exe -B tools\corpus_test.py --root 'D:\Roberts Space Industries\StarCitizen' --output reports\release-corpus --workers 2
.\.venv\Scripts\python.exe -B tools\story_test.py --root 'D:\Roberts Space Industries\StarCitizen' --output reports\release-story
```

Choose unused output names. Freeze/record discovered prefixes and compare exact event/state/ledger results; retain all diagnostics and explain changed counts. Run timing instrumentation separately from uninstrumented acceptance measurements.

- [ ] Complete T4 scheduled-stream profiles and T8 real-host tests; collect machine information, artifact hashes, API/build scope, rollback exercise and known limitations. Add a game build to verified declarations only when its stated qualification criteria have been met.
- [ ] Confirm original/reference hashes, no hidden uploads or silent activation, update package provenance, and an explicit unsupported-feature matrix. Keep the extreme private log intact.
- [ ] Present the installable artifact, release report and update bytes for the user/maintainers to review. Do not publish/install/merge as a side effect of preparing this plan.

**Release decision:** ship only the documented qualified scope. Remaining causal investigation, full old-skill parity or unsupported builds are explicit follow-on work; a passing synthetic suite does not make them completed.

## Plan self-review

- Spec sections 5/6 map to T1–T4; 7 maps to T5; 8 maps to T6/T8; 9 maps to T8/T9; 10 maps to T7; 11 maps to T4/T9.
- Existing functionality is retained rather than reimplemented. New interfaces are defined above; host-specific names must be established from the chosen target before coding that adapter.
- This plan changes no runtime settings. Performance/default-policy numbers are proposed acceptance/tuning choices, not claimed observations.
