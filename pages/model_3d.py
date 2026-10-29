"""Selected-plan 3D controls, reviewed modelling assumptions and mesh exports."""
from __future__ import annotations

import streamlit as st

from agents.base import AgentError
from agents.modeling_agent import ModelingAgent,ModelingInput
from schemas import Stage,content_hash
from tools.model_3d import ModelOptions,plotly_figure
from ui.components import back_to_home,hero,render_review_gate,tr
from ui.state import WorkflowError,get_workspace


def main() -> None:
    back_to_home();hero('🏠 '+tr('model'),'Inspect plan-derived geometry, floor visibility and assembled mesh exports.')
    workspace=get_workspace(st.session_state)
    try:
        requirements=workspace.get_output(Stage.REQUIREMENTS)
        layout=workspace.selected_layout()
        planning=workspace.get_output(Stage.PLANNING)
    except WorkflowError:
        st.info('Confirm requirements and select a reviewed layout in Floor Plans first.');return
    envelope=st.session_state.get('gh_planning_envelope')
    if envelope is None or st.session_state.get('gh_envelope_requirements_hash')!=content_hash(requirements):
        st.info('Review the concept envelope for the current brief in Floor Plans.');return
    option=next(a for a in planning.alternatives if a.layout.id==layout.id)
    with st.expander('Model geometry and colour assumptions',expanded=workspace.record(Stage.MODEL).status not in {'review','approved'}):
        st.caption('Slab/parapet dimensions and schematic straight stairs are modelling assumptions, not structural designs.')
        with st.form('gh_model_form'):
            cols=st.columns(3)
            slab=cols[0].number_input('Slab thickness m',min_value=.01,value=.15,step=.01)
            parapet=cols[1].number_input('Parapet height m',min_value=0.,value=.9,step=.1)
            parapet_width=cols[2].number_input('Parapet thickness m',min_value=.01,value=.115,step=.005,format='%.3f')
            colours=st.columns(5)
            names=['wall','slab','door','window','stair']
            defaults=['#E8DBCC','#A8B5C4','#986641','#65C7EB','#B4A7CF']
            selected={name:column.color_picker(name.title()+' colour',default) for column,name,default in zip(colours,names,defaults)}
            roof=st.checkbox('Include roof and parapet',value=True)
            infill=st.checkbox('Include door and window infill',value=True,help='Enable this option for semantic IFC door/window export.')
            accepted=st.checkbox('I accept these sizes and schematic stairs for concept modelling only')
            generate=st.form_submit_button('Build 3D concept model')
        if generate:
            if not accepted:st.warning('Review and accept the modelling assumptions before building.')
            else:
                try:
                    options=ModelOptions(slab_thickness_m=slab,parapet_height_m=parapet,
                        parapet_thickness_m=parapet_width,include_roof=roof,include_opening_infill=infill,
                        assumptions_accepted=True,**{name+'_colour':value for name,value in selected.items()})
                    request=ModelingInput(layout=layout,requirements=requirements,envelope=envelope,access=option.access,options=options)
                    key=content_hash(request)
                    workspace.authorize(Stage.MODEL,request,reviewed_hash=key,user_approved=True)
                    workspace.start(Stage.MODEL,request)
                    try:
                        with st.spinner('Building plan-derived meshes...'):
                            result=ModelingAgent.build(request,reviewed_hash=key,user_approved=True)
                        workspace.complete(Stage.MODEL,request,result)
                    except Exception:workspace.fail(Stage.MODEL);raise
                    st.session_state['gh_model_input']=request
                    st.rerun()
                except (ValueError,AgentError,WorkflowError) as error:
                    st.error(str(error) if isinstance(error,(AgentError,WorkflowError)) else 'Invalid model assumptions. Check dimensions and storey heights.')
    if workspace.record(Stage.MODEL).status not in {'review','approved'}:return
    result=workspace.outputs[Stage.MODEL]
    cols=st.columns([2,1,1])
    floors=cols[0].multiselect('Visible floors',list(result.model.floor_ids),default=list(result.model.floor_ids),key='gh_visible_floors_'+result.input_hash)
    gap=cols[1].slider('Exploded gap m',0.,6.,0.,.25,key='gh_exploded_'+result.input_hash)
    show_roof=cols[2].checkbox('Show roof',value=True,key='gh_show_roof_'+result.input_hash)
    st.plotly_chart(plotly_figure(result.model,visible_floor_ids=floors,exploded_gap_m=gap,show_roof=show_roof,
        theme=st.session_state.get('gh_theme','light')),key='gh_model_view_'+result.input_hash)
    st.caption('Display filters and exploded gaps do not alter the assembled exports. Review the current model snapshot before downloading.')
    with st.expander('Geometry assumptions and review items'):
        for warning in result.warnings:st.write(warning)
    render_review_gate(Stage.MODEL)
    try:approved=workspace.get_output(Stage.MODEL)
    except WorkflowError:return
    if st.button('Prepare reviewed GLB/OBJ exports'):
        try:
            st.session_state['gh_mesh_export']=(approved.input_hash,ModelingAgent.export(approved))
        except AgentError as error:st.error(str(error))
    cached=st.session_state.get('gh_mesh_export')
    if cached and cached[0]==approved.input_hash:
        st.download_button('Download assembled GLB/OBJ ZIP',cached[1],file_name='GharBuilder_3D_Model.zip',mime='application/zip')
    if st.button('Continue to BIM & IFC →'):st.switch_page('pages/bim_ifc.py')


main()
