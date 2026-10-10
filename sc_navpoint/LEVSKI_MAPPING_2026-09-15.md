# Levski mapping correction

The extracted localization catalog contains `Delamar_Levski=Levski` (line 5605),
but the runtime catalog previously contained only Stanton/Pyro frames. The live
2026-09-15 23:03:25 and 23:03:39 captures independently read `levski_all-001` in
the row between the ship and SolarSystem. The extracted asset index contains
`Data/ObjectContainers/PU/loc/flagship/nyx/levski/levski_all.socpak`.

Added that exact observed alias as a Nyx local site, labelled Levski. The existing
site path saves local coordinates and frame identity, without Solar/Root or ship
coordinates. Other unobserved Nyx names and guessed numeric suffixes remain
unsupported. Labels alone are not authoritative coordinate-frame identities.
An extraction rebuild must preserve this explicit, observed alias.

`unknown_zone_name` now says the location's coordinate frame is not supported and
needs a NavPoint mapping update. It no longer advises changing scenery/retrying.

Validation:
- Three new tests failed before the fix; 1,264 tests pass afterward (36.25 s).
- Tests cover the recorded rows through frame selection, scanner, actual database
  save, readable label, matching-frame distance, no cross-frame match, corrupted
  local coordinates with valid Root data, unknown aliases and failure messaging.
- One actual refused screenshot, `2026-09-15_230551_gate.png`, was inspected and
  replayed through V8 once. The returned Levski local coordinates match the image:
  1283.67 m, 1805.28 m, 2070.15 m. No game input or live waypoint save was issued.
- This fixes recognition/saving, not a measured Levski camera transform. Local
  site direction uses the existing site path and still needs a live alignment
  check before treating this as a validated Levski return-flight result.

Deploy `frame_names.json` and `main.py` from source to release and installed skill;
restart Wingman to reload the catalog and messages. Settings and saves preserved.

## Site direction correction after the live 180-degree error

The site branch bypassed planetary calibration and used the legacy camera basis.
Levski's local axes are tilted relative to SolarSystem, so neither that basis nor
a simple 180-degree yaw correction is sufficient.

`site_rotation.py` measures a proper rigid 3D transform from simultaneous site
and SolarSystem positions. The final fifth of samples is reserved for prediction
checks. Fits require observable motion in at least two directions, at least 12
samples, estimated angular uncertainty below one degree, and residuals no greater
than the existing user-selected 50 metres. Root/Solar agreement remains required.
It samples existing captures; there is no extra OCR or fixed 30-second wait.

The shared reader learns site orientation during idle/background captures and
navigation. Fits are transient, scoped to site plus SolarSystem session, and
reset after a capture gap over 30 seconds or a reversed clock. Each new position
pair must agree with the transform before direction is supplied. Stationary
repeats do not erase the movement used to establish orientation. Local distance
and waypoint saving continue without a calibrated direction.

Validation:

- Regression reproduced the old site's confident direction without calibration.
- 44 focused checks pass; the complete skill suite passes 1,279 tests (54.70 s).
- Replay of 75 distinct-timestamp Levski position pairs: training maximum error
  0.184 m, reserved prediction maximum error 0.146 m. Evidence is in
  `D:/Navpoint-background-20260909/live-v211-20260915-224128/site-calibration-replay.json`.
- Synthetic tilted frames verify yaw, pitch, roll, behind-camera targets,
  malformed transforms, stale positions, degenerate motion, session changes,
  bad fresh pairs, and the reader/scanner boundary.

After installation, restart Wingman. A new site calibration needs movement in
more than one direction (for example, forward then sideways); waiting stationary
cannot establish the tilt. Live Levski dot alignment remains to be confirmed.
