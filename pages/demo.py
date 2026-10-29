"""Explicit synthetic demonstration, isolated from the current project until loaded."""
from __future__ import annotations
import streamlit as st
from tools.demo import build_sample,DEMO_NOTE
from schemas import Stage,content_hash
from ui.components import back_to_home,hero


def main():
    back_to_home();hero('🧪 Demonstration','10-marla, Ground + 2 floors, Lahore. Reproducible synthetic data; no API key needed.')
    st.warning(DEMO_NOTE)
    st.write('Plot: 30 × 75 ft using 225 sq ft/marla. Assumed front/rear open spaces: 5 ft each. These are example inputs, not LDA rules. Materials, wages, crews, curing and progress are illustrative, not quotations or engineering prescriptions.')
    if st.button('Build separate demonstration workspace'):
        try:
            with st.status('Building demonstration...',expanded=True) as status:
                state,inputs=build_sample(include_reports=True,progress=st.write)
                st.session_state['gh_demo_workspace']=state;st.session_state['gh_demo_inputs']=inputs
                status.update(label='Demonstration built',state='complete')
        except Exception:st.error('The demonstration could not be built. Check the dependency installation and run the packaged smoke test.')
    state=st.session_state.get('gh_demo_workspace')
    if state:
        st.success('The separate demonstration workspace is ready. Your current project has not been changed.')
        report=state.outputs.get(Stage.REPORT)
        if report:st.download_button('Download synthetic demonstration exports',report.zip_bytes,file_name='GharBuilder_Demonstration_Exports.zip')
        replace=st.checkbox('Replace this session’s current workspace with the demonstration (save your current exports first)')
        if st.button('Load demonstration into workflow pages',disabled=not replace):
            inputs=st.session_state['gh_demo_inputs']
            runtime=st.session_state.pop('gh_runtime',None)
            if runtime:runtime.orchestrator.close()
            st.session_state.pop('gh_runtime_signature',None)
            st.session_state['gharbuilder_workspace']=state
            st.session_state['gh_planning_envelope']=inputs['envelope']
            st.session_state['gh_envelope_requirements_hash']=content_hash(inputs['requirements'])
            st.session_state['gh_envelope_compliance_hash']=content_hash(inputs['compliance'])
            st.session_state['gh_model_input']=inputs['model_input']
            st.session_state['gh_requirements_draft']=inputs['requirements'].model_dump_json()
            st.session_state['gh_requirements_editor']=inputs['requirements'].model_dump_json(indent=2)
            st.rerun()

main()
