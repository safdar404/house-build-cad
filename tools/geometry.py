"""Deterministic concept-plan geometry, access graphs and floor alignment.

Room rectangles are zoning cells measured to wall centre lines, not certified
clear internal dimensions. Wall thickness is retained for later CAD/BIM tools.
Local coordinates: x from left boundary, y inward from front road. The envelope
origin places those coordinates on the plot. No arbitrary compass rotation is
applied: the plot's facing direction is retained as orientation metadata.
"""
from __future__ import annotations

from collections import deque
from typing import Literal

from pydantic import Field, model_validator
from shapely.geometry import LineString, box

from schemas import (Contract, FloorPlan, Identifier, LayoutAlternative,
                     NonNegative, Opening, Positive, Requirements, Room, Wall)

TOLERANCE_M = 1e-5


class PlanningEnvelope(Contract):
    """Explicit setbacks: verified rules or user-approved concept assumptions."""
    front_m: NonNegative
    rear_m: NonNegative
    left_m: NonNegative
    right_m: NonNegative
    source: str = Field(min_length=1)
    status: Literal['verified_constraints', 'concept_assumptions']
    confirmed: bool = False
    # Hash of the reviewed compliance report, or accepted assumption description.
    reference_hash: str = Field(min_length=1)

    def dimensions(self, requirements: Requirements) -> tuple[float, float]:
        if not self.confirmed:
            raise ValueError('Review and confirm the proposed planning envelope first.')
        width = requirements.plot.width_m - self.left_m - self.right_m
        depth = requirements.plot.depth_m - self.front_m - self.rear_m
        if min(width, depth) <= 0:
            raise ValueError('Setbacks leave no positive building envelope.')
        return width, depth


class AccessLink(Contract):
    """A door's declared connection, checked against actual opening geometry."""
    floor_id: Identifier
    opening_id: Identifier
    room_a: Identifier
    # null is the outdoors, allowed only for doors on the floor envelope.
    room_b: Identifier | None


class GeometryIssue(Contract):
    severity: Literal['error', 'warning']
    code: str
    floor_id: str | None = None
    element_id: str | None = None
    message: str


class GeometryAssessment(Contract):
    valid: bool
    issues: list[GeometryIssue]
    covered_area_m2: NonNegative
    room_zone_area_m2: NonNegative
    area_basis: str = 'Floor envelope minus explicit voids; room areas are centre-line zoning cells.'


def room_polygon(room: Room):
    return box(room.x, room.y, room.x + room.width, room.y + room.length)


def opening_segment(wall: Wall, opening: Opening) -> LineString:
    """Opening offset is measured along the wall from its start point."""
    dx = (wall.end.x - wall.start.x) / wall.length_m
    dy = (wall.end.y - wall.start.y) / wall.length_m
    a = (wall.start.x + dx*opening.offset_m, wall.start.y + dy*opening.offset_m)
    b = (a[0] + dx*opening.width_m, a[1] + dy*opening.width_m)
    return LineString([a, b])


def _on_boundary(segment: LineString, polygon) -> bool:
    return polygon.boundary.buffer(TOLERANCE_M).covers(segment)


def _same_zone(a: Room, b: Room) -> bool:
    return room_polygon(a).symmetric_difference(room_polygon(b)).area < TOLERANCE_M


def validate_layout(layout: LayoutAlternative, requirements: Requirements,
                    envelope: PlanningEnvelope, access: list[AccessLink]) -> GeometryAssessment:
    """Check a complete alternative; no API calls or filesystem side effects.

    Access uses physical door segments on room boundaries, then tests whole-house
    connectivity from an exterior ground-floor entrance via aligned stairs.
    This does not certify egress travel distances, fire safety, accessibility,
    stair risers/headroom, structural viability or statutory ventilation.
    """
    layout = LayoutAlternative.model_validate(layout.model_dump(mode='json'))
    requirements = Requirements.model_validate(requirements.model_dump(mode='json'))
    envelope = PlanningEnvelope.model_validate(envelope.model_dump(mode='json'))
    access = [AccessLink.model_validate(a.model_dump(mode='json')) for a in access]
    width, depth = envelope.dimensions(requirements)
    issues: list[GeometryIssue] = []
    def add(severity: str, code: str, message: str, floor: str | None = None,
            element: str | None = None) -> None:
        issues.append(GeometryIssue(severity=severity, code=code, message=message,
                                    floor_id=floor, element_id=element))
    floors = {f.floor_id: f for f in layout.floors}
    requests = {f.id: f for f in requirements.floors}
    if set(floors) != set(requests):
        add('error', 'floor_set', 'The alternative must include exactly the requested floors.')
    if not any(r.level == 0 for r in requirements.floors):
        add('error', 'ground_missing', 'A ground level is required to establish external access.')
    graph: dict[tuple[str, str], set[tuple[str, str]]] = {}
    roots: set[tuple[str, str]] = set()
    link_map: dict[tuple[str, str], AccessLink] = {}
    for a in access:
        key = (a.floor_id, a.opening_id)
        if key in link_map:
            add('error', 'duplicate_access', 'A door has multiple access declarations.', *key)
        link_map[key] = a
    used_links: set[tuple[str, str]] = set()
    # Derive storey elevations from requested heights, with ground at zero.
    ordered_requests = sorted(requirements.floors, key=lambda f: f.level)
    expected_elevations: dict[str, float] = {}
    for r in ordered_requests:
        if r.level >= 0:
            expected_elevations[r.id] = sum(x.height_m for x in ordered_requests if 0 <= x.level < r.level)
        else:
            expected_elevations[r.id] = -sum(x.height_m for x in ordered_requests if r.level <= x.level < 0)
    levels = [r.level for r in ordered_requests]
    if any(b-a != 1 for a,b in zip(levels,levels[1:])):
        add('error', 'skipped_storey', 'Requested levels must be consecutive for this concept engine.')
    for floor in layout.floors:
        fid = floor.floor_id
        if floor.width_m > width + TOLERANCE_M or floor.depth_m > depth + TOLERANCE_M:
            add('error', 'envelope', 'Floor exceeds the confirmed buildable envelope.', fid)
        if fid in expected_elevations and abs(floor.elevation_m-expected_elevations[fid]) > TOLERANCE_M:
            add('error', 'elevation', 'Storey elevation disagrees with requested floor heights.', fid)
        # Voids need polygon geometry, absent from FloorPlan v1, so cannot be trusted.
        if floor.void_area_m2 > 0:
            add('error', 'unlocated_void', 'Explicit void polygons are not supported yet; area-only voids cannot be approved.', fid)
        rooms = {r.id: r for r in floor.rooms}
        walls = {w.id: w for w in floor.walls}
        outer = box(0,0,floor.width_m,floor.depth_m)
        boundaries = [room_polygon(r).boundary for r in floor.rooms]
        for room in floor.rooms:
            graph[(fid,room.id)] = set()
        if not floor.walls:
            add('error', 'walls_missing', 'Wall geometry is required for opening and access checks.', fid)
        # Walls must describe the room partitions or the exterior envelope.
        for wall in floor.walls:
            line = LineString([(wall.start.x,wall.start.y),(wall.end.x,wall.end.y)])
            if not any(b.buffer(TOLERANCE_M).covers(line) for b in [outer.boundary,*boundaries]):
                add('error', 'wall_location', 'Wall is not on a room or envelope boundary.', fid,wall.id)
        for i,a in enumerate(floor.walls):
            la=LineString([(a.start.x,a.start.y),(a.end.x,a.end.y)])
            for b in floor.walls[i+1:]:
                lb=LineString([(b.start.x,b.start.y),(b.end.x,b.end.y)])
                if la.intersection(lb).length > TOLERANCE_M:
                    add('error','duplicate_wall','Wall segments overlap; use one shared partition.',fid,a.id)
        from shapely.ops import unary_union
        wall_lines = unary_union([LineString([(w.start.x,w.start.y),(w.end.x,w.end.y)]) for w in floor.walls])
        if not wall_lines.buffer(TOLERANCE_M).covers(outer.boundary):
            add('error','envelope_walls','Exterior envelope has missing wall segments.',fid)
        zoned = unary_union([room_polygon(r) for r in floor.rooms])
        if outer.difference(zoned).area > TOLERANCE_M:
            add('error','unzoned_space','Floor contains unassigned space; model it as circulation or another explicit room zone.',fid)
        for room in floor.rooms:
            if not wall_lines.buffer(TOLERANCE_M).covers(room_polygon(room).boundary):
                add('error','incomplete_walls','Room boundary is missing wall segments.',fid,room.id)
        exterior_windows: set[str] = set()
        for opening in floor.openings:
            segment = opening_segment(walls[opening.wall_id],opening)
            touching = {r.id for r in floor.rooms if _on_boundary(segment,room_polygon(r))}
            outside = _on_boundary(segment,outer)
            if opening.kind == 'window':
                if not touching or not outside:
                    add('warning','window_not_external','Window lacks an established outdoor ventilation path.',fid,opening.id)
                else:
                    exterior_windows.update(touching)
                continue
            key=(fid,opening.id)
            link = link_map.get(key)
            if link is None:
                add('error','door_unlinked','Door requires an access declaration.',fid,opening.id)
                continue
            used_links.add(key)
            declared = {link.room_a} | ({link.room_b} if link.room_b is not None else set())
            if not declared <= set(rooms) or declared != touching or (link.room_b is None and not outside) or (link.room_b == link.room_a):
                add('error','door_connection','Door geometry does not match its declared rooms or exterior.',fid,opening.id)
                continue
            if opening.sill_m > TOLERANCE_M:
                add('error','door_sill','Doors must begin at the concept floor level.',fid,opening.id)
                continue
            if opening.width_m < .8 or opening.height_m < 2:
                add('warning','door_clearance','Door needs professional clearance/accessibility review; concept warning threshold is 0.8 × 2 m.',fid,opening.id)
            if link.room_b is None:
                if fid in requests and requests[fid].level==0:
                    roots.add((fid,link.room_a))
            else:
                a=(fid,link.room_a); b=(fid,link.room_b)
                graph[a].add(b); graph[b].add(a)
        for room in floor.rooms:
            if room.kind in {'bedroom','kitchen','lounge','drawing','dining'} and room.id not in exterior_windows:
                add('warning','ventilation_unresolved','No directly external window established; ventilation requires review.',fid,room.id)
        if fid in requests:
            r=requests[fid]
            for kind,needed in [('bedroom',r.bedrooms),('bathroom',r.bathrooms),('kitchen',r.kitchens)]:
                if sum(x.kind==kind for x in floor.rooms)!=needed:
                    add('error','room_program',f'{kind} count does not match the brief.',fid)
            if requirements.lift and not any(x.kind=='lift' for x in floor.rooms):
                add('error','lift_missing','Requested lift shaft is absent.',fid)
    for key in set(link_map)-used_links:
        add('error','unknown_access','Access declaration does not identify a door on this alternative.',*key)
    ordered = [floors[r.id] for r in ordered_requests if r.id in floors]
    for lower,upper in zip(ordered,ordered[1:]):
        lower_stairs=[r for r in lower.rooms if r.kind=='stairs']
        upper_stairs=[r for r in upper.rooms if r.kind=='stairs']
        if len(lower_stairs)!=1 or len(upper_stairs)!=1 or not _same_zone(lower_stairs[0],upper_stairs[0]):
            add('error','stair_continuity','Each connected storey requires one stair zone with the same footprint.',upper.floor_id)
        else:
            a=(lower.floor_id,lower_stairs[0].id); b=(upper.floor_id,upper_stairs[0].id)
            graph[a].add(b);graph[b].add(a)
        for kind in ('bathroom','kitchen','lift'):
            below=[r for r in lower.rooms if r.kind==kind]
            above=[r for r in upper.rooms if r.kind==kind]
            if any(not any(_same_zone(a,b) for b in below) for a in above):
                add('error' if kind=='lift' else 'warning','vertical_alignment',f'{kind} zones are not vertically stacked.',upper.floor_id)
    reachable=set(roots); queue=deque(roots)
    while queue:
        node=queue.popleft()
        for neighbour in graph[node]-reachable:
            reachable.add(neighbour);queue.append(neighbour)
    if not roots:
        add('error','entrance_missing','No ground-floor exterior entrance is established.')
    for node in set(graph)-reachable:
        add('error','room_inaccessible','Room has no door/stair route from the ground entrance.',*node)
    if envelope.status=='concept_assumptions':
        add('warning','bylaws_pending','Envelope uses accepted concept assumptions, not verified statutory constraints.')
    add('warning','professional_review','Centre-line zoning only. Clear dimensions, wall junctions, stairs, structure, egress, Qibla bearing and ventilation remain subject to detailed review.')
    return GeometryAssessment(valid=not any(i.severity=='error' for i in issues),issues=issues,
           covered_area_m2=sum(f.covered_area_m2 for f in layout.floors),
           room_zone_area_m2=sum(r.area_m2 for f in layout.floors for r in f.rooms))
