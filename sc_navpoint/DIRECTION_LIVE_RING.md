# Live return-ring calibration — 10 September 2026

**Superseding state:** The pilot recentered and flew part of the return leg, reducing distance from about 25.57 km to 22.9 km. Arrival was not tested. The final five-minute recording `direction-ring-20260910-230011` contains 1,198 frames: 671 accepted positions, 668 available directions, and 527 position failures (44%). During frames 640–879, only 106/240 positions were accepted (56% failure). The user paused navigation testing and approved replacing the OCR approach with learned recognition and a possible trained specialist. The ring is stopped. No pilot action is pending; the earlier requests below are historical.

Latest state: the pilot confirmed forward flight, stopped, then turned toward the saved reference and confirmed the bubble was centered. Yaw error decreased from -179.6 to +1.5 degrees. The subsequent pitch check exposed an OCR failure with a bright cockpit edge behind the coordinate text. The pilot has been asked to lower the nose and recenter before the return leg. Return flight is still pending; ordinary guidance remains disabled.

## Forward evidence

`D:/Navpoint-background-20260909/live-runtime-20260910-224701` contains 100 fresh captures, 82 accepted. Across 23 qualifying movement windows, corrected forward-direction error was median 0.5165 degrees, p95 2.1855 degrees, maximum 2.6240 degrees. Longest verification gap was 0.7497 seconds. This is stronger evidence than the earlier drift-dominated recordings; it does not validate every orientation, pitch or roll.

## Integration fault found live and corrected

The first actual ring run (`direction-ring-20260910-224953`) displayed NO BEARING even with accepted positions. `NavPointDatabase.navpoint_to_dict` deliberately leaves the coordinate stack out of its HUD summary. The new direction consumer therefore received no saved Root coordinates. Earlier direction tests constructed complete target dictionaries and missed this boundary.

`SC_NavPoint._sync_ring` now attaches the saved stack to its own target dictionary before calculating and tracing the arrow. The HUD summary remains compact. A regression test saves a real database waypoint, calls `_sync_ring`, and checks both the rendered direction and trace coordinates. It failed with a missing arrow before the fix and passed afterward.

- Focused tests: 28 passed in 0.24 seconds.
- Complete suite: 1,044 passed in 29.28 seconds.
- Diff whitespace check passed.
- The scratch live harness now calls actual `_sync_ring`, rather than reconstructing that connection.
- Corrected run `direction-ring-20260910-225547` initially reports (-179.6, -1.6) degrees and distance about 25,646 metres. Actual screenshot `direction-ring-fixed-visible.png` shows a red bubble at the left edge and CALIBRATION text.

No installed Wingman code or waypoint database was changed. The source reader still allows at most one recovery per image. The reference is saved in an isolated calibration database, not the installed skill database. Successful direction in this controlled open-space test must not be presented as validation of rotating-body or nested-container guidance.

## Actual turn and pitch check

The corrected ring run finished with 957 frames, 850 accepted positions and 845 available directions. The difference includes accepted positions with unreadable camera angles. Pilot explicitly replied `centered` after the left turn. Displayed Root distance was about 25,605 m at alignment.

Pitching upward from approximately -1 to +14 degrees moved the calculated vertical bubble from -1.4 to -16.4 degrees. At +17/+18 degrees, readable frames placed it around -19.4/-20.4 degrees. There is no 20-degree cutoff in the ring: the pilot's observed disappearance coincided with read failures. Original images show a bright cockpit edge moving behind the digits.

A separate fresh one-frame diagnostic `live-20260910-230109` at CamDir (30,0,-24) refused 12 cells in each of the SolarSystem and Root rows; no valid coordinate payload was produced. The original screenshot and detailed cell-level refusal output are saved there. This frame was processed once using the normal maximum-one-retry policy. No digit guard was weakened to draw an arrow over the failing view.

The pilot identified the white streak as sunlight reflected in the cockpit roof beam when pitching up. This identifies the scene feature; failure of the local smooth-background model at the sharp reflection remains the technical explanation to investigate. The pilot subsequently recentered the bubble and has been asked to perform a 15-second forward return leg and stop.

The dot and inner boundary both disappear on unavailable direction because the renderer switches to its idle face. A later valid read restores the live face. This is distinct from the whole overlay closing when a bounded recording ends.

Read-only peer review found no blocker in the database-to-ring repair; reviewed main.py SHA-256 `4fa10b3557f561980bd597e26a887c16e8c1d1dde9bd467cba0e5d5ad32cb0c5`. Full source validation remains 1,044 passing tests; no further runtime source change was made after that check.
