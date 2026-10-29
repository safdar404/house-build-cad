"""Reviewed 4D baseline with editable work/curing assumptions and calendar."""
from __future__ import annotations
import json
import streamlit as st
from ui.choices import source_choice
from ui.editors import calendar_editor,fill_missing_recipes
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
        seed_key='gh_schedule_seed_'+key;version_key='gh_schedule_editor_version_'+key
        version=st.session_state.get(version_key,0)
        rows=st.data_editor(st.session_state.get(seed_key,rows),key='gh_schedule_recipes_'+key+'_'+str(version),disabled=['kind'],hide_index=True,
            column_config={'productive_days':st.column_config.NumberColumn('Productive days',min_value=1,max_value=3650,step=1),
                'crew_size':st.column_config.NumberColumn('Crew size',min_value=1,max_value=1000,step=1),
                'curing_days':st.column_config.NumberColumn('Curing wait (days)',min_value=0,max_value=3650,step=1)})
        with st.expander('Fill missing recipe cells from my supplied starting values'):
            st.caption('These are your scenario inputs. Known cells are kept. Review every recipe, especially curing waits; no engineering curing period is recommended here.')
            col=st.columns(3)
            days=col[0].selectbox('Productive days starting value',[None,*range(1,31)],format_func=lambda v:'Keep unset' if v is None else str(v))
            crew=col[1].selectbox('Crew size starting value',[None,*range(1,51)],format_func=lambda v:'Keep unset' if v is None else str(v))
            cure=col[2].selectbox('Curing days starting value',[None,*range(0,29)],format_func=lambda v:'Keep unset' if v is None else str(v))
            if st.button('Fill only missing recipe cells'):
                st.session_state[seed_key]=fill_missing_recipes(rows,days,crew,cure)
                st.session_state[version_key]=version+1;st.rerun()
        source=source_choice('Duration/crew/curing source',key='gh_schedule_source')
        start=st.date_input('Construction start date',value=req.start_date)
        calendar_default=read_config('calendar_exceptions.json')
        try:calendar=calendar_editor(calendar_default,key='gh_schedule_calendar')
        except ValueError:calendar=None;st.info('Choose working days and complete any added exception rows.')
        horizon=st.number_input('Maximum calendar horizon days',min_value=30,max_value=7300,value=3650)
        try:
            assumptions=ScheduleAssumptions(source=source,accepted_for_planning=True,
                recipes=[TaskRecipe.model_validate(r) for r in rows],calendar=calendar,
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
