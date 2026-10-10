# SC Log Reader 0.5.1

Star Citizen observations, optional Wingman reactions, and automatic updates to
the JSON reading instructions. This Windows package includes the native CPython
3.11 x64 dependency used by the qualified Wingman AI 3.2.2 host.

## Install

1. Fully close Wingman AI, including its tray icon.
2. Extract the `sc_log_reader` folder into
   `%APPDATA%\ShipBit\WingmanAI\custom_skills`.
3. Start Wingman and enable **Star Citizen Log Reader** in the desired profile.
4. Set **Star Citizen Path** to the folder containing LIVE/PTU, and choose a
   separate writable **Runtime Directory** for history and update files.
5. Enable **React to Game Events** if you want spoken responses to selected events.

## Upgrade an existing installation

Keep the same skill folder name `sc_log_reader`. With Wingman closed, move the
existing skill folder to a backup location outside `custom_skills`, then extract
the new folder in its place. Keep the existing Wingman profile and Runtime
Directory and their saved settings. For an upgrade from a release named
`SCLogReader2`, enable **Star Citizen Log Reader** again in the profile's Skills
panel after starting Wingman. The enabled-skill list must contain `SCLogReader`;
an old `SCLogReader2` entry does not enable the newly named skill. If migrating
the profile file with Wingman closed, back it up and replace only that entry in
`discoverable_skills`, preserving all other settings. If you previously edited values directly in
`default_config.yaml`, carry those values into the new configuration rather than
discarding them. Do not delete runtime/history files or copy downloaded JSON into
the new package manually. Restore the backed-up folder to undo the code upgrade.

The saved class name `SCLogReader2` remains supported as a compatibility alias.
That Python class alias does not migrate Wingman's enabled-skill list.
New installations use `SCLogReader`. Existing runtime folders named SCLogReader2
can keep that name; it does not affect the skill's name or update behavior.

## Reading-instruction updates

The configured GitHub JSON is checked at startup and every six hours. A valid
newer revision is downloaded and staged, with a pop-up notice. Fully restart
Wingman to activate it. Python skill code is not downloaded by this updater.

To recover, select **Restore previous version** under **Instruction Recovery**,
save, then fully restart Wingman. The rejected revision stays blocked. To use
Restore again later, first save **No recovery requested**, then select Restore.

Published files retain their original internal package identifier and hashes for
compatibility. The new `sc_log_reader` package reads those files directly, keeping
the active revision, previous version and rejection history usable.

## Connect SC Accountant

SC Accountant 4.9.0.3 starts and connects automatically when enabled in the same
Wingman profile. Leave its **SC_LogReader database** blank and keep **Capture
interval** above zero (15 seconds by default). Configure this reader's Runtime
Directory normally; Accountant uses that setting and waits if the reader starts
later. Ask Wingman to open the accounting dashboard to view the captured records.

For Accountant 4.9.0.2, manually set **SC_LogReader database** to the full path
`<Runtime Directory>\events.sqlite3` and activate Accountant, for example by
opening its dashboard. An explicit path remains supported by newer versions.

The connection uses the database, not the reader's Python package or class name.
The reader 0.5.0 initializes feed metadata for existing reader databases without
discarding their history. Older installed reader versions may lack this feed.
The accountant resumes from its saved position, avoids duplicate imports, and
excludes PTU/test-economy money. It stops if the source database identity changes.
Leave old generated records in place; do not import legacy books automatically.

The ZIP contains no personal profiles, logs, databases or development reports.
See CONTRACT.md for integration details and qualification limits.
