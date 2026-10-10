# Skill publication — 2026-09-28

## Published state

- Log Reader 0.5.1: `contrib/sc-log-reader-0.5.1`, `777f2784cab52b3f239588137cc1bd69bcd162d0`, 28 allowlisted files. New branch directly from ShipBit develop `63b0c8a`; prior contribution branch preserved.
- NavPoint 4.9.0.27: `contrib/sc-navpoint`, `fc8727c7c29bdc36c0fe164907491a32319dd3df`, 53 files. All selected source files match the already-published branch.
- Accountant 4.9.0.4: `contrib/sc-accountant`, `d0a4dbcf6534e2c0bb6681a308e06637e28d8469`, 19 files. All selected source files match the already-published branch.
- ShipBit draft PR: https://github.com/ShipBit/wingman-ai/pull/439 (base develop). GitHub confirmed OPEN, draft, exact head SHA and only the 28 selected Reader paths.
- The upstream issue requirement was removed in `03e6fe0`; no new issue was needed or created.

## Changes

Reader contribution refreshed the configuration, version, orchestration wiring and notification policy from the current development runtime. Contribution-only documentation now describes the individual controls and SCLogReader2 discovery-name migration. Contribution metadata explicitly restricts the Windows native bundle to Windows. The development checkout and live Wingman installation were not modified.

## Validation

- Reader: 339 tests passed in 36.347 seconds; see reader-tests-final.txt. All imported runtime modules were checked to originate from the contribution package. The first run had two test-module import errors because the CLI is deliberately excluded from the runtime-only contribution; the final run supplied only that development CLI as a test harness helper. Native packaging tests rebuild both supported layouts from the development source.
- Current ShipBit SkillConfig schema accepted the contribution YAML, Windows platform restriction and unique property IDs.
- Current upstream offline host contract passed (host-contract.txt): real extracted loader/facade/lifecycle methods, isolated ingestion, seven queries, reaction context/history/TTS delegation, cleanup. Settings, GUI, providers and hardware were doubles; no live Wingman/game or audible speech qualification.
- Accountant: 58 tests passed in 2.76 seconds, plus QR/dashboard smoke. Snapshot: ../validation/accountant-9df9eed5.
- NavPoint: 255 tests passed, three old release-manifest tests deselected, in 3.01 seconds. The tested snapshot's 53 file hashes match the approved checkout. See navpoint-tests.txt.
- All three exact-file guards passed. Reader pre-commit/pre-push guards passed. Remote SHAs re-read and matched all three local candidates.
- NavPoint's no-op push was rejected by the existing pre-push guard because there were no updates to inspect. No guard was bypassed: remote SHA was verified identical. Accountant was also already current and required no new push.
- git diff --check reports only the retained third-party regex WHEEL metadata's blank final line.
- The configured public JSON update file exists on Diftic/wingman-ai main; it was not changed by this publication.

## Draft review items

Windows/CPython dependency packaging, existing seven-query schema and automatic activation versus current upstream budget guidance, and adoption of the newer language helper are called out in the PR. No upstream merge was attempted. Private reports, test snapshots and local allowlist policies were not published.
