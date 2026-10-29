"""Guided requirements interview, explicit corrections and normalized-brief approval."""
from __future__ import annotations

import json

import streamlit as st

from agents.base import AgentError,InvalidAgentOutput
from agents.requirements_agent import RequirementsAgent
from schemas import Requirements,Stage,content_hash
from ui.components import back_to_home,get_runtime,hero,render_review_gate,tr
from ui.state import WorkflowError,get_workspace


def _reject_secret(text: str) -> None:
    runtime=get_runtime(required=False)
    key=runtime.credentials.api_key.get_secret_value() if runtime else st.session_state.get('gh_api_key','')
    if key and key in text:
        raise AgentError('Remove the API key from the brief and conversation; use only the password sidebar.')


def _save_draft(text: str) -> None:
    _reject_secret(text)
    draft=RequirementsAgent.parse_draft(text)
    canonical=json.dumps(draft,ensure_ascii=False,sort_keys=True)
    workspace=get_workspace(st.session_state)
    if workspace.record(Stage.REQUIREMENTS).status in {'approved','review'}:
        try:
            changed=content_hash(Requirements.model_validate(draft))!=content_hash(workspace.outputs[Stage.REQUIREMENTS])
        except (ValueError,KeyError):changed=True
        if changed:workspace.invalidate(Stage.REQUIREMENTS)
    st.session_state['gh_requirements_draft']=canonical
    st.session_state['gh_requirements_editor']=json.dumps(draft,ensure_ascii=False,indent=2)


def _confirm(text: str) -> Requirements:
    brief=RequirementsAgent.confirm(text,approved_hash=RequirementsAgent.draft_hash(text),user_approved=True)
    workspace=get_workspace(st.session_state)
    fingerprint=content_hash(brief)
    workspace.authorize(Stage.REQUIREMENTS,brief,reviewed_hash=fingerprint,user_approved=True)
    workspace.start(Stage.REQUIREMENTS,brief)
    result_hash=workspace.complete(Stage.REQUIREMENTS,brief,brief)
    # This normalized output is the exact brief the user just reviewed.
    workspace.approve(Stage.REQUIREMENTS,reviewed_hash=result_hash,user_approved=True)
    return brief


def main() -> None:
    back_to_home();hero('💬 '+tr('requirements'),'Describe your house in a few messages. Review the extracted brief before planning.')
    workspace=get_workspace(st.session_state)
    st.session_state.setdefault('gh_requirements_draft','{}')
    st.session_state.setdefault('gh_requirements_messages',[
        {'role':'assistant','content':'Tell me your city and housing authority/society, then your plot dimensions and units. We will collect the remaining requirements step by step.'}])
    note=workspace.revision_notes.get(Stage.REQUIREMENTS)
    if note:st.info('Requested brief revision: '+note)
    runtime=get_runtime(required=False)
    from ui.requirements_form import render_project_form
    render_project_form(_save_draft)
    if runtime is None:st.info('The project form works without a key. Enter your API key and model ID in the sidebar for the guided AI interview and AI layout generation.')
    for message in st.session_state.gh_requirements_messages:
        with st.chat_message(message['role']):st.write(message['content'])
    message=st.chat_input('Describe your plot, household or a requested change',disabled=runtime is None,max_chars=6000)
    if message and runtime:
        try:
            _reject_secret(message)
            messages=[*st.session_state.gh_requirements_messages,{'role':'user','content':message}]
            specialist=RequirementsAgent(settings=runtime.settings,credentials=runtime.credentials,
                usage_log=workspace.project.usage,client=runtime.orchestrator._client)
            try:
                with st.spinner('Reviewing your requirements...'):
                    result=specialist.interview(messages,draft_json=st.session_state.gh_requirements_draft)
            finally:specialist.close()
            _reject_secret(result.value.message)
            _save_draft(result.value.draft_json)
            st.session_state.gh_requirements_messages=messages+[{'role':'assistant','content':result.value.message}]
            st.rerun()
        except (AgentError,InvalidAgentOutput,WorkflowError) as error:st.error(str(error))
    draft=RequirementsAgent.parse_draft(st.session_state.gh_requirements_draft)
    missing=RequirementsAgent.missing_fields(draft)
    with st.expander('Extracted brief and corrections',expanded=bool(draft)):
        if missing:st.caption('Missing or inconsistent fields: '+', '.join(missing))
        st.json(draft,expanded=False)
        st.session_state.setdefault('gh_requirements_editor',json.dumps(draft,ensure_ascii=False,indent=2))
        with st.form('gh_correct_brief'):
            edited=st.text_area('Correct the extracted brief JSON',key='gh_requirements_editor',height=260,
                help='Advanced correction option. Unknown facts should remain absent; do not insert invented defaults.')
            applied=st.form_submit_button('Apply corrections')
        if applied:
            try:
                # The editor widget already exists in this run: update its value on
                # the next run rather than mutating a live widget's session key.
                _reject_secret(edited)
                parsed=RequirementsAgent.parse_draft(edited)
                canonical=json.dumps(parsed,ensure_ascii=False,sort_keys=True)
                if canonical!=st.session_state.gh_requirements_draft:
                    workspace.invalidate(Stage.REQUIREMENTS)
                    st.session_state.gh_requirements_draft=canonical
                st.success('Corrections saved. Review the normalized brief below.')
                st.rerun()
            except (AgentError,InvalidAgentOutput,WorkflowError):st.error('Corrections are invalid. Use a JSON object with supported requirements fields and remove any secret values.')
    # Re-read the current draft after applying any explicit correction.
    text=st.session_state.gh_requirements_draft
    draft=RequirementsAgent.parse_draft(text);missing=RequirementsAgent.missing_fields(draft)
    if draft and not missing:
        st.subheader('Review the normalized brief')
        brief=Requirements.model_validate(draft)
        a,b,c=st.columns(3)
        a.metric('Plot area sq ft',f'{brief.plot.area_sqft:,.1f}')
        b.metric('Requested floors',len(brief.floors));c.metric('Budget PKR',f'{brief.budget_pkr:,.0f}')
        st.dataframe([{'Floor':f.name,'Level':f.level,'Bedrooms':f.bedrooms,'Bathrooms':f.bathrooms,'Kitchens':f.kitchens} for f in brief.floors],hide_index=True)
        st.json(brief.model_dump(mode='json'),expanded=False)
        if any(a.status!='accepted' for a in brief.assumptions):
            st.warning('Resolve proposed/rejected assumptions in the conversation or corrections before confirmation.')
        approved=st.checkbox('I reviewed all facts, floor choices, units and assumptions in this brief',key='gh_confirm_brief_'+RequirementsAgent.draft_hash(text))
        if st.button('Confirm requirements',disabled=not approved,type='primary'):
            try:_confirm(text);st.success('Requirements confirmed.');st.rerun()
            except (AgentError,WorkflowError) as error:st.error(str(error))
    render_review_gate(Stage.REQUIREMENTS)
    try:approved_brief=workspace.get_output(Stage.REQUIREMENTS)
    except WorkflowError:approved_brief=None
    if approved_brief:
        st.success('The normalized requirements are approved for concept planning.')
        st.download_button('Download confirmed brief JSON',approved_brief.model_dump_json(indent=2),
                           file_name='GharBuilder_Requirements.json',mime='application/json')
        if st.button('Continue to Floor Plans →'):st.switch_page('pages/floor_plans.py')
    with st.expander('Start a new brief'):
        st.caption('This clears this conversation and makes existing design outputs stale.')
        if st.button('Start new requirements interview'):
            workspace.invalidate(Stage.REQUIREMENTS)
            for key in ('gh_requirements_draft','gh_requirements_messages','gh_requirements_editor'):
                st.session_state.pop(key,None)
            st.rerun()


main()
