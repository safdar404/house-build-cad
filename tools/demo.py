"""Reproducible synthetic 10-marla Lahore G+2 scenario, never a real design."""
from __future__ import annotations
from datetime import date
from pathlib import Path
from schemas import *
from agents.planning_agent import PlannedAlternative,PlanningOutput
from agents.orchestrator import PlanningStageInput
from agents.compliance_agent import ComplianceInput,load_bylaws,evaluate_compliance
from agents.cad_agent import CADAgent,CADInput
from agents.modeling_agent import ModelingAgent,ModelingInput
from agents.structural_agent import StructuralAgent,StructuralInput
from agents.mep_agent import MEPAgent,MEPInput,MEPAssumptions
from agents.scheduling_agent import SchedulingAgent,SchedulingInput
from agents.cost_agent import CostAgent
from agents.labour_agent import LabourAgent
from agents.twin_agent import DigitalTwinAgent
from agents.bim_agent import BIMAgent
from agents.report_agent import ReportAgent
from tools.geometry import PlanningEnvelope,AccessLink,validate_layout
from tools.model_3d import ModelOptions
from tools.bim_ifc import BIMInput,ifc_available
from tools.schedule_4d import *
from tools.cost import *
from tools.labour import *
from tools.twin import TwinInput,ProgressObservation
from tools.report import ReportInput,ExportAttachment,report_fingerprint
from ui.state import WorkspaceState

DEMO_NOTE='SYNTHETIC DEMONSTRATION ONLY - not a surveyed, approved or engineered building.'


def sample_brief() -> Requirements:
    return Requirements(city='Lahore',authority='LDA',plot=Plot(width_m=9.144,depth_m=22.86,facing='N',marla_sqft=225,declared_area_sqft=2250),
        floors=[FloorRequest(id=fid,name=name,level=i,bedrooms=2,bathrooms=2,kitchens=1) for i,(fid,name) in enumerate([('g','Ground'),('f1','First'),('f2','Second')])],
        family_size=6,car_spaces=0,accessibility_needs=[],stairs_position='front right',lift=False,
        drawing_dining='Separate drawing and dining',tv_lounge=True,servant_quarter=False,lawn=False,
        budget_pkr=50_000_000,quality='Standard',style='Modern concept',green_features=['Illustrative solar allowance'],start_date=date(2026,10,1),
        assumptions=[Assumption(id='synthetic',description=DEMO_NOTE,status='accepted')])


def sample_envelope() -> PlanningEnvelope:
    return PlanningEnvelope(front_m=1.524,rear_m=1.524,left_m=0,right_m=0,source=DEMO_NOTE+' User-assumed 5 ft front/rear open space; no statutory rule implied.',
        status='concept_assumptions',confirmed=True,reference_hash=content_hash({'demo':DEMO_NOTE}))


def sample_alternatives(req: Requirements,env: PlanningEnvelope) -> PlanningOutput:
    width,depth=env.dimensions(req);a=(width-1.2)/2;b=a+1.2;ys=[0,4,8,12,15,depth]
    alternatives=[]
    for number in range(2):
        floors=[];access=[]
        for level,fr in enumerate(req.floors):
            room_specs=[('bed1','Bedroom 1','bedroom'),('bed2','Bedroom 2','bedroom'),('kitchen','Kitchen','kitchen'),('bath1','Bathroom 1','bathroom'),('drawing','Drawing','drawing')]
            if number:room_specs[2],room_specs[4]=room_specs[4],room_specs[2]
            right=[('stairs','Stair zone','stairs'),('lounge','TV lounge','lounge'),('dining','Dining','dining'),('bath2','Bathroom 2','bathroom'),('store','Store','store')]
            rooms=[Room(id='hall',name='Hall',kind='circulation',x=a,y=0,width=1.2,length=depth)]
            walls=[Wall(id=key,start=Point(x=x,y=0),end=Point(x=x,y=depth)) for key,x in [('west',0),('left_partition',a),('right_partition',b),('east',width)]]
            walls += [Wall(id=key,start=Point(x=0,y=y),end=Point(x=width,y=y)) for key,y in [('front',0),('rear',depth)]]
            openings=[Opening(id='entrance',wall_id='front',kind='door',offset_m=a+.15,width_m=.9,height_m=2.1)]
            access.append(AccessLink(floor_id=fr.id,opening_id='entrance',room_a='hall',room_b=None))
            for side,specs,x,w,partition,external in [('left',room_specs,0,a,'left_partition','west'),('right',right,b,width-b,'right_partition','east')]:
                for row,((rid,name,kind),lo,hi) in enumerate(zip(specs,ys,ys[1:])):
                    rooms.append(Room(id=rid,name=name,kind=kind,x=x,y=lo,width=w,length=hi-lo))
                    did='door_'+rid
                    openings.append(Opening(id=did,wall_id=partition,kind='door',offset_m=lo+.4,width_m=.9,height_m=2.1))
                    access.append(AccessLink(floor_id=fr.id,opening_id=did,room_a=rid,room_b='hall'))
                    openings.append(Opening(id='win_'+rid,wall_id=external,kind='window',offset_m=lo+1.2,width_m=1.2,height_m=1.2,sill_m=.9))
                    if row:
                        walls.append(Wall(id=side+'_row_'+str(row),start=Point(x=x,y=lo),end=Point(x=x+w,y=lo)))
            floors.append(FloorPlan(floor_id=fr.id,elevation_m=level*3.05,width_m=width,depth_m=depth,rooms=rooms,walls=walls,openings=openings))
        layout=LayoutAlternative(id='demo_'+str(number+1),title='Demonstration alternative '+str(number+1),floors=floors,
            rationale='Synthetic centre-line zoning with a continuous hall and stacked stair/services.',
            unresolved_issues=[DEMO_NOTE,'Stair treads/landings/headroom, structure, clear widths, detailed services and statutory setbacks require professional redesign.'])
        assessment=validate_layout(layout,req,env,access)
        if not assessment.valid:raise ValueError('The synthetic fixture failed geometry validation.')
        alternatives.append(PlannedAlternative(layout=layout,access=access))
    return PlanningOutput(alternatives=alternatives,design_notes=[DEMO_NOTE])


def sample_mep() -> MEPAssumptions:
    return MEPAssumptions(source=DEMO_NOTE,accepted_for_estimation=True,light_points_per_m2=.08,
        lighting_watts_per_point=10,lighting_hours_per_day=5,sockets_per_habitable_room=2,
        cooling_watts_thermal_per_m2=100,cooling_cop=3,cooling_hours_per_day=4,
        cooled_room_kinds=['bedroom','lounge','drawing','dining'],water_litres_person_day=100,storage_days=2,
        overhead_storage_fraction=.5,peak_sun_hours=5,solar_performance_ratio=.8,target_solar_energy_fraction=.5,
        roof_usable_area_m2=50,pv_module_area_m2_per_kw=6,wc_per_bathroom=1,basin_per_bathroom=1,
        shower_per_bathroom=1,sink_per_kitchen=1,gas_points_per_kitchen=1,appliances=[])


def build_sample(*,include_reports=True,progress=None):
    """Return isolated workspace and useful UI inputs; no API calls or disk writes."""
    state=WorkspaceState();state.project.name='DEMONSTRATION - 10 Marla Lahore G+2'
    req=sample_brief();env=sample_envelope();planning=sample_alternatives(req,env);choice=planning.alternatives[0]
    layout=choice.layout;access=choice.access
    def commit(stage,request,operation):
        if progress:progress('Demonstration: '+stage.value)
        state.authorize(stage,request,reviewed_hash=content_hash(request),user_approved=True)
        state.start(stage,request)
        value=operation(request)
        key=state.complete(stage,request,value)
        state.approve(stage,reviewed_hash=key,user_approved=True)
        return value
    commit(Stage.REQUIREMENTS,req,lambda v:v)
    compliance=commit(Stage.COMPLIANCE,ComplianceInput(requirements=req,assessment_date=date(2026,10,29)),lambda v:evaluate_compliance(v,load_bylaws()))
    commit(Stage.PLANNING,PlanningStageInput(requirements=req,envelope=env),lambda v:planning)
    state.select_layout(choice,req,env,reviewed_hash=content_hash(choice),user_approved=True)
    cad=commit(Stage.CAD,CADInput(layout=layout,requirements=req,envelope=env,access=access),lambda v:CADAgent.export(v,reviewed_hash=content_hash(v),user_approved=True))
    model_input=ModelingInput(layout=layout,requirements=req,envelope=env,access=access,options=ModelOptions(assumptions_accepted=True))
    model=commit(Stage.MODEL,model_input,lambda v:ModelingAgent.build(v,reviewed_hash=content_hash(v),user_approved=True))
    structural=commit(Stage.STRUCTURAL,StructuralInput(requirements=req,layout=layout,envelope=env,access=access,preferred_grid_spacing_m=4),StructuralAgent.evaluate)
    mep=commit(Stage.MEP,MEPInput(requirements=req,layout=layout,envelope=env,access=access,assumptions=sample_mep()),MEPAgent.evaluate)
    bim=None
    if ifc_available():bim=commit(Stage.BIM,BIMInput(project_id=state.project.id,project_name=state.project.name,requirements=req,layout=layout,envelope=env,access=access,options=model_input.options),lambda v:BIMAgent.export(v,reviewed_hash=content_hash(v),user_approved=True))
    assumptions=ScheduleAssumptions(source=DEMO_NOTE,accepted_for_planning=True,
        recipes=[TaskRecipe(kind=k,productive_days=3,crew_size=3,curing_days=7 if k in {'foundation','slab'} else 0) for k in TASK_KINDS],
        calendar=WorkCalendar(working_weekdays=[0,1,2,3,4,5],exceptions=[]))
    schedule=commit(Stage.SCHEDULE,SchedulingInput(model_hash=model_fingerprint(model.model),start_date=req.start_date,assumptions=assumptions),
        lambda v:SchedulingAgent.schedule(v,model.model,reviewed_hash=content_hash(v),user_approved=True))
    evidence=Evidence(source=DEMO_NOTE,effective_date=date(2026,10,29))
    catalog=RateCatalog(last_updated=date(2026,10,29),base_city='Lahore',notes=DEMO_NOTE,
        rates=[MaterialRate(id='demo_fee',description='Synthetic combined fee allowance',unit='job',value_pkr=100000,evidence=evidence)],
        city_factors=[CityFactor(city='Lahore',multiplier=1,evidence=evidence)],
        area_rates=[AreaRate(quality='Standard',grey_pkr_sqft=3200,finishing_pkr_sqft=3800,labour_fraction=.25,evidence=evidence)])
    cost=commit(Stage.COST,CostInput(requirements=req,layout=layout,envelope=env,access=access,rates=catalog,
        valuation_date=date(2026,10,29),quantity_rules=[],extra_charges=[ExtraCharge(id='demo_fee',label='Synthetic fees',rate_id='demo_fee',unit='job',quantity=1,category='other')],
        milestones=[Milestone(label='Synthetic milestone 1',percent=50),Milestone(label='Synthetic milestone 2',percent=50)],selected_basis='area_benchmark',tax_percent=0,
        assumptions_accepted=True,area_rate_scope_accepted=True),lambda v:CostAgent.estimate(v,reviewed_hash=content_hash(v),user_approved=True))
    wages=LabourRateCatalog(city='Lahore',last_updated=date(2026,10,29),standard_day_hours=8,
        wages=[WageRate(trade='labourer',daily_wage_pkr=100,evidence=evidence)],notes=DEMO_NOTE+' Wage 100 is a deliberately synthetic test value, not a legal or market rate.')
    labour=commit(Stage.LABOUR,LabourInput(city='Lahore',schedule=schedule,reviewed_schedule_hash=content_hash(schedule),rates=wages,
        valuation_date=date(2026,10,29),task_crews=[TaskCrew(activity_id=t.activity.id,trades=[TradeCrew(trade='labourer',workers=t.activity.crew_size)]) for t in schedule.tasks],
        material_cost_pkr=cost.material_pkr,material_cost_source=DEMO_NOTE,overhead_percent=0,contractor_margin_percent=0,assumptions_accepted=True),
        lambda v:LabourAgent.estimate(v,reviewed_hash=content_hash(v),user_approved=True))
    monitoring=commit(Stage.TWIN,TwinInput(layout=layout,reviewed_layout_hash=content_hash(layout),schedule=schedule,reviewed_schedule_hash=content_hash(schedule),as_of=date(2026,10,29),
        observations=[ProgressObservation(id='demo_'+str(i),activity_id=t.activity.id,observed_on=date(2026,10,29),progress_percent=0,cumulative_actual_cost_pkr=0,source=DEMO_NOTE) for i,t in enumerate(schedule.tasks)],
        construction_budget_pkr=cost.construction_pkr,budget_source=DEMO_NOTE,spend_scope='Synthetic construction cost only',spend_coverage_declared_complete=True),
        lambda v:DigitalTwinAgent.snapshot(v,reviewed_hash=content_hash(v),user_approved=True))
    if include_reports:
        report=ReportInput(project_name=state.project.name,report_date=date(2026,10,29),requirements=req,layout=layout,reviewed_layout_hash=content_hash(layout),
            cost=cost,cost_hash=content_hash(cost),schedule=schedule,schedule_hash=content_hash(schedule),labour=labour,labour_hash=content_hash(labour),
            monitoring=monitoring,monitoring_hash=content_hash(monitoring),structural=structural,structural_hash=content_hash(structural),mep=mep,mep_hash=content_hash(mep))
        attachments=[ExportAttachment('Drawings.zip',cad.archive_bytes),ExportAttachment('Meshes.zip',ModelingAgent.export(model))]
        if bim:attachments.append(ExportAttachment(bim.filename,bim.content))
        commit(Stage.REPORT,report,lambda v:ReportAgent.generate(v,attachments,reviewed_hash=report_fingerprint(v,attachments),user_approved=True))
    return state,{'requirements':req,'envelope':env,'planning':planning,'model_input':model_input,'compliance':compliance,
                   'schedule_assumptions':assumptions,'mep_assumptions':sample_mep()}
