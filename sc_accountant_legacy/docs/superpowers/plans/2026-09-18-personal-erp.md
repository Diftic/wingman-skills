# Personal ERP implementation plan

Approved design: the 18 September conversation. Personal operations ERP; Simple and Advanced share durable records. Shared organisation commerce is excluded.

Architecture: local SQLite engine, versioned SC Log Reader feed, thin Wingman adapter, offline local dashboard. Preserve the original checkout and legacy data.

- [x] Durable reader feed: ascending resumable pages, stable source and event identities, original evidence, read-only consumer, replay tests.
- [x] ERP engine: operations, journal, inventory lots, movements, production, assets, plans, evidence and reconciliation. Atomic commands/import cursors, decimal money, reversible corrections, unknown costs retained.
- [x] Dashboard: two modes, usable forms for all workflows, escaped text, loopback API protection.
- [x] Wingman adapter: three on-demand tools, background feed, drain/close lifecycle, explicit legacy migration.
- [x] Verify: partial-sale acceptance, restart/replay, requests versus confirmation, failed transactions, production collection, accounting corrections, full regression, browser workflow, distribution candidate.

Interfaces: ERP(path).command(action,data), view(section='overview',**filters), ingest_page(page), close().
Views return {mode,data}; reader page v1 contains source_id, after, next_cursor, has_more, events, health.
Money strings preserve decimal precision. Unknown money remains null. Every entity has id.
Runtime records are never placed in source or overwritten on upgrade.

Ruling: preserve legacy main.py and select a new thin erp_skill module through configuration; old regression coverage remains available.
Ruling: manual migration imports historical ledger as cash history and reconciles its opening balance; it never invents inventory costs from incomplete legacy records.
Ruling: built-in ERP tools remain three small entry points, activated on demand; ingestion does not call models.
