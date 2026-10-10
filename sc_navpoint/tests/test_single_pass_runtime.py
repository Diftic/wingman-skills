"""A failed image must not invoke another OCR path or rejuvenate an old fix."""
from test_capture_retry import _skill, _PAYLOAD
from test_brightness_capture_join import _RecoveryReader
from test_capture_outcome import _skill as outcome_skill


def test_legacy_attempt_count_cannot_retry_a_failed_capture(tmp_path, monkeypatch):
    skill, screen, sleeps = _skill(tmp_path, monkeypatch, [None, _PAYLOAD])
    assert skill._capture_position_local(attempts=5) is None
    assert screen.grabs == 1
    assert sleeps == []


def test_failed_frame_never_calls_recovery_model(tmp_path, monkeypatch):
    reader = _RecoveryReader([])
    skill = outcome_skill(tmp_path, monkeypatch, reader=reader, usable=(False, 'clipped'))
    assert skill._capture_position_local() is None
    assert reader.retries == 0


def test_stamp_precedes_decode(tmp_path, monkeypatch):
    import main
    skill, screen, sleeps = _skill(tmp_path, monkeypatch, [_PAYLOAD])
    clock = [100.0]
    monkeypatch.setattr(main.time, 'time', lambda: clock[0])
    read = skill._local_reader().read
    class SlowReader:
        def read(self, frame, count):
            clock[0] += 5.0
            return read(frame, count)
    skill._local_reader = lambda: SlowReader()
    position = skill._capture_position_local()
    assert position['captured_at'] == 100.0


def test_failed_read_keeps_last_valid_ring_with_age():
    import navigation
    from test_ring_message import _POSITION, _TARGET
    expected, _ = navigation.ring_status(_POSITION, _TARGET, 2.0, '')
    actual, message = navigation.ring_status(_POSITION, _TARGET, 2.0, 'GLARE')
    assert actual == expected
    assert actual is not None
    assert message == 'HELD 2s'


def test_reader_specific_gate_cannot_fall_through_to_looser_parser(tmp_path, monkeypatch):
    from test_capture_outcome import _FakeReader
    reader = _FakeReader([{'kind':'zone','trusted':True,'text':'Zone: Root'}])
    reader.capture_payload = lambda rows: (None, 'missing_or_ambiguous_facing')
    skill = outcome_skill(tmp_path, monkeypatch, reader=reader, payload={'local_frame':False})
    assert skill._capture_position_local() is None


def test_foreground_change_discards_the_image_before_decoding(tmp_path, monkeypatch):
    from test_capture_outcome import _FakeReader
    reader = _FakeReader([], exc=AssertionError('must not decode lost foreground'))
    reader.capture_still_valid = lambda: False
    skill = outcome_skill(tmp_path, monkeypatch, reader=reader)
    assert skill._capture_position_local() is None
    assert skill._last_outcome.kind == 'no_grab'
