# SC Log Reader

Version **0.5.1** for Wingman AI 3.x. The shipping folder and Python package are
`sc_log_reader`; the Wingman class is `SCLogReader`.

## Features

- Incremental Star Citizen log reading, observed state and durable history.
- Optional in-character reactions or literal GUI notifications for selected events.
- Individual notification switches, including one Armistice switch for entry and exit.
- Validated JSON instruction downloads at startup and every six hours.
- Activation at the next Wingman process startup, with native update pop-ups.
- Instruction Recovery dropdown, previous/bundled fallbacks and rejected-version blocking.

The architecture remains Reader (log interpretation), Handler (state/history),
and Orchestrator (Wingman settings and lifecycle).

## Install and upgrade

See [the packaged guide](integrations/wingman_target/README.md). The Windows ZIP
contains one `sc_log_reader` folder with its CPython 3.11 x64 regex dependency.
Keep existing settings and the same runtime directory during an upgrade.

The pre-release class name remains a compatibility alias. Published/bundled JSON
retains its original bytes and internal identifier, preserving hashes, active
revision, rollback objects and rejection history. New engines also accept the
canonical `sc_log_reader` identifier. No published JSON was rewritten for this rename.

## Instruction updates

[Current publisher](https://raw.githubusercontent.com/Diftic/wingman-ai/main/skills/sc_log_reader/updates/instructions.json).
Only JSON is downloaded; Python changes require a skill release. After the update
notice, fully close and reopen Wingman. Recovery uses **Restore previous version**,
Save, then restart. Before using Restore again, save **No recovery requested**.
See [publishing](updates/README.md) and [the JSON contract](docs/INSTRUCTIONS.md).

## Development

The skill root also contains the verified Wingman entry point, configuration and
portable `dependencies/` runtime, so the repository folder can be distributed as
a Windows CPython 3.11 skill. Maintain the reader under `src/` and the host wrapper
under `integrations/wingman_target/`; refresh the root copies from the tested
release when shipping. Run `python tools/verify_repository_release.py` before a
Git upload to catch differences between those copies. Development reports,
environments and archived releases are not part of the runtime package.

```powershell
$env:PYTHONPATH = "$PWD\src;$PWD\tests"
python -B -m unittest discover -s tests -v
python -B -m pytest tests/test_erp_feed.py -q
python -B -m sc_log_reader validate updates/instructions.json
python -B -m sc_log_reader replay examples/sample.log
```

Python 3.11+ is required; native Windows distribution targets CPython 3.11 x64.
Set SC_READER_T8_PYTHON and SC_READER_T8_REGEX_WHEEL for native packaging tests.
Release evidence lives under reports/ and is excluded from the shipping ZIP.
Historical reports/plans describe earlier snapshots and may use the project name.
Actual rendering, audio and game behavior need live checks. See the
[Wingman contract](integrations/wingman_target/CONTRACT.md) and
[local event-feed contract](docs/ERP_FEED.md).
