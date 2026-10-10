import math
import pytest
import numpy as np


def test_ita_two_headings_use_solar_camera_rotated_into_local_frame():
    from planet_rotation import local_camera_basis
    samples=[((-48,33,100),261.1553,(.6069078,-.4923621,-.623893)),
             ((-25,-55,25),271.2442,(-.9711194,-.0403885,-.2351509))]
    for cam,angle,motion in samples:
        forward,right,up=local_camera_basis(cam,math.radians(angle))
        assert math.degrees(math.acos(np.clip(np.dot(forward,motion),-1,1)))<1
        assert np.array([forward,right,up]) @ np.array([forward,right,up]).T == pytest.approx(np.eye(3))
        assert np.cross(right,forward)==pytest.approx(up)


def samples():
    result=[]
    for t in range(0,121,2):
        local=np.array([33000+25*t,-270000+4*t])
        angle=4.5+.00036*t
        c,s=math.cos(angle),math.sin(angle)
        world=np.array([12830194715.,114913608.])+[c*local[0]-s*local[1],s*local[0]+c*local[1]]
        result.append((float(t),*local,*world))
    return result


def test_fit_rotation_from_positions_predicts_heldout_time():
    from planet_rotation import fit_rotation
    fit=fit_rotation(samples())
    assert fit is not None
    assert math.remainder(fit['angle']+fit['rate']*150-(4.5+.00036*150),2*math.pi)==pytest.approx(0,abs=.005)


def test_fit_accepts_position_noise_within_fifty_metres():
    from planet_rotation import fit_rotation
    noisy = [(t, x, y, sx + 25 * math.sin(t), sy) for t, x, y, sx, sy in samples()]
    fit = fit_rotation(noisy)
    assert fit is not None
    assert 2 < fit['residual_m'] <= 50


@pytest.mark.parametrize('offset, accepted', [(49.9, True), (50.1, False)])
def test_heldout_prediction_uses_fifty_metre_limit(offset, accepted):
    from planet_rotation import fit_rotation
    data = samples()
    split = int(len(data) * .8)
    data[split:] = [(t, x, y, sx + offset, sy) for t, x, y, sx, sy in data[split:]]
    assert (fit_rotation(data) is not None) is accepted


@pytest.mark.parametrize('offset, accepted', [(49.9, True), (50.0, True), (50.1, False)])
def test_fresh_pair_uses_inclusive_fifty_metre_limit(offset, accepted):
    from planet_rotation import PlanetRotationTracker
    tracker = PlanetRotationTracker()
    key = ('hurston', 'SolarSystem_1')
    tracker.reset(key)
    tracker.model = dict(epoch=100., checked_at=100., angle=0., rate=0., center=[0., 0.])
    result = tracker.observe(key, 100., (100., 0., 0.), (100. + offset, 0., 0.))
    assert (result is not None) is accepted


def test_unobservable_or_inconsistent_rotation_refuses():
    from planet_rotation import fit_rotation
    assert fit_rotation([(float(t),1.,2.,10.,20.) for t in range(60)]) is None
    bad=samples()
    bad=[(t,x,y,sx+1000*math.sin(t),sy) for t,x,y,sx,sy in bad]
    assert fit_rotation(bad) is None


def test_planet_ring_needs_matching_fresh_rotation_but_space_is_unchanged():
    from navigation import ring_deflection,space_guidance
    p=dict(active_frame='planet',body='Ita',system='Stanton',frame_id='ooc_stanton_1d_ita',x=0,y=0,z=0,camdir=[0,0,0])
    target=dict(frame='local',body='Ita',system='Stanton',frame_id=p['frame_id'],x=0,y=100,z=0)
    assert ring_deflection(p,target,0) is None
    p['planet_rotation']=dict(frame_id=p['frame_id'],angle=0.,valid=True)
    assert ring_deflection(p,target,0)==pytest.approx((0,0))
    p['planet_rotation']['frame_id']='other'
    assert ring_deflection(p,target,0) is None
    space=dict(system_frame=True,frame_id='123',x=0,y=0,z=0,camdir=[0,0,0],planet_rotation={'angle':2.})
    st=dict(frame='system',frame_id='123',x=0,y=100,z=0)
    expected=space_guidance([0,0,0],(0,0,0),(0,100,0),allow_uncalibrated=True)
    assert ring_deflection(space,st,0,allow_uncalibrated_space=True)==pytest.approx((expected['horizontal_offset_deg'],expected['vertical_angle_deg']))


def test_tracker_drops_calibration_on_frame_change_and_bad_fresh_pair():
    from planet_rotation import PlanetRotationTracker,fit_rotation
    tracker=PlanetRotationTracker();key=('ita','SolarSystem_1')
    tracker.reset(key);tracker.model=fit_rotation(samples())
    t,x,y,sx,sy=samples()[-1]
    assert tracker.observe(key,t,(x,y,0),(sx,sy,0))['valid']
    assert tracker.observe(key,t+.1,(x,y,0),(sx+1000,sy,0)) is None
    assert tracker.observe(('lyria','SolarSystem_1'),t+.2,(x,y,0),(sx,sy,0)) is None
    assert tracker.model is None


def test_pair_and_payload_keep_solar_out_of_saved_position():
    import active_frame as af
    from planet_rotation import pair_from_rows
    rows=['CamDir: 0 0 0 FOV: 52 Focal: 3.00 FStop: 64.0',
          'Zone: OOC_Stanton_1d_Ita Pos: 1.0000km 2.0000km 3.0000km',
          'Zone: SolarSystem_123 Pos: 12345.0000km 100.0000km 3.0000km',
          'Zone: Root Pos: 12345.0000km 100.0000km 3.0000km']
    identity,_=af.resolve_zone_identity(rows)
    pair=pair_from_rows(rows,identity)
    assert pair[1]==[1000,2000,3000]
    payload,_=af.build_payload(rows,identity)
    payload['planet_rotation']=dict(frame_id=identity['planet_id'],valid=True,angle=1.)
    position=af.validate_planet_payload(payload)
    assert position['x']==1000 and position['planet_rotation']['angle']==1
    assert 'coordinate_stack' not in position and 'system_pos_raw' not in position
    rows[-1]=rows[-1].replace('12345','12346')
    assert pair_from_rows(rows,identity) is None
    assert af.build_payload(rows,identity)[0] is not None
