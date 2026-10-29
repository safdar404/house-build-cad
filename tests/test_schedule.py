from datetime import date
import pytest
from tools.model_3d import BuildingModel
from tools.schedule_4d import LinkedActivity,WorkCalendar,CalendarException,build_schedule,planned_progress

def test_slowdown_and_cure_delay():
    model=BuildingModel('unit',[],('g',),())
    calendar=WorkCalendar(working_weekdays=[0,1,2,3,4],exceptions=[CalendarException(name='test slowdown',
        start=date(2026,10,5),end_inclusive=date(2026,10,6),productivity_factor=.5,source='Synthetic test')])
    tasks=[LinkedActivity(id='a',name='a',duration_days=1,curing_days=2),LinkedActivity(id='b',name='b',duration_days=1,predecessor_ids=['a'])]
    result=build_schedule(tasks,date(2026,10,5),calendar,model=model)
    lookup={t.activity.id:t for t in result.tasks}
    assert lookup['a'].finish_exclusive==date(2026,10,7)
    assert lookup['b'].start==date(2026,10,9)
    assert planned_progress(result,result.finish_exclusive)==pytest.approx(100)

def test_cycles_and_unavailable_calendar_fail():
    model=BuildingModel('unit',[],('g',),())
    calendar=WorkCalendar(working_weekdays=[0],exceptions=[])
    tasks=[LinkedActivity(id='a',name='a',duration_days=1,predecessor_ids=['b']),LinkedActivity(id='b',name='b',duration_days=1,predecessor_ids=['a'])]
    with pytest.raises(ValueError):build_schedule(tasks,date(2026,10,5),calendar,model=model)
    closed=WorkCalendar(working_weekdays=[0],exceptions=[CalendarException(name='closed',start=date(2026,1,1),end_inclusive=date(2027,1,1),productivity_factor=0,source='Test')])
    with pytest.raises(ValueError):build_schedule([LinkedActivity(id='a',name='a',duration_days=1)],date(2026,10,5),closed,model=model,max_calendar_days=10)
