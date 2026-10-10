# SC NavPoint OCR background recovery — 9 September 2026

This records the original offline stage. For the subsequent live captures, performance changes, 1,004-test verification and outstanding blended-digit investigation, see [Live OCR validation](OCR_LIVE_VALIDATION.md).

**Saved-capture availability improved from 637/1028 to 883/1028. No previously successful capture was lost; shared coordinate values and existing headings did not change.**

These are successful coordinate captures through the scanner, not an accuracy percentage. The corpus contains repeated frames from 23 known sessions, including 30 deliberately unusable menu/overlay-off controls. Only the explicitly labelled rows are manual ground truth. Fresh live validation is still required.

## Implemented in the development project

- Corrected the shadow transmission to `(1-G) * (1-shift_down_right(G))`. The old 2×2 maximum expansion darkened pixels beside the glyph incorrectly.
- Required exact single spaces in Zone headers and coordinate fields. Erased leading signs/digits and erased name suffixes leave extra cells; they must not become harmless whitespace.
- Added a physical ambiguity veto for minus signs and decimal points. A constructed backdrop previously made a real minus read as `9` at cost 8.4 and margin 39; the new check refuses it. A genuine rendered `9` remains accepted.
- Added coordinate-only brightness recovery after an ordinary failure. It retains the cost-15/margin-8 and ink-contradiction checks. Exact layout and ambiguity checks replace blanket clipping/flat-white refusal in this retry. Newly recovered headings are not used.
- Added recovery of refused Root/SolarSystem header letters using a curved local background. It replaces only `?` cells, preserves every confident native header character and every system-id digit, and copies coordinate characters unchanged. Coordinates are checked again after a repaired `Pos:` label.
- Kept all downstream scanner checks and local-tracking policy. No neural model, additional runtime dependency, or game configuration change was required.

## Replay results

| Stage | Accepted captures | Added |
|---|---:|---:|
| Original reader | 637 | — |
| Corrected shadow | 824 | 187 |
| Brightness recovery and safety fixes | 859 | 35 |
| Header recovery | 883 | 24 |

The production reader was replayed on all 1,028 frames. After the header-only extension, the 169 remaining failures were replayed through the final retry sequence; previously successful reads bypass that extension. Source hashes are recorded in the JSON evidence.

| Session | Frames | Original | Final |
|---|---:|---:|---:|
| bright-01 | 11 | 0 | 11 |
| bright-02 | 10 | 0 | 9 |
| camdir-01 | 60 | 17 | 40 |
| dark-01 | 20 | 13 | 17 |
| flight-01 | 20 | 17 | 19 |
| fov-01 | 80 | 75 | 75 |
| game-bright | 5 | 0 | 5 |
| game-mid | 5 | 5 | 5 |
| ice-bright | 5 | 0 | 1 |
| jumppoint-pyro-nyx | 40 | 29 | 34 |
| login | 5 | 0 | 0 |
| login-black | 5 | 0 | 0 |
| nosignal-01 | 20 | 0 | 0 |
| p5l2 | 15 | 15 | 15 |
| preflight | 5 | 2 | 2 |
| pyro3-bloom-approach | 96 | 39 | 85 |
| pyro5-vuur | 156 | 78 | 136 |
| red-01 | 150 | 111 | 134 |
| starfield | 5 | 0 | 0 |
| surface-01 | 90 | 90 | 90 |
| terrain-01 | 20 | 0 | 20 |
| vote-fast | 5 | 0 | 0 |
| vuur-return-outside | 200 | 146 | 185 |

## Ground truth, adverse inputs, and verification

- 1,072 manually labelled characters across 16 Root/Solar rows: the corrected shadow matcher accepted 1,010 correctly and zero incorrectly at the scoring stage. This is a selected label set, not ground truth for every replayed frame.
- The small-mark veto removed zero coordinate cells from the 824 successful corrected-shadow captures.
- The isolated brightness experiment was stress-tested on 72 cases covering paired sign/digit/decimal/unit damage, dimming, gamma/exposure changes and flat frames: 9 retained correct coordinates, 63 refused, zero accepted wrong coordinates. This preceded the later ambiguity/header changes. Final production regression tests also cover the constructed minus-to-nine failure and its combination with a damaged `Pos:` label.
- A separate PP-OCRv6 medium recognition model agreed on 118/118 coordinate rows from the brightness/header gains. Model agreement is a cross-check, not independent ground truth.
- Final complete test suite: **977 passed**. This includes real saved images through Wingman’s actual capture dispatcher for bright ice and a damaged Root header.
- Independent code review found no blocking issues. Its damaged-label ambiguity-bypass concern was incorporated and regression-tested before header recovery was accepted.

## Why the gap idea helped, and which OCR models were tried

Sampling between lines estimated smooth background well, but direct interpolation could include descender shadows or miss small structures hidden beneath a glyph. On the 69-frame holdout it reduced acceptance from 30 to 28. It was useful evidence for discovering the incorrect shadow model, rather than a reliable universal replacement.

Tesseract 5.5, PP-OCRv6 small and PP-OCRv6 medium were tested locally. On the 16 labelled rows, raw PP-OCRv6 medium recovered all coordinate triples and 15 whole lines; Tesseract recovered one exact coordinate triple. Wider neural trials still inserted/dropped signs or damaged labels. Neural proposals therefore remain isolated experiments. The flexible background model is used only for headers, with native coordinate cells preserved.

Model provenance: [RapidOCR model manifest](https://github.com/RapidAI/RapidOCR/blob/main/python/rapidocr/default_models.yaml), [PaddleOCR](https://github.com/PaddlePaddle/PaddleOCR). Downloaded models and OCR packages live in the experiment folder’s separate virtual environment.

## Remaining limit and next input

145 captures still refuse, including all 30 menu/overlay-off controls. Dense starfield/ice detail still obscures numeric cells in some scenes. The model remains calibrated to native 7.5-pixel character pitch and 13-pixel rows; changes to rendering, scaling, gamma or font need fresh measurements. There is no claim of perfect OCR or universal protection against arbitrary image corruption.

Next: run Star Citizen with `r_displayinfo 2` visible and collect fresh native-resolution overlay PNGs under the current settings, including stationary and moving views against dark, bright and detailed scenery. The existing dev capture tool supports lossless PNG recording. The game was not running during the final offline verification.

Changes are in the development project. Generated `release_version/` and installed Wingman copies were not rebuilt or overwritten.

## Reproduction and evidence

```powershell
Set-Location 'D:\PycharmProjects\wingman-ai'
python -B -m pytest skills/sc_navpoint/tests -q -p no:cacheprovider --basetemp D:\Navpoint-background-20260909\pytest-new-check
```

Experiment/evidence folder: `D:\Navpoint-background-20260909`. Main evidence files:

- `full-replay.jsonl`: original and corrected-shadow comparisons, screenshot hashes.
- `production-replay.json`: complete production brightness replay.
- `header-runtime-replay.json`: final retry sequence on the remaining failures.
- `truth.json`, `labelled_cells.json`: manual labels and cell-level comparisons.
- `adversarial-saturation.json`, `adversarial-sign-shape.json`, `candidate-bounds.json`: stress cases and conditional bounds.
- `gains-neural-comparison.json`, `header-gains-neural-comparison.json`: alternative-model comparisons.
- `final-summary.json`, `OCR_changes.patch`: final counts, source hashes, and reviewable changes against the preserved starting files.

The numerical wrong-digit bounds apply only to the stated glyph/compositing model, not arbitrary display transforms. They must not be used to justify raising the coordinate refusal threshold.
