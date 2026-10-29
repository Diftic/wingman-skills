# Star Citizen Telemetry (Wingman AI skill)

Reads Star Citizen's own live telemetry: the ship's speed, altitude, heading, flight modes, power, warning lights,
weapons and countermeasures, and the pilot's health, hunger, thirst, oxygen and wallet. Your Wingman reacts to what
happens (shields down, under fire, quantum jumps, player down, ...) and answers questions about the ship and the
pilot. Other skills (NavPoint) read the same data from its feed.

Status: **0.1.0, not yet released.** Needs a Wingman AI version that ships gRPC (requested from ShipBit).

## Requirements

- Windows, Star Citizen 4.10.2 or later (tested on 4.10.2 LIVE).
- A Wingman AI version with gRPC support. Until then the skill says so instead of reading.
- Star Citizen telemetry switched on: the skill's setting **Enable Star Citizen telemetry** sets the Windows user
  variable `GRPC_CLIENT_SERVER_ENABLED=true`. Then **quit the RSI Launcher completely (also from the tray) and start
  it again**; the game only gets the variable from a freshly started launcher.

Details of the startup sequence and what the game sends: [TELEMETRY_REPORT.md](TELEMETRY_REPORT.md) (section 1).

## Install

Extract the ZIP, close Wingman AI, run `installer.bat`, restart Wingman AI, enable the skill on **one** wingman.
It is a single reader of the game's stream: on several wingmen at once, they would share one feed and one switch.

## Settings

- **Enable Star Citizen telemetry**: the switch above. Turning it off removes the variable again.
- **Enable Proactive Notifications**: lets your Wingman react to what happens to the ship and the pilot. Off: it stays
  quiet and only answers questions.

These two are the only settings (2026-10-29). Every reaction is on, and the thresholds are fixed: health below 30 %,
oxygen below 20 %, hunger and thirst below 25 %, hydrogen below 15 %, countermeasures at 3 bursts left; up to 10
reactions until you speak again, shown in the HUD and remembered in the conversation. The skill card lists every
reaction (untested ones marked *) and everything that is tracked.

## Privacy and safety

The game's telemetry is unencrypted and bound to `127.0.0.1` (this PC only). Any program on the PC can read it while
it is on. It contains vitals, ship state and the UEC balance, **not your position**. The switch is CIG's own,
undocumented setting: no game file or memory is touched, and a game patch can change or remove it.

## For other skills

`<generated files>/feed/telemetry_state.json` (current state, ~10 per second; stale after 2 s) and
`feed/telemetry_events.sqlite` (events, cursor-based). Read them with `read_state()` / `read_events()` from
`dependencies/sc_telemetry_core/feed.py`. Contract version 1.

## Development

```
python -m pytest tests          # replays recorded frames from live tests
python tools/build_config.py    # regenerate default_config.yaml after changing events.py
```
