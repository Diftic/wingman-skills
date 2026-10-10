# Header separator recovery validation — 10 September 2026

The reader now handles a narrow additional background failure: a high-contrast scene inside a space between otherwise fully readable header words. It requires the native best candidate to be a space and checks that every non-space glyph contradicts the original RGB pixels. It changes only that literal header space. Name letters, punctuation, IDs, digits, signs, units and coordinate separators remain native.

Incomplete RGB bands and invalid offsets are refused before fitting. This also fixes an existing header-recovery exception on truncated bands. Recovery keeps the original numeric tail and reruns the small-mark ambiguity check. The native-resolution input, glyph bank, parser, scanner, cadence and installed copies are unchanged. No neural model was added to the live path.

## Verification

- Full skill suite: **1,013 passed in 72.19 seconds**. New regression suite independently reviewed: 9 passed. Focused combined header suites: 12 passed. The pre-implementation tests failed on the two legitimate separator cases and three truncated-band cases; four negative cases already passed.
- Complete saved-frame replay: **1208 frames, 983 accepted before, 986 after**.
- Historical 1,028-frame corpus: **883 → 886 accepted**.
- Previously accepted frames lost: **0**. Previously accepted coordinate payloads changed: **0**.
- Recent 180-frame background comparison unchanged: looking around 40/60, fixed marker obstruction 0/60, clear fixed view 60/60.
- Independent review found no blocking defect in the final integration. The previously demonstrated mixed R/P label remains refused. 43 invalid-geometry/offset cases produced no exceptions. The earlier prototype checks also rejected 79 protected-character mutations and 130 nonblank-glyph substitutions.

New accepted historical files:
- `D:\PycharmProjects\wingman-ai\skills\sc_navpoint\ocr_dev\captures\bright-02\frame_0003.png`
- `D:\PycharmProjects\wingman-ai\skills\sc_navpoint\ocr_dev\captures\pyro5-vuur\frame_0058.png`
- `D:\PycharmProjects\wingman-ai\skills\sc_navpoint\ocr_dev\captures\pyro5-vuur\frame_0060.png`

The gain is modest. It does not solve the marker-obstructed view, and accepted-frame counts are availability evidence, not a whole-corpus accuracy measurement. The ordinary and recovery processing distributions in `header-separator-validation.json` describe this offline replay, not a guarantee of fresh valid positions every second.

## Fresh live measurement

```json
{
  "folder": "D:\\Navpoint-background-20260909\\live-runtime-20260910-212442",
  "frames": 60,
  "accepted": 0,
  "attempts_per_second": 0.9857173563646636,
  "accepted_per_second": 0.0,
  "seconds_median_p95_max": [
    0.9104219999999259,
    1.4158607100003768,
    2.6880952999999863
  ],
  "max_accepted_completion_gap": null
}
```

This is actual capture/reader/scanner timing with framework/UI outputs stubbed. It is not the full installed Wingman application. It is a fresh scene, not a paired comparison to earlier live runs. Visual inspection of shot030.png shows a desktop window covering the left part of the coordinate rows. This run therefore measures rejection under obstruction; it is not a clean game-view accuracy test.

## Recovery timing remains unresolved

The full saved replay measured ordinary reads at median 150 ms and p95 242 ms, with recovery median 452 ms, p95 908 ms and maximum 1.801 seconds. The target of at least one recovery attempt per second is therefore not established under the current load, and fresh accepted positions are a separate requirement.

`timing_isolation.py` alternated the previous and current readers on the same five saved frames over three repetitions. Default math-library threading gave previous/current medians of 728/696 ms and maxima of 1.019/1.020 seconds. A separate child process with `OPENBLAS_NUM_THREADS=1` gave medians of 720/702 ms and maxima of 914/1,066 ms. This small check does not attribute the slowdown to the new separator helper and shows no clear benefit from limiting math-library threads. No persistent threading setting was changed. Timing varied between runs while the game was running; the precise cause of that variation remains unverified.

Profiling five repetitions of a difficult saved marker frame put about one third of measured processing time in polynomial header batch scoring. Further optimization must retain candidate comparison, background clipping, scalar boundary checks and custom hooks. No speculative performance change was integrated in this pass.

## Rejected alternatives

`OCR_RESIZE_COMPARISON.md` records the native/nearest/bicubic comparisons for both installed neural models. All preparations read the 16 manual coordinate triples correctly after correcting an old full-desktop crop. Results on difficult live frames varied, with no consistent numerical advantage from enlargement. Both neural models still produced numerical mistakes on some difficult frames.

The broader physical-label prototype added 16 candidate acceptances and had 32/32 neural coordinate agreements, but a synthetic 95% R + 5% P header transition manufactured a false Root label. It remains excluded. The final change cannot repair any anchor letter and rejects that saved counterexample.

## Evidence and continuation

Evidence root: `D:\Navpoint-background-20260909`. Key files: `header-separator-validation.json`, `header-separator.patch`, `before-header-separators/overlay_reader.py`, `review-physical-header/final_review.py`, and the resize comparison data. Source hashes are recorded in the validation JSON and `header-separator-closeout.json`.

The user's broader OCR goal remains open. The pending requirement clarification is whether minimum 1 FPS during recovery refers to attempts or newly verified positions. Current evidence distinguishes these explicitly. No cached-label or inferred-position recovery has been implemented. Do not repeat the completed console probes or stationary-capture requests as if they were pending.
