"""Reviewed 4D baseline with editable work/curing assumptions and calendar."""
from __future__ import annotations
import json
import streamlit as st
from agents.scheduling_agent import SchedulingAgent,SchedulingInput
from schemas import Stage,content_hash
from tools.schedule_4d import (TASK_KINDS,ScheduleAssumptions,TaskRecipe,WorkCalendar,
    model_fingerprint,gantt_figure,construction_figure,workforce_by_day)
from ui.components import back_to_home,hero,render_review_gate,tr
from ui.workflow import selected_context,read_config,generation_control,approved_output
from ui.state import WorkflowError


def main():
    back_to_home();hero('📅 '+tr('schedule'),'Set task effort, curing waits and explicit calendar exceptions, then review the baseline.')
    try:workspace,req,layout,option,envelope=selected_context();model=workspace.get_output(Stage.MODEL).model
    except WorkflowError as error:st.info(str(error));return
    key=model_fingerprint(model)
    st.caption('Durations below repeat per applicable floor. They are planning inputs, not measured productivity or structural curing prescriptions.')
    with st.expander('Duration and crew assumptions',expanded=workspace.record(Stage.SCHEDULE).status not in {'review','approved'}):
        rows=[{'kind':k,'productive_days':None,'crew_size':None,'curing_days':None} for k in TASK_KINDS]
        rows=st.data_editor(rows,key='gh_schedule_recipes_'+key,disabled=['kind'],hide_index=True)
        source=st.text_input('Duration/crew/curing source',key='gh_schedule_source')
        start=st.date_input('Construction start date',value=req.start_date)
        calendar_default=read_config('calendar_exceptions.json')
        calendar_text=st.text_area('Work calendar JSON',value=calendar_default.model_dump_json(indent=2),height=180,
            help='Weekdays: Monday=0. Ramadan/Eid, holidays and monsoon effects require explicitly sourced date ranges; none are inferred.')
        horizon=st.number_input('Maximum calendar horizon days',min_value=30,max_value=7300,value=3650)
        try:
            assumptions=ScheduleAssumptions(source=source,accepted_for_planning=True,
                recipes=[TaskRecipe.model_validate(r) for r in rows],calendar=WorkCalendar.model_validate_json(calendar_text),
                max_calendar_days=int(horizon))
            request=SchedulingInput(model_hash=key,start_date=start,assumptions=assumptions)
        except ValueError:request=None
        if request:
            generation_control(Stage.SCHEDULE,request,lambda v:SchedulingAgent.schedule(v,model,reviewed_hash=content_hash(v),user_approved=True),'Generate construction baseline')
        else:st.info('Enter productive days, crew size, curing days (zero if no wait), a source note and a valid calendar before generation.')
    if workspace.record(Stage.SCHEDULE).status not in {'review','approved'}:return
    result=workspace.outputs[Stage.SCHEDULE]
    st.metric('Duration (calendar days)',result.duration_calendar_days)
    st.caption('Finish/release dates are exclusive boundaries. Cure waits and resource availability need project-specific review.')
    st.plotly_chart(gantt_figure(result),key='gh_schedule_gantt_'+result.input_hash)
    st.dataframe([{'Task':t.activity.name,'Start':t.start,'Finish exclusive':t.finish_exclusive,
        'Release exclusive':t.release_exclusive,'Crew':t.activity.crew_size} for t in result.tasks],hide_index=True)
    with st.expander('Weekly model construction sequence'):
        limit=st.number_input('Maximum animation frames',min_value=2,max_value=300,value=104)
        try:st.plotly_chart(construction_figure(model,result,max_frames=int(limit)),key='gh_schedule_animation_'+result.input_hash)
        except ValueError:st.info('This schedule exceeds the frame limit or refers to an old model. Increase the limit or regenerate the baseline.')
    with st.expander('Review items'):
        for warning in result.warnings:st.write(warning)
    render_review_gate(Stage.SCHEDULE)
    approved=approved_output(Stage.SCHEDULE)
    if approved:st.download_button('Download reviewed baseline JSON',approved.model_dump_json(indent=2),file_name='GharBuilder_Schedule.json',mime='application/json')

main()
