"""Deterministic indicative estimating from geometry and editable dated rates.

Two alternatives are reconciled, never added: covered-area benchmark and an
itemized BOQ/allowance estimate. Money is rounded with Decimal ROUND_HALF_UP.
Quantity coefficients are explicit user-supplied assumptions, not inferred
material specifications. Missing rates remain unpriced, not zero.
"""
from __future__ import annotations

from datetime import date
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path
from typing import Literal

from pydantic import Field, model_validator

from config import DATA_DIR, load_json
from schemas import (Contract, Evidence, Identifier, LayoutAlternative, NonNegative,
                     Positive, Quality, Requirements, content_hash)
from tools.geometry import AccessLink, PlanningEnvelope, validate_layout

Basis = Literal['covered_sqft','covered_m2','wall_net_face_m2','door_area_m2',
                'window_area_m2','bathrooms','kitchens','dwelling','manual']


def dec(value: float | int | str) -> Decimal:
    return Decimal(str(value))


def money(value: Decimal) -> float:
    return float(value.quantize(Decimal('.01'),rounding=ROUND_HALF_UP))


class MaterialRate(Contract):
    id: Identifier
    description: str = Field(min_length=1)
    unit: str = Field(min_length=1)
    value_pkr: Positive | None
    evidence: Evidence


class CityFactor(Contract):
    city: str = Field(min_length=1)
    multiplier: Positive | None
    evidence: Evidence


class AreaRate(Contract):
    quality: Quality
    grey_pkr_sqft: Positive | None
    finishing_pkr_sqft: NonNegative | None
    labour_fraction: float | None = Field(default=None,ge=0,le=1)
    evidence: Evidence


class RateCatalog(Contract):
    schema_version: Literal['1.0'] = '1.0'
    last_updated: date
    base_city: str = Field(min_length=1)
    rates: list[MaterialRate]
    city_factors: list[CityFactor]
    area_rates: list[AreaRate]
    notes: str

    @model_validator(mode='after')
    def unique_keys(self) -> RateCatalog:
        for keys in ([r.id for r in self.rates],[' '.join(c.city.casefold().split()) for c in self.city_factors],
                     [a.quality for a in self.area_rates]):
            if len(keys)!=len(set(keys)):
                raise ValueError('Duplicate rate, city or quality entry.')
        return self


class QuantityRule(Contract):
    id: Identifier
    description: str = Field(min_length=1)
    rate_id: Identifier
    unit: str = Field(min_length=1)
    basis: Basis
    # Factor converts one basis unit into the unit purchased in this BOQ row.
    quantity_per_basis_unit: NonNegative
    manual_quantity: NonNegative | None = None
    waste_percent: float = Field(default=0,ge=0,le=100)
    phase: Literal['grey','finishing']
    category: Literal['material','labour','composite']
    labour_fraction: float | None = Field(default=None,ge=0,le=1)
    source: str = Field(min_length=1)
    scope_key: Identifier

    @model_validator(mode='after')
    def consistent_rule(self) -> QuantityRule:
        if self.basis=='manual' and self.manual_quantity is None:
            raise ValueError('Manual basis requires an explicit quantity.')
        if self.basis!='manual' and self.manual_quantity is not None:
            raise ValueError('Manual quantity must be absent for geometry bases.')
        if self.category!='composite' and self.labour_fraction is not None:
            raise ValueError('Labour fraction is only used for composite rows.')
        return self


class ExtraCharge(Contract):
    id: Identifier
    label: str = Field(min_length=1)
    rate_id: Identifier
    unit: str = Field(min_length=1)
    quantity: NonNegative
    # Scope extras are explicitly outside both benchmark and BOQ construction totals.
    category: Literal['professional_fee','approval','utility','other']


class Milestone(Contract):
    label: str = Field(min_length=1)
    percent: float = Field(gt=0,le=100)


class CostInput(Contract):
    requirements: Requirements
    layout: LayoutAlternative
    envelope: PlanningEnvelope
    access: list[AccessLink]
    rates: RateCatalog
    valuation_date: date
    quantity_rules: list[QuantityRule]
    extra_charges: list[ExtraCharge] = Field(default_factory=list)
    milestones: list[Milestone]
    selected_basis: Literal['area_benchmark','boq']
    contingency_percent: float = Field(default=10,ge=0,le=50)
    # Explicit scope assumption, not automated Pakistani tax advice.
    tax_percent: float = Field(ge=0,le=100)
    assumptions_accepted: bool = False
    boq_scope_declared_complete: bool = False
    area_rate_scope_accepted: bool = False
    max_rate_age_days: int = Field(default=180,ge=1,le=3650)

    @model_validator(mode='after')
    def no_double_scope(self) -> CostInput:
        for keys in ([r.id for r in self.quantity_rules],[r.scope_key for r in self.quantity_rules],
                     [e.id for e in self.extra_charges]):
            if len(keys)!=len(set(keys)):
                raise ValueError('Duplicate BOQ identity, scope key or extra-charge identity.')
        if not self.milestones or abs(sum(dec(m.percent) for m in self.milestones)-100)>Decimal('.000001'):
            raise ValueError('Milestone percentages must sum to 100.')
        return self


class PricedRow(Contract):
    id: str
    description: str
    floor_id: str | None
    unit: str
    quantity: NonNegative
    rate_id: str
    rate_evidence: Evidence | None
    base_rate_pkr: Positive | None
    effective_rate_pkr: Positive | None
    amount_pkr: NonNegative | None
    category: str
    phase: str
    labour_pkr: NonNegative | None
    material_pkr: NonNegative | None
    formula: str
    source: str


class CostReport(Contract):
    input_hash: str
    rates_hash: str
    covered_area_sqft: Positive
    valuation_date: date
    selected_basis: str
    city_multiplier: Positive | None
    city_factor_evidence: Evidence | None
    area_benchmark_evidence: Evidence | None
    area_benchmark_pkr: NonNegative | None
    boq_known_subtotal_pkr: NonNegative
    boq_total_pkr: NonNegative | None
    comparison_difference_pkr: float | None
    construction_pkr: NonNegative | None
    extras_pkr: NonNegative | None
    contingency_pkr: NonNegative | None
    tax_pkr: NonNegative | None
    grand_total_pkr: NonNegative | None
    cost_per_covered_sqft_pkr: NonNegative | None
    grey_pkr: NonNegative | None
    finishing_pkr: NonNegative | None
    labour_pkr: NonNegative | None
    material_pkr: NonNegative | None
    floor_allocations_pkr: dict[str,float]
    room_allocations_pkr: dict[str,float]
    milestone_amounts_pkr: list[dict]
    rows: list[PricedRow]
    warnings: list[str]
    allocation_basis: str = 'Construction cost allocated by covered floor area; each floor allocated by room-zone area. Extras, tax and contingency are not room costs.'


def load_rates(path: Path | None=None) -> RateCatalog:
    result=load_json(path or DATA_DIR/'rates_pk.json',RateCatalog)
    assert isinstance(result,RateCatalog)
    return result


def _allocate(total: float, weights: list[tuple[str,float]]) -> dict[str,float]:
    """Cent-preserving proportional allocation with a last-row remainder."""
    denominator=sum(dec(w) for _,w in weights)
    if denominator<=0:
        raise ValueError('Allocation weights must have positive sum.')
    remaining=dec(total);out={}
    for i,(key,weight) in enumerate(weights):
        value=remaining if i==len(weights)-1 else min(remaining,dec(money(dec(total)*dec(weight)/denominator)))
        out[key]=money(value);remaining-=value
    return out


def estimate_cost(request: CostInput) -> CostReport:
    request=CostInput.model_validate(request.model_dump(mode='json'))
    if not request.assumptions_accepted:
        raise ValueError('Accept quantity, rate, scope and tax assumptions before estimating.')
    if not validate_layout(request.layout,request.requirements,request.envelope,request.access).valid:
        raise ValueError('Layout geometry must pass before cost estimation.')
    rates={r.id:r for r in request.rates.rates}
    normalize=lambda s:' '.join(s.casefold().split())
    city=next((c for c in request.rates.city_factors if normalize(c.city)==normalize(request.requirements.city)),None)
    factor=city.multiplier if city else None
    warnings=['Indicative estimate only. Quantity coefficients are supplied allowances unless independently measured; no reinforcement or mix design is inferred.',
              'Benchmark and BOQ are alternative methods and are never added together.',
              'Distinct scope keys prevent exact duplicate rows; a quantity surveyor must check overlapping material/composite scope and benchmark exclusions.',
              'Contingency applies to construction only. Tax applies to construction plus extras; this is an explicitly accepted scenario, not tax advice.',
              'Grey/finishing and material/labour splits cover construction only. Extras and contingency are separate.',
              'Room costs are area allocations, not measured room-level BOQs.']
    if factor is None: warnings.append('City multiplier is missing; prices are unresolved, including for the base city. Supply an explicit city factor.')
    if request.rates.last_updated>request.valuation_date:
        raise ValueError('Rate catalog date is later than the valuation date.')
    def evidence_notes(label,evidence):
        if not evidence.verified: warnings.append(label+': rate evidence is unverified.')
        if evidence.effective_date is None: warnings.append(label+': effective date is missing.')
        elif evidence.effective_date>request.valuation_date: raise ValueError('Rate evidence date is later than valuation date.')
        elif (request.valuation_date-evidence.effective_date).days>request.max_rate_age_days:
            warnings.append(label+': rate evidence exceeds the configured age threshold.')
    if city: evidence_notes('City multiplier',city.evidence)
    rows=[]
    def price(key,description,fid,unit,quantity,rate_id,category,phase,labour_fraction,formula,source):
        rate=rates.get(rate_id)
        if rate is not None and rate.unit!=unit:
            raise ValueError('BOQ quantity and rate units disagree; supply an explicit conversion coefficient.')
        if rate: evidence_notes(rate.id,rate.evidence)
        base=rate.value_pkr if rate else None
        effective=None if base is None or factor is None else dec(base)*dec(factor)
        amount=0. if quantity==0 else None if effective is None else money(dec(quantity)*effective)
        share=1 if category=='labour' else 0 if category=='material' else labour_fraction
        labour=None if amount is None or share is None else money(dec(amount)*dec(share))
        material=None if labour is None else money(dec(amount)-dec(labour))
        if amount is None: warnings.append(key+': item is unpriced.')
        rows.append(PricedRow(id=key,description=description,floor_id=fid,unit=unit,quantity=quantity,
            rate_id=rate_id,rate_evidence=rate.evidence if rate else None,
            base_rate_pkr=base,effective_rate_pkr=float(effective) if effective is not None else None,
            amount_pkr=amount,category=category,phase=phase,labour_pkr=labour,material_pkr=material,
            formula=formula,source=source))
    for rule in request.quantity_rules:
        if request.requirements.quality==Quality.GREY and rule.phase=='finishing': continue
        # Manual and dwelling quantities occur once, never once per floor.
        groups=[None] if rule.basis in {'manual','dwelling'} else request.layout.floors
        for floor in groups:
            if floor is None: basis=rule.manual_quantity if rule.basis=='manual' else 1.
            elif rule.basis=='covered_sqft': basis=floor.covered_area_m2/(.3048**2)
            elif rule.basis=='covered_m2': basis=floor.covered_area_m2
            elif rule.basis=='wall_net_face_m2':
                # One wall face; double this with a coefficient for both faces.
                basis=sum(w.length_m*w.height_m for w in floor.walls)-sum(o.width_m*o.height_m for o in floor.openings)
            elif rule.basis in {'door_area_m2','window_area_m2'}:
                kind='door' if rule.basis=='door_area_m2' else 'window'
                basis=sum(o.width_m*o.height_m for o in floor.openings if o.kind==kind)
            elif rule.basis in {'bathrooms','kitchens'}:
                kind='bathroom' if rule.basis=='bathrooms' else 'kitchen'
                basis=sum(r.kind==kind for r in floor.rooms)
            else: raise ValueError('Unsupported quantity basis.')
            quantity=float(dec(basis)*dec(rule.quantity_per_basis_unit)*(1+dec(rule.waste_percent)/100))
            fid=floor.floor_id if floor else None
            price(rule.id+('/'+fid if fid else ''),rule.description,fid,rule.unit,quantity,rule.rate_id,
                  rule.category,rule.phase,rule.labour_fraction,
                  f'{basis:g} {rule.basis} × {rule.quantity_per_basis_unit:g} × (1 + {rule.waste_percent:g}/100)',rule.source)
    construction_rows=list(rows)
    for extra in request.extra_charges:
        price('extra/'+extra.id,extra.label,None,extra.unit,extra.quantity,extra.rate_id,extra.category,'extra',None,
              f'{extra.quantity:g} × configured unit rate','Explicit extra outside both construction bases')
    extras_rows=rows[len(construction_rows):]
    extras=None if any(r.amount_pkr is None for r in extras_rows) else money(sum((dec(r.amount_pkr) for r in extras_rows),Decimal(0)))
    known=money(sum((dec(r.amount_pkr) for r in construction_rows if r.amount_pkr is not None),Decimal(0)))
    complete=bool(construction_rows) and request.boq_scope_declared_complete and all(r.amount_pkr is not None for r in construction_rows)
    boq=known if complete else None
    if not complete: warnings.append('BOQ total is unresolved: scope is incomplete, empty or contains unpriced rows. Known subtotal is not a project total.')
    area=sum(f.covered_area_m2 for f in request.layout.floors)/(.3048**2)
    benchmark=grey=finishing=labour=material=None
    selected=next((a for a in request.rates.area_rates if a.quality==request.requirements.quality),None)
    if selected:
        evidence_notes('Area benchmark',selected.evidence)
        finish_rate=0 if request.requirements.quality==Quality.GREY else selected.finishing_pkr_sqft
        if selected.grey_pkr_sqft is not None and finish_rate is not None and factor is not None:
            grey=money(dec(area)*dec(selected.grey_pkr_sqft)*dec(factor))
            finishing=money(dec(area)*dec(finish_rate)*dec(factor))
            benchmark=money(dec(grey)+dec(finishing))
    if request.selected_basis=='area_benchmark':
        construction=benchmark if request.area_rate_scope_accepted else None
        if not request.area_rate_scope_accepted: warnings.append('Benchmark scope has not been accepted; no project total is returned.')
        if construction is not None and selected.labour_fraction is not None:
            labour=money(dec(construction)*dec(selected.labour_fraction));material=money(dec(construction)-dec(labour))
    else:
        construction=boq
        grey=money(sum((dec(r.amount_pkr) for r in construction_rows if r.phase=='grey'),Decimal(0))) if complete else None
        finishing=money(sum((dec(r.amount_pkr) for r in construction_rows if r.phase=='finishing'),Decimal(0))) if complete else None
        if complete and all(r.labour_pkr is not None for r in construction_rows):
            labour=money(sum((dec(r.labour_pkr) for r in construction_rows),Decimal(0)))
            material=money(dec(boq)-dec(labour))
    contingency=tax=total=None
    if construction is not None and extras is not None:
        contingency=money(dec(construction)*dec(request.contingency_percent)/100)
        tax=money((dec(construction)+dec(extras))*dec(request.tax_percent)/100)
        total=money(dec(construction)+dec(extras)+dec(contingency)+dec(tax))
    floor_alloc={};room_alloc={};payments=[]
    if construction is not None:
        floor_alloc=_allocate(construction,[(f.floor_id,f.covered_area_m2) for f in request.layout.floors])
        for f in request.layout.floors:
            room_alloc.update(_allocate(floor_alloc[f.floor_id],[(f.floor_id+'/'+r.id,r.area_m2) for r in f.rooms]))
    if total is not None:
        amounts=_allocate(total,[(str(i),m.percent) for i,m in enumerate(request.milestones)])
        payments=[{'label':m.label,'percent':m.percent,'amount_pkr':amounts[str(i)]} for i,m in enumerate(request.milestones)]
    return CostReport(input_hash=content_hash(request),rates_hash=content_hash(request.rates),covered_area_sqft=area,
        valuation_date=request.valuation_date,selected_basis=request.selected_basis,
        city_multiplier=factor,city_factor_evidence=city.evidence if city else None,
        area_benchmark_evidence=selected.evidence if selected else None,area_benchmark_pkr=benchmark,
        boq_known_subtotal_pkr=known,boq_total_pkr=boq,
        comparison_difference_pkr=money(dec(boq)-dec(benchmark)) if boq is not None and benchmark is not None else None,
        construction_pkr=construction,extras_pkr=extras,contingency_pkr=contingency,tax_pkr=tax,grand_total_pkr=total,
        cost_per_covered_sqft_pkr=money(dec(construction)/dec(area)) if construction is not None else None,
        grey_pkr=grey,finishing_pkr=finishing,labour_pkr=labour,material_pkr=material,
        floor_allocations_pkr=floor_alloc,room_allocations_pkr=room_alloc,milestone_amounts_pkr=payments,
        rows=rows,warnings=list(dict.fromkeys(warnings)))
