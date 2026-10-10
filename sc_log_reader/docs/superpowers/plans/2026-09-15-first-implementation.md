# First runnable implementation

Historical implementation record. The completed foundation below is retained; future work is now governed by the [revised complete-skill specification](../../PLAN.md) and [17 September implementation sequence](2026-09-17-complete-skill.md).

Goal: implement an independent reader with single-file JSON updates.

Architecture: bounded record assembly -> JSON interpreter -> fixed state handler -> host service. Keep update checks, human approval and startup activation separate.

Tech stack: Python 3.11+, regex with timeouts, unittest, SQLite, setuptools.

Spec: docs/design/ASSESSMENT.md and reader-instructions.draft.json (design references).

Global constraints: work only in this project; freeze reference and original; no install or Wingman launch; no executable network instructions; missing or ambiguous data cannot invent state or money.

1. Write failing reader tests, implement strict JSON validation, bounded interpretation, complete records and runtime recipes.
2. Write failing state tests, implement missions, health, locations, ship attribution, sessions, request confirmation and rewards.
3. Write failing updater tests, implement HTTPS check, explicit digest-bound approval, staged startup activation and rollback.
4. Write service tests, implement file monitoring, persistence, read-only tools, CLI and thin host adapter.
5. Run all tests and package/import checks, verify frozen hashes, document commands and remaining real-game/host qualification.

Use a red/green cycle for each behavior. No live-game equivalence or Wingman compatibility claim based only on synthetic tests.

## Result

All five implementation stages completed for the first development build. See
docs/verification/first-build.json and the test/build logs for evidence. Independent
review findings were reproduced, fixed and reverified. Runtime JSON contains 59
event recipes. Real game qualification, public Wingman API 3 adaptation, a user-facing
review/install button and full old-skill feature parity remain follow-on work.
