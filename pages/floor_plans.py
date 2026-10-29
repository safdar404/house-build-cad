"""Bylaw evidence review, confirmed envelope, alternatives and CAD downloads."""
from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

import streamlit as st
from ui.choices import choose

from agents.base import AgentError
from agents.compliance_agent import ComplianceAgent,ComplianceInput,load_bylaws
from agents.orchestrator import PlanningStageInput
from agents.planning_agent import PlanningAgent,PlanningOutput
from agents.cad_agent import CADAgent,CADInput
from config import ConfigurationError
from ui.workflow import read_config
from schemas import FloorPlan,Stage,content_hash
from tools.cad_2d import floor_plan,render_png
from tools.geometry import PlanningEnvelope
from ui.components import back_to_home,get_runtime,hero,render_review_gate,tr
from ui.state import WorkflowError,get_workspace


def _local_generate(stage,request,operation):
    workspace=get_workspace(st.session_state)
    key=content_hash(request)
    workspace.authorize(stage,request,reviewed_hash=key,user_approved=True)
    workspace.start(stage,request)
    try:
        result=operation(request)
        workspace.complete(stage,request,result)
    except Exception:
        workspace.fail(stage)
        raise


def _preview(floor: FloorPlan) -> bytes:
    """Private per-session preview cache, never a cross-user Streamlit data cache."""
    cache=st.session_state.setdefault('gh_plan_previews',{})
    key=content_hash(floor)
    if key not in cache:
        if len(cache)>=24:cache.pop(next(iter(cache)))
        cache[key]=render_png(floor_plan(floor))
    return cache[key]


def main() -> None:
    back_to_home();hero('📐 '+tr('plans'),'Review constraints, compare coordinated alternatives and inspect every floor.')
    workspace=get_workspace(st.session_state)
    try:requirements=workspace.get_output(Stage.REQUIREMENTS)
    except WorkflowError:
        st.info('Confirm your requirements in Requirements Chat before planning.');return
    with st.expander('1. Bylaw evidence review',expanded=workspace.record(Stage.COMPLIANCE).status!='approved'):
        try:database=read_config('bylaws.json')
        except ConfigurationError:
            st.error('The bylaw configuration is missing or invalid. Restore data/bylaws.json or correct it in Rates Settings.');return
        assessment_date=st.date_input('Bylaw assessment date',value=datetime.now(ZoneInfo('Asia/Karachi')).date(),key='gh_bylaw_date')
        st.caption('Rules must match the actual authority and plot category. Missing rules remain undetermined; this check is not authority approval.')
        consent=st.checkbox('I reviewed the selected city/authority and the assessment date',key='gh_bylaw_consent_'+content_hash(database)+assessment_date.isoformat())
        if st.button('Generate bylaw review',disabled=not consent):
            request=ComplianceInput(requirements=requirements,assessment_date=assessment_date)
            try:
                _local_generate(Stage.COMPLIANCE,request,lambda value:ComplianceAgent.evaluate(value,database));st.rerun()
            except (ValueError,AgentError,WorkflowError):st.error('Bylaw review failed. Check the authority data and assessment date.')
        report=workspace.outputs.get(Stage.COMPLIANCE)
        if report and workspace.record(Stage.COMPLIANCE).status in {'review','approved'}:
            st.write('Preliminary numerical status: **'+report.status+'**')
            st.dataframe([{'Rule':i.rule_id,'Status':i.status,'Finding':i.explanation} for i in report.issues],hide_index=True)
            render_review_gate(Stage.COMPLIANCE)
    try:compliance=workspace.get_output(Stage.COMPLIANCE)
    except WorkflowError:
        st.info('Review and acknowledge the bylaw evidence result before setting a concept envelope.');return
    with st.expander('2. Concept envelope',expanded='gh_planning_envelope' not in st.session_state):
        st.warning('Setbacks below are concept assumptions. Acknowledging missing or failed rules does not establish legal compliance.')
        units=st.selectbox('Setback units',['metres','feet'],key='gh_setback_units')
        columns=st.columns(4);values=[]
        for column,label in zip(columns,['Front','Rear','Left','Right']):
            values.append(column.number_input(label+' setback',min_value=0.,value=0.,step=.1,key='gh_setback_'+label.lower()))
        source=choose(st,'Source / assumption note',['User-proposed concept setbacks; authority review pending','Architect-supplied concept envelope – reference to be checked','Survey / authority document supplied for review'],'User-proposed concept setbacks; authority review pending',key='gh_envelope_source')
        confirmed=st.checkbox('I accept these setbacks for concept exploration and understand authority review is still required',key='gh_envelope_consent')
        if st.button('Save concept envelope',disabled=not confirmed or not source.strip()):
            factor=.3048 if units=='feet' else 1
            parameters=dict(zip(['front_m','rear_m','left_m','right_m'],[v*factor for v in values]))
            try:
                envelope=PlanningEnvelope(**parameters,source=source.strip(),status='concept_assumptions',confirmed=True,
                    reference_hash=content_hash({'compliance':compliance.model_dump(mode='json'),'setbacks':parameters,'source':source.strip()}))
                envelope.dimensions(requirements)
                previous=st.session_state.get('gh_planning_envelope')
                if previous is None or content_hash(previous)!=content_hash(envelope):workspace.invalidate(Stage.PLANNING)
                st.session_state['gh_planning_envelope']=envelope
                st.session_state['gh_envelope_requirements_hash']=content_hash(requirements)
                st.session_state['gh_envelope_compliance_hash']=content_hash(compliance)
                st.rerun()
            except ValueError:st.error('Those setbacks leave no positive building envelope. Check dimensions and units.')
    envelope=st.session_state.get('gh_planning_envelope')
    if (envelope is None or st.session_state.get('gh_envelope_requirements_hash')!=content_hash(requirements)
        or st.session_state.get('gh_envelope_compliance_hash')!=content_hash(compliance)):
        st.info('Save a concept envelope for the current brief and bylaw review before generating alternatives.');return
    width,depth=envelope.dimensions(requirements)
    st.caption(f'Confirmed concept envelope: {width:.2f} × {depth:.2f} m. Front/left plot offsets: {envelope.front_m:.2f}/{envelope.left_m:.2f} m.')
    runtime=get_runtime(required=False)
    with st.expander('3. Generate or revise alternatives',expanded=workspace.record(Stage.PLANNING).status not in {'approved','review'}):
        goals=st.multiselect('Layout improvement choices',['Increase bedroom space','Improve daylight','Improve cross-ventilation','Reduce corridor space','Improve privacy','Add storage','Improve accessibility','Separate visitor and family areas'])
        revision=st.text_area('Requested layout change (optional)',value=workspace.revision_notes.get(Stage.PLANNING,''),key='gh_layout_revision',
            help='For changes to plot size, floors or room counts, update Requirements Chat first.')
        if goals:revision=(revision+'\nRequested priorities: '+', '.join(goals)).strip()
        st.json({'requirements':requirements.model_dump(mode='json'),'envelope':envelope.model_dump(mode='json')},expanded=False)
        accepted=st.checkbox('I reviewed the confirmed brief, concept envelope and requested revision',key='gh_planning_input_consent')
        if runtime is None:st.info('Enter an API key and model ID to generate layout alternatives.')
        if st.button('Generate 2–3 alternatives',disabled=not accepted or runtime is None,type='primary'):
            try:
                if runtime.credentials.api_key.get_secret_value() in revision:
                    raise AgentError('Remove the API key from the revision request.')
                request=PlanningStageInput(requirements=requirements,envelope=envelope,revision_request=revision)
                key=runtime.orchestrator.prepare_specialist(Stage.PLANNING,request)
                runtime.orchestrator.authorize_prepared(Stage.PLANNING,reviewed_hash=key,user_approved=True)
                with st.spinner('Generating coordinated floor alternatives...'):runtime.orchestrator.execute(Stage.PLANNING)
                st.rerun()
            except (AgentError,WorkflowError) as error:st.error(str(error))
    planning=workspace.outputs.get(Stage.PLANNING)
    if planning is None or workspace.record(Stage.PLANNING).status not in {'review','approved'}:return
    try:planning=PlanningOutput.model_validate(planning.model_dump(mode='json'))
    except ValueError:st.error('The planning result is invalid. Regenerate the alternatives.');return
    for tab,option in zip(st.tabs([a.layout.title for a in planning.alternatives]),planning.alternatives):
        with tab:
            st.write(option.layout.rationale)
            assessment=PlanningAgent.assess(option,requirements,envelope)
            if not assessment.valid:st.error('This alternative failed geometry checks and cannot be selected.')
            for floor_tab,floor in zip(st.tabs([f.floor_id for f in option.layout.floors]),option.layout.floors):
                with floor_tab:
                    st.image(_preview(floor),width=700,caption='Concept zones measured to wall centre lines; review clear dimensions separately.')
            with st.expander('Geometry findings and unresolved items'):
                st.dataframe([i.model_dump() for i in assessment.issues],hide_index=True)
                for item in option.layout.unresolved_issues:st.write(item)
            if workspace.record(Stage.PLANNING).status=='approved':
                checked=st.checkbox('I reviewed this alternative and its warnings',key='gh_select_review_'+content_hash(option))
                if st.button('Select '+option.layout.title,key='gh_select_'+option.layout.id,disabled=not checked or not assessment.valid):
                    try:
                        workspace.select_layout(option,requirements,envelope,reviewed_hash=content_hash(option),user_approved=True)
                        st.session_state['gh_selected_access']=option.access
                        st.session_state['gh_selected_option_hash']=content_hash(option)
                        st.rerun()
                    except (AgentError,WorkflowError) as error:st.error(str(error))
    render_review_gate(Stage.PLANNING)
    try:selected=workspace.selected_layout()
    except WorkflowError:return
    st.success('Selected concept: '+selected.id)
    option=next(a for a in planning.alternatives if a.layout.id==selected.id)
    # Access is recovered from the approved alternative, not an unchecked session copy.
    request=CADInput(layout=selected,requirements=requirements,envelope=envelope,access=option.access)
    if st.button('Generate selected-plan drawings'):
        try:
            with st.spinner('Rendering PNG and DXF drawings...'):
                _local_generate(Stage.CAD,request,lambda value:CADAgent.export(value,reviewed_hash=content_hash(value),user_approved=True))
            st.rerun()
        except (AgentError,WorkflowError,ValueError):st.error('CAD generation failed. Check the selected layout and drawing dependencies.')
    render_review_gate(Stage.CAD)
    try:drawings=workspace.get_output(Stage.CAD)
    except WorkflowError:drawings=None
    if drawings:
        st.download_button('Download reviewed drawings ZIP',drawings.archive_bytes,file_name=drawings.filename,mime='application/zip')


main()
