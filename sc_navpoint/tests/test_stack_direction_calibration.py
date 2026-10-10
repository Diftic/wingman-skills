"""Exercise stack directions without opening the normal guidance gate."""
import json
import pytest
from _stubs import install_runtime_stubs

install_runtime_stubs()

import coordinate_stack as cs
import navigation as nav
import overlay_fields as fields


def stack_at(xyz):
    return cs.CoordinateStack(
        root=cs.StackRow(*xyz), solar=cs.StackRow(*xyz),
        nested=(cs.StackRow(99.,88.,77.,depth=0),), candidate_depth=0,
    )


def pair(delta=(100.,0.,0.),camdir=(0.,0.,0.)):
    origin=(40_000_000_000.,-10_000_000_000.,500.)
    current=stack_at(origin)
    target=stack_at(tuple(x+d for x,d in zip(origin,delta)))
    # Flattened and nested coordinates deliberately disagree with Root.
    pos=dict(x=1.,y=2.,z=3.,camdir=camdir,coordinate_stack=cs.to_dict(current))
    dest=dict(x=-999.,y=2.,z=3.,frame='stack',coordinate_stack=cs.to_json(target))
    return pos,dest


@pytest.mark.parametrize('delta,camdir,expected',[
    ((0.,100.,0.),(0.,0.,0.),(0.,0.)),
    ((100.,0.,0.),(0.,0.,0.),(90.,0.)),
    ((-100.,0.,0.),(0.,0.,0.),(-90.,0.)),
    ((0.,100.,100.),(0.,0.,0.),(0.,45.)),
    ((100.,0.,0.),(0.,0.,-90.),(0.,0.)),
    ((100.,100.,0.),(0.,90.,0.),(0.,45.)),
])
def test_calibration_uses_root_and_corrected_space_basis(delta,camdir,expected):
    position,target=pair(delta,camdir)
    result=nav.ring_deflection(position,target,.1,allow_uncalibrated_space=True)
    assert result==pytest.approx(expected,abs=1e-8)


def test_normal_path_still_waits_for_live_calibration():
    position,target=pair()
    assert nav.ring_deflection(position,target,.1) is None


@pytest.mark.parametrize('bad',[None,{},'broken'])
def test_corrupt_stack_cannot_use_flat_coordinates(bad):
    for side in ('position','target'):
        position,target=pair()
        (position if side=='position' else target)['coordinate_stack']=bad
        assert nav.ring_deflection(position,target,.1,allow_uncalibrated_space=True) is None


@pytest.mark.parametrize('camdir',[None,(0.,0.),(0.,float('nan'),0.),(0.,0.,float('inf')),('east',0.,0.),(True,0.,0.)])
def test_invalid_facing_cannot_draw_arrow(camdir):
    position,target=pair(camdir=camdir)
    assert nav.ring_deflection(position,target,.1,allow_uncalibrated_space=True) is None


@pytest.mark.parametrize('age',[None,31.,float('nan'),float('inf'),-1.])
def test_invalid_or_stale_capture_age_cannot_draw_arrow(age):
    position,target=pair()
    assert nav.ring_deflection(position,target,age,allow_uncalibrated_space=True) is None


@pytest.mark.parametrize('side',['position','target'])
def test_root_solar_disagreement_cannot_draw_arrow(side):
    position,target=pair()
    obj=position['coordinate_stack'] if side=='position' else cs.to_dict(cs.from_json(target['coordinate_stack']))
    obj['solar']['x_m']+=100_000
    if side=='target': target['coordinate_stack']=json.dumps(obj)
    assert nav.ring_deflection(position,target,.1,allow_uncalibrated_space=True) is None


def test_same_point_and_refused_latest_frame_have_no_arrow():
    position,target=pair(delta=(0.,0.,0.))
    assert nav.ring_deflection(position,target,.1,allow_uncalibrated_space=True) is None
    position,target=pair()
    held, message = nav.ring_status(position,target,.1,fields.RING_GLARE,allow_uncalibrated_space=True)
    assert held is not None
    assert message == "HELD 0s"


def test_stack_calibration_trace_reports_the_root_points_used():
    import main
    position,target=pair()
    skill=main.SC_NavPoint.__new__(main.SC_NavPoint)
    skill._space_test_badge_shown=True
    messages=[]
    skill._poll_trace=lambda message,**kw: messages.append(message)
    skill._log_space_test(position,target,(90.,0.))
    assert len(messages)==1
    assert 'from=(40000000000.0, -10000000000.0, 500.0)' in messages[0]
    assert 'to=(40000000100.0, -10000000000.0, 500.0)' in messages[0]
    assert 'UNCALIBRATED' in messages[0]


@pytest.mark.parametrize('side',['position','target'])
def test_unrepresentable_saved_coordinate_refuses_without_exception(side):
    position,target=pair()
    obj=position['coordinate_stack'] if side=='position' else json.loads(target['coordinate_stack'])
    obj['root']['x_m']=10**400
    if side=='target': target['coordinate_stack']=json.dumps(obj)
    assert nav.ring_deflection(position,target,.1,allow_uncalibrated_space=True) is None


def test_saved_database_waypoint_reaches_ring_and_trace(tmp_path):
    import time
    from types import SimpleNamespace
    import main
    from database import NavPointDatabase

    position, destination = pair()
    db = NavPointDatabase(str(tmp_path))
    saved = db.add_navpoint(name='Return test', server_id='', body='',
        x=-999., y=2., z=3., frame='stack', coordinate_schema=1,
        root_x=40000000100., root_y=-10000000000., root_z=500.,
        coordinate_stack=destination['coordinate_stack'])
    states, traces = [], []
    skill = main.SC_NavPoint.__new__(main.SC_NavPoint)
    skill._db = db
    skill._active_target = saved
    skill._last_position = dict(position, captured_at=time.time())
    skill._last_ring_state = ''
    skill._get_space_direction_test = lambda: True
    skill._space_test_badge_shown = True
    skill._poll_trace = lambda text, **kw: traces.append(text)
    skill._ring_overlay = SimpleNamespace(set_state=lambda *args: states.append(args))
    skill._sync_ring()
    assert states[-1][1] == pytest.approx((90., 0.))
    assert 'to=(40000000100.0, -10000000000.0, 500.0)' in traces[-1]
    # The HUD summary remains compact; only the ring needs the full stack.
    assert 'coordinate_stack' not in db.navpoint_to_dict(saved)
