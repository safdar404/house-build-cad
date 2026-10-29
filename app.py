"""GharBuilder AI Streamlit entry point. Run: python -m streamlit run app.py

The entry point owns the persistent sidebar and registers installed workflow
pages through st.navigation. During incremental assembly, available pages appear
as their source files are added; no missing-page stub is executed.
"""
from __future__ import annotations

from pathlib import Path

import streamlit as st
from dotenv import load_dotenv

from ui.components import apply_theme,render_home,sidebar,tr
from ui.state import get_workspace

ROOT=Path(__file__).resolve().parent
load_dotenv(ROOT/'.env',override=False)


def main() -> None:
    st.set_page_config(page_title='GharBuilder AI',page_icon='🏗️',layout='wide',initial_sidebar_state='expanded')
    # Clear widget state before instantiating its password input on this rerun.
    if st.session_state.pop('gh_clear_key_on_rerun',False):
        st.session_state.pop('gh_api_key',None)
        st.session_state.pop('gh_connection',None)
        runtime=st.session_state.pop('gh_runtime',None)
        if runtime is not None:runtime.orchestrator.close()
        st.session_state.pop('gh_runtime_signature',None)
    workspace=get_workspace(st.session_state)
    sidebar(workspace)
    apply_theme(st.session_state.get('gh_theme','light'))
    home=st.Page(render_home,title=tr('home'),icon='🏠',default=True)
    st.session_state['gh_home_page']=home
    definitions=[
        ('requirements_chat.py','requirements','💬'),('floor_plans.py','plans','📐'),
        ('model_3d.py','model','🏠'),('bim_ifc.py','bim','🧩'),('schedule.py','schedule','📅'),
        ('estimation.py','cost','💰'),('labour.py','labour','👷'),('digital_twin.py','twin','📊'),
        ('downloads.py','downloads','📦'),('settings.py','settings','⚙️'),
        ('engineering.py','Engineering allowances','🔧'),('workflow_chat.py','Workflow agent','🤖'),('demo.py','Demonstration','🧪'),
    ]
    pages=[home]
    for filename,label,icon in definitions:
        path=ROOT/'pages'/filename
        if path.is_file():pages.append(st.Page(str(path),title=tr(label),icon=icon))
    selected=st.navigation(pages)
    selected.run()


if __name__=='__main__':main()
