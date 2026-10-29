from pathlib import Path
import copy
import pytest
from streamlit.testing.v1 import AppTest
from schemas import content_hash
ROOT=Path(__file__).resolve().parents[1]

def test_home_without_key():
    app=AppTest.from_file(str(ROOT/'app.py'),default_timeout=40).run()
    assert not app.exception
    assert len(app.metric)==4
    app.selectbox(key='gh_language').set_value('Urdu').run()
    assert not app.exception

@pytest.mark.parametrize('page',['requirements_chat','floor_plans','model_3d','bim_ifc','schedule','estimation','labour','digital_twin','downloads','settings','engineering','workflow_chat','demo'])
def test_pages_with_reviewed_synthetic_workspace(page,demo):
    original,inputs=demo
    app=AppTest.from_file(str(ROOT/'app.py'),default_timeout=60).run()
    app.session_state['gharbuilder_workspace']=copy.deepcopy(original)
    app.session_state['gh_planning_envelope']=inputs['envelope']
    app.session_state['gh_envelope_requirements_hash']=content_hash(inputs['requirements'])
    app.session_state['gh_envelope_compliance_hash']=content_hash(inputs['compliance'])
    app.session_state['gh_model_input']=inputs['model_input']
    app.session_state['gh_requirements_draft']=inputs['requirements'].model_dump_json()
    app.switch_page('pages/'+page+'.py').run()
    assert not app.exception
