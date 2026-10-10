# Current OCR target: 20 correct fresh complete reads per rolling 10 seconds

The user clarified on 13 September 2026 that brief rejection streaks are an
expected consequence of changing backgrounds and should not automatically fail
the target. This supersedes the strict two-reads-in-every-one-second interpretation.

Count at least 20 independently checked correct complete reads in each rolling
10-second observation window. Track rejection streak frequency, duration and
failed-frame counts separately, alongside the maximum verified-read gap. No new
hard gap limit has been specified; do not invent one or reject the whole cadence
test solely because a brief gap exceeds one second.

Accepted-but-wrong readings remain an accuracy defect and never count toward 20.
Unchecked proposals do not count as independently verified successes. Preserve
one attempt per fresh capture, no retries/recovery/old-frame queues, and holding
the last successful display with its age. Held values never count as fresh or
trigger new arrival events. New captures of unchanged coordinates can count.

The 6.4325-second V7 sample is insufficient to validate a 10-second window.
It contains 18 independently correct full readings and one checked wrong name;
its short gap is now diagnostic rather than an automatic cadence failure.
Next live validation must last longer than ten seconds. A sample-level cadence
pass still does not prove every scene, acceptable wrong-accept rate or installed
Wingman behavior. Do not silently promote an unvalidated recognizer.

The scratch cadence evaluator has nine passing tests, including tolerated short
streaks, rejection of an empty 10-second window despite a good whole-run average,
and exclusion of wrong/unchecked/refused/retried/reused captures.

---

## Earlier criteria and evidence (superseded where inconsistent)

# Current OCR requirement: two correct fresh complete reads per second

Set by the user on 13 September 2026. This supersedes the earlier one-per-second
recovery target and four-per-second preference in the historical material below.

- Count only successful readings from new captures whose complete required
  camera, coordinate digits, units and frame identifiers have been independently
  checked against the source image. Parser acceptance alone is not verification.
- Report both average verified throughput and gaps. The conservative sample
  audit checks every complete one-second window, including observation boundaries.
  Do not discard warm-up or failure intervals to produce a passing number.
- One attempt per fresh capture. No recovery, retries or queued old frames.
- Keep the last successful display on failures, with its age. Held values never
  count as new reads and never trigger a new arrival event.
- Same coordinates from a genuinely new capture can count. Training-set results,
  synthetic tests and unchecked proposals do not establish live accuracy.
- A short successful scene does not establish whole-feature readiness. Test
  movement, changing view/background and coordinate-frame transitions separately.

Current evidence contradicts completion: V6 and PP-OCRv6 Small both have confirmed
wrong accepted digits; Small also misses the throughput target. V7 is a separate
training experiment, not a deployed or validated replacement.

Current evidence report:
`D:\Navpoint-background-20260909\OCR_V6_LIVE_VALIDATION_2026-09-13.md`.
Cadence evaluator: `D:\Navpoint-background-20260909\verified_cadence.py`.
Six focused tests passed for its rate, burst-gap, wrong/unchecked output, refusal,
retry/queued-frame and short-observation handling.

---

## Historical requirement and evidence (superseded)

# Verified-position rate requirement — clarified 10 September 2026

The user answered **"One verified"**: the recovery minimum is one position verified from a fresh captured frame per second. A new frame may confirm identical coordinates. Attempts, cached output, interpolated positions and replaying an old frame do not count as fresh verifications. Optimal normal rate remains four fresh verifications per second.

Evaluate the maximum gap between successful verification completions, including observed startup and trailing periods. Mean accepted rate and per-attempt processing duration are insufficient. A bounded sample passing this check does not guarantee performance across every scene or load.

## Existing live evidence

| Sample | Verified frames | Longest observed interval without verification | Requirement |
| --- | ---: | ---: | --- |
| Stationary ship, looking around; earlier reader | 40/60 | 2.258 s | Fail |
| Fixed view, bright marker; earlier reader | 0/60 | 23.655 s | Fail |
| Clear fixed view; earlier reader | 60/60 | 0.300 s | Pass for sample |
| Unobstructed view, before allocation optimization | 60/60 | 0.406 s | Pass for sample |
| Unobstructed view, final optimized reader | 60/60 | 0.357 s | Pass for sample |

The first three samples used an earlier reader; the last sample used the final optimized reader. They are not paired live scene comparisons. Their source hashes and exact numbers are retained in `verified-position-gap-audit.json`. The allocation optimization preserves all 1,268 saved-frame decisions and payloads; it reduces computation but does not by itself repair unreadable scenes. The preceding separator change did not recover any of the fixed-marker sample's frames.

**The overall recovery requirement is not met.** The 943 ms maximum recovery-attempt duration from the latest offline replay is processing evidence only. It does not establish a verified position every second. Clear live views passed the sample-level gap check; the historical moving-view and fixed-marker cases demonstrate the outstanding availability problem.

## Continuation

Measure fresh accepted-result gaps in further live recovery tests and treat zero-result periods as failures. Further work must improve recovery of valid current coordinate evidence, not merely the attempt cadence. Preserve semantic anchors, digit/sign/unit checks and ambiguity rejection. Where the captured pixels do not contain enough evidence, report the read unavailable; the target does not authorize inventing a current position.

This clarification supersedes all earlier pending attempts-versus-verified-positions questions. Do not ask that question again. No production source, installed copy, or recognition threshold changed as part of recording it.
