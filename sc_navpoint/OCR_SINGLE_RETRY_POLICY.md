# Per-image retry policy — 10 September 2026

User instruction: "If one fails, just do reverification once, then if second failure, drop it an move on. Never retry one image more than once."

Each captured image now receives an initial read and **at most one recovery attempt**. The original failure selects brightness recovery or header recovery. Brightness failure can no longer trigger an additional header attempt on the same image. A failed recovery is discarded; the next polling cycle acquires a fresh screenshot. Existing multi-capture mark attempts also acquire a fresh screenshot each time. A scanner rejection ends that image immediately, without retrying the same deterministic validation.

This cap applies to dispatch-level reading/recovery attempts. Glyph candidate comparisons, alignment fitting and the checks inside one recovery method remain parts of that recognition attempt. No thresholds, coordinate safeguards or polling cadence changed. A newly captured image with identical pixels is still a fresh capture; an old image is not recycled.

## Verification

- Full skill suite: **1,016 passed in 43.36 seconds**.
- Regression tests: two cases failed before the fix because brightness failure could trigger a third attempt and incorrectly succeed under the new policy. They now pass. Another case verifies a failed header recovery ends the image and the next capture can succeed using a different frame object.
- Real capture dispatcher replay: **120 images**, including all **117** images previously reaching the brightness-plus-header chain in the 1,268-frame replay, plus three control cases.
- Maximum dispatch read calls per image: **2**. Maximum recovery calls: **1**.
- Previously accepted frames discarded under the new cap: **13**. No new acceptances; retained accepted coordinates matched. These losses are the measured cost of moving on instead of spending a third attempt. This is an affected-case replay, not a new whole-corpus or live-throughput benchmark.
- Independent review found no blocker for the maximum-one-retry rule. Whitespace check passed.

`main.py` is the runtime change. The scratch `live_probe.py` helper now matches its policy so future diagnostic replays do not silently use a third attempt. Their previous versions are preserved in `D:/Navpoint-background-20260909/before-single-retry`. The reader implementation is unchanged. No installed-copy deployment occurred.

The user still wants four freshly verified positions per second normally and at least one per second during recovery, subject to this retry cap. The new cap does not prove that rate on difficult backgrounds; actual gaps between fresh verified positions remain the measure. Earlier acceptance and timing results describe their recorded source revisions and must not be relabelled as results of this policy.

Evidence: `single-retry-validation.json`, `single_retry_validation.py`, `single-retry.patch`, and `tests/test_brightness_capture_join.py`.
