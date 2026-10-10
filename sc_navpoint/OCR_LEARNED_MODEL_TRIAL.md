**CURRENT — 12 September: project resumed, uncapped single-pass OCR.** No retries or fixed FPS delay; discard failures and capture fresh images. Final UI will retain the last successful display without counting it as fresh. Read `D:\Navpoint-background-20260909\OCR_CONTINUATION_2026-09-12.md`. Connected-game timing/accuracy pending; no deployment.

**CURRENT — live v4 captured, v5 sharp-edge training trial next.** Live106/120 complete,2.59proposals/sec,2.37-second maximum gap;14recoveries all failed. Eight selected coordinate/camera spot checks matched. Recovery1Hz NOT met. Read `D:\Navpoint-background-20260909\OCR_EVENING_CONTINUATION_2026-09-11.md`. No deployment or shutdown.

**CURRENT — frozen v4 evaluated, 11 September evening.** Fresh synthetic test:117/120 exact coordinates and direction,three discarded,zero wrong accepted; median185ms,maxrecovery1.155s. Full live accuracy and1Hz recovery NOT established. Fresh capture waits ended because game was not foreground. Read `D:\Navpoint-background-20260909\OCR_EVENING_CONTINUATION_2026-09-11.md`. No capture process, deployment or shutdown pending. Older banners below are historical.

**CURRENT — v4 training completed (218 steps), 11 September evening.** Read `D:\Navpoint-background-20260909\OCR_EVENING_CONTINUATION_2026-09-11.md`. Live48/60 complete with a3.111-second gap; confidence cutoff caused19 unnecessary retries. New no-cutoff/recovery-veto experiment awaits fresh timing. Results remain unverified; no deployment or shutdown. Older training-active banners below are historical.

**CURRENT — OCR experiment active, 11 September evening.** V3 was rejected after accepted wrong readings. Read `D:\Navpoint-background-20260909\OCR_EVENING_CONTINUATION_2026-09-11.md`. A complete-font/ASCII v4 trial is training; no deployment or shutdown is pending. The earlier live54/60 result had a1.939-second gap and was not independently verified accuracy. Earlier status banners below are historical.

**CURRENT — evening continuation, 11 September 2026.** Work resumed; no shutdown is pending. Read `D:\Navpoint-background-20260909\OCR_EVENING_CONTINUATION_2026-09-11.md`. New live reader produced 54/60 complete proposals, but a 1.939-second gap still fails the recovery requirement. These are not 54 independently verified readings. Full-row candidate v3 is being prepared. Installed Wingman and database unchanged. Older paused/pending statements below are historical.

# Learned overlay OCR trial — 10–11 September 2026

**Final shutdown state:** Paused at user request after tests completed. Full suite: **1,078 passed**, plus five standalone policy/scoring checks. The ONNX export succeeded (4,536,660 bytes; SHA256 `42fc3cf21c6d7401bd9ff7ed329b1f351f10f0141e6d3f0f23aba896adc718d5`), preserving raw text on all 17 comparison frames. Median processing fell to 74 ms, maximum 100 ms. Final camera-anchor localization tolerates unrelated leading row noise without changing numeric fields and rejects duplicate anchors.

**Final cascade evidence:** Specialist first, Small model once if incomplete, then discard. All 21 coordinate-labelled frames were correct; all 13 labelled camera rows were correct. Four frames required recovery; median 104 ms, maximum 585 ms. A 120-frame unlabelled moving-reflection challenge produced 103 complete proposals, with 37 recovery attempts and 17 discards. Median 105 ms, maximum 598 ms; longest consecutive discard run two frames. These are unverified proposals, so live accuracy and fresh 1 Hz recovery are not established. No deployment. The detailed continuation note is `D:\Navpoint-background-20260909\OCR_SHUTDOWN_HANDOFF_2026-09-11.md`, with hashes and environment snapshots alongside it. Pending export statements below record the earlier trial stage and are superseded.

Status: evaluation only. No trained model feeds navigation or the installed Wingman skill. The user approved a model replacement investigation after the live reader rejected 44% of the last five-minute return-ring recording. The return flight remains incomplete.

## Pretrained comparison

The development set has 17 manually transcribed coordinate frames; nine also have camera-angle labels. Complete proposals require readable anchors, exact Root/Solar metre agreement, and a current camera direction. Proposals are explicitly unverified: agreement does not establish correctness.

| CPU recognizer | Exact coordinate frames | Exact labelled cameras | Structurally complete proposals | Median / maximum processing |
| --- | ---: | ---: | ---: | --- |
| Tiny ONNX | 12/17 | 9/9 | 0/17 | 0.107 / 0.233 s |
| Small ONNX | 17/17 | 9/9 | 11/17 | 0.455 / 0.940 s |
| Medium ONNX | 17/17 | 9/9 | 16/17 | 1.909 / 3.774 s |
| Tiny Paddle training network, unchanged | 13/17 | 9/9 | 0/17 | 0.319 / 0.659 s |

Evidence: `D:\Navpoint-background-20260909\learned-spatial-batch1-rescored.json` and `learned-paddle-base-batch1-rescored.json`. Timing includes row preparation, recognition and parsing, but excludes screen capture and disk reads. Only nine frames have both kinds of independent manual label; structural completeness across all 17 is not complete-reading accuracy. These repeatedly examined examples are development data, not a final holdout.

The recognizer's spatial word groups recover missing camera separators without changing any non-whitespace character. This differs from guessing where to split a merged number. Header spelling remains a major refusal source.

## Training experiment

Isolated environment: `D:\Navpoint-background-20260909\.venv`. Official PaddleOCR tiny checkpoint, 1,119,614 parameters in the CTC branch, CPU training. The generator creates 2,000 training and 256 synthetic validation crops from measured game glyphs, procedural backgrounds and separate real background source images. Neither background source is a development evaluation image. Source hashes, labels and generated-image hashes are retained.

The first 200-step trial reduced training loss but failed all 17 real coordinate frames. Restoring its original normalization statistics recovered 14/17, but one wrong coordinate passed structural checks: both Root and Solar changed `-9633300.6073km` to `-9633300.6078km`. This five-metre correlated error rejects that candidate and directly demonstrates why cross-row agreement is not verification. Freezing normalization throughout training alone also failed.

Diagnosis: the official backbone pools training inputs to 40 time steps, while inference retains variable spatial width. Variable-width synthetic training crops therefore had mismatched character spacing. The corrected experiment uses inference pooling during training, retains raw CTC logits and gradients, and freezes normalization statistics. Independent review confirmed nonzero gradients and exactly matching training-softmax/evaluation output for identical input.

The corrected 200-step trial (`specialist-tiny-matched-pool`) scored 13/17 exact coordinate frames, 9/9 labelled cameras, and 12/17 structurally complete proposals, with zero observed wrong coordinate proposals. Synthetic validation improved from 31/64 to 58/64 exact strings. Real-frame median processing was 0.295 seconds, maximum 0.405 seconds. This is substantial header improvement over the unchanged tiny network but no net coordinate-accuracy improvement, and it does not meet the complete-read objective. Evidence: `learned-paddle-matched-pool-batch1.json`.

Four additional scenes were separately transcribed: Vuur return, bright hangar, P5 L2 and a red interior. The specialist read all four complete frames correctly (median 0.269 seconds, maximum 0.311 seconds). One manual label was corrected after inspecting a model discrepancy: the bright-scene X integer ends in 9, not the initially transcribed 0. The enlarged original crop visibly establishes that correction, and the original prediction/label file is preserved. This is a small additional check, not broad reliability evidence. Evidence: `learned-new-scenes-specialist-batch1.json` and `bright01-label-audit.png`.

Export to ONNX is being tested in a separate Python 3.12 environment because the exporter has no current Python 3.13 Windows wheel. No successful export or faster-runtime timing is established yet.

## Scoring and review

Review found that the original coordinate metric could silently ignore extra punctuation before a number. It now requires the entire three-token suffix to match; two regression tests failed before the correction and pass afterward. Re-scoring existing predictions reduced Tiny ONNX from 14 to 12 exact frames and Paddle baseline from 15 to 13. Small and Medium counts were unchanged. Original evidence files were preserved.

The experimental adapter has 30 passing tests. The full NavPoint suite passes 1,074 tests. The code remains outside the production reader path. A remaining training/inference preparation difference is one-pixel width rounding and padding to the longest example in a training batch.

## Enlargement

The neural recognizers already enlarge 13-pixel-high text rows to 48 pixels, approximately 3.7×. Earlier controlled 4× nearest-neighbour and bicubic experiments are recorded in `OCR_RESIZE_COMPARISON.md`: nearest-neighbour helped some header labels, but no method consistently improved numerical recognition across difficult backgrounds. Enlarged diagnostic images are separate from the native-pixel production reader.
