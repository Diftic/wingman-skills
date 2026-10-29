# sc_telemetry: design (draft, 2026-10-28)

Wingman skill that owns Star Citizen's built-in local telemetry stream, interprets it, tells the Wingman about
game events, and serves the data to other skills (first consumer: NavPoint). Status: design only, nothing built.

Evidence: **`sc_telemetry/TELEMETRY_REPORT.md`** (the current reference, startup first), the history in
`sc_navpoint/TELEMETRY_REPORT_2026-10-26.md` (live field tests 2026-10-26/27/28),
`sc_navpoint/SC_TELEMETRY_API_4.10.2.proto.txt` (schema), `sc_navpoint/telemetry_dev/` (working probe,
recordings to replay in tests).

## 1. Goals and scope

- One owner for the stream: enable it, connect, decode, apply the known quirks once, so consumers don't repeat them.
- Same user experience as SC Log Reader: same kind of settings menu (master switch + one switch per event) and the
  same `[Game Event]` delivery to the AI.
- Serve other skills without code imports (NavPoint has a history of cross-skill import collisions): a read-only,
  versioned feed like the log reader's.
- Scope of the data: ships and the player. Ground vehicles send no vehicle frame (tested: Ursa Rover), so they are
  covered only through the player and weapon frames.

Not in scope: position (the API has none; NavPoint keeps `/showlocation` and the overlay path), anything the log
reader already owns (missions, contracts, locations, shops, trade).

## 2. Layers (log reader terminology)

| Layer | Job |
| --- | --- |
| **Reader** | gRPC client for `127.0.0.1:2942`, `TelemetryStream`, reconnect with backoff, decode protobuf. No interpretation. |
| **Handler** | Normalise each frame into state, apply the quirk rules (section 5), derive events (section 6), keep a short history. |
| **Orchestrator** | Settings, Wingman integration (tools, `[Game Event]` reactions, toasts), the enable switch, health, the feed for other skills. |

The Reader runs in its own thread: ~17-18 frames/s must never block Wingman.

## 3. Switching telemetry on

The game reads `GRPC_CLIENT_SERVER_ENABLED=true` from its environment, which it inherits from the RSI Launcher
(verified on 4.10.2). Default address `127.0.0.1:2942`, no token.

- Setting **"Enable Star Citizen telemetry"** (off by default). Turning it on sets the Windows **user** environment
  variable `GRPC_CLIENT_SERVER_ENABLED=true`; turning it off removes it. This is persistent configuration, so it is
  only done on the user's explicit action, and the hint says so.
- After any change: tell the user to **fully quit the RSI Launcher (tray too) and start it again**. A running
  launcher never picks the variable up.
- Optional extra (later): a "Star Citizen (telemetry)" starter shortcut for users who don't want a permanent variable.
- Health, shown via tool and toast:
  - `off`: variable not set;
  - `waiting`: set, but port 2942 closed (game not running, or launcher not restarted);
  - `connected, no frames`: in menus or loading;
  - `live`: frames arriving;
  - `unsupported`: the game is running but Game.log has no `Service 'sc.game.telemetry.v1.GameTelemetryService'
    registered` line, so CIG changed the switch in a patch. Then say so plainly.

Security note for the README: the stream is unencrypted and readable by any local program while on; it is bound to
loopback only. It exposes the player's vitals, ship state and UEC balance, not position.

## 4. Normalised state (what the skill knows at any moment)

- **Player:** locomotion (on foot / EVA / seated, smoothed), seat, crew role (pilot / crew / gunner), vitals
  (health, oxygen, hunger, thirst, body temperature, heart rate, intoxication; each as a 0-1 fraction of its own
  `max`), environment (pressure, gravity, outside temperature, radiation, breathable), UEC balance.
- **Vehicle** (seated in a ship only): instance id (from the name suffix), class, manufacturer (from the class
  prefix, since the field is always empty), type, landed, gear, VTOL, lights.
  - Instruments: speed, heading, altitude, radar altitude, vertical speed, density, g-meter, boost (engaged,
    output, reserves, critical), hydrogen.
  - Power: 9 flags. Flight settings: enabled + active pairs.
  - The 10 warning lights, each translated to its own meaning (section 5).
- **Weapons** (per seat): list with powered/ready, gimbal lock, countermeasure counts and the last observed burst size.
- **Derived flags:** `in_planet_frame`, `in_quantum_mode`, `in_jump`, `heading_valid`, `radar_valid`,
  `player_down` (health 0), `weapons_limited`.

Fields the API has but the game never fills (doors, presets, quantum fuel, manufacturer, proximity-assist active,
the four death events) are not exposed as if they worked.

## 4a. Live readouts: every field, and what the field tests showed (user request 2026-10-28)

All of these are read and exposed (tools and feed), whether or not they trigger an event, so the user can see the
stream is really being read. "Live" = changed with real values in the tests; "static" = present but never changed;
"never" = the game never fills it.

**Flight instruments** (ships only)
| Readout | Unit / range | Tests |
| --- | --- | --- |
| Speed | m/s | live (0-814; frozen during a jump) |
| Heading | degrees 0-360, clockwise, nose direction, HUD-compass north | live in a planet frame (matched the HUD 3×) |
| Altitude | m above the planet's reference level (3.4e38 = no planet) | live (897.9 m Lorville hangar, 50 km frame edge) |
| Radar altitude | m above ground from the ship's reference point (= altitude when no reading) | live |
| Vertical speed | m/s (negative = descending) | live in a planet frame |
| Atmospheric density | ~kg/m³ (1.20 at Lorville ground) | live |
| G-meter | current g + max | live (up to 8.6 g) |
| Hydrogen fuel | 0-1 | live (slow drain) |
| Quantum fuel | 0-1 | never |
| Boost | engaged, output 0-1, reserves 0-1, critical (< 25 %) | live |

**Flight state and settings** (ships only)
| Readout | Tests |
| --- | --- |
| Landed | live |
| Landing gear: retracted / deploying / deployed / retracting | live (~7 s cycle) |
| VTOL: same 4 phases | live (~2 s each way) |
| Transformation | never seen (no transforming ship tested) |
| Coupled, ESP, G-safe, speed limiter, gravity compensation, cruise (each enabled + active) | live |
| Stability, wind compensation, command behaviour, core (enabled + active) | static (always on) |
| Proximity assist, proximity assist landing | static (enabled only; never active) |
| Space brake enables boost, boost disables G-safe | live |
| Advanced HUD (SCM / NAV), HUD labels, course prediction, light amplification | static |

**Ship identity, power and warning lights** (ships only)
| Readout | Tests |
| --- | --- |
| Ship name + instance id, class, type | live (changes on module separation / docking) |
| Manufacturer | never (derive from the class prefix) |
| Lights on/off | live |
| Doors open/closed, locked/unlocked | never |
| Power: powerplants, engines, weapons, coolers, life support, gravity generators, sensors, shield generators, shield emitters | live (gravity generators never on) |
| Warning lights: PWR, WPN, THR, SHLD, COOL, QDRV, RADR, PROX, HIT, MISL (6 states each) | live except COOL, MISL and PWR (section 5) |

**Weapons** (per seat)
| Readout | Tests |
| --- | --- |
| Weapon list: name + id, powered, ready to fire, in preset | live |
| Preset index / name | never |
| Gimbal lock | live |
| Fading pips, lag pips, single pips, precision lines, staggered fire, magnified UI, fallback convergence | static (seen once as a stale value) |
| Countermeasures: decoy / noise counts | live |

**Player**
| Readout | Unit / range | Tests |
| --- | --- | --- |
| Locomotion: on foot / EVA / seated | | live |
| Seat name, crew role (pilot / gunner / crew) | | live |
| UEC balance | aUEC | live (per item, mission payout) |
| Health | 0-100 | live (grenade 100 → 0, respawn 0 → 100) |
| Oxygen | 0-1 | static (1.0 even after 2 min of EVA) |
| Hunger, thirst | 0-100 | live (eating +10 per bite, drinking ~+8/s) |
| Body temperature | °C | static (36.5) |
| Heart rate | bpm | live (60-171.7) |
| Gravity | g | live (1 ↔ 0) |
| Pressure | atm-like 0-1 | live (venting curve) |
| Intoxication level | integer | static (0; no alcohol yet) |
| Outside temperature | °C | live (21 → −0.3) |
| Radiation rate | | static (0 everywhere tested) |
| Breathable atmosphere | yes / no | live |

**Other**
| Readout | Tests |
| --- | --- |
| Turret: light amplification | static (broken in game for many ships) |
| Force feedback: angular / linear resistance and damping per axis, gunfire, stick shaker | never (needs a force-feedback device) |
| Game events: spawn, dead, enter seat, leave seat, respawn, downed | enter/leave seat live; the other four never |

## 5. Quirk rules (from the field tests, applied once in the Handler)

1. Heading is valid only inside a planet's frame (altitude < 3.4e38). Outside it, it is absent or frozen.
2. During a quantum jump, speed and heading freeze at their last values and the g-meter reads 0, while THR is
   MAJOR_ON. Treat that combination as `in_jump`.
3. `radar_altitude == altitude` means "no ground reading". Radar altitude never reaches 0 when landed; use `is_landed`.
4. Missing fields mean default values (false, 0): a missing power flag is off, a missing countermeasure type is empty.
5. Vehicle data arrives 6-9 s after sitting down; enter/leave-seat events are not reliable on every seat (the
   Ironclad remote turret had none, the Ursa had no enter). Detect seat and vehicle changes from the frames
   themselves, with the events as hints.
6. The vehicle can change while seated (module separation or docking): the instance id changes. Reset all
   vehicle-specific state.
7. Ignore settings in the first frame after a seat change (stale values seen).
8. EVA ↔ on foot flickers many times per second at a gravity boundary. Require ~1.5 s of stability.
9. `enabled`/`active` can disagree for one frame during a toggle. Debounce derived events (~0.5 s).
10. Death events (downed, dead, respawn, spawn) never fire. Down or dead = health 0; respawn = health 0 → 100.
    Down and dead cannot be told apart.
11. Countermeasure burst size varies by ship and by player setting: take it from the last observed drop.
12. Food and drink drain depends on buffs that the API does not send: estimate from the current slope.
13. Known ship bugs: the Ironclad never reports QDRV and freezes speed and heading in space. Don't treat a missing
    QDRV as "not in quantum mode" on that class.

Warning-light meanings (10 lights; state words differ per light):

| Light | Meaning |
| --- | --- |
| QDRV | NOMINAL = quantum mode active |
| THR | OFF = engines off; MINOR = damaged; MAJOR = starting / in a jump / failing |
| SHLD | OFF = off; MAJOR = down or recharging from 0; MINOR = up (landed / near a station); NOMINAL = up |
| PROX | MINOR = close; MAJOR = collision danger |
| WPN | MINOR = limited (quantum mode, capacitor empty); MAJOR = unavailable (no power) |
| HIT | MAJOR_FLASHING = taking hits |
| RADR | MAJOR = being locked on (observed in combat); OFF = no power |
| COOL, MISL, PWR | not yet understood: exposed raw, no events |

## 6. Events (same delivery as the log reader)

Delivery: a `[Game Event]` / `[Game Events]` message to the AI with the log reader's rules (react briefly in
character, state only what happened, never act). Batching, de-duplication, one response at a time and the response
budget work as in the log reader. Telemetry runs at 17 Hz, so every event needs debouncing and a cooldown (a
fight must not produce 50 "taking hits" messages).

Settings menu (user, 2026-10-29): **only "Enable Star Citizen telemetry" and "Enable Proactive Notifications"**.
Every reaction is on and has no switch; the master mutes them all. The thresholds are fixed (health 30 %, oxygen 20 %,
hunger/thirst 25 %, hydrogen 15 %, countermeasures 3 bursts, 10 reactions until the user speaks, HUD and remember on).
The skill hint lists every reaction by group, untested ones marked *. This replaces the per-event switches, the
"Ship - ... - Selectable" labels and the group masters of 2026-10-28; the history below is kept. The defaults in
brackets below were the earlier per-event defaults; today all are on.

**Tracked states are shown, but cannot be switched off** (user decision 2026-10-28). The menu also lists every
readout from section 4a as "tracked", so the player sees what the skill provides. Wingman's settings have no
read-only control today (no read-only `CustomPropertyType`, no `readonly` flag), so:
- **Now:** the tracked states are listed in the skill's `hint` (HTML, which the client renders), grouped like section 4a.
- **Later:** a read-only "info" row per state, once Core has one. Logged as Core request #16 in
  `sc_log_reader/docs/CORE_UPDATE_REQUESTS.md`.
- **Each tracked state shows its status** (user, 2026-10-28): **tracked** (the game fills it), or **channel exists,
  not filled by the game** (greyed out). The status comes from section 4a, so the player sees both what is provided and
  what CIG has a channel for but doesn't send yet. Examples: everything in the vehicle frame for ground vehicles (the
  Ursa sends none), doors, weapon presets, quantum fuel, the four death events. If a game patch starts filling one, the
  skill detects live values and shows it as tracked without an update.

- **Ship systems:** powerplant offline / online [on]; engines failing / offline [on]; shields down [on] / restored
  [off]; weapons unavailable [off]; boost depleted [off].
- **Flight:** landed / took off [off]; landing gear deployed / retracted [off]; quantum mode on / off [off];
  quantum jump started / finished [on]; proximity warning [on]; switched to a new vehicle (incl. module
  separation) [off].
- **Combat:** under fire [on, long cooldown]; missile lock / being locked on [on]; countermeasures low [on]
  (threshold setting) / empty [on].
- **Player:** health low [on] (threshold setting); player down (health 0) [on]; respawned [off]; oxygen low [on];
  atmosphere not breathable while unprotected [off]; exhausted (heart rate ≥ 170) [off]; hunger / thirst low [on]
  (threshold setting); intoxicated [off].
- **Wallet:** UEC change [off by default, since the log reader already reports trades and rewards].

## 7. AI tools

Same style as the log reader's `get_current_game_state`:

- `get_ship_status`: identity, flight state, instruments, power, warning lights in plain words.
- `get_player_status`: locomotion, vitals, environment, UEC.
- `get_weapons_status`: weapons, gimbal, countermeasures (with an estimate of bursts left).
- `get_telemetry_health`: off / waiting / live / unsupported, with what to do.

## 8. Feed for other skills (NavPoint)

The same contract style as `sc_log_reader/dependencies/sc_log_reader/feed.py`:

- **Snapshot file** (`telemetry_state.json` in the skill's generated_files): the current normalised state plus
  `contract_version`, `source_id` (changes on every game session), `seq` and a monotonic `frame_time`. Written
  atomically (write + rename) at 10 Hz. Readers open it read-only and ignore a stale file (frame_time older than 2 s =
  no telemetry).
- **Event feed** (SQLite, read-only for consumers, cursor-based pages): the same derived events as section 6, but
  undebounced for machines and independent of the notification switches.

NavPoint consumes `heading` (+ `heading_valid`), `speed`, `vertical_speed`, `altitude`, `radar_altitude`
(+ `radar_valid`), `is_landed`, `in_jump`, `in_planet_frame`, the vehicle instance id and `g_meter`. It combines
them with the log reader (location / zone events, as now) and its own `/showlocation` fixes for position. 10 Hz is
enough for its dead reckoning; if it ever needs the full 17 Hz, it can connect to port 2942 itself (the game
accepts several clients).

## 9. Packaging

- Dependencies: `grpcio` and `protobuf`, bundled for the host's CPython 3.11 x64, like the log reader's
  `dependencies`. The generated `_pb2.py` files ship pre-built; no `grpcio-tools` at runtime.
- Size check needed: grpcio wheels are ~4-5 MB.
- Installer, manifest and release flow copied from the log reader / NavPoint (installer.bat, zip + sha256,
  pre-release first).

## 10. Testing

- Replay tests: feed the recorded frames (`frames_2026-10-26/27/28.jsonl`) through the Handler. Every quirk rule and
  event in sections 5-6 gets a test built from a real recorded moment (the grenade at 18:48:24, the
  powerplant loss at 18:15:08, module separation at 18:38:45, the EVA flicker at 19:00:11, ...).
- The fake server in `telemetry_dev/fake_server.py` covers the Reader (connect, reconnect, unavailable).
- Live check after each game patch: the probe plus the "service registered" line.

## 11. Decisions (user, 2026-10-28)

1. DECIDED: enabling = **user environment variable from the settings menu, plus an optional starter shortcut**.
2. DECIDED 2026-10-29: every event on, no per-event switches (section 6).
3. DECIDED: feed = **snapshot file + SQLite event feed** (section 8).
4. DECIDED 2026-10-29: none; the thresholds are fixed (section 6).
5. DECIDED: folder and module **`sc_telemetry`**, display name **"Star Citizen Telemetry"**.
6. DECIDED: lives in the **`wingman-skills` repo** (Diftic/wingman-skills), with the same release flow as the other
   skills.
