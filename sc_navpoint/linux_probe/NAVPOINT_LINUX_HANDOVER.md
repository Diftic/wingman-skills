# Star Citizen NavPoint on Linux — handover for you and your AI assistant

## Permission from the author

I, **Mallachi** (GitHub: **Diftic**), author of the Star Citizen NavPoint skill for Wingman AI, give **the person
holding this file and the AI assistant working on their computer** (Claude, ChatGPT or any other) **full rights to
edit the NavPoint skill**. You may read, change, fix, rewrite and test any of its files on your machine, without
asking me first.

NavPoint is licensed under the GNU GPL v3 (see `LICENSE` in the skill folder). That licence still applies if you
share copies or changes with others. I would love to get your changes back (see section 10).

— Mallachi, 2026-10-25

---

## 1. To the AI assistant reading this

You are helping a Linux player get **NavPoint 4.10.2.1** working in **Wingman AI** on their computer. The author
develops on Windows and has no Linux machine, so you are the author's hands and eyes on Linux. This file is
everything the author knows. Where it says "not verified", treat it as a hypothesis and check it on the machine.

Work in this order:

1. Read sections 2-5 to understand the skill and where it lives.
2. Find out how this machine runs things (section 6). Wingman may run **natively** or **under Wine/Proton**,
   and the answer changes everything.
3. Set up the test environment and record a **baseline** before changing anything (section 7).
4. Make the fixes in section 8, one at a time. Write or adjust a test first wherever you can, then fix, then re-run.
5. Test live in the game (section 9). Then package the results for the author (section 10).

Ask the user before anything that needs administrator rights (installing system packages) or that touches
files outside the NavPoint and Wingman folders. Follow the ground rules in section 11 at all times.

## 2. What NavPoint is for (intent)

Star Citizen has no way to mark a personal spot and find your way back to it. NavPoint adds that through Wingman AI,
a voice assistant for games:

- The player says "save this spot as Camp" and NavPoint stores their current position.
- Later they say "take me back to Camp". NavPoint shows the distance, and the direction once it has calibrated.
- The direction is shown in an in-game ring overlay (Windows only today) and on a web dashboard, which also works
  on a phone through a QR code.

The position comes from the game itself. With the console command `r_displayinfo 2` Star Citizen draws a small text
panel in the **top-right corner** of the screen listing coordinate "zones". NavPoint screenshots **only that
675x175-pixel corner**, reads the text with a small built-in OCR model, and works out the position.

**Scope, decided by the author:** planet and moon surfaces and open space. Most station interiors are deliberately
refused. Levski is the one supported "site". NavPoint never presses keys or sends any input to the game.

## 3. How it works (mechanics)

### 3.1 The capture pipeline (one reading)

1. `main.py` → `_capture_position_local()` takes a lock, so only one capture runs at a time.
2. `_quiet_capture_attempt()` wraps one `_capture_attempt()`. If the attempt fails for the same reason as the
   previous one, its log lines are dropped and counted instead of written. This stops log spam.
3. `_capture_attempt()` asks the reader for the region: `reader.capture_region(monitor)`, defined in
   `specialist_reader.py`. **Today that uses Windows calls** to check that the foreground window title contains
   "Star Citizen" and to find its client area. It returns the 675x175 block at the right edge of the game window.
4. The region is grabbed with **mss**, converted with **Pillow** and checked with `reader.capture_still_valid()`
   (Windows: the same window is still in front).
5. `frame_reader.FrameAwareReader.read()` runs the **V8 OCR model** (`models/specialist_v8/model.onnx`, through
   onnxruntime on the CPU). Each 13-pixel text band is preprocessed by `specialist_reader.prepare_band()`, which
   uses **OpenCV `cv2.resize`**. The model and alphabet are hash-checked at load; never change them.
6. `active_frame.py` decides which coordinate frame applies from the zone names (`Zone: <name> Pos: x y z`):
   - **planet**: a body's local frame, e.g. `pyro3`;
   - **site**: a named place, today only Levski, `levski_all-001`;
   - **space**: the star system frame (`SolarSystem_<id>` / `Root`).
   Unknown names are refused as `unknown_zone_name`. Names and labels live in `frame_names.json`.
7. `scanner.NavPointScanner.parse_payload()` validates the result into a position dict.
8. `planet_rotation.py` and `site_rotation.py` learn the camera orientation from movement, which the direction
   needs. `navigation.py` turns position + target into distance and direction.

Two loops call this pipeline:

- **Navigation polling** (`_start_nav_polling` → `_nav_polling_loop`) runs on its own thread while a target is
  active. It captures continuously, one reading straight after another (`_get_poll_interval()` returns 0).
- **Background calibration** (`_start_background_calibration`) runs while no target is active, about once a
  second, to keep the orientation fit warm.

Waypoints are stored in SQLite (`database.py`). A waypoint belongs to one frame, and navigation across frames is
refused on purpose.

### 3.2 Voice tools (what Wingman's AI can call)

| Tool | What it does |
|---|---|
| `mark_location(name)` | capture the current position and save it as a waypoint |
| `navigate_to(name)` | start navigation to a waypoint (starts the polling loop) |
| `update_position()` | one fresh reading and a spoken distance |
| `stop_navigation()` | stop navigating |
| `list_navpoints(body)` | list saved waypoints |
| `rename_navpoint(old_name, new_name)`, `delete_navpoint(name)` | manage waypoints |
| `show_navpoint_hud()` | open the dashboard |

No tool takes coordinates as an argument. Every position comes from a capture inside the tool.

### 3.3 Settings (Wingman → the wingman's skills → Star Citizen NavPoint)

| Setting | Default | Meaning |
|---|---|---|
| `display` | 1 | monitor to capture (1 = primary) |
| `arrival_alert_distance` | 1000 m | heads-up distance (0 disables) |
| `arrival_stop_distance` | 250 m | auto-stop distance (0 disables) |
| `overlay_size` | 220 px | ring overlay diameter |

### 3.4 The dashboard

`navpoint_ui/app.py` is a FastAPI/uvicorn server on **port 7869**: `http://127.0.0.1:7869`. About 15 seconds after
start-up, Wingman's chat shows a card with the link and a QR code for phones on the same network.

### 3.5 Files in the skill folder

Runtime (all are needed): `__init__.py`, `main.py`, `active_frame.py`, `coordinate_stack.py`, `database.py`,
`distance_precision.py`, `frame_reader.py`, `frame_names.json`, `learned_fields.py`, `navigation.py`,
`navpoint_location_names.py`, `overlay_fields.py`, `overlay_reader.py`, `overlay_win32.py`, `planet_rotation.py`,
`ring_overlay.py`, `scanner.py`, `site_rotation.py`, `specialist_reader.py`, `telemetry.py`, `default_config.yaml`,
`LICENSE`, `navpoint_ui/`, `models/specialist_v8/` and `_vendor/` (the bundled OpenCV, **a Windows build**).

Development only (in the GitHub repo, not in the release zip): `tests/`, `ocr_dev/`, `update_release.py`,
`skill_installer_config.json`, `installer.bat`, `TESTER_README.md`.

The modules import each other by flat names (`import database`, `import navigation`): `main.py` puts its own folder
on `sys.path`. Another skill with a module of the same name can clash with this. That has happened before, with
SC Log Reader's `location_names.py`.

## 4. Where everything lives (placement)

### 4.1 Source and releases

- Source: https://github.com/Diftic/wingman-skills, folder `sc_navpoint/` on branch `main` (commit `9803948` is
  4.10.2.1).
- Release: https://github.com/Diftic/wingman-skills/releases/tag/sc_navpoint-v4.10.2.1. The zip is
  `sc_navpoint_v4.10.2.1.zip`, SHA-256 `732c0b221872b7ce83484afd61908b590930488162acfc49330c0179344755cc`.
  It is the only place with `_vendor/` (the bundled OpenCV), which is not in git.

### 4.2 Wingman's folders

Wingman finds these with the `platformdirs` library (app name `WingmanAI`, author `ShipBit`).

| What | Windows | Native Linux (expected, not verified) |
|---|---|---|
| Custom skills (NavPoint goes here) | `%APPDATA%\ShipBit\WingmanAI\custom_skills\sc_navpoint\` | `~/.local/share/WingmanAI/custom_skills/sc_navpoint/` |
| NavPoint data: `navpoints.db`, `navpoint_poll.log`, `refused/` | `%APPDATA%\ShipBit\WingmanAI\generated_files\SC_NavPoint\` | `~/.local/share/WingmanAI/generated_files/SC_NavPoint/` |
| Wingman logs: `wingman-core.<date>.log` | `%APPDATA%\ShipBit\WingmanAI\<version, e.g. 3_2_11>\logs\` | `~/.local/share/WingmanAI/<version>/logs/` |

If `XDG_DATA_HOME` is set, it replaces `~/.local/share`. **Under Wine** all paths are the Windows ones inside the
Wine prefix (`drive_c/users/<user>/AppData/Roaming/ShipBit/WingmanAI/...`).

The installer (`installer.bat`, Windows only) copies the runtime files into the custom skills folder, never copies
itself or the readme, and removes an obsolete `location_names.py`. It leaves profiles and the waypoint database
alone. On Linux, copy the files yourself the same way, or write an `install.sh` (task T5).

## 5. Linux status: what is expected to break

None of this has been run on Linux. These are the author's predictions from reading the code:

1. **The skill may not start at all.** `overlay_win32.py` does `from ctypes import wintypes` at import time. On some
   Python versions that raises `ValueError` on Linux, not `ImportError`. `main.py` (around the
   `from ring_overlay import RingOverlay` line in `prepare`) catches only `ImportError`. Check the Wingman log for
   the NavPoint traceback first.
2. **The OCR reader will not load.** `frame_reader.py` puts `_vendor/` on `sys.path`, and `_vendor/cv2` is a
   **Windows** OpenCV (`cv2.pyd`). On Linux, `import cv2` fails, the reader becomes unavailable, and every capture
   fails with kind `no_reader` (the log says "NavPoint local reader unavailable").
3. **Every capture will fail to find the game.** `specialist_reader.capture_region()` and `capture_still_valid()`
   call `ctypes.windll.user32`, which doesn't exist on Linux.
4. **The in-game ring will not appear.** `ring_overlay.py` checks `overlay_win32.IS_WINDOWS` and declines to
   start. That is handled: NavPoint says the ring is still on the dashboard. A Linux ring is optional and later.
5. **Wayland.** NavPoint's capture (mss) and window detection use **X11**. Star Citizen under Wine/Proton is
   normally an X11 window (XWayland), which should work. A game running as a native Wayland client (Wine's Wayland
   driver) or inside gamescope may be invisible to X11.
6. **Wingman under Wine:** if Wingman itself runs under Wine, NavPoint's Windows code runs through Wine and may work
   unchanged. **Try the unmodified release first** in that case.

## 6. Step 1: find out how this machine runs things

A diagnostic skill, **NavPoint Linux Probe**, may have come with this file (`navpoint_linux_probe.zip`). It is
read-only. Install it as described in its `README.txt`, then in game say "Run the NavPoint Linux probe". It writes
`navpoint_probe_<time>.zip` to the home folder, containing:

- `report.json`, whose `verdict` reports Wingman's Python platform (`linux`, or `win32 (Wine x.y)`), the session
  type, whether the active window was seen as Star Citizen, and whether the corner capture was black;
- PNGs of the captured corner.

Its file `navpoint_probe_core.py` has a working-in-principle **X11 window lookup through ctypes** (class `_X11`).
Reuse it for task T3. Also read `system.python` in the report: that is the Python version **inside Wingman**,
which matters for task T2.

Without the probe, collect the same by hand:

- `echo $XDG_SESSION_TYPE $DISPLAY $WAYLAND_DISPLAY`
- how Star Citizen starts (Lutris, Steam/Proton, other);
- whether Wingman is a native Linux app or a Windows `.exe` under Wine (`ps aux | grep -i wingman`);
- the Wingman log after a start with NavPoint enabled.

## 7. Development and test setup

Wingman's own Python is frozen (PyInstaller), so tests run in a separate Python. Ask the user before installing
system packages.

```bash
# 1. Python 3.11 or newer (most distros already have python3):
python3 --version
# 2. Get the source
git clone https://github.com/Diftic/wingman-skills.git
cd wingman-skills
# 3. Private test environment
python3 -m venv .venv
.venv/bin/pip install pytest numpy pillow mss pyyaml fastapi uvicorn httpx onnxruntime opencv-python-headless
# 4. Run the NavPoint suite
cd sc_navpoint
../.venv/bin/python -m pytest -q -p no:cacheprovider tests
```

The tests stub out Wingman's runtime (`tests/_stubs.py`, `tests/conftest.py`), so Wingman itself isn't needed.
The `_vendor/` folder isn't in git. Get it from the release zip only if a test asks for it.

**Record the baseline before changing anything.** On the author's Windows machine the suite gives about
**1234 passed, 4 failed**. All four are environment gaps: OpenCV/numpy missing in a helper process, and
untracked real screenshots. On Linux, expect extra failures from Windows-only tests (the overlay and frozen-OpenCV
loader tests). Write the baseline down, so you can tell your regressions from pre-existing ones.

## 8. The fixes, in order

Work on a branch: `git switch -c linux-support`. Keep each task small. Re-run the full suite after each one.

**T1. NavPoint loads on Linux.** Make the ring-overlay import failure non-fatal: catch `Exception` in `main.py`'s
ring start, or guard the `wintypes` import in `overlay_win32.py` so non-Windows platforms only set `IS_WINDOWS = False`.
*Done when:* the Wingman log shows `Skill 'SC_NavPoint' validated and prepared` and the dashboard opens at
`http://127.0.0.1:7869`.

**T2. The OCR reader loads (OpenCV).** NavPoint needs `cv2.resize` with its default interpolation. Do not swap
it for Pillow or numpy, because the model was trained on OpenCV's exact pixels.
- If Wingman's Python already provides `cv2` (the probe reports it), stop `frame_reader.py` from putting the
  Windows `_vendor` first.
- Otherwise ship a Linux build: an `opencv-python-headless` manylinux wheel matching **Wingman's** Python version
  and CPU, unpacked into a separate folder such as `_vendor_linux/`. `frame_reader.py` then picks the folder by
  `sys.platform`.
- Re-apply the small loader patch described in `_vendor/NAVPOINT_PATCHES.md` (frozen NumPy 2 compatibility).

*Done when:* the reader loads without "NavPoint local reader unavailable", and
`tests/test_specialist_reader.py::test_preprocessing_matches_training_shape_and_normalization` passes.

**T3. Find the game window on Linux.** Give `capture_region()` and `capture_still_valid()` in `specialist_reader.py`
a Linux branch:
- `_NET_ACTIVE_WINDOW` on the root window;
- its `_NET_WM_NAME`/`WM_NAME` must contain "star citizen" (case-insensitive);
- the client geometry via `XGetGeometry` + `XTranslateCoordinates`;
- region = `left = x + width - 675`, `top = y`, `width = 675`, `height = 175` (the `capture_height` attribute);
- `capture_still_valid()` compares the active window id.

Put the X11 code in a new module, e.g. `window_x11.py`, based on the probe's `_X11` class. **Add every new runtime
file to both `RELEASE_FILES` in `update_release.py` and `files` in `skill_installer_config.json`.** Tests check that
the two lists agree, and a missing file has broken releases before. Raise the same `RuntimeError("Star Citizen is
not foreground")` for the not-focused case. `tests/test_capture_log_quiet.py` and existing log searches expect that
exact text.
*Done when:* with SC focused and `r_displayinfo 2` on, `navpoint_poll.log` shows successful captures instead of
`no_grab`.

**T4. The text reads correctly.** Compare what the OCR reads with what is on screen; the probe's PNGs or the
`refused/` frames help. If Wine/Proton renders the panel differently (scaling, fonts, colours) and the OCR misreads
it, **don't retrain or replace the model**. Collect example frames and report back (section 10).

**T5. Install script (optional).** An `install.sh` that does what `installer.bat` does: verify that the package is
complete, copy everything except the installer and readme into the custom skills folder, remove the obsolete
`location_names.py`, and leave data and profiles alone.

**T6. Version and notes.** Bump the 4th number for Linux work: `4.10.2.1` → `4.10.2.2`. Update it in `main.py`
(docstring line and `VERSION`), `__init__.py`, `default_config.yaml`, `skill_installer_config.json`, and the
assertions in `tests/test_version_49022.py`. Add a short "New in" note to `TESTER_README.md`. Leave the first three
numbers alone: they mean "built for Star Citizen 4.10.2".

## 9. Live test checklist

Before you start, back up `navpoints.db` from the NavPoint data folder (section 4.2).

1. Close Wingman completely. Copy the changed runtime files into the custom skills folder (section 4.2).
2. Start Wingman. In the log, check that NavPoint loads and look for any NavPoint traceback.
3. Start Star Citizen, enter `r_displayinfo 2`, and keep the game focused.
4. Say "save this spot as Test". It should succeed and name the location.
5. Walk or fly about 100 m away. Say "navigate to Test". Distance appears on the dashboard.
6. Move around in more than one direction: the direction appears once calibration is ready. Check that it points
   the right way.
7. Switch away from the game for a minute. `wingman-core.*.log` must get **one** "screen grab failed" line, not one
   per second. `navpoint_poll.log` should show "previous refusal repeated N more time(s)" when you return.
8. Say "stop navigation".
9. Repeat on a planet surface and once in open space.

## 10. Sending the results to the author

Send to Mallachi through a GitHub issue or pull request on https://github.com/Diftic/wingman-skills, or however the
user is in contact:

- the branch as a pull request, or a patch: `git format-patch main --stdout > navpoint-linux.patch`;
- the test results before and after (the pass/fail summary lines);
- `navpoint_probe_*.zip` (if used), and the relevant parts of `wingman-core.*.log` and `navpoint_poll.log`.
  Replace the user's home path with `~`;
- how SC and Wingman run on this machine (native/Wine, X11/Wayland, distro, desktop).

Do not publish releases or packages in the author's name. The author builds and publishes releases.

## 11. Ground rules (from the author)

- **Never send input to the game:** no key presses, no console commands from code. Tests guard this
  (`test_main_has_no_console_input_capability`, `test_overlay_never_sends_input_to_the_game`).
- **Capture only the overlay corner,** never the full screen. Never upload or transmit captures.
- **Never delete or overwrite the user's waypoint database** (`navpoints.db`). Back it up before live tests.
- **Don't change the OCR model or its alphabet** (`models/specialist_v8/`). They are hash-checked at load.
- **Keep the logs quiet:** one line per change of state, never a line per second.
- **Keep the Windows build working.** Linux code goes in branches or modules chosen by `sys.platform`; Windows
  behaviour must stay byte-for-byte the same. Run the whole suite, not just your new tests.
- Keep the skill small. Fix what is needed for Linux; don't redesign it.
- Report honestly: say what you verified and what you didn't.
