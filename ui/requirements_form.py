"""API-free project form with validation and explicit review."""
import streamlit as st
from schemas import Requirements,Plot,FloorRequest
from ui.workflow import today
from ui.choices import choose,multi,CITIES,AUTHORITIES,STYLES,STAIRS,DINING,ACCESS,GREEN


def render_project_form(save_draft):
    with st.expander('📝 Enter my project using a form — no API key required',expanded=True):
        st.caption('Save your draft, review the normalized brief below, then confirm it. Changing requirements makes dependent outputs stale.')
        try:old=Requirements.model_validate_json(st.session_state.get('gh_requirements_draft','{}'))
        except ValueError:old=None
        st.caption('Save your draft before changing the floor count, so existing entries can be retained.')
        floor_count=st.number_input('Number of floors to configure',min_value=1,max_value=24,value=len(old.floors) if old else 1,key='gh_form_floor_count')
        budget_presets={'Enter my own budget':None,'PKR 10 million':10000000.,'PKR 20 million':20000000.,'PKR 30 million':30000000.,'PKR 50 million':50000000.}
        budget_pick=st.selectbox('Budget entry choice',list(budget_presets),help='These are user-selectable budgets, not construction cost quotations.')
        room_patterns={'Keep / edit counts below':None,'1 bedroom, 1 bathroom, 1 kitchen':(1,1,1),'2 bedrooms, 2 bathrooms, 1 kitchen':(2,2,1),'3 bedrooms, 3 bathrooms, 1 kitchen':(3,3,1)}
        room_pick=st.selectbox('Starting room counts for each floor',list(room_patterns),help='The selected pattern applies to every listed floor. Edit each floor separately below before confirming.')
        with st.form('project_input_form'):
            a,b=st.columns(2)
            city=choose(a,'City',CITIES,old.city if old else None)
            authority=choose(b,'Housing authority / society',AUTHORITIES,old.authority if old else None)
            width=a.number_input('Plot width (feet)',min_value=.1,value=old.plot.width_m/.3048 if old else 30.)
            depth=b.number_input('Plot depth (feet)',min_value=.1,value=old.plot.depth_m/.3048 if old else 75.)
            directions=['N','NE','E','SE','S','SW','W','NW']
            facing=a.selectbox('Plot facing',directions,index=directions.index(old.plot.facing) if old else 0)
            marla=b.selectbox('Square feet per marla',[225.,272.25],index=1 if old and old.plot.marla_sqft==272.25 else 0)
            corner=a.checkbox('Corner plot',value=old.plot.corner if old else False)
            family=b.number_input('Family members',min_value=1,max_value=100,value=old.family_size if old else 1)
            budget=a.number_input('Budget PKR',min_value=1.,value=budget_presets[budget_pick] if budget_presets[budget_pick] is not None else float(old.budget_pkr) if old else None)
            qualities=['Grey only','Economy','Standard','Premium','Luxury']
            quality=b.selectbox('Construction quality',qualities,index=qualities.index(old.quality) if old else 2)
            style=choose(a,'Architectural style',STYLES,old.style if old else None)
            start=b.date_input('Intended start date',value=old.start_date if old else today())
            stairs=choose(a,'Stairs position / preference',STAIRS,old.stairs_position if old else None)
            parking=b.number_input('Car parking spaces',min_value=0,max_value=20,value=old.car_spaces if old else 0)
            dining=choose(a,'Drawing / dining arrangement',DINING,old.drawing_dining if old else None)
            accessibility=multi(b,'Accessibility needs',ACCESS,old.accessibility_needs if old else [])
            green=multi(a,'Green features',GREEN,old.green_features if old else [])
            lift=a.checkbox('Lift',value=old.lift if old else False)
            lounge=b.checkbox('TV lounge',value=old.tv_lounge if old else False)
            servant=a.checkbox('Servant quarter',value=old.servant_quarter if old else False)
            lawn=b.checkbox('Lawn',value=old.lawn if old else False)
            st.write('Edit floors below; add/delete rows. Levels: basement −1, ground 0, first 1. Review the proposed 3.05 m height or change it.')
            existing=[f.model_dump(include={'id','name','level','height_m','bedrooms','bathrooms','kitchens'}) for f in old.floors] if old else []
            rows=[existing[i] if i<len(existing) else dict(id='floor_'+str(i),name='Ground' if i==0 else 'Floor '+str(i),level=i,height_m=3.05,bedrooms=0,bathrooms=0,kitchens=0) for i in range(int(floor_count))]
            if room_patterns[room_pick] is not None:
                for row in rows:row.update(dict(zip(['bedrooms','bathrooms','kitchens'],room_patterns[room_pick])))
            floors=st.data_editor(rows,num_rows='dynamic',key='gh_floor_entry_'+str(floor_count)+'_'+room_pick,
                column_config={name:st.column_config.NumberColumn(name.title(),min_value=0,max_value=30 if name!='kitchens' else 10,step=1,help='Enter the requested count for this floor') for name in ['bedrooms','bathrooms','kitchens']})
            reviewed=st.checkbox('I checked these form values, including dimensions, floor heights and room counts')
            submitted=st.form_submit_button('Save project draft',type='primary')
        if submitted:
            if not reviewed:st.error('Check the form values and tick the review box first.');return
            missing=[label for label,value in [('City',city),('Housing authority / society',authority),('Architectural style',style),('Stairs preference',stairs),('Drawing / dining arrangement',dining)] if not value.strip()]
            if budget is None:missing.append('Budget PKR')
            if missing:st.error('Please complete: '+', '.join(missing));return
            try:
                split=lambda s:[x.strip() for x in s.split(',') if x.strip()]
                req=Requirements(city=city.strip(),authority=authority.strip(),plot=Plot(width_m=width*.3048,depth_m=depth*.3048,facing=facing,corner=corner,marla_sqft=marla),
                    floors=[FloorRequest.model_validate({**(next((f.model_dump() for f in old.floors if f.id==row.get('id')), {}) if old else {}),**row}) for row in floors],family_size=family,car_spaces=parking,
                    accessibility_needs=accessibility,stairs_position=stairs.strip(),lift=lift,drawing_dining=dining.strip(),tv_lounge=lounge,
                    servant_quarter=servant,lawn=lawn,budget_pkr=budget,quality=quality,style=style.strip(),green_features=green,start_date=start,
                    assumptions=old.assumptions if old else [],soil_description=old.soil_description if old else None)
                save_draft(req.model_dump_json());st.rerun()
            except (ValueError,TypeError) as error:st.error('Complete required text and valid floor rows. '+str(error).split('\n')[0])
