# SC_LogReader Development Log

## Version: 4.8.3.4

### Expanded donation success message (2026-07-11)

Skill-iteration bump only (`4.8.3.3` -> `4.8.3.4`); no SC-target change, donor
UX copy only.

The donor UI's post-upload success state now shows an expanded message: a
thank-you plus a line explaining the development value of a donated log (real
`Game.log` samples drive the parser regression corpus). Previously it showed a
bare confirmation. No change to the scanner, uploader, or the envelope schema.

This is the first release to carry the 4.8.3.3 crash-safe atomic writes
(`atomic_io.py`, audit finding NEW-A) into an install alongside the copy change,
so both ship together.

## Version: 4.8.3.3

### Crash-safe atomic writes (audit finding NEW-A) (2026-07-09)

Skill-iteration bump only (`4.8.3.2` -> `4.8.3.3`); no SC-target change,
reliability fix only.

Every rewrite of a persistent file used a truncating `open(path, "w")`: the
`EventLog.trim` startup rewrite, `_save_stack_state` in `main.py`, and the
`_flush_file_output` status writers in `logic.py` and `parser.py`. A crash
between truncate and the final write left the file partial, and readers of the
JSONL event log silently skip malformed lines, so a mid-write crash could
truncate history or leave a half-written status file that a sibling skill
reads.

Fix: new leaf module `atomic_io.py` with `atomic_write_text(path, text)`
(identical shape to SC_Accountant's; a separate copy avoids a cross-skill
import dependency). It writes to a uniquely named temp file in the same
directory, flushes and `os.fsync`es it, then `os.replace`s it over the target
(atomic on Windows and POSIX on the same volume). On any failure the temp file
is removed and the original is left intact. All four rewrite sites now route
through it and keep their existing exception handlers.

Added `tests/test_atomic_io.py` (3 tests): `EventLog.trim` leaves exactly the
recent entries a reader expects with no temp file behind, the helper replaces
content cleanly, and it preserves the original with no temp behind when
`os.replace` fails mid-write. Full suite green at 76 passed. `atomic_io.py`
added to the `files` manifest in `skill_installer_config.json` so releases
ship it.

### qt_arrived / fatal_collision gated on own-ship state (2026-07-08)

Skill-iteration bump only (`4.8.3.1` -> `4.8.3.2`); no SC-target change, bugfix
only.

Star Citizen's `Game.log` writes a `CSCItemNavigation::OnQuantumDriveArrived`
line for *every* ship in replication range, not just the player's, and
`<FatalCollision>` behaves the same way. The parser classified any such line as
`qt_arrived` / `fatal_collision` regardless of who it belonged to, so the
wingman announced "Arrived at quantum destination" while the player stood on
foot in a shop and a stranger's ship arrived nearby.

Evidence (real logs): a foreign Avenger Titan arrival while the player was on
foot, and the player's own Drake Clipper arrival, are byte-for-byte identical in
their AUTH marking: both read `NOT AUTH`. The AUTH field is therefore useless
as a discriminator. The reliable signal is the parser's existing `ship` state,
set from ship voice-channel join/leave lines: the player is only aboard a ship
when that state is populated.

Fix in `parser.py` `_classify_event`: both event types now pass through a new
`_event_belongs_to_player_ship` gate. It returns None when the player is not
aboard any ship (the on-foot false trigger), and, when aboard, compares the
arriving/colliding entity's model tokens against the current `ship` state via
`_ship_model_tokens` (drops manufacturer prefix codes like `DRAK`, human names
like `Drake`, the `@vehicle_Name` wrapper and numeric ids, so `DRAK_Clipper` and
a channel-derived `Drake Clipper`/`Clipper` reduce to `{clipper}`). A confident
mismatch (both sides derivable, model tokens disjoint) drops the event; anything
underivable fails open so a genuine own-ship event is never lost to a parse gap.
`fatal_collision` additionally requires `PlayerPilot: 1` in the line. New helpers
`_extract_qt_arrival_class` and `_extract_collision_vehicle_class` pull the
entity class (trailing numeric id stripped). Downstream consumers are unaffected:
the gate only suppresses spurious classifications; the event data contract is
unchanged. Covered by `tests/test_parser_ownership.py` (8 tests).

Residual risks (accepted):
- (a) A future ship whose channel display name shares no model token with its
  entity class would have its own QT arrival silently dropped. Manufacturer
  tokens are stripped before comparison, so if this ever bites, consider adding
  manufacturer-fallback matching.
- (b) An own QT arrival is dropped if the `ship` state is missing because the
  boarding happened before the last login line (catch-up replays only from the
  last login), so the channel-join that sets `ship` was never seen.
- (c) A same-model foreign arrival while aboard, or a stale aboard state after
  logging off inside a ship, still passes the gate. This is the narrow surviving
  remnant of the original bug and is not fixable by model-token matching alone.

### SC_TARGET_VERSION corrected 4.8.2 -> 4.8.3 (2026-07-07)

Corrected `SC_TARGET_VERSION` from the stale `4.8.2` to `4.8.3` to match the
current live Star Citizen patch and this skill's own `4.8.3.x` VERSION line
(VERSION unchanged at `4.8.3.1`). Updated in `main.py`, `__init__.py`, and
`skill_installer_config.json`. This clears the dependency-version mismatch
warning SC_Accountant raised while the two skills disagreed on their SC target.

### reward_earned entries now carry the resolved mission_id (2026-07-07)

Skill-iteration bump only (`4.8.3.0` -> `4.8.3.1`); no SC-target change, data
contract fix only.

Adversarial review of SC_Accountant's mission-reward reconciliation (which
supersedes a `reward_earned` component transaction once its canonical
`mission_reward` bundle arrives) found that the two could disagree on
`mission_id` in real logs. The bundle resolves the mission via
`_reward_context_for_event` (embedded `MissionId`, else the most recently
completed contract by time-proximity, else unresolved) and stamps that
resolved id on the bundle. The persisted `reward_earned` event-log entry was
written to disk *before* that resolution ran, so it kept whatever the raw log
line carried, which in the common time-correlation case is the zero-sentinel
`MissionId` (`00000000-0000-0000-0000-000000000000`), not the resolved one.
Downstream, matching component to bundle by `mission_id` would fail even
though they were the same reward, risking a double-counted payout.

Fix in `logic.py`'s `_write_raw_to_event_log`: for `reward_earned`, resolve
the reward context (`_reward_context_for_event`) once, *before* building the
persisted entry, and stamp the entry's `data.mission_id` / `data.mission_name`
with that resolved value. The same resolved context object is then passed
into `_record_reward_component` (new optional `context` parameter) instead of
letting it resolve its own copy, so the entry and the bundle it feeds can
never diverge. `blueprint_received` (the other reward-component event type)
is unaffected: it still resolves its own context on demand, since it has no
mission_id field of its own to keep in sync.

The `reward_earned` fingerprint is unchanged (still `notification_id` /
timestamp / amount based); `mission_id` deliberately does not enter it.

Also fixes a smaller latent issue as a side effect: the raw zero-sentinel
`MissionId` no longer leaks into the entry's `data.mission_id` at all (it's
normalized to `""` alongside every other unresolved case), where previously a
downstream consumer checking "is this field non-empty" could have mistaken
the sentinel for a real mission id.

Tests added to `tests/test_movement_reconciliation.py`:
`test_reward_earned_entry_inherits_recency_resolved_mission_id` (tier-2:
reward_earned with the zero-sentinel MissionId, preceded by a
`contract_complete` a few seconds earlier -- the written entry's
`data.mission_id` equals the bundle's) and
`test_reward_earned_entry_stays_mission_id_less_without_recent_contract`
(tier-3: no recent contract to correlate against -- both entry and bundle
stay mission_id-less).

---

### Donor UI security hardening, LIVE-only scope, upload caps (2026-07-07)

Skill-iteration bump only (`4.8.2.0` -> `4.8.3.0`); no SC-target change and
no parser pattern changes. Addresses code-review findings on the log
donation feature plus user-directed scope changes.

**Security (donor_ui/app.py)**
- Per-run session token (`secrets.token_urlsafe(32)`) generated in
  `DonorServer.__init__`, injected into the served `index.html` via a
  `<meta name="donor-session">` tag (template substitution on a placeholder
  comment, not a static-file mount). `app.js` reads the tag and sends it as
  `X-Donor-Session` on `POST /api/upload` and `POST /api/reset`; both
  routes 403 without a valid token (`secrets.compare_digest`).
- `Host` header check as a FastAPI middleware applied to every request:
  only `127.0.0.1:{port}` or `localhost:{port}` is accepted, else 403.
  Defeats drive-by CSRF and DNS rebinding against the local server.
- `/static/{filename}` now resolves the joined path and requires
  `resolved.parent == static_dir.resolve()`, replacing the old ad hoc
  `"/" in filename` guard. Blocks Windows drive-relative traversal
  (`C:foo`) that the old guard missed.
- Upload is now scoped to what the user actually saw: the preview response
  includes each candidate's sha256; `app.js` sends the previewed sha256
  list back on `POST /api/upload`; the server re-discovers (files may have
  rotated) but only uploads candidates whose hash is in that list.
- Dedup-store matching after upload is now sha256-only (dropped the
  `c.renamed == f.renamed` fallback -- `renamed` is a display string and
  collides across installs).

**Scope changes (user-directed)**
- Donation is now Live-install only (`scanner._INSTALL_NAMES = ("Live",)`).
  `discover_installs` / `discover_candidates` no longer look at PTU or
  HOTFIX at all.
- Donation requires a parseable `FileVersion` from the current Live
  `Game.log`; if the Live install or its version is missing, discovery
  raises `LiveLogUnavailableError` instead of silently returning an empty
  list, and the preview surfaces this as a distinct `error` field (not
  "no logs found").
- Client-side caps mirroring the Worker: files under 1 MB (`MIN_UPLOAD_FILE_BYTES`
  -- too small to carry usable session data) or over 50 MB are skipped,
  batches are capped at 50 files (newest-by-mtime kept when trimming). Both
  size bounds are inclusive (exactly 1 MB / exactly 50 MB are accepted).
  `scanner.apply_client_caps` / `discover_candidates_with_caps` surface
  `skipped_undersize_count`, `skipped_oversize_count`, and `trimmed_count`
  through the preview JSON and into the UI as separate, distinctly-worded
  reasons (added 2026-07-07, addendum to the original caps work same day).

**Other fixes**
- `main.py` donor bootstrap now catches `Exception` (was `ImportError` /
  `OSError` only) so a corrupt or locked `donor_state.sqlite` degrades to
  "no donor UI" instead of aborting `prepare()`. Both the missing-dependency
  and generic-failure paths now also emit a `printr` WARNING badge, matching
  `validate()`'s convention, not just a `logger.warning`.
- Donor state DB moved from a stray
  `${APPDATA}/Wingman/sc_log_reader/donor_state.sqlite` to this skill's own
  `get_generated_files_dir()/donor_state.sqlite`. `main.py` migrates the
  file on first run if the old path exists and the new one does not.
  `DONOR_STATE_DB_PATH` removed from `log_donor/_build_config.py`.
- `already_uploaded_count` in the preview is no longer hardcoded to 0 --
  `discover_candidates_with_caps` now counts files filtered out by the
  dedup store and wires the count through to the UI's "already donated"
  branches.
- A scan exception in `/api/preview` now returns a distinct `error` field
  instead of rendering as "no logs found"; `app.js` shows it in an
  `.empty-state.error` block.
- `uploader.Uploader._put_file` streams the file object to httpx instead of
  reading it fully into memory per PUT attempt, skips the retry sleep after
  the final attempt, and logs once when retries are exhausted. Candidates
  the Worker's begin-response silently drops are now appended as failed
  `FileUploadResult`s so upload progress always reaches the candidate
  total, and an unknown sha256 in the Worker's response now logs at debug
  level instead of silently continuing (both were open TODO polish items).
- `ui_dialog.CONSENT_BODY` is now served through `/api/preview` as
  `consent_text` and rendered client-side in `app.js`, replacing the
  hand-duplicated consent HTML. `format_file_row` (unused) removed.
- `main.py`: removed the dead `_donor_config` method; `unload()`'s donor
  teardown now catches `Exception` broadly (was `OSError`) so a teardown
  failure never blocks `super().unload()`; `_tool_donate_logs` now checks
  `donor_server.is_running` before opening a browser tab to a dead URL.
- Copied `assets/wingman-ai.ico` into `donor_ui/static/` -- `index.html`
  referenced it but the file was never shipped in the skill.

**Tests**
- `tests/test_donor_server.py` (new): FastAPI `TestClient` coverage for
  the preview JSON shape (including `error`, `already_uploaded_count`,
  `skipped_undersize_count`, `skipped_oversize_count`, `trimmed_count`),
  403 without/with-wrong session token, 403 on a forged `Host` header
  across every route, static path-traversal containment, sha256-restricted
  upload, and 409 on a concurrent upload/reset. The shared `fake_sc_install`
  fixture (`tests/conftest.py`) now pads its synthetic Game.log content
  past `MIN_UPLOAD_FILE_BYTES` so its candidates survive the new floor.
- `tests/test_scanner.py` gained undersize-skip coverage for
  `apply_client_caps`, including the exact-1-MB and exact-50-MB boundary
  cases (both inclusive/accepted).
- `tests/test_scanner.py` / `tests/test_log_donor_integration.py` updated
  for the Live-only scope (candidate counts, `discover_installs` no longer
  returning PTU) plus new tests for `LiveLogUnavailableError` and
  `apply_client_caps`.

## Version: 4.8.2.0

### Star Citizen 4.8.2 target bump (2026-06-28)

Rebaselined the skill metadata from `4.8.0.0` / SC target `4.8.0` to
`4.8.2.0` / SC target `4.8.2` for the current live-test pass. No parser
pattern changes in this bump.

## Version: 4.8.0.0

### Reward bundle reconciliation (2026-06-28)

Added canonical `mission_reward` event-log rows that group nearby reward
components into one mission-level reward bundle. `StateLogic` now keeps a
short-lived reward evidence buffer, attaches zero-MissionId reward notifications
to a recently completed contract when possible, preserves the existing
`reward_earned` / `blueprint_received` component entries for compatibility,
and flushes bundles before the next unrelated event so EventLog timestamp order
continues to work with restart dedup watermarks.

Parser reward cleanup: `blueprint_received` now extracts the shared
notification context (`notification_id`, `mission_id`, `objective_id`), and
legacy item rewards strip the trailing notification colon from item names.

Tests added for blueprint context extraction and money + item + blueprint
mission reward bundling. Verified with `python -m pytest
skills\\sc_log_reader\\tests -q`, targeted `compileall`, and Ruff.


### Live-test rebaseline (2026-05-25)

Version rebaselined from 4.8.0.2 to 4.8.0.0 to align all SC skills at a common
4.8.0.0 baseline for a coordinated local live-test pass against SC 4.8.0.
No code change; version strings only. Within-patch increments resume from
4.8.0.1 once test findings are incorporated.

## Version: 4.8.0.2

### Log donation feature live + post-launch fix cascade (2026-05-14)

Donation feature shipped end-to-end and verified against the live Cloudflare
Worker / R2 / D1 stack. Real SC logs successfully uploaded from a clean
install with no manual configuration.

**Bug cascade fixed during live testing** (one fix exposed the next, each
caught from the Wingman log):

1. `fastapi.staticfiles` submodule is not available in the Wingman runtime.
   Replaced `app.mount("/static", StaticFiles(...))` with an explicit
   `@app.get("/static/{filename}")` route that returns `FileResponse`. No
   dependency on the missing submodule. Path-traversal guard included.
2. FastAPI (Wingman's bundled version) fails to introspect
   `FileResponse | HTMLResponse` union return-type annotations even with
   `response_model=None`. Dropped the return annotation on `/` and
   `/static/{filename}` routes; FastAPI accepts the Response objects at
   runtime regardless.
3. `parse_game_version()` was written against an invented test-fixture
   format (`BranchName:` / `BuildId:`). Real SC Game.log writes
   `FileVersion: 4.8.180.28520` and `ProductVersion: ...` in the first 40
   lines. Switched the regex to capture `FileVersion:` (unique per build)
   and updated fixtures + assertions accordingly.
4. `DedupStore` opened its SQLite connection in the main thread during
   `prepare()`. The donor UI server runs in a daemon thread, so SQLite's
   Python-level cross-thread guardrail rejected access from FastAPI
   handlers. Added `check_same_thread=False` to the connection (we do not
   issue concurrent writes from multiple threads).
5. `extract_handle()` regex expected `name <handle> state` separated by
   whitespace only. Real SC log has `name <handle> - state` (dash separator
   on the AccountLoginCharacterStatus line). Replaced single regex with
   three patterns covering the three real markers SC writes during login:
   AccountLoginCharacterStatus, `Handle[X]`, and `nickname="X"`.
6. "Donate more logs" button left the server-side `_job_state.phase` at
   `"done"`, so a reload landed back on the same screen. Added
   `POST /api/reset` (refuses while a job is `running`) and updated the
   button to call it before reload.

**Settings panel tweaks**

- Removed `debug_file_output` custom property and its handling in
  `_create_stack`. We rely on Wingman logs for tracing.
- Notifications default to ON across the board, with these exceptions
  defaulting OFF to avoid noise: `notify_zone_entered_armistice`,
  `notify_zone_left_armistice`, `notify_jurisdiction_change`,
  `notify_hangar_access`, `notify_hangar_queue`, `notify_user_login`,
  `notify_session_start`, `notify_join_pu`.
- Removed the short-lived "Activate All Notifications" trigger toggle.
  Wingman framework limitations prevented the visual UI from reflecting
  the underlying state mutation cleanly.

**Settings panel hardening**

- Donor config (`donor_worker_url`, `donor_worker_token`,
  `donor_state_db_path`) moved out of `custom_properties` into a private
  `log_donor/_build_config.py` module so end users do not see internal
  build/secret values in the settings UI. `update_release.py` substitutes
  the token there at release-build time.
- Settings panel now shows a properly formatted "Hint" panel via the
  yaml `hint:` block (HTML-formatted) advertising the donate-logs voice
  command. The same hint is forwarded to the chat on skill startup via
  `self.printr.toast_info(...)` so users discover the feature without
  digging into settings.

**Install + ops**

- Rewrote `install.bat` to mirror youtube_video_player's structure:
  silent robocopy, goto-based flow, numbered "next steps" + numbered
  troubleshooting block. Notes that the WingmanAiCore process must be
  killed (not just the UI restarted) for code changes to take effect,
  because Wingman caches imported modules in `sys.modules`.

**Architecture note recorded during investigation**

Notification toggles (and the master `proactive_notifications` switch)
gate ONLY whether events are forwarded to Wingman for verbose narration.
All derived events are always written to
`sc_logreader_eventlog_<env>.jsonl`, the in-memory `_recent_events`
buffer, and the trade ledger. AI tool queries
(`get_recent_game_events`, `get_active_missions`, `get_trade_ledger`,
`get_trade_entries`) work regardless of toggle state. This is intentional.

---

## Version: 4.8.0.1

### Version bump for log donation feature (2026-05-14)

Bumped skill version to 4.8.0.1 (qualified against SC 4.8.0). See the
4.8.0.2 section above for the live-test fixes and the original 2026-05-14
section below (under 4.7.2) for the feature design.

---

## Version: 4.7.2

### New versioning scheme — mirror Star Citizen patch

Skill versioning now tracks the Star Citizen patch the skill is qualified
against, so dependent skills (sc_accountant and others) can programmatically
verify SC-version compatibility. Within a single SC patch lifespan, internal
updates append a dotted suffix (`4.7.2.1`, `4.7.2.2`, …).

Exposed as `__version__` and `__sc_target_version__` in `__init__.py`, and as
`SC_LogReader.VERSION` / `SC_LogReader.SC_TARGET_VERSION` for class-level access.
`skill_installer_config.json` carries both `version` and `sc_target_version`
fields. README header reflects the SC version qualification.

Replaces the previous independent SemVer track (last value `1.0.0`).

---

## Version: 1.0.0 (retired — superseded by 4.7.2 versioning scheme)

### Version bump to 1.0.0

Stable release. All core event types implemented and live-tested. Event log
write watermark prevents duplicate entries on restart. Blueprint parsing live.
Mission reward import working end-to-end with SC_Accountant.

---

## Version: 0.1.35

### Event Log Write Watermark + Blueprint Parsing

**Bug: Duplicate event log entries on Wingman restart**
Every restart triggered catch-up replay, which re-appended all events since last
login to the event log — creating duplicate entries. Fixed by adding a write
watermark to `EventLog`: on startup, reads the last timestamp in the file and
counts entries at that timestamp. During catch-up, any entry at or before the
watermark is silently dropped.

**New event: `blueprint_received`**
Parses `SHUDEvent_OnNotification` lines matching `"Received Blueprint: <name>: "`.
Classifier added in `_classify_event` (SHUDEvent block). Extractor added in
`_extract_event_data` — regex `r'Received Blueprint:\s*([^":]+)'` captures name
into `data["blueprint_name"]`. `logic.py` reads `event.data.get("blueprint_name")`
and sets `item_name` on the `EventLogEntry`.

**Removed duplicate extraction block**: A second `elif event_type == "blueprint_received"`
block (unreachable in elif chain) was writing to `data["name"]` instead of
`data["blueprint_name"]`. Removed.

**Files changed:** `event_log.py`, `parser.py`, `logic.py`, `main.py`

---

## Version: 0.1.34

### Fix — `reward_earned` for current CIG format

CIG changed mission reward notifications from `"You've earned: N aUEC"` to
`"Awarded N aUEC: "` via `SHUDEvent_OnNotification` (confirmed post 2026-02-06
patch). Updated classifier to match `Awarded ... aUEC` and extractor to parse
the new format first, falling back to legacy `You've earned:` for older logs.
Both formats store the amount in `data["amount"]`; `amount_auec` is set positive
(received). Legacy item-reward path (`data["item_name"]`) unchanged.

**Files changed:** `parser.py`, `main.py`

---

## Version: 0.1.33

### Hotfix — Derived Event Timestamps & Cosmetic Port Filter

**Bug: Derived events 2 hours ahead of raw events**
Game log timestamps are naive UTC. `datetime.now()` returns local time (UTC+2),
causing derived events (`mission_complete`, `zone_entered_armistice`, etc.) to
show timestamps 2+ hours ahead of the raw events that triggered them.

Fix: Changed `datetime.now()` fallback in `_fire_rule` and `_emit_derived_event`
to `datetime.now(timezone.utc).replace(tzinfo=None)` — always UTC when no source
timestamp is available. Added `_current_event_ts` tracking: set at the start of
`_on_raw_event` so event-based derived events (e.g. `hangar_access`,
`location_arrived`) inherit the exact raw event timestamp. Rule-based derived
events (fired before `_on_raw_event` during `_on_state_change`) still fall back
to UTC clock — within milliseconds of correct.

**Bug: Cosmetic item ports leaking into attachment_received**
`Beard_ItemPort` and `Piercings_*` ports were missing from `_COSMETIC_PORTS`.
Added: `Beard_ItemPort`, `Piercings_Eyebrows_ItemPort`, `Piercings_R_Ear_ItemPort`,
`Piercings_L_Ear_ItemPort`, `Piercings_Nose_ItemPort`, `Piercings_L_Eye_ItemPort`,
`Piercings_R_Eye_ItemPort`, `Tattoo_ItemPort`, `Scar_ItemPort`.

**Known: `reward_earned` not appearing**
CIG stopped emitting the `"You've earned: N aUEC"` line after the 2026-02-06
patch. Nothing to parse — this is a CIG-side regression.

**Files changed:** `parser.py`, `logic.py`, `main.py`

---

## Version: 0.1.32

### Event Log — Full Persistent Event History

Added `event_log.py`: append-only JSONL log of every meaningful game event,
written regardless of user notification settings. Serves as the data provider
for sibling skills (SC_Accountant etc.) that need historical queries like
"what rewards did I earn today?" or "when did I last arrive at Lorville?".

**Schema per entry:**
- `timestamp` / `event_type` / `location` / `player_name` — universal context
- `data` — full event-specific fields
- `amount_auec` — normalised financial value (+received / -spent) or None
- `item_name` — normalised item name where applicable

**What's logged:** all raw and derived events except internal pipeline mechanics
(`_money_sent_partial`, `shop_transaction_result`). Raw trade request events
(`shop_buy/sell`, `commodity_buy/sell`) are replaced by their confirmed
counterparts (written at the same point as the trade ledger).

**30-day trim** runs on skill startup per environment.

**Three new parser event types added:**
- `cargo_transfer` — freight elevator unstow (`FillUnstowRequest`)
- `refinery_submitted` — ore submitted to refinery (`OnRefineryRequest`)
- `attachment_received` — item equipped to player (`AttachmentReceived`,
  cosmetic ports filtered via `_COSMETIC_PORTS`)

**Parser fixes:**
- `reward_earned` now captures item rewards (e.g. "ASD Secure Drive") in
  addition to numeric aUEC amounts.

**Single source of truth:** `TradeLedger` retired from the write path.
Trades now write directly to the event log only. `ledger.py` kept on disk but
no longer used. `_GameStack.ledger` removed. AI tools `get_trade_ledger` and
`get_trade_entries` rewritten to query the event log. SC_Accountant sync will
be updated separately to read from the event log.

**Files changed:** `event_log.py` (new), `parser.py`, `logic.py`, `main.py`

---

## Version: 0.1.31

---

## Architecture Overview

SC_LogReader uses a **3-layer architecture** for clean separation of concerns:

```
┌─────────────────────────────────────────────────────────┐
│  Layer 1: main.py (AI Skill)                            │
│  - WingmanAI interface                                  │
│  - AI tools and notifications                           │
│  - Subscribes to Layer 2                                │
└─────────────────────────────────────────────────────────┘
                          │
                          ▼
┌─────────────────────────────────────────────────────────┐
│  Layer 2: logic.py (State Combiner)                     │
│  - Combines atomic states into derived events           │
│  - Mission tracking                                     │
│  - Rule-based event generation                          │
│  - Subscribes to Layer 3                                │
└─────────────────────────────────────────────────────────┘
                          │
                          ▼
┌─────────────────────────────────────────────────────────┐
│  Layer 3: parser.py (Log Reader)                        │
│  - Reads Game.log                                       │
│  - Classifies events                                    │
│  - Extracts atomic states                               │
│  - Standalone runnable                                  │
└─────────────────────────────────────────────────────────┘
```

---

## Design Principles

1. **Separation of Concerns**: Each layer has a single responsibility
2. **Standalone Operation**: Layer 3 and Layer 2 can run independently
3. **No Upward Dependencies**: Lower layers know nothing about higher layers
4. **Optional File Output**: JSON output for human debugging/inspection
5. **Easy Updates**: SC patches only affect Layer 3 parsing patterns

---

## Files

| File | Layer | Purpose |
|------|-------|---------|
| `main.py` | 1 | WingmanAI skill interface |
| `logic.py` | 2 | State combination and rules |
| `parser.py` | 3 | Log reading and parsing |
| `location_names.py` | 3 | Game code to name mapping |
| `clean.py` | - | Project cleanup utility |
| `__init__.py` | - | Package exports |
| `default_config.yaml` | - | Skill configuration |
| `requirements.txt` | - | Dependencies |
| `ledger.py` | - | Persistent trade ledger (JSONL storage) |
| `Devlog.md` | - | This file |
| `TODO.md` | - | Task tracking |
| `Test findings/EVENT_PATTERNS.md` | - | Comprehensive pattern documentation |
| `Test findings/test_patterns.py` | - | Pattern testing utility |

---

## Layer 3 API: LogParser

```python
from skills.SC_LogReader import LogParser

parser = LogParser("path/to/Game.log")

# Subscribe to events
parser.subscribe(lambda event: print(event.event_type))
parser.subscribe_state(lambda key, old, new: print(f"{key}: {new}"))

# Optional file output
parser.enable_file_output("debug_output.json")

# Control
parser.start()
parser.stop()

# Query
parser.get_state()           # All states
parser.get_state("ship")     # Single state
parser.is_running()
```

---

## Layer 2 API: StateLogic

```python
from skills.SC_LogReader import LogParser, StateLogic

parser = LogParser("path/to/Game.log")
logic = StateLogic(parser)

# Subscribe to derived events
logic.subscribe(lambda event: print(event.message))
logic.subscribe_raw(lambda event: print(event.event_type))  # Pass-through

# Custom rules
logic.add_rule(Rule(
    name="my_rule",
    trigger_key="in_armistice",
    conditions=[("ship", "exists", None)],
    event_type="custom",
    message_template="In ship while in armistice",
))

# Control
logic.start()
parser.start()

# Query
logic.get_combined_state()    # Atomic + derived
logic.get_active_missions()
```

---

## Changelog

### 2026-05-14 - Log donation feature (log_donor)

Added the `log_donor/` package and a browser-based donor UI for opt-in
upload of Star Citizen logs to a Cloudflare Worker / R2 backend.

**Discovery and upload flow**
- `log_donor/scanner.py` walks `Live` / `PTU` / `HOTFIX` installs, filters
  `logbackups/*.log` to those matching the current `Game.log` version per
  install, includes the active `Game.log` only when StarCitizen.exe is not
  running, and dedupes by SHA-256.
- `log_donor/handle_extractor.py` pulls the player handle from the log
  header so files can be renamed `{handle_or_unknown}_{original_name}`
  before upload (contributor attribution visible in R2).
- `log_donor/dedup.py` is a SQLite store with two tables: `uploaded_files`
  (content_hash -> upload_id) and `hash_cache` (path -> sha256, keyed by
  size+mtime).
- `log_donor/uploader.py` orchestrates one donation cycle: `/upload/begin`
  handshake, presigned R2 PUTs with bounded retries (408/425/429/5xx,
  exponential backoff), `/upload/complete` finalize. Always returns an
  `UploadResult` even on failure paths; uses context-manager protocol so
  the httpx client closes cleanly.
- `log_donor/ui_dialog.py` formats text used by both the consent body and
  the preview file rows.

**UI: FastAPI mini-server + browser**
- Original plan called for a settings-panel button, but the Wingman skill
  framework has no settings-panel button primitive. Pivoted to mirror
  `sc_accountant`'s pattern: a FastAPI server bundled in the skill,
  browser-launched via `webbrowser.open()`.
- `log_donor/donor_ui/app.py` exposes `GET /api/preview`, `POST /api/upload`,
  `GET /api/status`. The upload runs in a background daemon thread; the
  page polls `/api/status` every 1.5 s.
- `log_donor/donor_ui/window.py` is the thin `webbrowser.open(url)`
  wrapper.
- `log_donor/donor_ui/static/{index.html,app.js,style.css}` is the
  3-state UI: preview + consent, in-progress, done with per-file table.
- Triggered from voice: `@tool donate_logs` opens
  `http://127.0.0.1:7864` in the user's browser.

**Config (default_config.yaml custom_properties additions)**
- `donor_worker_url` -- defaults to the live Worker URL.
- `donor_worker_token` -- defaults to `__INJECT_AT_BUILD__`; substituted at
  release-build time by `update_release.py` from `DONOR_TOKEN_BUILD` env.
- `donor_state_db_path` -- defaults to
  `${APPDATA}/Wingman/sc_log_reader/donor_state.sqlite`.

**Companion repo**
- `sc-log-donate` (separate repo at `D:\PycharmProjects\sc-log-donate\`):
  Cloudflare Worker on `sc-log-donate.lars-erik-vaagen.workers.dev` with
  D1 (`sc-log-donate-meta`) + R2 (`sc-log-donations`). Operational state
  documented in `plans/2026-05-14-cloudflare-environment.md`.

**Test coverage**
- 31 tests in `tests/`: scanner discovery + version filter (10), dedup
  store (7), handle extractor (5), uploader handshake / PUT / orchestrator
  (8), end-to-end integration with mock Worker (1).
- UI server / browser frontend / main.py integration not unit-tested by
  convention (matches `sc_accountant`); manual smoke procedures in the
  Worker repo's TESTER.md.

---

### v0.1.31 (2026-03-22) — Performance & Coverage Notes
- **Confirmed: Ship exit is tracked** — `ship_exited` fires via the rule engine when the ship channel is left (`action == "left"` in `channel_change`). Both enter and exit are covered and have individual config toggles.
- **Analysis: No code-level lag sources** — All Python-side processing (parser loop, rule evaluation, state tracking, pending transaction cleanup) is lightweight and runs on a background thread. The only expensive operation is `_send_notification`, which triggers a full LLM inference + TTS pipeline — identical cost to a user voice command. Existing safeguards: 4-second batch window collapses rapid events into one AI call; 10-message auto-pause prevents runaway notifications; 10-second duplicate cooldown.
- **Known UX risk with all notifications active**: `notify_location_arrived` + `notify_jurisdiction_change` can both fire on the same area transition, and `notify_fuel_low` repeats every ~2 minutes. Heavy travel sessions with both enabled could consume the 10-message budget quickly. No code change required — this is a config guidance issue.

### v0.1.31 (2026-03-22)
- **Changed: Hangar events simplified** — Removed direction-aware hangar events (`zone_hangar_access`, `zone_takeoff_permit`, `zone_entered_hangar`, `zone_exited_hangar`) and the two-step armistice resolution logic. `hangar_ready` now emits a single `hangar_access` event immediately. Config toggle consolidated to `notify_hangar_access`.

### v0.1.30 (2026-03-22)
- **Fix: Death does not clear injury state** — `on_new_session()` in `logic.py` now scans all parser state keys and clears any `injury_*` entries. `session_start` (`AccountLoginCharacterStatus_Character`) fires on respawn after death, so injuries are correctly cleared when the player respawns.
- **Fix: `@dataclass` crash on skill load** — Removed `from __future__ import annotations` from `main.py`. Wingman's bundled Python hit a bug in `dataclasses._is_type` (`sys.modules.get(module, None).__dict__`) when annotations were stored as strings by PEP 563. Eager annotation evaluation at class definition time bypasses this entirely; Python 3.10+ union syntax (`X | Y`) is unaffected.
- **Fix: `debug_emitter` missing from release** — Added `debug_emitter.py` to `RELEASE_FILES` in `update_release.py`. The module is a silent UDP no-op in production but is imported at module level by `parser.py` and must ship with the release.

### v0.1.29 (2026-03-22)
- **Fix: F-11 — single-pass startup scan** — Removed duplicate full-file scan at skill startup. `LogParser.prepare()` now runs once via `_create_stack` before `_check_stack_session_change`; `_check_stack_session_change` reads `stack.parser.last_session_timestamp` from the cached result instead of calling `_find_last_session_timestamp`. The standalone `_find_last_session_timestamp` method in `main.py` has been removed entirely.
- **Fix: F-11 — robust `_startup_scanned` guard** — Replaced fragile `_last_session_ts is not None or _file_position != 0` check in `prepare()` and `start()` with an explicit `_startup_scanned: bool` flag. `prepare()` sets it on first call; `start()` checks it before running a fallback scan. Prevents double-scan in all cases including logs with no session_start.
- **Fix: F-09 — trade entries header variable rename** — Renamed `total` to `shown` in `_tool_get_trade_entries` to correctly convey that the count refers to entries shown, not a total in the database.
- **Fix: F-19 — mission ID truncation ellipsis** — `_tool_get_active_missions` no longer appends `...` unconditionally when slicing to 8 chars; `...` is only added when `len(mission_id) > 8`.

### v0.1.28 (2026-03-22)
- **Added: 9 new event types** — Cross-referenced against sc-companion Go project (sc_companion_comparison.md):
  - `qt_arrived` — `<Quantum Drive Arrived>` internal log: "Quantum Drive has arrived at final destination" — confirmed in test logs
  - `fined` — SHUDEvent "Fined X UEC" — extracts `amount` (UEC, commas stripped)
  - `transaction_complete` — SHUDEvent "Transaction Complete:" — no data (confirmed in test logs)
  - `incapacitated` — SHUDEvent "Incapacitated:" — player downed (distinct from `injury`)
  - `money_sent` — two-line SHUDEvent: "You sent PlayerName:" then "X aUEC" on next line — extracts `recipient` + `amount`; uses `_pending_money_sent` accumulator in `_process_line`
  - `blueprint_received` — SHUDEvent "Received Blueprint: {name}:" — extracts `name` (4.7+ content)
  - `fatal_collision` — `<FatalCollision>` internal log — extracts `vehicle` + `zone`
  - `insurance_claim` — `CWallet::ProcessClaimToNextStep` internal log — extracts `urn` + `request_id`; confirmed pattern in test logs
  - `insurance_claim_complete` — `CWallet::RmMulticastOnProcessClaimCallback` internal log — extracts `urn` + `result`; confirmed pattern in test logs
- **Added: 10 new config toggles** — `notify_qt_arrived`, `notify_fined`, `notify_transaction_complete`, `notify_incapacitated`, `notify_money_sent`, `notify_blueprint_received`, `notify_fatal_collision`, `notify_insurance_claim`, `notify_insurance_claim_complete`
- **Architecture: multi-line accumulation** — `_pending_money_sent` field added to `LogParser.__init__`; `_process_line` checks for pending state before normal parsing and combines two-line money_sent notifications into a single `money_sent` event
- **Fix: `join_pu` shard extraction** — was extracting join index `[0]`/`[1]` from `{Join PU}` line; now matches `<Join PU> address[...] shard[pub_euw1b_...]` line to extract real shard name; also captures `server_address`; confirmed from actual Game.log samples

### v0.1.27 (2026-03-22)
- **Added: 7 new event types** — All patterns confirmed via Research Pass 1 (157 PTU log files):
  - `fuel_low` — SHUDEvent "Low Fuel:" — fires every ~2 min while fuel stays low
  - `bleeding` — SHUDEvent "Bleeding:" — player started bleeding
  - `crimestat_increased` — SHUDEvent "CrimeStat Rating Increased:"
  - `vehicle_impounded` — SHUDEvent "Vehicle Impounded: {reason}:" — extracts reason
  - `party_member_joined` — SHUDEvent "{player} has joined the party." — extracts player name
  - `party_left` — SHUDEvent "You have left the party."
  - `qt_calibration_complete_group` — SHUDEvent "Quantum Travel Calibration Complete By {player}:" — party member's QT ready; classify check placed before existing `quantum_calibration_complete` to prevent overlap
- **Added: 10 new config toggles** — `notify_fuel_low`, `notify_bleeding`, `notify_crimestat_increased`, `notify_vehicle_impounded`, `notify_party_member_joined`, `notify_party_left`, `notify_qt_calibration_complete_group`; grouped under Health, Law, and Social sections
- **Fixed: `qt_calibration_complete_group` ordering** — `"Quantum Travel Calibration Complete By"` check now comes before `"Quantum Travel Calibration Complete"` in `_classify_event` so group events are not swallowed by the own-player check

### v0.1.26 (2026-03-22)
- **Changed: Injury reminder is now zone-triggered** — Replaced the escalating timer (5, 10, 15, 20, 25 min) with an armistice-entry trigger. The `health_injury_reminder` derived event fires whenever `in_armistice` transitions to `True` (direct zone entry or returning from a hangar) if the player has active injuries. Timer fields, `_start_injury_reminder`, `_stop_injury_reminder`, and `_on_injury_reminder_tick` removed from `logic.py`. Check lives in `_on_state_change`, before the pending-hangar block, so it fires on all armistice entries regardless of context.

### v0.1.25 (2026-03-22)
- **Changed: Multi-environment monitoring** — Skill now monitors LIVE, PTU, EPTU, HOTFIX, and TECH-PREVIEW simultaneously. Any `Game.log` found under those subfolders is picked up automatically. Since only one SC instance runs at a time, the parser that receives new lines becomes the "active" stack; AI tools always query the most recently active environment.
- **Changed: Settings path updated** — `sc_game_path` now expects the `StarCitizen` folder (e.g., `C:/Roberts Space Industries/StarCitizen`) instead of the `LIVE` subfolder. Backwards compatible: if an old LIVE path is configured, the skill detects the `Game.log` directly and steps up to the parent automatically.
- **Changed: Per-environment state files** — State is now persisted as `sc_logreader_state_LIVE.json`, `sc_logreader_state_PTU.json`, `sc_logreader_state_HOTFIX.json` in each environment's folder (replacing the single `sc_logreader_state.json`).
- **Changed: Per-environment trade ledgers** — Trade ledgers are now `sc_logreader_ledger_LIVE.jsonl`, `sc_logreader_ledger_PTU.jsonl`, `sc_logreader_ledger_HOTFIX.jsonl` (LIVE aUEC ≠ PTU test aUEC).
- **Architecture: `_GameStack` dataclass** — Each environment gets a `_GameStack(env, game_path, log_path, parser, logic, ledger, state_saved_at, last_event_at)`. `SC_LogReader` maintains `_stacks: list[_GameStack]` and `_active_stack: _GameStack | None`. Per-stack closures wire event handlers, catch-up suppression, and active stack tracking. Replaces single `_parser`/`_logic`/`_ledger`/`_game_path`/`_log_path` fields.
- **Removed: `_catching_up` skill field** — Catch-up suppression moved into per-stack closures (`if s.parser._catching_up: return`). Raw event collection into `_recent_events` still happens during catch-up (for AI tool queries); notifications are suppressed.

### v0.1.24 (2026-03-21)
- **Fixed: State change events no longer forwarded to wingman** — Removed `_parser.subscribe_state(_on_state_change)` subscription in Layer 1. Raw state key/value pairs (e.g. `"State: atc_available: False"`, `"State: last_contract_accepted: A Call to Arms"`) were appearing alongside their derived event counterparts in the Game Events bubble. The derived events already carry all meaningful context; the raw state strings are implementation detail. `_on_state_change` method and `_HAS_DERIVED_STATE` set removed as dead code.
- **Changed: Per-event notification toggles replace category system** — `default_config.yaml` now has one `boolean` toggle per distinct message that can reach the wingman (37 event toggles + master `proactive_notifications`). All default to `false`. Removed: `notify_contracts`, `notify_objectives`, `notify_zones`, `notify_ships`, `notify_travel`, `notify_health`, `notify_social`, `notify_economy`, `notify_trades`, `notify_session`, `notify_journal`, `notify_state_changes`. Removed: deprecated `notify_missions`, `notify_quantum` (no longer shown in UI; backwards-compatible code behaviour unchanged).
- **Changed: Derived event types made specific** — `logic.py` previously emitted broad types (`"zone"`, `"ship"`, `"mission"`, `"location"`, `"objective"`, `"health"`) making per-event toggle control impossible. All 14 derived event types renamed to specific strings: `zone_entered_armistice`, `zone_left_armistice`, `zone_hangar_access`, `zone_takeoff_permit`, `zone_entered_hangar`, `zone_exited_hangar`, `ship_entered`, `ship_exited`, `location_arrived`, `mission_accepted`, `mission_complete`, `mission_failed`, `mission_objective_new`, `health_injury_reminder`.
- **Changed: Unified event toggle map** — `_EVENT_CATEGORY_MAP` + `_DERIVED_CATEGORY_MAP` → single `_EVENT_TOGGLE_MAP` mapping every event type (raw and derived) directly to its config toggle ID. `_should_notify_category()` → `_should_notify(event_type)`, checking master switch + per-event toggle. `_DISABLED_BY_DEFAULT` set removed — all events default to `false` via `_get_config_value(toggle, False)`.
- **Note: `notify_trades` was dead config** — Trade events (`shop_buy`, `shop_sell`, `commodity_buy`, `commodity_sell`, `shop_transaction_result`) were in `_HAS_DERIVED_EVENT` so never forwarded as raw, and `logic.py` writes them to ledger without emitting derived events. No notification was ever sent. Toggle removed with the category system; not replaced.

### v0.1.23 (2026-03-12)
- **Added: `user_login` event type** — Triggered by `User Login Success - Handle[X]` log pattern. Extracts `player_name` from the handle field. Routed through `notify_session` category.
- **Added: Session replay on startup** — Parser scans Game.log for the last `User Login Success` line and replays all events from that point forward, building up current session state. Notifications to wingman are suppressed during catch-up (`_catching_up` flag) to avoid TTS spam from historical events. On reaching EOF, catch-up completes and notifications resume.
- **Added: DevKit NodeView (`devkit_nodeview/`)** — True dynamic node graph visualization of the parsing pipeline. Each event type, state key, rule, and output is its own node. Edges are discovered dynamically from packet stream timing. Animated SVG bezier paths with glow particles trace live data flow. 4-column layout: Events → States → Rules → Output.
- **Changed: DevKit entry points renamed** — `devkit/main.py` → `devkit/devkit.py`, `devkit_nodeview/main.py` → `devkit_nodeview/Devkit_node.py`

### v0.1.22 (2026-03-12)
- **Fixed: `player_name` not appearing in State Monitor** — Parser starts at EOF and misses `session_start`. Added fallback extraction from `location_change` events (`Player[name]` pattern in `RequestLocationInventory` lines). Only sets `player_name` if not already known from `session_start`.
- **Fixed: `ship` state not set for human-readable channel names** — Ship channel heuristic only checked coded manufacturer prefixes (`AEGS_`, `ANVL_`, etc.). Star Citizen sometimes uses human-readable channel names (`Aegis Avenger Titan : Mallachi` instead of `@vehicle_NameAEGS_Avenger_Titan : Mallachi`). Added `SHIP_MANUFACTURER_NAMES` tuple for human-readable detection.
- **Added: `ship_owner` state** — Extracted from the ` : PlayerName` suffix in ship channel names. Set on `channel_change` join, cleared on leave.
- **Added: `own_ship` state** — Boolean derived by comparing `ship_owner` against `player_name`. `True` = player's own ship, `False` = someone else's ship, `None` = unknown.
- **Updated: DevKit dashboard** — Ship group in State Monitor now displays `ship_owner` and `own_ship` alongside `ship`.

### v0.1.21 (2026-03-12)
- **Added: Debug dashboard (DevKit)** — Real-time state visualization via web browser/tablet. Runs as a separate process, connects via UDP fire-and-forget. Not included in release version.
- **Added: `debug_emitter.py`** — UDP emitter module (port 7865). Sends JSON packets for raw events, state changes, derived events, and rule firings. Zero impact when dashboard isn't running (UDP silently drops).
- **Added: `devkit/` directory** — Standalone FastAPI + SSE dashboard with 4 panels: Log Reader, State Monitor, Event Stream, Rule Evaluations. Dark theme, tablet-responsive.
- **Architecture:** Parser/logic emit via UDP → DevKit bridge receives → SSE pushes to browser. No modifications to core skill behavior.


- **Added: Station departure detection** — `AImodule_ATC` + `DoEstablishCommunicationCommon` re-enabled as `station_departed` event. Controlled testing with 4 isolated Game.log sessions proved that `AImodule_ATC` fires exclusively when a ship clears station airspace (departure), never on approach or terminal use. The original v0.1.13 false positives were caused by `AImodule_Cargo` (terminal/console interactions), not `AImodule_ATC`.
- **Added: "Departed station" derived event** — Logic layer emits `location`-type derived event on departure, routed through `notify_travel` config toggle
- **Changed: Station departure clears arrival dedup** — `_last_arrived_location` reset on departure so returning to the same station re-triggers "Arrived at" notification
- **Removed: `atc_available` and `atc_location` states** — No longer meaningful. ATC is a departure event, not a persistent state. Armistice-exit clearing of these states also removed.
- **Removed: Old `atc_established` event** — Replaced entirely by `station_departed`

**Investigation methodology:** 4 controlled Game.log sessions at Seraphim (RR_CRU_LEO):
1. On foot + terminal only → zero `AImodule_ATC`, only `AImodule_Cargo` on terminal use
2. Depart station → `AImodule_ATC` fires once on clearing station airspace
3. Depart + return (same session) → ATC on departure only, NOT on return
4. Fresh login in space + approach station → zero `AImodule_ATC` on approach

Cross-referenced with 164 historical log files (4,344 events): ATC and Cargo are independent services, not paired arrival/departure signals. ATC has named locations (LorvilleATC01, etc.), Cargo is always unnamed.

### v0.1.19 (2026-02-10)
- **Added: Trade ledger** — Persistent JSONL ledger that tracks all item shop and commodity buy/sell transactions across sessions. The ledger is never reset automatically — it survives session changes, skill reloads, and wingman restarts. Stored in `{generated_files_dir}/sc_logreader_ledger.jsonl`.
- **Added: 5 new parser event types** — `shop_buy`, `shop_sell`, `shop_transaction_result`, `commodity_buy`, `commodity_sell`. Item shop transactions use 2-phase confirmation (request → `RmShopFlowResponse`); commodity trades write immediately.
- **Added: `ledger.py` module** — Standalone `LedgerEntry` dataclass and `TradeLedger` class with `append()`, `query()` (time range, category, transaction filters), and `summarize()` (totals + per-item breakdown).
- **Added: `get_trade_ledger` tool** — Financial summary with per-item profit breakdown. Default time range: `last_12_hours`. Supports time range filters (last_12_hours, last_hour, today, this_week, this_month, this_year, all) and category filters (item, commodity, all).
- **Added: `get_trade_entries` tool** — Individual trade entry listing with pagination (default 50, max 200). Shows timestamp, location, item/commodity, price, and shop name. Default sort groups purchases first, sales last (`sort_by: "type"`); `sort_by: "time"` for chronological order.
- **Added: `notify_trades` config toggle** — Enables/disables trade event notifications (default: enabled).
- **Added: `_extract_bracketed()` helper** — Reusable parser method for extracting multiple `key[value]` fields from log lines.
- **Added: Pending transaction management** — Logic layer stores item shop requests in `_pending_transactions` until confirmed by `RmShopFlowResponse`. Stale pending transactions cleaned up after 10 seconds. Pending list persisted in state file, cleared on new session.
- **Added: Diagnostic logging** — Trade event flow now logs at key decision points (pending stored, confirmation matching, ledger write, stale cleanup) for runtime debugging.
- **Added: SC_LogReader to Computer wingman template** — `discoverable_skills` in Computer.template.yaml now includes `SC_LogReader`.
- **Fixed: UTC vs local time in pending cleanup** — `_cleanup_stale_pending()` compared `datetime.now()` (local time) against `event.timestamp` (UTC from log). Pending transactions appeared hours old and were immediately cleaned. Fix: store `received_at: datetime.now().isoformat()` for staleness, keep `event_timestamp` for ledger records.
- **Changed: Deprecated config defaults** — `notify_missions` and `notify_quantum` now default to `false` (were `true`). These toggles are unused but kept for backwards compatibility.
- **Added: Prompt guidance for summary vs list** — Prompt now distinguishes "tell me about" (→ `get_trade_ledger` summary) from "show me" (→ `get_trade_entries` list). Default list sort: purchases first, sales last.
- **Fixed: Duplicate ledger entries** — Two causes: (1) `_initialize_stack()` could be called twice (e.g., auto-activate), creating orphaned parser/logic that processed events in parallel. Fix: idempotent guard stops existing stack before creating new one. (2) Game may log duplicate request lines. Fix: pending transaction dedup by event_type + shop_id + kiosk_id + item_guid.
- **Updated: Cleaner v1.3.0** — Added SC_LogReader state file scanning (common game paths), generated_files debug output cleanup, and `--trade-data` flag for explicit trade ledger deletion.
- **Tests: 553 total** (up from 546)

### v0.1.18 (2026-02-09)
- **Fixed: Backwards compatibility for saved configs** — Added deprecated `notify_missions` and `notify_quantum` property IDs back to `default_config.yaml`. Users upgrading from pre-v0.1.6 had these old IDs in their saved wingman config; the `__merge_list` ID-based merge couldn't find matching defaults, resulting in bare `{id, value}` entries that failed Pydantic validation (missing `name`, `property_type`). The deprecated entries are ignored by skill code but satisfy the config merge.
- **Updated: README.txt** — Reflects current v0.1.18 properties, correct installation path (`custom_skills/`), added upgrade and troubleshooting sections.

### v0.1.17 (2026-02-08)
- **Added: Injury reminder timer** — Escalating reminder notifications when the player has active injuries. Fixed schedule: 5, 10, 15, 20, 25 minutes (5 reminders total, not user-configurable). Timer starts on injury, stops on full med bed heal or death. Schedule index resets on new injury, full heal, or death. Emits `"health"` derived events listing active injuries with severity and body part.
- **Added: `health` derived event category** — `_DERIVED_CATEGORY_MAP` now routes `"health"` events through `notify_health` config toggle
- **Tests: 499 total** (up from 482)

### v0.1.16 (2026-02-08)
- **Fixed: Silent notification delivery failure** — `_flush_batch()` runs on a Timer thread; any unhandled exception silently killed delivery for all future events. Refactored into `_flush_batch()` wrapper + `_flush_batch_inner()` with top-level try/except logging. Also added `_on_notification_done()` callback on the `run_coroutine_threadsafe` Future to catch async exceptions that were previously swallowed.
- **Fixed: INVALID_LOCATION_ID reported as arrival** — CIG sends `Location[INVALID_LOCATION_ID]` in `RequestLocationInventory` log lines. Parser still extracts it (Layer 3 unchanged), but the `arrived_at_location` rule in logic.py (Layer 2) now has a `!=` condition that suppresses the derived event.
- **Changed: State change notifications simplified** — Format changed from `"State: key: old_value -> new_value"` to `"State: key: new_value"` — only the current value is reported to the wingman.
- **Fixed: Redundant state change notifications** — State keys that are already covered by logic layer derived events (`location`, `location_name`, `star_system`, `in_armistice`, `ship`) are now suppressed in `_on_state_change`. Previously a location change would produce three raw state notifications plus the "Arrived at: X" derived event.
- **Fixed: Notification delivery using dedicated threads** — Replaced `run_coroutine_threadsafe` (which depended on the main event loop) with dedicated thread + throwaway event loop per notification — the same pattern PTT uses in wingman_core.py. The main event loop was silently not processing queued coroutines, causing all notifications to stop while PTT voice commands continued working on their own throwaway loops.
- **Fixed: Returning to same location produces no notification** — Location arrival was state-based (rule fired on `location_name` state change). The StateStore suppresses duplicate values, so returning to a location the player never officially "left" produced no notification. Moved to event-based handling in `_handle_event_derived`: every `location_change` event now emits "Arrived at: X" regardless of previous state. INVALID_LOCATION_ID filter preserved in the event handler.
- **Known issue: Config migration on property rename** — Tester hit Pydantic validation errors (`name` and `property_type` missing) after upgrading from pre-v0.1.6 config that still had `notify_missions` and `notify_quantum` (renamed to `notify_contracts` and `notify_travel`). WingmanAI saves custom properties as `{id, value}` only; orphaned entries that no longer exist in `default_config.yaml` have no template to merge with, so Pydantic rejects them. Fix: tester deletes and re-adds the wingman. Note for future: renaming or removing custom properties is a breaking config change for existing users.
- **Tests: 482 total** (up from 480)

### v0.1.15 (2026-02-07)
- **Added: Star system tracking** — `location_names.py` now uses `LocationInfo` NamedTuple with `name` and `system` fields instead of plain strings. Every location in the map carries its star system (Stanton, Pyro, Nyx, or Jump Point).
- **Added: `get_location_system()` function** — Returns the star system for any location code. Direct map lookup with case-insensitive fallback, plus prefix-based derivation for unknown codes (e.g., `Stanton*` → Stanton, `Pyro*` → Pyro).
- **Added: `star_system` state key** — Parser now sets `star_system` on every `location_change` event alongside `location` and `location_name`. AI tools can now answer "What system am I in?"
- **Added: Stanton-Nyx Jump Point** — `RR_JP_StantonMagnus` / `JP_StantonMagnus` mapped (CIG currently routes as Stanton→Nyx)
- **Changed: Quantum route notification** — Now reports "Quantum jump target set, ready for jump calibration" without destination name. Destination codes in logs are unreliable (LOCRRS codes, asset IDs like `ab_mine_stanton1_sml_003`). `quantum_destination` state key removed.
- **Changed: `add_location_mapping()` signature** — Now accepts optional `system` parameter (defaults to "Unknown")
- **Fixed: State change double-posting** — `_should_notify_category()` used `True` as default fallback for all categories, causing state changes to leak through when the property wasn't in the user's saved config. Categories that default to disabled (`notify_state_changes`, `notify_session`, `notify_journal`) now properly default to `False`.
- **Improved: Hangar/takeoff context-aware sequencing** — `_pending_hangar` changed from `bool` to `str | None` to distinguish context:
  - `hangar_ready` while `in_armistice=True` → "Hangar access granted" → exit armistice → "Entered hangar"
  - `hangar_ready` while `in_armistice=False` → "Takeoff permit granted" → enter armistice → "Exited hangar"
  - After exiting hangar, next armistice exit fires normal "Left armistice zone" (not another hangar event)
  - Legacy `True`/`False` state files auto-migrate to new format
- **Fixed: "Objective complete: Unknown" spam** — `objective_complete` and `objective_withdrawn` notifications suppressed when objective data is missing (CIG logging bug). Returns `None` instead of "Unknown" fallback.
- **Tests: 480 total** (up from 411)

### v0.1.14 (2026-02-07)
- **Added: Hangar entry/exit detection via armistice sequencing** — `hangar_ready` now sets a `_pending_hangar` flag instead of immediately emitting landing/takeoff. The next armistice transition resolves direction:
  - `in_armistice=True` → `hangar_ready` → `in_armistice=False` = **"Entered hangar"** (player took elevator from station common area into hangar)
  - `in_armistice=False` → `hangar_ready` → `in_armistice=True` = **"Left hangar"** (player returned from hangar to station)
- **Changed: Hangar events suppress normal armistice rules** — When a pending hangar is resolved, the armistice transition is consumed by the hangar event (no "Entered/Left armistice zone" fires alongside it)
- **Changed: `hangar_ready` now emits "Hangar access granted"** — Immediate acknowledgement before the direction is resolved
- **Added: `_pending_hangar` flag persisted** in `save_state()`/`load_state()` for crash resilience

### v0.1.13 (2026-02-07)
- **Reverted: Notification pipeline back to `wingman.process()`** — The v0.1.11 lightweight pipeline (`print_async()` → constrained `llm_call()` → `play_to_user()`) stripped the wingman of all emotional involvement. Events were injected as bare user messages with a restrictive prompt that suppressed the wingman's personality. Reverted to `wingman.process(transcript=message)` which runs events through the wingman's full personality pipeline (system prompt, backstory, natural LLM reaction, TTS).
- **Removed: `_get_event_reaction()` and constrained prompt** — No longer bypasses the wingman's personality with a separate LLM call
- **Removed: Manual message injection** — No longer appends events as `{"role": "user"}` messages directly to `wingman.messages`
- **Changed: Throttle cap raised from 5 to 10** — More headroom before notifications pause
- **Note: If chat locking returns**, adjust throttling parameters first (cap, batch delay) before rearchitecting the pipeline

### v0.1.12 (2026-02-06)
- **Fixed: Missions not cleared on new game session** — Parser starts at EOF and misses `session_start` written before it attached. New `_check_session_change()` scans Game.log for the latest `session_start` timestamp and compares against the state file's `saved_at`. If the log has a newer session, `on_new_session()` is triggered.
- **Fixed: Event details missing from conversation memory** — `print_async()` only displays in UI, doesn't add to wingman's conversation history. Event text is now also added as a user message to `self.wingman.messages` so the wingman remembers contract names, objectives, and locations for later queries.
- **Added: 5 new tests** — Session change detection: new session clears, same session preserves, edge cases (411 total)

### v0.1.11 (2026-02-06)
- **Fixed: Notification pipeline blocking other wingmen** — Replaced `wingman.process()` (full LLM+TTS pipeline) with a lightweight three-step pattern: `print_async()` → `add_assistant_message()` → `play_to_user()`
  - Text appears in UI immediately, TTS plays separately
  - No longer holds the wingman in a "busy" state during notifications
  - Other wingmen's written communication no longer halts
- **Added: In-character event reactions via `_get_event_reaction()`** — Lightweight `llm_call()` (no tool execution) gets a brief personality response to game events
- **Added: Per-notification prompt prefix** — Instructs LLM to react briefly without repeating event details
- **Added: System prompt guidance** — Permanent instruction in `default_config.yaml` for brief, conversational event reactions like a copilot acknowledging a situation

### v0.1.10 (2026-02-06)
- **Added: State persistence across WingmanAI restarts** — Parser and logic state saved to `sc_logreader_state.json` on shutdown, restored on startup
  - `StateStore.load_dict()` — bulk restore without triggering change notifications
  - `LogParser.save_state()` / `load_state()` / `clear_state()` — public state persistence API
  - `StateLogic.save_state()` / `load_state()` — persists active missions and derived state
  - `SC_LogReader._save_state()` / `_load_state()` — JSON file I/O in game directory
- **Added: Session-start mission clearing** — On `session_start` event, only mission-related state is wiped (active missions, objectives, contract history); all other state (location, ship, injuries, etc.) is preserved since it persists in the game between sessions
  - `StateLogic.on_new_session()` — clears missions and 7 mission-related parser state keys
  - Triggered automatically when parser detects `session_start` in the log
- **Added: 28 new tests** — StateStore load_dict (4), parser persistence (6), logic persistence (5), logic session clearing (6), main.py disk persistence (7) — 406 total

### v0.1.9 (2026-02-06)
- **Added: Game.log retry mechanism** — When Game.log is not found at startup, the skill retries every 30 seconds until the file appears (handles post-crash scenarios where the game's crash handler moves Game.log)
- **Refactored: Path discovery** — Extracted `_discover_log_path()` from `validate()` for reuse by retry mechanism (DRY)
- **Refactored: Stack initialization** — Extracted `_initialize_stack()` from `prepare()` for reuse by retry callback
- **Fixed: `debug_file_output` config access** — Changed from `retrieve_custom_property_value()` (which expects `errors` list) to `_get_config_value()` (correct for non-required properties)
- **Added: 11 new tests** — Retry timer lifecycle, discover_log_path, unload cleanup (378 total)

### v0.1.8 (2026-02-06)
- **Added: Comprehensive pytest test suite** — 367 automated tests across 7 test files covering all 3 layers
  - `test_location_names.py` (40 tests): LOCATION_MAP entries, case-insensitive lookup, fallback behavior
  - `test_state_store.py` (18 tests): set/get, subscribers, clear, thread safety
  - `test_parser.py` (144 tests): event classification, data extraction, timestamps, ship names, state updates, file handling
  - `test_logic.py` (35 tests): rule operators, trigger keys, default rules, mission tracking, derived events
  - `test_main.py` (69 tests): AI tools, notification system, throttling, event routing, category maps
  - `test_integration.py` (11 tests): cross-layer pipeline, contract lifecycle, state propagation
  - `test_regression.py` (50 tests): replay all 14 real Game.log files, player name verification, event distribution
- **Added: 6-phase manual test checklists** — `manual_checklists/` directory with phase1-6 markdown checklists
- **Fixed: "left the channel" not detected** — Parser now matches `"left the channel"` in addition to `"left channel"` (bug found by automated tests)
- **Fixed: `get_active_missions()` shallow copy** — Returns deep copy to prevent callers from mutating internal state
- **Fixed: `validate()` parameter bug** — `retrieve_custom_property_value("sc_game_path", "")` now correctly passes `errors` list instead of empty string

### v0.1.7 (2026-02-06)
- **Changed: ATC tracking is now state-only** — Removed `atc_disconnected` event; ATC is purely a state (`atc_available`) updated by `DoEstablishCommunicationCommon`
- **Changed: ATC deactivation tied to armistice exit** — Leaving armistice zone now clears `atc_available` and `atc_location` states
- **Added: ATC logic rule** — `atc_available: True` triggers "Contact established with ATC" derived event via logic.py
- **Fixed: ATC log spam** — Repeated ATC lines no longer generate notifications; StateStore suppresses duplicate state values
- **Removed: `atc_disconnected` event** — No longer classified or tracked as a separate event

### v0.1.6 (2026-02-05)
- **Added: Category-based notification toggles** — Replaced 5 narrow toggles with 11 category-based config toggles (contracts, objectives, zones, ships, travel, health, social, economy, session, journal, state_changes)
- **Added: Raw event forwarding** — Events without derived counterparts in logic.py now produce human-readable notifications directly from main.py
- **Added: State change notifications** — Optional toggle (`notify_state_changes`, off by default) forwards raw state changes to wingman
- **Added: `_format_raw_event()`** — Formats all raw event types into human-readable messages for wingman notifications
- **Added: `_forward_raw_event()`** — Routes raw events through category checks and batching
- **Added: `_on_state_change()`** — Subscribes to parser state changes for state notification forwarding
- **Changed: `_should_notify()` → `_should_notify_category()`** — Simplified to single category lookup
- **Changed: `_on_derived_event()`** — Now uses `_DERIVED_CATEGORY_MAP` for category resolution
- **Added: Module-level constants** — `_EVENT_CATEGORY_MAP`, `_DERIVED_CATEGORY_MAP`, `_HAS_DERIVED_EVENT` for clean event routing
- **Removed: `notify_quantum`** — Replaced by `notify_travel` which covers location, quantum, and ATC events
- **Removed: `notify_missions`** — Replaced by `notify_contracts` (same scope, clearer naming)

### v0.1.5 (2026-02-05)
- **Added: Event/state separation** - Formal categorization of all log patterns into events (one-time triggers) and states (persistent conditions)
- **Added: 13 new event types** - `contract_shared`, `contract_available`, `objective_withdrawn`, `objective_complete` (data extraction), `monitored_space_down`, `monitored_space_restored`, `journal_entry`, `restricted_area`, `hangar_queue`, `quantum_calibration_started`, `quantum_calibration_complete`, `party_invite`, `incoming_call`, `refinery_complete`, `emergency_services`
- **Added: 3 new states** - `in_monitored_space` (bool), `jurisdiction` (string), `in_restricted_area` (bool)
- **Fixed: `jurisdiction_change`** - Now extracts jurisdiction name from notification text (was returning empty data)
- **Fixed: `objective_complete`** - Now extracts objective text and mission ID (was classified but no data extracted)
- **Fixed: `objective_complete`/`objective_withdrawn`** - Now clear `current_objective` state
- **Added: `XNAA_` manufacturer code** - For Xi'an-manufactured ships (e.g., SantokYai)
- **Removed: `private_property`** - Not found in any test logs; replaced by `restricted_area`
- **Changed: Monitored space** - Now tracked as persistent `in_monitored_space` state, supports Down/Restored variants
- **Added: ATC communication tracking** - `atc_established`/`atc_disconnected` events from `CSCCommsComponent` + `AImodule_ATC` lines, with `atc_available` (bool) and `atc_location` (string) states

### v0.1.4 (2026-02-03)
- **Added: Location name mapping** - New `location_names.py` module with static dictionary mapping game codes to human-readable names
- **Added: `get_location_name()` helper** - Translates codes like `RR_MIC_LEO` → "Port Tressler", falls back to cleaned code if unmapped
- **Changed: Location notifications** - Now display human-readable names instead of raw game codes (e.g., "Arrived at: Port Tressler")
- **Added: `location_name` state** - Parser now stores both raw `location` code and translated `location_name`
- **Files added**: `location_names.py`

### v0.1.3 (2026-02-02)
- **Added: Notification throttling** - Prevents AI notification spam when user is AFK
- **Added: `_auto_messages_since_user_input` counter** - Tracks consecutive auto-messages
- **Added: `_notifications_paused` flag** - Pauses notifications after 5 auto-messages without user input
- **Added: `on_add_user_message()` hook** - Resets counter and resumes notifications when user engages
- **Added: `_max_auto_messages` setting** - Configurable threshold (default: 5)

### v0.1.2 (2026-02-01)
- **Fixed: Skill auto-activation** - Added `auto_activate: true` to ensure skill starts monitoring immediately on wingman load
- **Fixed: Async event loop** - Captured event loop during `prepare()` for cross-thread notification dispatch
- **Fixed: Notification delivery** - Changed from non-existent `process_proactive_message` to `wingman.process(transcript=...)`
- **Fixed: Config value retrieval** - Added `_get_config_value()` helper with proper default value support
- **Fixed: execute_tool signature** - Changed parameter from `wingman` to `benchmark` to match base class
- **Added: Landing/takeoff permit logic** - `hangar_ready` event now generates "Landing permit granted" (in armistice) or "Takeoff permit granted" (not in armistice)
- **Added: Event-based derived events** - New `_handle_event_derived()` for events that aren't state-based
- **Added: Mission/objective notifications** - Derived events now generated for contract_accepted, contract_complete, contract_failed, objective_new
- **Added: AI prompt** - Added prompt to skill config explaining available game state tools
- **Added: Documentation** - Created `EVENT_PATTERNS.md` with comprehensive pattern reference
- **Added: Test utility** - Created `test_patterns.py` for testing new log patterns
- **Added: Future roadmap** - Updated TODO.md with prioritized list of new events for gamers and roleplayers
- **Changed: hangar_ready handling** - Treated as event, not persistent state
- **Removed: Debug output** - Cleaned up all print() statements after debugging complete
- **Removed: mission_ended event** - Unverified pattern (`<EndMission>`) removed; contract events handle mission lifecycle

### v0.1.1 (2026-02-01)
- Fixed injury parsing: severity before "Injury Detected", body part between dashes
- Fixed med_bed_heal: match `part: true` pattern instead of just part name
- Fixed location_change: extract from `Location[xxx]` pattern
- Fixed channel_change duplicates: only match SHUDEvent lines
- Fixed ship name cleanup: `@vehicle_NameMISC_Hull_C : Player` → `Hull C`
- Fixed quantum_route_set: match `Player has selected point X as their destination`
- Added UpdateNotificationItem filter to prevent duplicate events
- Removed SC_LiveLogManager skill completely (replaced by SC_LogReader)
- Updated user config to use SC_LogReader
- Parser standalone testing successful with live Game.log

### v0.1.0 (2026-01-31)
- Initial 3-layer architecture implementation
- Layer 3: LogParser with event classification and state extraction
- Layer 2: StateLogic with rule engine and mission tracking
- Layer 1: SC_LogReader skill with AI tools and notifications
- Migrated event patterns from SC_LiveLogManager
- Added standalone entry points for Layer 2 and Layer 3
- Added optional JSON file output for debugging

### Movement ledger reconciliation pass (2026-06-27)

Reviewed June 2026 PTU/LIVE logs against the movement-ledger mission and fixed the largest confirmed economy gap. The parser now recognizes both `CEntityComponentShopUIProvider` and `CEntityComponentShoppingProvider` shop flows. The logic layer resolves ShoppingProvider confirmations that only include `playerId`/`result`, writes one confirmed trade movement, and suppresses nearby HUD `Transaction Complete` rows when they only confirm that trade.

`EventLogEntry` now carries movement metadata: `movement_category`, `movement_verb`, `confidence`, `fingerprint`, and `source_events`. Existing `event_type` values are preserved for compatibility.

Current reward status: aUEC rewards, blueprint rewards, and known legacy item reward notifications are distinguishable as separate entries, but a single mission reward containing money + item + blueprint is not yet grouped into one canonical reward bundle. See `plans/2026-06-27-movement-ledger-reconciliation.md` for the detailed findings, verification, and next-step plan.
