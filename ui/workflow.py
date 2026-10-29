"""Shared page helpers for reviewed deterministic stages and per-user settings."""
from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

import streamlit as st
from pydantic import BaseModel

from agents.base import AgentError
from config import ConfigurationError,DATA_DIR,load_json,resolve_credentials
from schemas import Contract,Stage,content_hash
from ui.components import _available_secrets
from ui.state import WorkflowError,get_workspace


def today():return datetime.now(ZoneInfo('Asia/Karachi')).date()


def read_config(filename: str):
    from tools.cost import RateCatalog
    from tools.labour import LabourRateCatalog
    from agents.compliance_agent import BylawDatabase
    from tools.pricing import PricingCatalog
    from tools.schedule_4d import WorkCalendar
    schemas={'rates_pk.json':RateCatalog,'labour_rates.json':LabourRateCatalog,'bylaws.json':BylawDatabase,
             'model_pricing.json':PricingCatalog,'calendar_exceptions.json':WorkCalendar}
    if filename not in schemas:raise ConfigurationError('Unknown configuration file.')
    override=st.session_state.get('gh_config_'+filename)
    if override is not None:return schemas[filename].model_validate(override)
    return load_json(DATA_DIR/filename,schemas[filename])


def protect_secret(text: str) -> None:
    try:credentials=resolve_credentials(st.session_state.get('gh_api_key',''),_available_secrets())
    except ValueError:credentials=None
    if credentials and credentials.api_key.get_secret_value() in text:
        raise WorkflowError('Remove the API key from project text; use the password sidebar only.')


def selected_context():
    workspace=get_workspace(st.session_state)
    req=workspace.get_output(Stage.REQUIREMENTS)
    layout=workspace.selected_layout();planning=workspace.get_output(Stage.PLANNING)
    option=next(a for a in planning.alternatives if a.layout.id==layout.id)
    envelope=st.session_state.get('gh_planning_envelope')
    if envelope is None or st.session_state.get('gh_envelope_requirements_hash')!=content_hash(req):
        raise WorkflowError('Review the current concept envelope in Floor Plans.')
    return workspace,req,layout,option,envelope


def _check_sources(request: Contract):
    workspace=get_workspace(st.session_state)
    protect_secret(request.model_dump_json())
    req=getattr(request,'requirements',None)
    if req is not None and content_hash(req)!=content_hash(workspace.get_output(Stage.REQUIREMENTS)):
        raise WorkflowError('Stage brief differs from approved requirements.')
    layout=getattr(request,'layout',None)
    if layout is not None and content_hash(layout)!=content_hash(workspace.selected_layout()):
        raise WorkflowError('Stage layout differs from selected planning output.')
    schedule=getattr(request,'schedule',None)
    if schedule is not None and content_hash(schedule)!=content_hash(workspace.get_output(Stage.SCHEDULE)):
        raise WorkflowError('Stage schedule is not the approved baseline.')


def run_local(stage: Stage,request: Contract,operation):
    workspace=get_workspace(st.session_state)
    _check_sources(request)
    key=content_hash(request)
    workspace.authorize(stage,request,reviewed_hash=key,user_approved=True)
    workspace.start(stage,request)
    try:result=operation(request);workspace.complete(stage,request,result)
    except Exception:workspace.fail(stage);raise
    return result


def generation_control(stage: Stage,request: Contract,operation,label: str):
    fingerprint=content_hash(request)
    from ui.components import get_runtime
    runtime=get_runtime(required=False)
    if runtime:
        def prepared_operation(value):
            _check_sources(value)
            return operation(value)
        runtime.orchestrator.prepare(stage,request,prepared_operation)
    reviewed=st.checkbox('I reviewed these inputs and accept the stated estimation assumptions',key='gh_review_input_'+stage.value+'_'+fingerprint)
    if st.button(label,disabled=not reviewed,type='primary',key='gh_run_'+stage.value):
        try:
            with st.spinner('Generating '+stage.value+'...'):run_local(stage,request,operation)
            st.rerun()
        except (AgentError,WorkflowError) as error:st.error(str(error))
        except (ValueError,TypeError,KeyError,ArithmeticError):st.error('Invalid stage inputs. Check quantities, dates, units and required values.')


def approved_output(stage: Stage):
    try:return get_workspace(st.session_state).get_output(stage)
    except WorkflowError:return None
