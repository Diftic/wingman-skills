# Saved-waypoint direction: calibration preparation — 10 September 2026

The user selected **Add direction** before the save/fly/return test. This work is not complete: the source now supports a calibration arrow for newly saved coordinate-stack waypoints, but normal direction remains disabled pending live flight evidence.

## Implemented

- The existing explicit `space_direction_test`/`allow_uncalibrated_space` path can now draw a Root-waypoint arrow using the corrected `system_camdir_orientation` calculation.
- Both endpoints come from serialized Root coordinates. Flattened x/y/z and nested container coordinates do not choose the direction.
- Missing/corrupt stacks, Root/Solar disagreement, missing/invalid facing, invalid or stale capture age, coincident positions and the latest reader refusal all suppress the arrow.
- Malformed integer coordinates that overflow float conversion now return no arrow in this path. Review found this case; both current/target regression tests failed before the guard and passed afterward.
- Existing calibration logs now include stack targets and record the actual Root points used. The badge describes the corrected convention as unverified, rather than incorrectly calling it the old known-wrong formula.
- No OCR, retry, coordinate-selection, local-tracking, normal voice or HUD gate was enabled or relaxed. No installed copy, database or release was changed.

## Verification

- Full suite: **1,043 passed in 38.85 seconds**.
- New test file alone, from the skill directory: **27 passed in 0.27 seconds**. Test bootstrapping was fixed after review found that importing main relied on other test modules.
- Initial direction tests failed in six positive cases because stack targets previously produced no arrow; eighteen refusal/default-gate cases already passed.
- Review checked Root provenance, gate containment, trace coordinates and the malformed-coordinate guard. The explicit test switch is not an automatic open-space detector: safe interpretation of this calibration still depends on the pilot arranging the requested flight context.
- The displacement analyzer was checked against `live-runtime-20260910-215506`: it found **zero qualifying flight windows** in the stationary control, as expected. This is a negative control, not positive calibration evidence.

## Next live step — user input required

The user has been asked to reach clear open space, stop the ship, center the cockpit view and disable freelook/head tracking, then report ready. No readiness reply has arrived yet. Do not enable ordinary direction or claim a successful return before that evidence exists.

1. Take a fresh baseline with `r_displayinfo 2` visible and the coordinate area unobstructed.
2. Capture a short pilot-controlled straight forward flight with fixed orientation. Use current `live_runtime_benchmark.py`; it obeys the one-retry cap and saves original PNGs and runtime decisions.
3. Run `direction_calibration_analyze.py <capture-folder>`. It compares Root displacement with predicted forward direction in >=50 m windows lasting 1–2 seconds, with >=4 accepted frames and <=2 degrees facing variation. The pilot must confirm no strafe/drift; the analyzer cannot infer that input condition.
4. Verify right/up/roll against the known saved starting point. Forward movement alone does not validate the complete screen arrow.
5. If results support a bounded camera-to-Root mapping, finish normal ring/HUD/voice integration and the real return flight. If context changes invalidate the mapping, keep direction unavailable and resolve that mapping first. Local tracking stays disabled until separately validated.

Wingman was not running at last inspection. Installed files are under `C:/Users/larse/AppData/Roaming/ShipBit/WingmanAI/custom_skills/sc_navpoint`; this copy is older, differs in main/reader/fields/config and has no coordinate_stack.py. It must not be mistaken for the tested source. The glyph bank matches. Preserve the installed waypoint database and existing configuration when preparing a reversible tested package.

The four-normal/one-recovery verified-position rate and at-most-one-retry-per-image requirements remain active. This calibration work does not establish either a universally correct arrow or a guaranteed verified result rate.

Evidence: `before-stack-direction/`, `stack-direction-calibration.patch`, `direction_calibration_analyze.py`, `tests/test_stack_direction_calibration.py`, and the source plan at `docs/superpowers/plans/2026-09-10-navpoint-direction.md`.
