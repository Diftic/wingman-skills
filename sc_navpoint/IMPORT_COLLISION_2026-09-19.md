# NavPoint / Log Reader import collision — 2026-09-19

The tester could not activate NavPoint: Python resolved `from location_names
import display_name` to SC Log Reader's module. NavPoint's generic import name
could collide through either the shared module cache or the search-path order.
Inserting NavPoint's directory does not override a cached module of that name.

## Fix — v4.9.0.24

- Renamed NavPoint's helper to `navpoint_location_names.py` and updated every
  runtime import, including the delayed site/planet normalization imports.
- Updated both packaging manifests and version declarations.
- The installer checks for the renamed module and removes only NavPoint's old
  `location_names.py` after a successful copy. The other skill is untouched.
- Retained a single installer.bat launcher. A full Wingman restart is necessary
  to discard any old modules already loaded in memory.

This is a targeted fix for the location-name collision, not a conversion of all
NavPoint modules to package-relative imports.

## Evidence

The regression reproduced the tester's exact ImportError before the fix. Both
load-order checks now pass without replacing the foreign module in sys.modules.
The full suite passes: 1,264 tests in 24.64 seconds.

The extracted ZIP passed fresh installation and upgrade from v4.9.0.23 in isolated
AppData. Both load orders passed for the installed files; V8 preprocessing and
inference executed. Sentinel Log Reader code, profile settings and waypoint data
were preserved. All packaged Python files passed Python 3.11 syntax checks; runtime
smoke checks used development Python 3.13.14. The tester's actual Wingman retry
remains to be confirmed.

Artifact: `sc_navpoint_v4.9.0.24.zip` and its `.zip.sha256` checksum in this folder.
Evidence and source backup: `D:/Navpoint-background-20260909/import-collision-20260919/`.
The actual user's installed skill and prior release_version tree were not changed.
