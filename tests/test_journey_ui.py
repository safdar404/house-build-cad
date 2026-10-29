from pathlib import Path
from types import SimpleNamespace as Obj
from streamlit.testing.v1 import AppTest
from agents.orchestrator import OrchestratorAgent
from ui.journey import next_action
from ui.state import WorkspaceState
from schemas import Stage
ROOT=Path(__file__).resolve().parents[1]


def test_empty_workspace_has_next_input_action():
    label,path,_=next_action(WorkspaceState(),{})
    assert path=='pages/requirements_chat.py' and 'house details' in label


def test_key_without_model_gives_explicit_next_action(monkeypatch):
    monkeypatch.delenv('OPENAI_MODEL',raising=False)
    app=AppTest.from_file(str(ROOT/'app.py'),default_timeout=60).run()
    app.text_input(key='gh_api_key').set_value('offline-test-key-not-real')
    app.button(key='gh_connect_continue').click().run()
    assert not app.exception
    assert any('model ID' in x.value for x in app.error)
    assert any('Continue →' in x.label for x in app.get('page_link'))


def test_connect_success_opens_input_form(monkeypatch):
    monkeypatch.setattr('ui.components._probe',lambda *args:(True,'Offline test connection accepted.'))
    monkeypatch.setattr('ui.components.OrchestratorAgent',lambda **kwargs:OrchestratorAgent(**kwargs,client=Obj()))
    app=AppTest.from_file(str(ROOT/'app.py'),default_timeout=60).run()
    app.text_input(key='gh_api_key').set_value('offline-test-key-not-real')
    app.text_input(key='gh_model_id').set_value('offline-test')
    app.button(key='gh_connect_continue').click().run()
    assert not app.exception
    assert any(b.label=='Save project draft' for b in app.button)
    assert any(x.label=='City' for x in app.selectbox)
    assert app.session_state['gh_connection'][1] is True


def test_dark_theme_and_native_logo_render():
    app=AppTest.from_file(str(ROOT/'app.py'),default_timeout=60).run()
    app.selectbox(key='gh_theme').set_value('dark').run()
    assert not app.exception
    assert any('gh-brand-mark' in m.value and 'data:image/svg+xml;base64,' in m.value for m in app.markdown)
    styles='\n'.join(m.value for m in app.markdown if '<style>' in m.value)
    assert 'stHeader' in styles and 'stTopNav' in styles and '#1b253a!important' in styles

def test_floor_count_builds_input_rows_and_budget_starts_blank():
    app=AppTest.from_file(str(ROOT/'app.py'),default_timeout=60).run()
    app.button(key='gh_form_without_ai').click().run()
    assert not app.exception
    assert next(n for n in app.number_input if n.label=='Budget PKR').value is None
    app.number_input(key='gh_form_floor_count').set_value(3).run()
    assert not app.exception
    assert len(app.dataframe[0].value)==3

def test_dark_mode_preserves_prepared_agent_tools(concept):
    import hashlib
    from config import Credentials
    from ui.components import Runtime
    req,_,_=concept
    app=AppTest.from_file(str(ROOT/'app.py'),default_timeout=60).run()
    app.text_input(key='gh_api_key').set_value('offline-test-key-not-real')
    app.text_input(key='gh_model_id').set_value('offline-test').run()
    state=app.session_state['gharbuilder_workspace'];settings=app.session_state['gh_settings']
    credentials=Credentials(api_key='offline-test-key-not-real')
    agent=OrchestratorAgent(state=state,settings=settings,credentials=credentials,client=Obj())
    agent.prepare(Stage.REQUIREMENTS,req,lambda value:value)
    runtime=Runtime(settings,credentials,state,agent)
    app.session_state['gh_runtime']=runtime
    app.session_state['gh_runtime_signature']=hashlib.sha256((credentials.api_key.get_secret_value()+settings.model_dump_json(exclude={'theme'})).encode()).hexdigest()
    app.selectbox(key='gh_theme').set_value('dark').run()
    assert not app.exception
    assert app.session_state['gh_runtime'] is runtime
    assert Stage.REQUIREMENTS in runtime.orchestrator.tasks


def test_old_session_workspace_offers_explicit_recovery():
    app=AppTest.from_file(str(ROOT/'app.py'),default_timeout=60).run()
    app.session_state['gharbuilder_workspace']=object()
    app.run()
    assert not app.exception
    assert any('older app version' in warning.value for warning in app.warning)
    assert any(button.label=='Start a new workspace' for button in app.button)
    assert app.session_state['gharbuilder_workspace'] is not None
    next(button for button in app.button if button.label=='Start a new workspace').click().run()
    assert not app.exception
    assert app.session_state['gharbuilder_workspace'].project
