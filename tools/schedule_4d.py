"""Dependency-based concept schedule, Gantt and weekly 3D sequence.

Calendar dates are explicit. Work effort is in productive crew-days per task,
not person-days. Finish/release dates are exclusive day boundaries. Curing is
an elapsed calendar wait after finish; it is not reduced by working-day factors.
"""
from __future__ import annotations

from collections import defaultdict
from datetime import date, timedelta
from typing import Annotated, Literal

import plotly.graph_objects as go
from pydantic import Field, model_validator

from schemas import Activity, Contract, Identifier, content_hash
from tools.model_3d import BuildingModel, plotly_figure

TaskKind = Literal['site_prep','excavation','foundation','dpc','columns','brickwork','slab',
                   'rough_in','waterproofing','plaster','flooring','woodwork','paint',
                   'fixtures','external','handover']
TASK_KINDS = ('site_prep','excavation','foundation','dpc','columns','brickwork','slab',
              'rough_in','waterproofing','plaster','flooring','woodwork','paint',
              'fixtures','external','handover')


class CalendarException(Contract):
    name: str = Field(min_length=1)
    start: date
    end_inclusive: date
    productivity_factor: float = Field(ge=0,le=1)
    source: str = Field(min_length=1)

    @model_validator(mode='after')
    def ordered(self) -> CalendarException:
        if self.end_inclusive<self.start:
            raise ValueError('Calendar exception dates are reversed.')
        return self


class WorkCalendar(Contract):
    # Monday=0 ... Sunday=6. No religious/public holidays inferred from names.
    working_weekdays: list[int] = Field(min_length=1,max_length=7)
    exceptions: list[CalendarException] = Field(default_factory=list)

    @model_validator(mode='after')
    def valid_days(self) -> WorkCalendar:
        if len(set(self.working_weekdays))!=len(self.working_weekdays) or any(d<0 or d>6 for d in self.working_weekdays):
            raise ValueError('Weekdays must be unique integers in 0..6.')
        return self

    def factor(self, day: date) -> float:
        if day.weekday() not in self.working_weekdays:
            return 0.
        # Conservative overlap policy: minimum factor, not compounded penalties.
        return min([1.,*[x.productivity_factor for x in self.exceptions if x.start<=day<=x.end_inclusive]])


class TaskRecipe(Contract):
    kind: TaskKind
    productive_days: int = Field(ge=1,le=3650)
    crew_size: int = Field(ge=1,le=1000)
    curing_days: int = Field(ge=0,le=3650)


class ScheduleAssumptions(Contract):
    source: str = Field(min_length=1)
    accepted_for_planning: bool = False
    recipes: list[TaskRecipe]
    calendar: WorkCalendar
    # Truncation is an explicit failure, never a silently incomplete schedule.
    max_calendar_days: int = Field(default=3650,ge=1,le=7300)

    @model_validator(mode='after')
    def complete_recipes(self) -> ScheduleAssumptions:
        kinds=[r.kind for r in self.recipes]
        if len(set(kinds))!=len(kinds) or set(kinds)!=set(TASK_KINDS):
            raise ValueError('Supply exactly one duration/crew/curing recipe for every task kind.')
        return self


class LinkedActivity(Activity):
    """Scheduling specialization accepts the 3D model's hierarchical element IDs."""
    element_ids: list[Annotated[str, Field(min_length=1,max_length=300,
        pattern=r'^[A-Za-z0-9_-]+(?:/[A-Za-z0-9_-]+)*$')]] = Field(default_factory=list)


class ScheduledActivity(Contract):
    activity: LinkedActivity
    start: date
    finish_exclusive: date
    release_exclusive: date
    working_dates: list[date]
    daily_earned_days: list[float]


class ScheduleResult(Contract):
    input_hash: str
    model_hash: str
    start: date
    finish_exclusive: date
    duration_calendar_days: int
    tasks: list[ScheduledActivity]
    warnings: list[str]


def model_fingerprint(model: BuildingModel) -> str:
    return content_hash({'layout_id':model.layout_id,'floors':list(model.floor_ids),
        'elements':[{'id':e.id,'floor':e.floor_id,'kind':e.kind,
                     'vertices':e.mesh.vertices.tolist(),'faces':e.mesh.faces.tolist()} for e in model.elements]})


def generate_wbs(model: BuildingModel, assumptions: ScheduleAssumptions) -> list[LinkedActivity]:
    """One task per mesh-producing phase, with fit-out tasks per floor.

    The lowest model floor is the first structure level. Basement-specific
    shoring/dewatering and any foundation system require a customized WBS before
    contractual use. Generic recipes are not measured productivity estimates.
    """
    if not assumptions.accepted_for_planning:
        raise ValueError('Accept the duration, crew and curing assumptions before scheduling.')
    recipes={r.kind:r for r in assumptions.recipes}
    tasks=[]
    def add(key: str,kind: str,name: str,previous: list[str],fid=None,elements=None):
        recipe=recipes[kind]
        tasks.append(LinkedActivity(id=key,name=name,duration_days=recipe.productive_days,
            predecessor_ids=previous,element_ids=elements or [],floor_id=fid,
            curing_days=recipe.curing_days,crew_size=recipe.crew_size))
    add('site_prep','site_prep','Site preparation',[])
    add('excavation','excavation','Excavation',['site_prep'])
    add('foundation','foundation','Foundation allowance',['excavation'])
    add('dpc','dpc','DPC / substructure interface',['foundation'])
    previous='dpc';rough=[]
    for index,fid in enumerate(model.floor_ids):
        prefix=f'floor_{index}'
        ids=lambda kinds:[e.id for e in model.elements if e.floor_id==fid and e.kind in kinds]
        col=prefix+'_columns';brick=prefix+'_brick';slab=prefix+'_slab';mep=prefix+'_rough'
        add(col,'columns',fid+' | columns / structural coordination',[prefix+'_base_slab'],fid)
        # Floor base slab belongs to the structure entering this level; roof and
        # stair flight belong to the closure of this level, avoiding duplicate IDs.
        base=prefix+'_base_slab'
        add(base,'slab',fid+' | floor base slab',[previous],fid,ids({'slab'}))
        add(brick,'brickwork',fid+' | walls',[col],fid,ids({'wall'}))
        add(slab,'slab',fid+' | stair / roof structure',[brick],fid,ids({'stairs','roof','parapet'}))
        add(mep,'rough_in',fid+' | electrical / plumbing rough-in',[slab],fid)
        rough.append(mep);previous=slab
    fitout=[]
    for index,fid in enumerate(model.floor_ids):
        prefix=f'fit_{index}'
        last=None
        for suffix,kind,label in [('waterproof','waterproofing','Waterproofing'),('plaster','plaster','Plaster'),
                                  ('floor','flooring','Flooring'),('wood','woodwork','Woodwork'),
                                  ('paint','paint','Paint'),('fixtures','fixtures','Fixtures / opening infill')]:
            key=prefix+'_'+suffix
            ids=[e.id for e in model.elements if e.floor_id==fid and e.kind in {'door','window'}] if kind=='fixtures' else []
            add(key,kind,fid+' | '+label,[last] if last else rough,fid,ids)
            last=key
        fitout.append(last)
    add('external','external','External works',fitout)
    add('handover','handover','Inspection / handover',['external'])
    return tasks


def build_schedule(activities: list[Activity], start: date, calendar: WorkCalendar,
                   *, model: BuildingModel, max_calendar_days: int=3650,
                   input_hash: str='') -> ScheduleResult:
    """Topological CPM-style early starts; no finite-resource levelling is implied."""
    if not activities or len(activities)>1000:
        raise ValueError('Supply 1..1000 activities.')
    if max_calendar_days<1 or max_calendar_days>7300:
        raise ValueError('Calendar horizon must be in 1..7300 days.')
    calendar=WorkCalendar.model_validate(calendar.model_dump(mode='json'))
    activities=[LinkedActivity.model_validate(a.model_dump(mode='json')) for a in activities]
    lookup={a.id:a for a in activities}
    if len(lookup)!=len(activities):
        raise ValueError('Activity IDs must be unique.')
    known={e.id for e in model.elements};assigned=[]
    for a in activities:
        if a.floor_id is not None and a.floor_id not in model.floor_ids:
            raise ValueError('Unknown activity floor.')
        if len(set(a.predecessor_ids))!=len(a.predecessor_ids):
            raise ValueError('Duplicate predecessor.')
        if set(a.predecessor_ids)-set(lookup):
            raise ValueError('Unknown predecessor.')
        if set(a.element_ids)-known:
            raise ValueError('Unknown linked model element.')
        assigned+=a.element_ids
    if len(assigned)!=len(set(assigned)):
        raise ValueError('An element is linked more than once in the construction sequence.')
    if set(assigned)!=known:
        raise ValueError('Every model element must have one construction activity.')
    scheduled={};pending=dict(lookup);limit=start+timedelta(days=max_calendar_days)
    while pending:
        ready=[a for a in pending.values() if set(a.predecessor_ids)<=set(scheduled)]
        if not ready:
            raise ValueError('Activity dependencies contain a cycle.')
        for a in ready:
            earliest=max([start,*[scheduled[p].release_exclusive for p in a.predecessor_ids]])
            cursor=earliest;remaining=float(a.duration_days);dates=[];earned=[]
            while remaining>1e-9:
                if cursor>=limit:
                    raise ValueError('Schedule exceeds the configured calendar horizon.')
                factor=calendar.factor(cursor)
                if factor>0:
                    day_effort=min(remaining,factor)
                    dates.append(cursor);earned.append(day_effort);remaining-=day_effort
                cursor+=timedelta(days=1)
            release=cursor+timedelta(days=a.curing_days)
            if release>limit:
                raise ValueError('Curing release exceeds the configured calendar horizon.')
            scheduled[a.id]=ScheduledActivity(activity=a,start=dates[0],finish_exclusive=cursor,
                release_exclusive=release,working_dates=dates,daily_earned_days=earned)
            del pending[a.id]
    tasks=sorted(scheduled.values(),key=lambda t:(t.start,t.activity.id))
    finish=max(t.release_exclusive for t in tasks)
    warnings=[
        'Preliminary planning schedule. Durations, crews and curing are supplied assumptions, not engineering prescriptions.',
        'Finish and release dates are exclusive. An activity is complete at its release boundary, including its curing wait.',
        'No finite-resource levelling, procurement, permit lead times, structural analysis or baseline calibration is included.',
        'Generic basement work excludes shoring/dewatering. MEP commissioning, lift commissioning and project-specific scope require additional activities.',
        'Overlapping calendar exceptions use the minimum productivity factor. Curing uses elapsed calendar days.',
        'Weekly mesh sequence is element-level appearance at release; no fabricated percentage of structural adequacy is implied.',
    ]
    return ScheduleResult(input_hash=input_hash,model_hash=model_fingerprint(model),start=start,
        finish_exclusive=finish,duration_calendar_days=(finish-start).days,tasks=tasks,warnings=warnings)


def gantt_figure(result: ScheduleResult) -> go.Figure:
    """Productive-work span plus visually distinct curing wait, in calendar time."""
    fig=go.Figure()
    for task in result.tasks:
        name=task.activity.name
        fig.add_trace(go.Bar(y=[name],x=[(task.finish_exclusive-task.start).days*86400000],
            base=[task.start.isoformat()],orientation='h',marker_color='#3949AB',
            name='Work span',showlegend=False,
            hovertemplate='Work span (includes nonworking dates)<br>'+task.start.isoformat()+' to '+task.finish_exclusive.isoformat()+' (exclusive)<extra></extra>'))
        days=(task.release_exclusive-task.finish_exclusive).days
        if days:
            fig.add_trace(go.Bar(y=[name],x=[days*86400000],base=[task.finish_exclusive.isoformat()],
                orientation='h',marker_color='#FB8C00',name='Curing wait',showlegend=False,
                hovertemplate='Curing wait: '+str(days)+' calendar days<extra></extra>'))
    fig.update_layout(title='Concept construction schedule | blue: work span · orange: curing wait',
        barmode='overlay',xaxis={'type':'date','title':'Calendar date'},
        yaxis={'autorange':'reversed'},height=max(450,28*len(result.tasks)),margin={'l':25,'r':20,'t':60,'b':30})
    return fig


def workforce_by_day(result: ScheduleResult) -> list[dict]:
    """Crew attendance assumes a full crew on any productive date, including partial last days."""
    totals=defaultdict(int)
    for t in result.tasks:
        for d in t.working_dates:
            totals[d]+=t.activity.crew_size
    return [{'date':d.isoformat(),'workers':totals[d]} for d in sorted(totals)]


def planned_progress(result: ScheduleResult, as_of: date) -> float:
    """Effort-weighted productive-work progress through the end of as_of date.

    This excludes curing and is not budget-weighted physical completion.
    """
    total=sum(t.activity.duration_days for t in result.tasks)
    earned=sum(e for t in result.tasks for d,e in zip(t.working_dates,t.daily_earned_days) if d<=as_of)
    return 100*earned/total


def construction_figure(model: BuildingModel, result: ScheduleResult,
                        *, max_frames: int=104) -> go.Figure:
    if result.model_hash!=model_fingerprint(model):
        raise ValueError('The model changed; rebuild its schedule before animation.')
    if not 2<=max_frames<=300:
        raise ValueError('Frame limit must be in 2..300.')
    releases={eid:t.release_exclusive for t in result.tasks for eid in t.activity.element_ids}
    dates=[result.start+timedelta(days=d) for d in range(0,result.duration_calendar_days+1,7)]
    if dates[-1]!=result.finish_exclusive:
        dates.append(result.finish_exclusive)
    if len(dates)>max_frames:
        raise ValueError('Weekly animation exceeds frame limit. Increase the limit or shorten the scope.')
    fig=plotly_figure(model)
    frames=[]
    for day in dates:
        visibility=[releases[e.id]<=day for e in model.elements]
        frames.append(go.Frame(name=day.isoformat(),traces=list(range(len(model.elements))),
                              data=[go.Mesh3d(visible=v) for v in visibility]))
    fig.frames=frames
    for trace,e in zip(fig.data,model.elements):
        trace.visible=releases[e.id]<=dates[0]
    steps=[{'label':d.isoformat(),'method':'animate','args':[[d.isoformat()],
            {'mode':'immediate','frame':{'duration':0,'redraw':True},'transition':{'duration':0}}]} for d in dates]
    fig.update_layout(title='4D concept | weekly element sequence at release dates',
        sliders=[{'active':0,'steps':steps,'currentvalue':{'prefix':'As of start of: '}}],
        updatemenus=[{'type':'buttons','buttons':[
            {'label':'Play','method':'animate','args':[None,{'frame':{'duration':500,'redraw':True},'transition':{'duration':0},'fromcurrent':True}]},
            {'label':'Pause','method':'animate','args':[[None],{'mode':'immediate','frame':{'duration':0,'redraw':False}}]}]}])
    return fig
