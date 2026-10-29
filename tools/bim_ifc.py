"""IFC4 concept exporter using plan-derived meshes and semantic relationships.

IFCOpenShell is imported on demand so other pages can run without its native
wheel. No substitute text file is returned when IFC export is unavailable.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Literal
from uuid import NAMESPACE_URL, uuid5

import numpy as np
import trimesh
from pydantic import Field, model_validator

from config import DISCLAIMER
from schemas import Contract, Identifier, LayoutAlternative, NonNegative, Requirements, content_hash
from tools.geometry import AccessLink, PlanningEnvelope, validate_layout
from tools.model_3d import ModelOptions, build_model

BIM_LEVELS = {
    '3D': 'Plan-derived concept geometry and spatial hierarchy.',
    '4D': 'Optional phase/start/finish attributes; a linked schedule is required for time simulation.',
    '5D': 'Optional supplied element costs; missing costs are unpriced, not zero.',
    '6D': 'Optional supplied sustainability notes; no certified energy assessment.',
    '7D': 'Optional asset references and maintenance notes; no live sensor connection.',
}


class BIMElementData(Contract):
    element_id: str = Field(min_length=1)
    material: str | None = None
    cost_pkr: NonNegative | None = None
    # General labels: no date arithmetic is performed on these metadata strings.
    phase: str | None = None
    planned_start: str | None = None
    planned_finish: str | None = None
    sustainability_note: str | None = None
    asset_reference: str | None = None
    maintenance_note: str | None = None


class BIMInput(Contract):
    project_id: Identifier
    project_name: str = Field(min_length=1)
    requirements: Requirements
    layout: LayoutAlternative
    envelope: PlanningEnvelope
    access: list[AccessLink]
    options: ModelOptions
    element_data: list[BIMElementData] = Field(default_factory=list)

    @model_validator(mode='after')
    def coherent_options(self) -> BIMInput:
        if not self.options.include_opening_infill:
            raise ValueError('IFC export requires opening infill enabled for semantic doors/windows.')
        ids=[e.element_id for e in self.element_data]
        if len(ids)!=len(set(ids)):
            raise ValueError('Duplicate BIM element metadata.')
        return self


@dataclass(frozen=True)
class IFCExport:
    filename: str
    content: bytes
    input_hash: str
    element_guids: dict[str,str]
    counts: dict[str,int]
    warnings: tuple[str,...]


class IFCExportError(RuntimeError):
    """Safe diagnostic without project contents or native exception bodies."""


def ifc_available() -> bool:
    try:
        import ifcopenshell
    except ImportError:
        return False
    return True


def _connected_parts(vertices: np.ndarray, faces: np.ndarray) -> tuple[list,list]:
    """One IFC representation item per connected shell, without extra packages.

    A single face set containing several touching box shells is ambiguous for
    solid/void processing in some IFC geometry engines. Keep each shell separate.
    """
    parent=list(range(len(vertices)))
    def root(i: int) -> int:
        while parent[i]!=i:
            parent[i]=parent[parent[i]]
            i=parent[i]
        return i
    for face in faces:
        a=root(int(face[0]))
        for v in face[1:]:
            parent[root(int(v))]=a
    groups={}
    for face in faces:
        groups.setdefault(root(int(face[0])),[]).append(face)
    vertex_sets=[];face_sets=[]
    for triangles in groups.values():
        used=sorted({int(v) for face in triangles for v in face})
        mapping={old:new for new,old in enumerate(used)}
        vertex_sets.append(vertices[used].tolist())
        face_sets.append([[mapping[int(v)] for v in face] for face in triangles])
    return vertex_sets,face_sets


def export_ifc(request: BIMInput) -> IFCExport:
    """Build IFC4, reparse and schema-check it before returning UTF-8 bytes.

    Mesh placements are local to storeys; building placement carries the envelope
    offset. Product GUIDs are deterministic within the supplied project ID.
    Walls retain the 3D model's precut meshes and also get semantic opening/filling
    relationships. No structural grid is promoted into a designed frame here.
    """
    try:
        import ifcopenshell
        import ifcopenshell.api
        import ifcopenshell.validate
    except ImportError:
        raise IFCExportError('Install the supported IFCOpenShell wheel to enable IFC4 export.') from None
    request=BIMInput.model_validate(request.model_dump(mode='json'))
    check=validate_layout(request.layout,request.requirements,request.envelope,request.access)
    if not check.valid:
        raise IFCExportError('Layout geometry/access checks failed; IFC export is blocked.')
    building_model=build_model(request.layout,request.requirements,request.envelope,request.options)
    annotations={a.element_id:a for a in request.element_data}
    known_ids={e.id for e in building_model.elements}
    known_ids.update(f'{f.floor_id}/space/{r.id}' for f in request.layout.floors for r in f.rooms)
    if set(annotations)-known_ids:
        raise IFCExportError('BIM metadata references unknown element IDs. Review stale annotations.')
    model=ifcopenshell.file(schema='IFC4')
    api=ifcopenshell.api.run
    def guid(key: str) -> str:
        return ifcopenshell.guid.compress(uuid5(NAMESPACE_URL,'gharbuilder:'+request.project_id+':'+key).hex)
    def create(cls: str,key: str,name: str):
        product=api('root.create_entity',model,ifc_class=cls,name=name)
        product.GlobalId=guid(key)
        return product
    def place(product,x=0.,y=0.,z=0.) -> None:
        matrix=np.eye(4);matrix[:3,3]=[x,y,z]
        api('geometry.edit_object_placement',model,product=product,matrix=matrix,is_si=True)
    def properties(product,name: str,values: dict) -> None:
        pset=api('pset.add_pset',model,product=product,name=name)
        api('pset.edit_pset',model,pset=pset,properties=values)
    project=create('IfcProject','project',request.project_name)
    length=api('unit.add_si_unit',model,unit_type='LENGTHUNIT')
    area=api('unit.add_si_unit',model,unit_type='AREAUNIT')
    volume=api('unit.add_si_unit',model,unit_type='VOLUMEUNIT')
    currency=model.create_entity('IfcMonetaryUnit',Currency='PKR')
    api('unit.assign_unit',model,units=[length,area,volume,currency])
    context=api('context.add_context',model,context_type='Model')
    body=api('context.add_context',model,context_type='Model',context_identifier='Body',
             target_view='MODEL_VIEW',parent=context)
    site=create('IfcSite','site',request.requirements.city+' concept site')
    building=create('IfcBuilding','building',request.project_name)
    api('aggregate.assign_object',model,relating_object=project,products=[site])
    api('aggregate.assign_object',model,relating_object=site,products=[building])
    api('geometry.edit_object_placement',model,product=site,matrix=np.eye(4))
    place(building,request.envelope.left_m,request.envelope.front_m,0)
    properties(project,'GharBuilder_Project',{
        'ProjectId':request.project_id,'LayoutId':request.layout.id,'InputHash':content_hash(request),
        'Status':'PRELIMINARY_CONCEPT','Disclaimer':DISCLAIMER,
        'CoordinateBasis':'Metres; X right, Y inward from front road, Z up; no survey georeferencing',
        'QuantityBasis':'Visual mesh allowances; wall junction overlaps are not a measured BOQ',
        **{key:val for key,val in BIM_LEVELS.items()}})
    floors={f.floor_id:f for f in request.layout.floors}
    req_floors={f.id:f for f in request.requirements.floors}
    storeys={}
    for fid in building_model.floor_ids:
        floor=floors[fid]
        storey=create('IfcBuildingStorey','storey/'+fid,req_floors[fid].name)
        storey.Elevation=floor.elevation_m
        api('aggregate.assign_object',model,relating_object=building,products=[storey])
        place(storey,request.envelope.left_m,request.envelope.front_m,floor.elevation_m)
        storeys[fid]=storey
    material_cache={};style_cache={};products={};guids={}
    def add_mesh(product,mesh,fid,colour='#D5DBE3',opacity=1.):
        # Input mesh is in project/world coordinates. Product placement is the
        # storey's world transform; subtract it from vertices exactly once.
        origin=np.array([request.envelope.left_m,request.envelope.front_m,floors[fid].elevation_m])
        vertices,faces=_connected_parts(mesh.vertices-origin,mesh.faces)
        rep=api('geometry.add_mesh_representation',model,context=body,
                vertices=vertices,faces=faces,unit_scale=1.)
        api('geometry.assign_representation',model,product=product,representation=rep)
        place(product,*origin)
        key=(colour,opacity)
        if key not in style_cache:
            style=api('style.add_style',model,name='Concept '+colour)
            rgb=[int(colour[i:i+2],16)/255 for i in (1,3,5)]
            api('style.add_surface_style',model,style=style,ifc_class='IfcSurfaceStyleRendering',
                attributes={'SurfaceColour':dict(zip(['Red','Green','Blue'],rgb)),
                            'Transparency':1-opacity,'ReflectanceMethod':'NOTDEFINED'})
            style_cache[key]=style
        api('style.assign_representation_styles',model,shape_representation=rep,styles=[style_cache[key]])
    def annotate(product,eid,fid,kind,source,mesh,zone_area=None):
        supplied=annotations.get(eid)
        defaults={'wall':'unspecified wall material','slab':'unspecified concrete',
                  'roof':'unspecified roof structure','parapet':'unspecified parapet',
                  'stairs':'unspecified stair structure','door':'unspecified door',
                  'window':'unspecified glazing/frame','space':'not applicable'}
        mat=supplied.material if supplied and supplied.material else defaults[kind]
        values={'ElementId':eid,'SourceId':source,'FloorId':fid,'Kind':kind,
                'Status':'PRELIMINARY_CONCEPT','MaterialStatus':'Supplied' if supplied and supplied.material else 'Unspecified',
                'Material':mat,'MeshSurfaceAreaM2':float(mesh.area),'MeshVolumeM3':float(mesh.volume),
                'CostStatus':'Supplied' if supplied and supplied.cost_pkr is not None else 'Unpriced',
                'Phase':supplied.phase if supplied and supplied.phase else 'Unassigned'}
        if zone_area is not None:
            values['CentrelineZoneAreaM2']=zone_area
        if supplied:
            if supplied.cost_pkr is not None: values['CostPKR']=supplied.cost_pkr
            for key,field in [('PlannedStart','planned_start'),('PlannedFinish','planned_finish'),
                              ('SustainabilityNote','sustainability_note'),('AssetReference','asset_reference'),
                              ('MaintenanceNote','maintenance_note')]:
                value=getattr(supplied,field)
                if value is not None: values[key]=value
        properties(product,'GharBuilder_Concept',values)
        if kind!='space' and supplied and supplied.material:
            if mat not in material_cache:
                material_cache[mat]=api('material.add_material',model,name=mat)
            api('material.assign_material',model,products=[product],type='IfcMaterial',material=material_cache[mat])
        guids[eid]=product.GlobalId
    classes={'wall':'IfcWall','slab':'IfcSlab','roof':'IfcSlab','parapet':'IfcWall',
             'stairs':'IfcStair','door':'IfcDoor','window':'IfcWindow'}
    for item in building_model.elements:
        product=create(classes[item.kind],item.id,item.id)
        if item.kind=='roof': product.PredefinedType='ROOF'
        elif item.kind=='slab': product.PredefinedType='FLOOR'
        elif item.kind=='parapet': product.PredefinedType='PARAPET'
        elif item.kind=='stairs': product.PredefinedType='STRAIGHT_RUN_STAIR'
        elif item.kind in {'door','window'}:
            opening=next(o for o in floors[item.floor_id].openings if o.id==item.source_id)
            product.OverallWidth=opening.width_m;product.OverallHeight=opening.height_m
        api('spatial.assign_container',model,relating_structure=storeys[item.floor_id],products=[product])
        add_mesh(product,item.mesh,item.floor_id,item.colour,item.opacity)
        annotate(product,item.id,item.floor_id,item.kind,item.source_id,item.mesh)
        products[item.id]=product
    for fid,floor in floors.items():
        for room in floor.rooms:
            eid=f'{fid}/space/{room.id}'
            space=create('IfcSpace',eid,room.name)
            space.PredefinedType='INTERNAL'
            api('aggregate.assign_object',model,relating_object=storeys[fid],products=[space])
            mesh=trimesh.creation.box(extents=[room.width,room.length,req_floors[fid].height_m])
            mesh.apply_translation([request.envelope.left_m+room.x+room.width/2,
                                    request.envelope.front_m+room.y+room.length/2,
                                    floor.elevation_m+req_floors[fid].height_m/2])
            add_mesh(space,mesh,fid,'#93CDB4',.12)
            annotate(space,eid,fid,'space',room.id,mesh,room.area_m2)
        walls={w.id:w for w in floor.walls}
        for opening in floor.openings:
            wall=walls[opening.wall_id]
            host=products.get(f'{fid}/wall/{wall.id}')
            if host is None:
                raise IFCExportError('Opening host wall has no exported solid geometry.')
            oid=f'{fid}/opening/{opening.id}'
            void=create('IfcOpeningElement',oid,oid)
            # Full host-wall depth, distinct from the thin door/glazing infill.
            mesh=trimesh.creation.box(extents=[opening.width_m,wall.thickness_m+.004,opening.height_m])
            mesh.apply_translation([opening.offset_m+opening.width_m/2,0,opening.sill_m+opening.height_m/2])
            theta=np.arctan2(wall.end.y-wall.start.y,wall.end.x-wall.start.x)
            transform=trimesh.transformations.rotation_matrix(theta,[0,0,1])
            transform[:3,3]=[request.envelope.left_m+wall.start.x,
                             request.envelope.front_m+wall.start.y,floor.elevation_m]
            mesh.apply_transform(transform)
            add_mesh(void,mesh,fid)
            api('feature.add_feature',model,feature=void,element=host)
            filling=products[f'{fid}/{opening.kind}/{opening.id}']
            api('feature.add_filling',model,opening=void,element=filling)
            guids[oid]=void.GlobalId
    content=model.to_string()
    reopened=ifcopenshell.file.from_string(content)
    logger=ifcopenshell.validate.json_logger()
    ifcopenshell.validate.validate(reopened,logger,express_rules=False)
    if any(s.get('level')=='error' for s in logger.statements):
        raise IFCExportError('Generated IFC failed schema validation; no export was returned.')
    counts={name:len(reopened.by_type(name)) for name in ['IfcProject','IfcSite','IfcBuilding',
            'IfcBuildingStorey','IfcWall','IfcSlab','IfcDoor','IfcWindow','IfcOpeningElement','IfcStair','IfcSpace']}
    warnings=tuple(dict.fromkeys([*(i.message for i in check.issues if i.severity=='warning'),
        *building_model.warnings,'IFC schema attributes/inverses checked. EXPRESS rules, model-view certification, clash detection and professional design review are separate checks.',
        '4D–7D properties are supplied metadata only. Unassigned/unpriced values do not establish schedule, cost, sustainability or operational completeness.']))
    return IFCExport('GharBuilder_Model.ifc',content.encode('utf-8'),content_hash(request),guids,counts,warnings)
