"""Site camera calibration must be measured independently of the pilot's aim."""
import math
import numpy as np
import pytest


FRAME = 'levski_all-001'
KEY = (FRAME, 'SolarSystem_123')


def trajectory():
    # Arbitrary 3D tilt, not a planet's rotation around Z.
    x, y, z = map(math.radians, (31, -22, 137))
    rx = np.array([[1,0,0],[0,math.cos(x),-math.sin(x)],[0,math.sin(x),math.cos(x)]])
    ry = np.array([[math.cos(y),0,math.sin(y)],[0,1,0],[-math.sin(y),0,math.cos(y)]])
    rz = np.array([[math.cos(z),-math.sin(z),0],[math.sin(z),math.cos(z),0],[0,0,1]])
    rotation = rz @ ry @ rx
    origin = np.array([-9641670000., -11490735000., -95000.])
    local = np.array([[1200+30*t, 1600+300*math.sin(t/5), 2700+150*math.cos(t/7)] for t in range(30)])
    world = local @ rotation.T + origin
    return rotation, [(float(i), *a, *b) for i,(a,b) in enumerate(zip(local,world))]


def test_fits_tilted_site_and_predicts_heldout_positions():
    from site_rotation import fit_rotation
    expected, samples = trajectory()
    fit = fit_rotation(samples)
    assert fit is not None
    assert np.array(fit['matrix']) == pytest.approx(expected, abs=1e-7)
    assert fit['residual_m'] < .001
    assert fit['check_error_m'] < .001


@pytest.mark.parametrize('mode', ['stationary', 'straight', 'reflection', 'heldout_drift', 'nan', 'duplicate_time'])
def test_unobservable_or_inconsistent_fits_are_withheld(mode):
    from site_rotation import fit_rotation
    _, samples = trajectory()
    a = np.array(samples)
    if mode == 'stationary': a[:,1:] = a[0,1:]
    if mode == 'straight':
        a[:,1:4] = np.arange(len(a))[:,None] * [30,15,6]
        a[:,4:] = a[:,1:4] + [1e10,2e10,3]
    if mode == 'reflection': a[:,4] *= -1
    if mode == 'heldout_drift': a[int(len(a)*.8):,4] += 100
    if mode == 'nan': a[3,4] = np.nan
    if mode == 'duplicate_time': a[4,0] = a[3,0]
    assert fit_rotation(a) is None


def test_camera_projection_correct_for_yaw_pitch_and_roll():
    from site_rotation import fit_rotation
    from navigation import ring_deflection
    from planet_rotation import local_camera_basis
    rotation, samples = trajectory()
    fit = fit_rotation(samples)
    p = dict(active_frame='site', frame_id=FRAME, body=FRAME, system='Nyx', x=10,y=20,z=30)
    p['site_rotation'] = dict(frame_id=FRAME, matrix=fit['matrix'], valid=True)
    for camera in ([0,0,0],[-5,20,13],[60,-50,-170]):
        p['camdir'] = camera
        f,r,u = [rotation.T @ axis for axis in local_camera_basis(camera,0)]
        for yaw,pitch in [(0,0),(-35,14),(160,-25)]:
            h,v = map(math.radians,(yaw,pitch))
            ray = math.cos(v)*(math.cos(h)*f+math.sin(h)*r)+math.sin(v)*u
            target = dict(frame='local',frame_id=FRAME,body=FRAME,system='Nyx',
                          **dict(zip(('x','y','z'),np.array([10,20,30])+ray*1000)))
            assert ring_deflection(p,target,0) == pytest.approx((yaw,pitch),abs=1e-5)
            assert ring_deflection(dict(p,site_rotation=None),target,0) is None
            assert ring_deflection(dict(p,site_rotation=dict(p['site_rotation'],frame_id='other')),target,0) is None
            assert ring_deflection(p,target,100) is None


def calibrated_tracker():
    from site_rotation import SiteRotationTracker
    _, samples = trajectory()
    tracker = SiteRotationTracker()
    for t,*xyz in samples:
        result = tracker.observe(KEY,t,xyz[:3],xyz[3:])
    assert result is not None
    return tracker, samples[-1]


def test_tracker_rechecks_fresh_pairs_and_survives_stationary_readings():
    tracker, (t,*xyz) = calibrated_tracker()
    # No need to repeat the maneuver while sitting still, but every pair is checked.
    for now in range(30,300):
        assert tracker.observe(KEY,float(now),xyz[:3],xyz[3:]) is not None
    assert tracker.observe(KEY,300,xyz[:3],[xyz[3]+50.1,*xyz[4:]]) is None
    assert tracker.observe(KEY,301,xyz[:3],xyz[3:]) is not None


@pytest.mark.parametrize('change', ['session','frame','gap','time_reversal'])
def test_tracker_invalidates_on_context_changes(change):
    tracker, (t,*xyz) = calibrated_tracker()
    key = ('other',KEY[1]) if change=='frame' else (FRAME,'SolarSystem_999') if change=='session' else KEY
    now = t+31 if change=='gap' else t-1 if change=='time_reversal' else t+1
    assert tracker.observe(key,now,xyz[:3],xyz[3:]) is None
    assert tracker.model is None


def test_site_pairs_allow_tilt_but_require_complete_matching_solar_and_root():
    import active_frame as af
    from site_rotation import pair_from_rows
    from test_levski_frame import ROWS
    identity,_ = af.resolve_zone_identity(ROWS)
    pair = pair_from_rows(ROWS,identity)
    assert pair is not None and pair[1][2] != pair[2][2]
    for bad in [ROWS[:-1], ROWS[:-1]+[ROWS[-1].replace('-95.1837km','-96.1837km')],
                [t.replace('1083.64m','108?.64m') for t in ROWS]]:
        assert pair_from_rows(bad,identity) is None


def test_reader_scanner_pipeline_carries_only_validated_rotation():
    from frame_reader import FrameAwareReader
    from scanner import NavPointScanner
    from site_rotation import SiteRotationTracker
    from navigation import ring_deflection
    import active_frame as af
    reader = FrameAwareReader.__new__(FrameAwareReader)
    reader.site_rotation_tracker = SiteRotationTracker()
    rotation,samples = trajectory()
    for t,*xyz in samples:
        rows = ['CamDir: 0 0 0 FOV: 48 Focal: 3.00 FStop: 64.0']
        for name,values in [(FRAME,xyz[:3]),(KEY[1],xyz[3:]),('Root',xyz[3:])]:
            rows.append('Zone: '+name+' Pos: '+' '.join(f'{v:.4f}m' for v in values))
        identity,_ = af.resolve_zone_identity(rows)
        parsed = [dict(raw_model_text=row) for row in rows]
        parsed[0].update(frame_identity=identity,captured_at=t)
        payload,reason = reader.capture_for_target(parsed)
        assert payload is not None,reason
        position = NavPointScanner().parse_payload(payload)
    assert position['site_rotation']['valid']
    assert np.array(position['site_rotation']['matrix']) == pytest.approx(rotation,abs=1e-6)
    assert not {'coordinate_stack','root_pos_raw','system_pos_raw'} & position.keys()
    target = dict(frame='local',frame_id=FRAME,body=FRAME,system='Nyx',x=0,y=0,z=0)
    assert ring_deflection(position,target,0) is not None
    payload['site_rotation']['matrix'] = [[1,0,0],[0,1,0],[0,0,-1]]
    assert 'site_rotation' not in af.validate_planet_payload(payload)
    payload['site_rotation']['matrix'] = [[1,0],[0,1]]
    assert 'site_rotation' not in af.validate_planet_payload(payload)
    # Malformed solar rows block the dot without blocking local coordinates.
    parsed[-1]['raw_model_text'] = parsed[-1]['raw_model_text'].replace('Pos:', 'Pos: ?')
    payload,_ = reader.capture_for_target(parsed)
    assert payload is not None and 'site_rotation' not in payload
