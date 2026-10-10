# SC Log Donation Tool - Design

**Date:** 2026-05-14
**Author:** Mallachi
**Status:** Draft (awaiting user review)
**Scope:** A two-part system that lets Star Citizen players donate their game logs to the developer for analysis used to improve the `sc_log_reader` skill.

---

## 1. Purpose

The `sc_log_reader` skill parses Star Citizen `Game.log` files to translate raw log lines into structured gameplay events (kills, mining, missions, locations, economy, etc.). Improving the parser requires real-world logs across many playstyles and patch versions. This tool gives community members a one-click way to donate their logs.

**Player value:** none beyond the act of helping. Player credits are handled separately via Discord using a later tool that mines uploaded logs for handles. This tool is out of scope for credit generation or display.

**Non-goals:**
- No public upload form, no anonymous-stranger uploads
- No in-skill credits surface (handled separately)
- No content validation on the server (the skill is the trusted filter)
- No automated abuse detection / IP blocking (social trust is sufficient at this community scale)
- No background uploads or telemetry beyond the explicit donation action

---

## 2. High-level architecture

Two components in two repos.

```
[ player's PC ]                [ Cloudflare edge ]              [ Cloudflare R2 ]
 sc_log_reader                  log-donate Worker                logs bucket
 ─────────────                   ────────────                     ──────────
 "Donate logs" button   POST     mints presigned PUT URLs
   → scan installs    ─────→     logs manifest to D1
   → preview dialog                                              {date}/{upload_id}/
   → confirm + upload   PUT                                        manifest.json
                       ─────────────────────────────────→          {install}/*.log
```

**Repo 1: `wingman-ai/skills/sc_log_reader/` (existing)**
New code lives inside the skill. Respects the project's "skills folder only" hard rule.

**Repo 2: `sc-log-donate` (new, separate)**
Cloudflare Worker source + Wrangler config + D1 schema. Standalone lifecycle, separate from `wingman-ai`.

---

## 3. Skill-side component (`skills/sc_log_reader/log_donor/`)

### Package layout

```
skills/sc_log_reader/
  log_donor/                       (new package)
    __init__.py
    scanner.py                     install discovery + version match + SC-running check
    handle_extractor.py            extract player name from a single log
    dedup.py                       local SQLite store for uploaded-file hashes
    uploader.py                    Worker handshake + R2 PUTs + retries
    ui_dialog.py                   preview + consent dialog widgets
  main.py                          (edited) add "Donate logs" section to settings panel
  default_config.yaml              (edited) add donor.* config keys
```

### Public API

```python
class LogDonor:
    def discover_candidates() -> list[Candidate]
    # Walks Live / PTU / HOTFIX install paths. Per install:
    #   - reads Game.log header → current game_version
    #   - excludes Game.log itself if StarCitizen.exe is running
    #   - walks logbackups/, keeps files whose game_version matches
    # Computes SHA-256 of each survivor.
    # Drops any whose hash is already in local uploaded_files table.
    # Reads ~1000 lines of each remaining file to extract player handle.
    # Returns list of Candidate(path, install, game_version, size, sha256,
    #                            detected_handle, target_name).

    def preview(candidates: list[Candidate]) -> PreviewSummary
    # Counts and sizes per install, total bytes, file list for the dialog.

    def upload(candidates: list[Candidate], progress_cb) -> UploadResult
    # 1. POST /upload/begin with manifest -> upload_id + presigned PUT URLs
    # 2. PUT each file (bounded concurrency = 3, retry 3x with exponential backoff)
    # 3. POST /upload/complete with upload_id
    # 4. Record (sha256, upload_id) in local uploaded_files
    # Returns UploadResult(succeeded, failed, total_bytes).
```

### File-naming transform

Before upload, each file is renamed in-flight to `{handle}_{original_name}` where `handle` is the player name parsed from the log content. If no handle is parseable, `unknown` is used and the fact is shown in the dialog's details view.

### Settings-panel UI

A new collapsible section "Help improve this skill" containing:

- Button: **Donate logs**
- Status line: "Last donation: N days ago" / "No donations yet"
- Link: **What gets uploaded?** (opens the privacy explainer)
- Link: **Open log folder** (reveals `logbackups/` in OS file browser)
- Smaller link: **Forget my donations** (clears local dedup state and resets consent - does NOT delete server-side data)

### Config additions (`default_config.yaml`)

```yaml
donor:
  worker_url: "https://log-donate.<your-domain>.workers.dev"
  worker_token: "__INJECT_AT_BUILD__"   # replaced by update_release.py for release_version/
  consent_accepted_at: null             # ISO-8601 string when player first consents
  last_donation_at: null                # ISO-8601 string after each successful donation
  state_db_path: "%APPDATA%/Wingman/sc_log_reader/donor_state.sqlite"
```

The placeholder `__INJECT_AT_BUILD__` is replaced by the existing `update_release.py` build step when producing `release_version/`. The source-tree `default_config.yaml` never carries the real token; only the released artifact does. Token rotation is performed by updating the build-time env var, re-running `update_release.py`, and shipping a new skill release.

### Local state DB (`donor_state.sqlite`)

```sql
CREATE TABLE uploaded_files (
  content_hash  TEXT PRIMARY KEY,
  original_path TEXT NOT NULL,
  uploaded_at   TEXT NOT NULL,
  upload_id     TEXT NOT NULL
);

CREATE TABLE hash_cache (
  abs_path  TEXT PRIMARY KEY,
  size      INTEGER NOT NULL,
  mtime     TEXT NOT NULL,
  sha256    TEXT NOT NULL
);
```

`hash_cache` lets repeated scans skip re-hashing files whose `(size, mtime)` haven't changed - keeps the candidate-discovery scan fast on subsequent runs.

### SC running detection

On Windows: check for `StarCitizen.exe` in the process list (via `psutil`). If running, that install's live `Game.log` is excluded from candidates; logbackups for that install are unaffected.

---

## 4. Worker + R2 component (`sc-log-donate` repo)

### Stack

- Cloudflare Worker (TypeScript), deployed via Wrangler
- R2 bucket `sc-log-donations` (private, no public listing, no public download)
- D1 database `sc-log-donate-meta` (single SQLite-like DB at the edge)

### Endpoints

| Method | Path | Purpose |
|---|---|---|
| `POST` | `/upload/begin` | Receives manifest + per-file hashes. Returns `upload_id` and per-file `{put_url}` or `{already_uploaded, key}`. |
| `POST` | `/upload/complete` | Marks the upload complete in D1, records new file hashes, writes `manifest.json` to R2. |
| `GET`  | `/healthz` | Returns 200 `ok` for uptime checks. |

### Authentication

- Skill sends `X-Donor-Token: <secret>` header on `POST` endpoints
- Worker checks against `DONOR_TOKEN` env var (Wrangler secret)
- Mismatch → 401
- Low-effort obfuscation; rotate by setting a new secret and shipping a new skill release. Not a security boundary.

### Rate limiting

- Cloudflare native rate-limit rule on `/upload/begin`: max **10 requests per IP per minute**.
- Generous for legitimate use, throttles automation.

### R2 layout

```
sc-log-donations/
  2026-05-14/
    {upload_id}/
      manifest.json
      Live/
        Mallachi_Game_2026_05_14_14_30_22.log
      PTU/
        Mallachi_Game_2026_05_13_19_15_03.log
      HOTFIX/
        ...
```

### D1 schema

```sql
CREATE TABLE uploads (
  upload_id      TEXT PRIMARY KEY,
  created_at     TEXT NOT NULL,
  client_ip      TEXT NOT NULL,
  skill_version  TEXT,
  wingman_version TEXT,
  total_bytes    INTEGER,
  file_count     INTEGER,
  manifest_json  TEXT NOT NULL,
  complete       INTEGER DEFAULT 0
);

CREATE TABLE file_hashes (
  content_hash   TEXT PRIMARY KEY,
  upload_id      TEXT NOT NULL,
  r2_key         TEXT NOT NULL,
  first_seen_at  TEXT NOT NULL,
  FOREIGN KEY (upload_id) REFERENCES uploads(upload_id)
);
```

No `player_name` column. Player attribution lives only in R2 filenames and is mined post-hoc by a separate tool.

### What the Worker does NOT do

- No log content validation
- No virus scanning
- No public download endpoint
- No deletion endpoint (deletion is a manual, out-of-band operation)

---

## 5. Deduplication

Two layers, each correct on its own; combined for defense in depth.

**Skill-side (primary):**
- SHA-256 of every candidate file
- Hashes cached in local `hash_cache` keyed by `(abs_path, size, mtime)` to keep rescans cheap
- Files whose hash is in `uploaded_files` are excluded from candidates

**Worker-side (recovery):**
- `/upload/begin` payload carries per-file hashes
- For each hash already in `file_hashes`, the response marks that file `already_uploaded: true` and returns its existing `r2_key`
- Skill omits those from the PUT batch and adds them to local state at handshake completion (so a fresh-install client converges with server state in one round trip)

**Why two layers:**
- Skill-side covers the common case cheaply, no network roundtrip
- Worker-side covers reinstalls, machine moves, wiped state - global memory survives the client

**Cost:**
- SHA-256 over a 30 MB file: ~50–100 ms on modern hardware
- 50-file initial scan: 2–5 seconds, run on a background thread so UI stays responsive
- Subsequent scans hit the cache and are near-instant

---

## 6. Data flow (happy path)

```
PLAYER opens skill settings → clicks "Donate logs"
  │
  ▼
SKILL: scanner.discover_candidates()
  ├── for each install (Live, PTU, HOTFIX):
  │     ├── read Game.log header → game_version
  │     ├── if StarCitizen.exe running and owns this install → exclude its Game.log
  │     └── filter logbackups/ to matching game_version
  ├── compute SHA-256 (with cache)
  ├── drop hashes already in local uploaded_files
  └── per surviving file: extract handle from content → set target_name
  │
  ▼
SKILL: shows preview dialog (Variant 2)
  ├── header: "Found 17 logs to donate (24.8 MB)"
  ├── breakdown by install
  ├── expandable file list (filename, install, version, size, detected handle)
  └── [Cancel] [Upload]
  │
  ▼ (player clicks Upload)
SKILL → Worker: POST /upload/begin
  {
    "client_version": "...",
    "wingman_version": "...",
    "files": [
      {"original_name": "...", "renamed": "Mallachi_...",
       "install": "Live", "game_version": "...",
       "size_bytes": 5242880, "sha256": "..."},
      ...
    ]
  }
  Headers: X-Donor-Token: <baked secret>
  │
  ▼
WORKER:
  ├── validate token → 401 on mismatch
  ├── for each sha256: lookup in file_hashes
  ├── mint upload_id (UUID v4)
  ├── for new hashes: generate R2 presigned PUT URL
  │     key = "{YYYY-MM-DD}/{upload_id}/{install}/{renamed}"
  ├── insert uploads row (complete=0)
  └── return per-file {put_url} or {already_uploaded: true, key}
  │
  ▼
SKILL:
  ├── show "X file(s) already received in prior upload, skipping" if any
  ├── PUT each new file directly to R2 (concurrency=3, retry 3x w/ backoff)
  ├── update progress bar after each completion
  │
  ▼
SKILL → Worker: POST /upload/complete {"upload_id": "..."}
  │
  ▼
WORKER:
  ├── (optional) HEAD each expected key to verify presence
  ├── insert new sha256s into file_hashes
  ├── write manifest.json to R2 at {date}/{upload_id}/manifest.json
  ├── update uploads.complete = 1
  └── return 200
  │
  ▼
SKILL:
  ├── record (sha256, upload_id) for each succeeded file in local uploaded_files
  ├── update default_config.yaml: donor.last_donation_at = now
  └── toast: "Thanks! Donated 15 logs (24.8 MB)."
```

---

## 7. Error handling

| Failure | Detection | Behavior |
|---|---|---|
| No SC installs found | `discover_candidates()` empty | Toast: "No Star Citizen installs detected." |
| Install path set, `Game.log` missing | I/O error | Skip that install with a logged warning; continue with others. |
| All candidates already uploaded | Zero new files after filtering | Dialog: "All eligible logs have already been donated. Thanks!" No upload button. |
| Worker unreachable | POST raises | Dialog: "Couldn't reach donation server. Check internet and try again." No state changes. |
| Worker returns 401 | Token mismatch | Dialog: "Donation service rejected the request. Please update the skill." |
| Worker returns 5xx | Server error | Dialog: "Server is having trouble. Try again later." No state changes. |
| Single file PUT fails | After 3 retries with exponential backoff | Continue with remaining files. Final dialog: "Uploaded 14 of 16 logs. 2 failed (will retry next time)." Failed files are NOT recorded in local `uploaded_files`. |
| `/upload/complete` fails after PUTs succeeded | POST returns 5xx | Files are in R2; local state still records the hashes; Worker D1 row stays `complete=0`. Reconciler script (one-off, in Worker repo) can sweep these. |
| Player closes dialog mid-upload | UI cancel | Active PUTs allowed to finish (no abort). If all in-flight succeed, post `/upload/complete`; otherwise leave incomplete. |
| Handle not parseable from a log | `handle_extractor` returns None | File uploaded with `unknown_` prefix. Shown in dialog details so player notices. |

### State invariants

- A file's hash is recorded in local `uploaded_files` **only after** its R2 PUT succeeds. (Pessimistic - over-uploads in failure scenarios, never under-records.)
- Worker's `file_hashes` is updated **only at** `/upload/complete`. (Same direction.)
- Donation is always player-initiated. No silent retries, no background re-uploads. Failure → player sees result → can click again.

---

## 8. Privacy / consent

### What gets uploaded

- Raw `Game.log` and rotated `logbackups/Game_*.log` files
- These contain: in-game chat, player handle, character names, locations, mission events, deaths, hangar/loadout, vehicle ownership, in-game purchases, party/org membership, kills, error stacks
- No system-level info beyond what SC writes to its own log

### Metadata uploaded alongside files

- Skill version, Wingman AI version
- Per file: install type, detected game version, file size, SHA-256, original filename
- Each filename rewritten as `{handle_or_'unknown'}_{originalname}`

### Not collected

- No telemetry outside the explicit donation action
- No background uploads
- No system info / machine ID / network info beyond the IP Cloudflare logs at the edge (used only for the 10-req/min rate limit)
- No persistent player identifier beyond what's already in the logs themselves

### Consent surface

- **First-time press** of "Donate logs" shows a one-time consent dialog with the bullets above
- Must check "I understand what gets uploaded" before "Continue" enables
- Consent timestamp stored in `donor.consent_accepted_at`
- After consent, the standard preview dialog is shown every donation
- Settings panel always has a **What gets uploaded?** link with the full text

### Revocation

- **Forget my donations** clears local `uploaded_files` and resets consent
- Does NOT delete already-uploaded data from R2 (player informed of this in the dialog)
- Server-side deletion is a manual out-of-band process - contact the developer directly

### Player-facing description (skill UI)

> "Donating your Star Citizen logs helps improve sc_log_reader's parsing. Logs contain in-game activity (chat, locations, missions, deaths, etc.) and are sent to a private donation server (Cloudflare R2). They are not made public and are used only to improve the skill. You can read full details under 'What gets uploaded?' before sending anything."

---

## 9. Testing strategy

### Skill side

| Test | Type | What it covers |
|---|---|---|
| `test_scanner_install_discovery` | unit | Fixture filesystem with Live/PTU/HOTFIX. Missing installs skipped quietly. |
| `test_scanner_version_filter` | unit | Logbackups matching current Game.log version kept; mismatches dropped. |
| `test_scanner_skips_locked_gamelog` | unit | When mock `is_sc_running()` returns true, Game.log excluded; logbackups kept. |
| `test_handle_extractor` | unit | Real-shaped log fixtures with handle in different positions plus a corrupted fixture. Returns handle or None. |
| `test_dedup_local` | unit | Files with hashes in local SQLite excluded; rescans idempotent. |
| `test_hash_cache` | unit | Files whose `(size, mtime)` unchanged use cached hash; changed files re-hashed. |
| `test_uploader_handshake` | unit (mock Worker) | Payload shape, header injection, mixed already-uploaded/new response. |
| `test_uploader_retry_backoff` | unit (mock R2) | PUT failures retry up to 3x with backoff; persistent failure recorded. |
| `test_uploader_partial_failure` | unit | Mixed success/failure handled correctly in local state and complete handshake. |
| `test_ui_dialog_preview_summary` | unit | Summary text matches expectations for counts, sizes, install breakdown. |

### Worker side

| Test | Type | What it covers |
|---|---|---|
| `upload_begin_happy` | integration (Wrangler local) | Valid token + manifest → upload_id and signed URLs. |
| `upload_begin_auth_fail` | integration | Missing or wrong token → 401. |
| `upload_begin_dedup` | integration | Hash in `file_hashes` → response marks `already_uploaded: true`, omits put_url. |
| `upload_complete_marks_done` | integration | After /complete, D1 row `complete=1`; new hashes inserted. |
| `rate_limit_smoke` | integration | 11th request in a minute → 429. |
| `healthz` | integration | Returns 200 ok. |

### Manual / smoke (documented in `sc-log-donate/TESTER.md`)

- End-to-end: patched skill → staging Worker → staging R2. One full donation cycle. Verify files in R2 dashboard and D1 row.
- Token rotation: rotate `DONOR_TOKEN`, confirm skill gets 401, ship new build, confirm flow recovers.
- Failure injection: block Worker URL via hosts file, verify skill UX during outage.

### Explicitly NOT tested

- Cloudflare R2 storage durability (their responsibility)
- Wingman AI settings-panel framework (assumed to work)
- Cross-Wingman-AI installer system (separate concern)

---

## 10. Deliverables

**Skill side (`wingman-ai`):**
- New package `skills/sc_log_reader/log_donor/` with the five modules above
- Edits to `skills/sc_log_reader/main.py` for the settings panel UI section
- Edits to `skills/sc_log_reader/default_config.yaml` for the `donor.*` config block
- New tests under `skills/sc_log_reader/tests/test_log_donor_*.py` (location matches existing skill conventions)
- DEVLOG.md and TODO.md updates per project documentation rules

**Worker side (new `sc-log-donate` repo):**
- `src/worker.ts` implementing the three endpoints
- `wrangler.toml` with R2 binding, D1 binding, secrets, rate-limit rule
- `migrations/0001_initial.sql` for D1 schema
- Integration test harness (Wrangler local + miniflare or equivalent)
- README.md with deploy + rotate-token + reconcile-uploads runbooks
- TESTER.md with manual smoke procedures
- `.github/workflows/deploy.yml` for CI deploy to Cloudflare

---

## 11. Open questions / future work

- **Bandwidth-friendly large uploads.** Multipart upload to R2 isn't needed at 30 MB max, but if file sizes grow we'd switch from single-PUT to multipart.
- **Reconciler script.** A separate one-off script (in the Worker repo) that scans D1 for `complete=0` uploads older than 1 hour and either marks complete (if R2 has all the files) or flags for manual review.
- **Post-hoc player extraction tool.** Out of scope here. Will live in its own repo and read R2 directly via `rclone` or the R2 API.
- **Discord credits generation.** Out of scope here. Driven by the extraction tool above.
- **Possible second skill** (`sc_log_donor`) if this functionality grows large enough to be installable independently of `sc_log_reader`. Initial scope keeps it inside `sc_log_reader` to share the parser code.
