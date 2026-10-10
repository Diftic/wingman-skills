"""Planet identity comes from the lower panel plus its actual active Zone."""
import pytest
import active_frame as af

def planet_rows(name='pyro3',coords='330.7421km 218.7408km 119.0037km'):
    return ['CamDir: -20 26 -174 FOV: 44',
            'Zone: DRAK_Clipper_742164815970 Pos: 0.00m 11.56m 2.83m',
            f'Zone: {name} Pos: {coords}',
            'Zone: SolarSystem_745338555312 Pos: ???km ???km ???km',
            'Zone: Root Pos: ???km ???km ???km']

def metadata(name='pyro3'):
    return [f'Planet:{name} (Load Complete)','Current player location : Pyro3']

def test_planet_label_must_match_an_active_zone():
    identity,reason=af.resolve_identity(planet_rows(),metadata())
    assert not reason and identity['kind']=='planet' and identity['zone_name']=='pyro3'

def test_planetary_numbers_do_not_depend_on_solar_numbers():
    text=planet_rows();identity,_=af.resolve_identity(text,metadata())
    payload,reason=af.build_payload(text,identity)
    assert not reason
    from scanner import NavPointScanner
    position=NavPointScanner().parse_payload(payload)
    assert position['body']=='pyro3' and position['local_frame']
    assert position['x']==330742.1
    assert 'coordinate_stack' not in position and 'root_pos_raw' not in position
    assert position['frame_id']=='pyro3'

def test_unreadable_planet_does_not_fall_back_to_solar():
    text=planet_rows(coords='330.???km 218.7408km 119.0037km')
    identity,_=af.resolve_identity(text,metadata())
    assert af.build_payload(text,identity)[0] is None

def test_stale_planet_label_in_space_does_not_select_a_ship():
    text=planet_rows();text.pop(2)
    identity,reason=af.resolve_identity(text,['Planet:OOC_Stanton_4_Microtech (Load Complete)',
                                             'Current player location : StantonSolarSystem'])
    assert not reason and identity['kind']=='space'

def test_matching_planet_below_root_is_not_active():
    text=planet_rows();planet=text.pop(2);text.append(planet)
    assert af.resolve_identity(text,metadata())[0] is None

def test_lower_label_without_active_match_cannot_authorize_planet_coordinates():
    assert af.resolve_identity(planet_rows(),metadata('OOC_Stanton_4b_Clio'))[0] is None

def test_no_current_planet_explicitly_selects_space():
    text=planet_rows();text.pop(2)
    assert af.resolve_identity(text,['No Current Planet'])[0]['kind']=='space'

def test_absent_metadata_does_not_guess_a_frame():
    assert af.resolve_identity(planet_rows(),[])[0] is None

def test_stanton_body_name_is_kept_with_its_stable_identifier():
    token='OOC_Stanton_4b_Clio'
    identity,_=af.resolve_identity(planet_rows(token),metadata(token))
    assert identity['body']=='Clio' and identity['planet_id']==token.casefold()

def test_planet_precision_uses_only_matching_planet_target_and_save_bypasses_it():
    text=planet_rows();identity,_=af.resolve_identity(text,metadata())
    target=dict(id=1,frame='local',frame_id='pyro3',body='pyro3',system='Pyro',x=430742.1,y=218740.8,z=119003.7)
    payload,_=af.build_payload(text,identity,target)
    assert payload['precision']['mode']=='cruise'
    from scanner import NavPointScanner
    assert NavPointScanner().parse_payload(payload)['x']==330500
    exact,_=af.build_payload(text,identity,target,full_precision=True)
    assert exact['precision']['mode']=='full'
    assert NavPointScanner().parse_payload(exact)['x']==330742.1
    target['frame_id']='clio'
    assert af.build_payload(text,identity,target)[0]['precision']['mode']=='full'

def test_near_planet_target_has_ten_metre_requirement():
    text=planet_rows();identity,_=af.resolve_identity(text,metadata())
    target=dict(id=1,frame='local',frame_id='pyro3',body='pyro3',x=331000,y=218000,z=119000)
    payload,_=af.build_payload(text,identity,target)
    assert payload['precision']['mode']=='approach'
    assert payload['precision']['required_position_error_m']==10

def test_invalid_location_cannot_be_cached_as_a_planet():
    assert af.resolve_identity(planet_rows(),['Planet:pyro3','Current player location : INVALID LOCATION ID'])[0] is None
