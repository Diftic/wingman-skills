# Satisfactory Assistant - TODO / Open Items

Status 2026-07-02: ROADMAP COMPLETE. All implementable phases (0-9) of
`SatisfactorySkillPlan.md` delivered and accepted; both section 15
definitions of done met. Released as v0.5.0 in `release_version/`
(443 tests passing). Highlights: LP factory planner with capability
gates, machine schedules, power budgets; five-stage reuse-aware master
plans with transitions and reservations; pins/bans and pace scenarios;
extraction and belt/pipe logistics modeling with explicit surpluses;
construction bills with commissioning checks and build todos;
actuals-vs-plan audit from the save; locate with schematic map
artifacts for the HUD. The live AppData install is still the
pre-planner version: install v0.5.0 when ready.

Designed deferrals (each with its unblocking condition, see DEVLOG):
mid-stage gate checkpoints (player tier state from saves), transport
links/station capacity/areas (layout data), miner purity and resource
wells.

---

## Resolved (performance maintenance - 2026-07-09)

- [x] Audit finding #11: `summary()` opened the SQLite store ~10 times per
      call. Now opens once and reuses it for all reads including `counts`.
      Behavior-preserving; `_open_store`/`_read` contracts unchanged.
- [x] Audit finding #11: `store_mirror_artifacts()` always rewrote
      `observations.jsonl`. Now rewrites only when history exceeds the cap
      (`max(50, window_saves * 4)`); at/under the cap the append is the only
      write. Health and returned dict unchanged.
- [x] Added `test_store_mirror_leaves_file_untouched_under_cap` and
      `test_store_mirror_caps_file_over_limit`; full suite `449 passed, 1
      skipped`.

## Resolved / implemented (factory mirror vertical slice - 2026-06-29)

- [x] Audited `@etothepii/satisfactory-file-parser@4.1.1` and its only runtime dependency, `pako@2.1.0`; no network/server/process execution behavior found in runtime scans.
- [x] Added quarantined Node save snapshot extractor and Python subprocess bridge.
- [x] Added Satisfactory Docs catalog loader for item/resource descriptors, recipes, buildables, manufacturer speeds, and extractor rates.
- [x] Added save-derived factory mirror artifacts for machines, expected input/output rates, inferred production lines, and rolling estimated health.
- [x] Added compact `audit_satisfactory_factory` tool; raw snapshots stay in generated artifacts, not tool responses.
- [x] Added tests for Docs parsing, expected rates, inferred clustering, zero-output streaks, and rolling deviation behavior.
- [x] Verified with `python -m compileall skills\satisfactory_assistant` and `python -m pytest skills\satisfactory_assistant\tests` -> `94 passed, 1 skipped`.
- [x] Smoke-tested copied real save `Nitric Acid is Outbound.sav`: `1130` machine candidates, `930` recipe machines, `172` extractors, `47` inferred lines after extractor fallback.

## Resolved / implemented (QC + discovery slice - 2026-07-01)

- [x] QC pass on `SSP-P8-W01`: `CHANGES_REQUESTED` at attempt 1
      (F-P8W01-1 live-save torn-read risk), fixed at attempt 2
      (copy-before-parse inside the workspace mirror dir), now `QC_PASSED`.
      98 -> 108 tests passing across both packages.
- [x] `SSP-P1-W01` cross-platform install/Docs discovery implemented and
      `QC_PASSED`: new `satisfactory_install.py` (six-step precedence,
      Steam `libraryfolders.vdf` parsing, Epic best-effort, locale
      fallback, searched-locations diagnostics); hard-coded drive-letter
      candidates removed from `satisfactory_docs.py`.

## Resolved (delegated pipeline - 2026-07-01, evening)

- [x] Roadmap Phase 1 COMPLETE: SSP-P1-W01 (discovery), W02
      (schematics/HUB gates), W03 (Project Assembly data + capability
      snapshots), W04 (memoized dataset + bounded lookup) all ACCEPTED.
- [x] SSP-P2-W01 (SQLite store foundation) and SSP-P2-W02 (workspace
      backend swap) ACCEPTED: journal writes are now transactional
      SQLite in `planning.sqlite3`; legacy JSONL imported idempotently
      and left untouched. Deferred data-loss finding F-W03-3 is RETIRED.
- [x] QC rulings logged in DEVLOG: one superseded storage-format test
      replaced under explicit authorization; pre-existing noqa:E402 and
      type:ignore tags accepted as loader-required convention (tracked
      debt); no new suppression comments permitted.

## Resolved (G3 acceptances - 2026-07-01)

- [x] `SSP-P8-W01` (mirror slice) and `SSP-P1-W01` (discovery) both
      ACCEPTED by the user.
- [x] F-P8W01-2 decided: keep `audit_satisfactory_factory` as a standalone
      third tool for now; fold it into `calculate_satisfactory_plan` when
      roadmap Phase 3 introduces the calculator.

## Open for next slices (factory mirror / Phase 1 dataset)
- [ ] Decode miner/resource-node resource descriptors and purity so miner rates stop assuming unknown/base behavior.
- [ ] Complete resource-well and geothermal expected-rate handling.
- [x] Parser packaging strategy: keep `node_modules` out of source/release, ship a pinned `package-lock.json`, and have `install.bat` run `npm ci --omit=dev --ignore-scripts` when npm is available.
- [x] Added `tools/save_parser/package-lock.json` with npm integrity pins for the parser runtime.
- [ ] Manually invoke `audit_satisfactory_factory` inside a running Wingman instance.
- [ ] Implement `focus` filtering for stored mirror artifacts if the compact audit output proves too broad.
- [ ] Update `release_version/` only after source QC passes.

## Resolved (Codex review pass 5 - 2026-06-17)

- [x] **Medium:** default context could exceed token target - `format_context`
      enforces a hard global char budget and de-duplicates blocked flows. Test added.
- [x] **Medium:** write-tool acks echoed unbounded titles - acknowledgement
      title clipped to 60 chars; stored title unchanged.
- [x] **Low:** non-ASCII ellipsis - `clip` now uses ASCII "..."; no Unicode
      ellipsis remains in source. Test added.

## Resolved (Codex review pass 4 - 2026-06-17)

- [x] **Medium:** status-focused context hid blocked flows - `matches()` now
      includes status (plus a "missing" alias). Tests added.
- [x] **Medium:** return size uncapped per field - hard caps on title (80),
      material-rate strings (48), and materials per flow (6 + "(+N more)"). Test added.
- [x] **Low:** travel parser could absorb unknown tokens - now delimiter-based
      (`split('?')` then `split('=',1)`); `_TRAVEL_KEYS` removed. Test added.

## Resolved (Codex review pass 3 - 2026-06-17)

- [x] **Medium:** large logs could miss a middle-only save switch - replaced
      head/tail sampling with line-by-line streaming (exact chronology, bounded
      memory). `max_log_bytes` property removed as obsolete. Regression test added.
- [x] **Low:** `resolve_save_file` could raise on filesystem errors - now
      wrapped in `OSError` handling, returns None. Tests added.

## Resolved (Codex full review - 2026-06-17)

- [x] **High:** resolver chose a stale save (source-type over chronology) - now
      newest recognized reference wins (travel URL or backup), session
      back-filled; whole-file read <= 8 MiB. Regression tests added.
- [x] **Medium:** focused context missed older matches - `summary(focus=...)`
      filters before truncation. Tests added.
- [x] **Medium:** containment fallback unsafe on case-sensitive FS - lowercase
      fallback now Windows-only. POSIX test added.
- [x] **Low:** stale `max_log_bytes` hint updated.
- [x] **Low:** discovery keywords expanded for crafting (recipe, inputs,
      outputs, materials, factory rates, bottleneck, machine count).
- [x] **Low:** helper modules renamed `satisfactory_*` to avoid `sys.modules`
      collisions with other skills' generic module names.
- [x] **Risk:** log rotation between selection and read now returns
      `no_active_save` instead of raising.

## Resolved (Codex first review - 2026-06-17)

- [x] **High:** tail-only detection in long sessions (superseded by the
      chronological-ordering fix above).
- [x] **Medium:** glob metacharacters in save names - direct profile-dir lookup.
- [x] **Low:** config coercion bounds - `_coerce_int` / `_coerce_bool`.

## Product decisions (confirmed by review)

- `status` param on `update_satisfactory_plan`: keep.
- "Configured directory is an explicit override": keep.
- `.sav` parsing stayed out of the original MVP; the 2026-06-29 mirror slice now has a reviewed local save-parser prototype pending QC and packaging.

## Still open for Codex (Phase 5)

- [ ] Manual tool calls inside a running Wingman for both tools (could not be
      done here: needs the app + a real `config`/`settings`/`wingman` object).

## Unverified assumptions (need a real install to confirm)

- [ ] **Multiplayer / dedicated-server** load-line format. Only single-player
      (`SessionDef_SinglePlayer`) was observed.
- [ ] **Epic (non-Steam) profile folder** naming under `SaveGames/`. Only a
      numeric Steam id was present in the test install.
- [ ] **Linux / Proton paths** are best-effort and untested.

## Feature ideas (user-requested, not yet packeted)

- [ ] HUD map pinpoint (requested 2026-07-01): when the user asks where
      something is, or the AI reports an event at a location, render the
      Satisfactory map with a coordinate pin and post it to the HUD.
      Verified groundwork already in place:
      - Machine world coordinates come from the save parser
        (`transform.translation`, world cm); the mirror stores
        per-machine `location` and per-line `centroid`.
      - The HUD renders images in notes and messages via markdown
        `![alt](path)` (hud_server/rendering/markdown.py `_load_image`,
        local file paths preferred; verified 2026-07-01).
      - Pillow is available in the Wingman runtime (hud_server uses it),
        so the skill can composite pin-on-map PNGs into the per-save
        workspace and reference them by path.
      Open design questions for the future packet:
      - Base map image source and licensing (community map vs generated
        schematic grid); world-to-pixel calibration constants must be
        verified, not guessed.
      - Delivery path: depend on the `hud` skill being active vs talk to
        the hud_server HTTP API directly from this skill.
      - Fits roadmap Phase 9 ("optional graph and map artifacts");
        candidate packet SSP-P9-W01 once the mirror/lookup surface
        stabilizes.

## Known follow-ups (not MVP)

- [ ] Replace `logo.png` placeholder with real art (256/512 PNG).
- [ ] Future enhancements from the plan: planner-export import, optional external
      imports, full recipe-rate planner/solver, optional proactive
      session-detection hook. Save parsing now has a reviewed local prototype;
      production packaging and resource-node completion remain open.

## Verified patterns (do not regress)

- Active save is resolved ONLY from the newest log; never fall back to the
  newest `.sav`.
- All writes stay inside `get_generated_files_dir()/saves/<safe_save_key>/`;
  containment is enforced with resolved-path checks (case-insensitive on
  Windows).
- Config values are retrieved just-in-time, never cached in `validate()`.
- Tool returns are compact summaries; no raw logs or raw JSONL dumps.


