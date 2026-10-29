"""Covered-area benchmark, explicit item allowances and cost scenario comparison."""
from __future__ import annotations
import json
import streamlit as st
import plotly.graph_objects as go
from agents.cost_agent import CostAgent
from config import ConfigurationError
from schemas import Stage,Quality,content_hash
from tools.cost import CostInput,QuantityRule,ExtraCharge,Milestone
from ui.components import back_to_home,hero,render_review_gate,tr
from ui.workflow import selected_context,read_config,generation_control,approved_output,today
from ui.state import WorkflowError


def main():
    back_to_home();hero('💰 '+tr('cost'),'Compare benchmark and itemized allowances without adding the two methods together.')
    try:workspace,req,layout,option,envelope=selected_context();catalog=read_config('rates_pk.json')
    except (WorkflowError,ConfigurationError) as error:st.info(str(error));return
    with st.expander('Estimate inputs',expanded=workspace.record(Stage.COST).status not in {'review','approved'}):
        st.caption('Benchmark seeds are unverified scenarios. Empty prices remain unresolved. A quantity surveyor must check BOQ scope and coefficients.')
        basis=st.selectbox('Selected estimate basis',['area_benchmark','boq'])
        valuation=st.date_input('Valuation date',value=today())
        left,right=st.columns(2);contingency=left.number_input('Contingency percent',0.,50.,10.);tax=right.number_input('Tax scenario percent',0.,100.,0.)
        rules=st.text_area('Itemized quantity rules JSON',value='[]',height=160,help='Coefficients must be supplied. Use the schema and example below; no material mix or reinforcement ratio is guessed.')
        st.caption('Each row requires id, description, rate_id, unit, basis, quantity_per_basis_unit, phase, category, source and a unique scope_key. Optional manual_quantity, waste_percent and labour_fraction follow the rule schema.')
        st.json(QuantityRule.model_json_schema(),expanded=False)
        extras=st.text_area('Explicit fees and utility extras JSON',value=json.dumps([
            {'id':'professional','label':'Architect/engineer fees','rate_id':'professional_fee','unit':'job','quantity':1,'category':'professional_fee'},
            {'id':'approval','label':'Approval/NOC fees','rate_id':'approval_fee','unit':'job','quantity':1,'category':'approval'},
            {'id':'utility','label':'Utility connections','rate_id':'utility_connection','unit':'job','quantity':1,'category':'utility'}],indent=2),height=150)
        payments=st.text_area('Milestone percentages JSON',value=json.dumps([{'label':'Contract','percent':10},{'label':'Grey complete','percent':35},
            {'label':'Roof/plaster','percent':20},{'label':'Finishing','percent':25},{'label':'Handover','percent':10}],indent=2),height=130)
        benchmark_scope=st.checkbox('I reviewed the benchmark scope and excluded extras')
        boq_scope=st.checkbox('A quantity surveyor has checked the listed BOQ scope for this scenario')
        try:
            request=CostInput(requirements=req,layout=layout,envelope=envelope,access=option.access,rates=catalog,
                valuation_date=valuation,quantity_rules=[QuantityRule.model_validate(r) for r in json.loads(rules)],
                extra_charges=[ExtraCharge.model_validate(r) for r in json.loads(extras)],milestones=[Milestone.model_validate(r) for r in json.loads(payments)],
                selected_basis=basis,contingency_percent=contingency,tax_percent=tax,assumptions_accepted=True,
                area_rate_scope_accepted=benchmark_scope,boq_scope_declared_complete=boq_scope)
        except (ValueError,TypeError):request=None
        if request:generation_control(Stage.COST,request,lambda v:CostAgent.estimate(v,reviewed_hash=content_hash(v),user_approved=True),'Calculate indicative estimate')
        else:st.info('Correct the quantity, fee and milestone JSON before estimating.')
    if workspace.record(Stage.COST).status in {'review','approved'}:
        result=workspace.outputs[Stage.COST]
        columns=st.columns(3)
        for col,label,value in zip(columns,['Construction PKR','Grand total PKR','Known BOQ subtotal PKR'],[result.construction_pkr,result.grand_total_pkr,result.boq_known_subtotal_pkr]):
            col.metric(label,f'{value:,.2f}' if value is not None else 'Unresolved')
        st.dataframe([r.model_dump(mode='json') for r in result.rows],hide_index=True)
        st.dataframe([{'Method':'Area benchmark','PKR':result.area_benchmark_pkr},{'Method':'Complete BOQ','PKR':result.boq_total_pkr}],hide_index=True)
        if result.grey_pkr is not None and result.finishing_pkr is not None:
            st.plotly_chart(go.Figure(go.Bar(x=['Grey','Finishing'],y=[result.grey_pkr,result.finishing_pkr],marker_color=['#3949AB','#8E24AA'])).update_layout(title='Construction split (PKR)'))
        with st.expander('Evidence and estimate review items'):
            for warning in result.warnings:st.write(warning)
        render_review_gate(Stage.COST)
        approved=approved_output(Stage.COST)
        if approved:st.download_button('Download reviewed estimate JSON',approved.model_dump_json(indent=2),file_name='GharBuilder_Cost.json',mime='application/json')
    with st.expander('What-if benchmark scenario'):
        st.caption('Scenario only. These controls do not revise the approved geometry, floor count or baseline estimate.')
        total_area=sum(f.covered_area_m2 for f in layout.floors)/.3048**2
        scale=st.slider('Covered-area multiplier',.5,2.,1.,.05)
        quality=st.selectbox('Scenario finishing quality',[q.value for q in Quality],index=list(Quality).index(req.quality))
        rate=next((r for r in catalog.area_rates if r.quality.value==quality),None)
        factor=next((c.multiplier for c in catalog.city_factors if c.city.casefold()==req.city.casefold()),None)
        finish=0 if quality=='Grey only' else rate.finishing_pkr_sqft if rate else None
        if rate and rate.grey_pkr_sqft is not None and finish is not None and factor is not None:
            st.metric('Scenario construction benchmark PKR',f'{total_area*scale*(rate.grey_pkr_sqft+finish)*factor:,.0f}')
        else:st.info('Scenario rate or city factor is unresolved.')

main()
