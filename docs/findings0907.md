# Skills Audit Findings — 2026-07-09

General quality audit of Lars's own skills across both projects (live v2.1.1 vs dev v3.1.x).
Reviewed: satisfactory_assistant, sc_accountant, sc_log_reader, sc_navigator (both projects), sc_navpoint, sc_radio (dev-only).
Method: five parallel review agents under evolve evidence discipline — every finding traced in actual code, confidence tier stated.
Triage decisions recorded per finding.

## Version parity

- **satisfactory_assistant**: live and dev byte-identical, every file.
- **sc_navigator**: live and dev byte-identical, every file.
- **sc_accountant**: 4 files differ (`__init__.py`, `models.py`, `guid_resolver.py`, `main.py`) + new `seed_demo.py`, `data/commodity_guid_map.json`. Dev changes are clean, backward-compatible improvements.
- **sc_log_reader**: real dev changes in `main.py`, `parser.py`, `logic.py`, and most of `log_donor/`. A solid hardening pass (sha256-only dedup, streaming uploads, CSRF/DNS-rebinding protection, static-file traversal fix, own-ship event filter).

---

## Findings and triage

### 1. sc_accountant — mission-reward bundle with no money field suppresses components without inserting anything
`main.py`, `_sync_from_logreader` / `_convert_event_log_entry` (~lines 669-680, 705-709, 914-921). Bundle windows are built unconditionally; `_convert_event_log_entry` returns `None` for falsy `amount_auec`, so matching `reward_earned` components get suppressed/deleted while the bundle inserts nothing.
**Triage: NOT AN ISSUE.** Skill tracks trades and money only, not item rewards — a money-less bundle correctly records nothing.

### 2. sc_navpoint — path traversal in HUD static file server
`navpoint_ui/app.py`, `static_file()` (~lines 65-75): `fp = _STATIC_DIR / filename` from a `{filename:path}` route, no containment check. `/static/../../main.py` reads arbitrary text files. Compounded by `0.0.0.0` bind with no auth.
**Triage: DEFERRED.** sc_navpoint development is paused; revisit when resumed. (Note: sc_log_reader's donor_ui already contains the correct fix pattern — `resolved.parent != _STATIC_DIR_RESOLVED` — to copy over.)

### 3. sc_navigator — unreachable route legs silently counted as 0 Gm
`route_optimizer.py`, `optimize_route`: `leg_dist = d if d is not None else 0.0`. Disconnected waypoints produce a valid-looking, artificially short route instead of an error.
**Triage: DEFERRED.** sc_navigator development is paused; revisit when resumed. Related while there: config says "(Outdated) pre-SC 4.7" but code declares `SC_TARGET_VERSION = "4.8.0"`.

### 4. sc_accountant — possible double-count on out-of-order sync (inferred)
`main.py` (~669-680 vs 819-861). Bundle-arrives-late is handled against stored transactions; component-arrives-late is only checked against the current sync batch — a straggler `reward_earned` after the watermark could insert a duplicate.
**Triage: MONITOR IN TESTING.** No fix now.

### 5. sc_accountant — seed_demo.py overwrites live data dir with no guard
`seed_demo.py` (~470-486): writes `transactions.jsonl`, `balance.json` etc. in `"w"` mode to the real AppData dir, no existing-data check, no prompt.
**Triage: PLANNED MITIGATION.** Current data will be wiped and rebuilt from scratch anyway. Add a timestamp/provenance marker to all entries so demo data is distinguishable and seeding can refuse to clobber non-demo data. (Open question: entries already carry event timestamps — likely a `source: demo|live` tag or seeded-at stamp is the actual mechanism; approach not yet confirmed.)

### 6. sc_log_reader — torn/partial line risk in tailer
`parser.py`, `_check_for_new_lines` (identical in live and dev): commits `_file_position = f.tell()` without checking the line ends in `\n`. A poll landing mid-write can commit a partial line; the remainder is never re-read — silent truncation/mangling of that event.
**Triage: REVISIT LATER.**

### 7. sc_log_reader — own-ship event filter depends on channel-name heuristic
`parser.py`, `_event_belongs_to_player_ship` (dev only): gates on ship state from `_is_ship_channel`; a missed join/leave line means a genuine own-ship `qt_arrived`/`fatal_collision` is silently dropped.
**Triage: WATCH, NO FIX.** Only occurs when the game itself mislogs channel join/leave (known to happen). Keep an eye on it during testing.

### 8. satisfactory_assistant — render_map PNG write has no error handling
`satisfactory_map.py::render_map` (~265-266): `image.save()` with no `OSError` guard, propagating uncaught out of a tool call — inconsistent with the same function's graceful missing-Pillow fallback and the codebase's defensive I/O pattern everywhere else.
**Triage: REVISIT LATER.** Likely fix is a simple error output ("Map artifact: unavailable" style line); the map is an important feature, handle when back in this area.

### 9. sc_navpoint — no error handling in database.py
Every method runs raw sqlite3 with no try/except; locked/corrupt DB raises unhandled through the tool layer. (No SQL injection — all queries parameterized.)
**Triage: DEFERRED** (paused, see #2).

### 10. sc_navigator — minor logic issues
Falsy-zero in nearest-neighbor (`... or float("inf")` treats a real 0.0 distance as missing); hardcoded `GATEWAY_PAIRS` currently dead code; docstring overclaims "optimal start."
**Triage: DEFERRED** (paused, see #3).

### 11. satisfactory_assistant — performance waste
(a) `satisfactory_workspace.py`: `SaveWorkspace.summary()` opens the SQLite store ~10x per call, each open re-hashing 5 legacy JSONL files via `import_jsonl`. (b) `satisfactory_mirror.py::store_mirror_artifacts` (~494-505): full read-and-rewrite of `observations.jsonl` on every audit instead of only when the cap is exceeded.
**Triage: FIXED 2026-07-09.** Opus agent implemented both halves (store opened once per `summary()` incl. counts, closed in finally; mirror log rewritten only on cap overflow, plain append otherwise); two new tests pin the append-only-under-cap and cap-trim contracts. Suite 449 passed / 1 pre-existing skip, re-run independently. Skeptic verdict SHIP after probe-based refutation attempts (health equivalence at cap boundaries, store leak on mid-read exception, counts semantics) all failed. One LOW completeness note: the old always-rewrite path incidentally self-healed a missing trailing newline; unreachable in normal operation since this function is the file's only writer and always newline-terminates.

### 12. sc_navpoint — minor issues
SQLite connections never `.close()`d; LIKE wildcards unescaped in `search_navpoints()`; unvalidated JSON body fields on two API endpoints.
**Triage: DEFERRED** (paused, see #2).

### 13. sc_log_reader — unsanitized handle flows into R2 storage key (investigated 2026-07-09)
Traced end-to-end: `handle_extractor.py` regexes (`\S+`, `[^\]]+`, `[^"]+`) accept arbitrary characters from player-controlled log lines → `scanner.py` builds `renamed = f"{handle}_{filename}"` → `uploader.py` sends it in the begin manifest → worker design (`plans/2026-05-14-sc-log-donate-worker.md`, `buildR2Key`) embeds `renamed` verbatim in the R2 object key `${date}/${uploadId}/${install}/${renamed}`, with only a `typeof === "string"` check.
Not classic path traversal (R2 keys are flat strings), but a handle containing `/` pollutes the key layout and breaks the reconciler's segment-based key parsing. Caveat: verified against the worker *plan doc*, not deployed worker code (outside the skills folders) — deployed behavior inferred.
**Fix when convenient:** allowlist the handle client-side (`[A-Za-z0-9_-]` — legit RSI handles fit); optionally the same regex on `renamed` in the worker.

---

## Blind re-review 2026-07-09 (sc_log_reader + sc_accountant)

Two context-free Opus reviewers (no knowledge of this document) re-reviewed both skills to test whether the original findings reproduce. Static reading only; neither could run the suites standalone (host-only `api.enums` import at collection; the suites do run in our usual invocation).

**Reproduction of original findings:**
- #13 (unsanitized handle to R2 key): REPRODUCED independently, same regexes, same trace.
- #4 (out-of-order sync double-count): REPRODUCED with a sharper mechanism: the gap opens at the exact watermark second when a component exceeds `count_at_ts` (main.py:686-689); holds only on the unenforced invariant bundle-ts == last_seen >= component ts.
- #7 (own-ship channel heuristic): not reproduced as a risk; blind reviewer rated the documented fail-open design a positive. WATCH triage stands.
- #6 (torn-line tailer): not reproduced (parser.py read fully, not flagged). Single-miss, does not invalidate; REVISIT LATER stands.
- #1 (money-less bundle): not flagged, consistent with NOT AN ISSUE.
- #5 (seed_demo): not comparable, reviewer skipped seed_demo.py.

**New findings the original audit missed** (top items re-verified in code by orchestrator):

- **NEW-A: FIXED 2026-07-09, skeptic verdict SHIP.** All ten truncating rewrite sites in both skills now route through a per-skill `atomic_io.atomic_write_text` (mkstemp in target dir + fsync + os.replace, temp cleaned and original intact on any failure); store.py docstring corrected; versions bumped to accountant 4.8.3.1 / log reader 4.8.3.3; `atomic_io.py` added to both manifests per skill (installer config AND update_release.py RELEASE_FILES, the latter caught in orchestrator verification). Suites 158 + 76 green, serialization byte-identical (probe-verified incl. CRLF and unicode escapes). Documented residual (LOW, accepted): on Windows, os.replace fails transiently with PermissionError if a concurrent reader holds the destination open, where the old truncating write would have proceeded; contract holds (original intact, logged-and-skipped, retried naturally, e.g. trim on next launch). Optional hardening if it ever shows in logs: bounded retry on PermissionError in the helper. Original finding follows:
  Non-atomic rewrites of source-of-truth files. sc_accountant `store.delete_transaction` rewrites transactions.jsonl via `open(path, "w")` (store.py:190) and is reached automatically per superseded reward component during background sync (main.py:855); contradicts the module docstring's append-only claim; same pattern in `_write_json_list`, `save_balance`, `save_sync_cursor`. sc_log_reader `EventLog.trim()` truncate-rewrites the event log every startup (event_log.py:224); `_save_stack_state` same pattern. Crash mid-write silently truncates the ledger (malformed lines are skipped on read). Fix class: temp file + os.replace.
- **NEW-B (MED-HIGH, accountant, verified bind + static token): dashboard binds 0.0.0.0 unauthenticated** (accountant_ui/app.py:1229), LAN URL advertised via QR; POST /api/reset wipes all data guarded only by the static literal "RESET" (app.py:1180); balance/transactions endpoints writable by anyone on the LAN.
- **NEW-C (MED-HIGH, accountant): corrupt balance.json silently resets balance to zero** (store.py:344-346 returns fresh AccountBalance on any read error) and no rebuild-from-ledger routine exists anywhere; every later mutation persists a zero-derived balance.
- **NEW-D (MED, log reader): EventLog watermark restart-dedup assumes append order == timestamp order**, violated by the reward-bundle Timer writing older-stamped bundles after newer events (logic.py:1239-1250); duplicates on catch-up. Also isoformat drops `.000000`, weakening the string compare.
- **NEW-E (MED, log reader): EventLog.append writes outside its lock** (event_log.py:142-157); parser thread and bundle Timer share one file; interleaved lines are silently dropped on read.
- **NEW-F (MED, log reader): parser timestamp fallback uses naive LOCAL now()** (parser.py:573) while everything else is naive UTC; one parse miss skews reward windows and watermark ordering by the UTC offset.
- **NEW-G (LOW-MED, log reader, UNVERIFIED GUESS): commodity sell quantity may be cSCU un-divided** (buy divides by 100 at logic.py:784, sell does not at :795, both labeled "scu"); consumer only re-divides when unit=="cscu", so if the sell field is centi-SCU the ledger overstates sold SCU 100x. Verify against a real sell line before believing.
- Minor, log reader: blueprint notifications always render "Unknown" (main.py:923 reads `name`, parser stores `blueprint_name`); dead "INVALID LOCATION ID" guard (logic.py:380); same-second equal-amount reward dropped when notification_id absent; ledger.py (TradeLedger) is dead code.
- Minor, accountant: fingerprint-less fallback dedup key is a latent collision trap (currently dead, producer always sets fingerprints); FIFO oversell remainder silently dropped from realized P&L; `store.update_transaction` dead code.
- Already known, not new: shared static donor token (design trust assumption), unauthenticated GET /api/preview forced-scan (skeptic client note 2026-07-07).

**Triage: PENDING user decisions.** Both skills are mid-live-test; recommendation is to triage now, fix after the live-test verdicts, with NEW-A (atomic writes) and NEW-B (dashboard exposure) first in line.

---

## Positives worth keeping

- **satisfactory_assistant**: ~9,700 lines reviewed, no crash-prone bugs, no bare excepts, consistent `_is_within` path containment, subprocess handling guards `FileNotFoundError`/`TimeoutExpired` and copies saves before parsing. Unusually disciplined.
- **sc_accountant dev**: GUID table moved off a hardcoded fake-UUID dict to a defensively-loaded JSON map (currently empty — resolution falls back to "Unknown" until populated); fingerprint dedup and `abs()` sign normalization verified sound.
- **sc_log_reader dev**: dedup collision risk fixed (sha256-only), uploads stream instead of buffering, donor UI gained session token + Host-header middleware and a correct traversal-rejecting static handler.
- **sc_radio**: planning-only, but genuinely fleshed out — repo layout, module specs, phased build plan, explicit open-questions table. Ready to implement once TTS endpoint/char limits/generation speed are verified.
