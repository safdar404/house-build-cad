"""Concept digital twin: actual progress ledger, room inspection and simulated IoT.

No network sensor connection or automatic actuator action exists here. Simulation
and user-entered observations use separate contracts and separate chart labels.
"""
from __future__ import annotations

import html
import math
import random
from datetime import date, datetime, timedelta

import plotly.graph_objects as go
from pydantic import Field, model_validator

from schemas import Contract, Identifier, LayoutAlternative, NonNegative, Positive, content_hash
from tools.cost import CostReport, dec, money
from tools.schedule_4d import ScheduleResult, planned_progress


class ProgressObservation(Contract):
    id: Identifier
    activity_id: Identifier
    observed_on: date
    progress_percent: float = Field(ge=0,le=100)
    cumulative_actual_cost_pkr: NonNegative | None
    source: str = Field(min_length=1)
    note: str = ''


class RoomMaterials(Contract):
    room_key: str = Field(min_length=1)
    materials: list[str]
    source: str = Field(min_length=1)


class TwinInput(Contract):
    layout: LayoutAlternative
    reviewed_layout_hash: str
    schedule: ScheduleResult
    reviewed_schedule_hash: str
    as_of: date
    observations: list[ProgressObservation] = Field(default_factory=list)
    # Explicit like-for-like construction budget; do not substitute grand total
    # when the ledger excludes fees, taxes and contingency.
    construction_budget_pkr: Positive | None
    budget_source: str = Field(min_length=1)
    spend_scope: str = Field(min_length=1)
    spend_coverage_declared_complete: bool = False
    lag_alert_percentage_points: float = Field(default=10,ge=0,le=100)
    room_materials: list[RoomMaterials] = Field(default_factory=list)

    @model_validator(mode='after')
    def unique_records(self) -> TwinInput:
        if len({o.id for o in self.observations})!=len(self.observations):
            raise ValueError('Observation IDs must be unique.')
        pairs=[(o.activity_id,o.observed_on) for o in self.observations]
        if len(set(pairs))!=len(pairs):
            raise ValueError('One observation per activity/date is permitted; use an explicit correction instead of duplicates.')
        if len({r.room_key for r in self.room_materials})!=len(self.room_materials):
            raise ValueError('Duplicate room-material records.')
        return self


class TaskProgress(Contract):
    activity_id: str
    floor_id: str | None
    planned_effort_percent: float
    actual_progress_percent: float | None
    latest_observation_date: date | None
    cumulative_actual_cost_pkr: NonNegative | None
    observation_source: str | None


class TwinSnapshot(Contract):
    input_hash: str
    as_of: date
    planned_effort_percent: float
    actual_reported_effort_weighted_percent: float | None
    progress_reporting_coverage_percent: float
    floor_progress: list[dict]
    tasks: list[TaskProgress]
    known_actual_cost_subtotal_pkr: NonNegative
    actual_cost_total_pkr: NonNegative | None
    construction_budget_pkr: Positive | None
    spend_variance_pkr: float | None
    alerts: list[str]
    limitations: list[str]


def build_snapshot(request: TwinInput) -> TwinSnapshot:
    request=TwinInput.model_validate(request.model_dump(mode='json'))
    if request.reviewed_layout_hash!=content_hash(request.layout):
        raise ValueError('Layout changed after baseline review.')
    if request.reviewed_schedule_hash!=content_hash(request.schedule):
        raise ValueError('Schedule changed after baseline review.')
    schedule=request.schedule
    tasks={t.activity.id:t for t in schedule.tasks}
    if not tasks or len(tasks)!=len(schedule.tasks):
        raise ValueError('A nonempty schedule with unique activity IDs is required.')
    floor_ids={f.floor_id for f in request.layout.floors}
    if any(t.activity.floor_id is not None and t.activity.floor_id not in floor_ids for t in schedule.tasks):
        raise ValueError('Schedule refers to an unknown floor.')
    known_rooms={f.floor_id+'/'+r.id for f in request.layout.floors for r in f.rooms}
    if any(r.room_key not in known_rooms for r in request.room_materials):
        raise ValueError('Room material metadata refers to an unknown room.')
    latest={}
    alerts=[]
    for observation in sorted(request.observations,key=lambda o:(o.observed_on,o.id)):
        if observation.activity_id not in tasks:
            raise ValueError('Observation refers to an unknown schedule activity.')
        # Future observations are retained in the ledger but excluded from snapshot.
        if observation.observed_on<=request.as_of:
            previous=latest.get(observation.activity_id)
            if previous and observation.progress_percent<previous.progress_percent:
                alerts.append(observation.activity_id+': reported progress decreased; check rework or correction notes.')
            if previous and previous.cumulative_actual_cost_pkr is not None and observation.cumulative_actual_cost_pkr is not None and observation.cumulative_actual_cost_pkr<previous.cumulative_actual_cost_pkr:
                alerts.append(observation.activity_id+': cumulative cost decreased; review the correction source.')
            latest[observation.activity_id]=observation
    rows=[]
    total_effort=sum(t.activity.duration_days for t in schedule.tasks)
    if total_effort<=0:
        raise ValueError('Schedule effort must be positive.')
    earned=0.;reported_effort=0
    for task in schedule.tasks:
        if (not task.working_dates or len(task.working_dates)!=len(task.daily_earned_days)
            or task.working_dates!=sorted(set(task.working_dates))
            or any(e<=0 or e>1 for e in task.daily_earned_days)
            or abs(sum(task.daily_earned_days)-task.activity.duration_days)>1e-7):
            raise ValueError('Schedule effort records are inconsistent.')
        if (task.start!=task.working_dates[0]
            or task.finish_exclusive!=task.working_dates[-1]+timedelta(days=1)
            or task.release_exclusive!=task.finish_exclusive+timedelta(days=task.activity.curing_days)):
            raise ValueError('Schedule date boundaries are inconsistent.')
        if any(p not in tasks or task.start<tasks[p].release_exclusive for p in task.activity.predecessor_ids):
            raise ValueError('Schedule predecessor order is inconsistent.')
        planned=100*sum(e for d,e in zip(task.working_dates,task.daily_earned_days) if d<=request.as_of)/task.activity.duration_days
        observation=latest.get(task.activity.id)
        if observation:
            reported_effort+=task.activity.duration_days
            earned+=task.activity.duration_days*observation.progress_percent/100
        rows.append(TaskProgress(activity_id=task.activity.id,floor_id=task.activity.floor_id,
            planned_effort_percent=planned,actual_progress_percent=observation.progress_percent if observation else None,
            latest_observation_date=observation.observed_on if observation else None,
            cumulative_actual_cost_pkr=observation.cumulative_actual_cost_pkr if observation else None,
            observation_source=observation.source if observation else None))
    # Partial reports do not silently turn every unreported task into 0% actual.
    actual=100*earned/total_effort if len(latest)==len(tasks) else None
    coverage=100*reported_effort/total_effort
    known=money(sum((dec(o.cumulative_actual_cost_pkr) for o in latest.values()
                    if o.cumulative_actual_cost_pkr is not None),dec(0)))
    complete_spend=(request.spend_coverage_declared_complete and len(latest)==len(tasks)
                    and all(o.cumulative_actual_cost_pkr is not None for o in latest.values()))
    actual_spend=known if complete_spend else None
    variance=None
    if actual_spend is not None and request.construction_budget_pkr is not None:
        variance=money(dec(actual_spend)-dec(request.construction_budget_pkr))
        if variance>0: alerts.append('Cumulative actual spend exceeds the supplied like-for-like construction budget.')
    planned_total=planned_progress(schedule,request.as_of)
    if actual is not None and planned_total-actual>request.lag_alert_percentage_points:
        alerts.append('Reported effort-weighted progress lags planned effort beyond the configured threshold.')
    floors=[]
    for fid in sorted(floor_ids):
        relevant=[t for t in schedule.tasks if t.activity.floor_id==fid]
        weight=sum(t.activity.duration_days for t in relevant)
        all_reported=bool(relevant) and all(t.activity.id in latest for t in relevant)
        actual_floor=(sum(t.activity.duration_days*latest[t.activity.id].progress_percent for t in relevant)/weight) if all_reported else None
        planned_floor=(100*sum(e for t in relevant for d,e in zip(t.working_dates,t.daily_earned_days) if d<=request.as_of)/weight) if weight else None
        floors.append({'floor_id':fid,'planned_effort_percent':planned_floor,
                       'actual_reported_effort_weighted_percent':actual_floor,
                       'reported_tasks':sum(t.activity.id in latest for t in relevant),'total_tasks':len(relevant)})
    limitations=[
        'Progress and cost are user-entered observations, not sensor measurements or certified valuations.',
        'Planned progress is productive-effort weighted. Reported percentages are weighted on the same task effort, not budget or measured physical quantities.',
        'Unreported tasks remain unknown. Whole-project actual progress requires a report for every task; floor progress requires every task on that floor.',
        'Known spend is a subtotal until all task costs are reported and scope coverage is explicitly confirmed. The latest cumulative cost is used once per task.',
        'Spend variance compares cumulative spend with total construction budget, not earned-value cost performance or forecast-at-completion.',
        'Site-wide work without a floor ID contributes to project progress but not floor-only percentages.',
        'Sensor charts are separate simulations and never establish actual progress, costs or operational safety.',
    ]
    return TwinSnapshot(input_hash=content_hash(request),as_of=request.as_of,
        planned_effort_percent=planned_total,actual_reported_effort_weighted_percent=actual,
        progress_reporting_coverage_percent=coverage,floor_progress=floors,tasks=rows,
        known_actual_cost_subtotal_pkr=known,actual_cost_total_pkr=actual_spend,
        construction_budget_pkr=request.construction_budget_pkr,spend_variance_pkr=variance,
        alerts=alerts,limitations=limitations)


def room_map_figure(layout: LayoutAlternative, floor_id: str) -> go.Figure:
    """Each room trace exposes room_key as customdata for Streamlit selection."""
    floor=next((f for f in layout.floors if f.floor_id==floor_id),None)
    if floor is None: raise ValueError('Unknown floor.')
    fig=go.Figure()
    palette=['#E53935','#FB8C00','#43A047','#1E88E5','#8E24AA','#3949AB']
    for i,room in enumerate(floor.rooms):
        key=floor_id+'/'+room.id
        fig.add_trace(go.Scatter(x=[room.x,room.x+room.width,room.x+room.width,room.x,room.x],
            y=[room.y,room.y,room.y+room.length,room.y+room.length,room.y],mode='lines',fill='toself',
            line={'color':palette[i%len(palette)]},name=room.name,customdata=[key]*5,
            meta={'room_key':key},hoveron='fills+points',
            hovertemplate=html.escape(room.name)+f'<br>{room.area_m2:.2f} m² zone<extra></extra>'))
        fig.add_annotation(x=room.x+room.width/2,y=room.y+room.length/2,text=html.escape(room.name),showarrow=False)
    fig.update_layout(title='Room inspection | '+html.escape(floor_id),clickmode='event+select',
        xaxis={'title':'X (m)','scaleanchor':'y','scaleratio':1},yaxis={'title':'Y (m)'},height=500,showlegend=False)
    return fig


def inspect_room(request: TwinInput, room_key: str, *, cost_report: CostReport | None=None,
                 reviewed_cost_hash: str | None=None, mep_report=None,
                 reviewed_mep_hash: str | None=None) -> dict:
    """Return room data; UI must invalidate report links when layout inputs change.

    Hashes bind supplied report snapshots, not proof of their source layout. The
    orchestrator must enforce upstream revision dependencies when attaching them.
    """
    if request.reviewed_layout_hash!=content_hash(request.layout): raise ValueError('Stale room layout.')
    found=[(f,r) for f in request.layout.floors for r in f.rooms if f.floor_id+'/'+r.id==room_key]
    if not found: raise ValueError('Unknown room.')
    floor,room=found[0]
    materials=next((m for m in request.room_materials if m.room_key==room_key),None)
    result={'room_key':room_key,'name':room.name,'kind':room.kind,'zone_area_m2':room.area_m2,
            'dimensions_m':[room.width,room.length],'cost_allocation_pkr':None,'mep':None,
            'materials':materials.materials if materials else [],
            'material_source':materials.source if materials else 'Not supplied',
            'basis':'Centre-line room zone; room cost is an allocation, not measured room BOQ.'}
    if cost_report is not None:
        if reviewed_cost_hash!=content_hash(cost_report): raise ValueError('Stale cost report.')
        result['cost_allocation_pkr']=cost_report.room_allocations_pkr.get(room_key)
    if mep_report is not None:
        from agents.mep_agent import MEPReport
        if not isinstance(mep_report,MEPReport) or reviewed_mep_hash!=content_hash(mep_report):
            raise ValueError('Stale or invalid MEP report.')
        row=next((r for r in mep_report.rooms if r.floor_id==floor.floor_id and r.room_id==room.id),None)
        result['mep']=row.model_dump(mode='json') if row else None
    return result


class SensorSimulation(Contract):
    start: datetime
    hours: int = Field(ge=2,le=8760)
    seed: int = Field(default=42,ge=0)
    temperature_mean_c: float = Field(default=27,ge=-20,le=60)
    temperature_swing_c: NonNegative = 3
    humidity_mean_percent: float = Field(default=50,ge=0,le=100)
    building_base_load_kw: NonNegative = 1
    solar_peak_kw: NonNegative = 3
    # Demonstration inputs only, not local weather or building performance.
    demonstration_label: str = 'SIMULATED DATA — no connected sensors'

    @model_validator(mode='after')
    def require_timezone(self) -> SensorSimulation:
        if self.start.tzinfo is None or self.start.utcoffset() is None:
            raise ValueError('Simulation start requires an explicit timezone.')
        return self


def simulate_sensors(room_keys: list[str], config: SensorSimulation) -> dict:
    config=SensorSimulation.model_validate(config.model_dump(mode='json'))
    if not room_keys or len(set(room_keys))!=len(room_keys) or len(room_keys)*config.hours>100000:
        raise ValueError('Supply unique rooms and keep room-hours within 100000.')
    rng=random.Random(config.seed);rooms=[];building=[]
    for hour in range(config.hours):
        stamp=config.start+timedelta(hours=hour)
        phase=2*math.pi*(stamp.hour-8)/24
        for key in room_keys:
            rooms.append({'timestamp':stamp.isoformat(),'room_key':key,'source':'SIMULATED',
                'temperature_c':round(config.temperature_mean_c+config.temperature_swing_c*math.sin(phase)+rng.uniform(-.4,.4),2),
                'humidity_percent':round(min(100,max(0,config.humidity_mean_percent-5*math.sin(phase)+rng.uniform(-2,2))),2)})
        daylight=max(0,math.sin(math.pi*(stamp.hour-6)/12)) if 6<=stamp.hour<=18 else 0
        building.append({'timestamp':stamp.isoformat(),'source':'SIMULATED',
            'electricity_kw':round(config.building_base_load_kw*(1+.3*math.sin(phase))+rng.uniform(0,.1),3),
            'solar_kw':round(config.solar_peak_kw*daylight,3),
            'tank_level_percent':round(min(100,max(0,70-20*math.sin(phase)+rng.uniform(-2,2))),2)})
    return {'label':'SIMULATED DATA — no connected sensors','rooms':rooms,'building':building,
            'notes':'Synthetic hourly instantaneous values; not actual weather, cumulative energy, water balance or alarm thresholds.'}


def sensor_figures(data: dict, room_key: str) -> dict[str,go.Figure]:
    room=[r for r in data['rooms'] if r['room_key']==room_key]
    if not room: raise ValueError('Room has no simulated series.')
    building=data['building'];figures={}
    for name,rows,columns,ylabel in [
        ('temperature',room,['temperature_c'],'°C'),('humidity',room,['humidity_percent'],'Percent'),
        ('power',building,['electricity_kw','solar_kw'],'kW'),('tank',building,['tank_level_percent'],'Percent')]:
        fig=go.Figure()
        for column in columns:
            fig.add_trace(go.Scatter(x=[r['timestamp'] for r in rows],y=[r[column] for r in rows],name=column,mode='lines'))
        fig.update_layout(title='SIMULATED DATA | '+name,xaxis_title='Timestamp (explicit timezone)',yaxis_title=ylabel,height=300)
        figures[name]=fig
    return figures


def progress_figure(snapshot: TwinSnapshot) -> go.Figure:
    labels=[r['floor_id'] for r in snapshot.floor_progress]
    fig=go.Figure()
    fig.add_trace(go.Bar(name='Planned effort',x=labels,y=[r['planned_effort_percent'] for r in snapshot.floor_progress]))
    fig.add_trace(go.Bar(name='Reported actual (unknown if incomplete)',x=labels,
        y=[r['actual_reported_effort_weighted_percent'] for r in snapshot.floor_progress]))
    fig.update_layout(title='Floor progress | effort-weighted, not measured physical quantities',
        barmode='group',yaxis={'range':[0,100],'title':'Percent'},height=400)
    return fig
