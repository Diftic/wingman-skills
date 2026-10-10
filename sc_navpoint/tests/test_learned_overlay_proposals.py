"""The experimental neural adapter must never repair numeric content."""
import pytest
from _stubs import install_runtime_stubs

install_runtime_stubs()

from ocr_dev.learned_overlay import normalize_row, parse_proposal

SOLAR='Zone: SolarSystem_782455043555 Pos: -9633301.1502km -11472554.0057km -89.1502km'
ROOT='Zone: Root Pos: -9633301.1502km -11472554.0057km -89.1502km'
CAM='CamDir: 29 0 -24 FOV: 50 Focal: 3.00 FStop: 64.0'


def test_unrelated_leading_row_noise_does_not_change_camera_numbers():
    result=parse_proposal(['- '+CAM,SOLAR,ROOT])
    assert result['complete']
    assert result['position']['camdir']==[29.,0.,-24.]


@pytest.mark.parametrize('camera',[CAM+' CamDir: 1 2 3','Not'+CAM,'- CamDir: --29 0 -24'])
def test_camera_anchor_localization_cannot_salvage_ambiguous_or_bad_fields(camera):
    assert not parse_proposal([camera,SOLAR,ROOT])['complete']


def test_model_whitespace_can_change_but_coordinates_cannot():
    compact=ROOT.replace('Pos: ', 'Pos:').replace('km -','km-')
    assert normalize_row(compact)==ROOT
    result=parse_proposal([CAM,SOLAR,compact])
    assert result['position']['coordinate_stack']['root']['x_m']==-9633301150.2
    assert result['position']['camdir']==[29.,0.,-24.]
    assert result['complete']
    assert result['status']=='unverified_proposal'


@pytest.mark.parametrize('bad',[
    ROOT.replace('1502km','15O2km'), ROOT.replace('1502km','1502'),
    ROOT.replace('-89.1502km',''), ROOT+' 4m', ROOT.replace('Root','R0ot'),
    ROOT.replace('-89.1502km','--89.1502km'), ROOT.replace('-89.1502km','NaNkm'),
    ROOT.replace('Root','Root_Cellar'), ROOT.replace('-89.1502km','-89..1502km'),
])
def test_no_character_repair_or_partial_coordinate_salvage(bad):
    assert parse_proposal([CAM,SOLAR,bad])['position'] is None


@pytest.mark.parametrize('rows',[
    [CAM,ROOT], [CAM,SOLAR], [CAM,SOLAR,ROOT,ROOT],
    [CAM,SOLAR,SOLAR,ROOT], [CAM,ROOT,SOLAR],
    [CAM,SOLAR,'Zone: room Pos: 1m 2m 3m',ROOT],
])
def test_anchors_and_order_are_required(rows):
    assert parse_proposal(rows)['position'] is None


@pytest.mark.parametrize('replacement',['-9633301.1503km','9633301.1502km','-9633301.1502m'])
def test_even_small_root_solar_disagreement_refuses(replacement):
    # Existing relative-coordinate tolerance could hide this decimal error.
    assert parse_proposal([CAM,SOLAR,ROOT.replace('-9633301.1502km',replacement)])['position'] is None


def test_missing_facing_is_not_a_complete_read():
    result=parse_proposal([SOLAR,ROOT])
    assert result['position'] is not None
    assert not result['complete']


def test_unrelated_camera_suffix_cannot_remove_readable_facing():
    result=parse_proposal([CAM.replace('Focal: 3.00','Fo?al: ????'),SOLAR,ROOT])
    assert result['complete']


@pytest.mark.parametrize('cam',[CAM.replace('29','NaN'),CAM.replace('29','9999'),CAM.replace('29','?')])
def test_invalid_facing_cannot_be_complete(cam):
    assert not parse_proposal([cam,SOLAR,ROOT])['complete']


@pytest.mark.parametrize('cam',[
    'CamDir: 29 0 -24 F0V: 50 Focal: 3.00',
    'CamDir:29 0-24 FOV:50',
])
def test_camera_extraction_uses_only_the_required_fields(cam):
    result=parse_proposal([cam,SOLAR,ROOT])
    assert result['complete']
    assert result['position']['camdir']==[29.,0.,-24.]


def test_merged_positive_camera_digits_cannot_be_split_by_guessing():
    assert not parse_proposal(['CamDir:290-24 FOV:50',SOLAR,ROOT])['complete']


def test_duplicate_camera_rows_cannot_choose_a_facing():
    assert not parse_proposal([CAM,CAM,SOLAR,ROOT])['complete']


def test_spatial_words_restore_only_measured_spaces():
    from ocr_dev.learned_overlay import spatial_text
    words=[list(s) for s in ['CamDir:','29','0','-24','F0V:','50']]
    text=spatial_text('CamDir:290-24 F0V:50',words)
    assert text=='CamDir: 29 0 -24 F0V: 50'
    assert parse_proposal([text,SOLAR,ROOT])['complete']


def test_spatial_words_cannot_change_a_recognized_character():
    from ocr_dev.learned_overlay import spatial_text
    words=[list(s) for s in ['CamDir:','29','0','-24','FOV:','50']]
    assert spatial_text('CamDir:280-24 FOV:50',words) is None
