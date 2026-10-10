# SC NavPoint — Devlog

## Version: 4.8.0.0 (Star Citizen 4.8.0 live-test baseline, 2026-05-25)

Adopted the SC-patch versioning convention from
[`skills/Versioning.md`](../Versioning.md) and bumped to `4.8.0.0` for the
cross-skill 4.8.0 live-test baseline. Populated `__init__.py` with
`__version__` / `__sc_target_version__`; replaced the module-level
`SKILL_VERSION` constant with `VERSION` / `SC_TARGET_VERSION` class attributes
on `SC_NavPoint`; updated module docstring.

**CAVEAT — the version bump does NOT mean the skill is requalified.** The
OUTDATED status below still applies: Vision AI parsing of `r_displayinfo 4`
and per-server storage have not been re-validated against the 4.7+ client.
The version is being aligned now for SC-version-comparison consistency; an
end-to-end revival pass is still required.

## 2026-07-11 — Decision: INDEFINITE HOLD until planet-tech releases

Same-day follow-up to the field test below. Decision by Lars: the surface-only
pivot is shelved until CIG ships planet-tech (his estimate: late 2026 to early
2027). Rationale: no point building against the current overlay and coordinate
frames when planet-tech may rework them within 4-6 months; the Vision AI
recalibration is the expensive part and would likely have to be redone.

The field-test findings below remain the requalification baseline: on planet-tech
release, re-run the stationary frame test first (stellar vs local, static vs
dynamic), then resume the pivot checklist in TODO.md if local frames still hold.

## 2026-07-11 — Field test: coordinate frames on SC 4.8.x live — verdict: pivot to surface-only

In-game stationary test by Lars (stand still, watch `r_displayinfo` XYZ over time):

- The overlay now shows **two coordinate sets**: stellar and local.
- **Stellar coordinates are dynamic** even while standing still, because planets and
  moons rotate on their axis. A stored stellar XYZ goes stale continuously.
- **Local coordinates (on a planet or moon surface) are static.** A stored local XYZ
  remains valid over time.
- Forward-looking (CIG planet-tech, unreleased): moons will orbit planets and planets
  their star, making stellar coordinates even more dynamic. Lars's estimate from current
  dev speed (2026-07-11): initial release late 2026 to early 2027, with the actual
  content of the first patches highly debatable. Local (body-fixed) frames should be
  unaffected by orbital motion, so the surface-only pivot is expected to survive
  planet-tech (assumption, re-verify on release).

**Decision** (rule agreed 2026-07-11: dynamic frame → not viable, static frame →
highly valuable): the skill pivots to **surface-only waypoints in the local frame**.
Stellar-frame waypoints are permanently out of scope; locations in open space cannot
be annotated. Within that scope the skill is considered highly valuable and moves
from "on hold" to active requalification.

**Proposed revival direction (not yet implemented):**
- Rework the Vision AI extraction to target the LOCAL coordinate set only, and to
  refuse capture when no local frame is present (open space).
- Recalibrate scanner prompts against the 4.8 overlay layout (screenshots needed:
  one on-surface, one in space, one in flight above a surface).
- Verify heading semantics in the local frame before trusting the bearing/compass math.
- Test whether local coordinates are identical across servers; if the local frame is
  deterministic per body, per-server keying can likely be dropped (hypothesis, unverified).
- Test whether local coordinates remain available while flying above a surface
  (in the planet's physics grid); determines if in-flight guidance toward a surface
  waypoint is possible or if guidance starts only after landing zone entry.

## Status: OUTDATED — pre-SC 4.7 (2026-04-25)

This skill was built before Star Citizen patch 4.7, which delivered a major overhaul
of navigation points. The Vision AI parsing of `r_displayinfo 4` and the per-server
storage assumptions were calibrated against the pre-4.7 client, and have not been
re-validated against 4.7. Treat any waypoints, bearings, and zone/planet info this
skill produces as suspect until verified.

`auto_activate` has been turned off so the skill no longer loads by default — enable
it explicitly only when re-validating.

**To revive:** re-run end-to-end against SC 4.7, confirm Vision AI still extracts the
expected fields from `r_displayinfo 4` (overlay layout may have shifted), validate
bearing math against in-game distances, update Devlog status, and remove the
"Outdated" tag from `default_config.yaml`.

---

## v1.0.0 — 2026-03-20 — Initial release

### Overview
Mark and navigate to custom waypoints in Star Citizen using r_displayinfo 4 position data.
Vision AI extracts XYZ coordinates, zone, planet, system, and server ID from the live screen.

### Architecture

**Files:**
- `main.py` — SC_NavPoint skill class; 9 @tool methods
- `scanner.py` — mss screen capture, dual-image b64 encoding, LLM message builder, JSON parser
- `database.py` — SQLite CRUD (`navpoints` table); per-server storage
- `navigation.py` — bearing math, format_distance(), turn/elevation instruction generators
- `navpoint_ui/app.py` — FastAPI server (port 7869); REST API for waypoints + nav state
- `navpoint_ui/window.py` — stdlib webbrowser opener
- `navpoint_ui/static/` — SPA: waypoint list (left panel) + navigation compass (right panel)

**Tools (voice commands):**
| Tool | Trigger phrases |
|---|---|
| `enable_displayinfo` | "enable position overlay", "activate r_displayinfo" |
| `disable_displayinfo` | "disable position overlay", "hide debug overlay" |
| `mark_location` | "mark location", "drop waypoint", "save position" |
| `navigate_to` | "navigate to X", "guide me to X" |
| `update_position` | "update position", "refresh bearing", "how far" |
| `stop_navigation` | "stop navigation", "cancel navigation" |
| `show_navpoint_hud` | "show navigation HUD", "open waypoints" |
| `list_navpoints` | "list waypoints", "show saved locations" |
| `delete_navpoint` | "delete waypoint X" |
| `rename_navpoint` | "rename X to Y" |

### Key Technical Decisions

**Dual-image Vision AI extraction**
Send two images per LLM call: full screenshot (context, low detail) + top-right 45%×55%
crop (high detail). The crop isolates r_displayinfo without noise from the rest of the screen.
Crop is upscaled to 900px wide if smaller — improves text legibility on high-res displays.
Pattern proven in old SC_MiningAssistant (solved GPT-4o-mini inconsistency on tiny overlay text).
Learning from SC_Signature_Scanner: crop to the region of interest before OCR.

**Auto-polling loop**
`navigate_to()` calls `_start_nav_polling()` which launches an `asyncio.Task`.
The task loops every N seconds (configurable 1–10s, default 5s):
- Capture screen → extract position → `ui_server.set_position()` → increment `_update_token`
- Frontend polls `/api/nav/state` every 2s → sees token change → recalculates bearing → redraws compass
Stops on: `stop_navigation()`, `delete_navpoint()` (active target), `unload()`, or target cleared.

**Console command automation**
`_send_console_command(cmd)` async helper:
```
tilde → sleep 0.5s → unicode_typewrite(cmd) → enter → sleep 0.2s → tilde
```
Uses `pydirectinput.unicode_typewrite()` (already a Wingman dependency).
All calls via `asyncio.to_thread()` to keep the event loop unblocked.
Star Citizen must be the focused window when called.

**Coordinate system**
SC uses X/Z for horizontal plane, Y for vertical. Bearing: `atan2(dx, dz)`.
Heading offset from current heading for the compass arrow direction.

**Port assignment**
7862=hud, 7863=accountant, 7864-7867=log_reader, 7868=mining, 7869=navpoint

### Configuration
| Property | Default | Description |
|---|---|---|
| `display` | 1 | Monitor to capture (1-based) |
| `poll_interval` | 5 | Auto-tracking refresh interval in seconds (1–10) |

### Known Limitations / Future Work
- Coordinate units from r_displayinfo vary by game version — navigation math works correctly
  as long as both stored and current positions use the same unit (they always will)
- No "arrived" notification when within a threshold distance of the target
- No support for multiple active targets / route waypoints
- SC console key (tilde) is hardcoded — could become a configurable property if needed
