# Survey mapping integration and next live test

## User workflow and scope

Ship navigation only. Save multiple independently named unmarked mining spots, leave to unload/refine, and return to the selected spot. Support scouting sweeps followed by mining runs. Sharing/export through Discord or another channel is a low-priority future item. No on-foot/interior navigation requirement.

Planet/moon and mining-site coordinates must retain their own frame identities. Treat sites as potentially moving/rotating even if currently stationary. Friendly names never replace matching keys. Saved planetary/site bookmarks contain local XYZ and frame identity, not SolarSystem/Root coordinates. A name match is not an established transform between frames.

## Implemented in source

- Runtime name catalog: 178 frame/name entries derived from installed LIVE localization, with source keys/lines and provenance. Full 3,052-entry master reference remains separate research data; it includes aliases, sublocations and historical entries, so it is not directly loaded as a list of trusted frames.
- Pyro moon support, including the surveyed Vatra and Vuur forms.
- Mining-site local capture, payload validation and save path, including surveyed Pyro and Stanton forms. Existing local schema is reused; `planet_id` remains a compatibility field containing the canonical local frame ID even for site payloads. `active_frame=site` distinguishes these from planets.
- Named bookmarks retain raw matching IDs and gain readable display labels in save responses and the HUD. Two independent site bookmarks tested; exact local coordinates persist without Solar/Root fallback.
- Fixed OOC-prefix O/0/Q normalization only when the resulting complete body token matches a catalog entry. Raw OCR strings remain available. Coordinate digits and unknown names are not repaired.
- Site ring/HUD guidance uses the same local-camera calculation as the planetary path; synthetic geometry passes, but a site-specific live direction test remains necessary.
- Package manifests include the name module/catalog.

## Verification

New tests reproduced seven failures before implementation. Bookmark label test separately failed before the display update. Focused tests: 9 passed. Full NavPoint suite: 1,170 passed in 31.56 seconds. This does not establish actual OCR truth rate or live return accuracy.

## Remaining gaps / live protocol

### Ita planetary direction correction (later on September 14)

Pilot confirmed Mining test one returned to the intended deposit, but the dot was incorrect. Paired local/SolarSystem rows explain the error as a camera-to-rotating-planet transform. The candidate now estimates that transform in a bounded background fit using NumPy only; it performs no additional OCR or retry. Bookmark XYZ, distance, frame IDs and database remain local-only. Solar/Root values are transient calibration inputs, never copied into saved planetary positions.

The new branch is restricted to active_frame=planet (planets and moons). System/Root space branches, their camera conventions, calibration gates and mining-site behavior are unchanged. A planetary dot requires a matching valid rotation; missing or inconsistent calibration withholds direction while position/distance remain available. Fit history is scoped to local frame and SolarSystem session, reset on a recognized frame change or a long capture gap, bounded to 180 samples, and never persisted. Short OCR refusals do not replay frames or erase all calibration history. Each fresh coordinate pair must agree with the model before it can supply direction.

Verification: 1,176 tests passed. A production-code replay fit only the first 150 seconds of existing OCR; errors for the initial heading and two later intervals were 0.73, 1.02 and 2.34 degrees. Calibration became available at the 45-second replay checkpoint; this is not a guaranteed warm-up time. Fit calls measured roughly 12–20 ms on that replay and run outside the OCR loop. The live ring, roll response, other planets and frozen Wingman still need validation. Planetary spin model assumes a stable origin and Z-axis rotation; checks refuse inconsistent/unobservable fits rather than extending this assumption to arbitrary site containers.

- Installed Wingman has not been updated or tested in its frozen runtime. Source tests alone do not validate installed dependency loading.
- Saved-frame re-entry is required before local guidance. Automatic guidance across different moving frames is not implemented; existing rejection remains. For the first round trip, manually return to the planet/site region using the game map, then test precise bookmark guidance within that frame.
- Camera orientation in a mining-site frame needs a pilot-supervised direction check; do not call it live-validated based on planet tests.
- Lagrange/gateway frame tokens from the survey are recorded but are not automatically authorized by the new planet/mining catalog. Unknown frame identities still refuse.
- Nyx live alias validation remains limited to previous observations; no new unsupported Nyx planet access inferred.
- Prefix confusion handling and new Pyro/site recognition need fresh live samples; no old image may exceed the user's one-reverification limit.

Live test: save two named ore spots in one local frame with full precision; verify separate database readback; leave for refinery/unload; manually return to the saved frame; select each spot in turn and check direction/distance against the pilot's physical reference. Retain last good reading with age, no recovery/retries, and do not count held positions as fresh reads. Report inability to read or mismatched frames explicitly.
