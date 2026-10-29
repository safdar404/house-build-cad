"""User-reported progress, room inspection and explicitly simulated sensor charts."""
from __future__ import annotations
from datetime import datetime,time
from zoneinfo import ZoneInfo
from uuid import uuid4
import streamlit as st
from agents.twin_agent import DigitalTwinAgent
from schemas import Stage,content_hash
from tools.twin import (TwinInput,ProgressObservation,SensorSimulation,simulate_sensors,sensor_figures,
    progress_figure,room_map_figure,inspect_room)
from ui.components import back_to_home,hero,render_review_gate,tr
from ui.workflow import selected_context,generation_control,approved_output,today,protect_secret
from ui.state import WorkflowError


def main():
    back_to_home();hero('📊 '+tr('twin'),'User-entered construction observations and a separate demonstration of operational sensors.')
    try:workspace,req,layout,option,envelope=selected_context();schedule=workspace.get_output(Stage.SCHEDULE)
    except WorkflowError as error:st.info(str(error));return
    cost=approved_output(Stage.COST);mep=approved_output(Stage.MEP)
    history_key='gh_observations_'+content_hash(schedule)
    history=st.session_state.setdefault(history_key,[])
    as_of=st.date_input('Monitoring as-of date',value=today())
    with st.expander('Record progress and cumulative actual costs'):
        observed=st.date_input('Observation date',value=as_of)
        source=st.text_input('Observation source / site record reference')
        entries=st.data_editor([{'activity_id':t.activity.id,'task':t.activity.name,'progress_percent':None,
            'cumulative_actual_cost_pkr':None} for t in schedule.tasks],disabled=['activity_id','task'],hide_index=True,
            key='gh_progress_entries_'+content_hash(schedule))
        correction=st.checkbox('Replace a previous record for the same task and observation date')
        if st.button('Save observations'):
            try:
                protect_secret(source)
                if not source.strip():raise ValueError('Source required.')
                additions=[ProgressObservation(id=uuid4().hex,activity_id=r['activity_id'],observed_on=observed,
                    progress_percent=r['progress_percent'],cumulative_actual_cost_pkr=r['cumulative_actual_cost_pkr'],source=source)
                    for r in entries if r['progress_percent'] is not None]
                if not additions:raise ValueError('Enter at least one progress value.')
                pairs={(o.activity_id,o.observed_on) for o in additions}
                if any((o.activity_id,o.observed_on) in pairs for o in history) and not correction:
                    raise ValueError('A record already exists for this task/date; explicitly enable replacement.')
                history[:]=[o for o in history if (o.activity_id,o.observed_on) not in pairs]+additions
                workspace.invalidate(Stage.TWIN);st.success('Dated observations saved. Generate a reviewed snapshot below.')
            except (ValueError,WorkflowError) as error:st.error(str(error) if isinstance(error,WorkflowError) else 'Check progress/cost values, source and duplicate task dates.')
        st.caption('Blank rows are unreported, not zero progress. Saving observations does not assert independent verification.')
    budget_known=st.checkbox('A like-for-like construction budget is available',value=cost is not None and cost.construction_pkr is not None)
    budget=st.number_input('Construction budget PKR',min_value=.01,value=float(cost.construction_pkr) if cost and cost.construction_pkr else 1.,step=1000.)
    budget_source=st.text_input('Budget source',value='Reviewed construction estimate' if cost else 'User-supplied budget')
    spend_scope=st.text_input('Actual spend scope',value='Construction-only task costs; exclude fees, tax and contingency')
    complete=st.checkbox('All task costs have been reported with complete matching scope')
    try:
        request=TwinInput(layout=layout,reviewed_layout_hash=content_hash(layout),schedule=schedule,
            reviewed_schedule_hash=content_hash(schedule),as_of=as_of,observations=history,
            construction_budget_pkr=budget if budget_known else None,budget_source=budget_source,spend_scope=spend_scope,
            spend_coverage_declared_complete=complete)
        generation_control(Stage.TWIN,request,lambda v:DigitalTwinAgent.snapshot(v,reviewed_hash=content_hash(v),user_approved=True),'Generate monitoring snapshot')
    except ValueError:st.info('Provide budget and spend-scope descriptions before generating the snapshot.');return
    if workspace.record(Stage.TWIN).status in {'review','approved'}:
        result=workspace.outputs[Stage.TWIN]
        st.plotly_chart(progress_figure(result))
        for alert in result.alerts:st.warning(alert)
        st.metric('Progress reporting coverage',f'{result.progress_reporting_coverage_percent:.1f}%')
        st.dataframe(result.floor_progress,hide_index=True)
        render_review_gate(Stage.TWIN)
    st.subheader('Room inspection')
    floor_id=st.selectbox('Inspect floor',[f.floor_id for f in layout.floors])
    figure=room_map_figure(layout,floor_id)
    event=st.plotly_chart(figure,on_select='rerun',selection_mode='points',key='gh_room_map_'+content_hash(layout)+'_'+floor_id)
    room_keys=[floor_id+'/'+r.id for f in layout.floors if f.floor_id==floor_id for r in f.rooms]
    clicked=None
    if event and event.selection.points:
        point=event.selection.points[0];candidate=point.get('customdata')
        if isinstance(candidate,list) and candidate:candidate=candidate[0]
        if candidate in room_keys:clicked=candidate
    selected=st.selectbox('Room',room_keys,index=room_keys.index(clicked) if clicked else 0,key='gh_room_choice_'+floor_id+'_'+str(clicked))
    st.json(inspect_room(request,selected,cost_report=cost,reviewed_cost_hash=content_hash(cost) if cost else None,
        mep_report=mep,reviewed_mep_hash=content_hash(mep) if mep else None),expanded=False)
    st.subheader('SIMULATED DATA - no connected sensors')
    st.caption('These series do not represent measured weather, energy, tank levels or actual building operations.')
    hours=st.slider('Simulation hours',24,168,48,24)
    date_start=st.date_input('Simulation start date',value=as_of)
    if st.button('Generate simulated sensor series'):
        config=SensorSimulation(start=datetime.combine(date_start,time(0),ZoneInfo('Asia/Karachi')),hours=hours)
        st.session_state['gh_sensor_demo']=(content_hash(layout),simulate_sensors([f.floor_id+'/'+r.id for f in layout.floors for r in f.rooms],config))
    demo=st.session_state.get('gh_sensor_demo')
    if demo and demo[0]==content_hash(layout):
        for name,fig in sensor_figures(demo[1],selected).items():st.plotly_chart(fig,key='gh_sensor_'+name)

main()
