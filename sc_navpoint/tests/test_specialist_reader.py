"""Portable specialist decoder contracts, independent of game or model weights."""
import numpy as np
import pytest

from specialist_reader import decode_ascii, prepare_band


def probabilities(tokens, classes=4):
    values = np.zeros((1,len(tokens),classes),dtype=np.float32)
    for i,token in enumerate(tokens):values[0,i,token]=1
    return values


def test_ctc_keeps_repeated_digit_only_when_separated_by_blank():
    text, score = decode_ascii(probabilities([1,1,0,1,2,2]), ['blank','1','2',' '])
    assert text == '112'
    assert score == 1.0


def test_large_spatial_gap_preserves_missing_word_separator():
    text, score = decode_ascii(probabilities([1]+[0]*6+[2]), ['blank','A','B',' '])
    assert text == 'A B'


def test_explicit_space_is_a_word_separator():
    text, _ = decode_ascii(probabilities([1,3,2]), ['blank','A','B',' '])
    assert text == 'A B'


def test_bad_model_output_is_refused():
    with pytest.raises(ValueError):
        decode_ascii(np.full((1,3,4),np.nan), ['blank','A','B',' '])


def test_preprocessing_matches_training_shape_and_normalization():
    import cv2
    band=np.arange(13*675*3,dtype=np.uint8).reshape(13,675,3)
    result=prepare_band(band)
    expected=cv2.resize(band,(2492,48)).astype('float32').transpose(2,0,1)/255
    expected=(expected-.5)/.5
    assert result.shape==(1,3,48,2492)
    np.testing.assert_array_equal(result[0],expected)


def test_malformed_nested_zone_cannot_disappear_from_a_saved_stack():
    from learned_fields import parse_proposal
    proposal = parse_proposal([
        'CamDir: -15 0 164 FOV: 55',
        'Zone: glaciemring_segment_ tn-003 Pos: 7780.45m -5573.29m -347.23m',
        'Zone: SolarSystem_795179149930 Pos: 14985413.4655km -674246.6844km -347.23m',
        'Zone: Root Pos: 14985413.4655km -674246.6844km -347.23m',
    ])
    assert proposal['complete'] is False
    assert proposal['reason'] == 'malformed_coordinate_row'


def test_valid_nested_stack_retains_every_row_and_camera():
    from learned_fields import parse_proposal
    proposal = parse_proposal([
        'CamDir: -15 0 164 FOV: 55',
        'Zone: glaciemring_segment_wtn-003 Pos: 7780.45m -5573.29m -347.23m',
        'Zone: SolarSystem_795179149930 Pos: 14985413.4655km -674246.6844km -347.23m',
        'Zone: Root Pos: 14985413.4655km -674246.6844km -347.23m',
    ])
    assert proposal['complete'] is True
    stack = proposal['position']['coordinate_stack']
    assert len(stack['nested']) == 1
    assert stack['nested'][0]['raw_name'] == 'glaciemring_segment_wtn-003'
    assert proposal['position']['camdir'] == [-15., 0., 164.]


def test_v8_reader_is_cached_across_capture_outcomes(monkeypatch):
    from _stubs import install_runtime_stubs
    install_runtime_stubs()
    import main
    import frame_reader
    skill = main.SC_NavPoint.__new__(main.SC_NavPoint)
    candidate = object()
    loads = []
    def load():
        loads.append('v8')
        return candidate
    monkeypatch.setattr(frame_reader, 'FrameAwareReader', load)
    assert skill._local_reader() is candidate
    skill._last_outcome = None
    assert skill._local_reader() is candidate
    assert loads == ['v8']


def test_missing_specialist_is_not_replaced_by_a_different_reader(monkeypatch):
    from _stubs import install_runtime_stubs
    install_runtime_stubs()
    import main
    import frame_reader
    skill = main.SC_NavPoint.__new__(main.SC_NavPoint)
    skill.retrieve_custom_property_value = lambda *args: True
    calls = []
    def unavailable():
        calls.append('load')
        raise ImportError('missing dependency')
    monkeypatch.setattr(frame_reader, 'FrameAwareReader', unavailable)
    monkeypatch.setattr(main.overlay_reader, 'OverlayReader', lambda *args: pytest.fail('fallback'))
    assert skill._local_reader() is None
    assert skill._local_reader() is None
    assert calls == ['load']
