# Stationary ship and background tests — 10 September 2026

**Later update:** The measurements below remain historical evidence. Subsequent source changes and timing checks are recorded in `OCR_HEADER_SEPARATOR_VALIDATION.md`; current continuation is at the top of `OCR_SESSION_HANDOFF.md`.

The user confirmed that the ship was stationary. They were already looking around during the first capture; it is a changing-view sample, not a fixed-camera control. CIG TSR was the last confirmed upscaler. No game settings were changed by these diagnostics.

## Actual runtime measurements

| Sample | Accepted frames | Attempts/s | Accepted/s | Median / p95 / maximum processing | Longest accepted-completion gap |
| --- | ---: | ---: | ---: | --- | --- |
| Looking around, `201747` | 40/60 | 3.40 | 2.26 | 120 / 506 / 610 ms | 2.26 s |
| Fixed view, bright marker behind text, `202709` | 0/60 | 2.54 | 0 | 379 / 605 / 684 ms | No accepted result during the sample |
| Clear dark-background control, `203006` | 60/60 | 4.03 | 4.03 | 113 / 153 / 200 ms | 0.30 s |

Evidence folders are `D:\Navpoint-background-20260909\live-runtime-20260910-<sample>`. Each contains the 60 native-resolution PNGs, `runtime.json`, `current-replay.json`, and `stationary-summary.json`. Offline replay reproduced all 180 acceptance decisions. Timing uses actual screen capture, reader, scanner and local diagnostic output, with framework/UI stubs; it is not a full installed-Wingman benchmark. PNG export occurs after timing. Finite-window rate is slightly above 4 because the final idle interval is excluded.

The user target is optimal 4 FPS, minimum 1 FPS during recovery. All individual processing attempts here took less than one second. That does **not** mean a fresh valid position was available every second: the moving view had a 2.26-second gap, and the marker-obstructed view supplied none.

The clear-background sample had exactly one unique accepted coordinate triple across 60 frames. The changing-view sample had nine triples, spanning 40.1 m / 62.2 m / 13.5 m in its displayed axes. Do not infer ship movement or an OCR error from this: the user was looking around, and the camera/reference behavior was not established. The fixed marker sample had ten fully decoded Root numeric tails, all identical, but no complete accepted position.

## What the repeatable failure shows

`202709/shot030.png` shows a bright marker crossing the SolarSystem header, with background structure elsewhere in both rows. The native reader returns `Zone:???????ystem_814261527756 ...`. It also refuses the separator and minus sign in this frame. Root's numeric tail is readable in that frame, but background artifacts contaminate its left margin. Across the sample, refusal reasons were missing readable SolarSystem anchor (48 frames) and missing readable Root anchor (12 frames). These categories summarize the first blocking parser reason, not every damaged character.

This is strong evidence that background interference limits current availability. It does not prove all other captures have the same cause, or identify the origin of previously observed digit transitions.

## Between-line background experiment

`gap_background_probe.py` estimates each cell's RGB background by interpolating between the pixel row immediately above the text band and its last pixel row. These pixels can contain small glyph/shadow remnants, so this is an approximate background estimate, not measured ground truth.

On the changing-view sample, its top-ranked glyph agreed with all 3,360 coordinate-tail characters in accepted frames. Of 93 refused coordinate cells sampled from rows with identifiable Root/SolarSystem text, 35 met the existing cost/margin limits under this model; the quadratic model produced 55 candidates. These are character proposals, **not** 35 or 55 newly valid positions. Severely damaged headers were excluded from this cell-level selection.

An additional conservative ambiguity probe asked whether a different digit, sign, point, unit character or blank could contribute 10%, 25% or 50% of the observed glyph under achievable pixel bounds. Every otherwise eligible quadratic proposal had at least one compatible mixture. This does not establish that those cells actually are mixtures: the bounds permit arbitrary background and are deliberately permissive. It does mean this probe did not certify a safe numerical recovery. None of the refused cells had quadratic residual at or below 2 intensity levels.

`gap_reader_replay.py` also tested complete-row interpolation with native alignment, existing cost/margin checks, small-mark checks, spacing checks and scanner validation. It is an unoptimized diagnostic subclass, including inherited native threshold-boundary fallback behavior, not a production candidate.

| Sample | Current reader | Experimental gap reader |
| --- | ---: | ---: |
| Looking around | 40/60 | 19/60 |
| Marker-obstructed fixed view | 0/60 | 0/60 |
| Dark fixed view | 60/60 | 60/60 |

The changing-view experiment gained only `shot030.png` and lost 22 currently accepted frames. Coordinate payloads agreed on all frames accepted by both. Experimental median processing was approximately 0.58–0.61 seconds; no optimization claim is made. The estimate can inform future work but is not a better whole-reader replacement and was not promoted.

## Alternative OCR cross-check

PP-OCRv6 medium agreed numerically with all 80 accepted Root/Solar rows in the changing-view sample. Its own two coordinate rows disagreed on five refused frames, including missing or extra minus signs and a digit error. In the marker sample, its rows disagreed numerically on three frames, and some headers were also misread. Each folder has `neural.json` and `neural-coordinate-comparison.json`. Neural agreement on other frames is not independent ground truth. The model remains diagnostic only.

A bounded string search of the current on-disk executable for display-info/debug-font/debug-text/background controls found `r_DisplayInfo` and `r_HideDebugText`, but no identified setting to reposition this overlay or give it an opaque background. This is not proof that no such setting exists. No new console probes or game-file edits were performed.

## Status and next decision

Production code, glyph bank, configuration and installed copies remain unchanged. The four runtime-source hashes were checked and match the prior validated revision. No new full test-suite result is claimed; the previous 1,004-test run remains historical evidence for that unchanged source.

The exact-reading policy remains the limiting boundary: fresh full Root/Solar evidence is required, with no numerical guessing or substitution of neural text. The tested background alternatives do not yet justify relaxing it. A materially different recovery design could reuse a recently confirmed system label while still reading fresh coordinate digits, but that changes the per-frame evidence contract and needs the user's requirement decision. It must not be silently enabled or treated as already authorized. Any such design must distinguish retained context from freshly observed data and invalidate it on ambiguous row/layout/system changes.

The OCR objective is not complete. Do not repeat the completed stationary captures or console checks as though they were pending.
