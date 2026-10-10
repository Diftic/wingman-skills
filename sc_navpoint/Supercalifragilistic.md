# SC NavPoint deterministic telemetry reader plan

**Plan name:** Supercalifragilistic  
**Date:** 2026-08-10  
**Scope:** Improve coordinate acquisition, validation, cadence, and integration without weakening NavPoint's refusal policy or enabling the unproven local-frame router.

---

## 1. Outcome

Build a single internal telemetry pipeline that:

- captures the raw `r_displayinfo 2` block in memory;
- keeps the existing native-resolution fixed-font reader as the authority;
- separates structural stack discovery from fast coordinate-tail updates;
- produces timestamped, explicitly fresh or stale position observations;
- rejects uncertain values instead of repairing or voting them into existence;
- feeds marking, navigation, the HUD, and the ring from one producer;
- adds no AI-callable tool and no model-visible coordinate payload;
- preserves Root-only routing for schema-1 waypoints until local-frame identity is actually solved.

The primary performance target is **five authoritative Root updates per second in a qualified scene**. Ten captures or decode attempts per second may be explored, but **10 Hz is a stretch result, not a release gate**. The three rates below must always be reported separately:

1. raw screen-grab rate;
2. decode-attempt rate;
3. accepted authoritative-position rate.

Correctness remains the first invariant. A missed sample is an availability cost. A wrong accepted sample is a safety failure.

---

## 2. What this plan supersedes

This document replaces `star_citizen_r_displayinfo_coordinate_reader_plan.md` as the implementation plan for a faster NavPoint reader.

It does **not** supersede:

- `ledger/LEDGER.md` for canonical measurements;
- `ledger/REFUTED.md` for approaches that must not be retried;
- `ledger/CORPUS.md` for capture provenance and coverage;
- `SUPERVISION.md` for preservation, installation, and diagnostic hazards;
- `COORDINATE_STACK_IMPLEMENTATION_PLAN.md` for schema-1 persistence and Root-routing invariants;
- the user's OCR-only decision.

If this plan conflicts with one of those sources, stop and resolve the conflict in the ledger before implementing.

---

## 3. Baseline facts

Treat these as constraints, not assumptions:

- The development suite has **862 passing tests**.
- Runtime uses deterministic local OCR only. Vision is not a fallback.
- Normal capture grabs the raw top-right block directly with `mss`.
- The grab region is approximately 667 by 175 pixels: 660 pixels of modeled text width plus the right margin.
- The position path scans eight rows because overlay stack depth changes with context.
- Rows are identified semantically. Physical line numbers are not identities.
- The current glyph matcher works at native resolution with a measured 7.5-pixel character pitch, two raster phases, and a 13-pixel row pitch.
- Autocontrast and image resampling have already been measured to destroy the reader.
- `REFUSE_COST = 15.0` and `REFUSE_MARGIN = 8.0` remain pinned.
- Units are mandatory per component. `m` and `km` may appear in the same row.
- Root/Solar agreement is a corruption tripwire, not independent proof of correctness.
- The best measured live in-skill read was 831 ms median, or 1.20 Hz.
- A full read with the game running has also measured 4.5 to 4.9 seconds. Both measurements remain in the ledger; benchmarks must name the exact path and scene rather than averaging them together.
- Brightness is the dominant availability limit. A live daylit descent and surface session produced stacks on 39 of 96 frames.
- Schema-1 local tracking remains off.
- The outermost pre-Solar row is **not** a universal body frame. It can be a movable ship, and its identity can change during ordinary flight.
- The main menu currently produces a complete, markable phantom stack. Whether to block it remains an explicit product decision.

---

## 4. Non-negotiable safety boundaries

### 4.1 Reader safety

- Never raise `REFUSE_COST` above its calibrated range to improve coverage.
- Never use minimum cost across frames. That rule was measured to relax the refusal floor into the known corruption region.
- Never infer a missing glyph phase from the other phase.
- Never apply autocontrast, resize, upscale, sharpening, or lossy encoding to authoritative pixels.
- Never assume an absent `k` means metres or kilometres.
- Never accept fewer than three complete coordinate components.
- Never allow temporal agreement to rescue a frame that failed a pixel, grammar, unit, Root, Solar, or echo gate.
- Never treat repeated decoding of identical pixels as independent evidence.

### 4.2 Frame and routing safety

- Never select a local frame from a fixed row number.
- Never select it from an `OOC_` prefix, a zone name, coordinate magnitude, scale, or Z pass-through.
- Never compare coordinates from two different stack identities as if they shared a frame.
- Never enable `LOCAL_TRACKING_ENABLED` as part of this reader project.
- Never announce arrival from Root distance for a schema-1 waypoint.
- Never invent a Root/system-frame direction while that convention remains uncalibrated.

### 4.3 Product and repository safety

- Do not add tools or tool parameters for telemetry.
- Do not expose raw coordinates, stack JSON, confidence internals, or thresholds to the language model.
- Do not change Core API types, FastAPI endpoints, or client-generated types.
- Do not emit `server_id` from the local reader. Doing so would re-arm a refuted waypoint-wipe rule.
- Do not strip the retained Vision-shaped code from `scanner.py` without a separate decision.
- Do not run the development-tree `install.bat`.
- Do not clean, reset, or normalize the dirty NavPoint tree.
- Do not rebuild a release, install it, commit, push, or open a PR without separate approval.

---

## 5. Definitions

### Structural scan

A complete decode of the existing eight-row position window. It locates CamDir, the ordered Zone stack, SolarSystem, and Root through the current semantic parser.

### Fast scan

A decode of only the previously located rows and right-aligned coordinate tails needed for the current navigation mode. It may use cached geometry only while that cache remains proven current.

### Authoritative observation

A sample that passed every mandatory single-frame gate and every applicable temporal veto. Only an authoritative observation may:

- be saved as a waypoint;
- replace the current navigation fix;
- update an authoritative distance;
- influence route state;
- contribute to arrival logic.

### Stale observation

The last authoritative observation retained with its original timestamp after a newer attempt failed. It may be displayed as stale or used as an animation origin, but it is not a new position.

### Display estimate

An interpolated value used only for visual smoothing. It must be visibly and structurally separate from authoritative navigation data and must never reach persistence, route selection, or arrival.

### Alignment epoch

An identifier for the current screen resolution, block geometry, vertical origin, and row mapping. A resolution change, structural re-scan, or cache invalidation starts a new epoch.

---

## 6. Target architecture

```text
One background capture worker
        |
        +-- raw block grab, latest-frame slot
        |
        +-- structural scan lane
        |       full eight-row native decode
        |       semantic Root/Solar/stack discovery
        |       alignment epoch publication
        |
        +-- fast scan lane
                cached authoritative row geometry
                native coordinate-tail decoding
                Root/Solar cross-check
        |
        v
Single-frame hard gates
        |
        v
Temporal veto and freshness state
        |
        v
Latest authoritative observation
        |
        +-- mark_location requests a fresh structural observation
        +-- navigation reads the latest compatible observation
        +-- HUD receives authoritative/stale/offline state
        +-- ring receives authoritative state or an explicit refusal
```

There must be one capture producer. Tools and the polling loop consume its state or request a fresh structural observation; they do not start competing OCR jobs.

Use a latest-frame slot rather than an unbounded queue. When decoding falls behind capture, discard superseded unprocessed frames. Old telemetry is not made useful by processing it later.

---

## 7. Observation contract

Define an internal immutable observation type in a pure runtime module. It should carry at least:

- monotonically increasing capture sequence;
- wall-clock timestamp for presentation;
- monotonic timestamp for age and velocity calculations;
- alignment epoch;
- source lane: structural or fast;
- accepted coordinate stack or the accepted Root/Solar subset;
- CamDir when present and trusted;
- per-frame hard-gate result;
- temporal result;
- freshness state;
- stable refusal/reacquisition reason code;
- diagnostic measurements already produced by the reader, without model exposure.

Do not put this type in `api/interface.py`. It is internal to the skill.

The contract must make it impossible to confuse:

- no capture attempted;
- capture in progress;
- fresh authoritative fix;
- stale retained fix;
- display-only interpolation;
- overlay absent;
- unusable image;
- decode refusal;
- parser or scanner rejection;
- structurally incompatible frame transition.

---

## 8. Structural scan lane

Retain the current eight-row native decode as the authoritative way to discover layout.

The structural scan must:

1. capture the existing raw block region;
2. run the fixed-geometry saturation precondition;
3. fit or revalidate vertical alignment;
4. decode all `POSITION_ROWS` with per-row phase and color selection;
5. classify rows by their labels and full grammar;
6. build the ordered coordinate stack through exact Root and Solar anchors;
7. run `scanner.parse_payload` and all existing echo/unit/plausibility gates;
8. publish row indexes and geometry only after the whole observation succeeds.

Run a structural scan:

- for every mark request;
- when navigation starts;
- after resolution or frame-shape changes;
- after alignment invalidation;
- after any fast-scan grammar mismatch;
- after Root or Solar moves from the cached row;
- periodically at a cadence established by measurement;
- after a prolonged refusal or stale period;
- after a stack-depth transition.

Do not hard-code a revalidation interval in the plan. Measure the cost and failure exposure first, then place the chosen value in the ledger with its evidence.

---

## 9. Fast scan lane

The fast lane is an optimization under a valid structural epoch, not a second parser with weaker rules.

### 9.1 Initial scope

For schema-1 Root-only navigation, decode:

- Root coordinate tail;
- SolarSystem coordinate tail;
- CamDir only if a consumer can use it safely;
- the minimum label cells needed to prove that the cached rows still carry the expected structural kinds.

Do not decode a local candidate for routing while local tracking is disabled. Marking still requires a structural scan because it persists the complete accepted stack.

### 9.2 Geometry

- Reuse the structural scan's vertical origin and row indexes only within the same alignment epoch.
- Coordinate lines are right-aligned, but token lengths vary. Decode a sufficient right-side suffix and parse it with the existing anchored coordinate-tail grammar.
- Do not define independent fixed X/Y/Z boxes whose positions assume a constant digit count.
- Prove the cropped suffix contains every supported sign, decimal, unit, and coordinate length represented in the corpus and synthetic boundary fixtures.
- Any truncated prefix or tail is a refusal, never permission to infer a value.

### 9.3 Recognition

Start with the existing complete glyph bank and matcher.

A coordinate-specific candidate alphabet may be benchmarked only if all of these hold:

- it includes digits, signs, decimal point, spaces, `m`, `k`, and every structural character the fast lane decodes;
- exhaustive equivalence tests show the same winning glyph, cost, margin, and refusal decision as the full alphabet for every affected corpus cell;
- missing templates fail closed;
- the optimization is removed if it changes any accepted character.

Alphabet restriction is optional. It must not be assumed as the source of the target rate.

---

## 10. Performance work

Optimize measured work in this order:

1. preserve the raw block-only grab;
2. remove unnecessary rows from fast scans, not structural scans;
3. batch candidate scoring across cells;
4. batch compatible cells across rows;
5. evaluate batching across a small grab axis while preserving per-frame decisions;
6. remove Python allocation and sorting overhead where the exact top-two result can be obtained equivalently;
7. evaluate a coordinate-specific alphabet only under the equivalence gate above;
8. profile alignment and diagnostic overhead separately from recognition.

Every optimization must prove bit-for-bit or decision-for-decision equivalence before a timing result matters.

Benchmark with:

- warm and cold alignment;
- Star Citizen running;
- at least one dark/clean scene;
- one structured background;
- one bright/refusal-heavy scene;
- structural and fast lanes separately;
- diagnostics enabled exactly as they ship;
- p50, p95, maximum latency, accepted-fix rate, and CPU time;
- total CPU utilization while the game is under representative load.

Do not quote a grab-only timing as a decode timing. Do not combine the 831 ms and 4.5-to-4.9-second paths without naming what differed.

---

## 11. Image preprocessing experiments

Local contrast processing may be evaluated as an offline feature experiment only.

Candidate experiments include local background subtraction, top-hat/black-hat pairs, or a high-pass representation. None may enter the authoritative path unless it:

- preserves native geometry and raster phase;
- improves accepted coverage on held-out bright/structured scenes;
- produces zero additional wrong accepted glyphs on truth-labelled cells;
- preserves every current hard refusal fixture;
- has a measured CPU cost compatible with the cadence target;
- never replaces a raw-pixel guard whose calibration assumes original 0-to-255 values.

Do not upscale or sharpen. If an experiment requires resampling, it is rejected for this reader.

The existing physical glyph/background model remains the control in every comparison.

---

## 12. Temporal policy

Temporal logic is a veto and a state machine. It is not an OCR repair engine.

### 12.1 Order of operations

For each frame:

1. apply image and cell refusal gates;
2. parse exact grammar and units;
3. require Root and Solar;
4. apply the Root/Solar disagreement tripwire;
5. apply scanner echo and plausibility gates;
6. verify alignment epoch and structural compatibility;
7. only then compare with recent authoritative observations.

A temporal check may reject step 7. It may never reverse a rejection from steps 1 through 6.

### 12.2 Multi-grab behavior

If several frames are decoded as one estimate:

- keep each frame's winning character and refusal decision separate;
- aggregate cost or margin with the median only when the character choice agrees;
- treat character disagreement as changing text or instability;
- refuse the aggregate or fall back to a separately valid newest frame;
- never take minimum cost;
- never use pixel-wise median imagery to manufacture a coordinate glyph;
- never majority-vote a missing unit, sign, decimal point, or digit.

### 12.3 Continuity

Continuity checks must be calculated only within compatible coordinate frames and alignment epochs.

Do not use one global maximum speed. Legitimate discontinuities include rapid travel, respawn, server transitions, and stack-identity changes. Instead:

- detect and name discontinuities;
- invalidate velocity history;
- enter reacquisition state;
- require a fresh structurally valid observation before resuming authoritative updates;
- keep the last valid fix stale during reacquisition;
- never interpret candidate-depth equality as frame identity.

Continuity can catch an isolated syntactically valid digit substitution. It cannot certify a stable correlated misread and must not be described as doing so.

### 12.4 Freshness and interpolation

- Preserve the last authoritative observation with its original timestamp.
- A refused frame never refreshes that timestamp.
- The ring must suppress its live bubble immediately on refusal, as it does now.
- Display interpolation may bridge a short visual gap but must be tagged display-only.
- Marking, route switching, distance announcements, and arrival require an authoritative observation.

---

## 13. Routing boundary

This work improves acquisition without claiming to solve local-frame identity.

- Keep `LOCAL_TRACKING_ENABLED = False`.
- Keep Root as the canonical long-range address for schema-1 waypoints.
- Preserve complete stacks on new marks for future research.
- Do not compare saved and current local candidates as bare numbers.
- Do not restore the outermost-row rule after merely excluding ship-only stacks; live evidence shows candidate identity changing between jump point, ship, and body during ordinary flight.

Any future local-routing project needs a stable, measurable frame-identity invariant. It is a separate product decision and plan.

---

## 14. Current-contract cleanup before integration

Complete these narrowly scoped fixes before introducing the provider so new code does not inherit contradictory contracts:

1. Consolidate or explicitly rename the reader entry points so runtime stack support cannot be lost by calling the legacy-only `read_payload` helper.
2. Correct the default skill prompt:
   - schema-1 surface marks currently use coarse Root-only distance;
   - local direction and arrival remain gated off;
   - complete stacks may be captured where the legacy body parser refused;
   - `list_navpoints` accepts `body`, not `server_id`.
3. Account for saved Wingman prompts, since changing `default_config.yaml` alone may not update an existing configured Wingman.
4. Validate every declared custom property in `validate`, while continuing to retrieve values just in time.
5. Route runtime output through `Printr` according to the repository convention:
   - synchronous calls only with `server_only=True`;
   - awaited async calls for client-visible messages;
   - no bare `print` in runtime code.
6. Keep the skill on demand and add no model-visible telemetry tool.

These fixes must be separate commits or reviewable waves from OCR behavior changes.

---

## 15. Corpus and ground truth

The existing corpus is broad in frames but narrow in independent places, ships, and players. Much of it lacks exact truth text.

Before claiming a correctness improvement, build a truth-labelled evaluation set containing:

- the exact lossless block pixels;
- an exact transcription of every authoritative row;
- Star Citizen version and resolution;
- capture source and timestamp provenance;
- player state: seated, standing, landed, flying, deep space, jump point, or menu;
- whether the transcription was independently checked;
- background class and representative brightness measurements.

Required scene coverage:

- clean dark space;
- structured starfield;
- bright sky;
- sunlit terrain;
- jump point before and after departure;
- ship-only stack;
- landed seated and standing-clear pairs;
- at least two ships;
- at least two planets or moons;
- main menu phantom stack;
- resolution or overlay-position changes;
- mixed `m` and `km` coordinates;
- signs, decimal points, zeros, and maximum observed token lengths.

Report results per session and regime. A single aggregate can hide a reader that works only in darkness.

---

## 16. Required tests

### Reader equivalence

- Structural scans preserve every current decode and refusal decision.
- Fast and structural scans agree on Root and Solar for every frame where both succeed.
- Any disagreement refuses the fast observation and schedules structural reacquisition.
- Native block capture remains pixel-identical to the corresponding full-screen crop.
- Fast suffix geometry covers every corpus and boundary token without truncation.
- Per-row phase selection remains independent.
- Existing thresholds remain exactly pinned.

### Parser and stack

- Exact Root and Solar anchors remain mandatory.
- Root/Solar disagreement refuses.
- Mixed units normalize correctly.
- Missing `k`, sign, decimal, digit, or component refuses.
- Stack depth changes trigger structural reacquisition.
- The runtime entry point accepts stack-only captures wherever current runtime does.
- Login-screen behavior is pinned to the explicit product decision once made.

### Temporal behavior

- Hard-gate failure cannot be rescued by temporal agreement.
- Minimum-cost aggregation is impossible.
- Identical pixels are not counted as independent evidence.
- Character disagreement refuses or selects an independently valid newest frame.
- A stale retained fix keeps its original timestamp.
- Display interpolation never reaches marking, routing, distance announcements, or arrival.
- Frame transitions clear velocity history.
- Refusal suppresses the ring bubble immediately.
- No failed observation replaces the last authoritative fix.

### Concurrency and lifecycle

- Only one producer grabs and decodes at a time.
- A mark request during navigation cannot receive another caller's outcome.
- A stopped or deleted target cannot be revived by an in-flight decode.
- The latest-frame slot remains bounded under decoder backpressure.
- `unload` stops and joins the provider without leaving a capture or UI thread alive.
- Repeated prepare/unload cycles do not leak resources.

### Model and token boundary

- No new tool is registered.
- No tool result contains coordinates, stack JSON, thresholds, or reader diagnostics.
- Tool descriptions and the configured prompt match actual schema-1 behavior.
- Discovery remains on demand.

### Mutation checks

For each safety guard, deliberately mutate the implementation, run the named focused test, confirm it fails, restore the file byte for byte, and rerun the focused test. At minimum mutate:

- mandatory unit suffix;
- Root requirement;
- Solar requirement;
- Root/Solar disagreement;
- fast/full mismatch fallback;
- temporal-rescue prohibition;
- stale timestamp preservation;
- display-only interpolation boundary;
- local-tracking feature gate;
- bounded latest-frame behavior.

A test that never failed under its intended mutation is not accepted as evidence.

---

## 17. Performance and quality gates

Record all measurements in the ledger with hardware, game state, capture set, code identity, and command.

### Correctness gate

- **Zero wrong accepted coordinate components** across the truth-labelled evaluation set.
- Zero regressions in current accepted values.
- Zero current refusal guards weakened.
- Every fast/full disagreement fails closed.

### Availability gate

- Report accepted observations divided by attempts for every named scene.
- Do not allow aggregate coverage to fall below the existing reader on any safety-critical scene without explicit approval.
- A release candidate must demonstrate usable fixes in the primary landed-ship use case and on a daylit surface.

### Cadence gate

- Structural scan cadence is measured and reported separately.
- Fast Root updates reach at least 5 accepted fixes per second in the qualified clean scene on the target machine.
- Capture and decode queues remain bounded during the measurement.
- Ten accepted fixes per second is recorded if achieved, but is not required for release.

### Latency and resource gate

- Report p50, p95, and maximum observation age at publication.
- Report CPU usage while Star Citizen is under representative load.
- No optimization may improve throughput by allowing stale frames to accumulate.
- Ring animation remains smooth through its render interpolation even when authoritative fixes arrive below render rate.

---

## 18. Implementation waves

### Wave 0: preservation and baseline

1. Read the repository and skill instructions plus all ledger sources.
2. Record tracked and untracked status without cleaning anything.
3. Snapshot or hash every file in scope.
4. Run the full NavPoint suite; expect 862 tests unless a later ledger entry accounts for a new baseline.
5. Record the current reader's corpus decisions and performance before changing code.

Exit gate: preservation is reproducible, baseline is green, and no release or installed file changed.

### Wave 1: contract cleanup

1. Resolve the runtime-versus-legacy reader entry-point ambiguity.
2. Correct the model prompt and tool signature description.
3. Validate all custom properties.
4. Bring touched logging into `Printr` compliance.
5. Add tests proving each corrected contract.

Exit gate: behavior is unchanged except the explicitly corrected messages and validation; the full suite is green.

### Wave 2: observation model and benchmark harness

1. Add the immutable internal observation and state types.
2. Add pure freshness and state-transition logic.
3. Build repeatable structural/fast benchmark instrumentation.
4. Produce the first named baseline report.

Exit gate: no runtime consumer uses the new model yet; pure tests and baseline measurements are complete.

### Wave 3: single producer

1. Add one lifecycle-owned capture worker.
2. Add a bounded latest-frame slot.
3. Preserve per-caller diagnostic attribution for explicit fresh requests.
4. Make shutdown deterministic.

Exit gate: existing structural reads pass through the producer with identical outcomes; concurrency and unload tests pass.

### Wave 4: structural epoch

1. Publish semantic row mapping only from accepted structural scans.
2. Invalidate it on resolution, alignment, stack, or grammar changes.
3. Add reacquisition states and reason codes.
4. Prove variable stack depth and row movement.

Exit gate: no fast coordinate is authoritative yet; epoch invalidation is mutation-proven.

### Wave 5: fast Root/Solar lane

1. Decode the cached Root/Solar tails and minimal structural proof.
2. Reuse the existing unit and cross-check gates.
3. Compare fast output with structural output across the full corpus.
4. Optimize batching without changing decisions.

Exit gate: zero fast/full accepted mismatch, five-Hz target measured or an evidence-backed bottleneck report produced.

### Wave 6: temporal veto and freshness

1. Add same-epoch continuity checks.
2. Add explicit discontinuity and reacquisition behavior.
3. Add median multi-grab evaluation only where glyph choice agrees.
4. Add display-only interpolation behind a separate presentation boundary.

Exit gate: temporal logic can reject but cannot rescue; stale and interpolated data cannot reach authoritative consumers.

### Wave 7: navigation integration behind a flag

1. Feed Root-only schema-1 navigation from the provider's latest authoritative observation.
2. Make mark requests demand a fresh structural observation.
3. Preserve compact tool responses.
4. Keep local tracking disabled.
5. Keep the current synchronous structural path available for controlled fallback during qualification.

Exit gate: marking, navigation start, polling, refusal, stop, delete, HUD, and ring tests all pass without model-visible expansion.

### Wave 8: corpus qualification and supervised flight

1. Replay every lossless session through both lanes.
2. Add the missing truth labels and scene metadata.
3. Run a supervised flight covering the required scene matrix.
4. Verify frame counts while each pose is still held.
5. Record exact availability, false-accept, cadence, latency, and CPU results.
6. Append facts to `LEDGER.md`, failures to `REFUTED.md`, and provenance to `CORPUS.md`.

Exit gate: all correctness and availability gates pass. A wrong accepted coordinate is an immediate stop.

### Wave 9: release, separately approved

1. Ask for implementation approval.
2. Select the next skill version.
3. Generate `release_version` only through the guarded release script.
4. Run source and packaged suites plus manifest, parity, security, metadata, and artifact checks.
5. Confirm no corpus, plan, ledger, backup glyph bank, database, log, cache, or test artifact entered the package.
6. Request explicit approval before installation.
7. If PR work is approved, ask for the Core GitHub issue or create and link one. Create a client PR only if client code actually changed; otherwise remove that worktree.

---

## 19. Mandatory stop conditions

Stop and report rather than improvising if:

- a fast scan accepts a coordinate different from the structural scan;
- any current refusal fixture becomes accepted;
- a preprocessing transform requires resampling or threshold relaxation;
- five-Hz throughput requires unbounded queues, concurrent independent readers, or stale publication;
- temporal logic must repair a missing digit, unit, sign, decimal, Root, or Solar value;
- a continuity rule rejects legitimate frame transitions without a safe reacquisition path;
- local routing appears to require names, prefixes, row numbers, scale, Z pass-through, or bare candidate-depth matching;
- the main-menu phantom stack needs a product decision that has not been made;
- Core API or client-generated type changes appear necessary;
- `server_id` would be emitted;
- the dirty tree cannot be preserved confidently;
- source, release, and installed copies cannot be distinguished and hash-checked;
- a truth-labelled sample produces one wrong accepted coordinate;
- an implementation test stays green when its claimed guard is deliberately removed.

The stop report must include the exact capture or test, code identity, alignment epoch, structural rows, fast result, hard-gate result, temporal result, and the smallest unresolved decision. Raw coordinates belong in local diagnostics, not model-visible output.

---

## 20. Definition of done

The project is complete only when:

- one bounded producer owns capture and decoding;
- structural and fast lanes share the same authoritative grammar and safety gates;
- structural scans remain semantic and support variable stack depth;
- fast Root/Solar updates meet the five-Hz qualified-scene target or the user explicitly accepts a measured lower result;
- the truth-labelled set contains zero wrong accepted coordinate components;
- bright and structured availability is measured per scene rather than implied by a clean aggregate;
- stale and interpolated positions cannot drive marking, routing, distance announcements, or arrival;
- local tracking remains disabled;
- current model prompt, tool signatures, and actual behavior agree;
- no new tool or model-visible telemetry payload was added;
- every new safety test was mutation-proven;
- the full source and packaged suites pass;
- the ledgers describe both successful evidence and failed hypotheses;
- release, installation, commit, push, and PR actions occurred only after their separate approvals.

