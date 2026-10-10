# Open-space Root guidance candidate

Normal navigation now draws direction for an active-frame reader capture that
positively identifies space. Current and saved SolarSystem identities must be
present and equal, and both Root/Solar coordinate pairs must agree. Malformed,
stale, nonfinite, cross-frame and mismatched coarse-target inputs withhold guidance.
The endpoints are serialized Root coordinates, never nested ship coordinates or
the flattened summary fields. Local container tracking remains disabled.

The camera basis is `planet_rotation.local_camera_basis(camdir, 0)`, the same
Rz(yaw) Ry(roll) Rx(pitch) basis exercised by the Ita flight, with no planetary
rotation. The older experimental `system_camdir_orientation` uses a different
combined pitch/roll convention and is not promoted by this change. Legacy system
guidance and the development-only switch retain their existing gates.

The ring, tool result and browser use one calculation. Distance remains visible
with SLOW DOWN. The ring retains its last direction and original capture age on
failed reads, displays ERROR after eight consecutive failures, and clears retention
when the target or coordinate session changes. Missing camera angles still permit
distance; the browser never substitutes a centered dot for a missing direction.

This navigates to a fixed saved point in space. It does not track a moving ship,
transform a saved planetary target into space. Confirmed matching space reads
now use the same arrival policy as surface navigation: two valid readings at or
below the configured stop distance (250 meters by default) announce "Arrived."
and stop navigation. The 1,000-meter approach notice is shared as well. Coarse,
stale, mismatched or invalid space positions cannot trigger arrival. Missing
camera angles do not block arrival when position remains valid.

## Verification

- Arrival follow-up: 82 focused tests passed in 1.79 seconds. New arrival tests
  failed before the change, then passed for two readings, the inclusive 250-meter
  boundary, zero distance, leaving/re-entering the radius, OCR failure between
  valid readings, invalid/coarse/stale/session-mismatched coordinates, disabled
  auto-stop, short approach/arrival speech, clearing navigation and keeping saves.
- New regressions failed before implementation: missing normal space direction,
  distance/retention and browser guidance.
- 1,242 tests passed in 26.72 seconds, including combined pitch/roll, frame and
  session rejection, real database-to-ring/API/tool integration, eight failed
  reads and recovery, and JavaScript execution of the browser navigation panel.
- Python 3.11 syntax and source/stage/installed hashes checked during installation.
- A fresh live input comparison was attempted, but the running NavPoint endpoint
  refused the connection. No live alignment or return-flight result is claimed.

## Next live check

Start/restart Wingman, activate NavPoint and navigate to Crash Site One. Center the
cockpit view and compare the dot with the known target; check yaw, pitch and roll
with the target off-center. Space needs a fresh accepted reading, not the 30-second
planet fit. Then approach the fixed point using the distance and check the
arrival announcement inside 250 meters. Auto-stop ends navigation, not ship motion.
Saved waypoint data and settings are preserved.
