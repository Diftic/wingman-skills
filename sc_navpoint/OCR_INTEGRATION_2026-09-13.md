# OCR integration continuation

Authorized behavior: automatic OCR only; no required `/showlocation` or manual coordinate input. One inference per image, failed frames discarded, sequential fresh captures without a fixed FPS cap. Retain the last successful display with its original capture time and visible age; held readings must not drive new arrival events or count as fresh fixes.

Implementation sequence: align the existing capture dispatcher and scheduler with that policy; preserve capture timestamps; restore held-display behavior without relaxing frame/target validity; provide a portable specialist-model adapter using the same scanner gates; validate on saved images and then connected-game footage. Keep production installation unchanged until the integrated reader is validated. No new tools or external APIs are required.

Current orientation found residual brightness/header recovery in main.py, an explicit polling interval, and capture timestamps assigned after inference. The browser already retains coordinate values, but the ring blanks on each failed attempt. Existing tests encode the superseded retry/blanking policies and need corresponding expectation updates.

## Implemented in the source checkout

- One screenshot and one selected-reader pass per capture, including marking. Legacy attempt arguments cannot enable retries. The brightness/header recovery path is no longer called.
- Capture timestamps are taken immediately before the screenshot and preserved through decoding. A failed poll never publishes a position or creates a new arrival event.
- Navigation immediately captures the next frame after the previous attempt finishes. There is no OCR rate cap or queue. A 250 ms availability wait applies only when no screenshot/reader is available or an unexpected exception occurs.
- A recent valid ring direction survives a failed read with `HELD` and its age. Existing freshness, target-frame and direction-calibration gates still apply; after the freshness window, coordinates remain visible as stale but direction is withheld. The position panel shows read age.
- The obsolete `poll_interval` property remains declared solely to let saved Wingman settings merge safely; its value is ignored.
- The optional `specialist_ocr_candidate` setting selects the portable CPU V6 reader. It is off by default. The model/alphabet are hash-pinned and stored under `models/specialist_v6`; V5 is preserved for comparison. No runtime downloads or automatic reader switching occur.
- The learned parser rejects malformed or empty intervening rows rather than silently dropping a damaged part of the coordinate hierarchy. This conservative empty-row rule needs further validation.
- Both release manifests include the runtime adapters and model directory. The release folder and installed Wingman have not been regenerated or overwritten. OpenCV bundling for the actual Wingman interpreter remains pending.

## Recognition evidence

The first portable V5 read of the previously paired saved screenshot took 157.1 ms. Root coordinates and camera matched the visual label, but `glaciemring_segment_wtn-003` became `glaciemring_segment_ tn-003`; the old parser silently dropped that nested row. A regression test now covers this refusal. The saved recognized strings were reparsed without another OCR attempt.

A cached synthetic-text audit also exposed uppercase/lowercase container-name errors. V6 was therefore trained for a bounded 80 CPU steps from V5, using new random mixed-case names and independently seeded synthetic rows. No failed evaluation screenshot, literal failed name or coordinate label was copied into training. Training took 119.9 seconds; all checkpoints and source provenance are preserved separately.

| Offline comparison | V5 | V6 |
| --- | ---: | ---: |
| Exact held-out rows, out of 192 | 130 | 185 |
| Median single-row inference | 17.5 ms | 17.6 ms |
| Accepted fresh complete blocks, out of 64 | 29 | 29 |
| Accepted blocks with every required field correct | 25 | 29 |
| Incorrect accepted blocks | 4 | 0 |
| Median complete-block processing | 120.6 ms | 122.3 ms |

The 64-block set contains 32 deliberately empty intervening rows, refused by the conservative parser; these are availability losses and must not all be described as OCR errors. Synthetic test images share the training renderer. Zero wrong accepts in this small test does not prove perfect live recognition, sustained fresh-fix cadence or navigation readiness.

The export parity check passed six inputs with identical argmax outputs. The source candidate loads using CPUExecutionProvider with 96 alphabet entries. JavaScript syntax validation passed for the position-age UI change. Full regression results are recorded in the scratch test logs; live accuracy and actual Wingman runtime compatibility remain unverified.

## Evidence and next validation

- `D:\Navpoint-background-20260909\v6-case-heldout-comparison.json`
- `D:\Navpoint-background-20260909\v6-frozen64-portable-comparison.json`
- `D:\Navpoint-background-20260909\portable-specialist-first-image-20260913.json`
- `D:\Navpoint-background-20260909\portable-cached-row-audit-20260913.json`
- `D:\Navpoint-background-20260909\specialist-ascii-case-v6\training.json`
- `D:\Navpoint-background-20260909\specialist-ascii-case-v6\export-parity.json`
- `D:\Navpoint-background-20260909\v6-integration-final-tests-20260913.txt`

Next: collect foreground Star Citizen display-info footage while connected, retain original images/timestamps, and independently label accepted and refused frames. Measure correct fixes per second and maximum fresh-fix gap, not merely syntactically complete proposals. Establish whether real layouts contain blank slots before relaxing that refusal. Then validate packaged dependencies and the save/fly/return workflow in Wingman. `/showlocation` is excluded from required operation and is unnecessary for this next test.

No training/capture monitor, shutdown or production deployment is pending after this bounded trial.

Final source validation: **1097 passed in 34.20s**; foreground guard returned `Star Citizen is not foreground`. No live image was captured during that guard check.

## Subsequent live test: promotion failed

Two accepted numeric errors were confirmed in connected-game footage. V6 is not navigation-ready despite the synthetic improvements. See `D:\Navpoint-background-20260909\OCR_V6_LIVE_VALIDATION_2026-09-13.md`. Installed Wingman remains unchanged. Stationary-control readiness is pending.
