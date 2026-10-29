"""Exercise user actions, not only page rendering."""
from pathlib import Path
from streamlit.testing.v1 import AppTest
from schemas import Stage
ROOT=Path(__file__).resolve().parents[1]

def test_form_save_confirm_and_navigation():
    app=AppTest.from_file(str(ROOT/'app.py'),default_timeout=60).run()
    assert any('Start / edit' in link.label for link in app.get('page_link'))
    app.switch_page('pages/requirements_chat.py').run()
    def field(kind,label):return next(x for x in getattr(app,kind) if x.label==label)
    for label,value in [('City','Lahore'),('Housing authority / society','User supplied society'),('Architectural style','Modern'),('Stairs position / preference','Front right'),('Drawing / dining arrangement','Separate')]:
        field('text_input',label).set_value(value)
    field('number_input','Budget PKR').set_value(10000000.)
    field('checkbox','I checked these form values, including dimensions, floor heights and room counts').check()
    field('button','Save project draft').click().run()
    assert not app.exception
    field('checkbox','I reviewed all facts, floor choices, units and assumptions in this brief').check().run()
    field('button','Confirm requirements').click().run()
    assert not app.exception
    state=app.session_state['gharbuilder_workspace']
    assert state.get_output(Stage.REQUIREMENTS).city=='Lahore'
    field('button','Continue to Floor Plans →').click().run()
    assert not app.exception
    assert any(x.label=='Generate bylaw review' for x in app.button)

def test_build_model_action_changes_workflow(demo):
    import copy
    from schemas import content_hash
    state,inputs=demo
    app=AppTest.from_file(str(ROOT/'app.py'),default_timeout=60).run()
    app.session_state['gharbuilder_workspace']=copy.deepcopy(state)
    app.session_state['gh_planning_envelope']=inputs['envelope']
    app.session_state['gh_envelope_requirements_hash']=content_hash(inputs['requirements'])
    app.session_state['gh_envelope_compliance_hash']=content_hash(inputs['compliance'])
    app.switch_page('pages/model_3d.py').run()
    next(x for x in app.checkbox if x.label=='I accept these sizes and schematic stairs for concept modelling only').check()
    next(x for x in app.button if x.label=='Build 3D concept model').click().run()
    assert not app.exception
    workspace=app.session_state['gharbuilder_workspace']
    assert workspace.record(Stage.MODEL).status=='review'
    assert workspace.record(Stage.BIM).status=='stale'
    assert workspace.outputs[Stage.MODEL].model.elements
