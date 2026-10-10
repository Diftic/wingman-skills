# SC NavPoint — plan for the four Project Manager findings

**Written:** 2026-08-02
**Baseline:** `python -m pytest tests -q` gives **654 passed in 26.00s** (re-measured, not quoted)
**Scope:** `skills/sc_navpoint/` dev tree only. No `release_version/`, no live install, no
`update_release.py`, no `install.bat`, no git commit, no version bump.

> **IMPLEMENTER, THE ONE TRAP IN THIS PLAN.** The final ring mapping must NOT be written into
> `self._reader_state`. That field keeps its exact three writes and its exact current values.
> `tests/test_capture_retry.py::test_a_retry_that_succeeds_leaves_a_clean_ring` asserts
> `_reader_state == ""` after a capture that is `KIND_NO_FRAME`, and writing the mapping there
> fails it. Cheapest detection: `python -m pytest tests/test_capture_retry.py -q`.

## 0. What was checked, and what the supervisor's briefing got wrong

Every line number was re-derived from the files. Two structural claims in the briefing were wrong
and both changed the shape of the work.

### 0.1 CONFIRMED

| Claim | Verified at |
|---|---|
| The truthy no-frame payload | `scanner.py`, `result = {` at 525, `return result` at 541, inside `if not data.get("local_frame"):` at 519 |
| `update_position` tests only falsiness | `main.py`, `if not pos_data:` under `async def update_position` |
| The null success shape | `main.py`, `result: dict = {"position": {...}}` reading `pos_data.get("x")` |
| `navigate_to` guards with the helper | `main.py`, `pos_frame = self._capture_frame(pos_data)` then `if pos_frame is None:` |
| `mark_location` open-codes it | `main.py`, `is_space = not pos_data.get("body") and pos_data.get("system_frame")` |
| `_reader_state` has exactly three writes | `main.py` 179, 462, 494 |
| `ring_state()` returns OK on `payload is not None` alone | `overlay_fields.py`, `if payload is not None: return RING_OK` |
| The ring reads the LIVE field, never the outcome | `_sync_ring`, `getattr(self, "_reader_state", "")` twice |
| The poll failure branch continues before `_set_position` | `main.py`, `self._sync_ring()` then `continue` |
| `ring_status` skips its message branch on `""` | `navigation.py`, `if reader_state: return deflection, reader_state` |
| `POSITION_FRESHNESS_S = 30.0`, enforced | `navigation.py`, `if position_age_s is None or position_age_s > freshness_s: return None` |
| Neither no_reader branch writes the ring state | one READS it onto the outcome, the other sets no `ring_state` at all |
| The lock releases before the awaiting caller resumes | the `with` is the whole body of `_capture_position_local`; every diagnostic read is after the `await` |

### 0.2 WRONG 1: finding 3 does NOT enable findings 2 and 4

**The ring is not a per-caller report.** There is one ring on one screen and it should show the
verdict of the most recent look at the screen, whoever took it. A shared last-known field is the
correct channel: `_sync_ring` is called from paths that made no capture at all
(`_on_hud_target_change` on the HUD server's thread, the target-cleared paths, `stop_navigation`),
and those callers cannot hold an outcome. Finding 3's atomicity requirement is about what a TOOL
RESULT says to the player who asked.

**Two pre-existing tests actively block the outcome-driven version.**

- `tests/test_capture_messages.py` builds every skill with `skill._sync_ring = lambda: None`, a
  zero-argument lambda. Giving `_sync_ring` a parameter would `TypeError` there.
- `tests/test_capture_retry.py::test_a_retry_that_succeeds_leaves_a_clean_ring` asserts
  `_reader_state == ""` after a capture that is `KIND_NO_FRAME`.

So findings 2 and 4 are driven by a NEW field, `_last_ring_state`, and `_reader_state` is left
exactly as it is. Independent of finding 3.

### 0.3 WRONG 2: the PM's shape for finding 3 is not reachable

Four groups of pre-existing tests forbid "make the internal capture operation return a result
object":

- `_capture_position_local` must keep returning `dict | None`. About twenty call sites assert it,
  and `test_the_capture_seams_still_return_position_or_none` pins it by name.
- `test_capture_async.py::test_the_offload_is_to_thread_and_wraps_the_local_read` asserts the
  EXACT source substring `await asyncio.to_thread(self._capture_position_local, attempts)`.
- Test doubles replace `_capture_position_local` with `lambda attempts=1: None`.
- `_capture_position` must keep returning `dict | None`; a tuple is never `None`.
- `CaptureOutcome` cannot grow a field: `test_the_outcome_carries_exactly_the_agreed_fields` pins
  the list. Its `metrics` dict may gain keys.

The per-caller channel is therefore out-of-band. Step 3 uses a `contextvars` sink, verified with a
real run rather than assumed: `asyncio.to_thread` copies the caller's context into the worker, so
a list placed in a ContextVar before the call is the same object the worker appends to, and two
concurrent tasks each got their own.

### 0.4 Correction of emphasis

**The `_handle_server_change` side effect of finding 1 is unreachable in production.**
`overlay_fields.payload_from_rows` deliberately never emits `server_id` ("A waypoint wipe must not
be driven from here"), and the local reader is the only payload producer since Vision was removed.
`server_id` is always `""` on this path and `if server_id:` never opens. **Finding 1 is a
wrong-answer bug, not a data-loss bug**, and must not drive priority on wipe-risk grounds.

## 1. Order of work

| Step | Finding | Why here |
|---|---|---|
| **1** | Finding 1, `update_position` no-frame guard | Independent. Smallest diff, largest player-visible lie. One function. |
| **2** | Findings 2 + 4, one final outcome-to-ring mapping | Independent of 1 and 3. One mapping serves both. |
| **2S** | Bubble suppression (user decision D-1) | Same subsystem as 2, and 2's ring test must be written knowing whether a bubble survives. |
| **3** | Finding 3, per-caller diagnostics | Last: touches the most source-text-pinned tests, and rewrites the same lines in the three tools that step 1 has just made four. |
| **4** | Finding 3, capture-level `ms=` | Split out so it can be dropped without unpicking step 3. |

Run the full suite after every step. Never carry a red suite into the next step.

## STEP 1 — `update_position` must refuse a payload with no frame

### 1.1 Files and functions

**`main.py`, `async def update_position`, and nothing else.** After the existing falsy guard:

```python
if self._capture_frame(pos_data) is None:
    return json.dumps(
        self._capture_error(
            getattr(self, "_last_outcome", None),
            overlay_fields.KIND_NO_FRAME,
        )
    )
```

Use `self._capture_frame(...)`. It is a `@staticmethod`, so it works on the `__new__`-built skills
the tests use. Do NOT open-code a fourth copy of the predicate; there are already two and
`_capture_frame` exists to stop that. Pass `KIND_NO_FRAME` explicitly rather than letting
`_capture_error` read `outcome.kind`: the returned payload proves its own kind, which is stronger
than a field that may hold an earlier capture's verdict.

### 1.2 What must NOT change

- No new message. `_CAPTURE_MESSAGES[KIND_NO_FRAME]` already exists; all three tools must keep
  producing the identical string.
- No `hint`. The overlay WAS read here.
- A system-frame capture (`body == ""`, `system_frame` True) must still succeed. `_capture_frame`
  returns `"system"` for it, so the guard keys on `is None`, never on `not pos_data.get("body")`.
- Do not touch `_capture_position`, the scanner, or the refusal classification.

### 1.3 New tests, `tests/test_update_position_no_frame.py`

Model fixtures on `tests/test_capture_messages.py`; import or re-declare locally, do not edit that
file.

| Test | Asserts | Mutation that must break it |
|---|---|---|
| `test_update_position_refuses_a_station_interior` | `capture_kind == "no_frame"`, `"position" not in result`, `"hint" not in result` | delete the guard, `position` present with `x: null` |
| `test_update_position_and_mark_location_agree_on_a_truthy_no_frame_payload` | the two `error` strings are equal | delete the guard, mark errors and update succeeds |
| `test_a_system_frame_capture_still_reports_its_position` | `result["position"]["x"] == 1.0`, no `error` | write the guard as `if not pos_data.get("body")`, refuses a legitimate deep-space fix |
| `test_update_position_uses_the_shared_frame_helper` | source slice contains `_capture_frame(` and not `system_frame` | open-coding the predicate fails |

Do not use `inspect.getsource` on the tools; they are `@tool`-decorated. Slice `_MAIN_SRC`.

### 1.4 Acceptance criteria

```
cd D:\PycharmProjects\wingman-ai\skills\sc_navpoint
python -m pytest tests -q
```
gives `658 passed` (654 + 4).

```
python -m pytest tests/test_update_position_no_frame.py -q   -> 4 passed
python -m pytest tests/test_capture_messages.py -q           -> all pass
grep -n "_capture_frame(pos_data)" main.py                   -> at least 2 hits
```

Record `grep -c "_OVERLAY_HINT" main.py` BEFORE editing; it must be the same integer after.

**Revert proof:** delete the four added lines, at least 3 of the 4 new tests fail. Restore.

## STEP 2 — one final outcome-to-ring mapping, applied after scanner validation

Covers findings 2 and 4. One mapping, one field, five call sites.

### 2.1 The new ring string

**`RING_NO_FRAME = "INDOORS"`.** User decision P-1, settled 2026-08-02. Seven characters, inside
the 12-character budget that `tests/test_ring_state.py::test_states_are_distinct_and_short_enough_for_the_ring`
documents against the 220 px render budget. ASCII only, which matters: the ring renders through PIL
with a bundled font and a missing glyph draws as a box, which is why `ACQUIRING...` uses three
ASCII dots rather than U+2026.

Rationale, recorded so nobody "tidies" it later: `INDOORS` names the player's SITUATION rather than
the instrument's internal state, so the action is self-evident without a second sentence. The user
rejected `NO FRAME` for that reason. It departs from the `NO SIGNAL` / `NO BEARING` pattern
deliberately. Under D-1 it is the ONLY thing on the ring during a no-frame capture, which is why
the wording carries more weight than it would have.

**THE EXACT SPELLINGS. Confirmed byte-exact against `overlay_fields.py`, not transcribed from any
summary. Use these, do not retype them from memory:**

```
RING_OK         = ""
RING_ACQUIRING  = "ACQUIRING..."     three ASCII full stops, U+002E. NOT U+2026.
RING_GLARE      = "GLARE"
RING_NO_SIGNAL  = "NO SIGNAL"        one space
RING_NO_BEARING = "NO BEARING"
RING_NO_FRAME   = "INDOORS"          new
```

The ellipsis matters and the file already says why: "ASCII dots, not U+2026. The ring renders
through PIL with a bundled font, and a missing glyph would show as a box on the HUD; three dots
cannot fail." Anyone typing an ellipsis character puts a box in front of the player. Both spellings
have appeared in working notes today, so this is a live hazard rather than a theoretical one.

### 2.2 The mapping

New function in `overlay_fields.py`, immediately after `ring_state()`:

```python
def ring_for_outcome(kind: str, reader_state: str) -> str:
    """What the ring must say once the capture is FULLY decided."""
```

| kind | returns | why |
|---|---|---|
| `KIND_OK` | `RING_OK` (`""`) | nothing to say |
| `KIND_NO_FRAME` | `RING_NO_FRAME` (`"INDOORS"`) | the overlay read perfectly; waiting produces no frame, so `ACQUIRING...` would promise a fix that cannot arrive |
| `KIND_NO_READER` | `RING_NO_SIGNAL` | user decision D-2, known imperfect and accepted |
| `KIND_REJECT`, `KIND_UNEXPLAINED` | `RING_ACQUIRING` | user decision D-3. `reader_state` is `RING_OK` on these paths because a payload existed |
| `KIND_NO_GRAB`, `KIND_UNUSABLE`, `KIND_ABSENT`, `KIND_DECODE_ERROR`, `KIND_GATE` | `reader_state` unchanged | the reader already answered correctly, including the rows-based ACQUIRING-vs-GLARE split that `kind` alone cannot reproduce |
| an unknown kind | `RING_ACQUIRING` | fail visible, never fail silent |

### 2.3 Where it is applied

**`_capture_attempt`**, the two returns AFTER `parse_payload` runs: change
`ring_state=self._reader_state` to `ring_state=overlay_fields.ring_for_outcome(kind, self._reader_state)`.
Leave the `KIND_NO_GRAB` return and the pre-`parse_payload` refusal return alone; the mapping is
identity for their kinds.

**`_capture_position_local`, `KIND_NO_READER` branch**: set `ring_state=overlay_fields.RING_NO_SIGNAL`
instead of `getattr(self, "_reader_state", "")`. Finding 4's first half.

**`_capture_position`, `if not self._scanner:` branch**: add `ring_state=overlay_fields.RING_NO_SIGNAL`.
Finding 4's second half; today that outcome takes the dataclass default `""`.

**`_capture_position_local`**: publish the final state. Inside the lock, at the two points the
outcome becomes final, add `self._last_ring_state = self._last_outcome.ring_state`. Also set it in
`_capture_position`'s no-scanner branch.

**`__init__`**: declare `self._last_ring_state = ""` immediately after `self._reader_state = ""`,
with a comment: `_reader_state` is the reader's per-attempt verdict, `_last_ring_state` is the
ring's, decided after validation.

**`_sync_ring`**: replace BOTH `getattr(self, "_reader_state", "")` with
`getattr(self, "_last_ring_state", "")`. Keep the zero-argument signature. Do NOT write
`getattr(self, "_last_ring_state", "") or getattr(self, "_reader_state", "")`: an empty
`_last_ring_state` means RING_OK, and `or` resurrects exactly the stale state this step removes.

### 2.4 What must NOT change

- `self._reader_state` keeps its current three writes and values. See the trap.
- `overlay_fields.ring_state()` keeps its exact behaviour; eight assertions cover it. The new
  function wraps its output, it does not replace it.
- `ring_deflection` untouched. No `CaptureOutcome` field added. No refusal behaviour moves.

### 2.5 New tests, `tests/test_ring_after_rejection.py`

| Test | Asserts | Mutation that must break it |
|---|---|---|
| `test_a_scanner_rejection_does_not_leave_the_ring_at_ok` | `_last_ring_state` and `_last_outcome.ring_state` both truthy | revert the `KIND_REJECT` return, both `""` |
| `test_a_no_frame_capture_leaves_a_terminal_ring_state` | `_last_ring_state == fields.RING_NO_FRAME`, neither OK nor ACQUIRING | revert, `""` |
| `test_a_missing_reader_leaves_an_unavailable_ring_state` | `RING_NO_SIGNAL` even though `_reader_state` was pre-set `""` | revert, `""` |
| `test_the_async_scanner_unavailable_branch_says_so_too` | both fields `RING_NO_SIGNAL` | revert, `""` on both |
| `test_the_poll_failure_branch_puts_a_message_on_the_ring` | **the reported harm end to end.** Fake overlay recording `set_state`; the message is non-empty | revert `_sync_ring`, message `""` |
| `test_a_clean_capture_still_leaves_the_ring_silent` | `_last_ring_state == ""`, message `""`, deflection non-None | map `KIND_OK` to anything non-empty, fails |
| `test_every_kind_maps_to_something_the_ring_can_show` | every `KIND_*` except OK maps non-empty and `0 < len <= 12` | add a kind with no mapping, or ship a 14-character string, fails |
| `test_the_reader_verdict_survives_for_the_kinds_it_answers` | ABSENT keeps NO SIGNAL, UNUSABLE keeps GLARE, GATE keeps ACQUIRING | flatten the mapping, the player is told to type `r_displayinfo 2` for glare |

### 2.6 Acceptance criteria

```
python -m pytest tests -q                                                     -> 666 passed
python -m pytest tests/test_capture_retry.py -q                               -> all pass
python -m pytest tests/test_ring_state.py tests/test_ring_message.py tests/test_ring_overlay.py -q   -> all pass
python -m pytest tests/test_space_direction_test_mode.py -q                   -> all pass
grep -c "_reader_state = " main.py                                            -> 3
grep -n "_last_ring_state" main.py                                            -> 6 hits
grep -c "getattr(self, \"_reader_state\"" main.py                             -> 0
grep -c "def ring_for_outcome" overlay_fields.py                              -> 1
```

`test_space_direction_test_mode.py` text-slices `main.py` on `def _sync_ring`, so it fails if a
method is inserted between `_get_space_direction_test` and `_sync_ring`. Do not insert one.

`grep -c "_reader_state = "` returning 4 means the final mapping went into the wrong field.

**Revert proof:** revert `_sync_ring`'s two reads, `test_the_poll_failure_branch_puts_a_message_on_the_ring`
fails. Revert the two `_capture_attempt` returns, three more fail. Restore.

## STEP 2S — suppress the bubble on a refusal

**User decision D-1, reaffirmed 2026-08-02 with the full cost stated.** On a refusal the ring shows
its no-fix face and the message, never a bearing from the last good capture. This reverses the
coexistence design recorded in `navigation.py`.

### 2S.1 What suppression means concretely

One line, in `navigation.ring_status`:

```python
if reader_state:
    return None, reader_state        # was: return deflection, reader_state
```

Consequences, all already-supported paths:

- `_sync_ring` receives `deflection is None` whenever a message exists and calls
  `overlay.set_state(True, None, message)`. **`ring_overlay.set_state` needs no change**: its
  docstring already defines `deflection=None` as "the ring shows its no-fix face rather than a
  bubble pointing somewhere invented".
- The renderer needs no change. `RingRenderer.frame(None, alpha, message)` is already exercised.
- `RING_NO_BEARING` and the aged-out `RING_ACQUIRING` paths are unaffected.
- **A behaviour change worth naming:** `_sync_ring`'s space-test logging is guarded by
  `deflection is not None`, so during a refusal no `SPACE TEST (UNCALIBRATED)` line is written any
  more. Consistent, but it thins the calibration log during a refusal-heavy flight. Mention it in
  the Devlog; do not work around it.
- `ring_deflection` is untouched and remains the single authority on whether a bubble MAY be drawn.
  Suppression is a second, stricter gate on top, not a replacement.

**Suppression is uniform on a truthy `reader_state`, not per kind.** So the bubble also vanishes on
GLARE and NO SIGNAL, not only on scanner rejections. Over sunlit terrain glare is the common case,
so in practice the bearing is absent for much of a surface flight. The user was told this and chose
it. `ring_status` receives only the string, not the kind, so a per-kind rule would move the decision
out of the one function that decides drawing and saying together.

### 2S.2 The comment that must be rewritten, not deleted

`navigation.py`, inside `ring_status`'s docstring, currently reads "A FRESH BUBBLE AND A MESSAGE CAN
COEXIST, deliberately" with the strobing-over-terrain rationale. **Rewrite it in place.** Deleting
it loses the reason the code was that way and invites a future reader to reintroduce coexistence as
a fix. The replacement must record all four of: that coexistence was the original design; the
rationale (over terrain the reader refuses most frames, so the bubble would strobe while a
two-second-old fix is still inside the freshness window); that the user reversed it on 2026-08-02
with the strobing cost stated and accepted; and that the message is now the ONLY thing on the ring
during a refusal, which is why each ring string's wording matters more than it did.

`ring_overlay.set_state`'s docstring says the message "is independent of the bubble". That stays
TRUE at the renderer level. Add one clause saying the policy above no longer asks for both at once.

### 2S.3 What must NOT change

- `ring_deflection`'s behaviour, its freshness rule, `POSITION_FRESHNESS_S = 30.0`.
- The renderer's ability to draw a bubble and a message together.
  `test_the_message_does_not_move_the_bubble` and `test_message_layers_are_cached_per_string` call
  `RingRenderer.frame` directly and must keep passing UNCHANGED. They test the renderer, not the
  policy.
- `MessageFader`, `_MESSAGE_FADE_S = 0.45`, `_MESSAGE_DWELL_S = 1.0` and every photosensitivity
  test. Do not extend the fader to the bubble in this step. See R13.

### 2S.4 New tests, added to `tests/test_ring_after_rejection.py`

| Test | Asserts | Mutation that must break it |
|---|---|---|
| `test_a_refusal_draws_no_bubble` | `ring_status(_POSITION, _TARGET, 2.0, RING_GLARE)` returns `(None, RING_GLARE)`; the fix is 2 s old, well inside freshness, so only the new rule can blank it | restore, deflection is not None |
| `test_the_poll_failure_branch_draws_no_bubble` | end to end through `_sync_ring`: `deflection is None` and a non-empty message | restore, a bearing is drawn with the message |
| `test_a_clean_read_still_draws_its_bubble` | `ring_status(_POSITION, _TARGET, 1.0, "")` returns non-None and `""` | suppress unconditionally, the ring never draws anything |

The third matters most: the cheapest way to get this step wrong is to blank the bubble always.

### 2S.5 Acceptance criteria

```
python -m pytest tests -q                                                  -> 669 passed
python -m pytest tests/test_ring_message.py -q                             -> all pass
python -m pytest tests/test_ring_overlay.py -q                             -> all pass
python -m pytest tests/test_ring_deflection.py tests/test_freshness.py -q  -> all pass
grep -n "return None, reader_state" navigation.py                          -> 1 hit, inside ring_status
grep -c "CAN COEXIST" navigation.py                                        -> 0
```

669 = 666 plus 3, with A-1 resolved by rewriting in place (see below), which keeps the count.

**Revert proof:** restore `return deflection, reader_state`, the first two 2S tests fail. Restore.

## STEP 3 — each caller reports its own capture's diagnostics

### 3.1 The mechanism, and why it is this one

Read 0.3 first. No signature and no return type may change, so the outcome travels in a
`contextvars` sink the CALLER creates. At MODULE scope in `main.py`, not class scope:
`test_capture_outcome.py` counts `_capture_lock` occurrences inside
`inspect.getsource(main.SC_NavPoint)` and a class-level helper would sit inside that text.

```python
import contextlib
import contextvars

_CAPTURE_SINK: contextvars.ContextVar[list | None] = contextvars.ContextVar(
    "navpoint_capture_sink", default=None
)


@contextlib.contextmanager
def _capture_sink():
    """A per-caller channel for the outcome of the capture THIS caller asked for.

    The lock in `_capture_position_local` releases when that function returns,
    which is BEFORE `asyncio.to_thread` marshals the result back to the awaiting
    coroutine. The poll thread fires every second unattended, so between those
    two moments a whole second capture can finish and overwrite
    `self._last_outcome`, `self._scanner.last_reject_reason` and the one-shot
    badge latches. A caller reading them afterwards could be handed the OTHER
    capture's kind, and with it the `r_displayinfo 2` hint for an overlay that
    had just been read.

    A ContextVar and not an argument: both capture seams have signatures and
    return types pinned by tests (see 0.3), and `asyncio.to_thread` copies the
    caller's context into the worker thread, so the list put here before the
    call is the same list object the worker appends to.
    """
```

Contract:

- The four callers of `_capture_position` wrap their `await` in `with _capture_sink() as sink:`.
- `_capture_position_local` appends its final `CaptureOutcome` to `_CAPTURE_SINK.get()` when one is
  set, at the same two points it assigns `self._last_outcome`, INSIDE the lock.
  `self._last_outcome` keeps being written: it is the observability snapshot and eight existing
  tests read it.
- `_capture_position` reads `outcome = sink[-1] if sink else getattr(self, "_last_outcome", None)`
  and uses it for the badge reason and for `_log_capture`'s metrics.
- Each tool reads its own `sink[-1] if sink else ...` and passes THAT to `_capture_error`.

**The fallback to the shared field is required, not sloppiness.** Eight existing tests replace the
capture seams with doubles that fill no sink. It is unreachable in production because the real
`_capture_position_local` always appends. Say so in a comment and pin it with a test.

Badge reasons: replace `reason = getattr(self._scanner, "last_reject_reason", None)` with
`reason = getattr(outcome, "reject_reason", "") or None` when an outcome came back from the sink,
falling back to the scanner read otherwise. `reject_reason` defaults to `""` and is set from
`last_reject_reason` on the `KIND_REJECT` path, so the five badges are reached by exactly the same
reasons as today.

### 3.2 What must NOT change

- `_capture_position_local(self, attempts: int = 1) -> dict | None`, not a coroutine.
- `_capture_position(self, attempts: int = 1) -> dict | None`, a coroutine.
- The exact source line `await asyncio.to_thread(self._capture_position_local, attempts)`.
- `CaptureOutcome`'s field list.
- Lines containing `_capture_position(`: exactly 5, of which 4 are `await self._capture_position(`.
  Wrapping a call in a `with` does not change either count; adding a helper that calls it would.
- The `with getattr(self, "_capture_lock", ...)` line: exactly one, holding no `await`, with
  `_capture_lock` appearing exactly twice in `inspect.getsource(main.SC_NavPoint)`.
- The five badge strings, byte for byte. One-shot latches stay one-shot per activation.
- A diagnostic can never break a capture: everything added is inside the existing swallow-and-log
  structure, or is a list append that cannot raise.

### 3.3 New tests, `tests/test_capture_diagnostics_atomic.py`

Make the handoff deterministic by injecting the second capture into the exact window:

```python
real_to_thread = asyncio.to_thread

async def _to_thread_then_b(func, /, *args, **kwargs):
    result = await real_to_thread(func, *args, **kwargs)
    if not fired:
        fired.append(1)
        make_b_the_next_capture()
        t = threading.Thread(target=skill._capture_position_local)
        t.start()
        t.join(timeout=5)
    return result

monkeypatch.setattr(main.asyncio, "to_thread", _to_thread_then_b)
```

| Test | Asserts | Mutation that must break it |
|---|---|---|
| `test_a_tool_reports_its_own_capture_not_the_poll_thread_s` | A is `KIND_GATE`, B is `KIND_NO_READER`; `capture_kind == "gate"` | revert the tool to the shared field, reports B's kind |
| `test_a_tool_is_not_handed_the_overlay_hint_for_an_overlay_it_just_read` | B = `KIND_ABSENT`; no `hint`, no `r_displayinfo` anywhere in the result | revert, the hint is relayed verbatim for a frame that WAS read |
| `test_the_badge_names_the_caller_s_own_reject_reason` | A `frame_mismatch`, B `example_echo`; the single printr call is the frame_mismatch text | revert the badge read, the echo badge fires |
| `test_the_capture_line_carries_the_caller_s_own_metrics` | the `capture frame=` line shows A's `trusted=`/`cost=` | revert `_log_capture`, B's numbers |
| `test_a_replaced_capture_seam_still_reports_through_the_shared_field` | with the seam replaced and `_last_outcome` pre-set, the tool still reports that kind | delete the fallback, eight existing tests break; this one names why it exists |
| `test_the_sink_does_not_outlive_its_caller` | after `asyncio.run(...)`, `main._CAPTURE_SINK.get() is None` | drop `finally: reset(token)`, leaks between callers |

`fired` as a list, not a `nonlocal` bool. `monkeypatch.setattr` on `main.asyncio` is undone
automatically.

### 3.4 Acceptance criteria

```
python -m pytest tests -q                                                     -> 675 passed
python -m pytest tests/test_capture_async.py tests/test_capture_outcome.py -q -> all pass
python -m pytest tests/test_capture_messages.py -q                            -> all pass
grep -c "await asyncio.to_thread(self._capture_position_local, attempts)" main.py -> 1
grep -c "await self._capture_position(" main.py                               -> 4
grep -c "with getattr(self, \"_capture_lock\"" main.py                        -> 1
grep -c "_capture_sink()" main.py                                             -> 5
grep -n "_CAPTURE_SINK" main.py                                               -> 4 hits
```

Plus, with the test stubs installed:
`inspect.getsource(main.SC_NavPoint).count('_capture_lock')` gives `2`.

**Revert proof:** in `mark_location`, replace the sink read with the shared field, the first two
tests fail. Restore.

## STEP 4 — the capture duration on the success line is the caller's own

Optional and separable. Drop it whole if step 3 runs long; nothing else depends on it.

### 4.1 The change

`_log_capture` ends its line with `self._capture_ms()`, reading `self._capture_started_at`. That
stamp is restamped inside the lock by every capture, so a caller reading it after its `await` can
report the OTHER capture's duration, always as a SHORTER time than it actually waited.

- In `_attempt_metrics`, add one key alongside `metrics["ms"]`:
  `metrics["capture_ms"] = round((time.perf_counter() - getattr(self, "_capture_started_at", started)) * 1000.0, 1)`.
  Every `_attempt_metrics` call happens inside the lock, so the value is unraced. `metrics["ms"]`
  keeps its meaning.
- `_log_capture` formats the trailing field as `ms={capture_ms:.0f}` when the key is present,
  falling back to `self._capture_ms()` when it is not.

### 4.2 What must NOT change

- The trailing field is still LAST and still matches `\bms=\d+$`, so integer formatting is
  mandatory: `capture_ms` is a float.
- `_capture_ms()` stays unchanged: the REFUSED line uses it from inside the lock, where it is
  already correct.
- No `CaptureOutcome` field. `metrics` is a plain dict and gaining a key is safe.

### 4.3 Test

`test_the_capture_line_reports_the_time_the_caller_actually_waited`: reuse the step 3 injection.
A's reader sleeps 0.25 s, B's does not. Assert A's `ms=` is `>= 200`. One-sided, so it cannot flake
on a fast machine; with the bug the value is near zero.

### 4.4 Acceptance criteria

```
python -m pytest tests -q                                                              -> 676 passed
python -m pytest tests/test_capture_attempt_trace.py tests/test_cell_diagnostics.py -q -> all pass
```

**Revert proof:** restore `self._capture_ms()` unconditionally, the new test fails.

## Existing tests that must still pass, and the ones at risk

All 654 must pass after every step, with the single authorised exception A-1. A validator should
run these by name as well as running the suite.

| Test | Step | Why at risk |
|---|---|---|
| `test_capture_retry.py::test_a_retry_that_succeeds_leaves_a_clean_ring` | 2 | asserts `_reader_state == ""` after `KIND_NO_FRAME`. **The trap.** |
| `test_capture_retry.py::test_the_ring_reflects_the_final_attempt` | 2 | the monkeypatched `ring_state` value must survive on `_reader_state` |
| `test_ring_message.py::test_a_fresh_bubble_survives_a_reader_refusal` | 2S | **asserts the behaviour D-1 reverses. See A-1.** |
| `test_ring_message.py::test_the_message_does_not_move_the_bubble` | 2S | renderer-level, must pass UNCHANGED |
| `test_ring_message.py` photosensitivity block (4 tests) | 2S | `MessageFader` untouched |
| `test_ring_state.py::test_states_are_distinct_and_short_enough_for_the_ring` | 2 | any new ring string is 1 to 12 characters |
| `test_ring_state.py` (8 assertions) | 2 | `ring_state()` keeps its behaviour |
| `test_space_direction_test_mode.py::test_the_skill_defaults_the_switch_off` | 2 | text-slices on `def _sync_ring` |
| `test_version_49022.py::test_skill_wires_the_ring_through_one_place` | 2 | `def _sync_ring` and `def _set_position` still exist |
| `test_capture_async.py` (6 pinning tests) | 3 | exact source substrings, sync/async split, no await in lock, one lock site, blocking sleep, no `create_task` |
| `test_capture_outcome.py::test_the_capture_call_sites_are_the_same_five` | 3 | 5 lines, 4 awaits |
| `test_capture_outcome.py::test_the_capture_seams_still_return_position_or_none` | 3 | position-or-None and sync |
| `test_capture_outcome.py::test_the_outcome_carries_exactly_the_agreed_fields` | 2, 3 | no new `CaptureOutcome` field |
| `test_capture_outcome.py` (8 producer tests) | 3 | each reads `_last_outcome` after a direct call |
| `test_capture_messages.py` (5 badge tests) | 3 | stub the seam and set `last_reject_reason`: they require the fallback |
| `test_capture_messages.py::test_all_three_tools_report_the_same_kind_identically` | 1, 3 | one string per kind across three tools |
| `test_capture_messages.py::test_the_three_correct_badges_are_byte_identical_to_baseline` | 3 | badge strings byte for byte |
| `test_capture_attempt_trace.py::test_the_successful_capture_line_carries_the_total` | 3, 4 | `\bms=\d+$` at the end |
| `test_cell_diagnostics.py::test_a_successful_capture_line_carries_the_baseline` | 3, 4 | ink / periodicity / trusted / cost on the success line |
| `test_refusal_thresholds.py` (whole file) | all | source-text match. Nothing here touches it; if a reformat breaks it, restore the formatting, never the test |
| `test_arrival.py`, `test_poll_thread.py`, `test_server_change.py`, `test_main_capture.py` | 3 | all replace or drive `_capture_position` |

## Risks and the cheapest detection

| # | Risk | Cheapest detection |
|---|---|---|
| R1 | Step 2 writes the mapping into `_reader_state` | `pytest tests/test_capture_retry.py -q`, 2 failures |
| R2 | `_sync_ring` keeps an `or _reader_state` fallback, resurrecting the stale state | `grep -c "getattr(self, \"_reader_state\"" main.py` gives 0 |
| R3 | A future ring string exceeds the render budget | `test_every_kind_maps_to_something_the_ring_can_show` asserts 1 to 12 characters |
| R3b | **`ACQUIRING...` typed with U+2026 instead of three ASCII full stops, drawing a box on the player's HUD.** Both spellings have appeared in working notes today | `python -c "import overlay_fields as f; print(f.RING_ACQUIRING.encode())"` gives `b'ACQUIRING...'` with no `\xe2\x80\xa6`. Add this as an assertion in the new mapping test so it cannot regress |
| R4 | A future `KIND_*` added with no mapping, silently showing OK | the same exhaustive test, which enumerates `dir(overlay_fields)` |
| R5 | Step 3 changes a pinned source string | `pytest tests/test_capture_async.py tests/test_capture_outcome.py -q` |
| R6 | The ContextVar leaks between callers | `test_the_sink_does_not_outlive_its_caller`, plus `finally: reset(token)` |
| R7 | The fallback is later deleted as dead code, breaking eight tests | `test_a_replaced_capture_seam_still_reports_through_the_shared_field` names it |
| R8 | Step 1 over-refuses and blocks legitimate deep-space fixes | `test_a_system_frame_capture_still_reports_its_position` |
| R9 | Step 4's `ms=` stops being last or stops being an integer | `test_the_successful_capture_line_carries_the_total` |
| R10 | A method inserted between `_get_space_direction_test` and `_sync_ring` | `pytest tests/test_space_direction_test_mode.py -q` |
| R11 | A reformat breaks the refusal-threshold source match | `pytest tests/test_refusal_thresholds.py -q`; restore formatting, never the test |
| R12 | The step 3 race test is flaky | it is not timed: the second capture is injected synchronously inside the wrapped `to_thread`, bounded by `join(timeout=5)`. Only step 4 uses a clock, one-sidedly |
| R13 | **Suppression makes the BUBBLE blink at the poll rate over terrain.** The message is damped by the fader; the bubble has no equivalent | Not a photosensitivity hazard: `poll_interval` is bounded 1 to 10 s, so worst-case toggle is about 0.5 Hz against the roughly 3 to 60 Hz hazardous band. A readability cost, accepted by the user with the figure stated. Detection is a live look during the diagnostic flight, not a test. See R13b for what makes it worse than the figure suggests, and R13c for the ready mitigations |
| R13b | **The bubble POPS, it does not fade, and after A-1 nothing guards that.** `MessageFader` ramps the message over `_MESSAGE_FADE_S = 0.45` and holds it `_MESSAGE_DWELL_S = 1.0`, and four photosensitivity tests enforce that the message never blinks. The bubble has no equivalent: `if target is None: smoothed = None` takes effect on the next frame at 30 fps, so it vanishes in about 33 ms, and `elif smoothed is None: smoothed = target` snaps it back deliberately so it "never streaks in from the centre". Only movement BETWEEN two live fixes is eased. **So suppression makes the bubble do exactly what the message is forbidden to do, with the machinery to prevent it present and unwired.** And `test_a_fresh_bubble_survives_a_reader_refusal` is the ONLY test asserting a bubble survives a refusal, so after A-1 the bubble's stability is guarded by nothing | A live look. There is no test, by construction |
| R13c | Which regime actually occurs is UNMEASURED | The 62 to 100 per cent figure is CELL refusal, a different measurement from how often a whole CAPTURE is refused, and no capture-level refusal rate exists in the evidence. Sustained refusal (bubble out once, stays out) is an unambiguous improvement; alternating refusal (0.5 Hz pop) is the ugly case. The diagnostic flight settles it. **Ready mitigations if it reads badly, in order of preference, each a small contained change to the same single line and none needing a replan:** (a) suppress only the TERMINAL kinds `no_frame` and `no_reader`, which cannot strobe by their nature since nothing about waiting brings the fix back, zero flicker by construction; (b) add an N-consecutive-refusal debounce for the transient kinds, changing the question from "did this frame refuse" to "has the fix stopped resuming"; (c) wire the existing fader to the bubble. **Note (a) and (b) both need a companion flag beside `_last_ring_state`**, because D-2 collapses `no_reader` onto `NO SIGNAL` alongside `absent`, so the ring string can no longer distinguish terminal from transient |

## User decisions, settled

Recorded so nobody rediscovers them as bugs.

- **D-1, the stale bubble is SUPPRESSED on a refusal.** Decided 2026-08-02 against the planning
  recommendation, then REAFFIRMED after being told two further costs: that suppression keys on any
  ring message so the bubble also vanishes in glare, which over sunlit terrain is the common case;
  and R13's up-to-0.5 Hz flicker during intermittent refusals. Both accepted. It is a judgement
  about how the user flies. Step 2S implements it.
- **D-2, `no_reader` reuses `RING_NO_SIGNAL`.** Decided 2026-08-02 against the planning
  recommendation of a new string, with the imperfection stated first. **The known imperfection:**
  `NO SIGNAL` is the string tied to typing `r_displayinfo 2`, and that action cannot help when the
  skill's own reader failed to load. `no_reader` and `absent` are indistinguishable on the ring.
  Diagnosis is not lost: the tool result still carries `capture_kind: "no_reader"` and the poll log
  still records `REFUSED: reader=unavailable`. **Do not "fix" this without asking.**
- **D-3, `ACQUIRING...` for all five reject reasons.** Decided 2026-08-02. No fifth string. **The
  known over-promise:** `implausible_body` is not transient, and its badge already says "There is no
  action here: looking again produces the same reading and the same refusal", while the ring says
  `ACQUIRING...`, which means wait. The two channels disagree for that one reason. Accepted.
- **P-1, the no-frame ring string is `INDOORS`.** Decided 2026-08-02. `NO FRAME` was rejected. See
  2.1 for the rationale.
- **A-1, the blocking test is REWRITTEN IN PLACE, not deleted.** Decided 2026-08-02.
  `tests/test_ring_message.py::test_a_fresh_bubble_survives_a_reader_refusal` becomes
  `test_a_refusal_blanks_even_a_fresh_bubble`, same fixtures, assertion inverted to
  `deflection is None`, and a docstring recording the reversal and its date. This is the THIRD
  authorised pre-existing test change in the project. **It is a test changed because the behaviour
  it guarded is no longer wanted, not because it was inconvenient**, and the docstring must say so
  in those terms. Rewriting keeps the count at 654 and keeps the original strobing argument visible
  beside the new assertion, so a future reader can see that suppression was weighed against it
  rather than wonder.

Rejected for the record: implementing suppression inside `_sync_ring` so `ring_status` keeps its old
return and the test stays green. It would leave a passing test whose docstring asserts the opposite
of shipped behaviour, and it splits the bubble-and-message decision across two files, which is the
disagreement `ring_status` exists to prevent.

## Definition of done

- `python -m pytest tests -q` gives **676 passed** (654 + 4 + 8 + 3 + 6 + 1). Subtract 1 if step 4
  is dropped.
- Every acceptance command produces its stated output.
- Every revert proof performed and the guard restored.
- `grep -c "INDOORS" overlay_fields.py` gives at least 1, and no placeholder string remains.
- No file outside `skills/sc_navpoint/` touched. No file inside `release_version/` touched.
- Exactly ONE existing test changed, the one named in A-1, recorded in the Devlog as an authorised
  spec change. `git diff --stat -- skills/sc_navpoint/tests/` shows added files plus that single
  modification. (`main.py`, `overlay_fields.py`, `navigation.py` and the reader files are untracked
  or predate HEAD, so `git diff` is not a reliable check for the source files; the tests directory
  is the one that matters.)
- No version bump: `4.9.0.22` unchanged in `main.py` and `skill_installer_config.json`.
- No new runtime file, so both manifests are unchanged.
- Devlog entry records D-1 including the two costs it was reaffirmed against, D-2, D-3, P-1, the
  A-1 resolution, and the two behaviour consequences in 2S.1 and R13.
