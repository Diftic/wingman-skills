from collections import OrderedDict
import numpy as np
from frame_reader import FrameAwareReader
from test_active_frame import planet_rows

def reader_for(texts):
    reader=FrameAwareReader.__new__(FrameAwareReader)
    reader._identity_cache=OrderedDict()
    calls=[]
    def recognize(frame,index):
        calls.append(index)
        return texts.get(index,'FPS: 60')
    reader._recognize_band=recognize
    return reader,calls

def test_zone_identity_never_caches_coordinates_or_repeats_a_band():
    texts=dict(enumerate(planet_rows()))
    texts[8]='Current player location : Pyro3';texts[9]='Planet:pyro3 (Load Complete)'
    reader,calls=reader_for(texts);frame=np.zeros((500,675,3),dtype=np.uint8)
    _,_,rows=reader.read(frame)
    assert calls==[0,1,2,3,4]
    payload,_=reader.capture_payload(rows)
    assert payload['planet_identity']['planet_id']=='pyro3'
    calls.clear();texts[2]=texts[2].replace('330.7421','331.7421')
    _,_,rows=reader.read(frame)
    assert calls==[0,1,2,3,4]
    assert reader.capture_payload(rows)[0]['pos_raw'][0]=='331.7421km'

def test_frame_change_uses_fresh_zone_names_and_never_reuses_planet_position():
    texts=dict(enumerate(planet_rows()));texts[9]='Planet:pyro3'
    reader,calls=reader_for(texts);frame=np.zeros((500,675,3),dtype=np.uint8)
    reader.read(frame);calls.clear()
    texts[2]='Zone: station_segment Pos: 1.0m 2.0m 3.0m'
    texts[8]='Current player location : PyroSolarSystem'
    _,_,rows=reader.read(frame)
    assert calls==[0,1,2,3,4] and rows[0]['frame_identity'] is None
    assert rows[0]['frame_identity_reason']=='unknown_zone_name'

def test_missing_planet_metadata_does_not_block_known_planet_zone():
    reader,calls=reader_for(dict(enumerate(planet_rows())))
    _,_,rows=reader.read(np.zeros((500,675,3),dtype=np.uint8))
    assert reader.capture_payload(rows)[0]['planet_identity']['planet_id']=='pyro3'
    assert len(calls)==len(set(calls))

def test_unreadable_coordinates_and_metadata_still_produce_a_ring_status():
    import overlay_fields
    texts={i:t.replace('Pos:','Pos: ?') for i,t in enumerate(planet_rows())}
    reader,_=reader_for(texts)
    _,_,rows=reader.read(np.zeros((500,675,3),dtype=np.uint8))
    assert isinstance(overlay_fields.ring_state(rows,None,True),str)
