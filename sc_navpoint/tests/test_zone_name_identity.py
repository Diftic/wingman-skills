"""Current user policy: identify active frames by Zone names, not lower metadata."""
import pytest
import active_frame as af
from test_active_frame import planet_rows
from test_frame_reader import reader_for
import numpy as np

@pytest.mark.parametrize('name',['pyro3','Pyro3','pyro4','pyro5','OOC_Stanton_4b_Clio'])
def test_known_planet_name_needs_no_lower_label(name):
    identity,reason=af.resolve_zone_identity(planet_rows(name))
    assert not reason and identity['planet_id']==name.casefold()

@pytest.mark.parametrize('name',['JumpTunnelHost_827728246598','RSI_Apollo_Medivac_818065948204'])
def test_third_row_container_is_not_a_planet(name):
    identity,reason=af.resolve_zone_identity(planet_rows(name))
    assert not reason and identity['kind']=='space'

@pytest.mark.parametrize('name',['pyro?','pyro30','unknown_body','station_segment'])
def test_unknown_name_cannot_be_guessed_as_planet_or_space(name):
    assert af.resolve_zone_identity(planet_rows(name))[0] is None

def test_reader_never_decodes_lower_status_rows():
    texts=dict(enumerate(planet_rows()))
    reader,calls=reader_for(texts)
    _,_,rows=reader.read(np.zeros((175,675,3),dtype=np.uint8))
    assert calls==[0,1,2,3,4]
    assert reader.capture_payload(rows)[0]['planet_identity']['planet_id']=='pyro3'

def test_two_named_planets_are_ambiguous():
    texts=planet_rows();texts.insert(3,'Zone: pyro4 Pos: 1.0km 2.0km 3.0km')
    assert af.resolve_zone_identity(texts)[0] is None
