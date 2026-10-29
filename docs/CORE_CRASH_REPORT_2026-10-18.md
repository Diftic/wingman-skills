# Core crash: `InvalidStateError` kills the main event loop (Windows)

Reported 2026-10-18 by the Wingman user running the test install. For the ShipBit Core developers.

## Summary

Wingman AI Core v3.2.8 on Windows lost its main asyncio loop in the middle of a session.
The traceback is entirely inside CPython's Windows proactor:
`asyncio.exceptions.InvalidStateError: invalid state`, raised from
`windows_events.py` `_poll` → `set_exception`. The exception escapes
`loop.run_until_complete(async_main(...))` in `main.py` and is logged as
`Error starting application: invalid state`.

The process does **not** exit. Windows still lists `WingmanAiCore.exe` as running
and "Responding", but Core is dead from the user's point of view:

- tool calls that use `asyncio.to_thread` fail with `RuntimeError: cannot schedule new futures after interpreter shutdown`
  (persistent memory writes in this case);
- push-to-talk records, but every frame fails with `Audio input: frame handler failed: cannot schedule new futures after shutdown`;
- the background threads (skill pollers, UEX import) keep running and logging.

The only way back is to restart Wingman.

It has happened **twice in four days** with the same traceback:

| When | Log file |
|---|---|
| 2026-10-15 21:44:44 | `wingman-core.2026-10-15_19-29-47.log` |
| 2026-10-18 13:21:32 | `wingman-core.2026-10-18_12-12-28.log` (around line 2785) |

The logs are in `%APPDATA%\ShipBit\WingmanAI\3_2_8\logs\`. We can send both files.

## Environment

- Wingman AI Core v3.2.8 (installed build, `C:\Program Files\WingmanAI`), bundled Python 3.11 (`python311.dll`)
- Windows 11 Home (build 26300)
- HUD server enabled (`127.0.0.1:7862`), HUD skill active
- Long session: about 1 h 10 min of uptime, 140 messages in the conversation, 37 tools
- Star Citizen running; custom skills loaded (including `sc_navpoint`)

## Traceback (2026-10-18, identical on 2026-10-15)

```
2026-10-18 13:21:32 - Error starting application: invalid state
Traceback (most recent call last):
  File "asyncio\windows_events.py", line 494, in finish_recv
OSError: [WinError 995] The I/O operation has been aborted because of either a thread exit or an application request

During handling of the above exception, another exception occurred:

Traceback (most recent call last):
  File "asyncio\windows_events.py", line 846, in _poll
  File "asyncio\windows_events.py", line 498, in finish_recv
ConnectionResetError: [WinError 995] The I/O operation has been aborted because of either a thread exit or an application request

During handling of the above exception, another exception occurred:

Traceback (most recent call last):
  File "main.py", line 837, in <module>
  File "asyncio\base_events.py", line 640, in run_until_complete
  File "asyncio\windows_events.py", line 321, in run_forever
  File "asyncio\base_events.py", line 607, in run_forever
  File "asyncio\base_events.py", line 1884, in _run_once
  File "asyncio\windows_events.py", line 444, in select
  File "asyncio\windows_events.py", line 848, in _poll
  File "asyncio\windows_events.py", line 88, in set_exception
asyncio.exceptions.InvalidStateError: invalid state
```

(The source line printed under the `main.py` frame is left out here because it is wrong. See "Side issue" below.)

What it means: an overlapped socket `recv` was aborted (`WinError 995`, `ERROR_OPERATION_ABORTED`).
This normally happens when its socket is closed while a read is pending. When the
proactor tried to put that error on the read's future, the future was already done
or cancelled. `set_exception` on a finished future raises `InvalidStateError`.
Nothing catches it inside `_poll`, so it ends `run_forever`.

This points to another thread. `_poll` checks `elif not f.done():` just before it runs the
completion callback. That guard is in the 3.12 and 3.13 standard library, and the code is
older than both, so it is very likely in 3.11 too. The future was therefore still pending
when it was checked, and it was finished during the callback. On a single thread nothing
can finish it at that moment. So code on **another thread** most likely cancelled the
main loop's read future (`_OverlappedFuture.cancel()` cancels the I/O, which gives
exactly `WinError 995`) or closed its socket. That is a thread-safety violation:
loop-owned objects being touched without `call_soon_threadsafe` /
`run_coroutine_threadsafe`.

## What happened just before

The two crashes look alike. In both, the HUD skill reconnected to the HUD server within the two seconds before the crash.

2026-10-18:

```
13:21:31 - [HUD] Connected to HUD server
13:21:32 - Heard 'Let's add one more thing to the checklist, please. Verify bag space.' ...
13:21:32 - [User] let's add one more thing to checklist please verify bag space (1.2s)
13:21:32 - Error starting application: invalid state
13:21:32 - [HUD] Connected to HUD server
13:21:32 - Calling LLM with 139 messages (excluding context) and 37 tools.
13:21:34 - Error while processing tool call: cannot schedule new futures after interpreter shutdown
```

2026-10-15:

```
21:44:43 - [HUD] Connected to HUD server
21:44:44 - [HUD] Connected to HUD server
21:44:44 - Error starting application: invalid state
21:44:45 - [HUD] Connected to HUD server
```

"[HUD] Connected to HUD server" is logged 104 times in the 18 October session.
It shows up about once per voice turn, several times a minute while talking.
So the HUD client reconnects all the time, not just once at startup.

## Likely cause (not proven)

`skills/hud/main.py` `_ensure_connected()` reconnects whenever
`HudHttpClient.connected` is false or the running loop differs from the stored
`_main_loop`. Each reconnect goes through `HudHttpClient.connect()`
(`hud_server/http_client.py`). That method first calls `aclose()` on the old
`httpx.AsyncClient`, swallowing all errors, and then opens a new client.

Closing a client whose keep-alive socket still has a read pending on the proactor
leads to exactly this sequence: the pending `WSARecv` completes with `WinError 995`
after its future was cancelled, and the proactor raises `InvalidStateError`.
The HUD reconnect in the same second as both crashes fits this.

The cross-thread angle fits as well. `_ensure_connected()` exists because the HUD
skill gets called from **more than one event loop** (it compares
`asyncio.get_running_loop()` with `_main_loop`). When it is called from a skill thread
with its own loop, it runs `await self._client.disconnect()`, and so `aclose()`, on an
httpx client whose sockets belong to the main loop. That closes a main-loop socket
from another thread.

We have **not** reproduced it on demand. The trigger could also be another
socket that closes during a pending read on the main loop (LLM HTTP client,
the client's websocket).

## Suggested fixes

1. **Keep the loop alive.** Catch `InvalidStateError` from the proactor so a
   single stale I/O completion can't end `run_forever`. One option is to subclass
   `IocpProactor` and drop completions whose future is already done. Another is
   to wrap `run_forever` and restart it when `InvalidStateError` comes from
   `windows_events`.
2. **Fail loudly if the loop dies.** Today Core keeps running as a zombie after
   "Error starting application". If the main loop exits with an exception, Core
   should either exit (so the client can notice and restart it) or tell the client.
   The user only found out because voice input stopped working.
3. **Never close or cancel main-loop I/O from another loop or thread.** In the HUD
   skill, keep one `httpx.AsyncClient` per event loop (for example a dict keyed by
   loop). Never `aclose()` a client from a loop other than the one that created it. If
   it has to be closed, schedule that on its own loop with
   `asyncio.run_coroutine_threadsafe(client.aclose(), owner_loop)`. Also look for other
   places where skill threads cancel main-loop tasks or close its transports directly.
   This removes the most likely trigger and the reconnect churn.
4. **A newer Python alone probably won't fix it.** Python 3.12 and 3.13 have the same
   `_poll` code, and that code is only wrong when another thread interferes.

## Side issue: tracebacks show the wrong `main.py` source line

Under the frame `File "main.py", line 837, in <module>`, the log prints this source line:

```
"so the capture was refused rather than risk a waypoint 1000x "
```

That text is not in Core. It is line 837 of a custom skill:
`%APPDATA%\ShipBit\WingmanAI\custom_skills\sc_navpoint\main.py`. The frozen Core
records its entry module as plain `main.py`. When a traceback is formatted,
`linecache` looks for a file called `main.py` and finds a skill's file instead.
Every skill's entry file is called `main.py`, so any of them can do this. That means
the source lines shown for Core's `main.py` frames in user logs can't be trusted.
The line number is still correct. The next frame (`run_until_complete`) shows that
line 837 in the 3.2.8 build is the `loop.run_until_complete(...)` call.

Fix: freeze the entry script with an absolute or unique filename, or clear
`linecache` lookups for it.

## Evidence

- `%APPDATA%\ShipBit\WingmanAI\3_2_8\logs\wingman-core.2026-10-18_12-12-28.log`: crash at line ~2785; memory-write failures right after; NavPoint poller and UEX import still logging at 13:45.
- `%APPDATA%\ShipBit\WingmanAI\3_2_8\logs\wingman-core.2026-10-15_19-29-47.log`: same traceback at 21:44:44.
- Core source checked against `wingman-ai` `develop` (merged 2026-10-17): `main.py` (around `loop.run_until_complete`), `hud_server/http_client.py` `connect()` / `disconnect()`, `skills/hud/main.py` `_ensure_connected()` (the installed 3.2.8 copy is the same).
- Sentry is active in Core (`sentry_sdk` shows up in the traceback), so both events may also be in Sentry.
