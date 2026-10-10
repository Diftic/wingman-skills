"""Distances sent to speech spell out the decimal separator and unit."""
import asyncio
from types import SimpleNamespace

import pytest
import navigation
from test_arrival import _bare_skill, _Target


@pytest.mark.parametrize('km, expected', [
    (4.5, '4 point 5 kilometers'),
    (.098, '98 meters'),
    (.001, '1 meter'),
    (1.0, '1 kilometer'),
    (0, '0 meters'),
    (5000, '5 megameters'),
    (1250000, '1 point 2 5 gigameters'),
])
def test_spoken_distance(km, expected):
    assert navigation.format_spoken_distance(km) == expected


def test_guidance_uses_spoken_distance_without_changing_visual_format():
    skill = _bare_skill()
    bearing = dict(distance_km=4.5, turn_instruction='Ahead', elevation_instruction='Level')
    assert skill._build_guidance(None, bearing) == '4 point 5 kilometers | Ahead'
    import coordinate_stack as cs
    decision = SimpleNamespace(distance_m=4500, mode=cs.MODE_LOCAL_TRACKING)
    assert skill._build_stack_guidance(SimpleNamespace(name='Camp'), decision) == 'Camp is 4 point 5 kilometers away.'
    assert navigation.format_distance(4.5) == '4.5 km'


def test_approach_sends_point_and_full_unit_to_tts():
    skill = _bare_skill()
    target = _Target(1, 'Camp', 'Daymar', 0, 0, 0)
    asyncio.run(skill._announce_arrival(target, 4500, 5000, 250))
    # Run the speech helper queued by the skill, as Wingman's scheduler would.
    assert len(skill._audio_calls) == 1
    callback, args = skill._audio_calls[0]
    asyncio.run(callback(*args))
    assert skill.wingman.speech_calls == [('Approaching: 4 point 5 kilometers.', False)]
