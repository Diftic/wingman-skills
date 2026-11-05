# Getting NavPoint's data without a visible r_displayinfo (2026-10-26)

Research only. No code changed.

## What NavPoint needs

From `screenshots/overlay-field-inventory-2026-07-13.md` and `coordinate_stack.py`:

1. **Position**: the Zone stack (local `OOC_*` row, SolarSystem, Root) or `CamPos Planet Zone`.
2. **Body identity**: the `OOC_<body>` token, which is also the local-frame gate.
3. **Heading**: `CamDir` (level 2+), for the bearing ring.
4. **Time**: rotation fitting (`planet_rotation.py`) already pairs local and Root rows over time.

Any replacement has to cover all four, or say which feature it drops.

## Options

### A. Keep reading the overlay, hide it from the player (Windows Graphics Capture + cover)

**REJECTED by the user (2026-10-26):** covering the overlay with a panel just swaps one screen
intrusion for another. Kept below for the record only.

Today `specialist_reader.capture_region` grabs **screen** pixels (`mss`), so anything drawn over the
overlay would be read too. Windows Graphics Capture (WGC) instead captures **one window's own surface**,
by HWND, including when other windows cover it ([WgcSharp](https://www.nuget.org/packages/WgcSharp)
states this; DXGI desktop duplication cannot). So NavPoint could:

- capture the SC window via WGC (Python binding: [windows-capture](https://github.com/NiiightmareXD/windows-capture), MIT, Rust-backed);
- draw an opaque, click-through, topmost panel over the top-right overlay block. NavPoint already does
  topmost overlays in `overlay_win32.py`. The panel can be styled as an in-game MFD, or show NavPoint's own
  readout (target, distance, ETA) in the space the overlay takes up.

Keeps **all four** fields, keeps the V8 OCR, and the work stays local to the capture function.
Costs: the corner is still covered (by something that looks like part of the game rather than debug text),
plus a new native dependency.

Unverified, and the project depends on it:
- that WGC returns SC's frame (Vulkan, borderless) while it is covered. OBS window capture over WGC works
  for many games, but I found no SC-specific confirmation;
- whether WGC's yellow capture border can be turned off (needs Windows 10 2104+ / Win 11 and
  `IsBorderRequired = false`; the library has a `DrawBorderSettings` option);
- what happens in exclusive fullscreen. SC normally runs borderless; the overlay ring already depends on that.

### B. `/showlocation` clipboard (position only)

Typing `/showlocation` in chat copies global (Root-frame) coordinates to the clipboard. Long used by
[Valalol's navigation tool](https://github.com/Valalol/Star-Citizen-Navigation) (partly deprecated),
[Project Jericho](https://github.com/Graupunkt/project-jericho) (now [starmap.space](https://starmap.space/about-jericho.php), updated 2026-01) and
[a show-location autotyper](https://github.com/MandoRick/Star-Citizen-Show-Location-Automation).
Wingman can send the keystrokes itself.

- **No heading** (the user's point): no `CamDir`, so no bearing ring as built.
- **No body identity** and **Root frame only**: body-local XYZ needs the planet rotation angle at the
  moment of the copy. `planet_rotation.py` fits that from local/Root pairs, but those pairs come from the
  overlay. Jericho needs per-body rotation constants plus server-time calibration and quotes ~15 m.
- Each read opens chat and prints a line: a smaller break in immersion, but the overlay is gone. Too
  slow and noisy for 1 Hz polling, fine for "mark this spot".
- TESTED 2026-10-27 on Hurston (4 copies, `telemetry_dev/showlocation_2026-10-27.jsonl`): format
  `Coordinates: x:<m> y:<m> z:<m>`, 6 decimals, **system frame** (x ≈ 12.85e9 m = Hurston's distance from the star; while
  hovering still it moved 514 m/s with the planet's rotation, and z stayed constant to 2 cm).

### C. Heading without CamDir

- **Course over ground**: bearing from two successive positions. Correct when moving forward; wrong when
  hovering, strafing or drifting. Gives an "arrow relative to travel direction", not "relative to the nose".
- **Absolute bearing instead of relative**: position alone gives the compass bearing to the target in the
  body's local frame ("target bearing 245, 3.2 km"). The player steers with the in-game HUD or compass.
  No heading needed, and the voice output stays immersive. The ring would become a compass rose.
  Not checked: what heading readout the 4.10 ship HUD and FPS visor show (search found nothing reliable).

### D. Game.log: ruled out

Scanned this machine's recent Game.logs (build 12913470, 23-25 Oct). The only coordinate-looking lines
are mission marker `ZonePos`/`position` fields (all 0,0,0 in the sample) and spawn errors. Location
changes are names only (`RequestLocationInventory`). No player position or heading.

### E. Memory reading, packet sniffing: ruled out

EAC and the ToS, and both would break with every patch.

### F. Localization tokens (user's idea: put CamDir/coordinates into a string the HUD already shows)

Scanned the stock 4.10.2 `global.ini` (`global.ini.bak` beside the user's override, 90,437 lines) and
`Bin64\StarCitizen.exe` (strings only, read-only):

- **The r_displayinfo text cannot be moved, restyled or reused through localization.** Its format strings are
  hard-coded in `C3DEngine` (`CamDir: %3d %3d %4d FOV: %.0f ...`, `Zone: %s Pos: %s %s %s`,
  `CamPos Planet Zone: %f %f %f`, `Current player location : %s`). They are not `global.ini` keys.
- **Tokens are resolved by context-bound handlers** (`ResolveExtendedTextSymbol`): `~mission()` (mission
  variables, ~9,900 uses), `~action()` (key binds), `~law()`, `~serviceBeacon()`, `~quantumLink()`
  (quantum calibration notifications), `~playerTrade()`, `~image()`/`~icon()`, `~shopInteractionData()`,
  `~rentalNotification()`, plus `~playername()`, `~bedroom()`, `~padnumber()` (only in CIG's test string
  `LOC_TESTJOURNALPARSING`). Each one reads its own object (the mission, the beacon, the shop), and none
  takes the player's position or camera. The closest are `~serviceBeacon(DistToInitiator)`, a distance to
  another player's beacon, and `~mission(...)` location names. **So no string can be made to print CamDir or
  coordinates.** Not checked: `~mission()` variables that might carry a position. They come from mission
  data, not the player.
- **Leads found on the way:**
  - The chat slash commands in the binary are `whereis`, `kick`, `serverstats`, `showlocation`, `kill`,
    `joininstance`, `joinplayer`, plus a `slash.displaylocation` response. `whereis` is untested; it is
    probably a player lookup.
  - The `/showlocation` output format is `Coordinates: x:<n> y:<n> z:<n>`, posted as a chat line
    (`[showlocation]: %s`).
  - Cockpit MFD panel titles include `UI_MF_Panel-Title_Heading=Heading`, plus `hud_pitch`, `hud_yaw`
    and `hud_AltitudeTitle`. Some ships may show a native heading readout on an MFD, which can be read
    with OCR without any debug text. What that panel binds to is defined in the Building Blocks UI data
    inside `Data.p4k` (not extracted).

### G. Building Blocks UI data (Data.p4k, 4.10.2 LIVE)

Extracted `Data/Game2.dcb` (DataCore, 337 MB) to scratch with `unp4k.exe` v3.13.66 (substring filter
`.dcb`). The sc-bridge `scdatatools` copy cannot open this p4k ("Corrupt extra field 0001"). Building Blocks
UI records live inside the DataCore, not as loose files. I read them from its string table (the bindings sit
next to their record path); I did not parse them record by record.

- **The MFD "Heading" panel binds to nothing.** `@UI_MF_Panel-Title_Heading` belongs to
  `f_fluffscreens/fm_modular/fmp_panels/rsi/fmp_rsi_v1_helm.xml`, a decorative RSI helm screen made of
  looping textures (`fm_aegs_helm-map-animation-0N.tif`, `FM_RSI_Helm_Radar_Animation.tif`). The
  `UI_MF_Data_Complex-Coordinates_N` strings are fake greeble text (`n677.a.+m79`). Dead end.
- **There is a real compass on the HUD:** `h_hud_visor_components/hc_hud_compassstrip.xml`, bound to
  `flightController.heading` and `/CompassStrip/yawAngle`, with numbered ticks (`TickText2/5/8/11`) and
  cardinal labels from localization (`@flightHUD_Label_Cardinal_N`, `_NE`, `_E` ...). The ship HUDs also have
  `hc_hud_ship_compass_master.xml` and a `hud_generic_headingtapecomponent.xml` (Gladius heading-tape art).
  Related bindings: `flightController.pitch`, `.horizonRoll`, `.altitude`, `.isOnPlanet`.
  - This is the in-game heading the compass-guidance plan (B + C) needs: NavPoint says "steer 245" and the
    player reads it off the native strip.
  - It is also a possible immersive heading **source**: OCR of the native compass strip instead of `CamDir`.
  - Only labels can be changed (the cardinal letters through `global.ini`); the layout is packed in the p4k.
  - Not verified in game: when the strip is visible (on foot, in a seat, every ship?), and whether
    `flightController.heading` follows the nose or the travel direction, and which north it uses.
- **Lat/long readouts exist, but only on map screens:**
  - the radar/starmap navigation grid: `CrosshairCoordinatesLatitude/Longitude`, `ShowCoordinates`
    (`rc_radarmapscreen_navigationgrid.xml`);
  - the selected object: `SelectedObjectLatitude/Longitude/Distance` and
    `StarMapData/SelectedMarkerDetail/ReferenceObjectRelativeLatitude/Longitude/Distance`
    (`rc_radarmapscreen_navigation.xml`).
  Opening the map is in-fiction, so OCR there would be immersive, but only on demand, not continuous.
- **The game has native Personal Markers**: `Maps_Header_Pins=Personal Markers`, `Place Pin`,
  `Set Marker Details`, a `Marker Databank`, and pin fields `entryLocation`, `entryCoordinates` and
  `entryDatetime`, all under `InteriorMapData/pinData/` (`rc_radarmapscreen_markerdatabank.xml`). The
  namespace suggests interior maps, which may be all it covers. Nothing about them in Game.log (25 recent
  logs). Not verified: whether pins work outdoors on planets and get a HUD marker. If they do, they overlap
  with NavPoint's core feature.

**User feedback on G (2026-10-26):** the HUD compass is fixed to the ship's nose and leaves view when the
player looks around, so cockpit-fixed readouts are no good as a source. Map lat/long is "map helper",
not GPS. Personal Markers have never worked in 10 years; if they did, NavPoint would not be needed.

### H. The game ships a gRPC telemetry API (`sc.game.telemetry.v1`)

Found in `Bin64\StarCitizen.exe` (4.10.2, build 12913470). The full decoded schema is in
`SC_TELEMETRY_API_4.10.2.proto.txt` beside this note, decoded from the embedded protobuf descriptors.

- **Service:** `GameTelemetryService.TelemetryStream(TelemetryStreamRequest{})`, which returns a server
  stream of `TelemetryStreamResponse { vehicle, weapons, events, actor, force_feedback, turret }`. A config
  string says "Per-client stream write interval ... 50 = ~20Hz". The server class (`CGameTelemetryServer`)
  logs "Client connected (id=.. total=..)".
- **What it carries:**
  - `VehicleFlightInstruments`: speed, hydrogen/quantum fuel, g-meter, boost, altitude, radar_altitude, vertical speed,
    atmospheric density, **heading**.
  - `VehicleState`: name, class, manufacturer, type, lights, doors, annunciators (PWR/WPN/THR/SHLD/COOL/QDRV/RADR/PROX/HIT/MISL),
    power state (powerplants, engines, weapons, coolers, life support, gravity, sensors, shield gens/emitters).
  - Flight settings: coupled, ESP, G-safe, cruise, speed limiter, proximity assist, wind compensation and more.
  - Gear, VTOL and transformation deployment state.
  - `WeaponsFrame` (preset, per-weapon powered/ready, countermeasures).
  - `ActorFrame`: vitals (health, O2, hunger, thirst, body temp, heart rate, gravity, pressure, intoxication),
    locomotion (on foot/EVA/seated), crew role, seat, **UEC balance**, environment (temperature, radiation,
    breathable).
  - `EventsFrame`: spawn, dead, enter/leave seat, respawn, downed.
- **What it does NOT carry: no position, no camera direction, no body/zone.** `heading` is the vehicle's
  (seated only), with unknown reference. Gaps in field numbers (response 1-2, `VehicleFrame` 1, vitals 6,
  force feedback 1) suggest removed or reserved fields. A position may have been taken out deliberately.
  That is speculation.
- **How it is switched on (unverified):** the binary's services config has
  `grpc.client.server.enabled` ("Boolean telling whether grpc services are hosted"), with default address
  `grpc.client.server.address = 127.0.0.1:2942`. The same setting can be given as env var
  `GRPC_CLIENT_SERVER_ENABLED`, a `grpc-client-server-enabled` CLI form, or an `sc-services.json` file
  (none in this install). No "Service registered" line appears in this machine's logs, so it is probably
  off by default. The stream code also looks for an `authorization: Bearer` header, so it may need a
  token. Every session logs "Initializing game telemetry component of local player [Haptic]".
- **Separate, older path:** the D-BOX LiveMotion feed. The game loads D-BOX's DLL, which sends gRPC/TLS to
  127.0.0.1:61666. [SC-Motion-Haptic-Bridge](https://github.com/DMUSER15/SC-Motion-Haptic-Bridge) captures it by
  replacing D-BOX's certificate (ToS/EAC status unknown, per its author). That feed is 6DOF motion and haptics, not position.

For NavPoint, H does not solve position or camera heading. It could give **vehicle heading and altitude**
without OCR, which supports compass-style guidance while seated. For the other project (HUD and ship-systems
state) it is close to ideal: power, annunciators, flight modes, gear, doors, lights, weapons, vitals.

## Direction agreed with the user (2026-10-26, latest)

**Scope: vehicles and ships only.** Walking players are out of scope.

Design: car-style sensor fusion, with no debug overlay.
- **Fix:** `/showlocation` (Root frame, converted to body-local with per-body rotation), taken rarely: at
  start, every 30-60 s, and on request.
- **Between fixes:** dead reckoning from telemetry `speed`, `heading` and `vertical_speed_indicator`
  (~20 Hz). That is one integration step instead of an accelerometer's two, so drift stays low.
- **Checks:** `g_meter` spikes and `altitude`/`radar_altitude` trigger or sanity-check a new fix.
- **Guidance:** relative to the telemetry heading (the ship's nose), so a ring or voice "turn left 30" works again.

Prove first, in game:
1. DONE 2026-10-26 (live tests 1-2, see the handover): the stream turns on via the env var
   `GRPC_CLIENT_SERVER_ENABLED=true` passed through the RSI Launcher (`telemetry_dev/launch_with_telemetry.ps1`),
   on `127.0.0.1:2942` with no token, at ~17-18 Hz. `heading` is 0-360° clockwise, follows the ship's nose (it
   tracked a 90° yaw at speed 0), and matches the HUD compass (304.28 vs 304). It is only present inside a
   planet's frame (from ~50 km altitude); in open space it is absent and altitude is FLT_MAX;
2. DONE 2026-10-27: `/showlocation` works on 4.10.2 with 6 decimals in the system frame (see section B). Still open
   only: how disruptive one call feels in flight (chat focus takes the controls);
3. per-body rotation rates are available (likely in `Game2.dcb`, not yet checked).

## Recommendation (superseded by the agreed direction above)

Nothing found gives heading without something on screen. What is left is the user's own framing:
**spam `/showlocation` for position + tell the player a compass heading to fly** (B + C), with the
overlay kept as an opt-in "precision mode" for the existing ring.

To check in game before building it:
- the 4.10.2 clipboard format and how often `/showlocation` can be sent before chat spam or throttling
  becomes a problem;
- whether the ship HUD and FPS visor show a compass the player can steer by;
- Root-to-local conversion without overlay pairs: per-body rotation constants plus a time reference.

## Next step

User decides whether to pursue B + C. If yes, step one is a single in-game `/showlocation` test.
