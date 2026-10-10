# Plan: Speech-Aware Notification Batching for SC_LogReader

## Context

The sc_log_reader skill sends game event notifications to the wingman via a debounce-style batch (4s sliding window). Currently it has zero awareness of whether the wingman is speaking — if a notification fires mid-speech, it collides/interrupts.

**Goal:** When the wingman is speaking, hold notifications and keep accumulating events. When playback finishes, flush the accumulated batch as one grouped message. Safety timeout: 30 seconds max hold.

**Critical discovery:** The PubSub `"finished"` event does NOT fire for all playback paths. `play_with_effects` natural finish only puts the WingmanCore callback in the event queue without publishing to PubSub. Only `stream_with_effects` and `stop_playback()` reliably publish `"finished"`. So we need a **hybrid** approach: PubSub "finished" as a fast-wake signal + polling `is_playing` every ~1s as fallback.

## File to modify

`skills/sc_log_reader/main.py` (+ version bump, Devlog update)

## Changes

### 1. Import — add `Event` (line 17)

```python
from threading import Event, Lock, Thread, Timer
```

### 2. New state variables in `__init__` (after line 184)

```python
# Speech-aware hold: defer notifications while wingman is speaking
self._held_for_playback = False
self._playback_finished_event = Event()
self._hold_timeout_seconds = 30.0
```

- `_held_for_playback` — True while batch is deferred waiting for playback to finish
- `_playback_finished_event` — threading.Event bridging async PubSub to sync hold thread
- `_hold_timeout_seconds` — 30s safety cap

### 3. Subscribe in `prepare()` (before the log-path check, ~line 223)

```python
self._subscribe_playback_events()
```

Subscription is independent of log file existence — playback awareness applies to the full lifecycle.

### 4. Modify `_add_to_batch` (~line 719) — skip timer when held

When `_held_for_playback` is True, just append the event and return — don't reset the timer. The hold mechanism will flush when ready, naturally grouping all accumulated events.

```python
def _add_to_batch(self, event: DerivedEvent) -> None:
    with self._batch_lock:
        self._notification_batch.append(event)
        if self._held_for_playback:
            return                          # <-- NEW: accumulate, don't reset timer
        if self._batch_timer is not None:
            self._batch_timer.cancel()
        self._batch_timer = Timer(self._batch_delay_seconds, self._flush_batch)
        self._batch_timer.start()
```

### 5. Modify `_flush_batch_inner` (~line 752) — check playback before flush

Insert after the `_notifications_paused` check, before the batch drain:

```python
# Speech-aware hold: defer if wingman is speaking
if (
    self.wingman
    and self.wingman.audio_player.is_playing
    and not self._held_for_playback
):
    self._enter_hold_state()
    return
```

The `not self._held_for_playback` guard prevents re-entering hold when the safety timeout fires flush again.

Also add `self._held_for_playback = False` in the batch-drain lock block (alongside existing `self._batch_timer = None`) to clear hold state on successful delivery.

### 6. Cleanup in `unload()` (~line 469) — before existing batch timer cancel

```python
self._unsubscribe_playback_events()
self._held_for_playback = False
self._playback_finished_event.set()  # unblock any waiting thread
```

### 7. Five new methods

**`_subscribe_playback_events`** — Subscribe to PubSub "finished" in `prepare()`.

**`_unsubscribe_playback_events`** — Unsubscribe in `unload()`, wrapped in try/except ValueError.

**`_on_playback_finished(wingman_name)`** — Async PubSub callback. Filters on own wingman name. If held, sets `_playback_finished_event`.

**`_enter_hold_state`** — Sets `_held_for_playback = True` under lock, clears Event, spawns daemon thread running `_wait_for_playback`.

**`_wait_for_playback`** — Hybrid wait loop:
```
deadline = now + 30s
while held:
    remaining = deadline - now
    if remaining <= 0: break (timeout)
    event.wait(timeout=min(1.0, remaining))  # wakes on PubSub or every 1s
    if not is_playing: break                 # poll fallback
flush_batch()
```

This handles all playback paths:
- **PubSub fires** → Event set, wait returns immediately, `is_playing` is False → flush
- **PubSub doesn't fire** (play_with_effects natural finish) → `is_playing` becomes False, detected within 1s → flush
- **Nothing happens** → 30s timeout → flush anyway

### 8. Version bump

`0.1.19` → `0.1.20`

## Thread Safety

| Thread | What it does | Protection |
|--------|-------------|------------|
| Parser callback | `_add_to_batch` — reads `_held_for_playback`, writes batch | `_batch_lock` |
| Timer (debounce) | `_flush_batch_inner` — reads `is_playing`, enters hold | `_batch_lock` for batch ops |
| Hold-wait thread | `_wait_for_playback` — Event.wait + poll, then flush | Event is thread-safe; flush acquires `_batch_lock` |
| Main event loop | `_on_playback_finished` — reads held flag, Event.set | Event.set is thread-safe |
| Unload | Clears held, sets Event, unsubscribes | Runs once at teardown |

## Edge Cases

- **Playback finishes before hold thread starts**: Event already set → wait returns immediately
- **Events arrive during hold**: Appended to batch, no timer reset → included in grouped flush
- **Skill unloads while held**: Event.set unblocks thread, held=False makes thread exit cleanly
- **Another wingman speaking**: PubSub callback filters on wingman name; polling `is_playing` is global but conservative (waits for any playback to finish, which is actually desirable)
- **Own response playback**: After we flush, wingman speaks the response → `is_playing` True → next batch timer naturally enters hold → events group during response speech too

## Verification

1. Run existing test suite: `python -m pytest tests/sc_log_reader/` (499 tests)
2. Manual test: trigger rapid game events while wingman is speaking — notifications should queue and deliver as one grouped message after speech ends
3. Manual test: trigger events while wingman is idle — should deliver immediately (no behavior change)
4. Verify 30s timeout: if playback gets stuck, notifications still deliver
