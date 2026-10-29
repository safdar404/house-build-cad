"""Prepare typed agent tools from current project data; never execute or approve."""
from schemas import Stage,content_hash
from ui.state import WorkflowError
from ui.workflow import read_config,today
from agents.compliance_agent import ComplianceInput
from agents.orchestrator import PlanningStageInput
from agents.cad_agent import CADInput
from agents.modeling_agent import ModelingInput,ModelingAgent
from tools.model_3d import ModelOptions
from tools.bim_ifc import BIMInput


def prepare_available(runtime,session):
    state=runtime.workspace;agent=runtime.orchestrator;prepared=[]
    def needed(stage):return state.record(stage).status not in {'review','approved'}
    def register(stage,request,context=None):
        agent.prepare_specialist(stage,request,context=context);prepared.append(stage.value)
    try:req=state.get_output(Stage.REQUIREMENTS)
    except WorkflowError:return ['Confirm your project brief in Requirements Chat first.']
    if needed(Stage.COMPLIANCE):
        register(Stage.COMPLIANCE,ComplianceInput(requirements=req,assessment_date=today()),read_config('bylaws.json'))
    try:compliance=state.get_output(Stage.COMPLIANCE)
    except WorkflowError:return prepared
    env=session.get('gh_planning_envelope')
    if (env is None or session.get('gh_envelope_requirements_hash')!=content_hash(req)
        or session.get('gh_envelope_compliance_hash')!=content_hash(compliance)):
        return prepared+['Review and save the current concept envelope in Floor Plans.']
    if needed(Stage.PLANNING):
        register(Stage.PLANNING,PlanningStageInput(requirements=req,envelope=env,revision_request=state.revision_notes.get(Stage.PLANNING,'')))
        return prepared
    try:
        layout=state.selected_layout();planning=state.get_output(Stage.PLANNING)
        option=next(a for a in planning.alternatives if a.layout.id==layout.id)
    except (WorkflowError,StopIteration):return prepared+['Select an approved floor alternative in Floor Plans.']
    if needed(Stage.CAD):register(Stage.CAD,CADInput(layout=layout,requirements=req,envelope=env,access=option.access))
    if needed(Stage.MODEL):
        previous=session.get('gh_model_input')
        options=previous.options if previous and content_hash(previous.layout)==content_hash(layout) else ModelOptions(assumptions_accepted=True)
        request=ModelingInput(layout=layout,requirements=req,envelope=env,access=option.access,options=options)
        # Sizes/colours are proposed modelling options visible in the input review.
        # Authorization remains mandatory; preparing a request does not accept it.
        def build(value):
            result=ModelingAgent.build(value,reviewed_hash=content_hash(value),user_approved=True)
            session['gh_model_input']=value.model_copy(deep=True)
            return result
        agent.prepare(Stage.MODEL,request,build);prepared.append(Stage.MODEL.value)
    try:model=state.get_output(Stage.MODEL)
    except WorkflowError:return prepared
    model_input=session.get('gh_model_input')
    if needed(Stage.BIM) and model_input and content_hash(model_input)==model.input_hash and model_input.options.include_opening_infill:
        register(Stage.BIM,BIMInput(project_id=state.project.id,project_name=state.project.name,requirements=req,
            layout=layout,envelope=env,access=option.access,options=model_input.options,
            element_data=list(session.get('gh_bim_metadata_'+model.input_hash,{}).values())))
    return prepared
