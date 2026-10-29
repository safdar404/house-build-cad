"""Schema-validated session settings and optional explicitly enabled local writes."""
from __future__ import annotations
import json
import os
import streamlit as st
from config import save_public_config
from schemas import Stage
from tools.cost import RateCatalog
from tools.labour import LabourRateCatalog
from agents.compliance_agent import BylawDatabase
from tools.pricing import PricingCatalog
from tools.schedule_4d import WorkCalendar
from ui.components import back_to_home,hero,tr
from ui.workflow import read_config,protect_secret
from ui.state import get_workspace,WorkflowError


def main():
    back_to_home();hero('⚙️ '+tr('settings'),'Edit dated quotations, authority evidence, calendar exceptions and API price scenarios.')
    workspace=get_workspace(st.session_state)
    schemas={'rates_pk.json':RateCatalog,'labour_rates.json':LabourRateCatalog,'bylaws.json':BylawDatabase,
             'model_pricing.json':PricingCatalog,'calendar_exceptions.json':WorkCalendar}
    dependencies={'rates_pk.json':Stage.COST,'labour_rates.json':Stage.LABOUR,'bylaws.json':Stage.COMPLIANCE,
                  'calendar_exceptions.json':Stage.SCHEDULE}
    filename=st.selectbox('Configuration',list(schemas))
    try:current=read_config(filename)
    except ValueError:st.error('Configuration cannot be loaded. Restore its JSON from the project package.');return
    st.caption('Changes are private to this session unless local writes are explicitly enabled by the server administrator. Export JSON to retain edits.')
    with st.form('gh_settings_'+filename):
        text=st.text_area('Configuration JSON',value=current.model_dump_json(indent=2),height=450)
        accepted=st.checkbox('I reviewed the units, effective dates, source evidence and scope')
        apply=st.form_submit_button('Apply validated session settings')
    if apply:
        try:
            protect_secret(text)
            candidate=schemas[filename].model_validate_json(text)
            if not accepted:raise WorkflowError('Review the edited configuration before applying it.')
            st.session_state['gh_config_'+filename]=candidate.model_dump(mode='json')
            if filename in dependencies:workspace.invalidate(dependencies[filename])
            st.success('Validated session settings applied.')
            st.rerun()
        except WorkflowError as error:st.error(str(error))
        except ValueError:st.error('Invalid configuration schema. Check required fields, units, dates and duplicate identifiers.')
    st.download_button('Download current JSON',current.model_dump_json(indent=2),file_name=filename,mime='application/json')
    if os.environ.get('GHARBUILDER_ALLOW_SETTINGS_WRITES')=='1':
        st.caption('Local file persistence is enabled. Use only on a trusted single-user installation.')
        if st.button('Persist current session configuration to local file'):
            try:save_public_config(filename,read_config(filename),enabled=True);st.success('Local configuration saved.')
            except ValueError:st.error('The local file could not be saved.')
    with st.expander('Evidence guidance'):
        st.write('The creation date of a file is not a quotation date. Keep unknown values null. Verified evidence requires an effective date and reviewer; bylaw checks additionally require the official source URL and clause.')
        st.write('City factors and taxes are explicit scenarios. Do not mix composite work rates with duplicate material/labour scope. API prices require exact model IDs; no current model prices are seeded.')

main()
