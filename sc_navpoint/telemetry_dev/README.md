# Telemetry probe (dev only, not shipped)

Checks whether Star Citizen's built-in gRPC telemetry stream (`sc.game.telemetry.v1.GameTelemetryService`,
found in the 4.10.2 binary) can be switched on and read. Background: section H of
`../NO_OVERLAY_RESEARCH_2026-10-26.md`. Schema: `sc_telemetry.proto`.

## One-time setup

```powershell
python -m venv .venv
.venv\Scripts\pip install -r requirements.txt
```

## Run

1. Quit the RSI Launcher completely (tray icon too) and Star Citizen.
2. In one PowerShell window: `.\launch_with_telemetry.ps1`. It starts the launcher with
   `GRPC_CLIENT_SERVER_ENABLED=true` and `GRPC_CLIENT_SERVER_ADDRESS=127.0.0.1:2942`, set for that process
   only. Start the game from the launcher. The script reports the game's listening ports and the related
   Game.log lines.
3. In a second window: `.venv\Scripts\python probe.py --wait --log frames.jsonl`, then get into a ship seat.

## Reading the result

| Probe says | Meaning | Try next |
| --- | --- | --- |
| summary lines with `hdg=` | it works | fly straight, then turn, and note what `hdg` does |
| `UNAVAILABLE` forever | the port never opened | `.\launch_with_telemetry.ps1 -Enabled 1`; check the ports the script listed |
| `UNIMPLEMENTED` | a gRPC server is there, but not telemetry | send the script's Game.log lines back |
| `UNAUTHENTICATED` | it wants a Bearer token | stop here; the token source is unknown |

Send back `frames.jsonl` (a minute or two is enough) and the launch script's output.

## Offline self-test (no game)

```powershell
.venv\Scripts\python fake_server.py --port 29420
.venv\Scripts\python probe.py --address 127.0.0.1:29420
```
