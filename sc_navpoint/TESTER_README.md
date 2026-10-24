# Star Citizen NavPoint — live-test package

Version 4.10.2.1, targeting Star Citizen 4.10.2. Prepared for Wingman AI 3.2.x
(loads on 3.2.11) on 64-bit Windows. This package includes the V8 OCR model and
bundled OpenCV; no separate Python installation is needed for the batch installer.

New in 4.10.2.1:

- Quieter logs. A capture that keeps failing for the same reason (game not
  focused, position panel off) is logged once, not every second. When the
  reason changes or a capture succeeds, one line says how many repeats were
  skipped. Before this, an evening with the game in the background wrote
  thousands of identical warnings to the Wingman log.
- Shorter skill description. The guidance that keeps saved waypoints apart
  from the route planner and HUD info cards now sits in the skill prompt.

NavPoint is meant for planet and moon surfaces and open space. Most station
interiors are refused with a message; Levski remains a supported site.

This release uses Wingman's Skill API v3 threading and speech interfaces.
Wingman AI 2.1.1 is no longer a supported target for this package. The web
dashboard keeps SC Accountant's operations-desk style.

NavPoint now activates automatically when Wingman starts, once enabled for your
wingman. Its compact dashboard card appears about 15 seconds later, with one
computer link and a phone/tablet QR code matching Accountant's size. The phone
or tablet must be connected to the same network; its address is inside the QR.

This includes the previous SC Log Reader import-collision fix. The installer
removes NavPoint's obsolete location_names.py; SC Log Reader is unchanged.

## Install

1. Fully close Wingman AI, including its system-tray process.
2. Extract the entire ZIP to a normal folder.
3. Double-click **installer.bat** as your normal Windows user.
4. Restart Wingman AI and enable **Star Citizen NavPoint** for your wingman.
5. In the Star Citizen console, enter `r_displayinfo 2` yourself. Keep the game
   focused with its position panel visible. Select the correct display in the
   skill settings if you use multiple monitors.

The installer copies the skill into
`%AppData%\ShipBit\WingmanAI\custom_skills\sc_navpoint` and refreshes its bundled
defaults. Your Wingman profile settings and saved waypoint database are stored
elsewhere and are not changed by the installer.

## Try it

- Ask your wingman to save your current position, then navigate back to it.
- The navigation ring shows direction and distance. Calibration needs useful
  movement; stationary waiting alone does not establish a heading. At a site
  such as Levski, move in more than one direction before checking the dot.
- Use the dashboard link or QR code displayed by NavPoint to view saved locations.
- If scans fail, the last valid dot is held. ERROR appears after eight consecutive
  failed readings. A held dot is not a fresh direction reading.

## Test status

This is a package for live testing. Automated checks do not establish live
navigation accuracy. Corrected Levski alignment still needs a flight test after
restarting Wingman; compare the selected target, distance and direction visually.

If installation fails, keep the error text from the installer window. For runtime
issues, include the relevant Wingman log and what you were doing at the time.
