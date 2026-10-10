# SC NavPoint — Supervision Report

**Date:** 2026-08-02
**Orders:** `ProjectManagerReport.md`, two rounds (Codex, project manager)
**Role:** coding supervisor. No production code written on the main loop. All work delegated to
Opus 5 agents, staged as analyse, then plan, then implement, then validate, each a separate agent.

---

## 1. Read this first

**The reader is still broken.** NavPoint has produced no successful field capture since
**2026-07-31 22:07:10**. Everything below makes that failure legible, measurable and honestly
reported. None of it fixes it. The next step belongs to a flight, not to an agent.

**Nothing has been committed.** The work IS now installed: propagated to `release_version` and
installed to the live AppData skill on 2026-08-02, verified byte-identical at every hop, with the
custom-property ids confirmed matching in both directions so the 2026-08-01 startup failure cannot
recur. Section 3 is now a record of what was run rather than a list of what to do.

**Rollback for the skill:** restore
`...\scratchpad\live_sc_navpoint_before_release\` over `custom_skills\sc_navpoint\`.
**Rollback for the wingman config:** the `Laura.yaml.2026-08-02.bak` command in section 3.

**Tests: 536 at the start of the day, 654 after three waves, 676 after the findings work, 678 after
the third round.** One hundred and forty-two added. Three pre-existing test assertions changed in
the entire job, each one individually authorised by you as a spec change.

---

## 2. What is true now

| | |
|---|---|
| Skill version | `4.9.0.22`, deliberately not bumped |
| Dev tree | Contains all the work below |
| `release_version/` | **PROPAGATED 2026-08-02.** 18 files, byte-identical to the dev tree |
| Live AppData install | **INSTALLED 2026-08-02.** 17 runtime files, byte-identical to `release_version` |
| `Laura.yaml` | Edited: `prompt` and `discovery_keywords` deleted, backed up |
| Git | Nothing committed, nothing staged |
| Field status | Zero successful captures since 2026-07-31 22:07:10 |

### What changed for the player

**A failed capture now tells you what actually happened.** One message became nine, one per failure
kind, each saying what happened, exactly one action you can take or plainly that there is none, and
that nothing was saved. The `r_displayinfo 2` instruction now appears only when the overlay is
genuinely absent, down from every failure.

**`navigate_to` no longer lies.** It previously set the target, started the poll thread, opened the
HUD and returned "Bearing tracking begins once a local frame is available" on a *total* capture
failure. It now refuses and sets nothing.

**`update_position` no longer reports null coordinates as success.** A station interior reads
cleanly but has no usable frame; that payload used to pass straight through and return
`{"x": null, "y": null, "z": null}` with no error.

**The ring no longer shows a stale bearing as if it were live.** This was the most serious defect
found all day. On a scanner rejection the ring kept drawing a real deflection bubble from the last
good capture, with no message, indistinguishable from a current fix, for up to 30 seconds. At your
`poll_interval: 1` that is thirty consecutive failed polls. What moves in those seconds is your
ship, so the bubble was wrong by however far you had flown.

**The capture no longer blocks core for eleven seconds**, and each tool now reports its own
capture's diagnostics rather than whichever capture finished last.

---

## 3. What you have to do

**Step 0 is done.** The `Laura.yaml` edit is not a step. Do not re-add a `prompt` key.

**1. Close Wingman AI completely**, including ending `WingmanAiCore` in Task Manager if it sits in
the tray.

**2.** From `D:\PycharmProjects\wingman-ai`:

```
python skills\sc_navpoint\update_release.py
```

Verify: no `WARNING: ... not found`, and
`findstr /C:"via Vision AI" skills\sc_navpoint\release_version\default_config.yaml` returns nothing.

**3.** Run:

```
skills\sc_navpoint\release_version\install.bat
```

Verify:
`findstr /C:"via Vision AI" "%AppData%\ShipBit\WingmanAI\custom_skills\sc_navpoint\default_config.yaml"`
returns nothing.

**4. Start Wingman AI.** Confirm it reaches a running state, `_Star Citizen` loads, NavPoint appears
under Laura's skills, and there is NO Pydantic `name` / `property_type` error. That error is the
2026-08-01 signature and means roll back.

**5. Fly.** Then send `navpoint_poll.log`, `navpoint_poll.log.1` if it exists, and the PNG crops.

**Rollback**, and keep the backup because it is the only copy of the frozen prompt:

```
copy /Y "C:\Users\larse\AppData\Roaming\ShipBit\WingmanAI\backups\Laura.yaml.2026-08-02.bak" "C:\Users\larse\AppData\Roaming\ShipBit\WingmanAI\2_1_1\configs\_Star Citizen\Laura.yaml"
```

### What to expect on that flight

- **A passing skill-selection result alongside a still-failing capture is the expected outcome**,
  not a regression.
- The refused-frame dump is ON. Up to 20 PNG crops, newest kept, local only, never transmitted. Six
  failure kinds write one; `no_grab`, `no_reader` and `no_frame` do not.
- **The bearing bubble will disappear whenever a capture is refused**, including in glare, which
  over sunlit terrain is common. It pops rather than fades. You chose this knowing both. If it reads
  badly, the ready mitigations are in `FINDINGS_PLAN.md` R13c and each is a small change to one line.

---

## 4. Standing hazards

These outlive this session. Do not let a tidy-up remove them.

**NEVER run `skills\sc_navpoint\install.bat`, the dev-tree one.** It is byte-identical to the release
copy and its robocopy source is `"%~dp0."` with `/E`, so it copies whatever folder it sits in. From
the dev tree that means `tests/`, `ocr_dev/`, `ledger/`, `screenshots/`, every planning document and
the `.npz` backups land in your live skill folder. There is no `/PURGE`, so it stays until cleaned by
hand. Only ever the copy inside `release_version/`.

**`git checkout` on this folder would destroy work, not restore it.** `overlay_reader.py`,
`overlay_fields.py` and `ring_overlay.py` are entirely untracked, and `scanner.py`'s copy at HEAD is
196 lines against 658 today because HEAD predates the whole 4.9 line. Never `git clean` here.

**Do not strip the Vision code from `scanner.py`.** It is not dead: roughly 40 test call sites reach
still-live guards through `_parse_json_response`, including the unit-suffix requirement, the
plausibility gate and the space-frame rules. Stripping breaks a large fraction of 676 tests and there
is no git recovery. Its deferral is also why Vision could be decided on three times in three days at
zero rebuild cost.

**`_handle_server_change` is harmless only because `overlay_fields` never emits `server_id`.** The
three-count confirmation rule is recorded REFUTED and is not fixable by raising the count. Any future
work that makes the `Server:` line readable re-arms the path that destroyed six waypoints on
2026-07-26. Redesign the rule BEFORE emitting the field, not after.

**A ring string must be ASCII, 1 to 12 characters.** `ACQUIRING...` is three ASCII full stops, never
U+2026: the ring renders through PIL with a bundled font and a missing glyph draws as a literal box
on your HUD. Both spellings appeared in working notes today.

**`tests/test_refusal_thresholds.py` pins the refusal thresholds by source text.** A reformat of
`overlay_reader.py` will break it spuriously. Restore the formatting; never delete the test.

**Editing a skill's `prompt` in `default_config.yaml` does nothing at runtime once a wingman has been
saved.** The loader re-reads the file and copies exactly two fields over it, `custom_properties` and
`prompt`, from the saved wingman config. `description` and `discovery_keywords` come from the file.

**A `PostToolUse` hook creates zero-byte files** whenever edited code contains a `-> dict` style
annotation, because the hook runs through `cmd` and `>` redirects. You chose to sweep rather than fix
it. Forty-three were swept today, 22 from the repo root and 21 from the skill root, and more will
appear on every edit.

They cannot reach your live install through the supported route: `update_release.py` rebuilds
`release_version` from an explicit allowlist. They would only travel via the dev-tree `install.bat`,
which is already the thing nobody may ever run. So this is hygiene, not a release hazard.

When sweeping, require all four gates together: zero bytes, untracked, a regular file, and a name
that is obviously debris. Delete one at a time by literal name; several contain shell
metacharacters. And note that a file being written is momentarily zero bytes, so never run a sweep
concurrently with an agent that creates files.

---

## 5. What was built

### Waves 1 to 3, from the first orders

| Wave | Contents | Tests |
|---|---|---|
| 1 | Per-attempt tracing, poll-log rotation, `CaptureOutcome` with ten failure kinds, capture lock | 536 to 587 |
| 2 | Per-cell refusal diagnostics, success baseline, refused-frame dump, nine per-kind messages, `navigate_to` fix, badge rewording, capture off the event loop | 587 to 651 |
| 3 | Metadata corrections, `Laura.yaml` cleanup, two validator defects, frame dump enabled | 651 to 654 |

### The findings work, from the second orders

| Step | Contents |
|---|---|
| 1 | `update_position` refuses a no-frame payload |
| 2 | One outcome-to-ring mapping applied AFTER scanner validation, into a new `_last_ring_state` field |
| 2S | The bubble is suppressed on a refusal (your decision D-1) |
| 3 | Each caller reports its own capture's diagnostics, via a `contextvars` sink |
| 4 | The capture duration on the success line is the caller's own |

Tests 654 to 676, every step hitting the plan's predicted count exactly.

### Where the reader fix will be decided

`overlay_reader.py:569` refuses a cell when `cost > REFUSE_COST` **or** `margin < REFUSE_MARGIN`.
Those mean opposite things: high cost is "nothing in the glyph bank matched", low margin is "two
glyphs matched almost equally". **The fix for one is not the fix for the other, and the log recorded
neither.** It does now. That single missing field is why nobody could say what was wrong.

Two further facts, established by reading the row dumps rather than the summaries. The failure is
**not** alignment: labels, zone ids and most digits decode perfectly, and three or four scattered `?`
cells inside the coordinate fields cost the whole capture because `trusted` is `refused == 0`. And no
success baseline existed because ink and periodicity were computed inside the `if payload is None`
branch, so they could only ever be recorded on a refusal.

**The strongest lead is measured, not guessed.** The alignment self-heal refit costs **+310 ms per
read**, and by `overlay_reader.py:725` it fires whenever nothing decodes as trusted, which in every
observed failure is every read. That is roughly 1.5 seconds of an 11 second mark spent refitting an
origin that was not wrong. Instrumentation item I4 logs `from_cache` and `refit`, so your first
flight confirms or kills it.

---

## 6. What the orders got wrong

Both PM reports were broadly sound and their central instincts were right. These did not survive
verification.

| Claim | Verdict |
|---|---|
| The proposed message fix (reuse ring state) | **Insufficient.** Ring state is computed before `parse_payload` and returns OK whenever a payload exists, so all six safety refusals would have reported as fine |
| "Vision output passes through the existing gates" | **False as written.** Three of six gates were conditional or refuted |
| `navigate_to` shares the wrong-message bug | **Refuted, and it was worse.** It emitted no message at all and silently accepted the failure |
| The `mark_location` tool description claims Vision | **Refuted.** No `@tool` description named a reader |
| The metadata fix as specified | **A runtime no-op.** The prompt is governed by a fourth file nobody had recorded |
| "Ink and periodicity were healthy and stable" | **Half unfounded.** All four measurements in history were on refusals; no baseline existed |
| VisionAI misuse is a pattern | **One occurrence** across all 44 core logs |
| "Make the capture return a result object" (finding 3) | **Unreachable.** Pinned shut by ~20 assertions and an exact source-substring test |
| The `_handle_server_change` wipe risk on finding 1 | **Unreachable in production.** A wrong-answer bug, not a data-loss bug |

Findings 1 to 4 in the second orders were all **confirmed**, and two of them were defects I had
identified in this report that morning and then failed to ensure the plan closed.

---

## 7. Corrections to this report and to my briefings

Consolidated here rather than scattered, because a report that silently repairs itself is harder to
trust than one that shows its working. Every one of these was caught by someone other than me.

**Mine, corrected:**

- I recorded a planner's *proposed* risk mitigation as an accomplished fact. A validator grepped for
  the test and found nothing. The lesson is logged: an agent's report mixes what it DID with what it
  RECOMMENDS, and condensing both into past tense turns a proposal into a claim.
- I cited `overlay_reader.py:548` and `:651` in three briefings and in this report. Both were real
  line numbers from an earlier revision. The disjunction is at `:569`, the self-heal at `:725`.
- I told you `unusable` frames were not dumped. They always were. Two validators contradicted each
  other and a probe settled it against me.
- I claimed finding 3's fix would enable findings 2 and 4. The ring is a global instrument, not a
  per-caller report, and two pre-existing tests block the outcome-driven version outright.
- I reported the ruflo swarm as "15 agents". That is a configured default, not a count. The swarm had
  **zero** agents in it for an hour, because Agent-tool workers never register with it.
- I said the 0.5 Hz bubble flicker was a readability cost without knowing the bubble *pops* rather
  than fades, which is what makes it read as a fault.
- I wrote "zero successful captures in six days" into the rewritten version of this report, beside
  a timestamp making it under two. Caught by the project manager, not by an agent. The report now
  states the timestamp rather than an elapsed figure, which is harder to get wrong later.
- I told an implementer to model a handoff test on an existing injection helper. That helper wraps
  `asyncio.to_thread`, and the branch under test returns before `to_thread` is reached, so the seam
  had no window and the helper would never have fired. Worse, a real second capture would have been
  useless as a discriminator there, because both callers gate on the same scanner and produce the
  identical kind. It kept the principle, moved the seam, and documented why.

**Agents correcting me, kept because the corrections were better than my instructions:**

- `plan-capture` refused my instruction on `scanner.py:513-529` and was right: the truthy return
  correctly represents a station interior, and three tests deliberately pin it.
- It found the hole in my own safety constraint: the Root cross-check exists only in the space
  branch, so the case I most wanted covered was not.
- `plan-metadata` showed the description, not the prompt, is the only lever on skill selection, and
  caught my open-question numbering before I relayed the wrong two to you.
- `plan-findings` corrected two structural claims of mine and verified `contextvars` semantics with a
  real Python run rather than assuming.
- `doc-decision` reported a wrong conclusion, I challenged it, and it verified against the code and
  retracted. It later found a factual error in its own morning's text, corrected it in two files,
  and chose a *different* treatment for the third because that file has a different purpose.
- `impl-findings` found **two plan tests that would have shipped green against the bug**, by running
  the specified mutations and watching the suite stay green.

---

## 8. Method

Analysis, planning, and implementation were separate agents throughout, on your standing rule that
merging any two produces shortcuts. Validation is a fourth pass, because the producer of an artifact
is never its sole validator.

| Stage | Rule |
|---|---|
| Analyse | Read-only. Evidence with `file:line`. No recommendations |
| Plan | Written plan with mechanically checkable acceptance criteria. No code |
| Implement | Works from the plan, not the planner's reasoning |
| Validate | Holds the artifact and the requirements, never the implementer's account |

**Two practices earned their keep and should be kept.**

*A test that has never failed is not yet known to be a test.* Every new guard is proven by reverting
the fix and confirming the named test fails, then restoring and verifying the file hash. Validators
repeat this independently. It caught a real defect in wave 1 and two worthless tests in the findings
work.

*A snapshot before every wave.* Four now exist in the session scratchpad. With three of the reader
files untracked, they are stronger evidence than git, and every validator used one to establish the
changed-file list by diff rather than by trust.

---

## 9. Open items

**Yours to decide:**

- Whether to propagate and fly. Nothing changes until you do.
- Whether the suppressed bubble reads acceptably in flight. Mitigations are pre-written.
- Whether to update `graphify-out/`. Both analysts opened with graphify and both found its line
  numbers stale across the board, then re-derived from the files.

**Known imperfections, accepted with the reasons recorded. Do not "fix" these without asking:**

- `no_reader` shows `NO SIGNAL`, which is tied to typing `r_displayinfo 2`, an action that cannot
  help when the reader itself failed to load.
- `ACQUIRING...` is shown for all five reject reasons, including `implausible_body`, which is not
  transient and whose badge already says there is no action.
- After the A-1 test rewrite, nothing in the suite guards bubble stability.

**Carried forward, untouched:**

- The `pyro3` body-token plausibility question, where the project record contradicts itself.
- Non-`OOC_` surface routing.
- Step 7 of the capture plan, the retry policy, blocked on live data.
- `_capture_attempt`'s docstring still says `_reader_state` is "the only channel that reports a
  refusal". The ring now reads `_last_ring_state`. Flagged by the implementer, deliberately not
  changed because that function's source is text-sliced by neighbouring tests.

### Third round of orders: all three findings closed, 678 tests

The PM reviewed the findings work, confirmed all four original defects resolved and independently
measured the suite, then raised three more. All are now closed.

**The scanner-unavailable fast path now publishes its outcome.** It was the one production path
where the per-caller sink invariant did not hold, and it had been left alone in the previous round
as a hair-thin window. The PM's reason for closing it was better than my reason for leaving it: not
that a misreport is likely, but that an invariant holding everywhere except one path is harder to
reason about later than no invariant. Two tests, both mutation-proven, 676 to 678.

**The 21 zero-byte artifacts in the skill root are swept.** All confirmed zero bytes, untracked and
regular files before removal, deleted one at a time by literal name. Tracked git status byte-identical
before and after; untracked count down by exactly 21 with zero additions. Two agents enumerated the
list independently and agreed name for name.

One judgement call, flagged rather than buried: `4.9.0.22` is the current version string, so its name
is not obvious debris. It was deleted on the grounds that a zero-byte, untracked, extensionless bare
version number is not a plausible project artifact. Nothing suggested it ever held content.

**The elapsed-time error in this report is corrected.** See section 7.

The PM's own disposition matches this one: go for a focused diagnostic flight after the documented
release sequence, and no-go on any general readiness claim until live evidence shows a successful
capture.

**Status of the findings work: PASSED validation at 676 tests, then 678 after the third round.**

All seven mutations caught. Delta from 654 accounted exactly by collect-only counts. Every
constraint verified independently against the pre-work snapshot. The rewritten A-1 docstring was
judged the strongest artifact in the change, carrying all five required elements plus two beyond
what was asked.

The two checks most at risk came back clean for the right reason rather than by luck. The
poll-failure ring test discriminates because it drives a no-frame capture, the one case where
`_reader_state` and `_last_ring_state` genuinely disagree, so the `ring_status` fallback message
cannot mask a revert. The leak test names the vacuous post-`asyncio.run` form in its own docstring,
rejects it, and proves distinct sinks across two calls on one event loop.

**The three comment corrections are DONE**, plus a one-word fix to a fourth clause the work itself
had falsified. Still 676, all 48 test files hash-identical, and "no code changed" was proven two
ways rather than asserted: the token stream with comments and docstrings stripped is identical, and
the AST is identical once docstrings are removed.

The lock comment now names BOTH verdict fields rather than swapping one for the other, which is
better than the instruction it was given: both are genuinely protected by that lock, and it puts
the distinction risk R2 depends on directly onto the lock itself. `ring_status`'s parameter
description also now records that any truthy value suppresses the bubble, so the argument decides
what is DRAWN as well as what is SAID, which the old text gave no hint of.

One known remainder, deliberately left and recorded rather than missed: the second sentence of the
`_reader_state` declaration comment still says the ring is "the only way a refusal is ever visible
to the player". The tool result carries `capture_kind` and its own message too. Pre-existing
looseness, and the corrected comment sits directly beneath it.

**Two plan defects, separate from the work.** Five acceptance commands cannot produce their stated
output at any commit: several test files error at collection when invoked per-file rather than as
part of the whole suite, and this was reproduced against the untouched snapshot before being
attributed. And one predicted grep count was short by one, because the plan did not anticipate a
helper the design needed.
