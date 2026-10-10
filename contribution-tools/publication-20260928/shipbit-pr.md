## What this adds

Star Citizen Log Reader 0.5.1 reads local `Game.log` observations in the background and exposes current state, missions, recent events, trade records, and reader/update health to Wingman Skill API v3. Optional spoken reactions and GUI notifications have 53 individual controls and seven category masters; paired transitions such as entering/leaving armistice share one switch.

Reading rules are JSON data. Valid updates from the configured GitHub URL stage automatically, activate after a full Wingman restart, and can be reverted through Instruction Recovery. The updater does not download Python code. The SQLite event feed supports separate SC Accountant installations.

The contribution contains 28 runtime, dependency, license, and usage-documentation files under `skills/sc_log_reader`. It is based on `develop` at `63b0c8a` and declares Windows support. Upgrade instructions explain re-enabling profiles that used the old `SCLogReader2` name.

## Validation

- 339 Reader tests passed against the selected runtime. The development-only CLI was supplied to the test harness without adding it to the contribution; runtime import locations were checked.
- Current `SkillConfig` schema validation passed.
- Offline integration with current upstream loader, facade, and lifecycle methods passed: construction, ingestion, seven tool calls, reaction context/history/TTS delegation, and cleanup. Providers, GUI, settings, and hardware were test doubles; this is not a live-game or audible-playback qualification.
- Exact file/content and contribution-history checks passed. Native packaging checks covered custom and bundled layouts.

## Maintainer review before merge

This is a draft for integration review. The current package includes a Windows x64 CPython 3.11 `regex` dependency with its license; please review the preferred bundled dependency layout. The existing seven-query interface and automatic activation also need review against the current tool-budget guidance. Reaction language currently uses the existing spoken-language setting; adoption of the newer `self.wingman.language.name` helper remains to be reviewed.
