"""Normal navigation to a fixed Root address in a confirmed space frame."""
import copy
import json
import time

import pytest
from _stubs import install_runtime_stubs
install_runtime_stubs()

import navigation as nav
from test_stack_direction_calibration import pair


def space_pair(delta=(0., 1000., 0.), camdir=(0., 0., 0.)):
    pos, target = pair(delta, camdir)
    pos.update(active_frame='space', captured_at=time.time())
    target.update(id=21, name='Crash Site One')
    saved = json.loads(target['coordinate_stack'])
    for stack in (pos['coordinate_stack'], saved):
        stack['solar']['raw_name'] = 'SolarSystem_806277473755'
        stack['root']['raw_name'] = 'Root'
    target['coordinate_stack'] = json.dumps(saved)
    return pos, target


@pytest.mark.parametrize('delta,camdir,expected', [
    ((0.,1000.,0.), (0.,0.,0.), (0.,0.)),
    ((1000.,0.,0.), (0.,0.,0.), (90.,0.)),
    ((0.,1000.,0.), (30.,0.,0.), (0.,-30.)),
    ((1000.,1000.,0.), (0.,90.,0.), (0.,45.)),
    # Rz(90) Ry(90) Rx(30): forward=(-sqrt(3)/2, 1/2, 0).
    ((-866.0254,500.,0.), (30.,90.,90.), (0.,0.)),
])
def test_fresh_space_direction_needs_no_planetary_fit(delta, camdir, expected):
    pos,target=space_pair(delta,camdir)
    assert nav.ring_deflection(pos,target,.1)==pytest.approx(expected,abs=.001)


def test_distance_and_retention_use_root_not_ship_local_coordinates():
    pos,target=space_pair()
    assert nav.ring_distance(pos,target,.1)=='1.0 km'
    key=nav.ring_hold_key(pos,target)
    assert key is not None
    moved=copy.deepcopy(pos)
    moved['coordinate_stack']['root']['y_m']+=20
    moved['coordinate_stack']['solar']['y_m']+=20
    moved['camdir']=None
    assert nav.ring_hold_key(moved,target)==key
    assert nav.ring_hold_key(pos,dict(target,id=22))!=key


@pytest.mark.parametrize('change', ['planet','unknown','session','missing_session','bad_root','bad_stack','other_target'])
def test_space_frame_and_provenance_refusals(change):
    pos,target=space_pair()
    if change=='planet':pos.update(active_frame='planet',body='Ita')
    if change=='unknown':pos.pop('active_frame')
    if change=='session':pos['coordinate_stack']['solar']['raw_name']='SolarSystem_other'
    if change=='missing_session':pos['coordinate_stack']['solar']['raw_name']=''
    if change=='bad_root':pos['coordinate_stack']['root']['x_m']+=100000
    if change=='bad_stack':target['coordinate_stack']='broken'
    if change=='other_target':pos['precision']=dict(mode='cruise',target_id=22)
    assert nav.ring_deflection(pos,target,.1) is None
    assert nav.ring_distance(pos,target,.1)==''


@pytest.mark.parametrize('age',[None,-1.,31.,float('nan'),float('inf')])
def test_space_freshness(age):
    pos,target=space_pair()
    assert nav.ring_deflection(pos,target,age) is None
    assert nav.ring_distance(pos,target,age)==''


def saved_skill(tmp_path):
    from test_coordinate_stack_navigation import _skill
    pos,target=space_pair()
    skill=_skill(tmp_path,pos)
    skill._active_target=skill._db.add_navpoint(
        name=target['name'],server_id='',body='',frame='stack',coordinate_schema=1,
        root_x=40000000000.,root_y=-9999999000.,root_z=500.,
        x=target['x'],y=target['y'],z=target['z'],coordinate_stack=target['coordinate_stack'])
    return skill,pos,target


def test_real_ring_keeps_space_dot_for_eight_failures_and_distance_above_warning(tmp_path):
    from ring_overlay import RingOverlay
    skill,pos,target=saved_skill(tmp_path)
    skill._last_position=pos
    skill._ring_overlay=RingOverlay()
    del skill._sync_ring
    pos['precision']=dict(mode='approach',target_id=skill._active_target.id,slow_down_advisory=True)
    skill._sync_ring()
    before=skill._ring_overlay._target
    assert before is not None
    assert skill._ring_overlay._distance=='1.0 km'
    assert skill._ring_overlay._message=='SLOW DOWN'
    skill._last_ring_state='ACQUIRING'
    for _ in range(7):skill._sync_ring()
    assert skill._ring_overlay._target==before
    assert not skill._ring_overlay._error
    skill._sync_ring()
    assert skill._ring_overlay._error
    assert skill._ring_overlay._distance=='1.0 km'
    skill._last_ring_state=''
    skill._sync_ring()
    assert not skill._ring_overlay._error


def test_browser_and_tool_use_the_same_space_direction(tmp_path):
    import asyncio
    from fastapi.testclient import TestClient
    from navpoint_ui.app import NavPointServer
    skill,pos,target=saved_skill(tmp_path)
    server=NavPointServer(db=skill._db,port=0)
    server._active_target=skill._active_target
    server._current_position=pos
    data=TestClient(server._app).get('/api/nav/state').json()
    assert data['space_guidance']['horizontal_offset_deg']==pytest.approx(0)
    assert data['space_guidance']['distance_km']==pytest.approx(1)
    assert data['stack_route']['allow_direction']
    result=json.loads(asyncio.run(skill.navigate_to(target['name'])))
    assert result['bearing']['horizontal_offset_deg']==pytest.approx(0)
    assert 'no direction' not in result['guidance'].lower()
    assert 'note' not in result


def test_browser_renders_space_offsets_and_never_invents_a_centered_dot():
    import shutil
    import subprocess
    from pathlib import Path
    node=shutil.which('node')
    if node is None:pytest.skip('node unavailable')
    source=(Path(__file__).parents[1]/'navpoint_ui/static/app.js').read_text(encoding='utf-8')
    render=source.split('function renderNavPanel() {',1)[1].split('// ── Navigation math',1)[0]
    script="""
const calls=[];
const element={classList:{add(){},remove(){}},style:{},textContent:''};
const document={getElementById:()=>element};
const state={activeTarget:{id:21,frame:'stack',name:'Crash'},
 currentPos:{active_frame:'space'},positionAgeS:0,
 spaceGuidance:{horizontal_offset_deg:23,vertical_angle_deg:-12,distance_km:1},
 stackRoute:{mode:'ROOT_APPROACH',distance_km:1,allow_direction:true}};
const POSITION_FRESHNESS_S=30;
function isSystemFrame(){return false;}
function hasCoords(){return false;}
function sameBody(){return false;}
function setDeflection(...args){calls.push(args);}
function clearDeflection(){calls.push('clear');}
function setNavRow(){} function renderGuidance(){} function renderPosition(){}
function renderDistance(){} function buildApproachSteps(){return [];}
""" + 'function renderNavPanel() {' + render + """
renderNavPanel();
if(JSON.stringify(calls)!=='[[23,-12]]')throw Error(JSON.stringify(calls));
calls.length=0; delete state.spaceGuidance.horizontal_offset_deg;
renderNavPanel();
if(JSON.stringify(calls)!=='["clear"]')throw Error(JSON.stringify(calls));
calls.length=0; state.positionAgeS=31;
renderNavPanel();
if(JSON.stringify(calls)!=='["clear"]')throw Error(JSON.stringify(calls));
"""
    result=subprocess.run([node,'-e',script],capture_output=True,text=True)
    assert result.returncode==0,result.stderr
