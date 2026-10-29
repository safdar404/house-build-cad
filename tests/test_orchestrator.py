"""Prepared workflow execution must have a separate, exact user authorization."""
from types import SimpleNamespace
import pytest
from config import Credentials,Settings
from schemas import Stage,content_hash
from agents.orchestrator import OrchestratorAgent
from ui.state import WorkspaceState,WorkflowError


def test_prepared_generation_requires_current_input_review(concept):
    req,_,_=concept
    state=WorkspaceState()
    agent=OrchestratorAgent(state=state,settings=Settings(model='offline-test'),
        credentials=Credentials(api_key='offline-test-key'),client=SimpleNamespace())
    calls=[]
    agent.prepare(Stage.REQUIREMENTS,req,lambda value:(calls.append(value) or value))
    with pytest.raises(WorkflowError):agent.execute(Stage.REQUIREMENTS)
    assert not calls
    agent.authorize_prepared(Stage.REQUIREMENTS,reviewed_hash=content_hash(req),user_approved=True)
    result=agent.execute(Stage.REQUIREMENTS)
    assert result['status']=='review' and len(calls)==1
    with pytest.raises(WorkflowError):state.get_output(Stage.REQUIREMENTS)
    changed=req.model_copy(update={'city':'Different city'})
    agent.prepare(Stage.REQUIREMENTS,changed,lambda value:(calls.append(value) or value))
    with pytest.raises(WorkflowError):agent.execute(Stage.REQUIREMENTS)
    assert len(calls)==1
