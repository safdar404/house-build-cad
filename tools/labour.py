"""Trade-level attendance, wage and indicative contract comparisons.

Calendar-linked crew attendance is costed as a full paid day whenever scheduled
work occurs, including slowed or partial final days. This is distinct from
productive effort and from person-days inferred from quantity/productivity.
"""
from __future__ import annotations

import math
from collections import defaultdict
from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Literal

import plotly.graph_objects as go
from pydantic import Field, model_validator

from config import DATA_DIR, load_json
from schemas import Contract, Evidence, Identifier, NonNegative, Positive, content_hash
from tools.cost import dec, money
from tools.schedule_4d import ScheduleResult

Trade = Literal['mason','labourer','steel_fixer','shuttering_carpenter','electrician',
                'plumber','tile_fixer','painter','welder','wood_worker']


class WageRate(Contract):
    trade: Trade
    daily_wage_pkr: Positive | None
    evidence: Evidence


class LabourRateCatalog(Contract):
    schema_version: Literal['1.0'] = '1.0'
    city: str = Field(min_length=1)
    last_updated: date
    standard_day_hours: Positive = Field(le=24)
    wages: list[WageRate]
    notes: str

    @model_validator(mode='after')
    def unique_trades(self) -> LabourRateCatalog:
        if len({w.trade for w in self.wages})!=len(self.wages):
            raise ValueError('Duplicate wage trade.')
        return self


class TradeCrew(Contract):
    trade: Trade
    workers: int = Field(ge=1,le=1000)


class TaskCrew(Contract):
    activity_id: Identifier
    trades: list[TradeCrew]

    @model_validator(mode='after')
    def unique_trades(self) -> TaskCrew:
        if len({t.trade for t in self.trades})!=len(self.trades):
            raise ValueError('Each trade occurs once in an activity crew.')
        return self


class TradeAvailability(Contract):
    trade: Trade
    available_workers: int = Field(ge=0,le=10000)


class LabourInput(Contract):
    city: str = Field(min_length=1)
    schedule: ScheduleResult
    # Bind the displayed baseline to the crew/wage review, including daily records.
    reviewed_schedule_hash: str
    rates: LabourRateCatalog
    valuation_date: date
    task_crews: list[TaskCrew]
    trade_availability: list[TradeAvailability] = Field(default_factory=list)
    material_cost_pkr: NonNegative | None
    material_cost_source: str = Field(min_length=1)
    overhead_percent: float = Field(ge=0,le=100)
    contractor_margin_percent: float = Field(ge=0,le=100)
    assumptions_accepted: bool = False
    max_wage_age_days: int = Field(default=90,ge=1,le=3650)

    @model_validator(mode='after')
    def unique_assignments(self) -> LabourInput:
        if len({a.activity_id for a in self.task_crews})!=len(self.task_crews):
            raise ValueError('Duplicate activity crew assignment.')
        if len({a.trade for a in self.trade_availability})!=len(self.trade_availability):
            raise ValueError('Duplicate trade capacity.')
        return self


class TradeLabourTotal(Contract):
    trade: Trade
    paid_person_days: int = Field(ge=0)
    productive_person_days: NonNegative
    peak_workers: int = Field(ge=0)
    daily_wage_pkr: Positive | None
    wages_pkr: NonNegative | None
    evidence: Evidence | None


class WorkforceDay(Contract):
    date: date
    total_workers: int = Field(ge=0)
    by_trade: dict[str,int]


class LabourReport(Contract):
    input_hash: str
    city: str
    valuation_date: date
    material_cost_source: str
    schedule_hash: str
    totals: list[TradeLabourTotal]
    daily_workforce: list[WorkforceDay]
    paid_person_days: int = Field(ge=0)
    productive_person_days: NonNegative
    peak_workers: int = Field(ge=0)
    known_wages_subtotal_pkr: NonNegative
    total_wages_pkr: NonNegative | None
    overhead_pkr: NonNegative | None
    labour_only_contract_pkr: NonNegative | None
    material_plus_labour_contract_pkr: NonNegative | None
    warnings: list[str]
    comparison_basis: str = ('Labour-only = wages plus supplied payroll overhead, then contractor margin. '
        'Material-plus-labour = supplied material cost plus wages and overhead, then margin once. '
        'Taxes, overtime, transport/accommodation and scope extras are excluded unless included in supplied amounts.')


class ProductivityInput(Contract):
    trade: Trade
    quantity: NonNegative
    quantity_unit: str = Field(min_length=1)
    output_per_worker_day: Positive
    crew_workers: int = Field(ge=1,le=1000)
    source: str = Field(min_length=1)


class ProductivityEstimate(Contract):
    theoretical_person_days: NonNegative
    productive_crew_days: NonNegative
    rounded_attendance_crew_days: int = Field(ge=0)
    rounded_paid_person_days: int = Field(ge=0)


def productivity_estimate(request: ProductivityInput) -> ProductivityEstimate:
    """Quantity allowance only; not a second amount to add to schedule payroll."""
    request=ProductivityInput.model_validate(request.model_dump(mode='json'))
    person_days=request.quantity/request.output_per_worker_day
    crew_days=person_days/request.crew_workers
    days=math.ceil(crew_days)
    return ProductivityEstimate(theoretical_person_days=person_days,productive_crew_days=crew_days,
        rounded_attendance_crew_days=days,rounded_paid_person_days=days*request.crew_workers)


def load_labour_rates(path: Path | None=None) -> LabourRateCatalog:
    result=load_json(path or DATA_DIR/'labour_rates.json',LabourRateCatalog)
    assert isinstance(result,LabourRateCatalog)
    return result


def estimate_labour(request: LabourInput) -> LabourReport:
    request=LabourInput.model_validate(request.model_dump(mode='json'))
    if not request.assumptions_accepted:
        raise ValueError('Accept crew, wage and paid-day assumptions before estimating labour.')
    schedule=request.schedule
    fingerprint=content_hash(schedule)
    if request.reviewed_schedule_hash!=fingerprint:
        raise ValueError('The schedule changed after crew review.')
    normalize=lambda s:' '.join(s.casefold().split())
    if normalize(request.city)!=normalize(request.rates.city):
        raise ValueError('Labour wage catalog city differs from the project city.')
    if request.rates.last_updated>request.valuation_date:
        raise ValueError('Wage catalog date is later than valuation date.')
    tasks={t.activity.id:t for t in schedule.tasks}
    crews={a.activity_id:a for a in request.task_crews}
    if len(tasks)!=len(schedule.tasks) or set(tasks)!=set(crews):
        raise ValueError('Supply one crew assignment for every unique schedule activity.')
    if not tasks or len(tasks)>1000:
        raise ValueError('Labour estimate requires a nonempty bounded schedule.')
    attendance=defaultdict(int);productive=defaultdict(float);daily=defaultdict(lambda:defaultdict(int))
    for aid,task in tasks.items():
        workers=sum(t.workers for t in crews[aid].trades)
        if workers!=task.activity.crew_size:
            raise ValueError('Trade crew total disagrees with the schedule activity crew size.')
        dates=task.working_dates;earned=task.daily_earned_days
        if not dates or len(dates)!=len(earned) or dates!=sorted(set(dates)):
            raise ValueError('Invalid daily schedule records.')
        if any(e<=0 or e>1 for e in earned) or abs(sum(earned)-task.activity.duration_days)>1e-7:
            raise ValueError('Daily productive effort does not reconcile to task duration.')
        if task.start!=dates[0] or task.finish_exclusive!=dates[-1]+timedelta(days=1):
            raise ValueError('Task dates disagree with its attendance records.')
        if task.release_exclusive!=task.finish_exclusive+timedelta(days=task.activity.curing_days):
            raise ValueError('Task curing dates do not reconcile.')
        if task.start<schedule.start or task.release_exclusive>schedule.finish_exclusive:
            raise ValueError('Task lies outside schedule boundaries.')
        for predecessor in task.activity.predecessor_ids:
            if predecessor not in tasks or task.start<tasks[predecessor].release_exclusive:
                raise ValueError('Schedule dependency order is invalid.')
        for crew in crews[aid].trades:
            attendance[crew.trade]+=crew.workers*len(dates)
            productive[crew.trade]+=crew.workers*sum(earned)
            for day in dates:
                daily[day][crew.trade]+=crew.workers
    rates={r.trade:r for r in request.rates.wages};totals=[];warnings=[
        'Indicative labour estimate only. Wages and productivity assumptions require current local quotations.',
        f'Wages apply to a supplied standard {request.rates.standard_day_hours:g}-hour paid day. Overtime is not inferred.',
        'A full crew-day is paid on each productive attendance date, including slowdown and partial final days. Curing-only days have no attendance.',
        'Crew peaks include parallel tasks. Availability alerts do not resource-level or reschedule the baseline.',
        'Contract comparisons are alternatives, not additional costs to add to an estimate already containing labour.',
        'Quantity/productivity effort estimates are separate planning comparisons and are not added to scheduled payroll.',
    ]
    for trade in sorted(attendance):
        rate=rates.get(trade);wage=rate.daily_wage_pkr if rate else None
        evidence=rate.evidence if rate else None
        if evidence:
            if evidence.effective_date and evidence.effective_date>request.valuation_date:
                raise ValueError('Wage evidence is later than valuation date.')
            if not evidence.verified: warnings.append(trade+': wage evidence is unverified.')
            if evidence.effective_date is None: warnings.append(trade+': wage effective date is missing.')
            elif (request.valuation_date-evidence.effective_date).days>request.max_wage_age_days:
                warnings.append(trade+': wage evidence exceeds the configured age threshold.')
        if wage is None: warnings.append(trade+': wage is missing; payroll and contract totals remain unresolved.')
        peak=max((workers.get(trade,0) for workers in daily.values()),default=0)
        totals.append(TradeLabourTotal(trade=trade,paid_person_days=attendance[trade],
            productive_person_days=productive[trade],peak_workers=peak,daily_wage_pkr=wage,
            wages_pkr=money(dec(wage)*attendance[trade]) if wage is not None else None,evidence=evidence))
    workforce=[WorkforceDay(date=d,total_workers=sum(values.values()),by_trade=dict(values)) for d,values in sorted(daily.items())]
    capacities={a.trade:a.available_workers for a in request.trade_availability}
    for total in totals:
        if total.trade in capacities and total.peak_workers>capacities[total.trade]:
            warnings.append(f'{total.trade}: peak requirement {total.peak_workers} exceeds supplied availability {capacities[total.trade]}; revise crews or resource-level the schedule.')
    if request.material_cost_pkr is None:
        warnings.append('Material cost is missing; the material-plus-labour comparison remains unresolved.')
    known=money(sum((dec(t.wages_pkr) for t in totals if t.wages_pkr is not None),Decimal(0)))
    wages=known if all(t.wages_pkr is not None for t in totals) else None
    overhead=labour_contract=full_contract=None
    if wages is not None:
        overhead=money(dec(wages)*dec(request.overhead_percent)/100)
        factor=1+dec(request.contractor_margin_percent)/100
        labour_contract=money((dec(wages)+dec(overhead))*factor)
        if request.material_cost_pkr is not None:
            full_contract=money((dec(request.material_cost_pkr)+dec(wages)+dec(overhead))*factor)
    return LabourReport(input_hash=content_hash(request),city=request.city,valuation_date=request.valuation_date,
        material_cost_source=request.material_cost_source,schedule_hash=fingerprint,totals=totals,
        daily_workforce=workforce,paid_person_days=sum(attendance.values()),productive_person_days=sum(productive.values()),
        peak_workers=max((d.total_workers for d in workforce),default=0),known_wages_subtotal_pkr=known,
        total_wages_pkr=wages,overhead_pkr=overhead,labour_only_contract_pkr=labour_contract,
        material_plus_labour_contract_pkr=full_contract,warnings=warnings)


def workforce_figure(report: LabourReport) -> go.Figure:
    """Stacked daily trade attendance; hover exposes the worker counts."""
    fig=go.Figure();days=[r.date.isoformat() for r in report.daily_workforce]
    for total in report.totals:
        trade=total.trade
        fig.add_trace(go.Bar(name=trade.replace('_',' ').title(),x=days,
            y=[r.by_trade.get(trade,0) for r in report.daily_workforce],
            hovertemplate='%{x}<br>%{y} workers<extra>%{fullData.name}</extra>'))
    fig.update_layout(title='Planned daily workforce | trade attendance',barmode='stack',
        xaxis_title='Work date',yaxis_title='Workers',template='plotly_white',height=450)
    return fig
