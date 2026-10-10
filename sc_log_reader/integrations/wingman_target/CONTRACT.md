# Selected Wingman source contract

## Shipping name — 0.5.0

Folder and Python package: `sc_log_reader`. Wingman module:
`skills.sc_log_reader.main`; class and catalog name: `SCLogReader`.
The wrapper keeps `SCLogReader2` as an alias for existing saved configurations.
Both names construct the same implementation. The process registry is shared
with pre-rename readers so process ownership and restart boundaries stay intact.
Published and bundled JSON bytes are unchanged: their legacy `package_id` remains
accepted alongside `sc_log_reader`. Runtime paths are user settings and are not
renamed or reset. Existing active/previous objects and rejection lists are reused.

## Instruction updates — reader 0.4.2

This update policy supersedes approval wording in the historical sections below.
Valid JSON updates download and stage automatically at skill startup and every
six hours, then activate at a later Wingman process startup. Running instructions
never hot-reload. Instruction Recovery is a native single-select setting: choosing
Restore previous version schedules recovery for the next process startup and
blocks the rejected revision. The selection runs once; save No recovery requested
before selecting Restore again. Later revisions remain eligible for downloading.
The previous version and bundled fallback remain available locally. Downloads
remain restricted to direct raw.githubusercontent.com HTTPS JSON URLs.
Download/staging and recovery notices use Wingman's native INFO toast channel;
they do not trigger an AI response or speech. Actual client visibility must still
be checked in the running application.

## Current target: installed Wingman AI 3.2.2 (2026-09-20)

This section supersedes the historical 3.1.2 target below. Evidence comes from the
installed `C:/Program Files/WingmanAI/_internal` source and migration guide.
The skill declares `api_version: 3`, module `skills.sc_log_reader.main`, class
`SCLogReader`. The registration wrapper only defines its class during discovery;
core/native imports and origin checks happen when the host constructs the skill.
Both custom `dependencies` and bundled `venv/Lib/site-packages` layouts remain
supported. This Windows package targets the host's CPython 3.11 x64 ABI.

Reactions call the public `ai.generate`, `conversation.add_user/add_assistant` and
`tts.speak(..., interrupt=False)` capabilities. The installed `ai.converse` method
does not insert the system prompt despite its docstring, so it is not used.
Generation receives the configured character name/backstory, spoken language and
explicit event rules. It intentionally uses a small event-specific context rather
than the full conversation, compiled host system prompt, other skill prompts or
persistent memory. The short event and response are appended to conversation
history and displayed using Printr's retained special-payload interface. No tools
or commands are passed to the model or executed for reactions.

Existing category, catch-up, deduplication, batching, one-response-at-a-time,
ten-response budget and 120-second timeout limits are preserved. GUI delivery has
its own short timeout. Empty AI responses and display failures are counted. A TTS
call returning does not prove audible playback: the host can swallow TTS errors.

Plain status uses `self.log`. Lifecycle cleanup uses the public base methods; a
failed host cleanup must succeed before reprepare can add another subscription.
The seven legacy-style get_tools definitions remain supported by API v3.

Default JSON source: Diftic/main/skills/sc_log_reader/updates/instructions.json.
Updates still require human approval and a later eligible Wingman process.
No parser definitions, reader/handler behavior, runtime database or profile values
are changed by this integration migration. Live startup/audio must be checked
after restart; isolated tests are not evidence of actual playback.

## Historical qualification (3.1.2)

## Target and evidence

Diftic/wingman-ai `main` at `3cd87936585da5faf17aed6be6855d057253af0e`, declaring development **3.1.2**. The nine remotely inspected interfaces match the local `69a3cf0c5e362aff780c033d0ef7f7e52f9c7568` development snapshot after newline normalization. This is not released public 2.x support, a general API-3 claim, or frozen executable qualification. Evidence/hashes: `reports/implementation-20260917/host-contract-audit.md` and `diftic-source-audit.json` in the source project. Windows workflow pins CPython 3.11.7; isolated package tests use CPython 3.11.15 (same cp311 ABI) with regex 2026.9.10 win_amd64. Actual host/GUI/frozen installer tests remain unperformed.

## Verified adapter interfaces

- `skills/skill_base.py`: `Skill(config, settings, wingman)`; async `prepare()`, `unload()`, `update_config(new_config)`, `ensure_activated()`; fields `is_prepared`, `is_validated`, `is_unloaded`. `services/wingman_skill_manager.py` passes a `wingmen/wingman_context.py` WingmanContext facade, not a private Wingman reference.
- Legacy `get_tools() -> list[tuple[str,dict]]` and async `execute_tool(name, parameters, benchmark) -> tuple[str,str]` remain supported. Exactly the existing seven read-only tools are retained; the immediate-speech return is empty. Approval is never a tool.
- Base prepare subscribes secrets; base unload unsubscribes once using `is_unloaded`. Adapter resets that flag before each new prepare, drains admitted threads before closing SQLite, and retains late initialization ownership through cancellation. Unload waits at most two seconds for its shielded cleanup; delayed workers retain their runtime owner until closed. Config changes stop/drain, invalidate old-runtime launchers, update settings and prepare the new configuration. Missing required paths raise rather than return false success.
- Known host limitation: bulk `unload_skills` skips `is_prepared == false`; no adapter can promise cleanup when a host neither unloads nor cancels initial prepare. Direct unload and cancelled prepare are tested.

## Wingman reactions (local 2.1.1 installation)

The installed 2.1.1 host was inspected on 2026-09-19. Its public async
`wingman.process(transcript=...)` runs the conversation response and configured
voice pipeline, matching the archived reader's integration. `react_game_events`
opts into this path and takes precedence over GUI-only display. Distribution
defaults remain off; the user's approved local test installation enables it.
The inspected 3.1.2 WingmanContext does not expose `process`; reaction mode on
that facade reports unavailable. A future supported host entry point is still
required; the adapter does not reach through private host internals.

Selected canonical summaries from one poll are batched (at most three, each
512 characters). Only one reaction may be in flight; new events while busy
are recorded but dropped from speech. There is no delayed speech queue or
retry. Ten admitted responses pause reactions until real user input, matching
the original reader's cap. Unload cancels the reaction; the call timeout is
120 seconds. Existing category filters, repeat control and catch-up fences apply.
Visible transcripts contain only `[Game Event]` and one concise event, or
`[Game Events]` and a short list. Event-specific detail fields prevent a player
name from being presented as a location, ship or injury. Known locations use
their resolved name; unresolved location codes are explicitly labeled.
Boarding and leaving messages identify the player as the actor and the ship
as the target. These are inferred from the player's ship-channel changes,
not evidence of nearby traffic, sensors, ownership or pilot-seat occupancy.
Location, zone and health summaries also identify the player explicitly.
The public `get_prompt()` hook adds background instructions for brief,
in-character reactions grounded in stated facts, treating values as untrusted
and requesting no tools or commands. Saved custom prompts are retained. These
instructions are absent from visible event messages. This is model guidance,
not host-enforced tool isolation. Concurrent user speech retains host behavior.

Health reports admission, busy/paused drops, failures, timeouts and calls
returned. Because host process() catches some errors internally, return is
not proof of audible playback. Automated tests use host doubles; actual
provider/voice playback remains a live check after restarting Wingman.

## GUI notifications

With reactions off, the optional GUI sink is `services.connection_manager.ConnectionManager().active_connections` plus public async `send_to(LogCommand, websocket)` from `api.commands` with `api.enums.LogType.INFO`. This display-only mode makes no conversation or model call. Snapshot at most eight existing connections and wait at most 250 ms per message; cancel pending sends and never queue/retry. `send_to` swallows send failures and disconnects, so transport success additionally requires that the connection remains active. Counts describe completed transport, not proven visible frontend rendering. Unsupported sink is visibly unavailable in reader health.

Pure NotificationPolicy retains T6 default bounds/rates; `delivered` means policy flush emission. Sink `transport_successes`, `transport_failures`, disconnected drops and connection-cap drops are separate. Master setting defaults off; per-type notification switches default on under the master.

Version 0.5.1 restores 53 individual notification switches. The seven category
switches remain as labelled group masters so saved Wingman profile properties
still have valid definitions and disabled groups remain disabled after upgrades.
Armistice entry/exit share one switch. Ship boarding/leaving, location
arrival/departure, monitored-space entry/exit, monitoring offline/restored and
party membership changes are likewise paired. Contract outcomes, health events,
quantum stages and other distinct types have independent switches. Disabled
announcements never disable reading, state updates or persisted evidence.

Both a group master and its individual switch must be enabled for an announcement.
New individual switches default on, preserving the user's saved group choices.
Old directional switches are fallbacks only when the combined switch is absent;
conflicting old directions default off in that case. Direct upgrades from the
retired predecessor may need profile migration for removed legacy property IDs;
the supported settings upgrade here is from the replacement reader's seven groups.

Supported legacy event announcements have been restored with literal wording.
Requests (cargo, refinery, commodity and insurance) remain requests, and claim
callbacks are results rather than assumed success. Raw inventory/channel records
remain silent. The retired periodic injury-reminder timer is not recreated.
The ten-response pause, busy-response drops and repeat suppression are unchanged.
This panel/filter change requires a skill release; instructions.json cannot
replace Python code or settings definitions.

`present_poll` discards presentation for any environment whose prior OR resulting health says `catching_up`, nonzero `unread_bytes`, or nonzero `pending_records`. This includes the final backlog drain and empty polls. Incomplete framing/read-ahead (`pending_bytes`/`bytes_behind` alone) is not queued work and does not suppress ordinary traffic. Older health without detailed work fields uses bytes_behind conservatively. Durable evidence/state/history is unchanged.

## Next-process instruction boundary

Approval and rollback store a complete bounded Windows Toolhelp PID snapshot under the manifest lock; 2048 PID maximum, strict integer/duplicate validation, 64-KiB total manifest write limit. Snapshot failure is explicit unresolved state. First later host prepare can resolve it but defers; an additional restart may be needed. Legacy stages without a fence receive this conservative migration. Unknown identity/unsupported OS cannot activate a stage. PID reuse only causes extra deferral; wall-clock timestamps and stale JSON host records provide no authority.

Current PID plus GetProcessTimes creation FILETIME qualifies identity. An active digest retains its exclusion fence, so an old never-prepared host cannot load a digest promoted by a newer process. A stable `sys.modules` registry pins the first decision even without a stage and keeps an OS lock on the canonical runtime for the process lifetime, across unload/module recreation. A separate active-monitor claim excludes duplicate Services and stays held through deferred cleanup. Explicit standalone startup remains distinct and is refused against a live host-owned runtime. A runtime must not be shared by independent host processes; choose separate persistent directories.

An activating standalone watch now retains that exclusive runtime OS lease from before instruction selection/database initialization through successful Service database close. It does not create a host-registry decision. Watch-first host admission, host-first watch admission and two-watch contention are excluded in-process and across processes. Partial constructor cleanup closes the database before releasing; failed close retains ownership for retry. Host leases remain process-lived; standalone leases end on successful close. Non-activating replay and short status/check/review retain their existing scope.

## Human review and maintainer gap

`api.enums.CustomPropertyType` has no button/action type; `api.interface.CustomProperty` and Skill/WingmanContext have no review callback contract. The candidate therefore provides a **source-Python local launcher**, not a fake native button. After preparation, `<exact-runtime>/review-launcher.json` records an argv list with the exact Python executable and `<runtime>/review-updates.py`. A maintainer may invoke that argv list directly with `shell=False` on an explicitly wired human action. The script rejects another interpreter and shows its resolved runtime. It reads the runtime's recorded publisher; it embeds no URL. Moving runtime invalidates the previous launcher. A frozen sys.executable is not Python and produces visible launcher-unavailable health; no frozen launcher support is claimed.

Review displays version, exact SHA-256, notes, publisher, minimum engine version and qualified builds. Update/Later/Skip/Cancel/Rollback remain human controls, with displayed digest/source-generation checks and unchanged active instructions until eligible startup. Host launcher says next Wingman process startup; standalone CLI has separate wording. Native settings review action and frozen review runtime require maintainer integration and real-host qualification.

## Packaging and preservation

Registration exists only here and in staged candidate archives. Folder `sc_log_reader`, module `skills.sc_log_reader.main`, class `SCLogReader` match ModuleManager fallback resolution. Custom layout is `dependencies`; bundled/development Windows layout is `venv/Lib/site-packages`. The wrapper imports the packaged core/regex temporarily and their absolute package paths support delayed imports after ModuleManager removes its temporary sys.path entry. Conflicting already-loaded package origins fail clearly. Both layouts include native regex and bundled instructions JSON; tests launch isolated `-I` Python without development PYTHONPATH.

`tools/build_target_candidate.py --output <new skill reports folder>/sc_log_reader --regex-wheel <qualified cp311 win_amd64 wheel> --layout custom` creates an owned-file manifest and ZIP. Its Python `deploy`/`uninstall` helpers intentionally accept only skill reports or task temp folders starting `sc-reader-t8-`; no live installation occurs. Upgrade/uninstall move previous owned files to a uniquely named sibling backup, leaving unknown files and separate runtime/history/settings intact. No destructive directory deletion is used. Backup is the recovery artifact if a copy fails; this is not an atomic production installer.

Native Wingman ConfigService uninstall removes host skill overrides and deletes its custom code folder; **it does not preserve all host settings**. Do not use native uninstall as the first upgrade step. Final archive/domain comparisons are complete and local paced/recovery qualification is complete. Final 0.4.0 local artifacts are prepared under final-artifacts for controller binding/review; earlier packages remain historical. Publication and live installation need separate authorization. Publisher and bundled instruction revision 4 are byte-identical, unchanged by this engine release.

Current default publisher is Diftic main/skills/sc_log_reader/updates/instructions.json. Future ShipBit migration is explicit, invalidates pending source approvals, and requires the documented migration; this candidate does not silently switch publisher.
