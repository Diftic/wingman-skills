# ERP implementation verification — 19 September 2026

Candidate: SC Accountant 4.9.0.1. Personal, local ERP with Simple and Advanced views.

## Verified

- Accountant plus new reader-feed tests: 230 passed (216 accountant, 14 feed). Existing Pydantic deprecation warnings remain.
- Reader documented unittest suite: 289 run, successful, one skipped. No installed Wingman or game was launched.
- Actual reader parser -> durable feed -> ERP: mission and cash reward captured once on replay; physical reward fixture does not invent money.
- Browser: wallet reconciliation, operation, stock purchase, partial sale, correct realised profit and remaining cost, mode persistence, mobile width, forecast plan, production completion/collection, Reports, read-only History, no JavaScript exceptions.
- Portable ZIP: 39 allowlisted files, isolated imports and HTTP dashboard, CLI help, no Wingman host imports, no player databases.
- Static check: new accountant modules and tests pass Ruff; dashboard JavaScript passes syntax validation.
- Independent bounded review of source identity, cursor/transaction integrity and reversal handling completed; identified issues were corrected and covered by regression tests.

## Accounting acceptance example

Starting wallet 200,000 aUEC; buy 100 SCU for 100,000; sell 50 SCU for 70,000.

- Recorded wallet: 170,000
- Cash movement: -30,000
- Realised profit: 20,000
- Remaining stock cost: 50,000

A subsequent production job consumes 10 SCU and pays 100 in fees. Collection transfers its 10,100 cost into output stock, giving 50,100 total stock and 169,900 wallet. Profit remains 20,000 until further sales or losses.

## Limits and delivery

Live installed-Wingman/game-session acceptance remains outstanding. Adapter lifecycle is tested with a host double. The feed connection is database-based and does not prove the reader monitor/game is active. Logs are incomplete evidence, so full wallet/inventory coverage is not claimed.

Scope excludes cloud/org collaboration, a shared-credit/banking module, live market forecasts and automatic game controls. Legacy data imports are explicit and partial; see ERP_README.md.

Changes were developed in an isolated worktree and copied selectively into the source checkout after testing. Legacy main.py and player data were not changed. No installed skills, running Wingman configurations or reader runtimes were updated.

Screenshots and machine-readable local checks are under reports/erp-20260919. The distribution candidate is under dist/.
