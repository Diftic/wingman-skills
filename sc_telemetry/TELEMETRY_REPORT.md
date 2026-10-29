# Star Citizen telemetry: report for the sc_telemetry skill

Current as of **2026-10-29** (day-3 live test with the skill itself: the real start path works; ballistic
overheating and empty ammo are not in the telemetry; the skill now shows only two settings, every reaction on). Game: Star Citizen **4.10.2 LIVE** (build 12913470). This report replaces
`sc_navpoint/TELEMETRY_REPORT_2026-10-26.md` as the reference for `sc_telemetry`; that file stays as the history of
the investigation.

Evidence: live field tests on 2026-10-26 (Drake Clipper), 2026-10-27 (Drake Ironclad, its Command Module, Drake
Vulture) and 2026-10-28 (Drake Cutter, RSI Ursa Rover). All frames are recorded in
`sc_navpoint/telemetry_dev/frames_<date>.jsonl`.

---

## 0. At a glance (2026-10-29)

**Connection.** Star Citizen 4.10.2 runs a local gRPC server when `GRPC_CLIENT_SERVER_ENABLED=true` is in the game's
environment. On Windows the game inherits it from the RSI Launcher, so: set the Windows **user** variable (the skill's
"Enable Star Citizen telemetry" does it), **quit the launcher completely (tray too)**, start it again, start the game.
The server is `127.0.0.1:2942`, insecure, no token; one server-streaming call
`sc.game.telemetry.v1.GameTelemetryService/TelemetryStream` sends about 17 frames a second once you have spawned.
`Game.log` proves it with `Service 'sc.game.telemetry.v1.GameTelemetryService' registered`. Read-only: nothing is
sent to the game, no game file or memory is touched. The skill connects only to loopback.

**Works (confirmed live, 2026-10-26 to 10-29):**
- Ships: speed, heading (inside a planet's frame only), altitude, radar altitude, vertical speed, g-force, hydrogen
  fuel, boost, landing gear, flight modes (coupled, VTOL, cruise, precision, quantum mode), quantum jump, power
  on/off (9 flags), the warning lights (THR, SHLD, PROX, WPN, HIT, RADR, QDRV), weapons per seat (name, powered,
  ready), countermeasure counts, ship and seat name, Command Module separation (becomes a new vehicle).
- Pilot: health (0 = down or dead, 0 → 100 = respawned), hunger, thirst, heart rate, locomotion (on foot, seated,
  EVA), surroundings (atmosphere, gravity), UEC balance, enter/leave seat events.
- The skill: the real start path (Wingman starts first, then the launcher and game), reactions in character
  (took off, quantum jump, being locked on, under fire, shields down, powerplant/engines, countermeasures, ...), and
  both tools answering (`get_ship_status`, `get_player_status`).

**Does not work / not in the API:**
- No position and no camera direction (NavPoint keeps `/showlocation` and the game log).
- No amounts: power allocation, heat, ammo, capacitor, hull or component health. Ballistic overheating and an empty
  magazine change nothing (tested twice).
- Ground vehicles (Ursa) send no vehicle frame at all; only the seat name shows you are in one.
- Never filled: doors, weapon presets, quantum fuel, manufacturer, death events, force feedback.
- Missiles and the MISL light: nothing seen, but the game's missiles are bugged right now, so not final. A hostile
  locking on shows as RADR (it is not your own missile lock).
- Heading freezes during a quantum jump; WPN MINOR is broad (quantum mode, empty capacitor, landed with guns
  firing), so it is not reported.

**Untested:** intoxication, oxygen low, unbreathable air, hydrogen low, boarding a ground vehicle (marked * in the
skill), PWR and COOL lights, a second ground vehicle, Linux (Wine/Proton: see the Core skill's README).

**The skill.** `sc_telemetry` 0.1.0, two settings ("Enable Star Citizen telemetry", "Enable Proactive
Notifications"), every reaction on. Needs `grpcio` in Wingman: proposed to ShipBit as a bundled Core skill (PR to
`develop`, which adds `grpcio` to Core's requirements).

---

## 1. Startup sequence and requirements (telemetry activation)

### What the game offers

Star Citizen contains a **local gRPC server** for telemetry: service `sc.game.telemetry.v1.GameTelemetryService`,
one call `TelemetryStream`, which streams frames to every connected client. It is **off by default**. It is the
game's own feature; nothing is patched, injected or read from memory.

### Requirements

| Requirement | Detail |
| --- | --- |
| Switch | the environment variable **`GRPC_CLIENT_SERVER_ENABLED=true`** in the environment of `StarCitizen.exe` |
| Address (optional) | `GRPC_CLIENT_SERVER_ADDRESS`; the default is already **`127.0.0.1:2942`**. Keep it on loopback. |
| How the game gets it | the game inherits it from the **RSI Launcher**, which starts the game. So the **launcher** must have the variable. |
| Launcher restart | the launcher only sees a variable that existed **when it started**. After setting it: **quit the launcher completely (including the tray icon) and start it again.** |
| Login / token | none. The server runs unencrypted (`[Insecure]`) and accepts any local client. |
| Several clients | allowed (the server counts clients). |
| Data flow | frames only arrive **after the player has spawned**; none in menus or loading screens. Then ~17-18 frames per second. |

### Two ways to set the switch

1. **Permanent (recommended):** set `GRPC_CLIENT_SERVER_ENABLED=true` as a Windows **user** environment variable.
   Every launcher start then passes it on, also when the launcher starts with Windows. In `sc_telemetry` this is a
   setting that only acts on the user's explicit choice, and can be undone the same way.
2. **Per start:** a starter (shortcut or script) that sets the variable only for the launcher process it starts.
   Nothing permanent, but the user must always use the starter. A launcher already open in the tray defeats it.
   Dev version: `sc_navpoint/telemetry_dev/launch_with_telemetry.ps1`.

### Startup sequence (what happens, in order)

1. The RSI Launcher starts with the variable in its environment.
2. The user clicks Launch. The launcher starts `StarCitizen.exe`, which inherits the variable.
3. During startup, Game.log shows:
   - `<Register Service> Service 'sc.game.telemetry.v1.GameTelemetryService' registered`
   - `<GRPC Server> Services configured: 1`, `[sc.game.telemetry.v1.GameTelemetryService]: 127.0.0.1:2942 [Insecure]`
4. The game listens on `127.0.0.1:2942`. A client connects and calls `TelemetryStream` (an empty request).
5. In menus and loading screens the stream is open but silent.
6. Once the player spawns, Game.log shows `Initializing game telemetry component of local player [Haptic]` (this
   appears every session, also without the switch) and frames start: the player frame always; vehicle and weapons
   frames once seated in a ship.

### How to tell what state it is in

| Observation | Meaning |
| --- | --- |
| Variable not set | off |
| Variable set, port 2942 closed | game not running, or the launcher was not restarted after setting the variable |
| Port open, no frames | in menus / loading |
| Frames arriving | live |
| Game running, no "Service … registered" line in Game.log | CIG changed or removed the switch in a patch |

### Security and privacy

The stream is unencrypted and readable by any program on the PC while it is on. It is bound to loopback only, so it
is not reachable from the network. It contains the player's vitals, ship state and UEC balance. It does **not**
contain position.

### Caveats

- The switch is **undocumented**. It is CIG's own configuration, not a hack, but it is not officially offered to
  players and can change with any patch.
- Easy Anti-Cheat is not affected by the switch itself (no game file or memory is touched). Nothing more can be said
  about CIG's or EAC's view.

---

## 2. What the stream contains

One response per frame, with up to six sub-frames: **vehicle**, **weapons**, **events**, **actor**, **force
feedback**, **turret**. The full decoded schema: `sc_navpoint/SC_TELEMETRY_API_4.10.2.proto.txt`; a compilable copy:
`sc_navpoint/telemetry_dev/sc_telemetry.proto`. Missing fields mean their default value (false, 0, empty).

Status in the tables: **live** = seen changing with real values · **static** = present, never changed in the tests
· **never** = the game never fills it.

### Flight instruments (ships only)

| Readout | Unit / range | Status |
| --- | --- | --- |
| Speed | m/s | live |
| Heading | 0-360°, clockwise, **nose direction**, same north as the HUD compass | live, inside a planet's frame only |
| Altitude | m above the planet's reference level; 3.4e38 = no planet | live |
| Radar altitude | m above ground, from the ship's reference point; equal to altitude = no reading | live |
| Vertical speed | m/s, negative = descending | live, inside a planet's frame only |
| Atmospheric density | ~kg/m³ (1.20 at ground level, Lorville) | live |
| G-meter | current g, max g | live (up to 8.6 g) |
| Hydrogen fuel | 0-1 | live |
| Quantum fuel | 0-1 | **never** |
| Boost | engaged, output 0-1, reserves 0-1, critical | live |

### Flight state and settings (ships only)

| Readout | Status |
| --- | --- |
| Landed | live |
| Landing gear, VTOL: retracted / deploying / deployed / retracting | live |
| Transformation | never seen (no transforming ship tested) |
| Coupled, ESP, G-safe, speed limiter, gravity compensation, cruise (each enabled + active) | live |
| Space brake enables boost, boost disables G-safe | live |
| Stability, wind compensation, command behaviour, core | static (always on) |
| Proximity assist (+ landing) | static: enabled only, never active |
| Advanced HUD (SCM / NAV), HUD labels, course prediction, light amplification | static |

Not in the API at all: auto slowdown.

### Ship identity, power, lights (ships only)

| Readout | Status |
| --- | --- |
| Name with instance id, class, type | live. The numeric suffix is the game's entity id (also used in Game.log) |
| Manufacturer | **never** (derive it from the class prefix, e.g. `DRAK` = Drake) |
| Lights on/off | live |
| Doors open/closed, locked/unlocked | **never** (4 vehicles tested) |
| Power: powerplants, engines, weapons, coolers, life support, gravity generators, sensors, shield generators, shield emitters | live (on/off only; no amounts, no capacity, no allocation) |
| 10 warning lights (section 3) | 7 understood, 3 open |

### Weapons (per seat)

| Readout | Status |
| --- | --- |
| Weapon list: name + id, powered, ready to fire, in preset | live. Missiles have never appeared in the list. |
| Preset index / name | **never** |
| Gimbal lock | live |
| Pip, precision-line, staggered-fire and other settings | static |
| Countermeasures: decoy / noise counts | live |

### Player

| Readout | Unit / range | Status |
| --- | --- | --- |
| Locomotion: on foot / EVA / seated | | live |
| Seat name, crew role (pilot / gunner / crew) | | live |
| UEC balance | aUEC | live (per item and per payout) |
| Health | 0-100 | live |
| Hunger, thirst | 0-100 | live |
| Heart rate | bpm | live (60-172) |
| Gravity | g | live |
| Pressure | 0-1 | live |
| Outside temperature | °C | live |
| Breathable atmosphere | yes / no | live |
| Oxygen | 0-1 | static (1.0, also after 2 min of EVA) |
| Body temperature | °C | static (36.5) |
| Intoxication level | integer | static (0; no alcohol tested yet) |
| Radiation rate | | static (0) |

### Other

| Readout | Status |
| --- | --- |
| Turret: light amplification | static (broken in game for many ships) |
| Force feedback | never (probably needs a force-feedback device) |
| Game events: enter seat, leave seat | live (not on every seat) |
| Game events: spawn, dead, respawn, downed | **never** |

### Ground vehicles

The **RSI Ursa Rover** sends **no vehicle frame at all**: no type, speed, heading, altitude, power or lights. Only
the seat (name, crew role), the weapons frame and the leave-seat event work (1,727 frames checked, while driving and
turning). The schema has `VEHICLE_TYPE_GROUND`, `GRAVLEV` and `BOAT`, so the channel exists. Only one ground vehicle
has been tested.

---

## 3. The warning lights (annunciators)

Each light has six states: NOMINAL, OFF, MINOR_FLASHING, MINOR_ON, MAJOR_FLASHING, MAJOR_ON. **The words mean
different things per light**, so each needs its own translation. The user's reading of the HUD colours: MINOR ≈
orange, MAJOR ≈ red.

| Light | Meaning | Evidence |
| --- | --- | --- |
| **QDRV** | NOMINAL = quantum mode active; OFF = not | Clipper, Command Module, Vulture. The Ironclad never reports it. |
| **THR** | OFF = engines off / without power; MINOR_ON = engines damaged; MAJOR_ON = starting up, during a quantum jump, or failing | startup, jumps, combat |
| **SHLD** | OFF = shields off (also in quantum mode); MAJOR_ON = down, or recharging from zero; MINOR_ON = up while landed / near a station; NOMINAL = up in flight | power toggles, combat |
| **PROX** | MINOR_ON = close to something; MAJOR_ON = collision danger | Everus Harbor, Command Module undocking |
| **WPN** | NOMINAL = ready; MINOR_ON = some limitation (quantum mode, laser capacitor empty, **but also constantly while landed in the Lorville hangar with the Gatlings firing normally**, 2026-10-29), so NOT "cannot fire"; MAJOR_ON = unavailable (no power) | partly: MINOR_ON is too broad to report on its own |
| **HIT** | MAJOR_FLASHING = taking hits | combat |
| **RADR** | MAJOR_ON = being locked on (seen throughout an attack); OFF = no power; NOMINAL = normal | combat, power loss |
| COOL | OFF throughout so far; overheating not yet tested | open |
| MISL | no reaction so far, also in missile mode | open (a ship with missiles in its list is needed) |
| PWR | no reaction, not even when the powerplant was destroyed | open |

---

## 4. Behaviour and quirks (what a reader must handle)

1. **Heading is valid only inside a planet's frame** (from ~50 km altitude). Outside it, it is missing or frozen. Use
   altitude < 3.4e38 as the gate.
2. **During a quantum jump, speed and heading freeze at their last values**, the g-meter reads 0, and THR is MAJOR_ON.
   Treat that combination as "in a jump".
3. **Radar altitude** equals altitude when there is no ground reading, and never reaches 0 when landed (it is
   measured from the ship's reference point: 11.6 m for a landed Ironclad). Use "landed" to detect landing.
4. **Missing field = default value**: a missing power flag is off; a missing countermeasure type is empty.
5. **Vehicle data arrives 6-9 s after sitting down.** Enter/leave-seat events don't fire on every seat (none on the
   Ironclad remote turret; no enter on the Ursa). Detect seat and vehicle changes from the frames.
6. **The vehicle can change while seated**: separating the Ironclad's Command Module turns it into its own vehicle
   (new name, weapons, lights) and fires an enter-seat event; docking reverses it. The instance id changes.
7. **The weapons frame is per seat**: each seat shows only the weapons and countermeasures it controls.
8. The **first frame after a seat change** can carry stale settings.
9. **EVA ↔ on foot flickers** many times per second at a gravity boundary (ship door). Smooth it (~1.5 s).
10. **Settings flicker for one frame** during a toggle (`enabled` and `active` disagree). Debounce.
11. **No death events**: down or dead = health 0 (they cannot be told apart); respawn = health 0 → 100 in one frame.
    Seen with a suicide, a grenade and respawning.
12. **Countermeasure burst size** varies by ship and can be changed by the player: take it from the last observed
    drop.
13. **Hunger and thirst drain** depends on food and drink buffs, which the API does not send: estimate from the
    current slope. Eating: +10 per bite; drinking: ~+8 per second.
14. **Power on/off only**: losing or switching off the powerplant takes every other flag with it; destroyed and
    unpowered look the same.
15. **Known ship bugs**: the Ironclad never reports QDRV, and freezes speed (0) and heading in space; its Command
    Module does not.
16. **Weapons can fail to stay powered** (seen once on the Ironclad; a power restart fixed it). A game bug, not the API.

---

## 5. Measured examples (for tests and sanity checks)

| Moment | Values |
| --- | --- |
| Sprint (on foot) | heart rate 60 → 171.7 bpm in ~40 s; the HUD turns red at ~170 |
| Purchase | 8 items, 21 aUEC, UEC balance updated per item ~2 s apart |
| Boost | reserves drain ~5 %/s and refill ~1.8 %/s; critical below 25 % |
| Landing gear | ~7 s per cycle; VTOL ~2 s each way |
| EVA (door opened in space) | pressure 1.0 → 0.267 → 0.034 → 0.001; breathable true → false; ~25 s to repressurise |
| Countermeasures (Cutter) | decoys 96 → 86 and noise 10 → 4, 2 per burst |
| Laser fire (Cutter) | WPN MINOR_ON while the capacitor is empty |
| Combat (Cutter) | HIT MAJOR_FLASHING per volley; SHLD MAJOR_ON when down; THR MINOR_ON when engines damaged |
| Powerplant destroyed | `powerplants` false, all other flags off except weapons; WPN MAJOR_ON; THR and RADR OFF |
| Grenade (on foot) | health 100 → 0 in ~7 s (about −17/s), then incapacitated; no event |
| Respawn | health 0 → 100 in one frame; no event |
| Heading checks against the HUD | 304.28 vs 304; 67.6 vs 67; a 90° yaw while hovering at speed 0 moved heading by 96° |

---

**Day 3 (2026-10-29), with the `sc_telemetry` skill in Wingman 3.2.12 (no probe):**

| Moment | Values |
| --- | --- |
| Real start path | Wingman start → skill `waiting` (once) → normal launcher start with the persistent user variable → game opens 2942 → `connected` 21:16:17 → `live` 21:17:57 on spawn; feed written ~8-10 times/s |
| On foot in the hangar | telemetry: indoors values only (breathable, 21 °C, 1 g, 1 atm), no location; Game.log has the hangar (ship elevator `HangarXLTop`) |
| Ironclad pilot seat + remote turret, fire held 2 min | nothing changed (735 samples), but that seat lists the pilot's own guns, so inconclusive |
| Clipper pilot seat, 2× GATS BallisticGatling S3, fire held 2 min with the overheat cycling, then ammo empty | nothing changed (732 samples): WPN MINOR_ON throughout, COOL OFF, both guns powered + ready, also with no ammo left |

## 6. What the API does not have

- **Position** of any kind (coordinates, latitude/longitude, zone, planet or body name) and **camera direction**.
  NavPoint keeps using `/showlocation` (system coordinates; on a planet they move with its rotation, axis = system z)
  and the game log for location.
- Power **amounts**, capacity, allocation, heat, ammo, capacitor charge, hull health, component health. Confirmed live
  2026-10-29: ballistic overheating and an empty magazine leave every field unchanged.
- Buffs and effects, stamina.
- Missions, contracts, locations, shops: these stay with the log reader.

---

## 7. Still to test

The skill's reactions that no live test has confirmed yet (marked * on the skill card): intoxicated, oxygen low, air not
breathable, hydrogen low, boarded a ground vehicle.

- DONE 2026-10-29: **ballistic overheating and empty ammo are NOT in the telemetry.** Drake Clipper pilot seat, 2× GATS
  BallisticGatling S3, fire held for 2 min with the overheat cycling, then the ammo ran out: 732 samples, nothing changed
  (WPN MINOR_ON throughout, COOL OFF, both guns powered + ready, also with no ammo left).
- **An alcoholic drink**: intoxication level.
- **MISL** with a ship whose missiles appear in the weapon list.
- **PWR**: perhaps only on specific power faults.
- A second ground vehicle (e.g. Cyclone) to confirm "no vehicle frame" for ground vehicles in general.
- After every game patch: does the "Service … registered" line still appear?

---

## 8. How it was found, and how to find it again after a patch

Read-only steps; nothing in the game is modified. Checked again on 2026-10-29 against build 12913470.

1. **The service is in the game binary.** `LIVE\Bin64\StarCitizen.exe` contains the strings
   `sc.game.telemetry.v1`, `GameTelemetryService`, `CGameTelemetryServer` and "Client connected (id=.. total=..)".
   Quick check (PowerShell):
   `Select-String -Path "D:\Roberts Space Industries\StarCitizen\LIVE\Bin64\StarCitizen.exe" -Pattern "sc.game.telemetry.v1" -SimpleMatch -Quiet`
2. **The schema is embedded.** gRPC binaries keep each `.proto` file as a serialized `FileDescriptorProto`.
   `tools/proto_dump.py` finds every `sc/game/telemetry/*.proto` name in the binary, parses the descriptor that starts
   there and prints it as proto text:
   `python tools/proto_dump.py "D:\Roberts Space Industries\StarCitizen\LIVE\Bin64\StarCitizen.exe" sc/game/telemetry/`
   Output: `sc/game/telemetry/v1/api.proto` (the service, one server-streaming RPC `TelemetryStream`) and
   `v1/types.proto` (28 messages). That output became `sc_telemetry.proto`; `schema.desc` is compiled from it.
   **After a patch, run it again and diff** against `dependencies/sc_telemetry_core/sc_telemetry.proto`: new or
   renumbered fields show up there first. Gaps in the field numbers (response 1-2, VehicleFrame 1, vitals 6, force
   feedback 1) suggest removed or reserved fields.
3. **The switch is a services config option.** The same binary has the option table row
   `grpc.client.server.enabled` ("Boolean telling whether grpc services are hosted"), with the forms
   `grpc-client-server-enabled` (command line) and `GRPC_CLIENT_SERVER_ENABLED` (environment), and
   `grpc.client.server.address` (default `127.0.0.1:2942`, env `GRPC_CLIENT_SERVER_ADDRESS`), plus
   `GRPC_CLIENT_SERVER_CHANNEL_ARGS`. An `sc-services.json` file is another source; none exists in a normal install.
   Search the binary for `GRPC_CLIENT_SERVER` to see whether a patch renamed them.
4. **Proof it is live.** Start the RSI Launcher with the variable (`sc_navpoint/telemetry_dev/launch_with_telemetry.ps1`
   sets it for that process only), start the game. `Game.log` then shows
   `Service 'sc.game.telemetry.v1.GameTelemetryService' registered` and `127.0.0.1:2942 [Insecure]`;
   `netstat -ano | findstr 2942` shows the port listening. No token was needed, although the binary also looks for an
   `authorization: Bearer` header.
5. **Read it.** `sc_navpoint/telemetry_dev/probe.py --wait --log frames.jsonl` is a plain Python gRPC client that
   prints a summary line per frame and logs every frame as JSON. `fake_server.py` replays frames for offline tests.
   Frames start only after the player has spawned.
6. **Map each field to the game.** Done by doing one thing at a time in the game (lower the gear, toggle each power
   switch, turn 90 degrees, get shot at, eat, die) and reading which fields changed in the log at that moment;
   `tools/cut_fixture.py` cuts those moments out as test fixtures. Section 2-5 are the results.

Not to be confused with: the **D-BOX LiveMotion** feed (the game loads D-BOX's DLL, gRPC over TLS to
`127.0.0.1:61666`): 6DOF motion and haptics only, no ship state.

## 9. The data on disk

| What | Where | Size |
|---|---|---|
| All frames, test 1 (Clipper, 2026-10-26) | `sc_navpoint/telemetry_dev/frames.jsonl` | 42 MB |
| All frames, day 1 (Ironclad, Command Module, Vulture, 2026-10-27) | `sc_navpoint/telemetry_dev/frames_2026-10-27.jsonl` | 772 MB |
| All frames, day 2 (Cutter, Ursa, 2026-10-28) | `sc_navpoint/telemetry_dev/frames_2026-10-28.jsonl` | 170 MB |
| `/showlocation` samples (Hurston, 2026-10-27) | `sc_navpoint/telemetry_dev/showlocation_2026-10-27.jsonl` | 0.4 KB |
| Probe and launcher output per day | `sc_navpoint/telemetry_dev/probe_output*.txt`, `launch_output*.txt` | |
| The 11 test moments | `sc_telemetry/tests/fixtures/*.jsonl` (gzipped copies in Core: `tests/star_citizen/sc_telemetry_fixtures/`) | 3.7 MB |
| Decoded schema, as dumped | `sc_navpoint/SC_TELEMETRY_API_4.10.2.proto.txt` | |
| Compilable schema + descriptor set | `sc_telemetry/dependencies/sc_telemetry_core/sc_telemetry.proto`, `schema.desc` | |
| History of the investigation | `sc_navpoint/NO_OVERLAY_RESEARCH_2026-10-26.md` (section H), `sc_navpoint/TELEMETRY_REPORT_2026-10-26.md` | |
| Day-3 test (2026-10-29) | in the installed skill's feed (`%APPDATA%\ShipBit\WingmanAI\generated_files\SC_Telemetry\`), not recorded separately | |
| Session logs (every command and prompt) | `~/.claude/logs/D-/2026-10-26.jsonl` to `2026-10-29.jsonl` | |

Each line of a frames file is `{"t": <unix time>, "frame": <TelemetryStreamResponse as JSON>}`; fields at their
default value are left out.

