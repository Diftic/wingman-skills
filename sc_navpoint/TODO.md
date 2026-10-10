# SC NavPoint — TODO

## Status
ON INDEFINITE HOLD until planet-tech releases (decided 2026-07-11; release
estimated late 2026 to early 2027). The 2026-07-11 field test on SC 4.8.x live
confirmed the viable design: surface-only waypoints in the static local frame
(stellar coordinates are dynamic and permanently out of scope). Building now is
not worth it because planet-tech may rework the overlay and frames within
months, forcing a redo of the Vision AI recalibration. On planet-tech release:
re-run the stationary frame test, then work the Pivot Tasks below if local
frames still hold. `auto_activate` stays disabled.

v4.8.0.0 — version aligned to SC 4.8.0 live-test baseline (paperwork bump
only; code is still the pre-4.7 implementation until the pivot lands).

## Pivot Tasks (blockers first)
- [ ] Collect 4.8 overlay screenshots: on-surface, in open space, in flight above
      a surface (needed to recalibrate the Vision AI extraction prompts)
- [ ] Rework scanner extraction to read the LOCAL coordinate set only; refuse
      capture when no local frame is present (open space)
- [ ] Verify heading semantics in the local frame; validate bearing/compass math
      between two known surface points
- [ ] Test cross-server stability of local coordinates (if identical, drop
      per-server keying — hypothesis, unverified)
- [ ] Test local-frame availability while flying above a surface (determines
      whether in-flight guidance toward a surface waypoint is possible)
- [ ] Update default_config.yaml description/tags and remove Outdated markers
      only after end-to-end re-validation

## Verified Patterns
- sys.path.insert pattern required for all sibling imports (confirmed working)
- @tool decorator supports async methods (confirmed in vision_ai skill)
- pydirectinput.unicode_typewrite() handles space and underscore correctly
- asyncio.to_thread() wraps blocking pydirectinput calls safely
- mss screen capture + PIL.Image.frombytes("RGB", ..., "raw", "BGRX") pattern from vision_ai skill
- FastAPI explicit static route (no aiofiles) from sc_accountant pattern

## Testing Checklist
- [ ] mark_location — r_displayinfo 4 visible, captures correct XYZ
- [ ] mark_location — no r_displayinfo, returns helpful error
- [ ] navigate_to — bearing calculation, compass arrow direction
- [ ] Auto-polling — compass updates every 5s without voice command
- [ ] stop_navigation — polling task actually cancels
- [ ] enable_displayinfo — tilde opens console, command typed, console closes
- [ ] disable_displayinfo — same sequence, r_displayinfo 0 sent
- [ ] HUD — waypoint list renders, server filter works, compass draws
- [ ] HUD — click waypoint → set as nav target → compass updates
- [ ] poll_interval setting — change to 2s, confirm faster updates
- [ ] Per-server filtering — waypoints correctly tagged with server_id

## Known Issues
- None yet (untested in game)

## Planned Features
- Arrival alert: notify player when within X km of target (threshold configurable)
- Console key configurable (some SC players rebind tilde)
- Bundle MinersRefuge coordinate data to identify nearest known location to any navpoint
