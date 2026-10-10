# NavPoint live OCR and cadence validation — 9 September 2026

Follow-up: NVIDIA frame generation was reported inactive. See [the capture diagnosis](OCR_CAPTURE_DIAGNOSIS.md) for neighboring-frame evidence, the alternative-capture experiment and the requested DLSS comparison.

The development reader now targets **4 readings/second**, with recovery aimed at **at least 1 reading/second**. In the final live sample the actual capture dispatcher averaged **3.67 readings/second**; its slowest cycle took **628 ms**. These are measured results on this machine and scene, not a hard latency guarantee for every rendering configuration.

## Implemented

- Batch native glyph arithmetic and per-cell measurements while retaining the full glyph search, refusal thresholds, clipping, ambiguity checks, and scalar extension hooks.
- Batch the existing header-only background fit. Flexible numerical recovery remains experimental and is not used by navigation.
- Recheck alignment as before; if the same immutable frame has the same origin, reuse its already decoded rows. A changed origin still triggers another decode.
- Support a 0.25–10 second tracking interval, with 0.25 seconds as the development default. Existing explicit settings remain effective.
- Schedule start-to-start: OCR time counts toward the interval, and slow reads do not create queued catch-up requests.

The changes are in the development project. Installed Wingman copies and generated `release_version/` were not overwritten. An existing installation configured for five seconds will retain that setting until changed.

## Measured timing

| Measurement | Samples | Median | 95th percentile | Slowest |
|---|---:|---:|---:|---:|
| Saved frames, ordinary path | 857 | 115 ms | 184 ms | 705 ms |
| Saved frames, recovery attempted | 171 | 299 ms | 654 ms | 904 ms |
| Live capture dispatcher | 60 | 135 ms | 461 ms | 628 ms |

All measured recovery cycles finished within one second. In the live sample, 54/60 complete cycles finished within 250 ms. The dispatcher measurement includes the real screen grab, OCR, scanner validation and diagnostic log writes. Framework/UI output was stubbed in an isolated process; it does not measure the complete running Wingman application. PNG export happened after measurement. The live sequence included both changing values and a stationary interval.

Before batching, the initial 45-frame live sequence took a median 1.06 seconds through the recovery pipeline. After batching its text and acceptance decisions were identical. The final full-corpus replay preserved **all 883/1,028 successful captures**, with no changed successful payloads or acceptance decisions. See [the earlier background investigation](OCR_BACKGROUND_VALIDATION.md) for the original 637/1,028 baseline and accuracy limitations.

## Live accuracy findings

The first moving sequence yielded 13/45 accepted captures versus 10/45 for the original reader. A later, different live sequence yielded 50/60; those rates describe availability in different scenes, not a controlled improvement comparison or a ground-truth accuracy percentage.

The separate neural recognizer agreed with all 100 Root/Solar coordinate rows from the 50 successful final live captures, and all 26 rows from the 13 initial successes. This is a cross-check, not independent ground truth.

Some changing coordinate digits are blended images. In `live-20260909-205443/shot020.png`, fitting one refused decimal cell as approximately 52–53% `2` plus 47–48% `5` reduces pixel error from about 37 to 1.1 RGB levels. The neural recognizer emitted `3` in both coordinate lines. This supports temporal blending as a separate problem from background noise; its source has not yet been established.

An isolated inter-line/background experiment recovered six additional live frames and 17 previously refused older captures. It remains **outside production**: independent review constructed a 90% `4` / 10% `0` blend that the experiment accepted as `4` in both Root and Solar, producing a 40 m endpoint difference. Agreement between the two lines cannot resolve that correlated ambiguity. The experiment's “unique glyph” check does not establish an unblended current digit.

Next required input: establish whether frame generation is enabled in the game, driver, or another application. If enabled, collect a comparable sequence with it disabled. This will distinguish rendering/capture blending from the remaining OCR/background issues.

## Verification and evidence

- Complete NavPoint suite: **1,004 passed**.
- Independent final code review: no blocking findings; 27 focused tests independently passed.
- The review's unsigned-PNG overflow finding was fixed with float promotion after custom-hook dispatch and covered by unsigned-input tests.
- Numerical recovery, local-tracking authority and glyph-bank calibration were not expanded by the performance work.

Evidence is saved under `D:\Navpoint-background-20260909`:

- `performance-replay.json`: final 1,028-frame replay, timing and source hashes.
- `live-20260909-205443/`: 45 native captures, original/current replay, neural checks, and pixel-mixture analysis.
- `live-runtime-20260909-212556/`: 60 native captures, actual-dispatcher timings and logs.
- `live-manual-truth.json`: selected visually checked coordinate examples; not full-corpus labels.
- `live_unique_probe.py`, `offline-unique-gap-probe.json`: isolated numerical recovery experiment, not runtime dependencies.
- `before-performance/overlay_reader.py`: exact reader before the performance changes.
