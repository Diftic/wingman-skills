# September 15: live Ita checks and held-dot display fix

## Live checks before the fix

Pilot confirmed Glacos target identity, distance and direction using visible deposits/radar. Astler also passed distance, alignment, yaw, pitch and roll checks. Scope is this Ita session. Independent 10 m ground-truth accuracy, actual arrival, refinery/frame-reentry, other planets/sites and installed Wingman compatibility remain unverified.

All seven waypoints in six standalone test databases and their target files were removed on user request. Current navigation ring is stopped. Recordings and check records remain; installed Wingman files/data were untouched.

## Display fix implemented in development source

The Astler recording contained 260 transitions from a visible dot to no dot, all on accepted positions lacking planetary rotation calibration. The renderer previously discarded the dot in this situation.

RingOverlay now supports explicit, scoped display retention for local planet/site navigation. It caches only a valid direction and its original capture timestamp. A failed read, missing calibration or aged reading retains that last dot and shows its held age. ERROR fades in within the upper circle, below the top marker, using the existing fade/dwell behavior. The error status is separate from the bottom message. Fresh valid direction replaces the display; cached display values never enter coordinates, saves, spoken guidance or arrival logic.

Target/frame changes, stopping navigation, unsupported frames, invalid XYZ and coincident positions clear retention. Space behavior remains on the existing path. Core ring integration and all three current standalone test runners use this behavior; no runner was restarted after cleanup.

## Verification

- Final full skill suite: 1,184 passed in 27.15 seconds, using development Python with the candidate bundled OpenCV and writable temporary directory.
- New regression tests first reproduced missing behavior. Runtime test uses the real ring path; renderer test verifies ERROR changes only the upper image region.
- Final source replay: 1,446 cached records; 769 valid directions unchanged; 527 held display updates; zero disappearances after the first valid direction. No OCR reruns and no waypoints restored.
- Inside-circle preview rendered and visually inspected. No live game validation of this display change yet.

## Package status and next work

The user authorized a clean replacement of the old installed skill. The prepared runtime package and installed copy now include the display fix and the v3 compatibility migration. The old installation, database and active profiles were backed up before replacement. The local installed defaults enable the tested specialist reader; the generic source default remains opt-in. No commit or release-directory regeneration occurred.

Wingman v3 compatibility: declared `api_version: 3` and package version in the manifest; migrated navigation announcements to the runtime threading, TTS and conversation facades. The async speech helper preserves queued speech (`interrupt=False`). The strict v3 arrival collaborator reproduced six failures before migration; the final complete suite passed all 1,184 tests in 34.19 seconds.

Actual installed Wingman startup accepted NavPoint (21 eligible skills; NavPoint absent from the legacy list). Enabling it for Alyssa succeeded: the runtime reported loaded and discoverable, and the local API confirmed enabled with eight tool definitions. All 85 installed package files match the refreshed staged manifest. Navigation remains stopped. On-demand `prepare`, OCR model loading and an in-game command through the installed app still need live verification; import/registration success does not establish those.

Deferred user requirements: adjustable capture rectangle for different display layouts; smaller top-five-line capture for this tested view. No crop change made; deeper hierarchies and text scaling need validation.

Meridian identified at user request: community behind StarMap/EUREKA and Project Jericho. User only requested its Discord link, supplied in conversation. No integration work authorized or performed.

## First-release settings cleanup

At the user's request, removed the obsolete polling interval and the open-space calibration experiment from source, staged and installed settings. The current profiles contained no saved copies to migrate. Capture remains continuous; the runtime cannot enable uncalibrated space direction through settings. Internal development harness hooks remain available. Focused regression: 69 passed. Wingman reloaded NavPoint and confirms enabled with five settings; both removed IDs absent. Installation manifest refreshed after this change. The 1184-test full-suite result above predates this settings-only follow-up.

# Follow-up: distance and consecutive failures

The installed runtime did not pass a distance to the ring. It now calculates
range for matching local frames independently of camera calibration and draws
it on a fixed line above the bottom status/advisory. SLOW DOWN and the distance
can both remain visible. Status fades do not fade the distance.

Display retention keeps the last valid dot and its accompanying distance on
missed direction updates, with the original HELD age. ERROR now requires eight
consecutive unavailable direction updates; a valid update, target/frame change,
or clear resets the count. This is eight updates, approximately one second at
8 Hz, not a wall-clock guarantee. The existing error fade remains in place.

Regression suite: 1,197 passed in 30.00 seconds. Pixel checks verify that distance
is above the warning, does not overlap it, and remains when the warning fades.
State checks cover failure 7 versus 8, recovery, target changes, no calibration,
held distance and invalid/stale/mismatched coordinates. Preview inspected at
`D:/Navpoint-background-20260909/wayfinder-distance-preview.png`.

The live reader is V8 (installed specialist flag enabled). Recent log examples
include malformed facing and coordinate text, not only foreground capture
failures. Live state also showed a fresh position without planet_rotation;
that is an unavailable fresh direction even when OCR returns a position.
This display change does not repair those recognition/calibration failures.
Source, staged package and installed runtime are updated; Wingman must restart
to load the changed Python modules. No Core files or saved waypoints changed.
