"""No public direction output may resurrect an uncalibrated legacy heading."""
import asyncio
import json
import shutil
import subprocess
from pathlib import Path
import pytest
from _stubs import install_runtime_stubs
install_runtime_stubs()
import main
from navigation import ring_deflection, calculate_bearing


@pytest.mark.parametrize('loads', [True,False])
def test_v8_is_the_only_reader_and_failure_never_uses_legacy(monkeypatch,loads):
    import frame_reader
    skill=main.SC_NavPoint.__new__(main.SC_NavPoint)
    def no_property(*args): pytest.fail('Reader selection must not read a setting')
    skill.retrieve_custom_property_value=no_property
    marker=object()
    def make_reader():
        if not loads: raise RuntimeError('V8 unavailable')
        return marker
    def legacy(*args): pytest.fail('Legacy OCR must never start')
    monkeypatch.setattr(frame_reader,'FrameAwareReader',make_reader)
    monkeypatch.setattr(main.overlay_reader,'OverlayReader',legacy)
    assert skill._local_reader() is (marker if loads else None)
    assert skill._local_reader() is (marker if loads else None)


def test_reader_selector_is_absent_from_settings():
    import yaml
    config=yaml.safe_load((Path(__file__).resolve().parent.parent/'default_config.yaml').read_text())
    assert 'specialist_ocr_candidate' not in [p['id'] for p in config['custom_properties']]


@pytest.mark.parametrize('frame', [None,'site','planet'])
def test_uncalibrated_local_outputs_withhold_all_direction_fields(frame):
    p=dict(body='Levski',frame_id='levski_all-001',system='Nyx',
           x=1000,y=2000,z=3000,heading=90,camdir=[0,0,0])
    if frame: p['active_frame']=frame
    target=dict(frame='local',body=p['body'],frame_id=p['frame_id'],system='Nyx',x=1100,y=2100,z=3100)
    assert ring_deflection(p,target,0) is None
    bearing=calculate_bearing((1000,2000,3000),(1100,2100,3100),current_heading=90,use_local_frame=True)
    result=main.SC_NavPoint._active_guidance(p,target,bearing)
    assert result['turn_instruction']=='Direction unavailable'
    assert result['distance_m']>0
    assert not {'horizontal_offset_deg','vertical_angle_deg','horizontal_bearing_deg','direction_label'} & result.keys()


def test_capture_does_not_publish_legacy_heading():
    from test_main_capture import _make_skill
    skill=_make_skill(scanner_pos=dict(local_frame=True,body='Daymar',x=1000,y=2000,z=3000,
                                      camdir=[0,0,0],heading=90),db=None)
    position=asyncio.run(skill._capture_position())
    assert 'heading' not in position
    assert position['camdir']==[0,0,0]


def test_dashboard_withholds_legacy_direction_but_keeps_distance():
    node=shutil.which('node')
    if node is None: pytest.skip('node unavailable')
    source=(Path(__file__).resolve().parent.parent/'navpoint_ui/static/app.js').read_text(encoding='utf-8')
    # Exercise the actual renderer without timers, network, or a browser window.
    nav=source[source.index('function renderNavPanel()'):source.index('// ── Navigation math')]
    pos=source[source.index('function renderPosition('):source.index('// ── Actions')]
    script='''
const nodes={};
const document={getElementById:id=>nodes[id]??=( {classList:{add(){},remove(){}},style:{},querySelector(){return null;} } )};
const state={activeTarget:{name:'Camp',body:'Daymar',x:100,y:0,z:0},currentPos:{body:'Daymar',x:0,y:0,z:0,heading:90},positionAgeS:0};
const POSITION_FRESHNESS_S=30;
const rows={}; let dot=null, distance=null;
function setNavRow(k,v){rows[k]=v;} function renderDistance(d){distance=d;}
function setDeflection(h,v){dot=[h,v];} function clearDeflection(){dot=null;}
function renderGuidance(){} function buildApproachSteps(){return [];} function buildSteps(){return [];}
function hasCoords(p){return true;} function sameBody(a,b){return a.body===b.body;} function isSystemFrame(){return false;}
function calcBearing(){return {horizontalOffset:90,elevation:0,distanceKm:.1,bearing:90,dirLabel:'E'};}
function fmt(v){return String(v);} function escHtml(v){return String(v);}
''' + nav + pos + '''
renderNavPanel();
console.log(JSON.stringify({dot,distance,turn:rows['nav-turn'],position:nodes['pos-grid'].innerHTML}));
'''
    completed=subprocess.run([node,'-e',script],capture_output=True,text=True)
    assert completed.returncode==0,completed.stderr
    result=json.loads(completed.stdout)
    assert result['dot'] is None
    assert result['distance']==pytest.approx(.1)
    assert result['turn']=='Direction unavailable'
    assert 'HDG' not in result['position']
