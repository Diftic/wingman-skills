"""Activation can warm the same reader without an active navigation target."""
import asyncio
import threading
from types import SimpleNamespace
from unittest.mock import MagicMock

from _stubs import install_runtime_stubs
install_runtime_stubs()
import main


def bare():
    skill = main.SC_NavPoint.__new__(main.SC_NavPoint)
    skill._active_target = None
    skill._capture_lock = threading.Lock()
    skill._poll_trace = MagicMock()
    return skill


def test_background_survives_activation_loop_and_stops_cleanly():
    skill = bare()
    captured = threading.Event()
    def capture(*args, **kwargs):
        assert kwargs['calibration_only']
        captured.set()
    skill._capture_position_local = capture
    async def activate():
        skill._start_background_calibration()
    asyncio.run(activate())
    thread = skill._calibration_thread
    try:
        assert captured.wait(2)
        skill._start_background_calibration()
        assert skill._calibration_thread is thread
    finally:
        skill._stop_background_calibration()
    assert not thread.is_alive()


def test_idle_capture_is_skipped_under_lock_when_navigation_or_stop_wins():
    skill = bare()
    skill._local_reader = MagicMock(side_effect=AssertionError('must not capture'))
    skill._active_target = object()
    assert skill._capture_position_local(calibration_only=True) is None
    skill._active_target = None
    stop = threading.Event()
    stop.set()
    assert skill._capture_position_local(calibration_only=True, stop_event=stop) is None
    skill._local_reader.assert_not_called()


def test_idle_capture_updates_shared_tracker_without_publishing_navigation_state():
    skill = bare()
    tracker = object()
    reader = SimpleNamespace(planet_rotation_tracker=tracker)
    skill._local_reader = lambda: reader
    skill._scanner = object()
    skill._last_outcome = sentinel = object()
    skill._last_ring_state = 'held'
    skill._reader_state = 'old reader state'
    position = dict(planet_rotation=dict(valid=True))
    def attempt(actual_reader, *_):
        assert actual_reader.planet_rotation_tracker is tracker
        assert main._FULL_PRECISION.get()
        skill._reader_state = 'new state'
        return SimpleNamespace(position=position, ring_state='')
    skill._capture_attempt = attempt
    with main._full_precision_capture():
        assert skill._capture_position_local(calibration_only=True) is position
    assert skill._last_outcome is sentinel
    assert skill._last_ring_state == 'held'
    assert skill._reader_state == 'old reader state'


def test_navigation_stop_does_not_stop_background_calibration():
    from test_arrival import _bare_skill
    skill = _bare_skill()
    skill._calibration_stop = threading.Event()
    skill.stop_navigation()
    assert not skill._calibration_stop.is_set()


def test_unload_stops_background_calibration(monkeypatch):
    skill = bare()
    skill._stop_nav_polling = MagicMock()
    skill._stop_background_calibration = MagicMock()
    skill._ring_overlay = skill._ui_window = skill._ui_server = None
    async def unload(self):
        pass
    monkeypatch.setattr(main.Skill, 'unload', unload, raising=False)
    asyncio.run(skill.unload())
    skill._stop_background_calibration.assert_called_once()


def test_target_selection_reuses_rotation_learned_without_a_target():
    import active_frame
    from frame_reader import FrameAwareReader
    from planet_rotation import PlanetRotationTracker
    from test_planet_rotation import samples
    reader = FrameAwareReader.__new__(FrameAwareReader)
    reader.planet_rotation_tracker = PlanetRotationTracker()
    def read_pair(sample, target=None):
        t, x, y, sx, sy = sample
        solar = f'{sx / 1000:.7f}km {sy / 1000:.7f}km 0m'
        text = ['CamDir: 0 0 0 FOV: 44',
                f'Zone: OOC_Stanton_1d_Ita Pos: {x / 1000:.7f}km {y / 1000:.7f}km 0m',
                'Zone: SolarSystem_1 Pos: ' + solar, 'Zone: Root Pos: ' + solar]
        identity, reason = active_frame.resolve_zone_identity(text)
        assert identity, reason
        rows = [dict(raw_model_text=line) for line in text]
        rows[0].update(frame_identity=identity, captured_at=t)
        return reader.capture_for_target(rows, target, full_precision=True)[0]
    for sample in samples():
        assert read_pair(sample) is not None
        worker = reader.planet_rotation_tracker.worker
        if worker:
            worker.join(timeout=2)
            assert not worker.is_alive()
    before = len(reader.planet_rotation_tracker.samples)
    final = samples()[-1]
    position = read_pair(final, dict(id=47, frame='local', frame_id='ooc_stanton_1d_ita',
                                    body='Ita', x=final[1]+100, y=final[2], z=0))
    assert position['planet_rotation']['valid']
    assert len(reader.planet_rotation_tracker.samples) == before
