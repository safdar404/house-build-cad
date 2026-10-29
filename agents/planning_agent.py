"""Space-planning specialist with geometry-gated whole-house alternatives."""
from __future__ import annotations

from pydantic import Field, model_validator

from agents.base import AgentError, AgentResult, BaseAgent, InvalidAgentOutput
from config import Credentials, Settings
from schemas import Contract, LayoutAlternative, Requirements, Usage, content_hash
from tools.geometry import AccessLink, GeometryAssessment, PlanningEnvelope, validate_layout


class PlannedAlternative(Contract):
    layout: LayoutAlternative
    access: list[AccessLink]


class PlanningOutput(Contract):
    alternatives: list[PlannedAlternative] = Field(min_length=2,max_length=3)
    design_notes: list[str]

    @model_validator(mode='after')
    def unique_ids(self) -> PlanningOutput:
        ids=[a.layout.id for a in self.alternatives]
        if len(ids)!=len(set(ids)):
            raise ValueError('Alternative IDs must be unique.')
        return self


SYSTEM_PROMPT='''You are the GharBuilder Space Planning Agent. Return two or three
DISTINCT, complete whole-house alternatives. Each includes EVERY requested floor;
whole-house alternatives keep stairs and services coordinated across floors.
All geometry is in metres. Local x runs left to right, y inward from the front
road at y=0. Use the SAME confirmed envelope and origin for all floors. Coordinates
are room zoning boundaries/wall centre lines, not net internal clear dimensions.
Ground elevation is zero, upper elevations sum lower storey heights, basement
elevations are negative. Preserve requested floor IDs and room counts exactly.
IDs for rooms, walls and openings must be unique within a floor. Draw complete
room boundary walls and exterior walls. A shared partition is ONE wall, not two.
Split long walls at junctions if necessary. No collinear overlapping wall segments.
Doors/windows reference existing wall IDs; offset_m runs from wall.start toward
wall.end. Openings fit within wall length and height and do not overlap. Every
door has exactly one AccessLink identifying its two rooms, or room_b=null for an
exterior entrance. The entire door segment must lie on the boundary of BOTH
connected rooms; an exterior door lies on the floor envelope. Every room must be
reachable from a ground-floor exterior entrance through doors and aligned stairs.
Never use windows as access. Doors begin at sill_m=0. Rooms cannot overlap.
For multiple storeys provide exactly one continuous stair zone per floor, same
x/y/width/length. Align lift zones if requested. Stack kitchens and bathrooms
where feasible; disclose compromises. void_area_m2 must be zero because this
schema cannot locate void polygons. Reserve corridors as circulation rooms.
Respect the confirmed setbacks. Do not invent authority compliance, soil tests,
structural safety, daylight certification or precise Qibla bearing. Address guest
privacy, kitchen ventilation and hot-climate orientation in design_notes. Provide
outdoor windows on habitable-room boundaries wherever feasible. Record unresolved
requirements such as service routing, parking manoeuvring, lawn, accessibility,
servant accommodation and all requested_spaces explicitly. Keep rationale concise.
Do not hide errors by deleting requested floors or rooms. If the brief is spatially
infeasible, describe the conflict in rationale; the geometry validator will block
approval and the user must revise requirements. Never silently change the brief.
'''


class PlanningAgent(BaseAgent[PlanningOutput]):
    def __init__(self, *, settings: Settings, credentials: Credentials,
                 usage_log: list[Usage] | None = None, **kwargs: object) -> None:
        super().__init__(settings=settings,credentials=credentials,
                         output_schema=PlanningOutput,
                         system_prompt=SYSTEM_PROMPT+'\nExplanation language: '+settings.language,
                         usage_log=usage_log,**kwargs)

    @staticmethod
    def assess(alternative: PlannedAlternative, requirements: Requirements,
               envelope: PlanningEnvelope) -> GeometryAssessment:
        return validate_layout(alternative.layout,requirements,envelope,alternative.access)

    def generate(self, requirements: Requirements, envelope: PlanningEnvelope,
                 revision_request: str='') -> AgentResult[PlanningOutput]:
        width,depth=envelope.dimensions(requirements)
        def check(output: PlanningOutput) -> PlanningOutput:
            signatures=set()
            for option in output.alternatives:
                assessment=self.assess(option,requirements,envelope)
                if not assessment.valid:
                    # Retry uses safe generic feedback from BaseAgent; errors are not
                    # interpolated into prompts and cannot leak supplied user data.
                    raise InvalidAgentOutput('Alternative failed geometry checks.')
                shape=[{'floor_id':f.floor_id,'rooms':sorted(
                       [(r.kind,r.x,r.y,r.width,r.length) for r in f.rooms])}
                       for f in sorted(option.layout.floors,key=lambda f:f.floor_id)]
                signature=content_hash(shape)
                if signature in signatures:
                    raise InvalidAgentOutput('Alternatives must have distinct room geometry.')
                signatures.add(signature)
                warnings=[i.message for i in assessment.issues if i.severity=='warning']
                option.layout.unresolved_issues=list(dict.fromkeys(option.layout.unresolved_issues+warnings))
            return output
        payload=ContractPayload(requirements=requirements,envelope=envelope,
                                envelope_width_m=width,envelope_depth_m=depth,
                                revision_request=revision_request)
        return self.run([{'role':'user','content':payload.model_dump_json()}],validate=check)

    @classmethod
    def select(cls, option: PlannedAlternative, requirements: Requirements,
               envelope: PlanningEnvelope, *, reviewed_hash: str,
               user_approved: bool=False) -> LayoutAlternative:
        """UI must display geometry warnings before enabling the select button."""
        if not user_approved or reviewed_hash!=content_hash(option):
            raise AgentError('Review the current alternative and approve it before selection.')
        if not cls.assess(option,requirements,envelope).valid:
            raise AgentError('The alternative failed geometry checks and cannot be selected.')
        return option.layout.model_copy(deep=True)


class ContractPayload(Contract):
    requirements: Requirements
    envelope: PlanningEnvelope
    envelope_width_m: float
    envelope_depth_m: float
    revision_request: str
