"""Levski frame from the accepted OCR rows logged on 2026-09-15 23:03:25."""
import pytest
from _stubs import install_runtime_stubs
install_runtime_stubs()

import active_frame as af
from test_coordinate_stack_navigation import _skill, _mark

ROWS = [
    'CamDir: -27 -6 -56 FOV: 48 Focal: 3.00 FStop: 64.0',
    'Zone: ANVL_C8R_Pisces_826163132579 Pos: -0.01m 3.86m 0.91m',
    'Zone: levski_all-001 Pos: 1083.64m 1218.65m -1580.33m',
    'Zone: SolarSystem_806277473759 Pos: -9641671.9011km -11490735.8070km -95.1837km',
    'Zone: Root Pos: -9641671.9011km -11490735.8070km -95.1837km',
]


def test_recorded_levski_rows_save_named_local_coordinates(tmp_path):
    from frame_reader import FrameAwareReader
    from scanner import NavPointScanner
    reader = FrameAwareReader.__new__(FrameAwareReader)
    import numpy as np
    reader._recognize_band = lambda frame,index: ROWS[index]
    _,_,rows = reader.read(np.zeros((175,675,3),dtype=np.uint8))
    payload,reason = reader.capture_for_target(rows,full_precision=True)
    assert payload is not None,reason
    position = NavPointScanner().parse_payload(payload)
    assert position['active_frame']=='site'
    assert position['system']=='Nyx'
    assert (position['x'],position['y'],position['z']) == pytest.approx((1083.64,1218.65,-1580.33))
    skill = _skill(tmp_path,position)
    result = _mark(skill,'Control Location')
    assert result['success'] and result['location_label']=='Levski'
    saved = skill._db.find_navpoint_by_name('Control Location')
    assert saved.frame=='local' and saved.frame_id=='levski_all-001'
    assert saved.coordinate_stack is None and saved.root_x is None
    target=skill._db.navpoint_to_dict(saved)
    assert af.same_planet(position,target)
    assert not af.same_planet(dict(position,frame_id='another_site'),target)
    from navigation import ring_distance
    assert ring_distance(dict(position,x=position['x']+250),target,0)=='250 m'


@pytest.mark.parametrize('name',['levski_all-002','levski_all-00I','Delamar','Nyx1','unknown_nyx_station'])
def test_only_observed_frame_alias_is_enabled(name):
    rows=[row.replace('levski_all-001',name) for row in ROWS]
    assert af.resolve_zone_identity(rows)==(None,'unknown_zone_name')


def test_levski_never_uses_root_to_repair_bad_local_coordinates():
    rows=[row.replace('1083.64m','1O83.64m') for row in ROWS]
    identity,reason=af.resolve_zone_identity(rows)
    assert identity is not None,reason
    assert af.build_payload(rows,identity,full_precision=True)==(None,'planet_coordinates_unreadable')


def test_unknown_frame_message_does_not_blame_scenery():
    import main
    from overlay_fields import CaptureOutcome, KIND_GATE
    skill=main.SC_NavPoint.__new__(main.SC_NavPoint)
    message=skill._capture_error(CaptureOutcome(kind=KIND_GATE,gate='unknown_zone_name'))['error']
    assert 'not supported' in message.lower()
    assert 'nothing was saved' in message.lower()
    assert 'scenery' not in message.lower() and 'ask again' not in message.lower()
