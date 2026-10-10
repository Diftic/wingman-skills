import asyncio
import json
import time
import math
import pytest
from _stubs import install_runtime_stubs
install_runtime_stubs()
import main
import coordinate_stack as cs
import navigation
from scanner import NavPointScanner
import active_frame as af
from test_active_frame import planet_rows,metadata
from test_coordinate_stack_navigation import _skill,_mark,_capture_from,KEEGER_ROWS

def planet_position():
    text=planet_rows();identity,_=af.resolve_identity(text,metadata())
    payload,_=af.build_payload(text,identity)
    position=NavPointScanner().parse_payload(payload)
    # Synthetic calibrated frame: 90 degrees reproduces this fixture's basis.
    position['planet_rotation']=dict(frame_id=position['frame_id'],angle=math.pi/2,valid=True)
    return position


def test_runtime_ring_retains_last_calibrated_dot_on_partial_read(tmp_path):
    from ring_overlay import RingOverlay
    pos = planet_position()
    skill = _skill(tmp_path, pos)
    _mark(skill, 'Held display camp')
    target = skill._db.find_navpoint_by_name('Held display camp')
    skill._active_target = target
    skill._ring_overlay = RingOverlay()
    del skill._sync_ring  # Exercise the real runtime path, not the helper's no-op.
    skill._last_ring_state = ''
    pos = dict(pos, x=pos['x'] + 100, captured_at=time.time())
    skill._last_position = pos
    skill._sync_ring()
    before = skill._ring_overlay._target
    assert before is not None
    assert skill._ring_overlay._distance == '100 m'
    uncalibrated = dict(pos, x=pos['x'] + 10, captured_at=time.time())
    uncalibrated.pop('planet_rotation')
    skill._last_position = uncalibrated
    skill._sync_ring()
    assert skill._ring_overlay._target == before
    assert not skill._ring_overlay._error
    assert 'HELD' in skill._ring_overlay._message
    skill._active_target = None
    skill._sync_ring()
    assert skill._ring_overlay._target is None
    assert skill._ring_overlay._distance == ''


def test_runtime_distance_survives_slowdown_and_missing_calibration(tmp_path):
    from ring_overlay import RingOverlay
    pos = planet_position()
    skill = _skill(tmp_path, pos)
    _mark(skill, 'Distance camp')
    target = skill._db.find_navpoint_by_name('Distance camp')
    skill._active_target = target
    skill._ring_overlay = RingOverlay()
    del skill._sync_ring
    skill._last_ring_state = ''
    pos = dict(pos, x=pos['x'] + 2200, captured_at=time.time(),
               precision=dict(mode='approach', target_id=target.id, slow_down_advisory=True))
    skill._last_position = pos
    skill._sync_ring()
    assert skill._ring_overlay._distance == '2.2 km'
    assert skill._ring_overlay._message == 'SLOW DOWN'
    pos['precision']['slow_down_advisory'] = False
    skill._sync_ring()
    assert skill._ring_overlay._distance == '2.2 km'
    assert skill._ring_overlay._message == ''
    skill._ring_overlay.clear()
    pos.pop('planet_rotation')
    skill._sync_ring()
    assert skill._ring_overlay._target is None
    assert skill._ring_overlay._distance == '2.2 km'


def test_distance_rejects_incompatible_or_stale_coordinates():
    pos = planet_position()
    target = dict(id=1, frame='local', frame_id='pyro3', body='pyro3',
                  x=pos['x'] + 300, y=pos['y'] + 400, z=pos['z'])
    assert navigation.ring_distance(pos, target, 0) == '500 m'
    assert navigation.ring_distance(pos, dict(target, frame_id='ita'), 0) == ''
    assert navigation.ring_distance(pos, target, 31) == ''
    assert navigation.ring_distance(dict(pos, x=float('nan')), target, 0) == ''
    assert navigation.ring_distance(pos, None, 0) == ''
    pos['precision'].update(mode='cruise', target_id=2)
    assert navigation.ring_distance(pos, target, 0) == ''

def test_mark_while_navigating_forces_full_precision_and_stores_no_solar(tmp_path):
    position=planet_position();skill=_skill(tmp_path,position)
    async def capture(attempts=1):
        assert main._FULL_PRECISION.get()
        return position
    skill._capture_position=capture
    result=_mark(skill,'Planet camp')
    assert result['success']
    saved=skill._db.find_navpoint_by_name('Planet camp')
    assert saved.frame=='local' and saved.frame_id=='pyro3'
    assert saved.body=='pyro3' and saved.x==330742.1
    assert saved.coordinate_stack is None
    assert saved.root_x is None and saved.root_y is None and saved.root_z is None

def test_coarse_navigation_position_can_never_be_saved(tmp_path):
    position=planet_position();position['precision']['mode']='cruise'
    skill=_skill(tmp_path,position)
    assert 'error' in _mark(skill,'Do not save')
    assert skill._db.find_navpoint_by_name('Do not save') is None

def test_planet_frame_wins_over_legacy_stack_when_saving(tmp_path):
    position=planet_position();position['coordinate_stack']=_capture_from(KEEGER_ROWS)['coordinate_stack']
    skill=_skill(tmp_path,position)
    assert _mark(skill,'Local only')['success']
    saved=skill._db.find_navpoint_by_name('Local only')
    assert saved.frame=='local' and saved.coordinate_stack is None and saved.root_x is None

def test_stack_target_cannot_use_solar_when_current_frame_is_planet(tmp_path):
    space=_capture_from(KEEGER_ROWS);skill=_skill(tmp_path,space)
    _mark(skill,'Space target');target=skill._db.find_navpoint_by_name('Space target')
    planet=planet_position();planet['coordinate_stack']=space['coordinate_stack']
    assert skill._stack_route(target,planet).mode==cs.MODE_REFUSED
    assert navigation.ring_deflection(planet,dict(frame='stack',coordinate_stack=target.coordinate_stack),0,allow_uncalibrated_space=True) is None

def test_planet_ring_uses_camera_pitch_and_matched_planet_identity():
    pos=planet_position();target=dict(id=1,frame='local',frame_id='pyro3',body='pyro3',system='Pyro',x=pos['x']+500,y=pos['y']+300,z=pos['z']+200)
    expected=navigation.relative_deflection(pos['camdir'],(pos['x'],pos['y'],pos['z']),(target['x'],target['y'],target['z']))
    assert navigation.ring_deflection(pos,target,0)==pytest.approx((expected['yaw_offset_deg'],expected['pitch_offset_deg']))
    target['frame_id']='another_planet'
    assert navigation.ring_deflection(pos,target,0) is None

def test_slowdown_advisory_once_per_target_and_never_for_held_or_other_target(tmp_path,monkeypatch):
    pos=planet_position();skill=_skill(tmp_path,pos);_mark(skill,'Camp')
    target=skill._db.find_navpoint_by_name('Camp');skill._active_target=target
    messages=[]
    async def record(message,**kwargs):messages.append(message)
    monkeypatch.setattr(skill.printr,'print_async',record)
    pos.update(captured_at=time.time(),precision=dict(mode='approach',target_id=target.id,slow_down_advisory=True))
    asyncio.run(skill._maybe_announce_slowdown(target,pos))
    asyncio.run(skill._maybe_announce_slowdown(target,pos))
    assert len(messages)==1 and 'slow down' in messages[0].lower()
    skill._reset_arrival_state();pos['captured_at']=0
    asyncio.run(skill._maybe_announce_slowdown(target,pos))
    assert len(messages)==1

def test_planet_hud_uses_same_camera_offsets_as_ring(tmp_path):
    from fastapi.testclient import TestClient
    from navpoint_ui.app import NavPointServer
    pos=planet_position();skill=_skill(tmp_path,pos);_mark(skill,'Camp')
    target=skill._db.find_navpoint_by_name('Camp')
    pos['x']+=100;pos['captured_at']=time.time()
    server=NavPointServer(db=skill._db,port=0)
    server._active_target=target;server._current_position=pos
    data=TestClient(server._app).get('/api/nav/state').json()
    offsets=navigation.ring_deflection(pos,skill._db.navpoint_to_dict(target),0)
    assert data['planet_guidance']['horizontal_offset_deg']==pytest.approx(offsets[0])
    assert data['planet_guidance']['vertical_angle_deg']==pytest.approx(offsets[1])
    assert data['stack_route'] is None

def test_ring_labels_cruise_and_approach_but_preserves_held_label():
    pos=planet_position();target=dict(id=1,frame='local',frame_id='pyro3',body='pyro3',x=0,y=0,z=0)
    pos['precision'].update(mode='cruise',target_id=1)
    assert navigation.ring_status(pos,target,0)[1]=='COARSE'
    pos['precision'].update(mode='approach',slow_down_advisory=True)
    assert navigation.ring_status(pos,target,0)[1]=='SLOW DOWN'
    assert navigation.ring_status(pos,target,0,reader_state='ACQUIRING')[1]=='HELD 0s'

def test_planet_ring_at_target_has_no_direction():
    pos=planet_position()
    target=dict(id=1,frame='local',frame_id='pyro3',body='pyro3',**{k:pos[k] for k in ('x','y','z')})
    assert navigation.ring_deflection(pos,target,0) is None
