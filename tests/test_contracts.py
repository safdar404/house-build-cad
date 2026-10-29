import pytest
from pydantic import ValidationError
from schemas import Plot,Usage,content_hash
from config import Credentials
from tools.geometry import validate_layout

def test_geometry_and_units(concept):
    req,env,planning=concept
    assert req.plot.area_sqft==pytest.approx(2250)
    assert len(planning.alternatives)==2
    for option in planning.alternatives:
        assert validate_layout(option.layout,req,env,option.access).valid

def test_room_overlap_blocks_approval(concept):
    req,env,planning=concept
    option=planning.alternatives[0].model_copy(deep=True)
    option.layout.floors[0].rooms[1].x=option.layout.floors[0].rooms[0].x
    with pytest.raises(ValueError):validate_layout(option.layout,req,env,option.access)

def test_invalid_declared_area_and_usage():
    with pytest.raises(ValidationError):Plot(width_m=10,depth_m=10,facing='N',declared_area_sqft=200)
    with pytest.raises(ValidationError):Usage(model='test',input_tokens=1,cached_input_tokens=2)

def test_key_excluded_and_hash_stable():
    credentials=Credentials(api_key='test-secret')
    assert credentials.model_dump()=={}
    assert 'test-secret' not in repr(credentials)
    assert content_hash({'a':1,'b':2})==content_hash({'b':2,'a':1})
