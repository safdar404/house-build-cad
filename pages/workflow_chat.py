"""Function-calling workflow conversation over prepared, reviewed stage inputs."""
from __future__ import annotations
import streamlit as st
from schemas import Stage,content_hash
from ui.components import back_to_home,hero,get_runtime,render_review_gate
from ui.state import get_workspace,WorkflowError
from agents.base import AgentError


def main():
    back_to_home();hero('🤖 Workflow agent','Request the next prepared stage or record a change for the affected stage.')
    workspace=get_workspace(st.session_state);runtime=get_runtime(required=False)
    st.session_state.setdefault('gh_workflow_messages',[])
    for row in st.session_state.gh_workflow_messages:
        with st.chat_message(row['role']):st.write(row['content'])
    if runtime is None:st.info('Enter an API key and model ID to use workflow chat.')
    if runtime:
        st.caption('Visit a stage page to prepare its inputs, then review and authorize the exact request below before asking the agent to run it.')
        for stage,task in tuple(runtime.orchestrator.tasks.items()):
            fingerprint=content_hash(task.request)
            with st.expander('Prepared inputs: '+stage.value):
                st.json(task.request.model_dump(mode='json'))
                accepted=st.checkbox('I reviewed these inputs and accept their stated assumptions',
                    key='gh_flow_review_'+stage.value+'_'+fingerprint)
                if st.button('Authorize '+stage.value+' generation',disabled=not accepted,
                             key='gh_flow_authorize_'+stage.value+'_'+fingerprint):
                    try:
                        runtime.orchestrator.authorize_prepared(stage,reviewed_hash=fingerprint,user_approved=True)
                        st.success('These exact inputs are authorized. Ask the workflow agent to run this stage.')
                    except WorkflowError as error:st.error(str(error))
    text=st.chat_input('For example: make the master bedroom bigger',disabled=runtime is None,max_chars=6000)
    if text and runtime:
        try:
            with st.status('Reviewing workflow...',expanded=True) as status:
                turn=runtime.orchestrator.run_flow(text,on_progress=st.write)
                status.update(label='Workflow response ready',state='complete')
            st.session_state.gh_workflow_messages.extend([{'role':'user','content':text},{'role':'assistant','content':turn.message}])
            st.rerun()
        except (AgentError,WorkflowError) as error:st.error(str(error))
    st.caption('The agent cannot approve outputs. Revision requests invalidate affected stages; update and review their inputs before regeneration.')
    for stage in Stage:
        if workspace.record(stage).status=='review':render_review_gate(stage)
    if workspace.revision_notes:
        st.dataframe([{'Stage':stage.value,'Requested change':note} for stage,note in workspace.revision_notes.items()],hide_index=True)

main()
