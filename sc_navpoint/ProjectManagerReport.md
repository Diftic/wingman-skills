# SC NavPoint — Project Manager Findings

**Reviewed:** 2026-08-02
**Scope:** independent analysis and bug-fix hypotheses only. Claude remains responsible for implementation.

## Executive assessment

Claude's findings work is validated in the development tree. All findings from all three review rounds are closed, and an independent full-suite run completed with **678 passing tests in 30.31 seconds**.

The local OCR reader itself is **not yet fixed or proven in flight**. The reviewed evidence still contains no successful field capture after **2026-07-31 22:07:10**. The new work makes failures measurable, correctly reported, and safe for navigation; live evidence is still required before changing OCR thresholds or geometry.

The development tree remains **local-OCR-only at runtime**. main.py creates NavPointScanner and calls only parse_payload; it does not call the scanner's retained image-capture or model-facing helpers. Retained Vision-era parser code is compatibility and validation scaffolding, not a live fallback.

Nothing has been propagated to release_version or the installed custom skill. The saved Laura configuration was separately cleaned so the shipped prompt and discovery metadata can take effect; its backup remains the recovery point.

## Resolved findings

### 1. update_position no-frame false success — resolved

update_position now uses the shared frame helper and rejects a truthy station-interior payload with capture kind no_frame. It no longer returns null x, y, and z values as a successful position.

Validation covers:

- refusal of a real truthy no-frame payload;
- agreement with mark_location;
- no missing-overlay hint for a readable overlay with no frame;
- use of the shared frame helper.

### 2. Stale OK ring after scanner rejection — resolved

The capture now publishes a final ring state only after scanner validation. Scanner rejection and unexplained parse failure no longer inherit the reader's pre-validation OK state.

The ring consumes _last_ring_state, and any non-empty failure state suppresses the old bearing bubble. A no-frame capture reports INDOORS; a no-reader capture reports NO SIGNAL under the accepted current wording.

Validation covers the mapping for every capture kind, scanner rejection, no-frame, no-reader, clean success, poll failure, and suppression of a previously valid deflection.

### 3. Per-caller capture diagnostics race — resolved

Each foreground tool opens a ContextVar-backed capture sink. asyncio.to_thread propagates that context to the worker, which publishes the CaptureOutcome while still under the capture lock. The caller therefore consumes its own outcome even if another capture overwrites the shared last-known fields before the await resumes.

The deterministic handoff-race tests demonstrate distinct outcomes, hints, metrics, and capture duration for the two callers. The sink is reset after each tool call. The scanner-unavailable fast path now publishes its no_reader outcome into the same per-caller channel.

### 4. No-reader stale ring state — resolved

Both local reader/scanner unavailability and the asynchronous scanner-unavailable path now replace the old ring state with NO SIGNAL rather than preserving a prior OK value.

## Third-round findings — closed

### Scanner-unavailable sink invariant

The asynchronous missing-scanner branch now constructs one no_reader outcome, assigns it to the shared last-known fields, and publishes the same object to the caller's ContextVar sink before returning.

Two dedicated tests cover direct sink publication and a forced shared-field overwrite. The test module documents why a to_thread interception would have been vacuous on a path that returns before reaching to_thread.

### Zero-byte hook artifacts

The 21 verified zero-byte, untracked regular files in the skill root were removed individually. Independent enumeration agreed on the complete name set, and a fresh filesystem check reports **zero remaining zero-byte files** in the NavPoint root.

The underlying PostToolUse hook defect remains external to NavPoint and can recreate the debris on future edits. Continue to avoid the development-tree installer and never use git clean in this folder.

### Timeline wording

SUPERVISION.md now uses the exact last-success timestamp rather than the incorrect “six days” elapsed-time claim.

## Deployment assessment

The development build is suitable for a **focused diagnostic flight** after the normal allowlisted release update. It is not evidence that OCR capture is operational.

Recommended sequence:

1. Fully close Wingman AI.
2. Run python skills\sc_navpoint\update_release.py from the repository root.
3. Confirm every allowlisted file copied with no warning.
4. Confirm release_version\default_config.yaml no longer contains the old “via Vision AI” claim.
5. Run only release_version\install.bat.
6. Start Wingman AI and verify clean skill initialization before flying.
7. Perform the diagnostic flight and preserve the generated evidence.

The zero-byte artifacts do not enter this release route because update_release.py rebuilds release_version from an explicit allowlist.

## Diagnostic flight decision points

Collect:

- navpoint_poll.log;
- navpoint_poll.log.1 if rotation occurred;
- the bounded refused-frame PNG set;
- the matching Wingman Core log.

Decide from those artifacts:

- whether refusals are dominated by excessive glyph cost, insufficient match margin, or both;
- whether alignment refitting is occurring on most failed reads and consuming the predicted extra time;
- whether later attempts recover after an initial refusal;
- whether successful and refused frames have separable ink, periodicity, trust, cost, or margin profiles;
- whether behavior changes between open space, shadow, and daylit terrain.

Do not change refusal thresholds, retry policy, or alignment behavior until the flight evidence identifies which condition actually dominates.

## Final disposition

- Original correctness findings: **resolved and independently validated**.
- Full suite: **678 passed**.
- VisionAI runtime fallback: **absent**.
- OCR reader field reliability: **still unresolved**.
- Propagation: **not yet performed**.
- Diagnostic flight: **go after the documented release sequence**.
- General readiness claim: **no-go until live OCR evidence shows successful captures**.
