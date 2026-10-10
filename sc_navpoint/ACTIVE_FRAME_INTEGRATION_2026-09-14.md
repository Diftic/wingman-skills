# Planetary frame candidate — 2026-09-14

Source candidate version: **4.9.0.23**. Staged at
`D:/Navpoint-background-20260909/candidate-active-frame-4.9.0.23`.
**Installed Wingman is unchanged. Live validation and frozen Wingman loading remain pending.**

## Implemented

- V8 reads the 675 x 500 top-right panel at native capture resolution. Primary coordinate bands are read once. For an unknown frame hierarchy, lower bands are read once until the Planet identity is resolved. There are no recovery passes or image queues.
- The lower `Planet:` token must match an active `Zone:` row. Historical full captures show a stale Planet label in space, so that label alone never selects a planetary coordinate. Unresolved identity refuses the image. No body is guessed from row index, magnitude, or a universal OOC rule.
- Identity is cached against the complete ordered Zone-name signature, up to 64 signatures. No coordinates are cached by the reader. A changed hierarchy needs its own identification. OCR identity errors remain possible; this is not an independent correctness guarantee.
- On a planet, only that planet's XYZ is used. Unreadable Solar/Root numbers do not prevent a planetary read. Unreadable planetary numbers never fall back to Solar. Solar/Root headings still participate in checking the hierarchy.
- Planetary saves contain the planet identity and full local XYZ. Solar/Root/stack fields remain NULL. Existing waypoint records are preserved; old address targets cannot use Solar routing while a planetary frame is active.
- The selected target determines precision: outside 15 km, fractional digits are omitted and bounds accompany a coarse midpoint. Possible entry into 15 km switches early. Near the target, full observed digits are required and a once-per-activation slowdown message is issued. Saves always request full precision.
- Coarse estimates cannot trigger arrival. Failed reads retain the previous display and its original capture age. Held values are not fresh fixes. Planetary ring and HUD use matching camera-relative direction; zero-distance targets have no direction. Spoken planetary guidance uses the same offsets.
- Both release manifests include the new modules and dependency folder. Bundled OpenCV is provenance checked. The installer preserves an existing default_config.yaml. The experimental reader remains disabled by default and no alternative reader is selected automatically on failure.

## Verification

- Baseline before this integration: 1,097 tests passed.
- Final complete skill suite: **1,144 passed in 19.99 seconds** (`pytest-active-final2`). Covers frame selection, save fields, no Solar fallback, precision boundaries, stale/held behavior, advisory debounce, direction, and legacy compatibility.
- Browser JavaScript syntax passed. All 31 staged Python source files compile under Python 3.11 syntax.
- Four newly generated synthetic full panels were each decoded exactly once. All four returned exact labelled local XYZ. Two uncached planet identifications took 0.302 and 0.283 seconds; two subsequent fresh-position reads with cached identity took 0.0769 and 0.0772 seconds. These are model/parser times, excluding game capture and Wingman overhead. The renderer shares training glyphs: this is a smoke test, not independent live accuracy evidence.
- The isolated staged reader loaded V8 and bundled OpenCV, produced finite model output, and verified all 83 runtime file hashes. This used development Python 3.13, NumPy 2.4.2, ONNX Runtime 1.29.0, CPUExecutionProvider. The installed application uses a different frozen runtime; passing here does not prove that runtime works.
- Model SHA-256: `0c775c270fda57437b34af99a1e0e8609a4e86dcbd3265201fde061b5aac0a39`.

Evidence: `D:/Navpoint-background-20260909/active-frame-synthetic-20260914/results.json`,
`D:/Navpoint-background-20260909/active-frame-staged-smoke-20260914.json`, and the staged `candidate-manifest.json`.
Pre-edit source snapshot: `D:/Navpoint-background-20260909/before-active-frames-20260914`.

## Remaining live checks

StarCitizen and Wingman were not running at the last process check. A request to prepare a planet/moon view with r_displayinfo 2 is pending. No capture monitor is running.

1. Capture a new full planetary panel, independently read its Planet label and matching Zone XYZ, and confirm the actual row geometry and CamDir convention. Do not rerun any exhausted prior audit image.
2. Verify candidate loading in installed/frozen Wingman with a backup of that installed skill and configuration. Enable the candidate for this test only after compatibility is established. Existing production files have not been overwritten.
3. Save a full-precision planetary location, move away, and test return guidance across 15 km. Verify planet entry/exit and different planets; no Solar position should be saved or used on a planet.
4. Independently score fresh positions against the 20-correct-reads-per-rolling-10-seconds requirement and at most 10 m total position error near the target. Recognizer confidence or repeated row agreement cannot establish truth accuracy.

The previous bright-background audit is unchanged: 96 exact correct, 29 wrong, 27 unresolved accepted frames, plus 88 refused. No unknown or incorrect acceptance was relabelled as correct by this integration. The new planetary path and 10 m goal remain unproven on live footage.

## Live Bloom follow-up — planetary reader currently blocked

The user reached Bloom during the Nyx-to-Pyro naming survey. First-three-line captures show `Zone: pyro3 Pos:`. A separate full-panel test at `D:/Navpoint-background-20260909/bloom-frame-20260914-142025` returned `planet_identity_unresolved` and no position. Lower OCR bands deteriorate despite readable upper coordinates; fixed lower-panel line alignment is suspected and must be measured. The synthetic checks did not expose this live geometry problem. One OCR pass and one visual inspection were used; only one re-verification is permitted. No live accuracy or save/return success is established.

The ten-second first-three-line recorder remains active, with status at `D:/Navpoint-background-20260909/location-names-active.json`, a stop-file control documented in its script, and a one-hour cap from its start. It pauses outside game foreground. Planned user route: Bloom, Pyro IV, Pyro V. Installed Wingman remains unchanged.

## Live policy change and saved Bloom return test

User explicitly replaced lower-label validation with upper Zone naming conventions. FrameAwareReader now captures 175 pixels, reads the upper hierarchy once, and uses resolve_zone_identity. It never reads the lower Planet status or caches identity. Known Pyro numbered names and Stanton OOC body forms identify planets; known ship/jump/space-container names do not. Unknown names refuse. The old resolve_identity function remains only for offline legacy comparison, not runtime capture. Zone-policy suite: 1157 passed.

Saved `Bloom mining node` from the fresh, visually checked sample `D:/Navpoint-background-20260909/bloom-frame-20260914-142524/panel.png`. Planet-local pyro3 XYZ only, no Solar fields. Readback verified. Persistent test target: `D:/Navpoint-background-20260909/bloom-return-test-20260914/target.json`; SQLite database alongside it. Installed Wingman unchanged; the pilot-supervised return runs using source modules and the actual ring renderer.

First return ring session: `bloom-return-ring-20260914-142924`. User independently confirmed distance was spot on, but reported turning right moved the dot farther right (also mirrored when turning left). Found local camera right axis had reversed handedness relative to its forward/up axes. Corrected camdir_orientation's right vector only; forward/up, distance, coordinates and system camera convention unchanged. Four independent handedness tests reproduced then passed. Full suite: 1161 passed in 39.41s.

Old ring stopped via STOP file before reload. Corrected live ring session: `bloom-return-ring-20260914-143423`, active state `D:/Navpoint-background-20260909/bloom-return-active.json`. Corrected process has produced fresh planetary reads; pilot confirmation of corrected horizontal response remains pending. Do not claim return success or 10 m independently verified OCR accuracy yet. This runner has a ten-minute cap and a STOP-file control. The separate ten-second naming recorder remains active under its original one-hour cap.

The staged candidate folder still predates these live policy/direction fixes; refresh it only after current live validation, preserving test evidence. Source is ahead of the staged package.
