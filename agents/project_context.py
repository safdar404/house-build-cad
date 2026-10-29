"""Credential-free context and readiness for the agent and its dashboard."""
from schemas import Stage,content_hash
from ui.state import WorkflowError

STAGE_PAGES={Stage.REQUIREMENTS:'requirements_chat',Stage.COMPLIANCE:'floor_plans',Stage.PLANNING:'floor_plans',
    Stage.CAD:'floor_plans',Stage.MODEL:'model_3d',Stage.STRUCTURAL:'engineering',Stage.MEP:'engineering',
    Stage.BIM:'bim_ifc',Stage.SCHEDULE:'schedule',Stage.COST:'estimation',Stage.LABOUR:'labour',
    Stage.TWIN:'digital_twin',Stage.REPORT:'downloads'}


def project_context(state,tasks):
    rows=[]
    for stage in Stage:
        task=tasks.get(stage);ready=False;reason='Prepare and review inputs on the stage page.'
        record=state.record(stage)
        if task and record.status not in {'review','approved','running'}:
            try:state.ensure_ready(stage,task.request);ready=True;reason='Authorized inputs and approved prerequisites are ready.'
            except WorkflowError as error:reason=str(error)
        if record.status=='approved':reason='Current output is approved. Open the stage page to revise or regenerate.'
        rows.append(dict(stage=stage.value,status=record.status,prepared=task is not None,
            authorized=bool(task and state.authorized_inputs.get(stage)==content_hash(task.request)),ready=ready,
            next_action='Review generated output.' if record.status=='review' else reason,
            page='pages/'+STAGE_PAGES[stage]+'.py'))
    context={'project_name':state.project.name,'stages':rows,'revision_notes':{s.value:n for s,n in state.revision_notes.items()}}
    try:
        req=state.get_output(Stage.REQUIREMENTS)
        context['confirmed_requirements']=req.model_dump(mode='json')
    except WorkflowError:pass
    try:
        layout=state.selected_layout()
        context['selected_layout']={'id':layout.id,'title':layout.title,'floors':[{
            'id':f.floor_id,'width_m':f.width_m,'depth_m':f.depth_m,
            'rooms':[{'id':r.id,'name':r.name,'kind':r.kind,'area_m2':round(r.area_m2,2)} for r in f.rooms]} for f in layout.floors]}
    except WorkflowError:pass
    return context
