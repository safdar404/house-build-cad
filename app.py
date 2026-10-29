"""GharBuilder AI Streamlit entry point. Run: python -m streamlit run app.py

The entry point owns the persistent sidebar and registers installed workflow
pages through st.navigation. During incremental assembly, available pages appear
as their source files are added; no missing-page stub is executed.
"""
from __future__ import annotations

from pathlib import Path

import streamlit as st

ROOT=Path(__file__).resolve().parent


def main() -> None:
    st.set_page_config(page_title='GharBuilder AI · Agent Studio',page_icon=str(ROOT/'assets'/'agent-mark.svg'),layout='wide',initial_sidebar_state='expanded')
    logo=ROOT/'assets'/'agent-mark.svg'
    if logo.is_file():st.logo(str(logo),icon_image=str(logo),size='large')
    # Cloud uses sidebar/secrets; a local .env file is optional.
    try:
        if (ROOT/'.env').is_file():
            from dotenv import load_dotenv
            load_dotenv(ROOT/'.env',override=False)
        from ui.components import apply_theme,render_home,sidebar,tr
        from ui.state import get_workspace
    except ModuleNotFoundError as error:
        st.error('An application dependency is missing: '+str(error.name))
        st.info('Open Manage app and inspect the dependency installation log. '
                'Install requirements.txt from the repository root, then reboot the app.')
        st.stop()
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
        ('engineering.py','Engineering allowances','🔧'),('workflow_chat.py','Agent Studio','🤖'),('demo.py','Demonstration','🧪'),
    ]
    pages=[home]
    registered={}
    for filename,label,icon in definitions:
        path=ROOT/'pages'/filename
        if path.is_file():
            page=st.Page(str(path),title=tr(label),icon=icon)
            pages.append(page);registered[filename]=page
    groups={'Workspace':[home]+[registered[n] for n in ['workflow_chat.py','requirements_chat.py'] if n in registered],
        'Design':[registered[n] for n in ['floor_plans.py','model_3d.py','bim_ifc.py','engineering.py'] if n in registered],
        'Construction':[registered[n] for n in ['schedule.py','estimation.py','labour.py'] if n in registered],
        'Monitor & Export':[registered[n] for n in ['digital_twin.py','downloads.py'] if n in registered],
        'Settings':[registered[n] for n in ['settings.py','demo.py'] if n in registered]}
    selected=st.navigation({name:items for name,items in groups.items() if items},position='top')
    target=st.session_state.pop('gh_next_page',None)
    if target:st.switch_page(target)
    selected.run()


if __name__=='__main__':main()
