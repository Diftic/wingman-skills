# OCR resize comparison — 10 September 2026

The production reader uses native pixels. Enlarged diagnostic illustrations are for inspection and are not its input. PP-OCRv6 separately resizes every row internally to48 pixels high using OpenCV interpolation. Thus native input means no extra external enlargement, not a model with no internal resizing.

Three external preparations were compared: native input,4x nearest-neighbour, and4x bicubic. Both installed models (small and medium) were tested on16 manually transcribed coordinate rows plus70 recent diagnostic rows. The recent rows consist of23 paired changing-view frames,6 paired marker-obstructed frames, and6 paired dark-control frames. Most difficult live rows have no independent ground truth.

## Corrected manual-reference results

| Model | Input preparation | Correct coordinate triples | Exact complete lines |
| --- | --- | ---: | ---: |
| Medium | Native |16/16|11/16|
| Medium |4x nearest|16/16|15/16|
| Medium |4x bicubic|16/16|7/16|
| Small | Native |16/16|3/16|
| Small |4x nearest|16/16|8/16|
| Small |4x bicubic|16/16|7/16|

Complete-line matching normalizes runs of whitespace but does not invent missing spaces or punctuation. These16 rows are a small existing reference set, not broad accuracy evidence. The initial medium run mistakenly included full-desktop width in four older reference rows. Its manual summary is invalid and explicitly marked superseded; use neural-resize-medium-manual-corrected.json. All medium live groups used proper ROI crops and remain valid.

## Recent difficult frames

On23 changing-view frame pairs, medium-model numeric disagreement between Root/Solar occurred on3 native,5 nearest,3 bicubic pairs. Small-model disagreement occurred on4,5,4 respectively. On6 fixed marker pairs the corresponding counts were medium1/0/3 and small0/0/0. Both models matched the available native references on the clear control. Pair agreement is not ground truth: both rows or models can make the same error.

No resize method had a clear numerical advantage across these samples. Additional enlargement is not assumed beneficial, and smoothing is not promoted to the native reader. Corrected medium inference typically took0.45–0.55 seconds per row; small took0.14–0.16 seconds. Two small-model rows appear feasible inside a recovery interval, but these are isolated recognition timings and do not demonstrate end-to-end4 FPS. Neither model's numerical text was connected to navigation.

## Other bounded experiments

channel_probe.py tested red,green,blue isolation on three saved marker-obstructed frames. None yielded a valid position. neural_header_probe.py tried label-only neural proposals with fresh native digits and physical pixel checks. Neural label spelling was itself unreliable in the marker case; the tested neural variants added no validated position.

physical_header_probe.py then used the fixed label grammar and pixel compatibility directly. It gained16 of225 saved refusals, and an independent neural check agreed on all32 corresponding native coordinate tails. However, independent review demonstrated a rounded8-bit mixture of95%R and5%P over a smooth background that the new rule falsely promoted to Root. The old reader refused that particular case. The broad physical-letter fallback remains a rejected diagnostic prototype; neural agreement does not overcome this counterexample.

The reviewed replacement in separator_header_probe.py permits only a missing space between otherwise fully decoded label words. It refuses any candidate if a nonblank glyph can explain the pixels, requires the original best candidate to be blank, and leaves every coordinate character unchanged. Its full integration and validation are recorded separately in OCR_HEADER_SEPARATOR_VALIDATION.md in the skill directory. No cached system identity or neural coordinate recovery was introduced.

Files: neural_resize_benchmark.py; neural-resize-medium.json (live groups only); neural-resize-medium-manual-corrected.json; neural-resize-small.json; channel_probe.py; neural-header-probe.json; physical-header-probe.json; physical-header-neural-comparison.json; separator-header-probe.json; review-physical-header/.
