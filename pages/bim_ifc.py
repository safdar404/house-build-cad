"""BIM element metadata editor, IFC4 generation, property inspection and download."""
from __future__ import annotations

import streamlit as st

from agents.base import AgentError
from agents.bim_agent import BIMAgent
from schemas import Stage,content_hash
from config import resolve_credentials
from tools.bim_ifc import BIMElementData,BIMInput,BIM_LEVELS,ifc_available
from ui.components import back_to_home,hero,render_review_gate,tr,_available_secrets
from ui.state import WorkflowError,get_workspace


def main() -> None:
    back_to_home();hero('🧩 '+tr('bim'),'Review stable element IDs, optional information and the exported IFC hierarchy.')
    workspace=get_workspace(st.session_state)
    try:
        model_result=workspace.get_output(Stage.MODEL)
        layout=workspace.selected_layout()
        requirements=workspace.get_output(Stage.REQUIREMENTS)
        planning=workspace.get_output(Stage.PLANNING)
    except WorkflowError:
        st.info('Build and approve the current 3D model before preparing IFC.');return
    model_input=st.session_state.get('gh_model_input')
    if model_input is None or content_hash(model_input)!=model_result.input_hash or content_hash(model_input.layout)!=content_hash(layout):
        st.error('The model inputs are absent or stale. Rebuild the selected layout on the 3D Model page.');return
    if not model_input.options.include_opening_infill:
        st.info('Enable door/window infill on the 3D Model page and rebuild before IFC export.');return
    option=next(a for a in planning.alternatives if a.layout.id==layout.id)
    ids=[e.id for e in model_result.model.elements]+[f.floor_id+'/space/'+r.id for f in layout.floors for r in f.rooms]
    cache_key='gh_bim_metadata_'+model_result.input_hash
    metadata=st.session_state.setdefault(cache_key,{})
    with st.expander('BIM information levels'):
        st.dataframe([{'Level':key,'Scope':value} for key,value in BIM_LEVELS.items()],hide_index=True)
        st.caption('Optional attributes do not establish a complete time, cost, sustainability or operational model.')
    st.subheader('Element information')
    selected=st.selectbox('Element / room',ids,key='gh_bim_selected_'+model_result.input_hash)
    stored=metadata.get(selected)
    # Element-scoped form keys avoid applying one element's widget state to another.
    with st.form('gh_bim_element_'+content_hash({'model':model_result.input_hash,'element':selected})):
        material=st.text_input('Material (leave blank if unspecified)',value=stored.material or '' if stored else '')
        has_cost=st.checkbox('A supplied cost allocation is available',value=stored is not None and stored.cost_pkr is not None)
        cost=st.number_input('Supplied element cost PKR',min_value=0.,value=float(stored.cost_pkr or 0) if stored else 0.,step=100.)
        phase=st.text_input('Phase',value=stored.phase or '' if stored else '')
        start=st.text_input('Planned start label (optional)',value=stored.planned_start or '' if stored else '')
        finish=st.text_input('Planned finish label (optional)',value=stored.planned_finish or '' if stored else '')
        sustainability=st.text_area('Supplied sustainability note',value=stored.sustainability_note or '' if stored else '')
        asset=st.text_input('Asset reference',value=stored.asset_reference or '' if stored else '')
        maintenance=st.text_area('Maintenance note',value=stored.maintenance_note or '' if stored else '')
        saved=st.form_submit_button('Save element information')
    if saved:
        data=BIMElementData(element_id=selected,material=material.strip() or None,cost_pkr=cost if has_cost else None,
            phase=phase.strip() or None,planned_start=start.strip() or None,planned_finish=finish.strip() or None,
            sustainability_note=sustainability.strip() or None,asset_reference=asset.strip() or None,
            maintenance_note=maintenance.strip() or None)
        try:credentials=resolve_credentials(st.session_state.get('gh_api_key',''),_available_secrets())
        except ValueError:credentials=None
        if credentials and credentials.api_key.get_secret_value() in data.model_dump_json():
            st.error('Remove the API key from element metadata before saving.');return
        if stored is None or content_hash(data)!=content_hash(stored):workspace.invalidate(Stage.BIM)
        metadata[selected]=data;st.success('Element information saved for this model snapshot.')
    with st.expander('Element register'):
        st.dataframe([{'Element ID':eid,'Material':metadata[eid].material if eid in metadata else None,
            'Cost PKR':metadata[eid].cost_pkr if eid in metadata else None,
            'Phase':metadata[eid].phase if eid in metadata else None} for eid in ids],hide_index=True)
    available=ifc_available()
    if not available:st.error('IFCOpenShell is unavailable. Install the supported wheel from requirements.txt to enable IFC export.')
    checked=st.checkbox('I reviewed the selected geometry, optional metadata and IFC concept limitations',key='gh_bim_review_'+model_result.input_hash)
    if st.button('Generate IFC4 concept model',disabled=not checked or not available,type='primary'):
        try:
            request=BIMInput(project_id=workspace.project.id,project_name=workspace.project.name,
                requirements=requirements,layout=layout,envelope=model_input.envelope,access=option.access,
                options=model_input.options,element_data=list(metadata.values()))
            key=content_hash(request)
            workspace.authorize(Stage.BIM,request,reviewed_hash=key,user_approved=True)
            workspace.start(Stage.BIM,request)
            try:
                with st.spinner('Building and validating IFC4...'):
                    result=BIMAgent.export(request,reviewed_hash=key,user_approved=True)
                workspace.complete(Stage.BIM,request,result)
            except Exception:workspace.fail(Stage.BIM);raise
            st.rerun()
        except (AgentError,WorkflowError) as error:st.error(str(error))
        except ValueError:st.error('Invalid IFC inputs. Review the current element IDs and metadata.')
    if workspace.record(Stage.BIM).status not in {'review','approved'}:return
    exported=workspace.outputs[Stage.BIM]
    st.subheader('Exported hierarchy and properties')
    st.dataframe([{'IFC class':name,'Count':count} for name,count in exported.counts.items()],hide_index=True)
    property_id=st.selectbox('Inspect exported element',list(exported.element_guids),key='gh_ifc_property_'+exported.input_hash)
    # Native IFC parsing stays inside this page; it is never called if unavailable.
    if available:
        import ifcopenshell
        import ifcopenshell.util.element
        parse_key='gh_ifc_file_'+exported.input_hash
        native=st.session_state.get(parse_key)
        if native is None:
            native=ifcopenshell.file.from_string(exported.content.decode('utf-8'))
            # Keep only the current parsed IFC model in this user's session.
            for key in list(st.session_state):
                if key.startswith('gh_ifc_file_'):st.session_state.pop(key,None)
            st.session_state[parse_key]=native
        product=native.by_guid(exported.element_guids[property_id])
        st.json({'IFC class':product.is_a(),'GlobalId':product.GlobalId,
                 'Property sets':ifcopenshell.util.element.get_psets(product)},expanded=False)
    with st.expander('IFC limitations'):
        for warning in exported.warnings:st.write(warning)
    render_review_gate(Stage.BIM)
    try:approved=workspace.get_output(Stage.BIM)
    except WorkflowError:return
    st.download_button('Download reviewed IFC4',approved.content,file_name=approved.filename,mime='application/x-step')


main()
