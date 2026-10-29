from pathlib import Path
from types import SimpleNamespace as Obj
import pytest
from streamlit.testing.v1 import AppTest
from ui.editors import flatten,unflatten,parsed_rows,fill_missing_recipes
from tools.cost import RateCatalog,Milestone
from config import load_json
ROOT=Path(__file__).resolve().parents[1]


def test_evidence_table_roundtrip_preserves_unknown_prices():
    catalog=load_json(ROOT/'data/rates_pk.json',RateCatalog)
    data=catalog.model_dump(mode='json')
    data['rates']=[unflatten(flatten(row)) for row in data['rates']]
    result=RateCatalog.model_validate(data)
    assert result==catalog
    assert result.rates[0].value_pkr is None


def test_fill_recipe_choices_preserves_user_values_and_unknowns():
    rows=[{'kind':'slab','productive_days':5,'crew_size':None,'curing_days':None}]
    result=fill_missing_recipes(rows,productive_days=3,crew_size=4)
    assert result[0]=={'kind':'slab','productive_days':5,'crew_size':4,'curing_days':None}
    assert rows[0]['crew_size'] is None


def test_requirement_controls_offer_design_choices_and_room_pattern():
    app=AppTest.from_file(str(ROOT/'app.py'),default_timeout=60).run()
    app.button(key='gh_form_without_ai').click().run()
    style=next(x for x in app.selectbox if x.label=='Architectural style')
    assert {'Modern','Contemporary','Architect to advise'}<=set(style.options)
    assert any(x.label=='Accessibility needs' for x in app.multiselect)
    next(x for x in app.selectbox if x.label=='Starting room counts for each floor').set_value('2 bedrooms, 2 bathrooms, 1 kitchen').run()
    frame=app.dataframe[0].value
    assert frame.iloc[0]['bedrooms']==2 and frame.iloc[0]['kitchens']==1


def test_account_model_choices_load_only_on_request(monkeypatch):
    calls=[]
    monkeypatch.setattr('ui.components.available_model_ids',lambda credentials:(calls.append(True) or ['account-model-a','account-model-b']))
    app=AppTest.from_file(str(ROOT/'app.py'),default_timeout=60).run()
    assert not calls
    app.text_input(key='gh_api_key').set_value('offline-not-real').run()
    app.button(key='gh_load_models').click().run()
    assert not app.exception and calls==[True]
    assert {'account-model-a','account-model-b'}<=set(app.selectbox(key='gh_model_id').options)


@pytest.mark.parametrize('page',['estimation','schedule','settings','engineering'])
def test_common_module_inputs_do_not_require_json(page,demo):
    import copy
    from schemas import content_hash
    state,inputs=demo
    app=AppTest.from_file(str(ROOT/'app.py'),default_timeout=90).run()
    app.session_state['gharbuilder_workspace']=copy.deepcopy(state)
    app.session_state['gh_planning_envelope']=inputs['envelope']
    app.session_state['gh_envelope_requirements_hash']=content_hash(inputs['requirements'])
    app.session_state['gh_envelope_compliance_hash']=content_hash(inputs['compliance'])
    app.switch_page('pages/'+page+'.py').run()
    assert not app.exception
    assert not any('JSON' in field.label for field in app.text_area)


def test_guided_settings_apply_preserves_unpriced_values():
    app=AppTest.from_file(str(ROOT/'app.py'),default_timeout=90).run()
    app.switch_page('pages/settings.py').run()
    next(c for c in app.checkbox if c.label=='I reviewed the units, effective dates, source evidence and scope').check()
    next(b for b in app.button if b.label=='Apply validated session settings').click().run()
    assert not app.exception
    catalog=RateCatalog.model_validate(app.session_state['gh_config_rates_pk.json'])
    assert catalog.rates[0].value_pkr is None


def test_estimate_table_controls_generate_real_result(demo):
    import copy
    from schemas import Stage,content_hash
    state,inputs=demo
    app=AppTest.from_file(str(ROOT/'app.py'),default_timeout=90).run()
    app.session_state['gharbuilder_workspace']=copy.deepcopy(state)
    app.session_state['gh_planning_envelope']=inputs['envelope']
    app.session_state['gh_envelope_requirements_hash']=content_hash(inputs['requirements'])
    app.session_state['gh_envelope_compliance_hash']=content_hash(inputs['compliance'])
    app.switch_page('pages/estimation.py').run()
    next(c for c in app.checkbox if c.label=='I reviewed the benchmark scope and excluded extras').check().run()
    next(c for c in app.checkbox if c.key and c.key.startswith('gh_review_input_cost_')).check().run()
    app.button(key='gh_run_cost').click().run()
    assert not app.exception
    workspace=app.session_state['gharbuilder_workspace']
    assert workspace.record(Stage.COST).status=='review'
    assert workspace.outputs[Stage.COST].construction_pkr is not None
