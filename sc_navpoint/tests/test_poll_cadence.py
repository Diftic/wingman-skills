"""Capture fresh frames sequentially with no fixed FPS delay or queued ticks."""
import asyncio
from types import SimpleNamespace

import pytest
from _stubs import install_runtime_stubs

install_runtime_stubs()
import main


@pytest.mark.parametrize("value, expected", [
    (None, 0.), (.25, 0.), (.5, 0.), (1, 0.), (5, 0.),
    ("0.25", 0.), (-1, 0.), (100, 0.), ("bad", 0.),
    (float("nan"), 0.), (float("inf"), 0.),
])
def test_legacy_poll_interval_cannot_reintroduce_a_rate_cap(value, expected):
    skill = main.SC_NavPoint.__new__(main.SC_NavPoint)
    skill.retrieve_custom_property_value = lambda *args: value
    assert skill._get_poll_interval() == expected


@pytest.mark.parametrize("durations, expected", [
    ([.15, .70, .12], [0., .15, .85]),
    ([.70, .70, .70], [0., .70, 1.40]),
])
def test_capture_time_counts_toward_period_without_catchup_bursts(monkeypatch, durations, expected):
    clock = [0.]
    starts = []
    skill = main.SC_NavPoint.__new__(main.SC_NavPoint)
    skill._active_target = object()
    skill._get_arrival_alert_m = skill._get_arrival_stop_m = lambda: 0.
    skill._poll_stopping = lambda: False
    skill._poll_trace = lambda *args, **kwargs: None
    skill._sync_ring = lambda: None
    skill._scanner = SimpleNamespace(last_reject_reason=None)

    async def sleep(delay):
        clock[0] += delay

    async def capture():
        starts.append(clock[0])
        clock[0] += durations[len(starts)-1]
        if len(starts) == len(durations):
            skill._active_target = None
        return None

    skill._capture_position = capture
    monkeypatch.setattr(main.time, "monotonic", lambda: clock[0])
    monkeypatch.setattr(main.asyncio, "sleep", sleep)
    asyncio.run(skill._nav_polling_loop(.25))
    assert starts == pytest.approx(expected)


@pytest.mark.parametrize('kind, delay', [
    (main.overlay_fields.KIND_NO_GRAB, .25),
    (main.overlay_fields.KIND_NO_READER, .25),
    (main.overlay_fields.KIND_GATE, 0.),
])
def test_wait_only_when_capture_is_unavailable(monkeypatch, kind, delay):
    skill = main.SC_NavPoint.__new__(main.SC_NavPoint)
    skill._active_target = object()
    skill._get_arrival_alert_m = skill._get_arrival_stop_m = lambda: 0.
    skill._poll_stopping = lambda: False
    skill._poll_trace = lambda *args, **kwargs: None
    skill._sync_ring = lambda: None
    skill._scanner = SimpleNamespace(last_reject_reason=None)
    skill._last_outcome = SimpleNamespace(kind=kind)
    waits = []
    async def sleep(value):
        waits.append(value)
    async def capture():
        skill._active_target = None
        return None
    skill._capture_position = capture
    monkeypatch.setattr(main.asyncio, 'sleep', sleep)
    asyncio.run(skill._nav_polling_loop(1.))
    assert sum(waits) == pytest.approx(delay)


def test_unexpected_capture_error_still_refreshes_held_display_age(monkeypatch):
    skill = main.SC_NavPoint.__new__(main.SC_NavPoint)
    skill._active_target = object()
    skill._get_arrival_alert_m = skill._get_arrival_stop_m = lambda: 0.
    skill._poll_stopping = lambda: False
    skill._poll_trace = lambda *args, **kwargs: None
    syncs = []
    skill._sync_ring = lambda: syncs.append(skill._last_ring_state)
    async def sleep(value):
        pass
    async def capture():
        skill._active_target = None
        raise RuntimeError('unexpected capture failure')
    skill._capture_position = capture
    monkeypatch.setattr(main.asyncio, 'sleep', sleep)
    asyncio.run(skill._nav_polling_loop(1.))
    assert syncs == [main.overlay_fields.RING_NO_SIGNAL]
