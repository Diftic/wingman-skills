# Durable ERP event feed (contract 1)

The feed provides a local, read-only export of committed handler output for
`sc_accountant` and other explicit consumers. It does not activate the monitor,
initialize a runtime, approve instruction updates, or infer financial outcomes.

## Wingman setup

Run reader 0.5.0 to initialize the feed. Enable Accountant 4.9.0.3 in the same
Wingman profile and leave `reader_database` blank: it discovers the reader's
configured Runtime Directory and starts automatically. Keep `auto_sync_interval`
greater than zero. It waits for a reader that starts later and retries without
resetting the persisted source identity or cursor.

An explicit `<reader runtime directory>/events.sqlite3` path overrides discovery.
Accountant 4.9.0.2 requires that path and manual activation. Both use the independent
`erp_reader_client.py`; the rename from `sc_log_reader_2` does not change the feed.
These source releases and packaged clients were checked with temporary records;
preparing the ZIPs does not update the installed skills.

## API

```python
from sc_log_reader.feed import ReaderFeed

page = ReaderFeed('/path/to/runtime/events.sqlite3').read_page(after=0, limit=200)
# An existing Service also exposes service.export_events(after=0, limit=200).
```

The updated Service creates feed metadata during normal database initialization.
The standalone reader refuses missing or incompatible metadata; it never upgrades
or creates a database. `FeedError` describes database/contract failures;
`ValueError` describes invalid arguments. `after` is a nonnegative integer;
`limit` is an integer from 1 through 1000. Booleans and numeric strings are rejected.

Each page contains:

- `contract_version`: integer `1`.
- `source_id`: opaque persistent identity of this database history.
- `after`: requested insertion-sequence cursor.
- `next_cursor`: last returned sequence, or `after` for an empty page.
- `has_more`: more committed rows existed in the page's database snapshot.
- `events`: ascending insertion sequence, across **all** environments.
- `health`: snapshot high-water sequence and explicit notice that the read does
  not establish current game or reader-monitor activity.

Each event preserves the stored handler payload, including original status,
amount/currency fields, source occurrence lists, timestamps and uncertainty.
The envelope adds `id` (`source_id:sequence`), integer `sequence`, primary
`source_occurrence`, database `environment`, and `source` containing the primary
observation's generation, byte positions, source timestamp, instruction version,
and rule ID. Evidence fields can be null in legacy or incomplete history. Multiple
output events from one observation have different IDs and the same primary
occurrence. A confirmed trade can retain multiple `source_occurrences` connecting
its request and result; the primary observation is not its sole evidence.

## Consumer responsibilities

Persist `(source_id, next_cursor)` atomically with imported event IDs and any
resulting financial entries. Compare the source identity **before applying a
page**, including an empty page. On identity mismatch, stop and explicitly
reconcile the replacement source; never reuse its cursor silently. Filter player,
environment and economy within the consumer. An absent player identity or amount
must remain unknown. A commodity request is not a completed purchase.

Read while `has_more` is true, and poll later for new pages. Each page runs in one
SQLite read transaction, so its metadata, high-water mark and rows share a
committed snapshot. Equal timestamps and late historical events cannot skip rows.
Concurrent inserts appear on a subsequent page. Normal reader operation retains
append-only output history; editing/deleting rows externally is unsupported.

A restarted service retains identity. A new/rebuilt database has a new identity.
A byte-for-byte copy or backup retains the original identity because it is the
same lineage. A cursor ahead of the current high water fails explicitly (including
restoring an older backup). Divergent copies with the same identity cannot be
detected reliably by this contract: do not independently write to two clones or
merge them. Rebuild into a new database and reconcile if an independent lineage
is required. The feed alone does not certify that all historical log data was
available or parsed.
