"""Trade crew allocation, dated wage overrides and contract scenarios."""
from __future__ import annotations
import streamlit as st
from agents.labour_agent import LabourAgent
from schemas import Stage,content_hash
from tools.labour import (LabourInput,TaskCrew,TradeCrew,WageRate,TradeAvailability,workforce_figure)
from ui.components import back_to_home,hero,render_review_gate,tr
from ui.workflow import selected_context,read_config,generation_control,approved_output,today
from ui.state import WorkflowError


def _suggest_trade(task):
    name=task.activity.name.casefold()
    if 'electrical' in name:return 'electrician'
    if 'paint' in name:return 'painter'
    if 'flooring' in name:return 'tile_fixer'
    if 'wood' in name:return 'wood_worker'
    if 'slab' in name:return 'shuttering_carpenter'
    if 'column' in name:return 'steel_fixer'
    if 'wall' in name or 'plaster' in name or 'dpc' in name:return 'mason'
    return 'labourer'


def main():
    back_to_home();hero('👷 '+tr('labour'),'Review crew composition, paid attendance, wage evidence and alternative contract scenarios.')
    try:
        workspace,req,layout,option,envelope=selected_context()
        schedule=workspace.get_output(Stage.SCHEDULE);cost=workspace.get_output(Stage.COST)
        rates=read_config('labour_rates.json')
    except (WorkflowError,ValueError) as error:st.info(str(error));return
    trades=['mason','labourer','steel_fixer','shuttering_carpenter','electrician','plumber','tile_fixer','painter','welder','wood_worker']
    with st.expander('Crew and wage inputs',expanded=workspace.record(Stage.LABOUR).status not in {'review','approved'}):
        st.caption('Suggested trade labels below are editable classifications, not measured labour productivity. Each row must match the schedule crew total.')
        seed=[]
        for task in schedule.tasks:
            n=task.activity.crew_size;trade=_suggest_trade(task)
            seed.append({'activity_id':task.activity.id,'main_trade':trade,'main_workers':n if trade=='labourer' else min(1,n),
                         'helpers':0 if trade=='labourer' else max(0,n-1),'schedule_crew':n})
        rows=st.data_editor(seed,key='gh_trade_crews_'+content_hash(schedule),disabled=['activity_id','schedule_crew'],hide_index=True)
        valuation=st.date_input('Wage valuation date',value=today())
        st.write('Wages for '+rates.city)
        wage_rows=st.data_editor([{'trade':w.trade,'daily_wage_pkr':w.daily_wage_pkr} for w in rates.wages],
            key='gh_wage_editor_'+content_hash(rates),disabled=['trade'],hide_index=True)
        wage_source=st.text_input('Source for any wage changes',key='gh_wage_override_source')
        wage_date=st.date_input('Effective date for changed quotations',value=today())
        material_available=st.checkbox('A like-for-like material-only cost allowance is available',value=cost.material_pkr is not None)
        material=st.number_input('Material-only cost PKR',min_value=0.,value=float(cost.material_pkr or 0),step=1000.)
        source=st.text_input('Material cost source',value='Reviewed cost construction split' if cost.material_pkr is not None else '')
        overhead=st.number_input('Payroll overhead percent',min_value=0.,max_value=100.,value=0.)
        margin=st.number_input('Contractor margin percent',min_value=0.,max_value=100.,value=0.)
        try:
            effective=rates.model_copy(deep=True)
            if effective.city.casefold()!=req.city.casefold():raise ValueError('Update wage catalog city in Rates Settings.')
            for w,row in zip(effective.wages,wage_rows):
                changed=row['daily_wage_pkr']!=w.daily_wage_pkr
                w.daily_wage_pkr=row['daily_wage_pkr']
                if changed:
                    if not wage_source.strip():raise ValueError('A wage source is required.')
                    w.evidence=w.evidence.model_copy(update={'source':wage_source,'effective_date':wage_date,
                        'verified':False,'verified_by':None,'source_url':None})
            allocations=[]
            for row in rows:
                if row['main_trade'] not in trades:raise ValueError('Unknown trade.')
                crew=[]
                if int(row['main_workers'])>0:crew.append(TradeCrew(trade=row['main_trade'],workers=int(row['main_workers'])))
                if int(row['helpers'])>0:
                    if row['main_trade']=='labourer':raise ValueError('Include all labourers in main_workers for a labourer-only crew.')
                    crew.append(TradeCrew(trade='labourer',workers=int(row['helpers'])))
                if sum(t.workers for t in crew)!=row['schedule_crew']:raise ValueError('Crew total mismatch.')
                allocations.append(TaskCrew(activity_id=row['activity_id'],trades=crew))
            request=LabourInput(city=req.city,schedule=schedule,reviewed_schedule_hash=content_hash(schedule),rates=effective,
                valuation_date=valuation,task_crews=allocations,material_cost_pkr=material if material_available else None,
                material_cost_source=source or 'Not supplied',overhead_percent=overhead,contractor_margin_percent=margin,assumptions_accepted=True)
        except (ValueError,TypeError,KeyError):request=None
        if request:generation_control(Stage.LABOUR,request,lambda v:LabourAgent.estimate(v,reviewed_hash=content_hash(v),user_approved=True),'Calculate reviewed labour scenario')
        else:st.info('Check wage source/city, valid trade names and crew totals before calculating.')
    if workspace.record(Stage.LABOUR).status not in {'review','approved'}:return
    result=workspace.outputs[Stage.LABOUR]
    a,b,c=st.columns(3);a.metric('Paid person-days',result.paid_person_days);b.metric('Peak workers',result.peak_workers)
    c.metric('Total wages PKR',f'{result.total_wages_pkr:,.0f}' if result.total_wages_pkr is not None else 'Unresolved')
    st.plotly_chart(workforce_figure(result));st.dataframe([t.model_dump(mode='json') for t in result.totals],hide_index=True)
    st.dataframe([{'Scenario':'Labour-only contract','PKR':result.labour_only_contract_pkr},
                  {'Scenario':'Material + labour contract','PKR':result.material_plus_labour_contract_pkr}],hide_index=True)
    with st.expander('Scope and review items'):
        st.write(result.comparison_basis)
        for item in result.warnings:st.write(item)
    render_review_gate(Stage.LABOUR)
    approved=approved_output(Stage.LABOUR)
    if approved:st.download_button('Download labour JSON',approved.model_dump_json(indent=2),file_name='GharBuilder_Labour.json')

main()
