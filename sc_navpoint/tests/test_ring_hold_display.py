"""Display retention never upgrades an old direction into a fresh fix."""
import numpy as np
import ring_overlay as ro
import navigation


def test_failure_keeps_dot_and_original_age_until_new_valid_direction(monkeypatch):
    monkeypatch.setattr(ro.time, 'time', lambda: 110.0)
    overlay = ro.RingOverlay()
    overlay.set_state(True, (12.0, -3.0), '250 m', hold_key=('ita', 1), captured_at=100.0)
    angles, message = overlay.set_state(True, None, 'READING', hold_key=('ita', 1), read_failed=True)
    assert angles == (12.0, -3.0)
    assert 'HELD 10s' in message
    assert not overlay._error  # One missed update only holds the display.
    # A new position lacking calibration must not overwrite the last valid dot.
    angles, message = overlay.set_state(True, None, '249 m', hold_key=('ita', 1), captured_at=109.0)
    assert angles == (12.0, -3.0) and 'HELD 10s' in message
    angles, _ = overlay.set_state(True, (5.0, 2.0), '240 m', hold_key=('ita', 1), captured_at=110.0)
    assert angles == (5.0, 2.0) and not overlay._error


def test_refused_sample_cannot_replace_cached_direction(monkeypatch):
    monkeypatch.setattr(ro.time, 'time', lambda: 103.0)
    overlay = ro.RingOverlay()
    overlay.set_state(True, (12.0, 3.0), hold_key=('ita', 1), captured_at=100.0)
    angles, message = overlay.set_state(True, (99.0, 99.0), hold_key=('ita', 1), read_failed=True, captured_at=103.0)
    assert angles == (12.0, 3.0) and 'HELD 3s' in message


def test_changed_target_or_frame_cannot_inherit_dot():
    overlay = ro.RingOverlay()
    overlay.set_state(True, (12.0, 3.0), hold_key=('ita', 1), captured_at=100.0)
    angles, _ = overlay.set_state(True, None, hold_key=('ita', 2))
    assert angles is None
    overlay.set_state(True, (8.0, 2.0), hold_key=('ita', 2), captured_at=101.0)
    angles, _ = overlay.set_state(True, None, hold_key=('bloom', 2))
    assert angles is None


def test_clear_or_disabled_hold_discards_cached_dot():
    overlay = ro.RingOverlay()
    overlay.set_state(True, (12.0, 3.0), hold_key=('ita', 1), captured_at=100.0)
    overlay.clear()
    assert overlay.set_state(True, None, hold_key=('ita', 1))[0] is None
    overlay.set_state(True, (12.0, 3.0), hold_key=('ita', 1), captured_at=100.0)
    assert overlay.set_state(True, None)[0] is None
    assert overlay.set_state(True, None, hold_key=('ita', 1))[0] is None


def test_error_renders_at_top_without_removing_dot():
    renderer = ro.RingRenderer(220)
    base = np.frombuffer(renderer.frame((12.0, 3.0)), np.uint8).reshape(220, 220, 4)
    error = np.frombuffer(renderer.frame((12.0, 3.0), error_alpha=1.0), np.uint8).reshape(220, 220, 4)
    changed = np.any(base != error, axis=2)
    assert changed[:45].any()
    assert not changed[45:].any()


def test_distance_has_fixed_pixels_independent_of_status_and_fade():
    renderer = ro.RingRenderer(220)
    def pixels(**kw):
        return np.frombuffer(renderer.frame((0, 0), **kw), np.uint8).reshape(220, 220, 4)
    plain = pixels()
    distance = pixels(distance='2.2 km')
    notice = pixels(distance='2.2 km', message='SLOW DOWN')
    hidden_notice = pixels(distance='2.2 km', message='SLOW DOWN', message_alpha=0)
    distance_rows = np.any(distance != plain, axis=(1, 2))
    notice_rows = np.any(notice != distance, axis=(1, 2))
    assert distance_rows.any() and notice_rows.any()
    assert np.where(distance_rows)[0].max() < np.where(notice_rows)[0].min()
    assert np.array_equal(notice[distance_rows], distance[distance_rows])
    assert np.array_equal(hidden_notice, distance)
    assert np.array_equal(notice[:150], plain[:150])


def test_held_distance_is_scoped_to_last_valid_dot_and_target(monkeypatch):
    monkeypatch.setattr(ro.time, 'time', lambda: 110)
    overlay = ro.RingOverlay()
    overlay.set_state(True, (1, 2), 'SLOW DOWN', distance='2.2 km',
                      hold_key=('ita', 1), captured_at=100)
    overlay.set_state(True, None, distance='2.1 km', hold_key=('ita', 1),
                      read_failed=True, captured_at=109)
    assert overlay._distance == '2.2 km'
    assert overlay._message == 'HELD 10s'
    overlay.set_state(True, None, hold_key=('ita', 2))
    assert overlay._distance == ''


def test_error_requires_eight_consecutive_failures_and_success_resets_count():
    overlay = ro.RingOverlay()
    def good():
        overlay.set_state(True, (1, 2), hold_key=('ita', 1), captured_at=100)
    def bad(key=('ita', 1)):
        overlay.set_state(True, None, hold_key=key, read_failed=True)
    good()
    for _ in range(7):
        bad()
        assert not overlay._error
        assert overlay._target == (1, 2)
    good()
    for _ in range(7):
        bad()
        assert not overlay._error
    bad()
    assert overlay._error
    good()
    assert not overlay._error
    for _ in range(8):
        bad()
    bad(('ita', 2))
    assert not overlay._error and overlay._target is None
    for _ in range(7):
        bad(('ita', 2))
    assert overlay._error
    overlay.clear()
    bad(('ita', 2))
    assert not overlay._error


def test_missing_calibration_uses_same_eight_failure_threshold():
    overlay = ro.RingOverlay()
    for i in range(8):
        overlay.set_state(True, None, hold_key=('ita', 1), captured_at=100+i,
                          distance='2.2 km')
        assert overlay._error == (i == 7)
        assert overlay._distance == '2.2 km'


def test_hold_identity_requires_matching_local_frame_and_specific_target():
    pos = dict(active_frame='planet', frame_id='ita', planet_id='ita', body='Ita', system='Stanton', x=0, y=0, z=0)
    target = dict(id=1, frame='local', frame_id='ita', body='Ita', system='Stanton', x=1, y=2, z=3)
    key = navigation.ring_hold_key(pos, target)
    assert key is not None
    assert navigation.ring_hold_key(pos, dict(target, id=2)) != key
    assert navigation.ring_hold_key(pos, dict(target, x=4)) != key
    assert navigation.ring_hold_key(pos, dict(target, frame_id='bloom')) is None
    assert navigation.ring_hold_key(dict(pos, active_frame='space'), target) is None
    assert navigation.ring_hold_key(pos, None) is None


def test_arrived_or_invalid_position_cannot_retain_old_direction():
    pos = dict(active_frame='planet', frame_id='ita', body='Ita', x=1, y=2, z=3)
    target = dict(id=1, frame='local', frame_id='ita', body='Ita', x=1, y=2, z=3)
    assert navigation.ring_hold_key(pos, target) is None
    assert navigation.ring_hold_key(dict(pos, x=float('nan')), target) is None
