# What each source tracks: log reader vs. telemetry

Summary as of 2026-10-28 (Star Citizen 4.10.2). **Log reader** = Game.log, read by Core's SC log service and
reported through `sc_game_events` (the event list that came from SC Log Reader). **Telemetry** = the game's local
telemetry stream, read by `sc_telemetry` (field tests: `TELEMETRY_REPORT.md`).

The two hardly overlap: the log reader knows **what happens in the world** (missions, places, zones, money, injuries
by body part), telemetry knows **the live state of the ship and the body** (instruments, systems, vitals as numbers).

## Ship (seated in a spaceship)

| Topic | Log reader | Telemetry |
| --- | --- | --- |
| Which ship | ship name when boarding / leaving | class, instance id, type; changes live (incl. Ironclad module separation) |
| Boarding / leaving | ship boarding events | enter / leave seat (not on every seat) |
| Hangar | hangar ready, hangar queue | – |
| Speed, altitude, heading, vertical speed, g-force | – | **live** (heading inside a planet's frame) |
| Landed, landing gear, VTOL, lights | – | **live** |
| Flight modes (coupled, ESP, G-safe, speed limiter, cruise, gravity compensation) | – | **live** |
| Power of 9 systems | – | **live** (on / off only) |
| Warning lights (quantum, thrusters, shields, proximity, weapons, hits, radar) | – | **live** |
| Shields down, under fire, being locked on, collision warning | – | **live** (from the warning lights) |
| Fuel | low fuel warning | hydrogen fuel level live; quantum fuel never filled |
| Boost | – | **live** (engaged, reserves, low) |
| Weapons, countermeasures | – | weapons powered / ready, gimbal lock, decoy / noise counts (per seat) |
| Quantum travel | route set, calibration started / complete, party member quantum ready, quantum arrival | quantum mode on / off, jump in progress (no destination, no fuel) |
| Crash / destruction | fatal vehicle collision | powerplant / engines offline, damage via warning lights |
| Impound, insurance | vehicle impounded, insurance claim requests / results | – |
| Crew role | – | pilot / gunner / crew, turret |

## Ground vehicle (seated in a rover, bike, tank)

| Topic | Log reader | Telemetry |
| --- | --- | --- |
| Which vehicle, boarding / leaving | boarding events (same as ships) | seat name and crew role; leave-seat event (no enter) |
| Speed, heading, systems, warnings | – | **not sent** (no vehicle frame; tested on the Ursa Rover) |
| Weapons | – | weapons powered / ready (the vehicle's guns) |
| Crash, impound, insurance, low fuel | same as ships | – |

## On foot (incl. EVA)

| Topic | Log reader | Telemetry |
| --- | --- | --- |
| On foot / EVA / seated | – | **live** (EVA smoothed at doors) |
| Health | injuries per body part with severity, bleeding, incapacitation, medical bed treatment, emergency services | **health 0-100 live**; down or dead = health 0; respawn = back to 100 (no death events) |
| Hunger, thirst | – | **live** (0-100; +10 per bite, ~+8/s drinking) |
| Heart rate, exhaustion | – | **live** (red at ~170 bpm) |
| Oxygen, body temperature, intoxication | – | sent; static in the tests so far |
| Surroundings | – | pressure, gravity, outside temperature, breathable air (live), radiation (static) |

## Anywhere (not tied to a vehicle)

| Topic | Log reader | Telemetry |
| --- | --- | --- |
| Location | arrivals and departures, location changes, system | – (no position or place at all) |
| Zones and law | armistice zone, restricted area, monitored space (and outages), jurisdiction changes, CrimeStat increase | – |
| Missions | contracts accepted / completed / failed / withdrawn / shared / available, objectives new / completed / withdrawn | – |
| Money | rewards, fines, money sent, shop purchases / sales, transactions, commodity buy / sell, cargo transfers, refinery, blueprints | **UEC balance live** (every change, but without the reason) |
| Session and social | login, session start, joining the PU, party invitations and membership, incoming calls, journal entries | – |

## Together

- **Ship and body state**: telemetry only. **World, missions, places, law, money reasons**: log reader only.
- **Both**: boarding a ship (log reader names it, telemetry gives its live state); money (log reader gives the reason,
  telemetry the balance); health (log reader gives injuries per body part, telemetry the overall number).
- **Neither**: the player's position and camera direction (NavPoint uses `/showlocation`), quantum destination and
  fuel, doors, power amounts, ammo, hull and component health.
