"""Space uses the surface arrival policy, measured from saved Root anchors."""
import asyncio
import copy
import time

import pytest
from test_open_space_navigation import saved_skill
from test_arrival import _bare_skill, _ScriptedCapture, _arrived, _approaching


def run_space(tmp_path, distances, change=None, stop_m=250):
    saved, position, _ = saved_skill(tmp_path)
    skill = _bare_skill(saved._db)
    skill._active_target = saved._active_target
    skill._get_arrival_stop_m = lambda: stop_m
    captures = []
    for distance in distances:
        if distance is None:
            captures.append(None)
            continue
        pos = copy.deepcopy(position)
        for anchor in ('root', 'solar'):
            pos['coordinate_stack'][anchor]['y_m'] = -9999999000. - distance
        pos['captured_at'] = time.time()
        pos['camdir'] = None  # Arrival depends on position, not direction.
        if change == 'coarse':pos['precision'] = dict(mode='cruise', target_id=skill._active_target.id)
        if change == 'planet':pos.update(active_frame='planet', body='Ita')
        if change == 'session':pos['coordinate_stack']['solar']['raw_name'] = 'SolarSystem_other'
        if change == 'stale':pos['captured_at'] -= 31
        if change == 'bad_root':pos['coordinate_stack']['root']['x_m'] += 100000
        captures.append(pos)
    skill._capture_position = _ScriptedCapture(captures)
    asyncio.run(skill._nav_polling_loop(0))
    return skill


@pytest.mark.parametrize('distances,arrives', [
    ([250., 250.], True), ([0.,0.], True), ([249.], False),
    ([250.1,250.1], False), ([200.,500.,200.], False),
    ([200.,None,200.], True),
])
def test_space_uses_two_valid_in_range_readings(tmp_path, distances, arrives):
    skill=run_space(tmp_path, distances)
    assert len(_arrived(skill)) == int(arrives)
    assert (skill._active_target is None) == arrives
    if arrives:
        skill._stop_nav_polling.assert_called_once()
        assert skill._ui_server.set_active_target_calls[-1] is None
        assert len(skill._db.get_navpoints()) == 1
        assert skill._audio_calls[-1][1] == ('Arrived.',)


@pytest.mark.parametrize('change',['coarse','planet','session','stale','bad_root'])
def test_unusable_space_positions_never_announce_arrival(tmp_path,change):
    skill=run_space(tmp_path,[200.,200.],change)
    assert not _arrived(skill)
    assert skill._active_target is not None


def test_space_respects_disabled_arrival_setting(tmp_path):
    assert not _arrived(run_space(tmp_path,[0.,0.],stop_m=0))


def test_space_approach_message_remains_short_and_once(tmp_path):
    skill=run_space(tmp_path,[500.,400.,200.,200.])
    assert len(_approaching(skill)) == 1
    assert _approaching(skill)[0][0] == '[NavPoint] Approaching: 500 meters.'
    assert len(_arrived(skill)) == 1
