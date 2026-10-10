# SC NavPoint coordinate-stack rework

Implementation plan for Claude Code, 2026-08-09.

## Outcome

Replace zone-name-dependent routing for newly marked NavPoints with a coordinate-stack model:

- Capture every valid `Zone: ... Pos: ...` row in the opening overlay block, through the exact `Zone: Root Pos:` row.
- Treat zone names as opaque diagnostic text. A missing, changed, or partly unreadable local name must never select or reject a routing frame.
- Persist Root, SolarSystem, and all pre-Solar coordinate rows from the same accepted capture.
- Use saved Root coordinates for deep-space navigation and coarse approach.
- Permit a validated local/body-fixed coordinate only while the Root distance and the local distance are both strictly below `3_000_000 m` (3 Mm / 3,000 km).
- Fall back to Root immediately when the local candidate becomes unavailable, untrusted, or reaches the hard limit.

This document supersedes only the zone-name/OOC-dependent surface-routing design in Waves 4-5 of `CLAUDE_PLAN_2026-08-03_23-35-09.md`. Its preservation, security, packaging, release, and evidence gates remain mandatory.

## Authority and safety boundaries

Before editing code, read these files in full:

1. repository `AGENTS.md`
2. `skills/AGENTS.md`
3. `skills/README.md`
4. `skills/sc_navpoint/ledger/LEDGER.md`
5. `skills/sc_navpoint/ledger/REFUTED.md`
6. `skills/sc_navpoint/ledger/CORPUS.md`
7. `skills/sc_navpoint/SUPERVISION.md`
8. `skills/sc_navpoint/CLAUDE_PLAN_2026-08-03_23-35-09.md`

The implementation must obey these constraints:

- Do not use zone-name equality, an `OOC_` prefix, a fixed absolute row number, coordinate magnitude, or Z pass-through to choose a local frame. Those approaches are refuted or unproven.
- Do not loosen OCR refusal thresholds, unit requirements, echo checks, freshness checks, or the SolarSystem/Root agreement tripwire.
- Do not re-enable the disabled `server_id` wipe.
- Do not remove the retained Vision-era helpers or tests. Runtime remains OCR-only.
- Do not use bare `print()`. Follow the repository's `Printr` rules.
- Do not add tools or expose the stored coordinate stack to the language model. This change must remain token-neutral.
- Do not change `api/interface.py`, FastAPI endpoints, or client types. This feature does not require a Core API change.
- Do not clean or normalize the dirty tree. Essential NavPoint evidence and code are untracked. Never use `git clean`, `git checkout`, or a broad reset.
- Do not edit the installed AppData copy, restart Wingman, install a release, create commits, push, or open PRs without separate user approval.
- Do not run `skills/sc_navpoint/install.bat` from the development tree.

## Product decisions already made

These are requirements, not open questions:

- Planet and moon centers are presently stationary in SolarSystem/Root coordinates.
- Surface points move in Root coordinates as their parent object rotates.
- The approximate largest OM1-to-OM2 separation is 1.5 Mm. The user selected twice that distance as the absolute local-tracking ceiling: `LOCAL_TRACKING_MAX_M = 3_000_000.0`.
- Root is the canonical long-range position for every newly stored waypoint.
- The old 10,000 km handoff is removed for coordinate-stack waypoints.
- At `d_root >= 3_000_000 m`, navigation is Root-only. Equality belongs to Root mode.
- Local guidance may be used only when `d_root < 3_000_000 m` and the chosen local delta is also `< 3_000_000 m`.
- Zone text may be retained verbatim for diagnostics, but it has no routing authority.

The motivating overlay has this logical order:

```text
CamDir: ...
Zone: rs_int_layout_keeger_01 Pos: -386.02m 209.38m -437.00m
Zone: keeger_segment_social_001 Pos: 21.5842km -23.2325km 22.6220km
Zone: SolarSystem_753098466557 Pos: -45804302.9778km -14351319.5080km 29.3847km
Zone: Root Pos: -45804302.9778km -14351319.5080km 29.3847km
```

Do not copy the temporary screenshot into the repository. Use the transcription above as a synthetic parser fixture. Add lossless real captures later only with explicit user permission.

## Terminology and normalized representation

Use these terms consistently:

- **Root position**: the exact `Zone: Root Pos:` triple, normalized to metres. It is the long-range address.
- **Solar row**: the `Zone: SolarSystem_<opaque-id> Pos:` triple. The ID and row are diagnostics/cross-check data for new stack waypoints, not a session addressability gate.
- **Nested rows**: all valid `Zone: ... Pos:` rows before SolarSystem, in on-screen order from innermost to outermost.
- **Local candidate**: the outermost nested row, meaning the row immediately before SolarSystem after semantic parsing. It is only a candidate until the validation gate below passes.
- **Deeper rows**: nested rows closer to the camera/player than the local candidate. Store them, but do not route with them in the first implementation.

Create a pure runtime module, preferably `skills/sc_navpoint/coordinate_stack.py`, containing typed immutable value objects and routing decisions. Keep OCR mechanics in `overlay_fields.py`/`scanner.py`, persistence in `database.py`, and orchestration in `main.py`.

The serialized record should be versioned and shaped approximately as follows; exact Python types may follow existing conventions:

```json
{
  "schema": 1,
  "root": {"x_m": 0.0, "y_m": 0.0, "z_m": 0.0, "raw": "Zone: Root Pos: ..."},
  "solar": {
    "x_m": 0.0,
    "y_m": 0.0,
    "z_m": 0.0,
    "raw_name": "SolarSystem_753098466557",
    "raw": "Zone: SolarSystem_... Pos: ..."
  },
  "nested": [
    {"depth": 0, "x_m": 0.0, "y_m": 0.0, "z_m": 0.0, "raw_name": "...", "raw": "..."}
  ]
}
```

Store `nested` in observed screen order and document that the final element is the outermost pre-Solar candidate. Do not put CamDir into the persistent coordinate stack; it describes capture-time view orientation, not the target address. Continue using the current CamDir path for live bearing calculations where calibrated.

Raw names and lines are diagnostic data only. Code review should be able to delete or scramble every `raw_name` value without changing a routing decision.

## Extraction contract

Refactor extraction without changing OCR glyph classification or crop geometry:

1. Scan the existing opening position-row window (`POSITION_ROWS`, currently eight). Do not assume that Root is physical line five or that the local candidate is physical line two or three.
2. Locate an exact semantic Root label. `Root_Cellar`, an OCR-fragmented Root label, or a row merely containing the word `Root` is not the Root anchor.
3. Locate the SolarSystem row directly before Root in the logical zone stack. Preserve its opaque suffix but do not require a known system name.
4. Parse every preceding `Zone: <opaque text> Pos: <x><unit> <y><unit> <z><unit>` row in the same stack block.
5. Parse the `Pos:` tail independently from the local zone-name cells. A `?` or other refusal in `raw_name` may be retained, but it must not contaminate otherwise trusted coordinate cells.
6. Require all three coordinate tokens and explicit supported unit suffixes for every accepted row. A refused digit, sign, decimal, or unit in the `Pos:` tail makes that row unusable.
7. Require a fully trusted Root coordinate triple and a fully trusted Solar coordinate triple.
8. Preserve the existing SolarSystem/Root numeric agreement check and tolerance. Treat it as a corruption tripwire, not independent proof that both OCR readings are correct.
9. Reject the entire new stack payload if Root or Solar fails. It is acceptable to retain a diagnostic about an unusable nested row; it is not acceptable to promote a deeper row around a failed outer candidate silently.
10. Return the normalized stack in addition to current diagnostics. Keep the legacy payload branch available for retained Vision-era tests and legacy waypoint reads.

Prefer semantic anchors and relative ordering. The user's “first five lines” describes the common overlay layout, not a license to hard-code screen row indexes.

## Persistence and migration

Implement an additive database schema v4 migration in `database.py`. Never wipe the database for this change.

Add fields equivalent to:

- `coordinate_schema INTEGER NOT NULL DEFAULT 0`
- `root_x REAL NULL`
- `root_y REAL NULL`
- `root_z REAL NULL`
- `coordinate_stack TEXT NULL`

`NULL` is meaningful for legacy records whose Root position was never captured. Extend `NavPoint` with corresponding defaulted fields at the end so existing constructors and tests remain compatible.

For a new stack waypoint:

- set `coordinate_schema = 1`;
- persist the three Root columns for direct access;
- serialize the normalized full stack as compact, deterministic JSON;
- use a new explicit frame discriminator such as `frame="stack"` rather than overloading the meaning of legacy `local` or `system` rows;
- keep existing `x/y/z`, `body`, `system`, and `frame_id` columns readable for backward compatibility, but do not consult display-name fields when routing a stack waypoint;
- if `x/y/z` must remain populated for existing listing/UI code, mirror Root there and document that compatibility behavior.

Migration rules:

- v3 rows survive byte-for-byte in their existing semantic fields and receive `coordinate_schema = 0` plus null Root/stack fields.
- Do not synthesize Root data for legacy local rows.
- Legacy system rows may continue through the existing system/frame-ID behavior; do not silently reinterpret them as schema-1 Root waypoints.
- Existing CRUD, list, rename, delete, and import behavior must round-trip both schemas.
- Malformed or unknown future stack JSON must fail closed for navigation while leaving the database row intact and listable.

No YAML config field is needed. The 3 Mm ceiling is a deliberate product invariant, not a user-tunable default.

## Routing state machine

Put the selection logic in a pure function so it can be exhaustively tested without the game, OCR, Wingman, or the HUD.

Inputs:

- saved target coordinate stack;
- current accepted coordinate stack;
- current navigation state, only if required to clear presentation state;
- constants such as `LOCAL_TRACKING_MAX_M`.

Outputs should include:

- mode: `ROOT_APPROACH`, `LOCAL_TRACKING`, or `REFUSED`;
- selected current/target triples;
- distance in metres;
- a stable reason code suitable for logs/tests;
- whether directional UI is allowed;
- whether a previous local target/bubble must be cleared.

Decision order:

```text
if target stack invalid or target Root absent:
    REFUSED
elif current stack invalid or current Root absent:
    REFUSED
else:
    d_root = euclidean(current.root, target.root)
    if d_root >= 3_000_000 m:
        ROOT_APPROACH
    elif target/current local candidate is missing or untrusted:
        ROOT_APPROACH
    else:
        d_local = euclidean(current.local_candidate, target.local_candidate)
        if d_local >= 3_000_000 m:
            ROOT_APPROACH
        else:
            LOCAL_TRACKING
```

Additional invariants:

- Root is always computed before considering local data.
- No local coordinate may influence distance, bearing, arrival, HUD, ring, or announcements at or above either hard ceiling.
- There is no hysteresis band above 3 Mm. If future capture evidence justifies a lower acquisition threshold, the hard maximum still remains 3 Mm.
- When switching or falling back to Root, clear any stale local vector and local HUD/ring bubble in the same state update.
- In `ROOT_APPROACH`, report the distance as coarse approach distance. A rotating surface target's saved Root position is intentionally stale within a bounded body-sized envelope.
- Do not announce arrival from Root distance for a stack waypoint. Arrival requires valid `LOCAL_TRACKING` and the existing arrival/debounce policy.
- Keep `SPACE_DIRECTION_CALIBRATED = False` behavior: Root distance can be reported, but an uncalibrated Root direction must not be invented.
- New schema-1 stacks are Root-addressable across sessions even if the opaque SolarSystem ID changed. Remove the old frame-ID mismatch rejection only for schema-1 stacks. Preserve it for legacy rows.
- Never align rows by their zone names. Do not route on deeper nested rows in this first release.

### Local-candidate evidence gate

“Outermost row immediately before SolarSystem” is the implementation hypothesis, not yet a proven universal identity signal. Before enabling `LOCAL_TRACKING` outside tests, prove it against paired captures that include at least:

- on foot on a moon/planet;
- seated in a landed ship, then outside that ship at the same site;
- two different ships or interior containers near one another;
- asteroid base/interior stacks like the supplied example;
- an orbital marker pair near the claimed 1.5 Mm maximum;
- deep space with no body row;
- a jump-point/small-world-container case that defeats scale-only classification;
- Stanton and Pyro examples, including a case with no `OOC_` row.

For each pair, record the full ordered stack and determine whether the outermost pre-Solar row is stable in the desired body/area frame. Repeated captures from one stationary pose are not independent evidence.

If the candidate selects a movable ship/interior frame across different vehicles, or if corresponding surface captures cannot be aligned without reading names, stop the rollout. Keep capture/persistence work, leave `LOCAL_TRACKING` feature-gated off, append evidence to the ledger, and ask the user for a revised invariant. Do not substitute a row-number, prefix, name, or scale heuristic.

## Integration changes by file

### `coordinate_stack.py` (new)

- Define typed stack/row value objects and strict JSON serialization/deserialization.
- Define `LOCAL_TRACKING_MAX_M = 3_000_000.0`.
- Implement Euclidean distance and the pure routing selector.
- Use stable enum/reason strings; do not log from pure functions.

### `overlay_fields.py`

- Add coordinate-tail extraction that isolates label confidence from `Pos:` confidence.
- Build the semantically anchored ordered stack through Root.
- Retain current field diagnostics and refusal margins.
- Do not delete OOC or body-scale code yet; legacy tests and evidence still depend on it. Ensure new stack routing does not call it.

### `scanner.py`

- Add a deterministic schema-1 coordinate-stack payload branch before legacy local/system interpretation.
- Keep Root/Solar agreement, required units, retry diagnostics, and echo rejection.
- Return structured stack data without making routing decisions.
- Retain dormant Vision-shaped parsing paths.

### `database.py`

- Add the non-destructive v3-to-v4 migration and extended `NavPoint` fields.
- Add deterministic compact-JSON round trips and fail-closed decode behavior.
- Preserve legacy behavior and data.

### `main.py`

- Make marking persist an accepted schema-1 stack rather than one name-selected coordinate triple.
- Route schema-1 waypoints through the pure state machine during initial navigation and polling.
- Bypass system/frame-ID mismatch only for schema-1 Root-addressable records.
- Use local distance for arrival only in `LOCAL_TRACKING`.
- Keep spoken/tool responses compact and omit raw coordinates, labels, JSON, and internal thresholds unless specifically requested.
- Send state transitions and refusal diagnostics through `Printr` with the correct sync/async convention.

### `navigation.py`, `ring_overlay.py`, and `navpoint_ui/`

- Reuse existing vector/bearing math where its frame assumptions remain valid.
- Surface the active mode as concise UI text such as `ROOT APPROACH` or `LOCAL`.
- Suppress/clear local bearing graphics immediately on Root fallback.
- Do not show a directional marker in Root mode while space direction remains uncalibrated.
- Ensure offline/rejected states cannot leave a stale target visible.

### `update_release.py` and release manifests/tests

- Add the new runtime module to the explicit release allowlist.
- Do not copy tests, plans, captures, ledgers, caches, or development artifacts into `release_version`.
- Generate the release tree only after implementation and evidence gates pass.

## Implementation waves

Keep each wave independently reviewable and testable.

### Wave 0: preserve and baseline

1. Follow the preservation procedure in the prior Claude plan before touching runtime files.
2. Record `git status --short` without modifying unrelated files.
3. Run the current NavPoint suite and confirm the known baseline of 678 passing tests. If the baseline has legitimately changed, record the exact new count and cause before proceeding.
4. Snapshot/checksum the development, release, and installed copies as required by `SUPERVISION.md`.

### Wave 1: pure model and extraction

1. Add `coordinate_stack.py` value objects and serialization.
2. Refactor coordinate-tail trust in `overlay_fields.py`.
3. Add the scanner's schema-1 stack result without switching navigation behavior.
4. Add parser tests using the supplied transcription and existing lossless corpus.
5. Mutation-prove the exact Root anchor, unit enforcement, coordinate-cell refusal, and name independence.

### Wave 2: additive persistence

1. Implement schema v4 migration.
2. Extend CRUD and `NavPoint` round trips.
3. Prove v3 databases retain all rows and legacy semantics.
4. Prove corrupt/unknown JSON fails closed without deleting the waypoint.

### Wave 3: pure routing

1. Implement the state machine with no Wingman/HUD dependencies.
2. Test every boundary and fallback.
3. Run the local-candidate corpus analysis. Keep runtime activation gated until it passes.
4. Mutation-prove that changing `<` to `<=`, using a deeper row, consulting a name, or omitting stale-state clearing fails tests.

### Wave 4: orchestration and presentation

1. Persist stacks from mark operations.
2. Integrate schema-aware route selection into navigation start and polling.
3. Integrate mode, arrival, announcements, HUD, and ring cleanup.
4. Preserve legacy waypoint behavior.
5. Test retry/refusal/offline transitions and compact tool output.

### Wave 5: replay and supervised live evidence

1. Replay the full retained lossless corpus; do not validate from OCR text logs alone.
2. Run the specific paired-capture matrix in the evidence gate.
3. Append new measured facts to `ledger/LEDGER.md`, refutations to `ledger/REFUTED.md`, and capture provenance to `ledger/CORPUS.md`.
4. Only after replay passes, request approval for supervised live capture/testing. Live testing must not install an unreleased dev tree.
5. Treat any wrong local-frame selection as a release blocker, even if unit tests pass.

### Wave 6: package and release

1. Select and apply the next skill version only after implementation approval; do not bump early.
2. Generate `release_version` through the guarded release process. Never hand-maintain a divergent runtime copy.
3. Run source and packaged suites plus parity, allowlist, metadata/token, security, and install-artifact checks from the prior plan.
4. Confirm no corpus images, plans, ledgers, backup glyph files, databases, logs, or caches entered the package.
5. Request explicit approval before installing, committing, pushing, or creating PRs.
6. If PR work is approved, ask whether a Core GitHub issue exists; create/link one if not. Create a client PR only if client code actually changed.

## Required tests

Add focused files such as:

- `tests/test_coordinate_stack_fields.py`
- `tests/test_coordinate_stack_database.py`
- `tests/test_coordinate_stack_router.py`
- `tests/test_coordinate_stack_navigation.py`

At minimum, prove all of the following:

### Extraction

- the supplied multi-level stack parses and preserves every row;
- a changed, unreadable, or `?`-containing nested zone name does not change accepted coordinates;
- an unreadable coordinate digit, sign, decimal, or unit refuses that row;
- mandatory unit suffixes remain mandatory;
- `Zone: Root Pos:` is accepted while `Zone: Root_Cellar Pos:` is not the anchor;
- Root missing, Solar missing, malformed order, or Root/Solar disagreement refuses schema 1;
- variable stack depth and shifted physical row positions work;
- no `OOC_` row is required;
- raw stack order and deterministic JSON round-trip exactly.

### Persistence

- v3-to-v4 migration is additive and retains every old row;
- old local and system waypoints retain their prior behavior;
- schema-1 stacks survive create/read/list/update/delete and process restart;
- null Root has explicit legacy meaning;
- malformed JSON is listable but non-navigable;
- marking never wipes waypoints because `server_id` or SolarSystem suffix changes.

### Router boundaries

- `d_root > 3 Mm` selects Root;
- `d_root == 3 Mm` selects Root;
- `d_root < 3 Mm` cannot select local without both candidates;
- `d_local > 3 Mm` and `d_local == 3 Mm` select Root;
- both distances strictly below 3 Mm select local only after the evidence gate is enabled;
- missing/refused current candidate falls back to Root;
- the final pre-Solar nested row is selected and an innermost seat/room row is never selected;
- labels can be independently randomized without changing the decision;
- SolarSystem ID changes do not block schema-1 Root navigation;
- legacy system frame-ID mismatch remains rejected;
- Root fallback clears stale local direction and cannot cause arrival;
- deep-space stacks with no nested row remain Root-only.

### Integration and presentation

- mark stores the full stack and returns no raw coordinates to the model;
- navigation and polling use the same pure selector;
- arrival is local-only for schema-1 waypoints;
- Root mode is visibly/coarsely labeled and does not claim precise surface arrival;
- uncalibrated Root direction yields no invented bearing or ring marker;
- rejection/offline/fallback clears the previous bubble immediately;
- all output uses `Printr`, never bare `print()`;
- the full existing suite remains green.

For each safety guard, deliberately mutate or temporarily invert the implementation and observe the intended test fail. Record the mutation and failing test in the implementation report; “the test passed once” is not sufficient evidence.

## Acceptance criteria

The rework is implementation-complete only when:

- new NavPoints persist Root, SolarSystem, and the complete accepted nested stack from one fresh capture;
- local zone-name OCR cannot cause a false rejection or select a frame;
- Root drives every schema-1 route outside the strict 3 Mm envelope;
- local tracking never operates at or above 3 Mm by either distance;
- local arrival is never inferred from coarse Root distance;
- the outermost pre-Solar candidate passes the paired live-corpus gate without movable-container false positives;
- schema v4 migration is non-destructive and legacy waypoints retain their behavior;
- stale local HUD/ring state cannot survive a Root fallback;
- no new model-visible tool payload or tool is added;
- source tests, packaged tests, security checks, and source/release parity pass;
- evidence and limitations are recorded in the ledgers;
- installation and release actions remain separately approved.

## Mandatory stop conditions

Stop and report rather than improvising if any of these occur:

- the local candidate cannot be distinguished safely without zone-name semantics;
- a different ship/interior can produce a plausible local delta and false tracking;
- the 3 Mm assumption is contradicted by measured object geometry;
- Root/Solar agreement no longer holds in a supported game context;
- migration would require deleting or reinterpreting legacy rows;
- OCR safety thresholds must be weakened to parse the new stack;
- Core API/client changes appear necessary;
- the current dirty-tree artifacts cannot be preserved confidently;
- any source/release/installed-tree divergence is unexplained;
- any release generation step is fail-open or includes development artifacts.

In a stop report, include the exact capture/test, normalized stack, selected mode and reason, and the smallest unresolved product decision. Do not work around a failed invariant with a zone-name, row-number, prefix, or scale heuristic.

