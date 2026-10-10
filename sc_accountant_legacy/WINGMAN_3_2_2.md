# Wingman AI 3.2.2 compatibility — SC Accountant 4.9.0.2

Updated 20 September 2026. Source and installed custom skill are updated.

## Changes

- Declared Skill API 3 and release version in the default manifest.
- Added a standard main.py entry that loads the ERP under both package imports and Wingman's custom file loader. It creates no records, tasks, network calls or global search-path changes during catalog probing.
- Preserved the prior main.py byte-for-byte as legacy_main.py. Legacy regression tests still exercise that saved implementation.
- Removed the dashboard dependency on starlette.middleware.trustedhost, which the v3.2.2 executable does not bundle. Equivalent strict local Host checks remain alongside Origin checks.
- Updated the installer manifest so a pre-v3 default_config.yaml cannot keep the new release ineligible.
- Installed the current ERP modules and defaults. Existing Engaged preference maps to Advanced; the previous capture interval was retained. No legacy ledger import ran.

## Verification

- 223 accountant tests passed; 19 existing Pydantic deprecation warnings.
- Changed Python files pass Ruff.
- Installed v3.2.2 catalog, module loader, Skill base class, decorators, configuration models and web dependencies exercised under Python 3.11.15. API models and frozen dependencies came from the installed executable's PYZ archive.
- Both staged and installed copies return catalog verdict ok, expose exactly three valid tool schemas, activate, dispatch a wallet/report command, serve the dashboard and unload.
- Test doubles replace printer, secret-event bus, benchmark, storage path and settings view. No real model/audio calls or player data writes occur. This is a compatibility test, not live Wingman/game qualification.
- Portable ZIP manifest and entry point verified. SHA-256: ed10d32493ae791c058fc1fd80a7f3310f785d1c078f47197c9cfe3c0b756bed.
- Existing generated records unchanged: 2 files checked before/after installation.

## Activation and rollback

Restart Wingman to rescan the catalog, then re-enable SC_Accountant in the Computer profile if it remains absent after the earlier automatic removal. Ask to open the accountant dashboard to activate its lazy lifecycle.

Installed path: C:\Users\larse\AppData\Roaming\ShipBit\WingmanAI\custom_skills\sc_accountant

Previous installation backup: C:\Users\larse\AppData\Roaming\ShipBit\WingmanAI\skill_backups\sc_accountant\20260920-133833-wingman322

Restore files from that backup with Wingman stopped if rollback is needed. Player records are in the separate generated_files/SC_Accountant folder and were not migrated or removed. The old backup is legacy and is not compatible with the v3 catalog.

The reader was separately rejected as legacy by the host and is outside this update. Its current installed API declaration is None. Automatic ERP capture requires a compatible active reader and an explicitly configured reader database; manual ERP use is available.

Machine-readable host and installation results: reports/wingman-3.2.2/.
