# OCR recovery allocation optimization — 10 September 2026

The header background fitter now reuses its private temporary array for the predicted image and squared residual. It avoids several large allocations without changing the candidate bank, coordinate parser, guards, recovery eligibility, capture method or cadence. Native-resolution pixels remain the input. No neural model or new dependency was added. Installed copies are unchanged.

## Verification

- Full skill suite: **1,013 passed in 38.83 seconds**.
- Complete replay: **1,268 frames, 1,046 accepted**. Acceptance decisions changed: **0**. Payloads changed: **0**, compared with the preceding header-space implementation.
- Independent reviewer found no blocker. Its 36 score-array comparisons covered float16/32/64, uint8, contiguous/Fortran/reversed layouts and read-only inputs. Inputs and template banks stayed unchanged; rankings matched.
- The scratch prototype compared 528 score arrays and 25 full-decode pairs. Maximum score difference was 2.84e-14: numerical equivalence, not bitwise identity. Existing scalar checks around refusal thresholds and near ties remain in place.
- Paired selected-frame experiment: current/candidate median 884/707 ms, p95 1,070/945 ms, maximum 1,147/1,128 ms. This is about a 20% median reduction on five selected saved frames repeated five times; it is not a universal throughput guarantee.

Full replay timing:

```json
{
  "ordinary": {
    "frames": 1019,
    "seconds_median_p95_max": [
      0.15038690000073984,
      0.21350628999989565,
      0.33330600000044797
    ]
  },
  "recovery": {
    "frames": 249,
    "seconds_median_p95_max": [
      0.3976762000002054,
      0.7136180199995579,
      0.943103899999187
    ]
  }
}
```

## Unobstructed live checks

After the user moved the desktop window, the previous reader captured 60/60 accepted frames at 3.96 accepted reads/second, with one stable coordinate triple. Median 152 ms, p95 245 ms, maximum 406 ms; maximum accepted-result gap 320 ms. Evidence: `live-runtime-20260910-214443`. Replay agreed on all 60 frames. The representative native image visibly shows readable, unobstructed coordinate rows.

Final current-source capture:

```json
{
  "folder": "D:\\Navpoint-background-20260909\\live-runtime-20260910-215506",
  "accepted": 60,
  "frames": 60,
  "attempts_per_second": 4.01299828873054,
  "accepted_per_second": 4.01299828873054,
  "seconds_median_p95_max": [
    0.15033339999990858,
    0.19707311000056507,
    0.25683919999937643
  ],
  "max_accepted_completion_gap": 0.3572167000002082,
  "unique_positions": 1
}
```

These runs exercise actual capture, reader, parser, scanner and diagnostic writes with framework/UI output stubbed. They do not measure the entire installed Wingman application. Reading agreement and coordinate stability are evidence for these samples, not whole-corpus ground truth.

The earlier `live-runtime-20260910-212442` run had a desktop window covering coordinate text and is retained only as obstruction/rejection evidence. The user's readiness request has been fulfilled; do not ask them again as though it were pending.

## Remaining work

The normal 4 FPS target has support in clear live views. A universal minimum 1 FPS recovery rate is not established: the selected paired experiment still exceeded one second, and fully obscured coordinates cannot produce freshly verified values at any rate. Clarification of attempts versus newly verified positions remains unanswered. The broad OCR goal remains open.

Read `OCR_HEADER_SEPARATOR_VALIDATION.md` for the preceding three additional recoveries and rejected broad letter reconstruction. Read `OCR_RESIZE_COMPARISON.md` for the neural resize comparison. Original frozen reports and baselines are retained. Current evidence: `header-inplace-validation.json`, `header-inplace-probe.json`, `header-inplace.patch`, and `review-physical-header/allocation_review.py` under `D:/Navpoint-background-20260909`.
