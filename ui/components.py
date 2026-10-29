"""Shared Streamlit presentation, connection controls and reviewed stage actions.

Credentials and API clients exist only in per-session runtime state. Exported
Project data never includes this runtime. All user strings embedded in HTML are
escaped. This module performs no network operation until a user presses a button
or a specialist explicitly runs.
"""
from __future__ import annotations

import base64
import hashlib
import html
import json
import os
from pathlib import Path
from dataclasses import dataclass,fields,is_dataclass

import streamlit as st
from openai import (APIConnectionError,APIStatusError,APITimeoutError,AuthenticationError,
                    OpenAI,PermissionDeniedError,RateLimitError)

from agents.base import AgentError
from agents.orchestrator import OrchestratorAgent
from config import Credentials,DISCLAIMER,RAINBOW,Settings,resolve_credentials
from schemas import Contract,Stage,Usage,content_hash
from ui.state import WorkspaceState,WorkflowError,get_workspace

LABELS={
 'home':('Home','ہوم'),'requirements':('Requirements Chat','ضروریات کی گفتگو'),
 'plans':('Floor Plans','منزلوں کے نقشے'),'model':('3D Model','تھری ڈی ماڈل'),
 'bim':('BIM & IFC','بی آئی ایم اور آئی ایف سی'),'schedule':('4D Schedule','تعمیراتی شیڈول'),
 'cost':('Cost Estimation','لاگت کا تخمینہ'),'labour':('Labour','افرادی قوت'),
 'twin':('Digital Twin','ڈیجیٹل ٹوئن'),'downloads':('Reports & Downloads','رپورٹ اور ڈاؤن لوڈ'),
 'settings':('Rates Settings','نرخ کی ترتیبات'),'project':('Project name','منصوبے کا نام'),
 'key':('OpenAI API Key','اوپن اے آئی کی اے پی آئی کلید'),
 'test':('Test API connection','اے پی آئی کنکشن آزمائیں'),
 'back':('Back to Home','ہوم پر واپس جائیں'),
 'review':('I reviewed this concept output','میں نے یہ ابتدائی نتیجہ دیکھ لیا ہے'),
 'approve':('Approve concept output','ابتدائی نتیجہ منظور کریں'),
 'generate':('Generate reviewed stage','جائزہ شدہ مرحلہ تیار کریں'),
}


def tr(key: str) -> str:
    pair=LABELS.get(key,(key,key))
    return pair[1] if st.session_state.get('gh_language','English')=='Urdu' else pair[0]


def apply_theme(theme: str='light') -> None:
    dark=theme=='dark';bg='#0e1424' if dark else '#f4f6fc';fg='#edf2ff' if dark else '#21334d'
    card='#1b253a' if dark else '#f8faff';border='#35435e' if dark else '#cbd8f0'
    button_bg='#263858' if dark else '#e3ecff';button_hover='#344c73' if dark else '#cddfff'
    gradient=','.join(RAINBOW)
    extra=Path(__file__).resolve().parents[1]/'assets'/'style.css'
    if extra.is_file():st.markdown('<style>'+extra.read_text(encoding='utf-8')+'</style>',unsafe_allow_html=True)
    st.markdown(f'''<style>
    .stApp{{background:{bg};color:{fg};}}
    :root{{--gh-bg:{bg};--gh-card:{card};--gh-fg:{fg};--gh-border:{border};}}
    header,[data-testid="stHeader"],[data-testid="stTopNav"],nav{{background:{card}!important;color:{fg}!important;}}
    header button,nav button,[data-testid="stTopNav"] button{{background:{card}!important;color:{fg}!important;border-color:{border}!important;}}
    [data-testid="stTopNavPopover"],[data-testid="stTopNavPopoverBody"],
    [data-testid="stTopNavLink"],[data-testid="stTopNavDropdownLink"],[data-testid="stTopNavSection"]{{background:{card}!important;color:{fg}!important;}}
    button:disabled{{opacity:.48!important;cursor:not-allowed;}}
    header button svg,nav button svg{{fill:currentColor;}}
    [data-testid="stBaseButton-primary"],[data-testid="stBaseButton-primary"] p,[data-testid="stBaseButton-primary"] span{{color:#ffffff!important;}}
    [data-testid="stBaseButton-secondary"],[data-testid="stBaseButton-tertiary"],
    [data-testid="stPageLink-NavLink"],button[kind="secondary"],button[kind="tertiary"]{{background:{button_bg}!important;color:{fg}!important;border-color:{border}!important;}}
    [data-testid="stPageLink"] a,[data-testid="stDownloadButton"] button,button[kind="secondaryFormSubmit"]{{background:{button_bg}!important;color:{fg}!important;border:1px solid {border}!important;}}
    [data-testid="stPageLink"] a:hover,[data-testid="stBaseButton-secondary"]:hover,[data-testid="stDownloadButton"] button:hover{{background:{button_hover}!important;transform:translateY(-1px);}}
    [data-testid="stTopNavLink"],[data-testid="stTopNavSection"]{{border:1px solid {border}!important;border-radius:9px!important;background:{button_bg}!important;}}
    [data-testid="stTopNavLink"][aria-current="page"]{{box-shadow:inset 0 -3px #7c3aed;}}
    [data-baseweb="select"]>div,[data-baseweb="input"],[data-baseweb="base-input"],
    [data-testid="stTextArea"] textarea,[data-testid="stNumberInput"] input{{background:{card}!important;color:{fg}!important;border-color:{border}!important;}}
    [data-baseweb="popover"],[data-baseweb="popover"] ul,[data-baseweb="menu"],
    [data-testid="stPopoverBody"],[data-testid="stMainMenuPopover"],
    [role="menu"],[role="listbox"],[role="option"]{{background:{card}!important;color:{fg}!important;}}
    [role="menuitem"],[data-baseweb="popover"] button,[data-baseweb="popover"] li{{color:{fg}!important;background:{card}!important;}}
    input,textarea{{color:{fg}!important;caret-color:{fg};}}
    [data-testid="stExpander"] summary,[data-testid="stExpander"] details{{background:{card}!important;color:{fg}!important;}}
    [data-testid="stTabs"] button{{color:{fg}!important;}}

    .block-container{{max-width:1480px;padding-top:1.4rem;padding-bottom:2rem;}}
    [data-testid="stWidgetLabel"] p,[data-testid="stMarkdownContainer"]{{color:{fg};}}
    [data-testid="stSidebar"]{{background:{card};border-right:1px solid {border};}}
    [data-testid="stMetric"]{{background:{card};border:1px solid {border};border-radius:16px;padding:14px;box-shadow:0 6px 18px #182b5010;}}
    [data-testid="stMetricLabel"],[data-testid="stMetricValue"]{{color:{fg};}}
    .gh-hero{{background:linear-gradient(115deg,#182b50,#3949ab 68%,#8e24aa);color:white;border-radius:22px;padding:24px 28px;margin-bottom:14px;border-top:6px solid transparent;position:relative;overflow:hidden;}}
    .gh-hero:before{{content:"";position:absolute;top:0;left:0;width:100%;height:6px;background:linear-gradient(90deg,{gradient});}}
    .gh-hero h1{{color:white;font-size:clamp(1.65rem,3vw,2.7rem);margin:0 0 6px;line-height:1.2;}}
    .gh-hero p{{margin:0;color:#e8ebff;max-width:850px;}}
    .gh-stepper{{display:flex;flex-wrap:wrap;gap:7px;padding:4px 0 12px;}}
    .gh-step{{background:{card};color:{fg};border:1px solid {border};border-top:4px solid var(--stage);min-width:115px;border-radius:12px;padding:9px 11px;font-size:.78rem;}}
    .gh-step strong{{display:block;margin-bottom:4px;}}
    .gh-card{{background:{card};color:{fg};border:1px solid {border};border-radius:16px;padding:17px;margin:8px 0;min-height:110px;}}
    .gh-card h3{{margin:0 0 6px;font-size:1.05rem;color:{fg};}}
    .gh-card p{{margin:0;font-size:.87rem;line-height:1.5;}}
    .gh-brick{{height:7px;border-radius:5px;margin:18px 0;background:repeating-linear-gradient(90deg,#e8b5a8 0,#e8b5a8 36px,transparent 36px,transparent 40px);opacity:.6;}}
    .stButton>button,.stDownloadButton>button{{border-radius:11px;min-height:2.5rem;}}
    @media(max-width:700px){{.block-container{{padding-left:1rem;padding-right:1rem;}}.gh-hero{{padding:20px;}}}}
    </style>''',unsafe_allow_html=True)


def hero(title: str='🏗️ GharBuilder AI',subtitle: str='Agentic House Design & Estimation Studio') -> None:
    logo=Path(__file__).resolve().parents[1]/'assets'/'agent-mark.svg'
    mark=''
    if logo.is_file():
        source=base64.b64encode(logo.read_bytes()).decode('ascii')
        mark='<img class="gh-brand-mark" src="data:image/svg+xml;base64,'+source+'" alt="GharBuilder AI agent logo" />'
    st.markdown('<div class="gh-hero">'+mark+'<div class="gh-brand-copy"><h1>'+
        html.escape(title.replace('🏗️ ',''))+'</h1><p>'+html.escape(subtitle)+'</p></div></div>',unsafe_allow_html=True)



def stage_stepper(workspace: WorkspaceState) -> None:
    cards=[]
    for i,stage in enumerate(Stage):
        status=workspace.record(stage).status
        cards.append('<div class="gh-step" style="--stage:'+RAINBOW[i%len(RAINBOW)]+'"><strong>'+
            html.escape(stage.value.title())+'</strong>'+html.escape(status.replace('_',' '))+'</div>')
    st.markdown('<div class="gh-stepper">'+''.join(cards)+'</div>',unsafe_allow_html=True)


def safe_output(workspace: WorkspaceState,stage: Stage):
    try:return workspace.get_output(stage)
    except WorkflowError:return None


def metric_cards(workspace: WorkspaceState) -> None:
    cost=safe_output(workspace,Stage.COST);schedule=safe_output(workspace,Stage.SCHEDULE)
    labour=safe_output(workspace,Stage.LABOUR)
    try:layout=workspace.selected_layout()
    except WorkflowError:layout=None
    values=[('Construction PKR',f'{cost.construction_pkr:,.0f}' if cost and cost.construction_pkr is not None else '—'),
            ('Covered m²',f'{sum(f.covered_area_m2 for f in layout.floors):,.1f}' if layout else '—'),
            ('Calendar days',str(schedule.duration_calendar_days) if schedule else '—'),
            ('Peak workers',str(labour.peak_workers) if labour else '—')]
    for column,(label,value) in zip(st.columns(4),values):column.metric(label,value)


def _available_secrets():
    try:
        if 'OPENAI_API_KEY' in st.secrets:return {'OPENAI_API_KEY':st.secrets['OPENAI_API_KEY']}
    except (FileNotFoundError,st.errors.StreamlitSecretNotFoundError):pass
    return None


def agent_model_choices(ids: list[str]) -> list[str]:
    """Conservative text-agent candidates, not a capability/access guarantee."""
    excluded=('audio','realtime','transcrib','tts','search','image','instruct','chat-latest','codex')
    candidates=[m for m in ids if m.startswith(('gpt-4o','gpt-4.1','gpt-5','gpt-6','o3','o4'))
                and not any(part in m.lower() for part in excluded)]
    preferred=['gpt-4.1-mini','gpt-4o-mini','gpt-5-mini','gpt-4.1','gpt-4o']
    return sorted(set(candidates),key=lambda m:(preferred.index(m) if m in preferred else len(preferred),m))


def available_model_ids(credentials: Credentials) -> list[str]:
    """Explicit user action only; list account model IDs without generating tokens."""
    try:
        with OpenAI(api_key=credentials.api_key.get_secret_value(),max_retries=0,timeout=20) as client:
            return sorted({model.id for model in client.models.list()})
    except (APIConnectionError,APIStatusError,APITimeoutError):
        raise AgentError('Could not load account models. Check the key, access and connection, or type your model ID.') from None


def _record_probe(response,workspace: WorkspaceState,model: str) -> None:
    usage=getattr(response,'usage',None)
    if usage:
        details=getattr(usage,'input_tokens_details',None)
        workspace.project.usage.append(Usage(model=getattr(response,'model',None) or model,
            input_tokens=usage.input_tokens,output_tokens=usage.output_tokens,
            cached_input_tokens=getattr(details,'cached_tokens',0) or 0))


def _probe(credentials: Credentials,settings: Settings,workspace: WorkspaceState) -> tuple[bool,str]:
    try:
        with OpenAI(api_key=credentials.api_key.get_secret_value(),max_retries=0,timeout=20) as client:
            response=client.responses.create(model=settings.model,input='Reply OK.',max_output_tokens=256,store=False)
        _record_probe(response,workspace,settings.model)
        return True,'API connected; the selected model accepted the request.'
    except AuthenticationError:return False,'Authentication failed. Check your API key.'
    except PermissionDeniedError:return False,'This API project cannot access the selected model.'
    except RateLimitError:return False,'API quota or rate limit reached. Check API billing and limits.'
    except (APIConnectionError,APITimeoutError):return False,'Connection failed or timed out. Try again.'
    except APIStatusError as error:
        body=error.body if isinstance(error.body,dict) else {}
        details=body.get('error',body)
        code=details.get('code') if isinstance(details,dict) else None
        if code=='model_not_found':return False,'Model unavailable for this API project. Load models and select a text-agent model.'
        if code=='insufficient_quota':return False,'API credit/quota exhausted. Check API project billing; changing models will not fix billing.'
        return False,f'API request rejected (HTTP {error.status_code}). Select a text-agent model; check project permissions and Responses API support.' 


@dataclass
class Runtime:
    settings: Settings
    credentials: Credentials
    workspace: WorkspaceState
    orchestrator: OrchestratorAgent


def get_runtime(required: bool=True) -> Runtime | None:
    """Pages call this after app.py has rendered the shared sidebar."""
    settings=st.session_state.get('gh_settings')
    try:credentials=resolve_credentials(st.session_state.get('gh_api_key',''),_available_secrets())
    except ValueError:
        if required:st.error('Check the key entered in the password field.')
        return None
    if settings is None or credentials is None:
        if required:st.info('Enter your API key and a model ID in the sidebar to use AI agents.')
        return None
    workspace=get_workspace(st.session_state)
    signature=hashlib.sha256((credentials.api_key.get_secret_value()+settings.model_dump_json(exclude={'theme'})).encode()).hexdigest()
    runtime=st.session_state.get('gh_runtime')
    if runtime is None or runtime.workspace is not workspace or st.session_state.get('gh_runtime_signature')!=signature:
        if runtime is not None:runtime.orchestrator.close()
        runtime=Runtime(settings,credentials,workspace,OrchestratorAgent(state=workspace,
                        settings=settings,credentials=credentials,usage_log=workspace.project.usage))
        st.session_state['gh_runtime']=runtime;st.session_state['gh_runtime_signature']=signature
    runtime.settings.theme=settings.theme
    runtime.orchestrator.settings.theme=settings.theme
    return runtime


def sidebar(workspace: WorkspaceState) -> None:
    with st.sidebar:
        st.markdown('### GharBuilder AI')
        st.caption('CONNECT → DESCRIBE → GENERATE → REVIEW')
        st.text_input(tr('key'),type='password',key='gh_api_key',help='Your key stays in this session. Server secrets may provide it instead.')
        try:model_credentials=resolve_credentials(st.session_state.get('gh_api_key',''),_available_secrets())
        except ValueError:model_credentials=None
        model_identity=hashlib.sha256(model_credentials.api_key.get_secret_value().encode()).hexdigest() if model_credentials else None
        if st.button('Load available models',disabled=model_credentials is None,key='gh_load_models'):
            try:
                with st.spinner('Loading model choices...'):ids=available_model_ids(model_credentials)
                st.session_state['gh_account_models']=(model_identity,ids)
            except AgentError as error:st.error(str(error))
        cached_models=st.session_state.get('gh_account_models')
        if cached_models and cached_models[0]==model_identity and cached_models[1]:
            current=st.session_state.get('gh_model_id') or os.environ.get('OPENAI_MODEL','')
            options=agent_model_choices(cached_models[1])
            if current and current not in options:
                if current in cached_models[1]:st.session_state['gh_model_id']=None
                else:options.append(current)
            st.caption('Text-agent candidates only. Connection test verifies access. Custom IDs can be typed.')
            model=st.selectbox('OpenAI model ID',options,index=None,
                accept_new_options=True,key='gh_model_id',placeholder='Select a model or type an ID',
                help='Choose an accessible model supporting Responses, structured outputs and function calling. Listing a model does not verify those capabilities. Video, image and audio models are excluded.') or ''
        else:
            model=st.text_input('OpenAI model ID',value=os.environ.get('OPENAI_MODEL',''),key='gh_model_id',
                placeholder='Load model choices above, or enter an ID',help='Choose a model available to your API project with Responses and function calling.')
        settings=Settings(model=model.strip(),language=st.session_state.get('gh_language','English'),
            theme=st.session_state.get('gh_theme','light'),max_output_tokens=int(st.session_state.get('gh_tokens',6000)),
            max_retries=int(st.session_state.get('gh_retries',2)),max_tool_calls=int(st.session_state.get('gh_tools',30))) if model.strip() else None
        st.session_state['gh_settings']=settings
        try:credentials=resolve_credentials(st.session_state.get('gh_api_key',''),_available_secrets())
        except ValueError:credentials=None;st.error('Remove whitespace from the API key.')
        if credentials and not settings:st.warning('Key entered. Add a model ID to activate AI.')
        cached_runtime=st.session_state.get('gh_runtime')
        if cached_runtime is not None and (credentials is None or settings is None
            or cached_runtime.credentials.api_key!=credentials.api_key or cached_runtime.settings.model_dump(exclude={'theme'})!=settings.model_dump(exclude={'theme'})):
            cached_runtime.orchestrator.close()
            st.session_state.pop('gh_runtime',None);st.session_state.pop('gh_runtime_signature',None)
        identity=hashlib.sha256((credentials.api_key.get_secret_value()+model).encode()).hexdigest() if credentials and model else None
        if st.button('Connect & continue →',key='gh_connect_continue',type='primary',use_container_width=True):
            if not credentials:st.error('Enter your OpenAI API key above, or use the project form below without AI.')
            elif not settings:st.error('Enter a model ID above so the agent knows which LLM to use.')
            else:
                result=st.session_state.get('gh_connection')
                if not result or result[0]!=identity or not result[1]:
                    with st.spinner('Checking your key and model...'):ok,message=_probe(credentials,settings,workspace)
                    result=(identity,ok,message);st.session_state['gh_connection']=result
                if result[1]:st.session_state['gh_next_page']='pages/requirements_chat.py'
        if st.button('Enter project details without AI',key='gh_form_without_ai',use_container_width=True):
            st.session_state['gh_next_page']='pages/requirements_chat.py'
        if st.button(tr('test'),disabled=not bool(credentials and settings)):
            with st.spinner('Checking API connection...'):ok,message=_probe(credentials,settings,workspace)
            st.session_state['gh_connection']=(identity,ok,message)
        result=st.session_state.get('gh_connection')
        if result and result[0]==identity:
            (st.success if result[1] else st.error)(('✅ ' if result[1] else '❌ ')+result[2])
        elif credentials and settings:st.caption('Ready to connect. Press Connect & continue above.')
        with st.expander('Appearance & project'):
            st.selectbox('Language / زبان',['English','Urdu'],key='gh_language')
            st.selectbox('Appearance',['light','dark'],key='gh_theme')
            project_name=st.text_input(tr('project'),value=workspace.project.name,max_chars=100)
            if project_name!=workspace.project.name:
                workspace.project.name=project_name;workspace.invalidate(Stage.REPORT)
        with st.expander('Agent limits'):
            st.number_input('Maximum output tokens',min_value=256,max_value=32000,value=6000,step=256,key='gh_tokens')
            st.number_input('Validation retries',min_value=0,max_value=5,value=2,key='gh_retries')
            st.number_input('Maximum workflow tool calls',min_value=1,max_value=100,value=30,key='gh_tools')
        usage=workspace.project.usage
        try:
            from ui.workflow import read_config
            from tools.pricing import price_usage
            price_catalog=read_config('model_pricing.json')
            for entry in usage:entry.estimated_usd=price_usage(entry,price_catalog)
        except (ValueError,ImportError):pass
        st.caption(f'Session tokens: {sum(u.input_tokens+u.output_tokens for u in usage):,}')
        if usage and all(u.estimated_usd is not None for u in usage):
            st.caption(f'Estimated API cost at configured prices: USD {sum(u.estimated_usd for u in usage):.4f}')
        else:st.caption('API cost unavailable until dated model prices are configured.')
        st.caption('API charges are billed separately from ChatGPT subscriptions.')
        if st.button('Clear entered key'):
            st.session_state['gh_clear_key_on_rerun']=True;st.rerun()


def render_input_gate(stage: Stage) -> bool:
    runtime=get_runtime()
    if runtime is None:return False
    task=runtime.orchestrator.tasks.get(stage)
    if task is None:st.info('Complete the required inputs for this stage.');return False
    fingerprint=content_hash(task.request)
    with st.expander('Review generation inputs',expanded=True):
        payload=task.request.model_dump(mode='json')
        if 'payload_json' in payload:payload=json.loads(payload['payload_json'])
        st.json(payload)
    reviewed=st.checkbox('I reviewed these inputs and accepted their stated assumptions',key='gh_input_review_'+stage.value+'_'+fingerprint)
    if st.button(tr('generate'),key='gh_generate_'+stage.value,disabled=not reviewed,type='primary'):
        try:
            runtime.orchestrator.authorize_prepared(stage,reviewed_hash=fingerprint,user_approved=True)
            with st.spinner('Generating '+stage.value+'...'):runtime.orchestrator.execute(stage)
            st.rerun()
        except (AgentError,WorkflowError) as error:st.error(str(error))
    return True


def render_review_gate(stage: Stage) -> None:
    workspace=get_workspace(st.session_state);record=workspace.record(stage)
    if record.status!='review':return
    st.info('Review this preliminary concept before the next stage. This is not professional or authority approval.')
    value=workspace.outputs[stage]
    if isinstance(value,Contract):st.json(value.model_dump(mode='json'))
    elif is_dataclass(value):
        summary={}
        for field in fields(value):
            item=getattr(value,field.name)
            if isinstance(item,bytes):summary[field.name]=f'{len(item):,} bytes'
            elif isinstance(item,(str,int,float,bool,list,tuple,dict)):
                # Avoid rendering entire mesh vertex arrays or binary artifacts.
                summary[field.name]=item if field.name!='model' else '3D model'
        st.write(summary)
    key=record.output_hash or ''
    explainers={Stage.COMPLIANCE:('agents.compliance_agent','ComplianceAgent'),
        Stage.MODEL:('agents.modeling_agent','ModelingAgent'),Stage.STRUCTURAL:('agents.structural_agent','StructuralAgent'),
        Stage.MEP:('agents.mep_agent','MEPAgent'),Stage.BIM:('agents.bim_agent','BIMAgent'),
        Stage.SCHEDULE:('agents.scheduling_agent','SchedulingAgent'),Stage.COST:('agents.cost_agent','CostAgent'),
        Stage.LABOUR:('agents.labour_agent','LabourAgent'),Stage.TWIN:('agents.twin_agent','DigitalTwinAgent')}
    runtime=get_runtime(required=False)
    if stage in explainers and runtime:
        explanation_key='gh_explanation_'+stage.value+'_'+key+'_'+runtime.settings.language
        if st.button('Ask specialist to explain',key='gh_explain_'+stage.value):
            import importlib
            module,name=explainers[stage]
            specialist=getattr(importlib.import_module(module),name)(settings=runtime.settings,
                credentials=runtime.credentials,usage_log=workspace.project.usage,client=runtime.orchestrator._client)
            try:
                with st.spinner('Preparing specialist explanation...'):
                    st.session_state[explanation_key]=specialist.explain(value).value
            except AgentError as error:st.error(str(error))
            finally:specialist.close()
        explanation=st.session_state.get(explanation_key)
        if explanation is not None:st.json(explanation.model_dump(mode='json'),expanded=False)
    reviewed=st.checkbox(tr('review'),key='gh_output_review_'+stage.value+'_'+key)
    if st.button(tr('approve'),key='gh_approve_'+stage.value,disabled=not reviewed,type='primary'):
        try:workspace.approve(stage,reviewed_hash=key,user_approved=True);st.rerun()
        except WorkflowError as error:st.error(str(error))


def back_to_home() -> None:
    page=st.session_state.get('gh_home_page')
    if page is not None and st.button('← '+tr('back')):st.switch_page(page)
    workspace=get_workspace(st.session_state)
    from ui.journey import next_action
    label,path,_=next_action(workspace,st.session_state)
    st.page_link(path,label='Workflow next: '+label,icon='➡️')



def render_home() -> None:
    workspace=get_workspace(st.session_state)
    hero()
    a,b=st.columns(2)
    with a:st.page_link('pages/requirements_chat.py',label='Start / edit my house project',icon='🏗️')
    with b:st.page_link('pages/demo.py',label='Try the working demonstration — no API key',icon='▶️')
    with st.container(border=True):
        st.subheader('🤖 Your design agent')
        st.write('Brief → concepts → CAD / 3D / IFC → schedule → costs → monitoring. Ask the agent to inspect progress and run reviewed tools.')
        st.page_link('pages/workflow_chat.py',label='Open Agent Studio',icon='⚡')
    from ui.journey import next_action
    label,path,description=next_action(workspace,st.session_state)
    with st.container(border=True):
        st.subheader('Next: '+label)
        st.write(description)
        st.page_link(path,label='Continue → '+label,icon='➡️')
    approved=sum(workspace.record(stage).status=='approved' for stage in Stage)
    st.progress(approved/len(Stage),text=str(approved)+' of '+str(len(Stage))+' stages reviewed')
    with st.expander('Detailed workflow status'):
        stage_stepper(workspace)
    metric_cards(workspace)
    st.markdown('<div class="gh-brick"></div>',unsafe_allow_html=True)
    features=[('💬 Guided requirements','Describe your household, plot and priorities, then review the extracted brief.'),
              ('📐 Coordinated concepts','Compare floor alternatives and inspect dimensions, access routes and room zones.'),
              ('🏠 CAD and BIM','Review 2D drawings, 3D geometry and IFC properties before exporting.'),
              ('📅 Construction planning','Inspect task dependencies, curing waits and the weekly construction sequence.'),
              ('💰 Costs and crews','Trace quantity allowances, rate evidence, cost splits and workforce requirements.'),
              ('📊 Progress monitoring','Review reported progress and costs separately from simulated operational sensors.')]
    columns=st.columns(3)
    destinations=['requirements_chat','floor_plans','model_3d','schedule','estimation','digital_twin']
    for index,(title,body) in enumerate(features):
        with columns[index%3]:
            with st.container(border=True):
                st.subheader(title)
                st.write(body)
                st.page_link('pages/'+destinations[index]+'.py',label='Open '+title[2:],icon='➡️')
    st.caption(DISCLAIMER)
    pending=[s for s in Stage if workspace.record(s).status=='review']
    if pending:
        st.subheader('Outputs awaiting review')
        for stage in pending:render_review_gate(stage)
    else:st.info('Use the sidebar navigation to open a workflow stage. AI actions require your API key and model ID.')
    with st.expander('Workflow status'):
        st.dataframe([{'Stage':s.value,'Status':workspace.record(s).status,'Revision':workspace.record(s).revision} for s in Stage],hide_index=True)
