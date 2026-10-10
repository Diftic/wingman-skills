"""Physical precision boundaries for the experimental reader; no model or game."""
import pytest
from distance_precision import PrecisionTarget, parse_with_precision, within_approach_error

SOLAR='SolarSystem_795179149930'
def rows(x='42603250.1234km', solar_x=None, local='-25.1234km', z='68.0559km'):
    return ['CamDir: 8 21 170 FOV: 39',
            f'Zone: keeger_segment Pos: {local} 114.5437km {z}',
            f'Zone: {SOLAR} Pos: {solar_x or x} 22112563.1247km {z}',
            f'Zone: Root Pos: {x} 22112563.1247km {z}']
def target(offset=30000):
    return PrecisionTarget((42603250000.+offset,22112563124.7,68055.9),SOLAR)

def test_far_fraction_disagreement_does_not_reject_and_is_explicitly_coarse():
    r=parse_with_precision(rows(solar_x='42603250.9999km'),target())
    assert r['complete']
    assert r['precision']['mode']=='cruise'
    assert r['position']['coordinate_stack']['root']['x_m']==42603250500.
    assert r['precision']['root_quantization_radius_m']==pytest.approx(866.0254038)
    assert r['precision']['actual_accuracy_verified'] is False

def test_far_unreadable_fraction_can_be_discarded_without_guessing_it():
    r=parse_with_precision(rows(x='42603250.????km',local='-25.??km'),target())
    assert r['complete'] and r['precision']['mode']=='cruise'
    assert r['position']['coordinate_stack']['nested'][0]['x_m']==-25500

@pytest.mark.parametrize('bad',['4260325?.1234km','42603250.1234kB','42603250..1234km'])
def test_integer_unit_and_decimal_structure_are_not_repaired(bad):
    assert not parse_with_precision(rows(x=bad),target())['complete']

def test_integer_disagreement_is_still_rejected():
    assert not parse_with_precision(rows(solar_x='42603251.1234km'),target())['complete']

def test_approach_preserves_full_precision_and_ten_metre_requirement():
    r=parse_with_precision(rows(),target(10000))
    assert r['complete'] and r['precision']['mode']=='approach'
    assert r['precision']['required_position_error_m']==10
    assert r['position']['coordinate_stack']['root']['x_m']==42603250123.4

def test_near_uncertain_fraction_is_not_promoted_to_a_ten_metre_fix():
    r=parse_with_precision(rows(x='42603250.????km'),target(10000))
    assert not r['complete'] and r['precision']['mode']=='approach'

def test_approach_anchor_crosscheck_allows_ten_metres_total_not_exact_decimals():
    r=parse_with_precision(rows(solar_x='42603250.1334km'),target(10000))
    assert r['complete']
    assert r['precision']['actual_accuracy_verified'] is False
    stack=r['position']['coordinate_stack']
    assert stack['root']['x_m']==42603250123.4
    assert stack['solar']['x_m']==42603250133.4

def test_approach_anchor_crosscheck_rejects_combined_axis_error_over_ten():
    text=rows(solar_x='42603250.1314km')
    text[2]=text[2].replace('22112563.1247km','22112563.1327km')
    assert not parse_with_precision(text,target(10000))['complete']

def test_approach_does_not_relax_integer_or_camera_requirements():
    assert not parse_with_precision(rows(solar_x='42603251.1234km'),target(10000))['complete']
    text=rows(solar_x='42603250.1314km');text[0]='CamDir: ? 21 170'
    assert not parse_with_precision(text,target(10000))['complete']

def test_possible_inside_boundary_switches_early():
    r=parse_with_precision(rows(),target(15500))
    assert r['precision']['mode']=='approach'
    assert r['precision']['distance_lower_bound_m']==pytest.approx(14500)

def test_exact_15000_lower_bound_remains_cruise():
    assert parse_with_precision(rows(),target(16000))['precision']['mode']=='cruise'

def test_no_target_keeps_strict_precision_for_saving():
    r=parse_with_precision(rows(),None)
    assert r['precision']['mode']=='full'
    assert r['position']['coordinate_stack']['root']['x_m']==42603250123.4
    assert not parse_with_precision(rows(solar_x='42603250.9999km'),None)['complete']

def test_metres_stay_metres_and_negative_zero_keeps_its_region():
    r=parse_with_precision(rows(local='-0.25m'),target())
    assert r['complete']
    assert r['position']['coordinate_stack']['nested'][0]['x_m']==-.5

def test_target_system_mismatch_is_not_used_for_mode_selection():
    t=PrecisionTarget(target().root_m,'SolarSystem_123')
    assert not parse_with_precision(rows(),t)['complete']

def test_ten_metres_means_vector_error_not_ten_per_axis():
    assert within_approach_error((0,0,0),(6,8,0))
    assert not within_approach_error((0,0,0),(8,8,0))
    assert not within_approach_error((0,0,0),(10.01,0,0))

@pytest.mark.parametrize('xyz',[(float('nan'),0,0),(True,0,0),(0,0)])
def test_invalid_targets_are_rejected(xyz):
    with pytest.raises(ValueError): PrecisionTarget(xyz,SOLAR)

def test_frame_reader_uses_policy_without_loading_or_rerunning_model():
    from frame_reader import FrameAwareReader
    reader=FrameAwareReader.__new__(FrameAwareReader)
    context=dict(id=1,frame='system',frame_id=SOLAR.split('_')[1],**dict(zip(('x','y','z'),target().root_m)))
    cached=[{'raw_model_text':t} for t in rows(solar_x='42603250.9999km')]
    cached[0]['frame_identity']={'kind':'space'}
    payload,reason=reader.capture_for_target(cached,context)
    assert payload is not None and not reason
    assert payload['precision']['mode']=='cruise'
    from scanner import NavPointScanner
    assert NavPointScanner().parse_payload(payload)['precision']['mode']=='cruise'
    context['x']=target(10000).root_m[0]
    payload,reason=reader.capture_for_target(cached,context)
    assert payload is None
    assert reason

def test_frame_reader_without_target_preserves_existing_coordinates():
    from frame_reader import FrameAwareReader
    from specialist_reader import SpecialistReader
    reader=FrameAwareReader.__new__(FrameAwareReader)
    cached=[{'raw_model_text':t} for t in rows()]
    cached[0]['frame_identity']={'kind':'space'}
    actual,reason=reader.capture_payload(cached)
    expected,_=SpecialistReader.capture_payload(cached)
    assert not reason
    assert all(actual[k]==v for k,v in expected.items())
    assert actual['precision']['mode']=='full'
