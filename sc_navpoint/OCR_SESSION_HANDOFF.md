# CURRENT — 2026-09-14: planetary frame candidate staged, live test pending

Version 4.9.0.23 source implements lower Planet label matched to active Zone,
planet-local-only save/navigation, no Solar fallback, target-dependent 15 km
precision and slowdown notice, full-precision saves, held display with capture
age, no retries. Final suite: 1144 passed in 19.99s. Four new synthetic full
panels decoded once each, all exact; cold identification 0.28–0.30s, known-frame
fresh reads about 0.077s. Synthetic timing/accuracy is not live evidence.

Candidate with bundled OpenCV staged at:
D:/Navpoint-background-20260909/candidate-active-frame-4.9.0.23
Installed Wingman remains unchanged. Frozen runtime, real planetary panel,
save/move/return and rolling correct-read cadence remain unverified. User has
one pending readiness request; no capture monitor remains armed.
Full handoff: D:/PycharmProjects/wingman-ai/skills/sc_navpoint/ACTIVE_FRAME_INTEGRATION_2026-09-14.md
Original 240-frame audit labels unchanged. Never re-OCR exhausted audit images.

--- Previous record follows ---

# CURRENT — 2026-09-14: target-dependent precision implemented in experimental reader

User requirement: discard coordinate fractional digits at long range; below
15 km require at most 10 m total position error. Implemented candidate cruise
cells and conservative 15 km transition; approach Root/Solar agreement allows
up to 10 m total while retaining both observed values. Actual accuracy remains
unverified: agreement is not truth. No-target/save path remains exact.
Optional target context wired into scratch V7/V8 and bounded live runner.
Wingman production integration and spoken slowdown advisory remain pending.
22 policy/integration tests and 9 existing reader tests pass. Cached text only:
176 proposals permitted versus 152, in both hypothetical distance scenarios;
24 newly permitted proposals are not newly verified correct reads. No OCR reruns.
Exact audit remains 96 correct, 29 wrong, 27 uncertain accepted / 88 refused.
See D:/Navpoint-background-20260909/DISTANCE_PRECISION_POLICY_2026-09-14.md.
Earlier statements that no tolerance was agreed or that the rule is only a
proposal are historical. No observer or readiness question pending.

---

# CURRENT — 2026-09-14: full bright-sun visual audit complete

All 240 saved frames inspected. Of 152 accepted proposals: 96 manually exact,
29 confirmed wrong, 27 unresolved; 88 other frames rejected. Previous partial
7-correct/3-wrong figures below are historical and superseded. No OCR reruns.
Manual source-to-cached-output comparison, not blind transcription. At most one
extra visual recheck per flagged image; unresolved cases dropped from successes.
Minimum 36 verified correct fresh reads per rolling 10 seconds in this 25.46 s
sample, exceeding the target of 20. Acceptance reliability remains a separate
failure: 29 known wrong proposals; V8 remains experimental and undeployed.
Quantified examples affect fractional coordinates by 0.4–9 m on a listed axis;
not an exhaustive bound on position error. No cross-frame error probability claimed.

User proposed distance-sensitive precision and an advisory to slow down within
15 km of a target. Recorded, not implemented; no relaxed acceptance tolerance agreed.
Slower movement reduces stale-position displacement; improved recognition untested.
Next: specify physical error/age requirements before changing acceptance behaviour.
No observer, new capture, readiness question, or shutdown pending.
Full report: D:/Navpoint-background-20260909/OCR_V8_FULL_MANUAL_AUDIT_2026-09-14.md
All earlier CURRENT sections and capture requests below are historical.

---

# CURRENT — 2026-09-14: bright-sun test found accepted errors

240 fresh frames / 25.46 s; 9.43 captures/s; 152 proposals, 88 refusals.
Partial diagnostic audit: seven verified correct acceptances, three confirmed wrong
acceptances; 142 acceptances remain unchecked. Frames 150 and 235 have wrong matching
Root/Solar values. No adjacent-frame persistence probability has been established.
The earlier normal-view 25-per-ten-second result is sample-specific. Bright-sun
verified cadence remains unestablished; this partial audit is not a measured rate failure.
V8 stays experimental. No observer or readiness request pending. No OCR retries.
See D:/Navpoint-background-20260909/OCR_V8_BRIGHT_SUN_TEST_2026-09-14.md.
Earlier CURRENT/pending-capture notices below are historical and superseded.

---

# CURRENT — 2026-09-14: V8 live throughput demonstrated in one sample

Resumed after shutdown. 240 new frames / 29.13 s; 231 accepted, nine refused.
80 evenly spaced frames audited: 77 accepted correct, three refused; 154 acceptances
remain unchecked. Minimum 25 verified complete reads per rolling ten seconds;
excluding seven visually corrected manual labels still establishes minimum 20.
No OCR retries. Prior synthetic false accepts remain; V8 is still experimental.
Next: fresh deliberate bright-background/camera-sweep sample after user replies
starting. Request sent, no observer running. Broader validation/integration remain.
See D:/Navpoint-background-20260909/OCR_V8_LIVE_VALIDATION_2026-09-14.md.
Earlier pause/foreground-blocked status notes below are historical and superseded.

---

# Session closeout — 2026-09-13, 20:04 Europe/Oslo

**PAUSED BY USER — logs saved for shutdown; resume tomorrow (2026-09-14).**
This closeout supersedes earlier ACTIVE/waiting-for-ready notices below.
The earlier readiness request is withdrawn. No observer or training job is running.
The formal goal remains blocked, not achieved; no further capture is requested tonight.

## Current result

The target is 20 independently correct, fresh, complete reads per rolling 10 seconds.
Rejection streak frequency and duration are separate diagnostics; brief gaps do not
automatically fail. Each fresh image gets one attempt, without recovery, retries or
old-image queues. Failed reads retain the last successful display with its age;
held values and unchecked predictions never count as new verified successes.

V8 training and export finished. The experimental model is in specialist-ascii-ui-v8;
SHA256: 0c775c270fda57437b34af99a1e0e8609a4e86dcbd3265201fde061b5aac0a39.
320 CPU steps took 340.6 seconds; new synthetic validation was 49/64 exact.
Export parity and Wingman development-interpreter compatibility passed. This does
not establish compatibility with the installed/frozen Wingman application.

Fresh synthetic row challenge: V8 85/96 required fields correct versus V7 55/96,
using different new images with matching category balance (not a paired or live test).
V8 complete-block challenge: 48 blocks, 23 accepted, only 17 fully correct;
six accepted-but-wrong results remain (five identifiers and one camera sign).
Median block processing was 79.47 ms. These are synthetic results, not live accuracy.
No parser gates were loosened, and V8 has not been deployed or staged into source models.

The V8 live attempt timed out because the game was not foreground: no V8 live result.
The previous V7 sample lasted only 6.43 seconds, insufficient for the rolling ten-second
criterion; 19 accepted frames were independently checked, 18 correct and one wrong.
Therefore the requested verified rate and overall feature completion remain unproven.
The isolated OpenCV dependency bundle is prepared, but installed skill/release are untouched.
Existing dirty repository changes were preserved; no commit or release regeneration.

## Restart tomorrow

1. Bring Star Citizen forward with r_displayinfo 2 visible when the user is ready.
2. Run check_capture_ready.py using the scratch .venv Python; it only checks eligibility.
3. Once eligible, run live_portable_v6.py --reader v8 --frames 240 for fresh images.
4. Independently transcribe original captures before looking at model predictions.
5. Use verified_cadence.measure to evaluate correct reads in rolling ten-second windows,
   alongside wrong accepts and rejection streaks. Pay special attention to names and signs.
6. Continue model work based on this evidence; do not count confidence as correctness.
7. Installed Wingman integration and save/fly-away/return validation still remain afterward.

Completed sessions 81335 and 90403 and failed capture 31214 are terminal; do not restart
or poll them. No automatic capture or background wait is armed for tomorrow.

Evidence: OCR_V8_UI_TRAINING_2026-09-13.md, v7-v8-new-ui-challenge/results.json,
v8-new-ui-full-blocks/results.json, v8-wingman-interpreter-compatibility.json,
and live-portable-v7-20260913-130851/cadence-ten-second-criterion.json.

---

**CURRENT — V8 finished; waiting for game foreground for the longer live test.**
Target: 20 independently correct fresh complete reads per rolling 10 seconds.
Brief rejection streaks are diagnostic, not automatic failures. One user-ready
request is pending; last eligibility check returned game not foreground.
Training 81335 and failed capture attempt 31214 are TERMINAL; no observer armed.
V8 export/parity and development-interpreter compatibility passed. New synthetic
row challenge: 85/96 required fields exact; full blocks: 17 correct accepted,
six wrong accepted (five names, one camera sign), out of 48 generated blocks.
Read OCR_V8_UI_TRAINING_2026-09-13.md in D:\Navpoint-background-20260909.
Next: recheck eligibility, then fresh --reader v8 --frames 240 capture and audit.
Current turn made progress; first occurrence of live-input blocker. Goal ACTIVE.
Installed/runtime skill unchanged; no shutdown. All earlier banners superseded.

---

**CURRENT — target clarified: 20 correct fresh complete reads per rolling 10 seconds.**
Brief rejection streaks are expected and diagnostic, not automatic failures.
Wrong accepted readings and unchecked proposals never count toward the 20.
V8 interface-background training started: poll live shell session 81335; do not
restart on timeout. Previous V7 training session 90403 is terminal.
Read OCR_V8_UI_TRAINING_2026-09-13.md in D:\Navpoint-background-20260909.
After export/parity, use NEW gameplay captures lasting >10 seconds (--frames 240).
V7's 6.43-second sample is insufficient for this criterion; its average was 2.80
independently correct reads/s with one checked wrong identifier. Goal active.
Runtime/installed Wingman unchanged; no shutdown. All earlier banners superseded.

---

**CURRENT — V7 finished; fresh live audit demonstrates average rate, not steady coverage.**
18 independently correct complete reads over 6.4325 s = 2.80/s lower bound.
One confirmed accepted identifier error (keeger -> keeyer); 15 accepts unchecked.
48 captures, 34 proposals, maximum accepted/verified gap 1.3163 s. Goal NOT met.
Training session 90403 is TERMINAL and all captures finished; do not restart it.
Next: targeted synthetic ship-interface background augmentation, preserving V7
and using new captures for validation. Do not loosen gates or rerun old images.
Read OCR_V7_REAL_TRAINING_2026-09-13.md under D:\Navpoint-background-20260909.
Isolated OpenCV/V7 compatibility check passed in Wingman's development Python;
installed Wingman, runtime model and release remain unchanged. No shutdown.
All older current/readiness banners below are historical and superseded.

---

**CURRENT — V7 real-game training trial started.**
Poll training shell session 90403 before further work; last verified step 140/320.
Do not launch another training job on timeout. Details and export/live-test steps:
D:\Navpoint-background-20260909\OCR_V7_REAL_TRAINING_2026-09-13.md.
Two-correct-reads/s goal active, not achieved. Runtime/installed Wingman unchanged.
All earlier current banners below are superseded by this experiment status.

---

**CURRENT — target is TWO correct fresh complete reads per second.**
One attempt per fresh image; no recovery, retries or old-frame queues. Held
last-success display remains visible with age and never counts as fresh success.
V6 and larger Small model both have confirmed accepted-digit errors.
Six-thread Small live test: 19/24 accepted, 1.12 proposals/s, max gap 2.013 s;
three checked accepted frames match, one is wrong, one checked frame is refused.
The new goal is ACTIVE and NOT achieved. No production promotion or deployment.
Next: larger-model operation profiling and a separate recognition experiment
using live failure evidence with untouched validation data. No user-readiness
request, capture process or shutdown is pending. All earlier banners superseded.
Read `D:\Navpoint-background-20260909\OCR_V6_LIVE_VALIDATION_2026-09-13.md`.

---

**CURRENT — walking and larger-model tests completed, 13 September.**
V6: 93/120 accepted at 4.72/s, but three checked accepted frames contained
visually confirmed wrong digits, including character scores above 99.98%.
Larger local Small model: 22/24 accepted at 1.04/s; five independent image checks
all match, but maximum proposal gap was 2.63 s. Remaining outputs unverified.
Neither result establishes one correct complete read every second in movement.
Next: profile larger-model row batching on fresh captures; no retries or fallback.
No capture observer, readiness request, production deployment or shutdown pending.
Read `D:\Navpoint-background-20260909\OCR_V6_LIVE_VALIDATION_2026-09-13.md`.
All earlier current/readiness banners below are historical and superseded.

---

**CURRENT — stationary control completed, 13 September.**
120/120 identical proposals at 6.87/s; three original-image spot checks match,
and all outputs match their shared reference. Maximum proposal gap 0.180 s.
This was a different hangar scene, so it does not isolate motion as the cause.
Earlier V6 false accepts remain confirmed: no navigation promotion or deployment.
Next: short movement in the same hangar scene with view direction steady; user
readiness pending. No observer, training, deployment or shutdown is active.
Read `D:\Navpoint-background-20260909\OCR_V6_LIVE_VALIDATION_2026-09-13.md`.
Earlier stationary-readiness requests below are superseded.

---

**CURRENT — V6 live validation failed promotion, 13 September.**
Two confirmed accepted numeric errors occurred in the longer live run, including
a 40 m local error and correlated Root/Solar mistakes. First short run: 18 checked
correct outputs with max 0.6585 s gap; longer run: 194/360 proposals, max 1.263 s
gap. Do not infer perfect reads from accepted proposals. Read
`D:\Navpoint-background-20260909\OCR_V6_LIVE_VALIDATION_2026-09-13.md`.
Stationary ship/view control readiness is pending. No capture observer, training,
deployment or shutdown is running/pending. Installed Wingman is unchanged.
All earlier readiness/current banners below are superseded by this finding.

---

**CURRENT — 13 September: single-pass integration implemented; V6 candidate staged in source.**

Resume from `D:\PycharmProjects\wingman-ai\skills\sc_navpoint\OCR_INTEGRATION_2026-09-13.md`.
One attempt per image, no recovery or FPS cap; original capture timestamps retained.
Recent valid ring direction is held with its age on failed reads; the coordinate
panel shows read age. All 1,097 NavPoint tests pass. V6 improved exact synthetic
held-out rows from 130/192 to 185/192 at unchanged row speed. Fresh synthetic
blocks: 29/64 accepted and all 29 correct, versus four wrong accepts with V5.
The conservative blank-row refusal accounts for many drops; this is not live
accuracy or a completed navigation feature. V6 is opt-in and off by default.

No production install, release regeneration, active capture monitor or shutdown
is pending. OpenCV packaging for installed Wingman remains unverified. The latest
foreground guard says Star Citizen is not foreground; the next live test needs
the connected game visible with `r_displayinfo 2`. No `/showlocation` or manual
coordinate input is required. All earlier paused/shutdown/current banners below
are historical and superseded by this entry.

---

**CURRENT — 13 September: paused; progress saved and shutdown requested by user.** Resume from `D:\Navpoint-background-20260909\SESSION_HANDOFF_2026-09-13.md`. Three `/showlocation` clipboard snapshots confirmed without OCR; paired Root comparison differs by 1.0584 m, cause unresolved. Short uncapped OCR: 24 complete proposals at 7.01/s, not fully verified accuracy. All observers stopped; no production deployment. No retries or fixed FPS cap; final UI hold-last-success policy retained. Earlier CURRENT banners below are historical.

**HISTORICAL — 12 September: project resumed, uncapped single-pass OCR.** No retries or fixed FPS delay; discard failures and capture fresh images. Final UI will retain the last successful display without counting it as fresh. Read `D:\Navpoint-background-20260909\OCR_CONTINUATION_2026-09-12.md`. Connected-game timing/accuracy pending; no deployment.

**CURRENT — live v4 captured, v5 sharp-edge training trial next.** Live106/120 complete,2.59proposals/sec,2.37-second maximum gap;14recoveries all failed. Eight selected coordinate/camera spot checks matched. Recovery1Hz NOT met. Read `D:\Navpoint-background-20260909\OCR_EVENING_CONTINUATION_2026-09-11.md`. No deployment or shutdown.

**CURRENT — frozen v4 evaluated, 11 September evening.** Fresh synthetic test:117/120 exact coordinates and direction,three discarded,zero wrong accepted; median185ms,maxrecovery1.155s. Full live accuracy and1Hz recovery NOT established. Fresh capture waits ended because game was not foreground. Read `D:\Navpoint-background-20260909\OCR_EVENING_CONTINUATION_2026-09-11.md`. No capture process, deployment or shutdown pending. Older banners below are historical.

**CURRENT — v4 training completed (218 steps), 11 September evening.** Read `D:\Navpoint-background-20260909\OCR_EVENING_CONTINUATION_2026-09-11.md`. Live48/60 complete with a3.111-second gap; confidence cutoff caused19 unnecessary retries. New no-cutoff/recovery-veto experiment awaits fresh timing. Results remain unverified; no deployment or shutdown. Older training-active banners below are historical.

**CURRENT — OCR experiment active, 11 September evening.** V3 was rejected after accepted wrong readings. Read `D:\Navpoint-background-20260909\OCR_EVENING_CONTINUATION_2026-09-11.md`. A complete-font/ASCII v4 trial is training; no deployment or shutdown is pending. The earlier live54/60 result had a1.939-second gap and was not independently verified accuracy. Earlier status banners below are historical.

**CURRENT — evening continuation, 11 September 2026.** Work resumed; no shutdown is pending. Read `D:\Navpoint-background-20260909\OCR_EVENING_CONTINUATION_2026-09-11.md`. New live reader produced 54/60 complete proposals, but a 1.939-second gap still fails the recovery requirement. These are not 54 independently verified readings. Full-row candidate v3 is being prepared. Installed Wingman and database unchanged. Older paused/pending statements below are historical.

# SC NavPoint handoff — 10 September 2026

**PAUSED FOR USER-REQUESTED SHUTDOWN — 11 September 2026.** Tests finished: 1,078 skill tests plus five scratch tests pass. Read `D:\Navpoint-background-20260909\OCR_SHUTDOWN_HANDOFF_2026-09-11.md`. The trained specialist plus one Small-model recovery reads all 21 labelled coordinate frames correctly; the 120-frame unlabelled challenge produces 103 proposals, which is not verified accuracy. No Wingman deployment; no pilot action is pending. Earlier running/pending statements below are historical.

**Current objective: learned game-overlay OCR.** The user stopped the old reader-tuning goal and approved comparing neural models and training a Star Citizen specialist. The return flight was partially flown but paused because the reader rejected 527/1,198 frames (44%) in `direction-ring-20260910-230011`; the moving segment rejected 56%. The sun reflection on the cockpit roof beam is a confirmed scene feature. Prior pending pilot-readiness questions below are historical and must not be repeated. No ring process is running and no installed Wingman update occurred.

**Current experiment:** Read `OCR_LEARNED_MODEL_TRIAL.md`. Corrected scoring gives pretrained Small 17/17 exact coordinate frames, nine exact labelled camera rows, and 11/17 complete proposals. Tiny ONNX is faster but scores 12/17 coordinates exactly. A trained tiny specialist with corrected spatial pooling scores 13/17 coordinates and 12/17 complete proposals, plus 4/4 complete separately transcribed scene samples. It is not navigation-ready. The failed first trial and a normalization-reset diagnostic are rejected; the latter produced a correlated five-metre error in both Root and Solar. The successful training checkpoint is `D:\Navpoint-background-20260909\specialist-tiny-matched-pool\model.pdparams`, not the earlier `specialist-tiny-v1` file. ONNX export is being investigated separately. The evaluation-only adapter has 30 tests; the full skill suite passes 1,074 tests. Normal navigation gates remain disabled.

**Latest live state:** Read DIRECTION_LIVE_RING.md. Pilot confirmed forward flight and stopped. Latest forward sample: 82/100 accepted, 23 movement windows, median direction error 0.52 degrees, longest verification gap 0.750 seconds. Fixed missing saved-stack connection from database to ring; 1,044 tests pass. Actual ring now visible with a return bubble roughly 180 degrees behind at 25.6 km. Pilot alignment is pending. Ordinary guidance is still off and installed Wingman remains unchanged. This supersedes earlier pending flight/stop requests.


**Latest flight evidence:** User is in space. Baseline and two forward-flight recordings are saved; read `DIRECTION_FIRST_FLIGHT.md`. Seven qualifying motion windows favor the corrected camera formula over the legacy one, but residual drift exists, right/up/roll are unverified, and the pilot's "done/stopped" reply is pending. Recording is finished and the pilot was told to stop. The latest sample had a 2.256 s verified-position gap. Ordinary direction is still off; no installed waypoint or return flight has been completed. This supersedes the earlier pending request to get into space.

**Current task: add direction before the return flight.** Calibration-only support for new Root waypoints is implemented and tested (1,043 full-suite tests; 27 new isolated tests). Read `DIRECTION_CALIBRATION_STATUS.md`. Normal direction remains off; the user must provide the pending open-space/centered-view readiness signal so measured forward flight and return-arrow checks can establish the mapping. No live calibration or return test has happened. Installed AppData is older, lacks coordinate_stack.py, and has not been updated; Wingman was not running at last inspection. Do not claim operational direction complete or test the stale installed copy as though it contained this work.

**Latest user-directed policy:** Maximum one retry per image is implemented: initial read, then brightness OR header recovery, then discard on failure and capture fresh next cycle. Read `OCR_SINGLE_RETRY_POLICY.md`. Full suite 1,016 passed; actual-dispatch audit of 120 saved images confirmed at most two reads and one recovery per image. It discarded 13 readings previously rescued by a third attempt. Those losses honor the new cap. Fresh verified-position rate remains the requirement; older throughput/acceptance measurements predate this change. The diagnostic helper now follows the same cap. No deployment occurred.

**Requirement clarified:** The user requires **one freshly verified position per second during recovery**, optimally four normally. Attempts and cached results do not count; identical coordinates freshly verified from a new frame do. Read `OCR_VERIFIED_RATE_REQUIREMENT.md` in the skill directory for the live gap audit. Clear-view samples pass, but the overall recovery requirement remains unmet on difficult backgrounds. All older pending attempts-versus-verified-position questions below are superseded. Continue accuracy/availability work and measure verification gaps, not just processing latency.

**Latest verified continuation:** Read `OCR_RECOVERY_ALLOCATION_VALIDATION.md` in the skill directory. The header fitter now reuses temporary arrays; full suite 1,013 passed, replay 1,268 frames with zero changed decisions or payloads. The user moved the desktop obstruction and the requested clear capture is complete: previous reader 60/60 at 3.96 reads/sec; final reader 60/60 at 4.01 accepted reads/sec. Minimum recovery rate remains unproven, and attempts-versus-fresh-positions clarification remains unanswered. No deployment occurred. Older pending requests for an unobstructed view below are superseded.

**Current continuation — header-space recovery and resize comparison:** Read `OCR_HEADER_SEPARATOR_VALIDATION.md` and `OCR_RESIZE_COMPARISON.md` in the skill directory. A narrowly guarded recovery of literal spaces between readable header words is implemented, plus truncated-band protection. Full suite: 1,013 passed. Saved replay: 986/1,208 accepted versus 983 before; historical corpus 886/1,028 versus 883. No lost accepted frames or changes to previously accepted payloads. Native-resolution input and numeric evidence are preserved; neural models remain diagnostic only. The broader letter-recovery prototype was rejected after a synthetic false-Root counterexample.

**Timing and next live step:** The full replay had recovery median 452 ms / p95 908 ms / maximum 1.801 s. The previous and current readers had similar timing in a paired sample; restricting math-library threads did not clearly help. The latest live capture (`live-runtime-20260910-212442`) had a desktop window covering coordinate text: 0/60 accepted and maximum 2.688 s. It is not a clean game-view accuracy test. User has been asked to bring the game forward with an unobstructed overlay for a fresh timing capture. There is also a pending clarification whether minimum 1 FPS means attempts or newly verified positions. Neither has been answered as of this update. No installed-copy deployment occurred. All older statements below saying source is unchanged or requesting completed stationary/console checks are historical and superseded.

**Newest evidence:** Stationary-ship tests are complete; read `OCR_STATIONARY_BACKGROUND.md`. Looking around: 40/60 accepted. Fixed view with a bright marker behind the overlay: 0/60. Clear dark fixed view: 60/60 at about 4 FPS, one stable coordinate triple, all processing under 201 ms. Between-line background scoring helped individual candidates but its full-row prototype regressed and did not solve the marker case. PP-OCRv6 also made sign/digit errors. Production remains unchanged. The next requirement decision is whether recovery may retain a previously confirmed system label while reading fresh digits, or must keep the current independent full-row evidence requirement. Older stationary-readiness instructions below are superseded.

**Latest OCR continuation:** Fresh baseline, CIG TSR comparison and a test of the existing two-attempt capture path are complete. Read `OCR_TSR_COMPARISON.md` in this directory, or `D:\Navpoint-background-20260909\OCR_CONTINUATION_2026-09-10.md`. The user could not disable upscaling and selected CIG TSR. This did not eliminate captured digit mixtures. Source remains unchanged and undeployed. The next useful input is readiness for a controlled stationary-position capture while changing the view/background; verify stability from the images.

**Continuation update:** The pending console checks below have now been performed. `system.trace.filter.user.filename` gave no visible response; `system.trace.` plus Tab completed nothing. A control query returned `r_displayinfo = 0 []`, while `sys_analytics_debug` was also silent. Neither proposed logging route exposed a usable player-console control. No filter or analytics setting was applied. Stop this round of console probing and resume OCR with `r_displayinfo 2` and a fresh baseline. Details are in `D:\Navpoint-background-20260909\telemetry-investigation\CONSOLE_CHECK_2026-09-10.md`. The remaining text records the earlier shutdown handoff; its pending-query instructions are superseded by this update.

User requested that all progress be logged, followed by computer shutdown, with continuation later today. Work is paused for that request; the OCR objective is not complete.

## Resume here

The latest investigation is alternatives to OCR. Ask for the result of this **read-only game-console query**, which has not yet been answered:

```text
system.trace.filter.user.filename
```

The candidate trace filter is prepared but **not applied**. Read `telemetry-investigation/FINDINGS.md` before testing. Record the existing filter value and a fresh Game.log offset; verify the probe actually loads and emits a positive-control marker; then test movement and restore the original filter. Console availability, file-path acceptance, event schema, coordinate reference frame and update frequency remain unverified. Do not treat the old log byte offset as valid after a new game session.

User was also asked whether `/showlocation` had worked in recent builds. No answer has arrived. Its handler exists in the current executable; that is not proof that the command is available.

## Requirements and boundaries

- Improve OCR as far as practical, including other models if useful; continue until actual user input is necessary.
- Target **4 fresh reads/second normally, minimum 1/second in recovery**. Attempt rate and accepted-position rate are different measures.
- User suggested estimating scene background from the gaps between text rows. Preserve that direction and measured results rather than restarting the investigation.
- Preserve the intentionally dirty project at `D:\PycharmProjects\wingman-ai\skills\sc_navpoint`. Originally untracked reader files mean git HEAD is not a valid pre-work baseline.
- Frozen original files are in this scratch folder's `baseline/`; `before-performance/` holds the previously validated slower reader.
- No deployment to the installed Wingman/AppData or release-version copies has occurred.
- LIVE remains read-only for our tools. No process-memory reads, injection, backend authentication, network interception, anti-cheat bypasses, or persistent game configuration edits.
- No additional work, scheduled monitoring or automatic continuation was requested during shutdown.

## Implemented and validated OCR changes

1. Corrected the native glyph shadow/background model to `(1-G)*(1-shift_down_right(G))`.
2. Tightened coordinate/header spacing checks so erased digits, decimal points and signs cannot become harmless whitespace.
3. Added a pixel-based small-mark ambiguity veto. Re-run it after header repairs so those repairs cannot bypass refusal.
4. Added bounded coordinate brightness recovery and quadratic background fitting for uncertain Root/Solar header characters. Existing parser, scanner, tripwires and disabled local tracking remain authoritative. No general numerical reconstruction was promoted.
5. Batched glyph fitting and cell statistics, preserving customization hooks and scalar checks at decision boundaries. Fixed a reviewer-discovered unsigned-integer overflow possibility by casting after hook dispatch.
6. Reused already decoded rows when alignment refitting returns the same origin for the same immutable frame. Changed origins still re-decode.
7. Set the default poll period to 0.25 seconds; finite configured values clamp to 0.25–10 seconds. Explicit existing slower settings remain respected. Polling accounts for processing time and avoids queued catch-up work.

Last full verification: **1004 tests passed in 38.02 seconds**. Independent review approved the final changes and passed 27 focused tests. No runtime changes followed those checks. Closeout verifies source hashes against `live-summary.json`; it does not claim a new test run.

Full replay: **1028 frames, 883 accepted**, versus 637 before the full OCR work. The final performance revision changed **zero acceptance decisions or successful payloads** relative to the already validated recovery implementation. This is acceptance coverage, not whole-corpus accuracy. Only selected frames have manual truth labels.

Timing on saved frames: ordinary reads median 115 ms / p95 184 ms; recovery median 299 ms / p95 654 ms / max 904 ms. On a 60-frame live capture-and-runtime test: 50 accepted, median 135 ms / p95 461 ms / max 628 ms, average **3.67 attempts/second**; 54/60 cycles finished within 250 ms. Real capture, reader, scanner and diagnostic writes ran with framework/UI parts stubbed. This is not a benchmark of the entire installed Wingman application.

PP-OCR medium agreed with all 100 Root/Solar coordinate rows from the 50 accepted live frames. Agreement between models is a cross-check, not ground truth. The isolated scratch environment contains RapidOCR, ONNX Runtime, PP-OCR small/medium models and DXcam; none became a new production dependency. Tesseract and neural alternatives did not justify replacing the native reader.

## Remaining OCR failures and rendering diagnosis

- A native 240-frame burst over 4.07 seconds yielded 206 accepted frames. Across 12 refused frames, 34 numeric cells closely matched mixtures of the actual neighboring captured frames.
- Strong example: frame 191, Root row 3, cell 20, fitted approximately 56.8% previous digit 5 and 43.2% next digit 6; mixture RMS 0.974 versus 22.1/29.0 for either endpoint alone. See `burst-20260909-230104/neighbor-comparison.png` and `analysis.json`.
- This supports temporal mixtures in captured pixels. **The cause is unproven.** The user reports no visible overlapping digits and NVIDIA frame generation disabled. Do not reassert that frame generation caused this.
- User graphics screenshot: Vulkan, 5120×1440 fullscreen, DLSS Balanced 57%, Transformer, HDR off. VRAM estimate 9.4 GB versus user-reported previous 11.0 GB. The estimate change does not prove its cause.
- A DLSS/upscaling-off comparison was proposed, keeping renderer/resolution unchanged. **The user has not reported making that change.** It is pending and secondary to the current non-OCR lead.
- A numerical gap-recovery prototype was withheld after a concrete false acceptance on blended digits, despite neural agreement on selected gains. Reviewer example: 90% digit 4 + 10% digit 0 passed prototype bounds and produced a coordinate differing by 40 m from the newer endpoint. Do not integrate `live_unique_probe.py` or the offline equivalent.
- A DXGI comparison captured a materially different brightness/transfer representation from MSS. The native bank rejected all 240 DXGI frames; this is not a fair accuracy comparison or evidence that DXGI lacks transitions. Pixel-only transitions appeared in both paths.
- DXcam crashed during isolated cleanup because of an apparent double release; the scratch comparison script used a process-local workaround. Production capture and installed library files were unchanged. Legacy DXGI capture mode was considered but not tested.

## Non-OCR investigation, current patch

Installed build inspected: `sc-alpha-4.10.0-hotfix`, shipping, change **12572603**, version **1.0.191.55227**. Build-specific source hashes and counts are in `telemetry-investigation/summary.json`.

- No direct whole-overlay file export was found by the bounded current-file/string/code/log investigation.
- Fresh StarBreaker extraction recovered 308 protobuf descriptors. `GameTelemetryService` API/types hashes exactly match the August build and still lack world position/zone fields. Speed, altitude and heading cannot substitute for world coordinates.
- The inspected Game.log checkpoint had nine mission-marker positions, zero rendered coordinate rows, zero Player Position Update events, and zero showlocation output. Objective positions are not the player's position.
- Current `/showlocation` handler obtains a position triple and constructs coordinate text, a log call and a location response. Live availability and usable cadence remain unknown.
- Two on-disk code paths supply player position/rotation to **Player Position Update** through the modern cigTrace filter at severity value 7. This is consistent with Debug in the listed severity order; runtime confirmation is still required.
- Current default trace configuration is CODE version 2. Its local Log rules omit Debug. The binary exposes user-filter filename, reload and event-marker controls, and Include Events filter keys. This is a more specific lead than assuming `sys_analytics_debug` enables the event.
- `trace-position-probe.json` preserves all embedded default rules and adds a local Debug rule only for Player Position Update and NavpointTraceProbe. JSON/preservation checks pass. It has not been loaded by the game. Runtime execution, frame semantics, timestamp cadence and 1–4 Hz suitability are unknown.

## Evidence map and resumption cautions

- `FINAL_RESULTS.md`, `live-summary.json`, `performance-replay.json`: final OCR validation and hashes.
- Project `OCR_BACKGROUND_VALIDATION.md`, `OCR_LIVE_VALIDATION.md`, `OCR_CAPTURE_DIAGNOSIS.md`: detailed stages and limits.
- `OCR_changes.patch`: existing review patch against the frozen baseline; the closeout archive additionally preserves current runtime files, tests and documents.
- `live-runtime-20260909-212556/`: 60-frame actual capture/runtime benchmark and neural cross-check.
- `live-20260909-205443/`: difficult live frames and experimental recovery results.
- `burst-20260909-230104/`: neighboring-pixel analysis and illustration.
- `backends-20260909-230734/`: MSS/DXGI frames and pixel analysis.
- `telemetry-investigation/FINDINGS.md`, `disk-code-references.json`, `protos/`: current alternative-source findings and limits. Disassembly was offline and bounded, not a complete call-graph audit.
- `closeout-20260910/`: verified source snapshot, working-tree status/diff, log snapshot and closeout manifest. Preserve the logged distinction between a shutdown request and confirmed shutdown completion.
- Do not rerun old `final_report.py`: it targets an older stage and can overwrite historical reports. `finish_live_report.py` is the newer report builder.
- Do not import top-level replay scripts as helpers. `live_probe.py` is main-guarded and reusable. `experiment.py` imports the frozen baseline, not the production reader.

Resume by reading this handoff and the trace findings, obtaining the pending console response, and testing only a supported reversible path. Preserve the OCR gains regardless of whether the trace experiment succeeds.

## Live Bloom follow-up — planetary reader currently blocked

The user reached Bloom during the Nyx-to-Pyro naming survey. First-three-line captures show `Zone: pyro3 Pos:`. A separate full-panel test at `D:/Navpoint-background-20260909/bloom-frame-20260914-142025` returned `planet_identity_unresolved` and no position. Lower OCR bands deteriorate despite readable upper coordinates; fixed lower-panel line alignment is suspected and must be measured. The synthetic checks did not expose this live geometry problem. One OCR pass and one visual inspection were used; only one re-verification is permitted. No live accuracy or save/return success is established.

The ten-second first-three-line recorder remains active, with status at `D:/Navpoint-background-20260909/location-names-active.json`, a stop-file control documented in its script, and a one-hour cap from its start. It pauses outside game foreground. Planned user route: Bloom, Pyro IV, Pyro V. Installed Wingman remains unchanged.

## Live policy change and saved Bloom return test

User explicitly replaced lower-label validation with upper Zone naming conventions. FrameAwareReader now captures 175 pixels, reads the upper hierarchy once, and uses resolve_zone_identity. It never reads the lower Planet status or caches identity. Known Pyro numbered names and Stanton OOC body forms identify planets; known ship/jump/space-container names do not. Unknown names refuse. The old resolve_identity function remains only for offline legacy comparison, not runtime capture. Zone-policy suite: 1157 passed.

Saved `Bloom mining node` from the fresh, visually checked sample `D:/Navpoint-background-20260909/bloom-frame-20260914-142524/panel.png`. Planet-local pyro3 XYZ only, no Solar fields. Readback verified. Persistent test target: `D:/Navpoint-background-20260909/bloom-return-test-20260914/target.json`; SQLite database alongside it. Installed Wingman unchanged; the pilot-supervised return runs using source modules and the actual ring renderer.

First return ring session: `bloom-return-ring-20260914-142924`. User independently confirmed distance was spot on, but reported turning right moved the dot farther right (also mirrored when turning left). Found local camera right axis had reversed handedness relative to its forward/up axes. Corrected camdir_orientation's right vector only; forward/up, distance, coordinates and system camera convention unchanged. Four independent handedness tests reproduced then passed. Full suite: 1161 passed in 39.41s.

Old ring stopped via STOP file before reload. Corrected live ring session: `bloom-return-ring-20260914-143423`, active state `D:/Navpoint-background-20260909/bloom-return-active.json`. Corrected process has produced fresh planetary reads; pilot confirmation of corrected horizontal response remains pending. Do not claim return success or 10 m independently verified OCR accuracy yet. This runner has a ten-minute cap and a STOP-file control. The separate ten-second naming recorder remains active under its original one-hour cap.

The staged candidate folder still predates these live policy/direction fixes; refresh it only after current live validation, preserving test evidence. Source is ahead of the staged package.
