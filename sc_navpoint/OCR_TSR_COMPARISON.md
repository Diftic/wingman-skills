# OCR continuation: DLSS / CIG TSR comparison — 10 September 2026

The user could not turn upscaling off and changed the technique to **CIG TSR (Recommended)**. This was a DLSS-to-TSR comparison, not an upscaling-off test. The scene, world position and number of coordinate rows also changed between samples. These results cannot establish a causal performance or quality difference between the techniques.

| Measurement | Before switch | CIG TSR |
| --- | ---: | ---: |
| Frames accepted | 52/60 | 53/60 |
| Attempts per second | 3.68 | 4.00 |
| Accepted results per second | 3.19 | 3.53 |
| Median processing time | 123 ms | 105 ms |
| 95th percentile | 338 ms | 181 ms |
| Maximum processing time | 787 ms | 323 ms |
| Longest gap between accepted completions | 1.93 s | 0.83 s |
| Neural agreement on accepted coordinate rows | 104/104 | 106/106 |

The original frozen reader accepted only **12/60** on the same saved pre-switch images, versus **52/60** for the current source. Offline replay reproduced every current acceptance decision. This supports the existing OCR changes, not whole-corpus accuracy. Neural agreement is a cross-check rather than ground truth. Timing includes actual capture/reader/scanner but framework/UI outputs are stubbed; it is not a benchmark of the complete installed Wingman app.

## Captured digit transitions

A separate CIG TSR burst recorded 240 native overlay frames over 4.057 seconds. 131/240 passed the existing reader. The pixel comparison found **22** refused numeric cells closely matching mixtures of neighboring captured frames. Example: frame 132, row 2, cell 14 lies approximately 49.2% between the neighboring digit-2 and digit-3 images, with RMS error 0.801 versus 35.6/34.5 against either neighbor alone.

Thus changing to CIG TSR did not eliminate the captured transition phenomenon. The source of the phenomenon remains unknown. Do not attribute it to frame generation; the user reports that disabled. The 131/240 burst acceptance rate is from a different moving scene and cadence, and must not be directly ranked against the earlier DLSS burst's rate.

## Existing fresh-image retry path

An isolated benchmark exercised the already-existing `attempts=2` path. Each attempt captured a new image and used unchanged validation; no digits or coordinates were combined across frames. Production polling was not changed.

- 60 cycles, 77 separately saved frames.
- First attempts accepted: 43/60; with one retry: 49/60.
- Six of the 17 failed first attempts were recovered by the second image.
- Median cycle 129 ms; p95 762 ms; maximum 971 ms.
- 2.85 cycles/second and 2.33 accepted results/second in this sample.
- No cycle exceeded one second, but the maximum leaves little margin. This run does not establish compliance on other scenes or machines.

The retry helps some single-frame failures. It is not yet justified as a poll-loop change: the existing poll loop already obtains another fresh image, and additional retries/delay could reduce useful throughput. This experiment measures within-cycle recovery, not a proven improvement in time-to-next-valid-position versus normal polling on equivalent footage.

## Status and next direction

No production OCR source changed in these experiments. The prior 1004-test result still applies to the unchanged source; no new full test run was claimed. No deployment occurred. Current performance is near the normal attempt-rate target in these samples, but rejected frames can produce gaps longer than one second between valid positions. Therefore reliable 1 Hz fresh output in every recovery condition is **not established**.

The trace/analytics console experiments are paused: a known `r_displayinfo` query answered normally, while the proposed trace/analytics controls gave no response or completion. The trace filter remains unapplied. The game now has the user-selected CIG TSR setting; there is no evidence-based requirement to keep it for OCR, and any restoration to DLSS should follow the user's preference.

Further recovery work must demonstrate increased valid-position throughput while preserving single-image validation and the one-second recovery budget. Do not revive the previously rejected numerical gap-reconstruction prototype or treat neural confidence as permission to emit uncertain digits. Bright scene edges and transition frames remain the principal observed limits.

Evidence folders: `live-runtime-20260910-200039`, `live-runtime-20260910-200550`, `burst-20260910-200631`, and `live-retry-20260910-201229`, all under `D:/Navpoint-background-20260909`. Each contains saved images and machine-readable results.
