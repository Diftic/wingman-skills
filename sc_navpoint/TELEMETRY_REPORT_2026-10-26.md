# NavPoint without the debug overlay: findings and live telemetry test (2026-10-26)

SC 4.10.2 LIVE, build 12913470. Tested on the user's PC with a Drake Clipper, Wingman not involved.
Background research: `NO_OVERLAY_RESEARCH_2026-10-26.md`. Decoded API schema: `SC_TELEMETRY_API_4.10.2.proto.txt`.
Probe tooling: `telemetry_dev/`.

## Summary

- Star Citizen ships a **local gRPC telemetry stream** (`sc.game.telemetry.v1.GameTelemetryService`). It is
  off by default. One environment variable switches it on, and it then streams at ~17-18 frames/s on
  `127.0.0.1:2942` with no token.
- It gives **ship heading (nose direction, compass convention, same north as the HUD compass), altitude, radar
  altitude, vertical speed and speed**, plus full ship-systems, weapons and player state.
- It gives **no coordinates of any kind**. Position must still come from `/showlocation`.
- So the agreed design holds: a GPS-style fix from `/showlocation` now and then, plus dead reckoning
  from telemetry between fixes. Vehicles and ships only. One of its three open questions is answered.

## How it is switched on (verified)

| Item | Value |
| --- | --- |
| Setting | `GRPC_CLIENT_SERVER_ENABLED=true` (+ `GRPC_CLIENT_SERVER_ADDRESS=127.0.0.1:2942`) |
| How | environment of the RSI Launcher process; the game inherits it (`telemetry_dev/launch_with_telemetry.ps1`) |
| Game.log proof | `Service 'sc.game.telemetry.v1.GameTelemetryService' registered`, `127.0.0.1:2942 [Insecure]` |
| Auth | none needed |
| Rate | ~17-18 frames/s once the player has spawned (none in menus or loading) |
| Client | plain gRPC server stream, any language (`telemetry_dev/probe.py` is a working Python client) |

The setting is undocumented and could change in any patch. Nothing in the game files is modified; it is the
game's own config option. Whether CIG considers it supported for players is unknown.

## What the stream contained (live)

| Area | Fields seen with real values |
| --- | --- |
| Ship identity | `DRAK_Clipper`, entity name, type SPACESHIP |
| Instruments | speed, **heading**, altitude, radar_altitude, vertical speed, atmospheric density, g-meter (up to ~8.6 g), hydrogen fuel, boost reserves |
| Flight state | landing gear and VTOL (RETRACTED → DEPLOYING → DEPLOYED, ~7 s), is_landed |
| Flight settings | coupled, ESP, G-safe, stability, wind compensation, proximity assist (and landing), command behaviour, speed limiter, advanced HUD, course prediction, light amplification; each with enabled + active |
| Power | powerplants, engines, weapons, coolers, life support, sensors, shield generators, shield emitters |
| Annunciators | PWR, WPN, THR, SHLD, COOL, QDRV, RADR, PROX, HIT, MISL (WPN seen OFF → MINOR_ON) |
| Weapons | loadout (`BEHR_LaserCannon_S3`), powered/ready, gimbals locked, countermeasures (36 decoy / 5 noise) |
| Player | on foot → seated, seat name, crew role PILOT, enter-seat event, health, O2, hunger, thirst, body temp, heart rate (~60), gravity, pressure, UEC balance, outside temp, breathable air |

Not seen, probably because they were not triggered: quantum fuel, cruise mode, doors, turret frame,
force feedback.

**Not in the API at all:** position, coordinates, latitude/longitude, zone or body name, camera direction.
Gaps in the field numbering suggest removed or reserved fields; that is speculation.

## Heading: behaviour (verified)

| Test | Result |
| --- | --- |
| Open space, 90° left turn | heading absent the whole time; altitude = FLT_MAX (3.4e38, "no planet") |
| Quantum jump to a planet | heading absent; speed frozen at 814.4 for the jump |
| Planet, from ~50 km altitude | heading, altitude, radar altitude, vertical speed and density all appear |
| Straight flight | steady to ~0.01° |
| 90° left turn in atmosphere | 35.5 → 348 → 307.7 → 305.1 (≈ -90°): 0-360°, clockwise, compass convention |
| Hover vs HUD compass | telemetry 304.28, HUD 304: same north |
| 90° right yaw in a hover, speed 0.0 | 304.28 → 357.7 → 5.8 → 40.52 (+96°): **follows the nose, not the velocity** |

So heading only exists inside a planet's local frame. That is where NavPoint's surface navigation happens.

## What this means for NavPoint (vehicles and ships)

- **Bearing ring and "turn left 30" work without OCR**: target bearing (from position) minus telemetry
  heading. This works while hovering too, because heading is the nose.
- **Dead reckoning between fixes**: horizontal from speed + heading, vertical from altitude directly
  (planet radius + altitude = distance from the planet's centre, with no drift). One integration step
  instead of an accelerometer's two.
- **Fix triggers**: start, every 30-60 s, on request, and on a g-meter spike (collision or hard manoeuvre).
- **Bonus signals**: gear down / is_landed for arrival detection; enter/leave seat events for start and stop
  of tracking.
- **Out of scope / unsolved**: open space (no heading there), walking players (no heading or speed in the
  actor frame).

## Power and warning lights (annunciators)

**Power is on/off only.** `VehiclePowerState` is 9 booleans (powerplants, engines, weapons, coolers, life support,
gravity generators, sensors, shield generators, shield emitters). There is no allocation, capacity, power-triangle
balance, heat or signature anywhere in the API. The stream drops default values, so a missing flag means
`false`: `gravity_generators` never appeared on the Clipper, so it read OFF throughout.

**Annunciators:** 10 lights, each with 6 states (NOMINAL, OFF, MINOR_FLASHING, MINOR_ON, MAJOR_FLASHING,
MAJOR_ON). **The state words mean different things per light**, so each light needs its own translation. For QDRV,
NOMINAL = quantum mode active and OFF = not active. For SHLD, NOMINAL = shields up.

User's reading of the HUD lights (2026-10-26), checked against the recording:

| Light | User's meaning | Recorded | Status |
| --- | --- | --- | --- |
| PWR | power on / off / damaged | NOMINAL throughout | unconfirmed (not triggered) |
| WPN | combat mode active | OFF → MINOR_ON on sitting down; **stayed MINOR_ON in quantum mode** | doubtful: may be "weapons powered, not armed" |
| THR | thrusters on / off / drained (boost drains reserves) | NOMINAL → **MAJOR_ON for the whole quantum jump** → NOMINAL | partly: MAJOR_ON seen as "thrusters unavailable"; drain not tested |
| SHLD | shields on / off / drained | NOMINAL → **OFF on entering quantum mode** → MAJOR_ON → NOMINAL within 1 s on leaving it | fits (MAJOR_ON = down while coming back up) |
| COOL | cooling on / off / insufficient | **OFF throughout**, while the coolers' power flag was true | partly: OFF seems to mean "no cooling problem" |
| QDRV | quantum mode active | OFF → **NOMINAL on entering quantum mode** (22:32:18) → OFF on leaving it (22:34:31) | **confirmed** |
| RADR | (not given; likely radar / scanner) | NOMINAL throughout | unconfirmed |
| PROX | proximity / collision warning | NOMINAL throughout | unconfirmed (not triggered) |
| HIT | taking damage (sometimes buggy in game) | NOMINAL throughout | unconfirmed (not triggered) |
| MISL | missile mode active | NOMINAL throughout | unconfirmed (missile mode not used) |

**Test plan to settle the rest** (one short session, probe recording):

1. Switch combat mode on and off a few times (WPN).
2. Enter and leave missile mode (MISL).
3. Fly close to the ground or a structure until the collision warning shows (PROX).
4. Hold boost until the reserves run out (THR "drained").
5. Power a group down and up again in the power screen (PWR and the 9 power flags; does an off group flip its flag?).
6. Optional: let shields take damage, or bump something (HIT, SHLD drained).

Note the in-game time of each step. Each one is then matched to its frame in `frames.jsonl`.

## Other project: HUD and ship-systems state

The stream is close to complete for a "what is my ship doing" tool. It covers every power group, all
10 annunciators, every flight mode, gear and VTOL, weapons and countermeasures, vitals and UEC, at ~17 Hz, with no
OCR or memory reading. MFD panel *content* is not in the API, but the systems behind the MFDs mostly are.

## Crash during test 1 (not caused by telemetry)

At 22:27:17 the game crashed with 0xC0000005. The dump (`%LOCALAPPDATA%\Star Citizen\Crashes\error.dmp`)
places it in **`nvoglv64.dll`, NVIDIA's Vulkan driver (621.1.0.0)**, reading address 0xFFFFFFFFFFFFFFFF.
Game.log had `VK PSO Cache not valid anymore!` at startup, and the user saw the shaders rebuilding slowly
(~10%). The most likely cause is the shader rebuild in the driver. Nothing points at the telemetry
server. Test 2 ran without problems.

## Full field test, day 1 (2026-10-27, 17:32-19:04)

Ships: Drake Ironclad (plus its Command Module, separated), then Drake Vulture. Start at Lorville (Hurston),
flight over Hurston, Everus Harbor, quantum jumps to Magda and ARC-L1, EVA at ARC-L1. Recording:
`telemetry_dev/frames_2026-10-27.jsonl` (it kept recording an idle Vulture until 22:47: the user fell asleep;
nothing after 19:04 is part of the test). `/showlocation` reads: `showlocation_2026-10-27.jsonl`.

**Player**
- Heart rate is live: 60 → 171.7 bpm sprinting. The HUD turns red at ~170 (user). There is no stamina or
  "exhausted" field. Oxygen, body temperature, health, hunger and thirst did not change while sprinting.
- `uec_balance` = the real wallet (4,107,874, confirmed by the user).
- Gauge scales differ: oxygen 0-1; health, hunger and thirst 0-100. Always use each gauge's `max`.
- EVA (Vulture, ARC-L1): the cabin vented when the door opened. Pressure 1.0 → 0.267 → 0.034 → 0.001,
  breathable true → false, outside temperature 21 °C → −38 (venting artefact) → −0.3. Repressurising took
  ~25 s, and breathable went back to true. Locomotion **flips ON_FOOT↔EVA (and gravity 1↔0) many times per second
  at the door / gravity boundary**, so it needs smoothing. Oxygen stayed 1.0 over 2 min of EVA; radiation 0.

**Seats and vehicles**
- Vehicle data only exists while seated, and arrives ~6-9 s after sitting down. `ACTOR_ENTER_SEAT` and
  `ACTOR_LEAVE_SEAT` events fire for most seat changes, but **not** for the Ironclad remote-turret seat. Watch the
  vehicle frame appearing or disappearing, not only the events.
- Crew role: pilot seats = PILOT, the remote turret (operations seat) = CREW, the manned nose turret = GUNNER. The
  turret frame appears in both turret seats (in the remote one once turret mode is entered).
- **The weapons and countermeasures frame is per seat**: each seat shows only what it controls.
- **Command Module separation**: the vehicle switches from `DRAK_Ironclad_…` to `DRAK_Command_Module_…` with its own
  weapons, countermeasures and lights, and an `ACTOR_ENTER_SEAT` fires even though the player never moved. Docking
  reverses it. Software must expect the vehicle to change mid-flight.
- The first frame after a seat change can carry stale settings (`use_fading_pips` for one frame).

**Ship state**
- `lights_enabled`, `is_landed`, gear and VTOL work. VTOL also has all 4 phases, ~2 s each way.
- Power: each group toggled cleanly. `powerplants` is the main switch: off takes everything with it. The
  cooler could not be toggled on its own (the flag never moved). Weapons once needed a power restart to
  stay on (game bug). Radar = `sensors`.
- Flight settings confirmed: coupled, ESP, G-safe, speed limiter, gravity compensation, cruise mode,
  boost-disables-G-safe, space-brake-enables-boost, headlights. ESP and G-safe go **inactive** (still enabled) while
  the engines are off. `g_safe.active` also drops whenever boost is in use (boost key or space brake). Brief
  one-frame `enabled`/`active` disagreement during toggles.
- Not in the API: **auto slowdown** (no field moved), and **proximity assist intervention** (`active` never set;
  the user has never seen the assist intervene in 5 years). Light amplification is in the API but broken in game
  for many ships.
- **Doors: never populated** (Ironclad, Command Module, Vulture; Clipper the day before).
- **Weapon presets: never populated** on any seat or ship tested.
- Gimbal lock (turret): `gimbals_locked` true/false works.
- Boost: `engaged`, `output` (ramps to 1.0 in ~2 s) and `reserves` (drains ~5 %/s, refills ~1.8 %/s).
  `critical` = reserves below 25 % (the HUD's red threshold, per the user); it stays true while refilling.
- `radar_altitude` falls back to exactly `altitude` when there is no ground reading, so equal values mean "no
  reading". It is measured from the ship's reference point (11.6 m when landed in an Ironclad), so it never
  reaches 0. Use `is_landed` to detect landing.
- Atmospheric density: 1.20 at Lorville ground level; 0.003-0.007 high up.

**Warning lights, updated**
- **QDRV = quantum mode active**: confirmed on the Clipper, the Command Module and the Vulture. The Ironclad
  never reports it (bug). Combat mode = leaving quantum mode: QDRV off, shields up.
- **THR = engines**: OFF with engines off, MAJOR_ON while starting up and for the whole quantum jump. It does
  *not* show boost drain (that is `boost.critical`).
- **SHLD = shields**: OFF = off (also in quantum mode), MAJOR_ON ≈ 1 s while coming up, MINOR_ON = up while landed or
  near a station, NOMINAL = up in flight.
- **PROX = proximity alert**: MINOR_ON (close) → MAJOR_ON (collision danger), confirmed at Everus Harbor.
- **PWR**: did not react to powerplant off/on. **WPN, MISL**: no reaction to weapon power, combat mode or
  missile mode (the Vulture had no missiles listed). **RADR**: OFF on the pad, NOMINAL in the Command Module.
- Missile mode shows instead as the guns' `ready_to_fire` → false (and back on returning to guns).

**Quantum travel**
- `quantum_fuel` is never populated (the Vulture HUD showed 100 % → 99 %, and a route needing 101.57). There is
  no route or fuel-plan data at all.
- During a jump, **speed and heading freeze at their last values** and the g-meter is 0, while THR is MAJOR_ON. Use
  that combination as "in a jump".
- **Outside a planet's frame, heading is absent or frozen.** Trust heading only while altitude is valid
  (< 3.4e38). The Ironclad also showed speed 0 throughout and a frozen heading (bug); the separated module did not.

**`/showlocation` (Hurston, 18:15-18:17)**
- Format `Coordinates: x:<m> y:<m> z:<m>`, system frame, 6 decimals.
- Hovering still (telemetry speed 0.0), the system coordinates moved **14.1 km in 27.5 s = 514 m/s**: Hurston's
  rotation. **z stayed constant to 2 cm**, so the rotation axis is the system z axis (planet north = +z), and the
  conversion is a rotation about z by the planet's angle at that moment.
- The weak point is timing, not precision: at 514 m/s, every second of timestamp error is 514 m. The skill must
  timestamp the clipboard change itself.
- Disruption in flight (one call at ~109 m/s): not yet rated by the user.

## Full field test, day 2 (2026-10-28, from 17:26, in progress)

Ship: Drake Cutter (`DRAK_Cutter_907038284543`), from the Lorville hangar. Recording: `telemetry_dev/frames_2026-10-28.jsonl`.

**Identity**
- The numeric suffix of `name` (and of seat and weapon names) is the game's **entity ID** for that instance. A newly
  spawned ship gets a new ID, so the ID distinguishes "same ship" from "new ship". The same IDs appear in Game.log,
  so telemetry and the log reader can be joined on them. For display, use `class_name` and take the manufacturer from
  the class prefix (`DRAK`); the `manufacturer` field has always been empty.

**Purchases, food and drink**
- `uec_balance` updates per item, ~2 s apart: 8 items bought (5 × 3 aUEC + 3 × 2 aUEC = 21 aUEC).
- Eating: hunger 70 → 80 → 90 → 100, +10 per bite. Drinking: thirst rises ~8 per second while drinking (35 → 62,
  63 → 90, 91 → 100).
- Background drain was ~0.1 per 8-10 s (thirst slightly faster), but **the drain rate depends on the player's
  current food and drink buffs** (user), and **buffs and effects are not in the API**. A "time until
  hungry/thirsty" estimate must use the current slope and keep recalculating; a change in slope means a buff
  starting or ending.
- `intoxication_level` stayed 0 (non-alcoholic drinks). Still to test.

**Countermeasures**
- Counts drop live, within ~2 s of each burst: decoys 96 → 94 → 92 → 90 → 88 → 86, noise 10 → 8 → 6 → 4.
- The burst size (2 per press on this Cutter) **differs by ship and can be changed by the player in flight**. Never
  hardcode it: take the size of the last observed drop as the current burst size, and estimate "bursts left" from
  that.
- When a type runs out, it drops out of the list (seen as "0 decoys" on the Ironclad on day 1).

**Weapons and the WPN light (now explained)**
- **WPN = weapon availability.** NOMINAL = ready. **MINOR_ON = weapons limited or unable to fire**: seen for the whole
  time in quantum mode (17:55:31-17:57:53) and flickering during sustained laser fire (17:58:22-26), exactly when the
  guns stopped and stuttered (user confirmed): the **capacitor ran empty**.
- The capacitor, ammo and weapon heat are not in the API; WPN is the stand-in. Probably the same light covers
  ballistic overheating (not yet tested). MAJOR_ON for WPN has not been seen.
- `ready_to_fire` does **not** drop when the capacitor empties. It only drops briefly on mode or group switches (and
  in missile mode for the guns).

**Warning lights: status after day 2**
| Light | Meaning | Status |
| --- | --- | --- |
| QDRV | quantum mode active | confirmed (the Ironclad doesn't report it) |
| THR | engines on/off/starting; MAJOR_ON for a whole quantum jump | confirmed |
| SHLD | shields off / coming up / up (MINOR_ON when landed or near a station) | confirmed |
| PROX | proximity alert, MINOR_ON close, MAJOR_ON collision danger | confirmed |
| WPN | weapon availability (MINOR_ON = limited: quantum mode, capacitor empty) | confirmed |
| COOL | OFF throughout so far; overheating not yet tested | partly |
| RADR | OFF on the pad, NOMINAL in flight in the Command Module | partly |
| HIT | not triggered yet | open (combat) |
| MISL | no reaction so far, and missiles never appear in the weapon list | open |
| PWR | no reaction to powerplant off/on | open (maybe damage) |

## Still to prove

1. `/showlocation`: precision DONE (6 decimals; rotation about z). Still open: how disruptive one call is in
   flight (user's rating).
2. Per-planet rotation rates and reference angles for converting `/showlocation` (system frame) to
   planet-local. Probably in `Game2.dcb`; not checked.
4. Combat (day 2): countermeasures (counts drop), firing (`ready_to_fire`), hits (HIT, SHLD drained, health),
   downed / dead / respawn events, WPN/MISL meaning (a ship with missiles).
5. Optional: food/drink (hunger, thirst, intoxication, UEC drop on purchase), a ground vehicle
   (`VEHICLE_TYPE_GROUND`).
3. Optional: whether `altitude` is above the planet's reference radius (to turn it into a distance from the
   planet's centre exactly).

## Evidence

- Local, git-ignored: `telemetry_dev/frames.jsonl` (all frames, both tests), `probe_output.txt`, `launch_output.txt`.
- Game: `Game.log` of the 22:23 and ~22:31 sessions; crash dump and copies under `%LOCALAPPDATA%\Star Citizen\Crashes\`.
- Session log: `~/.claude/logs/` for 2026-10-26.
