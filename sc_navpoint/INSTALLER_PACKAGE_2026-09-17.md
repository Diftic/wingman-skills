# NavPoint installer package — 2026-09-17

Artifact: `sc_navpoint_v4.9.0.23.zip` beside this file, with a `.zip.sha256`
checksum. Extract it and run `sc_navpoint/installer.bat`.
Updated September 18: removed the redundant alternate launcher and rebuilt the ZIP.

The package uses their normal-user AppData/Robocopy installation pattern. It
refreshes shipped defaults, leaves external profiles and waypoint data alone,
reports Robocopy failure codes and checks essential payload files before copying.
Instructions are in the packaged `TESTER_README.md`.

Only V8 model assets are shipped. The source's older research models, tests,
recordings, glyph bank and personal data are excluded. Bundled OpenCV retains its
license/provenance files and frozen-NumPy loader patch.

## Verification

- Extracted ZIP integrity checked; all installed runtime bytes matched source.
- Fresh install and update through the alternate launcher passed in isolated
  AppData, including a path with spaces and an ampersand.
- Sentinel waypoint data and profile settings were unchanged.
- Incomplete-package rejection passed without changing the destination.
- All packaged Python files passed Python 3.11 syntax checks.
- The installed V8 model and native image preprocessing executed successfully
  under development Python 3.13.14.
- Release-manifest/version checks: 111 passed. Skill runtime code did not change
  during packaging; the preceding cleanup's full-suite result is in the ledger.

Evidence: `D:/Navpoint-background-20260909/installer-20260917/verification/`.
Staged release: `D:/Navpoint-background-20260909/installer-20260917/sc_navpoint/`.
The previous `release_version/` and actual user installation were not changed by
this packaging task. The active installation manifest still describes that
previous installed tree. Live Wingman restart/Levski checks remain pending.

## Rebuild

Run `update_release.py --output <new-folder> --zip` with the development Python.
Both the output folder and versioned ZIP must be new; the builder refuses to
overwrite previous artifacts and fails if a listed input is missing. Archive
the prior ZIP before deliberately rebuilding the same version. Runtime file and
directory lists in update_release.py and skill_installer_config.json must agree;
only installer.bat and the tester readme are package-only extras.
