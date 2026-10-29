"""Agent Studio: project-aware function calling and reviewed automation."""
from __future__ import annotations
import json
import streamlit as st
from schemas import Stage,content_hash
from ui.components import back_to_home,hero,get_runtime,render_review_gate
from ui.state import get_workspace,WorkflowError
from agents.base import AgentError
from agents.project_context import project_context,STAGE_PAGES
from ui.agent_preparation import prepare_available


def main():
    back_to_home();hero('Agent Studio','Your LLM · project context · specialist tools · reviewed execution')
    workspace=get_workspace(st.session_state);runtime=get_runtime(required=False)
    st.session_state.setdefault('gh_workflow_messages',[])
    if runtime is None:
        st.info('Add your OpenAI API key and model ID in the sidebar to activate the agent. Your key is session-only unless you configure server secrets.')
    else:st.caption('Model: '+runtime.settings.model+' · Function calling enabled · API usage appears in the sidebar')
    tasks=runtime.orchestrator.tasks if runtime else {}
    context=project_context(workspace,tasks)
    a,b,c=st.columns(3)
    a.write('**Prepared tools:** '+str(len(tasks)))
    b.write('**Ready to execute:** '+str(sum(row['ready'] for row in context['stages'])))
    c.write('**Waiting for review:** '+str(sum(row['status']=='review' for row in context['stages'])))
    def prepare_tools():
        try:
            messages=prepare_available(runtime,st.session_state)
            st.session_state['gh_runtime']=runtime
            st.session_state['gh_preparation_summary']=' · '.join(messages) or 'Current automatically supported stages are complete. Configure other tools on their pages.'
            st.session_state.pop('gh_preparation_error',None)
        except (AgentError,WorkflowError,ValueError) as error:
            st.session_state['gh_preparation_error']=str(error)
    left,right=st.columns(2)
    left.button('Prepare available project tools',key='gh_prepare_project_tools',disabled=runtime is None,
                use_container_width=True,on_click=prepare_tools)
    if st.session_state.get('gh_preparation_error'):st.error(st.session_state['gh_preparation_error'])
    automatic=right.button('Ask agent to continue workflow',key='gh_agent_continue',disabled=runtime is None,type='primary',use_container_width=True)
    if st.session_state.get('gh_preparation_summary'):st.caption(st.session_state['gh_preparation_summary'])
    chat,tools,activity=st.tabs(['💬 Agent conversation','⚡ Tools & automation','📋 Project activity'],
        default='⚡ Tools & automation' if tasks else '💬 Agent conversation')
    with tools:
        st.caption('Automatic preparation covers bylaw review, AI planning, CAD, 3D and IFC when their project sources exist. Other tools use the explicit rates, crew, schedule and monitoring inputs from their pages. Preparation never starts an API call.')
        for stage,task in tuple(tasks.items()):
            row=next(item for item in context['stages'] if item['stage']==stage.value)
            with st.expander(stage.value.title()+' inputs · '+row['status'],expanded=True):
                st.page_link(row['page'],label='Edit '+stage.value.title()+' inputs',icon='↗️')
                payload=task.request.model_dump(mode='json')
                if 'payload_json' in payload:
                    st.json(json.loads(payload['payload_json']),expanded=False)
                    st.caption('Context digest: '+payload['context_hash'][:12])
                else:st.json(payload,expanded=False)
                if stage==Stage.MODEL:st.caption('Slab, parapet and stair options are schematic modelling assumptions. Review the values above or change them on the 3D Model page.')
                fingerprint=content_hash(task.request)
                accepted=st.checkbox('I reviewed these exact inputs and their assumptions',key='gh_flow_review_'+stage.value+'_'+fingerprint)
                def authorize_tool(selected_stage,selected_hash):
                    try:runtime.orchestrator.authorize_prepared(selected_stage,reviewed_hash=selected_hash,user_approved=True)
                    except WorkflowError as error:st.session_state['gh_preparation_error']=str(error)
                def run_tool(selected_stage):
                    try:runtime.orchestrator.execute(selected_stage)
                    except (AgentError,WorkflowError) as error:st.session_state['gh_preparation_error']=str(error)
                st.button('Authorize '+stage.value,disabled=not accepted,key='gh_flow_authorize_'+stage.value+'_'+fingerprint,
                          on_click=authorize_tool,args=(stage,fingerprint))
                st.button('Run authorized '+stage.value,disabled=not row['ready'],key='gh_flow_run_'+stage.value,
                          on_click=run_tool,args=(stage,))
                st.caption(row['next_action'])
        st.write('**All specialist tools**')
        for stage in Stage:
            st.page_link('pages/'+STAGE_PAGES[stage]+'.py',label=stage.value.title()+' · '+workspace.record(stage).status)
    with activity:
        st.dataframe(context['stages'],hide_index=True,column_order=['stage','status','prepared','authorized','ready','next_action'])
        if workspace.revision_notes:st.json({s.value:n for s,n in workspace.revision_notes.items()})
        st.download_button('Download agent conversation',json.dumps(st.session_state.gh_workflow_messages,ensure_ascii=False,indent=2),file_name='GharBuilder_Agent_Conversation.json',mime='application/json')
        if st.button('Clear agent conversation'):
            st.session_state['gh_workflow_messages']=[];st.rerun()
    with chat:
        for row in st.session_state.gh_workflow_messages:
            with st.chat_message(row['role']):st.write(row['content'])
        st.caption('Try: “Inspect my project and tell me the next steps”, “Run the next authorized tool”, or “Make the master bedroom bigger”. Changes are recorded for regeneration; they do not silently edit approved designs.')
        text=st.chat_input('Ask your house-design agent…',disabled=runtime is None,max_chars=6000)
        if automatic:text='Inspect my current project. Run one ready authorized tool if available; otherwise explain the next input or output review action. Do not repeat an approved stage.'
        if text and runtime:
            try:
                with st.status('Agent inspecting project and tools...',expanded=True) as status:
                    turn=runtime.orchestrator.run_flow(text,conversation=st.session_state.gh_workflow_messages,on_progress=st.write)
                    status.update(label='Agent response ready',state='complete')
                st.session_state.gh_workflow_messages.extend([{'role':'user','content':text},{'role':'assistant','content':turn.message}])
                st.rerun()
            except (AgentError,WorkflowError) as error:st.error(str(error))
        for stage in Stage:
            if workspace.record(stage).status=='review':
                st.subheader(stage.value.title()+' output review')
                render_review_gate(stage)
    st.caption('Tools execute inside this session. This is supervised automation, not a background construction-control service. No real sensor feeds are connected.')

main()
