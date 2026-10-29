"""Validated contracts shared by GharBuilder agents and deterministic tools.

Geometry is in metres; money is PKR. Model dumps never contain API keys.
Further specialist contracts can compose these public models.
"""
from __future__ import annotations

import hashlib
import json
from datetime import date
from enum import StrEnum
from typing import Annotated, Literal
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, model_validator

Positive = Annotated[float, Field(gt=0, allow_inf_nan=False)]
NonNegative = Annotated[float, Field(ge=0, allow_inf_nan=False)]
Identifier = Annotated[str, Field(min_length=1, max_length=100, pattern=r'^[A-Za-z0-9_-]+$')]


class Contract(BaseModel):
    """Reject unknown keys and nonfinite numbers; validate subsequent assignments."""
    model_config = ConfigDict(extra='forbid', validate_assignment=True, allow_inf_nan=False)


class Quality(StrEnum):
    GREY = 'Grey only'
    ECONOMY = 'Economy'
    STANDARD = 'Standard'
    PREMIUM = 'Premium'
    LUXURY = 'Luxury'


class Stage(StrEnum):
    REQUIREMENTS = 'requirements'
    COMPLIANCE = 'compliance'
    PLANNING = 'planning'
    CAD = 'cad'
    MODEL = 'model'
    STRUCTURAL = 'structural'
    MEP = 'mep'
    BIM = 'bim'
    SCHEDULE = 'schedule'
    COST = 'cost'
    LABOUR = 'labour'
    TWIN = 'twin'
    REPORT = 'report'


class Evidence(Contract):
    source: str = Field(min_length=1)
    effective_date: date | None = None
    source_url: str | None = None
    verified: bool = False
    verified_by: str | None = None
    notes: str = ''

    @model_validator(mode='after')
    def require_verification_record(self) -> Evidence:
        if self.verified and (not self.effective_date or not self.verified_by):
            raise ValueError('Verified evidence requires effective_date and verified_by.')
        return self


class Assumption(Contract):
    id: Identifier
    description: str = Field(min_length=1)
    status: Literal['proposed', 'accepted', 'rejected'] = 'proposed'
    source: str = 'user confirmation required'


class Plot(Contract):
    width_m: Positive
    depth_m: Positive
    facing: Literal['N', 'NE', 'E', 'SE', 'S', 'SW', 'W', 'NW']
    corner: bool = False
    marla_sqft: Literal[225.0, 272.25] = 225.0
    declared_area_sqft: Positive | None = None

    @property
    def area_m2(self) -> float:
        return self.width_m * self.depth_m

    @property
    def area_sqft(self) -> float:
        return self.area_m2 / (0.3048 ** 2)

    @model_validator(mode='after')
    def check_declared_area(self) -> Plot:
        if self.declared_area_sqft is not None:
            if abs(self.area_sqft - self.declared_area_sqft) > max(1, self.area_sqft * .01):
                raise ValueError('Declared area disagrees with dimensions by more than 1%.')
        return self


class FloorRequest(Contract):
    id: Identifier
    name: str = Field(min_length=1)
    level: int = Field(ge=-3, le=20)
    height_m: Positive = 3.05
    bedrooms: int = Field(ge=0, le=30)
    bathrooms: int = Field(ge=0, le=30)
    kitchens: int = Field(ge=0, le=10)
    requested_spaces: list[str] = Field(default_factory=list)


class Requirements(Contract):
    city: str = Field(min_length=1)
    authority: str = Field(min_length=1)
    plot: Plot
    floors: list[FloorRequest] = Field(min_length=1)
    family_size: int = Field(gt=0, le=100)
    car_spaces: int = Field(ge=0, le=20)
    accessibility_needs: list[str] = Field(default_factory=list)
    stairs_position: str = Field(min_length=1)
    lift: bool
    drawing_dining: str = Field(min_length=1)
    tv_lounge: bool
    servant_quarter: bool
    lawn: bool
    budget_pkr: Positive
    quality: Quality
    style: str = Field(min_length=1)
    green_features: list[str] = Field(default_factory=list)
    start_date: date
    soil_description: str | None = None
    assumptions: list[Assumption] = Field(default_factory=list)

    @model_validator(mode='after')
    def unique_floors(self) -> Requirements:
        if len({f.id for f in self.floors}) != len(self.floors):
            raise ValueError('Floor IDs must be unique.')
        if len({f.level for f in self.floors}) != len(self.floors):
            raise ValueError('Floor levels must be unique.')
        return self


class InterviewTurn(Contract):
    """An incomplete brief remains a draft, never a construction-ready brief."""
    message: str = Field(min_length=1)
    draft_json: str = '{}'
    missing_fields: list[str] = Field(default_factory=list)
    confirmed_requirements: Requirements | None = None


class Point(Contract):
    x: float
    y: float


class Room(Contract):
    id: Identifier
    name: str = Field(min_length=1)
    kind: Literal['bedroom', 'bathroom', 'kitchen', 'lounge', 'drawing', 'dining',
                  'stairs', 'lift', 'garage', 'circulation', 'store', 'utility', 'other']
    x: NonNegative
    y: NonNegative
    width: Positive
    length: Positive

    @property
    def area_m2(self) -> float:
        return self.width * self.length


class Wall(Contract):
    id: Identifier
    start: Point
    end: Point
    thickness_m: Positive = .23
    height_m: Positive = 3.05
    material: str = 'brick'

    @property
    def length_m(self) -> float:
        return ((self.end.x-self.start.x)**2 + (self.end.y-self.start.y)**2)**.5

    @model_validator(mode='after')
    def nonzero(self) -> Wall:
        if self.length_m < .01:
            raise ValueError('Wall length must be at least 0.01 m.')
        return self


class Opening(Contract):
    id: Identifier
    wall_id: Identifier
    kind: Literal['door', 'window']
    offset_m: NonNegative
    width_m: Positive
    height_m: Positive
    sill_m: NonNegative = 0


class FloorPlan(Contract):
    floor_id: Identifier
    elevation_m: float
    width_m: Positive
    depth_m: Positive
    rooms: list[Room] = Field(min_length=1)
    walls: list[Wall] = Field(default_factory=list)
    openings: list[Opening] = Field(default_factory=list)
    void_area_m2: NonNegative = 0
    notes: list[str] = Field(default_factory=list)

    @property
    def covered_area_m2(self) -> float:
        """Rectangular floor envelope less declared open voids; not plot area."""
        return self.width_m * self.depth_m - self.void_area_m2

    @model_validator(mode='after')
    def check_geometry(self) -> FloorPlan:
        if self.void_area_m2 >= self.width_m * self.depth_m:
            raise ValueError('Voids must be smaller than the floor envelope.')
        ids = [r.id for r in self.rooms] + [w.id for w in self.walls] + [o.id for o in self.openings]
        if len(ids) != len(set(ids)):
            raise ValueError('Element IDs must be unique within each floor.')
        eps = 1e-6
        for r in self.rooms:
            if r.x+r.width > self.width_m+eps or r.y+r.length > self.depth_m+eps:
                raise ValueError(f'Room {r.id} exceeds floor bounds.')
        for i, a in enumerate(self.rooms):
            for b in self.rooms[i+1:]:
                overlap_x = min(a.x+a.width, b.x+b.width)-max(a.x, b.x)
                overlap_y = min(a.y+a.length, b.y+b.length)-max(a.y, b.y)
                if overlap_x > eps and overlap_y > eps:
                    raise ValueError(f'Rooms {a.id} and {b.id} overlap.')
        wall_map = {w.id: w for w in self.walls}
        for w in self.walls:
            for pt in (w.start, w.end):
                if not (-eps <= pt.x <= self.width_m+eps and -eps <= pt.y <= self.depth_m+eps):
                    raise ValueError(f'Wall {w.id} exceeds floor bounds.')
        for o in self.openings:
            w = wall_map.get(o.wall_id)
            if w is None:
                raise ValueError(f'Opening {o.id} references an unknown wall.')
            if o.offset_m+o.width_m > w.length_m+eps or o.sill_m+o.height_m > w.height_m+eps:
                raise ValueError(f'Opening {o.id} exceeds its wall.')
        for i, a in enumerate(self.openings):
            for b in self.openings[i+1:]:
                if a.wall_id == b.wall_id:
                    dx = min(a.offset_m+a.width_m,b.offset_m+b.width_m)-max(a.offset_m,b.offset_m)
                    dz = min(a.sill_m+a.height_m,b.sill_m+b.height_m)-max(a.sill_m,b.sill_m)
                    if dx > eps and dz > eps:
                        raise ValueError(f'Openings {a.id} and {b.id} overlap.')
        return self


class LayoutAlternative(Contract):
    id: Identifier
    title: str
    floors: list[FloorPlan] = Field(min_length=1)
    rationale: str
    unresolved_issues: list[str] = Field(default_factory=list)

    @model_validator(mode='after')
    def unique_floor_ids(self) -> LayoutAlternative:
        if len({f.floor_id for f in self.floors}) != len(self.floors):
            raise ValueError('Duplicate floor in layout.')
        return self


class ComplianceIssue(Contract):
    rule_id: str
    status: Literal['pass', 'fail', 'undetermined']
    explanation: str
    suggested_fix: str | None = None
    evidence: Evidence


class Rate(Contract):
    id: Identifier
    description: str
    unit: str = Field(min_length=1)
    value_pkr: Positive | None = None
    evidence: Evidence


class BOQItem(Contract):
    id: Identifier
    description: str
    floor_id: Identifier | None = None
    category: Literal['material', 'labour', 'composite', 'fee', 'utility']
    unit: str
    quantity: NonNegative
    rate_id: Identifier
    rate_pkr: Positive | None = None
    formula: str = Field(min_length=1)

    @property
    def amount_pkr(self) -> float | None:
        return None if self.rate_pkr is None else round(self.quantity*self.rate_pkr, 2)


class Activity(Contract):
    id: Identifier
    name: str
    duration_days: int = Field(gt=0)
    predecessor_ids: list[Identifier] = Field(default_factory=list)
    element_ids: list[Identifier] = Field(default_factory=list)
    floor_id: Identifier | None = None
    curing_days: int = Field(default=0, ge=0)
    crew_size: int = Field(default=0, ge=0)


class StageRecord(Contract):
    status: Literal['pending', 'running', 'review', 'approved', 'failed', 'stale'] = 'pending'
    input_hash: str | None = None
    output_hash: str | None = None
    revision: int = Field(default=0, ge=0)
    message: str = ''


class Usage(Contract):
    model: str
    input_tokens: int = Field(default=0, ge=0)
    cached_input_tokens: int = Field(default=0, ge=0)
    output_tokens: int = Field(default=0, ge=0)
    estimated_usd: NonNegative | None = None

    @model_validator(mode='after')
    def valid_cache(self) -> Usage:
        if self.cached_input_tokens > self.input_tokens:
            raise ValueError('Cached tokens cannot exceed input tokens.')
        return self


class Project(Contract):
    schema_version: Literal['1.0'] = '1.0'
    id: Identifier = Field(default_factory=lambda: uuid4().hex)
    name: str = 'My GharBuilder project'
    requirements: Requirements | None = None
    alternatives: list[LayoutAlternative] = Field(default_factory=list)
    selected_layout_id: Identifier | None = None
    stages: dict[Stage, StageRecord] = Field(default_factory=lambda: {s: StageRecord() for s in Stage})
    usage: list[Usage] = Field(default_factory=list)

    @model_validator(mode='after')
    def selection_exists(self) -> Project:
        ids = [a.id for a in self.alternatives]
        if len(ids) != len(set(ids)):
            raise ValueError('Layout IDs must be unique.')
        if self.selected_layout_id is not None and self.selected_layout_id not in ids:
            raise ValueError('Selected layout is not available.')
        return self


def content_hash(value: Contract | dict | list) -> str:
    """Stable digest for validated, public project data and revision checks."""
    data = value.model_dump(mode='json') if isinstance(value, Contract) else value
    encoded = json.dumps(data, sort_keys=True, ensure_ascii=False, separators=(',', ':'), allow_nan=False)
    return hashlib.sha256(encoded.encode('utf-8')).hexdigest()
