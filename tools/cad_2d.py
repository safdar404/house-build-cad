"""Shared vector primitives for dimensioned concept PNG and DXF exports.

SI metres throughout. Wall polygons have real plan openings. Furniture, MEP,
elevations and sections are explicit concept diagrams, not working drawings.
No model-generated code is executed and no export path is supplied by an LLM.
"""
from __future__ import annotations

import io
import json
import math
import re
import zipfile
from threading import RLock
from functools import wraps
from dataclasses import dataclass, field
from typing import Iterable

import ezdxf
import matplotlib
matplotlib.use('Agg')
from matplotlib.backends.backend_agg import FigureCanvasAgg
from matplotlib.figure import Figure
from matplotlib.patches import Circle as MplCircle, Polygon as MplPolygon
from shapely.geometry import LineString, Polygon, box
from shapely.ops import unary_union

from config import DISCLAIMER
from schemas import FloorPlan, LayoutAlternative, Requirements
from tools.geometry import PlanningEnvelope, opening_segment

LAYERS = {
    'WALLS': (7, '#24364b'), 'DOORS': (3, '#21815b'),
    'WINDOWS': (4, '#168dbe'), 'DIMENSIONS': (2, '#695c32'),
    'TEXT': (7, '#24364b'), 'FURNITURE': (8, '#8c75ac'),
    'ELECTRICAL': (1, '#d07a12'), 'PLUMBING': (5, '#2476d0'),
    'SITE': (3, '#459c66'), 'SECTION': (6, '#ad568f'),
}
Point2 = tuple[float, float]
_RENDER_LOCK = RLock()


def _serialized_render(function):
    @wraps(function)
    def guarded(*args, **kwargs):
        with _RENDER_LOCK:
            return function(*args, **kwargs)
    return guarded



@dataclass
class Stroke:
    points: list[Point2]
    layer: str
    closed: bool = False
    fill: bool = False


@dataclass
class Label:
    point: Point2
    text: str
    height: float = .16
    layer: str = 'TEXT'
    center: bool = True
    rotation: float = 0


@dataclass
class Symbol:
    point: Point2
    radius: float
    layer: str


@dataclass
class Dimension:
    start: Point2
    end: Point2
    base: Point2
    angle: int = 0


@dataclass
class Drawing:
    name: str
    title: str
    notes: list[str]
    strokes: list[Stroke] = field(default_factory=list)
    labels: list[Label] = field(default_factory=list)
    symbols: list[Symbol] = field(default_factory=list)
    dimensions: list[Dimension] = field(default_factory=list)

    def rectangle(self, x: float, y: float, w: float, h: float,
                  layer: str, fill: bool = False) -> None:
        self.strokes.append(Stroke([(x,y),(x+w,y),(x+w,y+h),(x,y+h)],layer,True,fill))


def _polygons(geometry) -> Iterable[Polygon]:
    if geometry.is_empty:
        return
    if geometry.geom_type == 'Polygon':
        yield geometry
    elif hasattr(geometry,'geoms'):
        for part in geometry.geoms:
            yield from _polygons(part)


def wall_geometry(floor: FloorPlan):
    """Union centre-line wall strips then subtract full-width opening slots."""
    walls={w.id:w for w in floor.walls}
    solids=[LineString([(w.start.x,w.start.y),(w.end.x,w.end.y)]).buffer(
            w.thickness_m/2,cap_style=2,join_style=2) for w in floor.walls]
    cuts=[]
    for o in floor.openings:
        w=walls[o.wall_id]
        # Window also interrupts the plan cut at window level; elevation sill is retained separately.
        cuts.append(opening_segment(w,o).buffer(w.thickness_m/2+.002,cap_style=2))
    return unary_union(solids).difference(unary_union(cuts))


def _floor_base(floor: FloorPlan, name: str, title: str) -> Drawing:
    d=Drawing(name,title,['Concept drawing | metres | room dimensions to wall centre lines',
                          'Door swings are diagrammatic; clearances and junctions require review.'])
    for poly in _polygons(wall_geometry(floor)):
        # Outline interior rings too; no opaque filling that could hide an inner courtyard.
        d.strokes.append(Stroke(list(poly.exterior.coords)[:-1],'WALLS',True))
        for ring in poly.interiors:
            d.strokes.append(Stroke(list(ring.coords)[:-1],'WALLS',True))
    walls={w.id:w for w in floor.walls}
    for o in floor.openings:
        seg=opening_segment(walls[o.wall_id],o)
        a,b=list(seg.coords)
        dx=(b[0]-a[0])/o.width_m; dy=(b[1]-a[1])/o.width_m
        if o.kind=='window':
            for shift in (-.035,0,.035):
                d.strokes.append(Stroke([(a[0]-dy*shift,a[1]+dx*shift),
                                         (b[0]-dy*shift,b[1]+dx*shift)],'WINDOWS'))
        else:
            end=(a[0]-dy*o.width_m,a[1]+dx*o.width_m)
            d.strokes.append(Stroke([a,end],'DOORS'))
            arc=[(a[0]+o.width_m*(dx*math.cos(t)-dy*math.sin(t)),
                  a[1]+o.width_m*(dy*math.cos(t)+dx*math.sin(t)))
                 for t in [i*math.pi/2/18 for i in range(19)]]
            d.strokes.append(Stroke(arc,'DOORS'))
    return d


def _room_labels(d: Drawing, floor: FloorPlan, detailed: bool) -> None:
    for r in floor.rooms:
        height=min(.18,max(.09,min(r.width,r.length)*.055))
        text=r.name
        if detailed:
            text+=f'\n{r.width:.2f} × {r.length:.2f} m\n{r.area_m2:.2f} m² (zone)'
        d.labels.append(Label((r.x+r.width/2,r.y+r.length/2),text,height))


def floor_plan(floor: FloorPlan) -> Drawing:
    d=_floor_base(floor,f'{floor.floor_id}_plan',f'{floor.floor_id} | Dimensioned floor plan')
    _room_labels(d,floor,True)
    d.dimensions=[Dimension((0,0),(floor.width_m,0),(0,-.75)),
                  Dimension((0,0),(0,floor.depth_m),(-.75,0),90)]
    d.notes.append(f'Covered envelope: {floor.covered_area_m2:.2f} m²; elevation {floor.elevation_m:+.2f} m.')
    return d


def furniture_plan(floor: FloorPlan) -> Drawing:
    d=_floor_base(floor,f'{floor.floor_id}_furniture',f'{floor.floor_id} | Furniture concept')
    for r in floor.rooms:
        inset=.35
        available_w=max(0,r.width-2*inset); available_l=max(0,r.length-2*inset)
        sizes={'bedroom':(1.5,2,'BED'),'lounge':(1.9,.85,'SOFA'),
               'drawing':(1.9,.85,'SOFA'),'dining':(1.2,1.8,'TABLE'),
               'kitchen':(.6,1.8,'COUNTER'),'garage':(2.5,5,'CAR ENVELOPE'),
               'stairs':(1,2.5,'STAIR ZONE'),'bathroom':(.6,.8,'FIXTURE')}
        if r.kind not in sizes:
            continue
        w,h,label=sizes[r.kind]
        if w>available_w or h>available_l:
            d.notes.append(f'{r.id}: nominal {label.lower()} does not fit with the concept inset; review dimensions.')
            continue
        x=r.x+inset;y=r.y+inset
        d.rectangle(x,y,w,h,'FURNITURE')
        d.labels.append(Label((x+w/2,y+h/2),label,.1,'FURNITURE'))
    d.notes.append('Illustrative furniture only; door swings, circulation and usable clearances are not certified.')
    return d


def electrical_plan(floor: FloorPlan) -> Drawing:
    d=_floor_base(floor,f'{floor.floor_id}_electrical',f'{floor.floor_id} | Electrical point concept')
    for r in floor.rooms:
        cx=r.x+r.width/2;cy=r.y+r.length/2
        d.symbols.append(Symbol((cx,cy),.1,'ELECTRICAL'))
        d.strokes.append(Stroke([(cx-.08,cy-.08),(cx+.08,cy+.08)],'ELECTRICAL'))
        d.strokes.append(Stroke([(cx-.08,cy+.08),(cx+.08,cy-.08)],'ELECTRICAL'))
        d.rectangle(r.x+.15,r.y+.2,.12,.12,'ELECTRICAL')
        d.labels.append(Label((r.x+.35,r.y+.25),'S',.1,'ELECTRICAL'))
        if r.kind not in {'stairs','circulation','bathroom'}:
            d.rectangle(r.x+r.width-.3,r.y+.2,.14,.1,'ELECTRICAL')
            d.labels.append(Label((r.x+r.width-.23,r.y+.45),'P',.1,'ELECTRICAL'))
        d.labels.append(Label((cx,cy+.35),r.name,.12))
    d.notes+=['Legend: crossed circle = proposed light, S = switch, P = socket.',
               'Schematic points only. No circuit design, cable sizing, protection or certified load schedule.']
    return d


def plumbing_plan(floor: FloorPlan) -> Drawing:
    d=_floor_base(floor,f'{floor.floor_id}_plumbing',f'{floor.floor_id} | Plumbing fixture concept')
    for r in floor.rooms:
        if r.kind not in {'bathroom','kitchen','utility'}:
            continue
        x=r.x+min(.4,r.width/3);y=r.y+min(.5,r.length/3)
        d.symbols.append(Symbol((x,y),.1,'PLUMBING'))
        d.labels.append(Label((x+.25,y),'W',.12,'PLUMBING',False))
        d.symbols.append(Symbol((x,y+min(.4,r.length/4)),.08,'PLUMBING'))
        d.labels.append(Label((x+.25,y+min(.4,r.length/4)),'D',.12,'PLUMBING',False))
    d.notes+=['Legend: W = proposed water connection; D = proposed drainage connection.',
               'Fixture nodes only; routes, slopes, vents, pipe sizes and authority connection points remain unresolved.']
    return d


def site_plan(layout: LayoutAlternative, req: Requirements, env: PlanningEnvelope) -> Drawing:
    d=Drawing('site_plan','Site plan | confirmed concept envelope',[
        'Metres | x from left boundary, y inward from front road',
        f'Facing: {req.plot.facing}; diagram is not a georeferenced survey.',
        f'Envelope status: {env.status}; source: {env.source}'])
    p=req.plot
    d.rectangle(0,0,p.width_m,p.depth_m,'SITE')
    w,h=env.dimensions(req)
    d.rectangle(env.left_m,env.front_m,w,h,'DIMENSIONS')
    ground=next((f for f in layout.floors if next(r.level for r in req.floors if r.id==f.floor_id)==0),None)
    if ground:
        d.rectangle(env.left_m,env.front_m,ground.width_m,ground.depth_m,'WALLS')
        d.labels.append(Label((env.left_m+ground.width_m/2,env.front_m+ground.depth_m/2),'GROUND FOOTPRINT',.18))
    d.labels.append(Label((p.width_m/2,-.4),'FRONT ROAD / APPROACH',.18,'SITE'))
    d.dimensions=[Dimension((0,0),(p.width_m,0),(0,-1.2)),Dimension((0,0),(0,p.depth_m),(-1.1,0),90)]
    d.notes.append(f'Setbacks F/R/L/R: {env.front_m:g}/{env.rear_m:g}/{env.left_m:g}/{env.right_m:g} m.')
    return d


def front_elevation(layout: LayoutAlternative, req: Requirements) -> Drawing:
    d=Drawing('front_elevation','Front elevation | schematic massing',[
        'Metres | front facade at local y=0; basement shown dashed concept is not supported.',
        'No architectural facade detailing or certified structural member dimensions.'])
    requests={r.id:r for r in req.floors}
    for f in layout.floors:
        height=requests[f.floor_id].height_m
        if requests[f.floor_id].level<0:
            continue
        d.rectangle(0,f.elevation_m,f.width_m,height,'WALLS')
        walls={w.id:w for w in f.walls}
        for o in f.openings:
            wall=walls[o.wall_id]
            if abs(wall.start.y)>1e-5 or abs(wall.end.y)>1e-5:
                continue
            seg=opening_segment(wall,o)
            xs=[p[0] for p in seg.coords]
            d.rectangle(min(xs),f.elevation_m+o.sill_m,max(xs)-min(xs),o.height_m,
                        'DOORS' if o.kind=='door' else 'WINDOWS')
        d.labels.append(Label((f.width_m+.25,f.elevation_m+.2),f'{f.floor_id} {f.elevation_m:+.2f} m',.14,center=False))
    return d


def section(layout: LayoutAlternative, req: Requirements) -> Drawing:
    d=Drawing('section_aa','Section A–A | schematic longitudinal cut',[
        'Metres | cut at x = 0.47 × floor width; slabs are diagram lines without designed thickness.',
        'Stairs shown as zones, not riser/tread design. Foundation and beam design excluded.'])
    requests={r.id:r for r in req.floors}
    for f in layout.floors:
        z=f.elevation_m;h=requests[f.floor_id].height_m;cut=f.width_m*.47
        d.rectangle(0,z,f.depth_m,h,'SECTION')
        for r in f.rooms:
            if r.x<=cut<=r.x+r.width:
                d.strokes.append(Stroke([(r.y,z),(r.y,z+h)],'SECTION'))
                d.strokes.append(Stroke([(r.y+r.length,z),(r.y+r.length,z+h)],'SECTION'))
                d.labels.append(Label((r.y+r.length/2,z+h/2),r.name,.13))
        d.labels.append(Label((f.depth_m+.3,z+.2),f'{f.floor_id} {z:+.2f} m',.14,center=False))
    return d


def _dimension_primitives(dim: Dimension) -> tuple[list[Stroke],Label]:
    a,b,base=dim.start,dim.end,dim.base
    if dim.angle==0:
        p=(a[0],base[1]);q=(b[0],base[1]);value=abs(b[0]-a[0]);anchor=((p[0]+q[0])/2,p[1]+.13)
    else:
        p=(base[0],a[1]);q=(base[0],b[1]);value=abs(b[1]-a[1]);anchor=(p[0]-.13,(p[1]+q[1])/2)
    strokes=[Stroke([a,p],'DIMENSIONS'),Stroke([b,q],'DIMENSIONS'),Stroke([p,q],'DIMENSIONS')]
    for x,y in (p,q):
        strokes.append(Stroke([(x-.08,y-.08),(x+.08,y+.08)],'DIMENSIONS'))
    return strokes,Label(anchor,f'{value:.2f} m',.14,'DIMENSIONS',True,dim.angle)


@_serialized_render
def render_png(d: Drawing) -> bytes:
    """Agg canvas avoids global pyplot state across Streamlit sessions."""
    fig=Figure(figsize=(9,11),dpi=140,facecolor='#f6f8fc');FigureCanvasAgg(fig)
    ax=fig.add_axes((.09,.27,.82,.62));ax.set_aspect('equal');ax.set_facecolor('#f6f8fc')
    strokes=list(d.strokes);labels=list(d.labels)
    for dim in d.dimensions:
        extra,label=_dimension_primitives(dim);strokes+=extra;labels.append(label)
    for s in strokes:
        color=LAYERS[s.layer][1]
        pts=s.points+[s.points[0]] if s.closed else s.points
        if s.fill:
            ax.add_patch(MplPolygon(s.points,closed=True,color=color,alpha=.12))
        ax.plot([p[0] for p in pts],[p[1] for p in pts],color=color,lw=.8)
    for s in d.symbols:
        ax.add_patch(MplCircle(s.point,s.radius,fill=False,color=LAYERS[s.layer][1],lw=.9))
    for label in labels:
        ax.text(*label.point,label.text,fontsize=max(5,min(9,label.height*42)),color=LAYERS[label.layer][1],
                ha='center' if label.center else 'left',va='center',rotation=label.rotation)
    ax.relim();ax.autoscale_view();ax.margins(.16);ax.axis('off')
    fig.text(.07,.96,'GHARBUILDER AI',fontsize=11,weight='bold',color='#3949ab')
    fig.text(.07,.925,d.title,fontsize=13,weight='bold',color='#24364b')
    import textwrap
    notes=[*d.notes,'Preliminary concept. '+DISCLAIMER]
    y=.22
    for line in textwrap.wrap(' | '.join(notes),width=114):
        if y<.035:
            break
        fig.text(.07,y,line,fontsize=7,color='#47566a');y-=.016
    output=io.BytesIO();fig.savefig(output,format='png',dpi=140);fig.clear()
    return output.getvalue()


def render_dxf(d: Drawing) -> bytes:
    doc=ezdxf.new('R2010');doc.units=6 # INSUNITS: metres
    for name,(aci,_) in LAYERS.items():
        doc.layers.new(name,dxfattribs={'color':aci})
    msp=doc.modelspace()
    for s in d.strokes:
        msp.add_lwpolyline(s.points,close=s.closed,dxfattribs={'layer':s.layer})
    for s in d.symbols:
        msp.add_circle(s.point,s.radius,dxfattribs={'layer':s.layer})
    for label in d.labels:
        # MTEXT handles multiline labels without injecting DXF formatting commands.
        safe=label.text.replace('\\','/').replace('{','(').replace('}',')').replace('\n',r'\P')
        msp.add_mtext(safe,dxfattribs={'insert':label.point,'char_height':label.height,
                      'layer':label.layer,'attachment_point':5 if label.center else 4,
                      'rotation':label.rotation})
    for dim in d.dimensions:
        entity=msp.add_linear_dim(base=dim.base,p1=dim.start,p2=dim.end,angle=dim.angle,
             dimstyle='Standard',override={'dimtxt':.14,'dimasz':.12,'dimdec':2,'dimpost':'<> m'},
             dxfattribs={'layer':'DIMENSIONS'})
        entity.render()
    # Title and full notes retained even if PNG footer capacity is exceeded.
    points=[p for s in d.strokes for p in s.points]
    ymax=max((p[1] for p in points),default=0)
    msp.add_mtext(d.title.replace('\\','/'),dxfattribs={'insert':(0,ymax+1),'char_height':.22,'layer':'TEXT'})
    notes=' | '.join([*d.notes,DISCLAIMER]).replace('\\','/').replace('{','(').replace('}',')')
    msp.add_mtext(notes,dxfattribs={'insert':(0,-2),'char_height':.12,'width':12,'layer':'TEXT'})
    audit=doc.audit()
    if audit.has_errors:
        raise ValueError('Generated DXF failed its internal audit.')
    stream=io.StringIO();doc.write(stream)
    return stream.getvalue().encode('utf-8')


def build_drawing_bundle(layout: LayoutAlternative, req: Requirements,
                         env: PlanningEnvelope) -> bytes:
    """Produce all conceptual drawing variants as PNG + DXF in a ZIP.

    Caller must run access/geometry validation before invoking this tool.
    PNG rendering is serialized across threads because Matplotlib is not
    thread-safe. This function does not create background jobs.
    """
    drawings=[]
    for f in layout.floors:
        drawings += [floor_plan(f),furniture_plan(f),electrical_plan(f),plumbing_plan(f)]
    drawings += [site_plan(layout,req,env),front_elevation(layout,req),section(layout,req)]
    stream=io.BytesIO()
    manifest={'schema_version':'1.0','layout_id':layout.id,'units':'m',
              'dimension_basis':'wall centre-line zones; not clear internal dimensions',
              'disclaimer':DISCLAIMER,'drawings':[]}
    with zipfile.ZipFile(stream,'w',zipfile.ZIP_DEFLATED) as archive:
        for d in drawings:
            if not re.fullmatch(r'[A-Za-z0-9_-]+',d.name):
                raise ValueError('Unsafe drawing filename.')
            archive.writestr('png/'+d.name+'.png',render_png(d))
            archive.writestr('dxf/'+d.name+'.dxf',render_dxf(d))
            manifest['drawings'].append({'name':d.name,'title':d.title,'notes':d.notes})
        archive.writestr('drawing_manifest.json',json.dumps(manifest,ensure_ascii=False,indent=2))
    return stream.getvalue()
