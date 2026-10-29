from types import SimpleNamespace as Obj
import copy,json
import pytest
from agents.orchestrator import OrchestratorAgent
from agents.project_context import project_context
from agents.base import AgentError
from config import Credentials,Settings
from schemas import Stage,content_hash
from ui.state import WorkspaceState,WorkflowError
from ui.agent_preparation import prepare_available

class FakeResponses:
    def __init__(self):self.calls=[]
    def create(self,**kwargs):
        self.calls.append(copy.deepcopy(kwargs))
        if len(self.calls)==1:
            return Obj(status='completed',output=[Obj(type='function_call',name='inspect_project',arguments='{}',call_id='inspect-1')],usage=None)
        return Obj(status='completed',output=[],output_text='Confirm the project brief, then review the constraints.',usage=None)

def make_agent(state,client=None):
    return OrchestratorAgent(state=state,settings=Settings(model='offline-test'),
        credentials=Credentials(api_key='test-secret-never-send'),client=client or Obj())

def test_llm_inspects_project_and_remembers_conversation():
    state=WorkspaceState();responses=FakeResponses();agent=make_agent(state,Obj(responses=responses))
    turn=agent.run_flow('What should I do next?',conversation=[{'role':'user','content':'My house project is in Lahore.'}])
    assert turn.tool_calls==1 and len(responses.calls)==2
    history=responses.calls[1]['input']
    assert any(row.get('content')=='My house project is in Lahore.' for row in history if isinstance(row,dict))
    output=next(row for row in history if isinstance(row,dict) and row.get('type')=='function_call_output')
    assert json.loads(output['output'])['stages'][0]['stage']=='requirements'
    assert 'test-secret-never-send' not in str(responses.calls)
    assert state.record(Stage.REQUIREMENTS).status=='pending'

def test_secret_history_blocked_before_api():
    responses=FakeResponses();agent=make_agent(WorkspaceState(),Obj(responses=responses))
    with pytest.raises(AgentError):agent.run_flow('Continue',conversation=[{'role':'user','content':'test-secret-never-send'}])
    assert not responses.calls

def test_automatic_preparation_requires_authorization_and_outputs_review(demo):
    state,inputs=demo;state=copy.deepcopy(state);state.invalidate(Stage.CAD)
    agent=make_agent(state);runtime=Obj(workspace=state,orchestrator=agent)
    session={'gh_planning_envelope':inputs['envelope'],'gh_envelope_requirements_hash':content_hash(inputs['requirements']),
        'gh_envelope_compliance_hash':content_hash(inputs['compliance'])}
    prepared=prepare_available(runtime,session)
    assert {'cad','model'}<=set(prepared)
    with pytest.raises(WorkflowError):agent.execute(Stage.CAD)
    task=agent.tasks[Stage.CAD]
    agent.authorize_prepared(Stage.CAD,reviewed_hash=content_hash(task.request),user_approved=True)
    agent.execute(Stage.CAD)
    assert state.record(Stage.CAD).status=='review'
    with pytest.raises(WorkflowError):state.get_output(Stage.CAD)
    assert not any(row['ready'] for row in project_context(state,agent.tasks)['stages'] if row['stage']=='model')

def test_agent_studio_prepares_tools_without_api_request(demo,monkeypatch):
    from pathlib import Path
    from streamlit.testing.v1 import AppTest
    state,inputs=demo;state=copy.deepcopy(state);state.invalidate(Stage.CAD)
    monkeypatch.setenv('OPENAI_API_KEY','offline-test-key-not-real')
    monkeypatch.setattr('ui.components.OrchestratorAgent',lambda **kwargs:OrchestratorAgent(**kwargs,client=Obj()))
    root=Path(__file__).resolve().parents[1]
    app=AppTest.from_file(str(root/'app.py'),default_timeout=90).run()
    app.session_state['gharbuilder_workspace']=state
    app.text_input(key='gh_api_key').set_value('offline-test-key-not-real')
    app.text_input(key='gh_model_id').set_value('offline-test')
    app.run()
    app.session_state['gh_planning_envelope']=inputs['envelope']
    app.session_state['gh_envelope_requirements_hash']=content_hash(inputs['requirements'])
    app.session_state['gh_envelope_compliance_hash']=content_hash(inputs['compliance'])
    app.switch_page('pages/workflow_chat.py').run()
    assert not app.exception
    app.button(key='gh_prepare_project_tools').click().run()
    assert not app.exception
    runtime=app.session_state['gh_runtime']
    assert Stage.CAD in runtime.orchestrator.tasks
    assert not runtime.workspace.authorized_inputs.get(Stage.CAD)
    assert not runtime.workspace.project.usage
    next(c for c in app.checkbox if c.key and c.key.startswith('gh_flow_review_cad_')).check().run()
    next(b for b in app.button if b.key and b.key.startswith('gh_flow_authorize_cad_')).click().run()
    assert not app.exception
    app.button(key='gh_flow_run_cad').click().run()
    assert not app.exception
    assert app.session_state['gharbuilder_workspace'].record(Stage.CAD).status=='review'

def test_llm_tool_call_generates_and_pauses_for_review(concept):
    req,_,_=concept;state=WorkspaceState()
    class Calls:
        def create(self,**kwargs):
            return Obj(status='completed',usage=None,output=[Obj(type='function_call',name='run_stage',arguments='{"stage":"requirements"}',call_id='run-1')])
    agent=make_agent(state,Obj(responses=Calls()))
    agent.prepare(Stage.REQUIREMENTS,req,lambda value:value)
    agent.authorize_prepared(Stage.REQUIREMENTS,reviewed_hash=content_hash(req),user_approved=True)
    turn=agent.run_flow('Run the authorized requirements tool.')
    assert turn.pending_review==Stage.REQUIREMENTS and turn.tool_calls==1
    assert state.record(Stage.REQUIREMENTS).status=='review'
    with pytest.raises(WorkflowError):state.get_output(Stage.REQUIREMENTS)
