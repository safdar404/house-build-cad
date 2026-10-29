"""Plan-derived concept meshes, interactive Plotly view and mesh exports.

Box decomposition cuts openings without optional Boolean/triangulation engines.
Each element retains a stable ID for later IFC/scheduling links. The mesh is a
visual concept: intersecting wall joints are not a fabrication-ready solid union.
"""
from __future__ import annotations

import html
import io
import json
import math
import zipfile
from dataclasses import dataclass
from typing import Literal

import numpy as np
import plotly.graph_objects as go
import trimesh
from pydantic import Field

from config import DISCLAIMER
from schemas import Contract, LayoutAlternative, NonNegative, Positive, Requirements
from tools.geometry import PlanningEnvelope


class ModelOptions(Contract):
    wall_colour: str = Field(default='#E8DBCC',pattern=r'^#[0-9a-fA-F]{6}$')
    slab_colour: str = Field(default='#A8B5C4',pattern=r'^#[0-9a-fA-F]{6}$')
    door_colour: str = Field(default='#986641',pattern=r'^#[0-9a-fA-F]{6}$')
    window_colour: str = Field(default='#65C7EB',pattern=r'^#[0-9a-fA-F]{6}$')
    stair_colour: str = Field(default='#B4A7CF',pattern=r'^#[0-9a-fA-F]{6}$')
    slab_thickness_m: Positive = .15
    parapet_height_m: NonNegative = .9
    parapet_thickness_m: Positive = .115
    include_opening_infill: bool = True
    include_roof: bool = True
    # Explicit UI acceptance; values are unverified modelling assumptions.
    assumptions_accepted: bool = False


@dataclass
class MeshElement:
    id: str
    floor_id: str
    source_id: str
    kind: str
    mesh: trimesh.Trimesh
    colour: str
    opacity: float = 1


@dataclass
class BuildingModel:
    layout_id: str
    elements: list[MeshElement]
    floor_ids: tuple[str,...]
    warnings: tuple[str,...]


def _rgba(colour: str, opacity: float=1) -> list[int]:
    return [int(colour[i:i+2],16) for i in (1,3,5)]+[round(opacity*255)]


def _box(x: float,y: float,z: float,w: float,d: float,h: float) -> trimesh.Trimesh:
    if min(w,d,h)<=0:
        raise ValueError('Mesh dimensions must be positive.')
    mesh=trimesh.creation.box(extents=[w,d,h])
    mesh.apply_translation([x+w/2,y+d/2,z+h/2])
    return mesh


def _combine(parts: list[trimesh.Trimesh]) -> trimesh.Trimesh:
    if not parts:
        raise ValueError('An element has no solid geometry.')
    return trimesh.util.concatenate(parts)


def _colour(mesh: trimesh.Trimesh, colour: str, opacity: float) -> None:
    mesh.visual=trimesh.visual.TextureVisuals(material=trimesh.visual.material.PBRMaterial(
        baseColorFactor=_rgba(colour,opacity),metallicFactor=0,roughnessFactor=.8,
        alphaMode='BLEND' if opacity<1 else 'OPAQUE',doubleSided=True))


def _slab_parts(width: float,depth: float,z: float,thickness: float,
                holes: list[tuple[float,float,float,float]]) -> list[trimesh.Trimesh]:
    """Rectangle grid decomposition with exact rectangular stair/lift cutouts."""
    xs=sorted({0.,width,*[v for x,y,w,d in holes for v in (x,x+w)]})
    ys=sorted({0.,depth,*[v for x,y,w,d in holes for v in (y,y+d)]})
    parts=[]
    for a,b in zip(xs,xs[1:]):
        for c,d in zip(ys,ys[1:]):
            if b-a<1e-8 or d-c<1e-8:
                continue
            mx=(a+b)/2;my=(c+d)/2
            if any(x<mx<x+w and y<my<y+h for x,y,w,h in holes):
                continue
            parts.append(_box(a,c,z,b-a,d-c,thickness))
    return parts


def build_model(layout: LayoutAlternative, requirements: Requirements,
                envelope: PlanningEnvelope, options: ModelOptions) -> BuildingModel:
    """Caller must validate layout/access before invoking this geometry tool.

    Model coordinates are x-right, y-inward, z-up, in metres, translated to plot
    envelope origin. GLB exports rotate z-up to glTF y-up; OBJ remains z-up.
    """
    options=ModelOptions.model_validate(options.model_dump(mode='json'))
    if not options.assumptions_accepted:
        raise ValueError('Accept the slab/parapet/stair modelling assumptions before building.')
    envelope.dimensions(requirements)
    requests={r.id:r for r in requirements.floors}
    ordered=sorted(layout.floors,key=lambda f:requests[f.floor_id].level)
    elements=[]
    warnings=[
        'Visual concept only. Slab/parapet sizes and stair risers/treads are unverified modelling assumptions.',
        'Wall strips may intersect at junctions; meshes are not Boolean-unioned and must not be used for measured BOQ volumes.',
        'Straight stair blocks omit landings, handrails and headroom checks; lift shafts have no equipment.',
        'Local coordinates are not surveyed/georeferenced. Structure, roof drainage and detailed facade design are excluded.',
        DISCLAIMER,
    ]
    def add(fid: str,source: str,kind: str,parts: list[trimesh.Trimesh],colour: str,
            opacity: float=1) -> None:
        mesh=_combine(parts)
        if not np.isfinite(mesh.vertices).all() or not mesh.is_watertight:
            raise ValueError('Generated element failed finite/watertight component checks.')
        mesh.apply_translation([envelope.left_m,envelope.front_m,0])
        _colour(mesh,colour,opacity)
        eid=f'{fid}/{kind}/{source}'
        mesh.metadata.update({'element_id':eid,'floor_id':fid,'source_id':source,'kind':kind})
        elements.append(MeshElement(eid,fid,source,kind,mesh,colour,opacity))
    for index,floor in enumerate(ordered):
        fid=floor.floor_id;z=floor.elevation_m;storey_height=requests[fid].height_m
        if options.slab_thickness_m>=storey_height:
            raise ValueError('Slab thickness must be smaller than storey height.')
        holes=[(r.x,r.y,r.width,r.length) for r in floor.rooms if r.kind in {'stairs','lift'}] if index>0 else []
        add(fid,'floor','slab',_slab_parts(floor.width_m,floor.depth_m,z-options.slab_thickness_m,
                                        options.slab_thickness_m,holes),options.slab_colour)
        wall_map={w.id:w for w in floor.walls}
        for wall in floor.walls:
            if wall.height_m>storey_height+1e-6:
                raise ValueError('Wall height exceeds the requested storey height.')
            openings=[o for o in floor.openings if o.wall_id==wall.id]
            xs=sorted({0.,wall.length_m,*[v for o in openings for v in (o.offset_m,o.offset_m+o.width_m)]})
            zs=sorted({0.,wall.height_m,*[v for o in openings for v in (o.sill_m,o.sill_m+o.height_m)]})
            parts=[]
            for a,b in zip(xs,xs[1:]):
                for c,d in zip(zs,zs[1:]):
                    if min(b-a,d-c)<1e-8:
                        continue
                    mx=(a+b)/2;mz=(c+d)/2
                    if any(o.offset_m<mx<o.offset_m+o.width_m and o.sill_m<mz<o.sill_m+o.height_m for o in openings):
                        continue
                    parts.append(_box(a,-wall.thickness_m/2,c,b-a,wall.thickness_m,d-c))
            if parts:
                mesh=_combine(parts)
                transform=trimesh.transformations.rotation_matrix(
                    math.atan2(wall.end.y-wall.start.y,wall.end.x-wall.start.x),[0,0,1])
                transform[:3,3]=[wall.start.x,wall.start.y,z]
                mesh.apply_transform(transform)
                add(fid,wall.id,'wall',[mesh],options.wall_colour)
        if options.include_opening_infill:
            for o in floor.openings:
                wall=wall_map[o.wall_id]
                mesh=_box(o.offset_m,-.02,o.sill_m,o.width_m,.04,o.height_m)
                transform=trimesh.transformations.rotation_matrix(
                    math.atan2(wall.end.y-wall.start.y,wall.end.x-wall.start.x),[0,0,1])
                transform[:3,3]=[wall.start.x,wall.start.y,z]
                mesh.apply_transform(transform)
                add(fid,o.id,o.kind,[mesh],options.window_colour if o.kind=='window' else options.door_colour,
                    .35 if o.kind=='window' else 1)
        if index<len(ordered)-1:
            next_floor=ordered[index+1]
            rise=next_floor.elevation_m-z
            for room in (r for r in floor.rooms if r.kind=='stairs'):
                count=math.ceil(rise/.18);run=room.length/count
                if run<.25:
                    warnings.append(f'{fid}/{room.id}: schematic tread depth {run:.3f} m is below the 0.25 m concept warning threshold; redesign stair geometry.')
                # Non-overlapping step blocks, not a structural stair flight/slab.
                steps=[_box(room.x,room.y+i*run,z,room.width,run,rise*(i+1)/count)
                       for i in range(count)]
                add(fid,room.id,'stairs',steps,options.stair_colour)
    if options.include_roof:
        top=ordered[-1];fid=top.floor_id
        z=top.elevation_m+requests[fid].height_m
        add(fid,'roof','roof',[_box(0,0,z,top.width_m,top.depth_m,options.slab_thickness_m)],options.slab_colour)
        if options.parapet_height_m>0:
            t=options.parapet_thickness_m
            if 2*t>=min(top.width_m,top.depth_m):
                raise ValueError('Parapet thickness exceeds roof dimensions.')
            parts=[_box(0,0,z+options.slab_thickness_m,top.width_m,t,options.parapet_height_m),
                   _box(0,top.depth_m-t,z+options.slab_thickness_m,top.width_m,t,options.parapet_height_m),
                   _box(0,t,z+options.slab_thickness_m,t,top.depth_m-2*t,options.parapet_height_m),
                   _box(top.width_m-t,t,z+options.slab_thickness_m,t,top.depth_m-2*t,options.parapet_height_m)]
            add(fid,'roof_parapet','parapet',parts,options.wall_colour)
    return BuildingModel(layout.id,elements,tuple(f.floor_id for f in ordered),tuple(warnings))


def plotly_figure(model: BuildingModel, *, visible_floor_ids: list[str] | None=None,
                  exploded_gap_m: float=0,show_roof: bool=True,
                  theme: Literal['light','dark']='light') -> go.Figure:
    """Pass the returned figure to st.plotly_chart; click legend groups to toggle floors.

    Streamlit can also supply multiselect floor IDs, roof toggle and gap slider.
    These presentation choices never change the assembled export geometry.
    """
    if not math.isfinite(exploded_gap_m) or exploded_gap_m<0:
        raise ValueError('Exploded-view gap must be finite and nonnegative.')
    selected=set(model.floor_ids if visible_floor_ids is None else visible_floor_ids)
    if not selected<=set(model.floor_ids):
        raise ValueError('Unknown floor selected.')
    fig=go.Figure();seen=set()
    for item in model.elements:
        vertices=item.mesh.vertices.copy()
        vertices[:,2]+=model.floor_ids.index(item.floor_id)*exploded_gap_m
        faces=item.mesh.faces
        visible=item.floor_id in selected and (show_roof or item.kind not in {'roof','parapet'})
        fig.add_trace(go.Mesh3d(x=vertices[:,0],y=vertices[:,1],z=vertices[:,2],
            i=faces[:,0],j=faces[:,1],k=faces[:,2],color=item.colour,opacity=item.opacity,
            name=item.floor_id,legendgroup=item.floor_id,showlegend=item.floor_id not in seen,
            visible=True if visible else False,flatshading=True,
            hovertemplate=html.escape(item.id)+'<br>Concept geometry<extra></extra>',
            meta={'element_id':item.id,'floor_id':item.floor_id,'kind':item.kind}))
        seen.add(item.floor_id)
    fig.update_layout(template='plotly_dark' if theme=='dark' else 'plotly_white',
        title='GharBuilder AI | concept 3D'+(' | exploded display' if exploded_gap_m else ''),
        scene={'aspectmode':'data','xaxis_title':'X (m)','yaxis_title':'Y (m)','zaxis_title':'Z (m)'},
        legend={'groupclick':'togglegroup'},margin={'l':0,'r':0,'t':50,'b':0},
        uirevision='gharbuilder-'+model.layout_id,height=650)
    return fig


def export_bundle(model: BuildingModel) -> bytes:
    """ZIP contains assembled GLB, Z-up OBJ and complete element/source manifest.

    OBJ uses vertex colours (viewer support varies); GLB has PBR materials. No
    MTL/texture sidecars or external URLs are needed. Presentation-only exploded
    transforms and visibility filters are excluded from these assembled exports.
    """
    scene=trimesh.Scene()
    for item in model.elements:
        scene.add_geometry(item.mesh.copy(),node_name=item.id,geom_name=item.id)
    # glTF is Y-up. Preserve right handedness by mapping (x,y,z) to (x,z,-y).
    gltf_scene=scene.copy()
    gltf_scene.apply_transform(trimesh.transformations.rotation_matrix(-math.pi/2,[1,0,0]))
    glb=gltf_scene.export(file_type='glb')
    obj_parts=[]
    offset=0
    for item in model.elements:
        obj_parts.append('o '+item.id.replace('/','_'))
        rgb=[c/255 for c in _rgba(item.colour)[:3]]
        for v in item.mesh.vertices:
            obj_parts.append('v '+' '.join(f'{n:.9g}' for n in [*v,*rgb]))
        for f in item.mesh.faces:
            obj_parts.append('f '+' '.join(str(int(i)+1+offset) for i in f))
        offset+=len(item.mesh.vertices)
    obj=('# GharBuilder concept mesh | metres | Z-up\n'+'\n'.join(obj_parts)+'\n').encode()
    manifest={'layout_id':model.layout_id,'units':'m','glb_axes':'Y-up; (x,z,-y) from project',
              'obj_axes':'Z-up project coordinates','export_pose':'assembled; all floors',
              'warnings':list(model.warnings),'elements':[{'id':e.id,'floor_id':e.floor_id,
              'source_id':e.source_id,'kind':e.kind,'triangles':len(e.mesh.faces)} for e in model.elements]}
    out=io.BytesIO()
    with zipfile.ZipFile(out,'w',zipfile.ZIP_DEFLATED) as z:
        z.writestr('GharBuilder_Model.glb',glb)
        z.writestr('GharBuilder_Model.obj',obj)
        z.writestr('model_manifest.json',json.dumps(manifest,ensure_ascii=False,indent=2))
    return out.getvalue()
