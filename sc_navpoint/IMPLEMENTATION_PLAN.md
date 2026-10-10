# sc_navpoint: capture path repair, local OCR only

Planner: planning agent. Written 2026-08-02, revised the same day after a direction
change. Author of the code: a separate agent. Checker: a separate validation agent.

Baseline, measured directly: 536 tests pass (`python -m pytest tests -q` from
`skills/sc_navpoint`, 22.7 s). Version 4.9.0.22. Dev tree, `release_version/` and the
AppData live install are byte-identical for the runtime files.

## The operative decision

**No Vision AI at all. Local OCR is the only reader.** Stated three times by the user on
2026-08-02 in response to three separate questions. This supersedes the "BUILD THE ROUTER"
decision recorded at `TODO.md:26` and everything downstream of it. The skill's own records
(`TODO.md`, `Devlog.md`, `ledger/LEDGER.md`, `ledger/REFUTED.md`) still say the opposite
and must be updated as the work lands.

Do NOT delete the Vision code in `scanner.py`. Vision has now been decided on three times
in three days: removed 07-31, restored 08-02, removed again 08-02. Deleting that path is
the one irreversible step, and its deferral is the only reason two reversals have cost
nothing so far. Leave `_EXTRACTION_PROMPT`, the canaries, `capture_screen_b64`,
`build_extraction_messages`, `parse_completion` and `_parse_json_response` exactly as they
stand, uncalled.

## The consequence, stated plainly

The local reader has produced ZERO successful captures in the field since 2026-07-31
22:07:10. With no fallback, fixing the reader is not a side investigation, it is the
product. This plan does not attempt the fix, because the evidence to diagnose it does not
exist yet. It builds the evidence. Section 10 is the centre of this document.

---

## 1. Scope

IN SCOPE: diagnostic instrumentation sufficient to diagnose the reader from one live
session, a structured capture outcome, correct user-facing messages, getting the capture
off the event loop, poll log rotation, and making the retry policy measurable.

OUT OF SCOPE, stated so the implementer does not drift:

- **The OCR fix itself.** Not planned here. There is no evidence base for it yet and a
  guessed fix to a safety-critical reader is worse than no fix. Section 10 exists to
  produce the evidence; Section 9 is the decision that follows it.
- Any Vision AI code path, router, token budget or model call.
- The stale "via Vision AI" metadata strings. A separate planner owns those. See RISK R6.
- Non-`OOC_` surface routing, the body-token plausibility gate, and the `body_scale`
  guard. `pyro3` failing that gate is an open item awaiting the user.
- Any trust-threshold relaxation. `REFUSE_COST = 15.0` and `REFUSE_MARGIN = 8.0`
  (`overlay_reader.py:110-111`) are not to be touched by this plan, in either direction.
  No accepting rows with uncertain coordinate digits, no assuming a missing unit suffix
  means m or km, no changing `kind='zone'` to `kind='system'`.
- Any change outside `skills/`.
- Any keystroke or console command sent into Star Citizen. The player types everything.
- Any git commit, or any version bump. The user manages the release flow.
- Any in-game testing by an agent. Items that can only be settled in game are marked
  BLOCKED ON USER.

---

## 2. Order of work

Seven steps. Two dependencies drive the order: the deeper instrumentation and the message
work both need a structured outcome to hang off (Step 3), and the log will grow faster
once Step 1 lands, so rotation comes immediately after it.

| Step | Name | Depends on | User-visible |
|------|------|-----------|--------------|
| 1 | Diagnostic instrumentation, tier 1 | nothing | no |
| 2 | Poll log rotation | 1 | no |
| 3 | `CaptureOutcome`, and the capture lock | nothing | no |
| 4 | Diagnostic instrumentation, tier 2 | 3 | no |
| 5 | Correct user-facing messages | 3 | yes |
| 6 | Capture off the event loop | 3 | no |
| 7 | Retry policy decision | 1, and live data | maybe |

Step 1 goes first because every item in it is free (the data already exists and is being
discarded) and because the user is the bottleneck: every diagnostic data point costs a
live session, so the sooner the instrumentation ships the sooner a session is worth
flying.

Step 4 is ahead of Step 5 deliberately, even though Step 5 is the more visible fix. Fixing
the reader is the product now. A day without the per-cell data is a day of flying that
produces less evidence than it could, and Step 5 unblocks nothing.

Steps 1, 2, 3 and 6 change no behaviour the player can see. Step 5 is the only step in
this plan that changes what the assistant says.

---

## 3. Step 1: diagnostic instrumentation, tier 1

Everything in this step is data that is ALREADY COMPUTED and then thrown away, plus one
new line per activation. No new measurements, no new pixels touched, nothing that can
change a capture outcome.

Full specification in Section 10, items I1, I2, I4 and I7. In outline:

- **I1, the build identity line.** One line at `prepare()`: version, the mtime and size of
  `main.py`, `overlay_reader.py` and `overlay_glyphs.npz`, the display index, the poll
  interval, the monitor geometry and the computed block region. Without this the log
  cannot tell "the skill did not run" from "the skill ran and said nothing", which is
  exactly the ambiguity that makes the 2026-08-01 13:28 gap unresolvable today.
- **I2, promote the row fields that already exist.** `OverlayReader._decode_block`
  (`overlay_reader.py:689-694`) puts `cost`, `margin`, `refused`, `colour`, `offset` and
  `y` into every row dict. `main._trace_rows` (`:849-869`) prints only `row`, `kind`,
  `trusted` and `text`. Print the rest.
- **I4, alignment provenance.** `OverlayReader.read` (`:642-655`) computes `from_cache` and
  whether the self-heal refit fired, then discards both, and returns `y0` which
  `main.py:336` discards with `_, _, rows =`. Record all three.
- **I7, durations.** No line in the log carries a duration. Add elapsed milliseconds per
  attempt and per capture.
- Plus the per-attempt trace line, so the retry policy becomes measurable at all.

### The retry measurement, and why it matters more now

`MARK_CAPTURE_ATTEMPTS = 5` (`main.py:59`) and `CAPTURE_RETRY_DELAY_S = 0.06` (`:66`)
produce five attempts. Today attempts 1 through m-1 write nothing, because
`final = attempt == attempts` at `main.py:300` guards all three trace sites, and a success
on attempt 1 also writes nothing. Zero "read on attempt" lines exist in the whole log,
which is equally consistent with "no late attempt ever succeeded" and "no capture ever
needed a second look". Retry is one of the few levers left on a local-only reader, so this
ambiguity now costs more than it did.

Add one compact line per attempt, at every attempt:

```
attempt 2/5 outcome=gate gate='no_system_line: no readable SolarSystem line' ms=2180
attempt 1/1 outcome=ok ms=910
attempt 3/5 outcome=reject reason='unreadable_units' ms=2240
```

`outcome=` uses the Step 3 `KIND_*` vocabulary. If Step 1 ships before Step 3, use the same
literal strings so Step 3 changes no emitted text.

Do NOT add a row dump per attempt. `_trace_rows` stays guarded by `final`: it is 8 lines of
up to 88 characters and the volume matters at `poll_interval: 1`.

### What must NOT change

- `MARK_CAPTURE_ATTEMPTS` and `CAPTURE_RETRY_DELAY_S` keep their values. This step measures
  the policy; Step 7 decides it.
- The existing `REFUSED:` line keeps its exact current wording, including the parenthesised
  `reason=` clause. Months of logs are grepped for both. Add fields to the end of the
  bracketed block; do not reorder or reword what is there.
- `_poll_trace`'s swallow-everything contract (`main.py:800-806`). A logging failure must
  never change a capture outcome.

### Acceptance criteria

1. `python -m pytest tests -q`: at least 536 passed, 0 failed. No existing test file is
   edited in this step.
2. A new test drives `_capture_position_local(5)` against a stub screen that refuses all
   five frames, and asserts the trace file contains exactly five lines matching
   `capture attempt \d/5 outcome=`, numbered 1 to 5 in order, each carrying `ms=`.
3. A new test drives a stub that refuses attempts 1 and 2 and succeeds on 3, and asserts
   the trace contains `attempt 3/5 outcome=ok` and does NOT contain `attempt 4/5`.
4. A new test asserts a single-attempt refusal writes exactly one `attempt 1/1` line AND
   still writes the pre-existing `REFUSED:` line unchanged in its leading text.
5. A new test asserts the row dump lines now carry `cost=`, `margin=`, `refused=` and
   `colour=` for every row, with the pre-existing `row=`, `kind=`, `trusted=` and `text=`
   fields still present and still in that order.
6. A new test asserts `prepare()` writes exactly one build identity line containing the
   version string, all three file names, and the block region.
7. `_trace_rows` is still called only inside an `if final:` suite.
8. `MARK_CAPTURE_ATTEMPTS == 5` and `CAPTURE_RETRY_DELAY_S == 0.06`.

---

## 4. Step 2: poll log rotation

No longer optional. The poll log is now the only instrument this project has, Step 1 adds
lines to it, and at `poll_interval: 1` a session writes one line per second per successful
capture plus up to nine per refusal.

`_poll_trace` (`main.py:784-813`) appends with no rotation and no size cap.

**Rotate, do not truncate.** A cap that truncates or overwrites would destroy the very
evidence this plan exists to collect. Before appending, if the live file exceeds 8 MB,
rename it to `navpoint_poll.log.1`, replacing any existing `.1`, and start a fresh live
file. Keep exactly one generation behind the live one: two files, 16 MB worst case. Put the
whole thing inside the existing `try/except Exception: pass`.

Say so in the handover to the user: when they send a log after a session, they must send
BOTH files if a `.1` exists.

### Acceptance criteria

1. `python -m pytest tests -q`: at least 536 passed, 0 failed.
2. A new test writes a file just over the threshold in `tmp_path`, calls the rotation
   helper, and asserts the live file is small, `navpoint_poll.log.1` exists, and its
   content is the old content verbatim. Test the helper directly; do not write 8 MB through
   real trace calls.
3. A new test asserts a second rotation replaces `.1` and does not create `.2`.
4. A new test asserts a rotation failure (patch `os.replace` to raise) does not raise out of
   `_poll_trace` and does not prevent the append.

---

## 5. Step 3: `CaptureOutcome`, and the capture lock

### The problem

There are more than a dozen distinct failure producers and one channel to report them: a
`None` return. `self._scanner.last_reject_reason` is a second channel and it is unreliable
in two verified ways, both load-bearing here.

- `scanner.py:606-619`: when `coords is None` and `pos_raw is None`, `parse_payload` returns
  `None` with `last_reject_reason` still `None` (cleared at `:492`, never set on this
  branch). A consumer switching on the reason gets `None` and cannot tell this from "no
  capture attempted".
- `scanner.py:521-529`: in the space branch, `parse_payload` returns a TRUTHY dict when
  `system` is `None`, in BOTH sub-cases. When `system_pos_raw` is absent the reason stays
  `None`; when `system_pos_raw` was present but unreadable it sets
  `last_reject_reason = "unreadable_units"` AND STILL RETURNS THE TRUTHY DICT. So the
  reason can be non-`None` after a successful-looking return. Any code that reads the reason
  without first checking whether a payload came back will misclassify.

Ring state cannot carry this either. `ring_state` is called at `main.py:341` BEFORE
`parse_payload` at `main.py:371`, and `overlay_fields.py:495` returns `RING_OK` whenever a
payload exists, so all six scanner validation refusals leave the ring at `RING_OK`.
Separately, `main.py:260-266` returns without writing `_reader_state` at all, so a stale
value from the previous capture survives.

### The object

In `skills/sc_navpoint/overlay_fields.py`, not a new module: that file already owns the
refusal vocabulary (the `GATE_*` ids at `:211-221`, the `RING_*` strings at `:462-473`), is
already imported by `main.py`, and is already registered in both release manifests.

```python
@dataclass(frozen=True)
class CaptureOutcome:
    kind: str                    # one of KIND_*, below
    position: dict | None        # the validated position data, or None
    overlay_present: bool | None # None when the question was never asked
    frame_usable: bool | None    # None when the question was never asked
    ring_state: str              # one of overlay_fields.RING_*
    gate: str                    # a GATE_* id with its clause, or ""
    reject_reason: str           # a scanner last_reject_reason value, or ""
    attempts: int                # grab-and-decode attempts made
    metrics: dict                # the diagnostic block, see Section 10
    detail: str                  # free text for the trace, never shown to the player
```

**I dropped the `source` field.** It existed only to distinguish a local read from a Vision
read. With one reader it would be a constant, and a constant field invites a future reader
to think there is a second producer. `metrics` replaces it as the useful carrier: it is the
vehicle Section 10 items I3, I4, I5 and I7 travel in, and it is the reason the deeper
instrumentation depends on this step.

`kind` vocabulary, as module constants beside the `GATE_*` ids, for the same "treat them as
an interface" reason:

| Constant | Value | Producer |
|---|---|---|
| `KIND_OK` | `"ok"` | a validated position |
| `KIND_NO_READER` | `"no_reader"` | `main.py:260`, reader or scanner unavailable |
| `KIND_NO_GRAB` | `"no_grab"` | `main.py:318`, screen grab raised |
| `KIND_UNUSABLE` | `"unusable"` | `main.py:329`, `capture_is_usable` false |
| `KIND_ABSENT` | `"absent"` | `main.py:330`, `overlay_is_present` false |
| `KIND_DECODE_ERROR` | `"decode_error"` | `main.py:338`, decode raised |
| `KIND_GATE` | `"gate"` | any of the five `overlay_fields` gates, named in `gate` |
| `KIND_REJECT` | `"reject"` | any `parse_payload` refusal with a reason, named in `reject_reason` |
| `KIND_UNEXPLAINED` | `"unexplained"` | `parse_payload` returned None with no reason (`scanner.py:617-619`) |
| `KIND_NO_FRAME` | `"no_frame"` | a truthy payload carrying neither `body` nor `system_frame` |

Ten kinds covering every producer: the five gate ids live in `gate` and the six scanner
reasons in `reject_reason`, so the full set stays distinguishable. The two producers that
appeared on nobody's list get their own kinds, `KIND_UNEXPLAINED` and `KIND_NO_FRAME`.

### Contract changes, and every caller

The part most likely to go wrong, so it is spelled out call site by call site.

**Do NOT change the return type of `_capture_position_local` or `_capture_position`.**
Twenty existing tests in `tests/test_capture_retry.py` and `tests/test_capture_trace.py`
call `_capture_position_local(...)` and assert `is None` or `== position`. Those tests are
correct and must keep passing. The structured outcome travels alongside, not instead.

| Function | Current | New |
|---|---|---|
| `main._capture_attempt(reader, attempt, attempts)` | returns `dict \| None` | returns `CaptureOutcome`; the only call site is `_capture_position_local:268` |
| `main._capture_position_local(attempts=1)` | returns `dict \| None` | UNCHANGED return, additionally sets `self._last_outcome` |
| `main._capture_position(attempts=1)` | returns `dict \| None` | UNCHANGED return, additionally sets `self._last_outcome` |
| `overlay_fields.payload_from_rows(rows)` | returns `dict \| None` | UNCHANGED |
| `overlay_fields._payload_and_reason(rows)` | returns `(dict \| None, str)` | UNCHANGED, already correct |
| `scanner.parse_payload(data)` | returns `dict \| None` | UNCHANGED. No `require_root` parameter: that existed only for Vision payloads. Leave the local path's Root behaviour exactly as it is. |

`main.py:337` calls the lossy `payload_from_rows`, then `main.py:359` re-runs the whole gate
walk through `_refusal_gate` to recover the name it discarded. Replace the `:337` call with
`overlay_fields._payload_and_reason(rows)` so the reason arrives with the payload, wrapped
in the same try/except `_refusal_gate` already has, so a gate walk that raises still cannot
change the capture outcome. `tests/test_capture_trace.py:385` proves that property today and
must keep proving it.

Do NOT delete `payload_from_rows` or `refusal_reason`. Both are covered by
`tests/test_capture_trace.py:277-330` and `tests/test_overlay_reader.py`, and
`overlay_fields.read_payload` (`:517-533`) uses `payload_from_rows`. `read_payload` has no
caller in `main.py` and this plan does not give it one.

### The capture lock

`_capture_position_local` mutates `self._reader_state`, lazily builds `self._reader`
(`main.py:213-232`), and drives a single shared `OverlayReader` whose alignment cache
(`self._fit_cache`, `self._fit_uses`, `overlay_reader.py:630-654`) is mutable state refitted
on demand. The poll loop already runs on its own thread with its own event loop
(`main.py:880-920`), so a background poll and a foreground `mark_location` can already call
this concurrently today. Step 6 makes that interleaving more likely, not less.

Add `self._capture_lock = threading.Lock()` and hold it for the whole of
`_capture_position_local`. Read it with `getattr(self, "_capture_lock", None)` and fall back
to a module-level lock when absent, because the tests build the skill with `__new__` and
never run `__init__` (see the `tests/test_main_capture.py` docstring). **Every new instance
attribute in this plan must be read through `getattr` with a default for the same reason.**
This is the single most likely way to break the existing suite.

### Acceptance criteria

1. `python -m pytest tests -q`: at least 536 passed, 0 failed. No existing test file is
   edited in this step.
2. `overlay_fields.CaptureOutcome` exists, is a frozen dataclass, and has exactly the ten
   fields named above. It has NO `source` field.
3. All ten `KIND_*` constants exist with exactly the tabulated string values, and there is
   no constant whose name contains `VISION`.
4. A new test drives all six precondition and gate kinds through the real
   `_capture_position_local` with a stubbed screen, following the pattern already used at
   `tests/test_capture_trace.py:126-243`, and asserts the resulting `_last_outcome.kind`.
5. A new test asserts `KIND_UNEXPLAINED`: a local-frame payload with a valid `body_token`,
   no `pos_raw` key and no x/y/z returns `None` with `last_reject_reason is None`, and the
   outcome kind is `unexplained`, not `reject`.
6. A new test asserts `KIND_NO_FRAME`: `parse_payload({"local_frame": False})` returns
   truthy, and the outcome kind is `no_frame` with `position` set to that dict.
7. A new test asserts the false-positive case: a space payload whose `system_pos_raw` has an
   unsuffixed component returns TRUTHY and sets `last_reject_reason == "unreadable_units"`,
   and the outcome kind is `no_frame`, NOT `reject`. This is the regression guard for the
   second unreliability above.
8. `inspect.signature(NavPointScanner.parse_payload)` is unchanged from the baseline.
9. `grep -n "self\._capture_lock" main.py` shows the lock acquired in exactly one function,
   and the `with` block contains no `await`.
10. A new test calls `_capture_position_local` from two threads concurrently against a stub
    reader that records overlapping entry, and asserts no overlap was observed.
11. `grep -n "_capture_position(" main.py` returns the same five call sites as the baseline:
    `:405` internal, `:970` poll, `:1190` mark, `:1345` navigate, `:1499` update.

---

## 6. Step 4: diagnostic instrumentation, tier 2

The items that need the outcome object or a new measurement. Full specification in Section
10, items I3, I5 and I6:

- **I3, per-cell refusal detail.** Which of the two refusal conditions tripped on each
  refused cell, its cost and margin, and the top two candidate glyphs. This is the single
  piece of evidence that decides the OCR fix, and nothing in the code records it today.
- **I5, a success baseline.** Fold `ink`, `periodicity`, the trusted-row count and the mean
  cost into the existing successful-capture line, so a baseline accumulates from ordinary
  play without a single extra line in the log.
- **I6, refused frame dump.** An opt-in, capped, local PNG of the refused 667x175 crop, so
  the OCR work has an offline corpus and does not need the user to fly for every iteration.

### Acceptance criteria

Listed with each item in Section 10. Summarised: 536 still pass; a new test asserts each new
field is present in the trace for a refusal; a new test asserts the success line carries the
baseline fields; a new test asserts the frame dump is off by default, capped when on, and
that a dump failure cannot change a capture outcome.

---

## 7. Step 5: correct user-facing messages

### The problem, verified

Three sites collapse every cause into two messages, and one tool says nothing at all.

- `main.py:1191-1199`, `mark_location` on a falsy capture: "Could not extract position from
  screen" plus the `r_displayinfo 2` hint.
- `main.py:1208-1221`, `mark_location` on a truthy payload with no usable frame: a different
  error, then a byte-identical hint block.
- `main.py:1500-1503`, `update_position`: a flat string, no hint.
- `navigate_to` never emits the instruction at all, and is worse than a wrong message. Both
  refusal gates (`:1353`, `:1374`) key on a truthy `pos_frame`, and `_capture_frame`
  (`:503-515`) returns `None` when the capture proved nothing. So on a total capture failure
  `navigate_to` walks past both gates and past the frame-id gate at `:1389`, sets
  `self._active_target` at `:1403`, reaches `:1442-1454`, returns "Bearing tracking begins
  once a local frame on {body} is available", and starts the poll thread. A failed capture
  is reported as a normal deferred state.

Amplifier: `default_config.yaml:130` tells the model to give the console command whenever "a
NavPoint tool reports the overlay is missing", and `:131` orders any `hint` field relayed
verbatim. A wrong hint is not a nuance, it is a script the model reads out.

### Every refusal is now terminal

There is no fallback. A refused capture is the end of that capture, so the text must tell
the player what THEY can do about it, in the game, with their own hands. Three rules:

1. **Say what happened, in one clause, without instrument-fault language.** A refusal is the
   reader correctly declining. "Malfunctioning" sends the player hunting a fault that does
   not exist. This is the same reasoning already recorded for the ring strings at
   `overlay_fields.py:457-461`.
2. **Give exactly one action the player can take, or say plainly that there is none.** "Look
   at darker ground" is an action. "Try again" alone is not, and on a repeatable refusal it
   is a lie.
3. **Say that nothing was saved.** Every one of these paths stores nothing, and the player
   should never have to infer that.

`r_displayinfo 2` is emitted for exactly ONE kind: `KIND_ABSENT`. Nowhere else. The skill
never types it; the player does.

Add one helper `_capture_error(outcome) -> dict` in `main.py`, called from all three tools,
so there is one table and not three copies.

| Kind | What happened | The player's action |
|---|---|---|
| `no_reader` | The overlay reader could not be loaded, so no position can be read. Nothing was saved. | None in game. This is an installation problem. |
| `no_grab` | The screen could not be captured on display N. Nothing was saved. | Check the NavPoint display setting if you have more than one monitor. |
| `unusable` | The overlay was too washed out on this frame to read safely. Nothing was saved. | Look at darker ground or away from the sun, then ask again. |
| `absent` | The position overlay is not on screen. Nothing was saved. | THE `r_displayinfo 2` BLOCK, verbatim as it stands today, as a `hint`. |
| `decode_error` | The overlay reader failed on this frame. Nothing was saved. | Ask again. If it repeats, the log has the detail. |
| `gate` | The overlay was on screen and read, but the position could not be confirmed safely, plus the specific gate's plain clause. Nothing was saved. | Depends on the gate; see below. |
| `reject` | The overlay was read but the position failed a safety check, so it was discarded rather than risk a waypoint in the wrong place, plus the specific reason's plain clause. Nothing was saved. | Hold still with a clear view of the overlay and ask again. |
| `unexplained` | The overlay was read but carried no usable coordinates. Nothing was saved. | None. This is not a place a waypoint can be marked. |
| `no_frame` | No usable coordinate frame here: neither a planet or moon local frame nor a readable open-space position. A space station or asteroid base interior looks like this. Nothing was saved. | None. Move outside the station. |

Per-gate actions, since the five gates mean genuinely different things:

- `no_system_line` and `refused_above`: the overlay is there and parts of it did not read.
  Action: reduce what is behind the overlay block. Point away from bright or busy scenery,
  or hold still, then ask again.
- `body_scale`: you are on a body surface and the skill will not store a system-frame point
  there. Action: none, this is a refusal by design.
- `no_coordinate`: a zone line read with no readable coordinate. Same action as
  `no_system_line`.
- `no_root`: the cross-check line did not read. Same action as `no_system_line`.

Reuse the existing wording where it exists: the `GATE_*` ids each carry a human clause after
the colon (`overlay_fields.py:217-221`), and three of the five chat badges already phrase
their scanner reason correctly for a player. The other two do not. See the next subsection.

### The five chat badges at `main.py:408-447`

These are a SECOND user-facing channel, separate from the tool results above. The tool
result goes to the model, which paraphrases it. A badge goes straight to the chat log as
written. Both are in scope for this step.

The block sits inside `if not pos_data:` in `_capture_position` (`:406`), so it reads
`last_reject_reason` only on a falsy return. That is the safe direction and the
stale-reason hazard from Section 5 does not apply here. Do not move this block.

| Line | Reason | Verdict |
|---|---|---|
| `:410-415` | `example_echo` | **WRONG.** Says "Vision AI echoed the calibration example". Reachable from the local reader. Rewrite. |
| `:418-423` | `implausible_body` | **WRONG.** Says "Vision AI overlay read was rejected as implausible". Rewrite. |
| `:426-431` | `unreadable_units` | Correct. Names no reader. Leave verbatim. |
| `:434-439` | `frame_mismatch` | Correct. Names no reader. Leave verbatim. |
| `:442-447` | `coord_mismatch` | Correct. Names no reader. Leave verbatim. |

The two wrong ones tell the player that a model failed when no model was involved. They are
not dead code: `example_echo` is set by `parse_payload` at `scanner.py:499-504` and
`implausible_body` at `:573-578`, and `parse_payload` is on the local reader's path, so
either can fire during ordinary OCR-only operation.

Rewrite both to name the overlay and the check, never a reader. Apply the same three rules
as the tool results: say what happened, give one action or say plainly there is none, say
nothing was saved. The `implausible_body` badge should also drop "Retry with a clear view",
because a body token that fails the plausibility gate is not fixed by looking harder; that
gate is the `pyro3` open item and retrying will produce the same refusal.

**The guards themselves must not be weakened, relaxed or removed.** Only the strings change.
`_is_example_echo` (`scanner.py:365-399`) and the plausibility gate (`:570-579`) stay exactly
as they are, and `tests/test_scanner_echo.py` and `tests/test_plausibility.py` must pass
unchanged.

**Recorded as unexplained, not buried:** the canaries exist to catch a language model
echoing the prompt's worked example, and they are contrived values
(`ExampleSys_0x_ExampleBody`, `99999999.9999km`, `111111.111111m`). A deterministic reader
tripping them would mean something is producing example-shaped values from real pixels,
which nothing in the record explains. No local capture has been observed tripping it. Do
NOT investigate this now. It is written down so that if the reworded badge ever appears in
the field, whoever sees it knows it is a finding and not a cosmetic message.

### The `navigate_to` fix

Insert a gate immediately after the capture at `main.py:1345-1347`, before the
frame-comparison gates:

```
if outcome.kind != KIND_OK:
    return json.dumps(self._capture_error(outcome) | {"target_not_set": True})
```

`navigate_to` must not set `self._active_target`, must not call `_start_nav_polling`, and
must not open the HUD when the capture failed. `KIND_NO_FRAME` is included in this refusal:
a station-interior capture cannot begin tracking either.

The two existing frame-comparison gates at `:1353` and `:1374` stay exactly as they are.
They handle a SUCCESSFUL capture whose frame differs from the target's, which is a different
and correctly-handled case.

### The config reword

- `default_config.yaml:130`: narrow "a NavPoint tool reports the overlay is missing" to "a
  NavPoint tool returns a hint naming `r_displayinfo`". This ties the model's behaviour to
  the hint field rather than to its own reading of an error string. The clause that the
  skill has no tool to enable the overlay and must never claim it can stays verbatim.
- `:131`: unchanged. Relaying a hint verbatim is correct once hints are correct.
- The "If marking was refused" paragraph tells the model a refusal "means neither a surface
  local frame nor a readable open-space position was present", which is now one of nine
  cases. Reword to: relay the tool's error as given, and never add a console command unless
  the tool supplied a hint.

Update the dev tree copy only. The installer lists `default_config.yaml` under
`preserve_on_update`, so the live copy is not overwritten by a skill update; propagating it
is the user's release step and must be called out in the handover.

### What must NOT change

- The `r_displayinfo 2` hint TEXT where it is still used. Asserted by
  `tests/test_main_strings.py:28` and `tests/test_main_capture.py:430`.
- `_capture_frame` (`:503-515`) and its `None`-means-nothing-proved contract. It is correct;
  the callers that ignored `None` were not.
- `scanner.parse_payload`'s truthy return in the space branch (`:513-529`). Changing it to
  `None` would break three existing tests that assert the current contract deliberately:
  `tests/test_space_waypoints.py:97-104`, `:107-114`, and `tests/test_scanner.py:107-127`.
  The truthy dict correctly represents "the overlay read fine and there is genuinely no
  frame here". The bug was never the return value, it was the message and `navigate_to`'s
  missing gate.

### Acceptance criteria

1. `python -m pytest tests -q`: 536 pass. ONE existing assertion changes, and only one:
   `tests/test_main_capture.py:430`. See DECISION D1 in Section 14, which carries the
   before and after text and the reason. Every other test must pass UNCHANGED.
2. `grep -c "r_displayinfo 2" main.py` returns exactly 2, down from 4 at baseline. The two
   survivors are the module docstring at `main.py:6`, which is documentation and must not
   be touched, and the single `KIND_ABSENT` hint block. The two that go are the duplicate
   hint at `:1218` and the `update_position` string at `:1502`, both replaced by the shared
   helper. Note separately that `grep -c "r_displayinfo" main.py` (without the level) starts
   at 6, because `:420` and `:1171` mention the overlay by name without giving a command;
   `:1171` is the tool description and stays, and `:420` is one of the two badges being
   rewritten.
3. A new test drives each of the nine failure kinds through `mark_location` and asserts
   `hint` is present if and only if the kind is `absent`.
4. A new test asserts the string `r_displayinfo` appears in a `mark_location` result only for
   `KIND_ABSENT`.
5. A new test asserts every failure message contains a phrase stating nothing was saved.
6. A new test asserts every failure message for the five gate ids names a distinct player
   action, and that `body_scale`, `unexplained` and `no_frame` explicitly say there is no
   action rather than saying "try again".
7. A new test: `navigate_to` on each of the nine failure kinds returns an error, leaves
   `skill._active_target is None`, and never calls `_start_nav_polling` (patch it with a
   recorder).
8. A new test: `navigate_to` with `KIND_NO_FRAME` refuses and sets no target. This is the
   exact silent-accept path.
9. A new test: `navigate_to` with a SUCCESSFUL local capture on the target's body still sets
   the target, still starts polling, and still opens the HUD once. The existing tests at
   `tests/test_main_capture.py:643-672` cover this and must pass unchanged.
10. A new test: `update_position` returns the same per-kind error the other two tools return.
    Assert the error strings are identical for the same kind across all three.
11. `grep -n "the overlay is missing" default_config.yaml` returns nothing.
12. `grep -ci "vision" main.py` returns 0 for the two badge blocks at `:408-423`. Mechanical
    form: no line between the `example_echo` branch and the end of the `implausible_body`
    branch contains the string `Vision`.
13. The three correct badges are byte-identical to baseline. Mechanical form: a test asserts
    the exact current strings for `unreadable_units`, `frame_mismatch` and `coord_mismatch`
    still appear in `main.py`.
14. `tests/test_scanner_echo.py` and `tests/test_plausibility.py` pass unchanged, proving no
    guard was weakened while its message was rewritten.
15. A new test asserts each of the five badges fires at most once per activation and that the
    one-shot guards at `main.py:107-122` are untouched.
16. BLOCKED ON USER: with `r_displayinfo 0`, say "mark this location" and confirm the
    assistant tells you to type `r_displayinfo 2`. Then with `r_displayinfo 2` up inside a
    station, say "mark this location" and confirm the assistant does NOT tell you to type a
    console command. Then say "navigate to <any waypoint>" with `r_displayinfo 0` and confirm
    no tracking starts and no HUD opens.

---

## 8. Step 6: capture off the event loop

### The problem, verified

`main.py:382 async def _capture_position` calls `self._capture_position_local(attempts)`
directly at `:405` with no offload. Everything under it blocks: the in-function imports at
`:305-307`, `mss()` at `:309`, `sct.grab` at `:314`, the PIL and numpy conversion at
`:315-317`, `capture_is_usable` at `:329`, `overlay_is_present` at `:330`, the OCR at `:336`,
the field parse at `:337`, the ink and periodicity measurements at `:364-365`,
`parse_payload` at `:371`, `time.sleep(CAPTURE_RETRY_DELAY_S)` at `:276`, and a synchronous
file append per trace line at `:803-804` including one per decoded row via `:866`. There is
no `to_thread` and no executor anywhere in the skill. The two 2026-08-02 refusals took
roughly 11 seconds each, all of it on the caller's loop.

### The fix, and the constraint it must respect

`main.py:880-920` records the finding that a task created inside a tool call belongs to that
call's loop, that Wingman does not keep that loop alive, and that `asyncio.create_task`
inside a tool is therefore silently abandoned at its first await.

`asyncio.to_thread` does not violate that finding. It schedules work on the default executor
and the coroutine AWAITS the result, so the caller's loop is alive for the whole duration by
construction. Nothing outlives the call, so nothing can be abandoned.

```python
pos_data = await asyncio.to_thread(self._capture_position_local, attempts)
```

Do NOT use `create_task`, do NOT use a fire-and-forget thread, and do NOT touch
`_start_nav_polling`. The polling thread stays exactly as it is; inside its own loop,
`to_thread` behaves the same way. Python 3.13 is the runtime (the live install carries
`main.cpython-313.pyc`), so `to_thread` is available with no fallback.

### What must NOT change

- The `async def` signature of `_capture_position` and its `dict | None` return.
- `_capture_position_local` stays fully synchronous. It is the unit the lock and the thread
  wrap.
- `time.sleep(CAPTURE_RETRY_DELAY_S)` at `:276` stays a blocking sleep. It now sleeps on a
  worker thread, which is where a blocking sleep belongs. Converting it to `asyncio.sleep`
  would force `_capture_position_local` async and break the 20 tests that call it
  synchronously.

### Acceptance criteria

1. `python -m pytest tests -q`: at least 536 pass, 0 fail.
2. `grep -n "to_thread" main.py` shows it wrapping `_capture_position_local`.
   `grep -n "create_task" main.py` shows only the pre-existing legacy `_nav_task` handling at
   `:934-938`.
3. A new test asserts the loop stays responsive: run `_capture_position` against a stub whose
   `_capture_position_local` sleeps 0.3 s, concurrently with an `asyncio.sleep(0.05)` ticker,
   and assert the ticker completed at least 3 ticks before the capture returned. Under the
   current code it completes 0.
4. A new test asserts `inspect.iscoroutinefunction(_capture_position_local)` is False and
   `inspect.iscoroutinefunction(_capture_position)` is True.
5. `tests/test_poll_thread.py` passes unchanged.

---

## 9. Step 7: the retry policy decision (BLOCKED ON DATA)

Do not change `MARK_CAPTURE_ATTEMPTS` or `CAPTURE_RETRY_DELAY_S` in this plan. After Step 1
has collected one ordinary session, the log answers whether any attempt after the first ever
succeeds, and whether the gate differs between attempts within one capture. See OPEN
QUESTION 3.

Worth recording now: the five attempts are NOT fully independent, and the direction of that
is the opposite of how it is usually framed. The `OverlayReader` instance is reused across
attempts and holds a cached alignment origin (`overlay_reader.py:630-654`) which is
invalidated and refitted when nothing decodes as trusted. In the observed failures nothing IS
trusted, so every read pays the self-heal refit and re-decode. So attempt 2 can differ from
attempt 1 by more than 60 ms of frame timing, which is an argument FOR retries. It is also a
candidate explanation for the per-attempt cost, which Step 1's `ms=` field will settle.

---

## 10. INSTRUMENTATION: what the next live session must produce

**This is the centre of the plan.** The reader has produced no successful field capture since
2026-07-31 22:07:10. Diagnosing it needs evidence that does not exist. This section specifies
exactly what to log, where in the pipeline, in what format, and what question each field
answers. It does NOT propose a fix.

### What the log actually contains, read directly

I read `%APPDATA%\ShipBit\WingmanAI\generated_files\SC_NavPoint\navpoint_poll.log`, 495
lines. Findings that shape everything below.

**The whole failure record is six lines.** Two on 2026-08-01 (14:05:57, 21:58:02), two on
2026-08-02 (00:10:12, 00:10:49), plus the sixteen row-dump lines belonging to the 08-02 pair.
Nothing at all between 2026-07-31 22:07:21 and 2026-08-01 14:05:57.

**The two 08-01 lines are the OLD TRACE FORMAT.** They carry no gate name and no `attempts=`
field. Both are written unconditionally by the current code (`main.py:359` and `:366`). So
the 08-01 build had neither the gate instrumentation nor the retry loop. **The "two distinct
failure shapes" in the brief I was given is a BUILD difference, not a game difference.** The
duration difference follows the same arithmetic: one attempt against five. I cannot prove the
underlying frames were alike, but nothing in the evidence requires a second failure mode, and
treating it as two would send the OCR work chasing a phantom.

One caveat I will not smooth over: 11.1 s over five attempts is about 2.2 s per attempt,
against about 1.1 s for the single-attempt build. That doubling is unexplained and is exactly
what item I7 measures.

**The failure is legible in the row dump, and it is not alignment.** From 00:10:12:

```
row[2] kind='zone' trusted=False text='Zone: SolarSystem_729968885548 Pos: -3663644.4772km -43199322.??3?km 818086.6176k?'
row[3] kind='zone' trusted=False text='Zone: Root Pos: -3663644.4772km -43199322.4?37k? 818086.?176km'
```

The labels, the zone id and most digits decode perfectly, so the alignment fit is right and
the block region is right. The gate fired `no_system_line` because `_payload_and_reason` only
considers rows where `row["trusted"]` is True (`overlay_fields.py:298`), and `trusted` is
`refused == 0` (`overlay_reader.py:691`): ONE refused cell anywhere in the row discards the
whole row. Three or four scattered cells, inside the coordinate fields and the unit suffixes,
are costing the entire capture.

That fail-closed rule is correct and is not up for negotiation in this plan. The question it
raises is why those individual cells refuse, and that is precisely what nothing records.

**The refusal condition is a disjunction, and the log cannot tell which side fired.**
`overlay_reader.py:548`: a cell is refused when `cost > REFUSE_COST (15.0)` OR
`margin < REFUSE_MARGIN (8.0)`. Those mean opposite things. High cost means nothing in the
glyph bank matches, which points at a render change, a missing template, or a scale or colour
the bank was not built for. Low margin means two glyphs matched almost equally, which points
at genuine ambiguity between similar characters at this size. The fix for one is not the fix
for the other, and the log records neither.

**The data for half of this is already computed and thrown away.**
`OverlayReader._decode_block` (`:689-694`) puts `cost` (mean), `margin` (median), `refused`
(count), `colour`, `offset` and `y` into every row dict. `main._trace_rows` (`:849-869`)
prints only `row`, `kind`, `trusted` and `text`. Six fields per row are discarded at the
point of writing them to a file.

**There is no successful-capture baseline** because `ink` and `periodicity` are computed only
inside the `if payload is None` branch (`main.py:364-365`). All four measurements in the log
history are on refusals. Without a baseline, `ink=0.0525` is a number with nothing to compare
against.

**The log cannot distinguish "the skill did not run" from "the skill ran and said nothing".**
The three 2026-08-01 13:28 failures that left no line are unresolvable today, and the next
such gap will be too unless the log opens with a build identity line.

### The instrumentation

Seven items. Channel discipline throughout: file writes via `_poll_trace` and chat badges via
`self.printr.print`. The skill's python `logger` reaches no file anyone can read (recorded at
`main.py:787-792`), so `logger.warning` is not a channel, and every `logger.warning` in
`scanner.py` naming a rejection reason (`:500`, `:524`, `:544`, `:573`, `:595`, `:611`)
currently reaches nobody.

---

**I1. Build identity line.** Step 1. Written once per `prepare()`, before anything else.

```
BUILD version=4.9.0.22 sc=4.9.0 main.py=74827b@2026-08-01T23:12 overlay_reader.py=33159b@2026-08-01T23:32 overlay_glyphs.npz=93112b@2026-07-31T23:44 display=1 poll=1s monitor=5120x1440 region={'left': 4453, 'top': 0, 'width': 667, 'height': 175}
```

Question answered: was this build running at all, and which one was it? Size and mtime rather
than a hash, because they are free and hashing a 93 KB npz on every activation is not. Also
fixes the 13:28-style ambiguity permanently: a session with no BUILD line means the skill
never activated.

Acceptance: a new test asserts `prepare()` writes exactly one line starting `BUILD` that
contains the version, all three file names, and the region dict.

---

**I2. Promote the row fields that already exist.** Step 1. In `_trace_rows`, append the six
discarded fields to each row line. Keep the existing four fields first, in their current
order, so existing greps keep working.

```
row[2] kind='zone' trusted=False refused=4 cost=6.21 margin=11.40 colour='white' offset=0.31 y=44 text='Zone: SolarSystem_...'
```

Questions answered: how close was this row to being trusted (`refused=1` is one bad cell,
`refused=20` is a different problem); is the whole row marginal or is it one outlier cell
(mean `cost` against the per-cell detail in I3); did the colour variant that won change
between a working and a failing scene?

Cost: zero new computation. Acceptance: as Step 1 criterion 5.

---

**I3. Per-cell refusal detail.** Step 4. The item that decides the OCR fix.

`decode_row` (`overlay_reader.py:516-559`) computes per-cell `cost`, `margin`, and the full
ranked candidate list, then reduces them to a mean and a median and discards the rest.
Capture the per-cell record for REFUSED cells only.

Mechanism: `_decode_block` calls `decode_row` once per colour variant and keeps the best
(`:676-681`), so the records must belong to the WINNING variant. Do not change `decode_row`'s
return signature: have it store the refused-cell records for its own call on the reader
instance, and have `_decode_block` copy the winner's records into the row dict under a new
key, `refused_cells`. That keeps every existing caller and test of `decode_row` untouched.

Emit one line per refused cell, on the FINAL attempt only, and only for rows whose `kind` is
`zone` or `camdir`. The FPS row and the percentile bar refuse constantly by design and their
cells are noise.

```
cell row=2 i=41 cost=17.82 margin=2.10 trip=cost top1='8'@17.82 top2='9'@19.92
cell row=2 i=42 cost=9.10 margin=3.40 trip=margin top1='3'@9.10 top2='8'@12.50
```

`trip` is `cost`, `margin`, or `both`, computed from the same disjunction at `:548` rather
than re-derived, so it cannot disagree with the decision it explains.

Questions answered, and this is the whole point: is the reader failing because nothing matches
(`trip=cost`, high `top1` cost, meaning the bank or the render is wrong) or because two glyphs
are indistinguishable (`trip=margin`, low `top1` cost with `top2` right behind it, meaning a
genuine ambiguity)? Which characters are involved? Which column positions? Are the failures
clustered in the coordinate fields, as the two 08-02 dumps suggest, or spread evenly?

Volume: the two observed refusals had roughly four refused cells across two relevant rows, so
under ten lines per refused capture. Bounded by a constant, `MAX_CELL_TRACE_LINES = 40`, so a
catastrophically bad frame cannot write hundreds.

Acceptance: a new test drives a synthetic row with two refused cells, one tripping cost and
one tripping margin, and asserts both lines appear with the correct `trip` value and that
`top1` and `top2` are the two lowest-cost candidates. A second test asserts a row of kind
`None` produces no cell lines. A third asserts the line count is capped.

---

**I4. Alignment provenance.** Step 1. `OverlayReader.read` (`:642-655`) computes `from_cache`,
knows whether the self-heal refit fired, and returns `y0`; `main.py:336` discards all three
with `_, _, rows =`.

```
align y0=44 from_cache=True refit=True fit_uses=7
```

Question answered: is the reader working from a stale cached origin, and is the self-heal
refit firing on every read? In the observed failures nothing is trusted, so the refit MUST be
firing every time, which doubles the decode work and is a live candidate for the unexplained
per-attempt cost in I7. A `from_cache=True refit=True` pair on every line confirms it;
anything else refutes it.

Acceptance: a new test asserts the line is written per attempt and that `refit=True` appears
when the stub reader reports nothing trusted on the first decode.

---

**I5. The success baseline.** Step 4. Move `overlay_ink_fraction` and
`overlay_row_periodicity` out of the refusal-only branch and into the outcome's `metrics`,
then fold them into the EXISTING successful-capture line at `_log_capture`
(`main.py:486-497`), along with the trusted-row count and the mean cost.

```
capture frame=system pos=(...) camdir=(...) body='' zone='' frame_id='...' ink=0.0531 periodicity=0.6572 trusted=6/8 cost=4.10
```

Questions answered: what do these numbers look like when the reader WORKS? Is `ink=0.0525` on
the failures actually different from a good capture, or is it the same and therefore not the
discriminator? How many rows are normally trusted, and is 6 of 8 normal or already degraded?
Right now `ink` and `periodicity` are four numbers with no control group, which makes them
undiagnostic no matter how many more refusals are collected.

Adds no new LINES: the successful-capture line already exists and already runs once per
capture. It adds two numpy passes over a 667x175 crop per successful capture, cheap against
the roughly 900 ms a read already costs. It needs the outcome object to carry the metrics out
of `_capture_attempt`, which is why it is Step 4 and not Step 1.

Acceptance: a new test asserts a successful capture's log line carries all four new fields,
and that `ink` and `periodicity` are still present on the refusal line unchanged.

---

**I6. Refused frame dump.** Step 4. OPT-IN, capped, local.

Module constant `SAVE_REFUSED_FRAMES = False`. When True, on a final-attempt refusal, save the
grabbed 667x175 crop as a PNG under `<generated_files>/SC_NavPoint/refused/` named
`YYYY-MM-DD_HHMMSS_<kind>.png`, keeping at most the 20 most recent and deleting the oldest
beyond that.

Question answered: everything the log cannot answer. A per-cell classifier failure is
ultimately a question about pixels, and this is the difference between the OCR work iterating
offline against a real corpus and the user having to fly a session for every hypothesis. The
user is the only source of live frames and their time is the scarcest resource in this
project.

Constraints: off by default so nobody's disk fills silently; the crop only, never the full
screen; written locally and never transmitted anywhere; the whole thing inside a try/except so
a dump failure cannot change a capture outcome; and the cap enforced before the write, not
after.

Acceptance: a new test asserts nothing is written when the constant is False; a second asserts
a file appears when True; a third writes 25 and asserts exactly 20 remain and that the
survivors are the newest; a fourth patches the PNG write to raise and asserts the capture
outcome is unchanged.

BLOCKED ON USER: turning this on for a session is the user's call. It is the highest-value
single item in this section and the only one that needs their consent. See OPEN QUESTION 2.

---

**I7. Durations.** Step 1. No line in the log carries a duration today, which is why the 1.1 s
against 11.1 s question needed an outside source to answer at all.

Per attempt: `ms=` on the attempt line. Per capture: total elapsed on the `REFUSED:` line and
on the success line. Optionally per phase (grab, decode, parse) on the attempt line, since the
three are trivially separable and the decode is expected to dominate.

Questions answered: where do the roughly 2.2 seconds per attempt go? Did the per-attempt cost
really double between the 08-01 and 08-02 builds, and if so what changed? Does the self-heal
refit account for it (cross-reference I4)? Is a five-attempt mark costing the player eleven
seconds for nothing (cross-reference Step 7)?

Acceptance: as Step 1 criterion 2, plus a test asserting the success line carries a total.

---

### What the user must do, and what it will produce

BLOCKED ON USER, after Steps 1 to 4 land. One ordinary session, `r_displayinfo 2` up,
including at least one place where marking is known to fail and at least one where it is known
to work. Set `SAVE_REFUSED_FRAMES = True` first if they agree to it. Then hand over
`navpoint_poll.log`, `navpoint_poll.log.1` if it exists, and the `refused/` folder.

Nothing in this instrumentation requires Star Citizen to hold focus. The capture is a screen
grab of a fixed region, which matters because the user plays windowed-borderless with the
terminal on top.

That session yields, for every refused capture: which build, which gate, which rows, how many
cells short each row was, which cells refused and on which of the two conditions, what the two
best candidates were, whether the alignment came from cache and whether it refit, how long
each attempt took, and optionally the pixels. And for every SUCCESSFUL capture in the same
session, the same ink, periodicity, trusted-count and cost figures as a control group. That is
enough to distinguish the two candidate causes without guessing, which is the whole purpose.

---

## 11. Tests

### Existing tests that must still pass, unchanged

All 536. The files most likely to be disturbed, and what they pin:

| File | Pins |
|---|---|
| `tests/test_capture_retry.py` | `_capture_position_local` returns `dict \| None`; the attempt count reaches the local path; the ring reflects the FINAL attempt; 5 grabs and 5 gate calls on full exhaustion |
| `tests/test_capture_trace.py` | all six precondition trace lines; all five gate ids and their clauses; the row dump; a gate walk that raises cannot change the capture |
| `tests/test_main_capture.py` | `captured_at` stamping; auto-naming; the space-mark path; `navigate_to` frame and body refusals; the HUD opening once |
| `tests/test_overlay_reader.py` | `decode_row` and `_decode_block` return shapes; the payload extraction |
| `tests/test_scanner.py` | `local_frame: false` returns a truthy dict with no coordinates |
| `tests/test_space_waypoints.py` | the space branch's truthy return in both sub-cases; the omitted-Root tolerance at `:88-94`; the echo rejection |
| `tests/test_ring_state.py` | the five ring strings and their conditions |
| `tests/test_poll_thread.py` | the dedicated thread and its own loop |
| `tests/test_main_strings.py` | `r_displayinfo 2` present, `r_displayinfo 4` absent |
| `tests/test_reader_rate.py` | the corpus decode rate; I3's record capture must not change any decode decision |

`tests/test_scanner_echo.py` and `tests/test_plausibility.py` must also pass unchanged. Step 5
rewrites the two badge STRINGS for `example_echo` and `implausible_body`; those two files
prove the GUARDS behind them are intact, which is what makes a wording change safe.

The one deliberate exception in the whole plan is the single assertion at
`tests/test_main_capture.py:430`. See DECISION D1, which is approved and scoped to that one
line. A second edited test assertion anywhere is a defect, not a precedent.

`tests/test_space_waypoints.py:88-94` asserts that a space payload with `root_pos_raw` DELETED
still returns a position. That is the local path's Root tolerance and this plan leaves it
exactly as it is.

### New test files

- `tests/test_capture_attempt_trace.py` (Step 1: per-attempt lines, row field promotion, build
  identity, alignment provenance, durations)
- `tests/test_poll_log_rotation.py` (Step 2)
- `tests/test_capture_outcome.py` (Step 3, including the two unlisted producers, the
  false-positive reject reason, and the concurrency test)
- `tests/test_cell_diagnostics.py` (Step 4: I3, I5, I6)
- `tests/test_capture_messages.py` (Step 5: the per-kind table and the `navigate_to` gate)
- `tests/test_capture_async.py` (Step 6)

Every new test installs the runtime stubs via `tests/_stubs.py:install_runtime_stubs` and
builds the skill with `__new__`, following `tests/test_capture_trace.py`. No new test may
require PIL, mss or a screen beyond what `pytest.importorskip` already handles.

---

## 12. Risks

| # | Risk | Cheapest detection |
|---|---|---|
| R1 | New instance attributes read without `getattr`, breaking every test that builds the skill with `__new__` | The existing 536 fail immediately. Run the suite after every step. |
| R2 | I3's per-cell record capture changing a decode decision | `tests/test_reader_rate.py` measures the corpus decode rate. Any change in it means the instrumentation is not read-only. Assert the rate is identical to the baseline. |
| R3 | Instrumentation volume swamping the log and burying the events worth reading | Step 2's rotation, the `MAX_CELL_TRACE_LINES` cap, and keeping `_trace_rows` final-only. Check the file size after the first session. |
| R4 | The added measurements slowing a capture that already costs about 2.2 s per attempt | I7's `ms=` fields make this self-detecting: compare per-phase timings before and after. |
| R5 | `to_thread` plus the capture lock deadlocking if the lock is ever held across an await | Step 6 criterion 3 hangs and the suite times out. Also grep that the lock's `with` block contains no `await`. |
| R6 | Colliding with the metadata planner over the "via Vision AI" strings | Boundary REVISED 2026-08-02. The two chat badges at `main.py:410-423` are IN this plan's scope (Step 5) because they are a live user-facing defect on the local path. Everything else stays with the metadata planner: `default_config.yaml:11` and `:100`, the tool descriptions, and any stored-metadata string. Detection: the two planners must not both edit the same line. Diff Step 5's change and confirm it touches only the two badge string literals and nothing in `default_config.yaml` beyond the two clauses quoted in Step 5. |
| R7 | The reworded `default_config.yaml` changing how the model narrates other tools | Only two clauses change and both are quoted here. Diff the file and confirm exactly those hunks. |
| R8 | Someone "fixing" the reader by lowering `REFUSE_COST` or `REFUSE_MARGIN` while the diagnosis is still open | Add a test asserting both constants equal 15.0 and 8.0, so a change to either is a deliberate act with a failing test attached. |
| R9 | The refused-frame dump filling the disk or capturing something the user did not intend | Off by default, crop only, capped at 20, local only. Enabling it is the user's explicit call. |

---

## 13. Standing hazards, recorded so a future session does not re-arm them

**`_handle_server_change` has no producer, and that is the only reason it is safe.**
`main.py:471-473` routes any non-empty `server_id` into `_handle_server_change`, which wipes
waypoints after three agreeing captures. `ledger/REFUTED.md:243-254` records that the
three-count confirmation does NOT survive a deterministic reader and is explicitly not fixable
by raising the count; `REFUTED.md:260-262` records that it is currently harmless only because
the local reader never emits `server_id`. That is a deliberate omission documented at
`overlay_fields.py:234-240`, not an oversight.

So: **any future change that makes the local reader emit `server_id` re-arms a path that
destroyed six waypoints on 2026-07-26 and killed the poll thread in the same second.** The
`Server:` line is structurally unreadable anyway (lowercase `v`, `j`, `q` and `z` have no
template at either phase), and the `ShardId` line is not a substitute: it carries a different
token shape than the rule was built on. If a future glyph-bank improvement makes that line
readable, the wipe rule must be redesigned BEFORE the field is emitted, not after.

This plan adds no guard and removes none. It changes nothing about this path. See OPEN
QUESTION 2.

**Vision code is dormant, not dead.** Deleting it is irreversible and has been the correct call
to defer three times. Do not delete it as cleanup.

---

## 14. Decisions taken, and what is still open

### DECISION D1: one existing test assertion changes, and exactly one

**USER APPROVED, 2026-08-02.** `tests/test_main_capture.py:430`.

Before:

```python
    assert "r_displayinfo 2" in result["hint"]
```

After:

```python
    assert "hint" not in result
```

Plus a sibling test asserting the hint IS present, with `r_displayinfo 2` in it, for
`KIND_ABSENT`.

**Why the test changed: the SPECIFICATION changed, not the implementation.** The requirement
that changed it is stated in Step 5: *the `r_displayinfo 2` instruction is reserved for the
case where the overlay-presence check actually fails.* The test at `:430` covers the
`no_frame` case, where the overlay WAS on screen and WAS read and there is simply no usable
coordinate frame at that location. Telling the player to enable an overlay that is already
enabled is wrong, and `default_config.yaml:131` orders the model to read that wrong hint out
verbatim. The test's intent, that the refusal message suits the situation, is preserved and
strengthened by the change.

**THIS IS NOT GENERAL PERMISSION TO EDIT FAILING TESTS.** It is a one-line exception,
approved in advance, for one named assertion, for a stated reason. If ANY other test fails
during implementation, that is a different situation entirely: the implementer must fix the
CODE, not the test. A validator should treat any second edited test assertion as a defect in
the implementation until proven otherwise, and should require the same three things this
decision carries before accepting one: the requirement that changed, the before and after,
and an explicit approval.

### DECISION D2: `_handle_server_change` stays, inert

**SUPERVISOR'S CALL, 2026-08-02.** Do not delete it, do not delete
`wipe_on_server_change`, and do not add a guard. Two reasons: it would be a feature removed
as a side effect of a capture-path change, which is not what this work is for and the user
manages his own feature set; and with no Vision there is no new producer, so it is not a live
hazard.

Why it is harmless, so a future session cannot re-arm it without noticing: it is unreachable
ONLY because `overlay_fields` deliberately never emits `server_id`, a deliberate omission
documented at `overlay_fields.py:234-240`. `ledger/REFUTED.md:243-254` records the three-count
confirmation rule as NOT surviving a deterministic reader and explicitly NOT fixable by
raising the count. Section 13 carries the full statement and must not be deleted from this
document.

### CONFIRMATION C1: the failure state distinguishes overlay-absent from overlay-unreadable

**YES.** Confirmed for plan-metadata's change M4, which may proceed.

`KIND_ABSENT` means `overlay_reader.overlay_is_present(frame)` returned False at
`main.py:330`: no overlay on screen. It is the ONLY kind that carries the `r_displayinfo 2`
hint.

Overlay present but unreadable is spread across five other kinds, none of which carries the
hint: `KIND_UNUSABLE` (the frame was too washed out to attempt), `KIND_GATE` (rows decoded, a
field gate refused), `KIND_REJECT` (a payload was built and a safety check refused it),
`KIND_UNEXPLAINED` (a payload was built and carried no usable coordinates), and
`KIND_NO_FRAME` (the overlay read cleanly and there is genuinely no frame at this location).

The distinction is not merely representable, it is the load-bearing rule of Step 5, and Step 5
acceptance criteria 3 and 4 check it mechanically: `hint` is present if and only if the kind
is `absent`.

### CONFIRMATION C2: prompt wording cannot steer skill selection

Noted, and it does not affect this plan. `skill_registry.py:312-354` concatenates every
discoverable skill's DESCRIPTION into one `activate_skill` tool description, while
`open_ai_wingman.py:1556-1574` injects a skill's PROMPT only after that skill is already
active. Nothing in Step 5 relies on prompt wording to influence which skill the model picks.
The per-kind messages are tool RETURN values, which the model always sees. The
`default_config.yaml` reword governs behaviour once NavPoint is running, which is exactly what
it is for. The badges are chat output and bypass the model entirely.

### OPEN QUESTION 1: what should the retry policy become?

Blocked on Step 1's data. Candidates: keep 5; drop to 2 or 3 if late attempts never help;
raise the delay if the gates differ across attempts in a way that suggests 60 ms is too short;
or raise the count if the data shows late attempts DO recover. Not a decision for now, flagged
so it is not forgotten.

### OPEN QUESTION 2: may the refused-frame dump be enabled?

I6 needs the user's consent. It writes local PNGs of a 667x175 top-right screen crop, off by
default, capped at 20 files, never transmitted. It is the highest-value item in Section 10
because it is the only one that lets the OCR work iterate without the user flying a session per
hypothesis. Recommendation: ask them to enable it for one session and hand over the folder with
the log.

---

## 15. Handover notes for the implementer

- Work in the dev tree only: `D:\PycharmProjects\wingman-ai\skills\sc_navpoint\`. Do not touch
  `release_version/` or the AppData live install. The user runs `update_release.py` and the
  installer as part of their own release flow.
- No new runtime files are needed, so neither `skill_installer_config.json` nor
  `update_release.py`'s `RELEASE_FILES` needs an entry. If a step forces a new runtime file
  after all, STOP and add it to BOTH before doing anything else; three past incidents came from
  omitting one.
- `default_config.yaml` is under `preserve_on_update`, so the Step 5 reword will NOT reach the
  live install through a normal skill update. Flag it to the user explicitly.
- Do not bump `VERSION` or `SC_TARGET_VERSION`. Version alignment across the three trees is the
  user's release step.
- Update `Devlog.md` and `TODO.md` as the work lands. In particular, `TODO.md:26` still says
  "BUILD THE ROUTER" and `TODO.md:387` still labels the 07-31 removal SUPERSEDED. Both are now
  wrong and must be corrected to the local-OCR-only decision, with the reversal history kept
  rather than overwritten: this has been decided three times in three days and the record
  should show that.
- Record what was measured, not what was intended.
- Run `python -m pytest tests -q` from `skills/sc_navpoint` after every step, not at the end.
  The baseline is 536 passed in about 23 s.
