import pytest
from ui.state import WorkspaceState,WorkflowError,output_hash
from schemas import Stage,content_hash
from tools.model_3d import ModelOptions,build_model

def test_review_gates_and_mutation(concept):
    req,env,planning=concept;state=WorkspaceState();key=content_hash(req)
    with pytest.raises(WorkflowError):state.start(Stage.REQUIREMENTS,req)
    state.authorize(Stage.REQUIREMENTS,req,reviewed_hash=key,user_approved=True)
    state.start(Stage.REQUIREMENTS,req);result=state.complete(Stage.REQUIREMENTS,req,req)
    with pytest.raises(WorkflowError):state.get_output(Stage.REQUIREMENTS)
    state.approve(Stage.REQUIREMENTS,reviewed_hash=result,user_approved=True)
    state.outputs[Stage.REQUIREMENTS].city='Changed'
    with pytest.raises(WorkflowError):state.get_output(Stage.REQUIREMENTS)
    assert state.record(Stage.REQUIREMENTS).status=='stale'

def test_mesh_metadata_fingerprint(concept):
    req,env,planning=concept
    model=build_model(planning.alternatives[0].layout,req,env,ModelOptions(assumptions_accepted=True))
    original=output_hash(model)
    assert original==output_hash(model)
    model.elements[0].mesh.vertices[0,0]+=.01
    assert original!=output_hash(model)

def test_wage_revision_does_not_invalidate_planning():
    state=WorkspaceState()
    assert Stage.PLANNING not in state.affected(Stage.LABOUR)
    assert Stage.REPORT in state.affected(Stage.LABOUR)
