# First direction-flight recording — 10 September 2026

User reported being in space. We requested a stopped ship and centered cockpit view, captured a baseline, then requested about ten seconds of straight forward flight followed by a stop. A completion/stop reply has not yet arrived. Interpretation of deliberate flight therefore remains provisional.

- Baseline `224155`: 23/24 verified. Camera remained (0,0,156); reported Root coordinates moved approximately 7.6/3.7/19.6 m by axis. Do not call this perfectly stationary.
- First flight recording `224238`: 145/160 verified; longest verification gap 0.777 s. Motion above the analyzer threshold began near the end, yielding one qualifying one-second window. Corrected forward error 5.49 degrees; legacy formula 87.86 degrees.
- Follow-up `224424`: 47/120 verified; longest verification gap 2.256 s. Six qualifying windows; corrected error median 3.73 degrees and maximum 4.31 degrees.
- Seven windows combined: corrected median/p95/max [3.7485022866673203, 5.13848397937377, 5.493920517348547]; legacy [88.75014489931391, 88.8331441672655, 88.84720063794263] degrees.

The corrected forward model fits measured travel far better than the legacy model in these samples. The residual error may include pre-existing drift, which is visible in the baseline. No drift correction, calibration fit, or flag change was applied. Straight forward displacement does not validate right/up/roll, and the pilot has not confirmed the requested control sequence yet.

The reference position is stored in `direction-reference-20260910.json`, with original frame and image hash. This is a calibration reference, not a saved waypoint in the installed Wingman database. Original images and full runtime decisions are retained in all three folders under `D:/Navpoint-background-20260909`.

**Next:** Wait for the pilot's completion/stop confirmation. Check yaw/pitch/roll against the known reference before ordinary direction is enabled, then perform the actual save/fly/return skill test. Do not represent this first forward test as a successful return or a universal 1 Hz verification result. No installed copy changed.
