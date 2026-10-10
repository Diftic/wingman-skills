"""Survey-derived frame boundaries; never substitute SolarSystem for a site."""
import pytest
import active_frame as af
from _stubs import install_runtime_stubs
install_runtime_stubs()
from test_active_frame import planet_rows

@pytest.mark.parametrize('name', ['pyro5b', 'pyro5f'])
def test_pyro_moons_use_their_own_local_coordinates(name):
    rows=planet_rows(name)
    identity,reason=af.resolve_zone_identity(rows)
    assert not reason
    payload,reason=af.build_payload(rows,identity,full_precision=True)
    assert not reason
    position=af.validate_planet_payload(payload)
    assert position['frame_id']==name and position['x']==330742.1
    assert 'coordinate_stack' not in position

@pytest.mark.parametrize('name', ['ab_mine_stanton3_sml_002','ab_mine_stanton3_med_006','ab_mine_pyro_regionb_med_001'])
def test_mining_sites_preserve_local_identity_and_ignore_bad_solar_numbers(name):
    rows=planet_rows(name)
    identity,reason=af.resolve_zone_identity(rows)
    assert not reason and identity['kind']=='site'
    payload,reason=af.build_payload(rows,identity,full_precision=True)
    assert not reason and payload['active_frame']=='site'
    position=af.validate_planet_payload(payload)
    assert position['frame_id']==name and position['x']==330742.1
    assert position['active_frame']=='site'
    assert 'coordinate_stack' not in position

def test_other_site_cannot_share_target_coordinates():
    assert not af.same_planet(dict(body='ab_mine_stanton3_sml_002',frame_id='ab_mine_stanton3_sml_002'),
                              dict(frame='local',body='ab_mine_stanton3_med_006',frame_id='ab_mine_stanton3_med_006'))

def test_fixed_prefix_correction_does_not_repair_numbers_or_unknown_names():
    rows=planet_rows('O0C_Stanton_3a_Lyria')
    identity,reason=af.resolve_zone_identity(rows)
    assert not reason
    payload,reason=af.build_payload(rows,identity)
    assert not reason
    assert af.validate_planet_payload(payload)['frame_id']=='ooc_stanton_3a_lyria'
    assert af.resolve_zone_identity(planet_rows('O0C_Stanton_3a_NotLyria'))[0] is None
    bad=planet_rows('O0C_Stanton_3a_Lyria',coords='33O.7421km 218.7408km 119.0037km')
    assert af.build_payload(bad,af.resolve_zone_identity(bad)[0])[0] is None

def test_site_direction_requires_measured_frame_orientation():
    from navigation import ring_deflection
    position=dict(active_frame='site',local_frame=True,body='ab_mine_stanton3_sml_002',frame_id='ab_mine_stanton3_sml_002',system='Stanton',x=0,y=0,z=0,camdir=[0,0,0])
    target=dict(frame='local',body=position['body'],frame_id=position['frame_id'],system='Stanton',x=100,y=0,z=0)
    # Site axes can be rotated/tilted relative to the camera's solar axes.
    # Previously this returned a confident centered dot without calibration.
    assert ring_deflection(position,target,0) is None

def test_two_named_site_bookmarks_keep_independent_precise_local_positions(tmp_path):
    from test_coordinate_stack_navigation import _skill,_mark
    name='ab_mine_stanton3_sml_002'
    rows=planet_rows(name);identity,_=af.resolve_zone_identity(rows)
    position=af.validate_planet_payload(af.build_payload(rows,identity,full_precision=True)[0])
    skill=_skill(tmp_path,position)
    result=_mark(skill,'First ore patch')
    assert result['success'] and result['location_label']=='Mining Base #RSV-8HL'
    async def moved(attempts=1):return dict(position,x=position['x']+50)
    skill._capture_position=moved
    assert _mark(skill,'Second ore patch')['success']
    first=skill._db.find_navpoint_by_name('First ore patch')
    second=skill._db.find_navpoint_by_name('Second ore patch')
    assert second.x-first.x==50
    for saved in [first,second]:
        assert saved.frame=='local' and saved.frame_id==name
        assert saved.coordinate_stack is None and saved.root_x is None
        assert skill._db.navpoint_to_dict(saved)['display_location']=='Mining Base #RSV-8HL'
