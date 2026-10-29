"""API-free project form with validation and explicit review."""
import streamlit as st
from schemas import Requirements,Plot,FloorRequest
from ui.workflow import today


def render_project_form(save_draft):
    with st.expander('📝 Enter my project using a form — no API key required',expanded=True):
        st.caption('Save your draft, review the normalized brief below, then confirm it. Changing requirements makes dependent outputs stale.')
        try:old=Requirements.model_validate_json(st.session_state.get('gh_requirements_draft','{}'))
        except ValueError:old=None
        with st.form('project_input_form'):
            a,b=st.columns(2)
            city=a.text_input('City',value=old.city if old else '')
            authority=b.text_input('Housing authority / society',value=old.authority if old else '')
            width=a.number_input('Plot width (feet)',min_value=.1,value=old.plot.width_m/.3048 if old else 30.)
            depth=b.number_input('Plot depth (feet)',min_value=.1,value=old.plot.depth_m/.3048 if old else 75.)
            directions=['N','NE','E','SE','S','SW','W','NW']
            facing=a.selectbox('Plot facing',directions,index=directions.index(old.plot.facing) if old else 0)
            marla=b.selectbox('Square feet per marla',[225.,272.25],index=1 if old and old.plot.marla_sqft==272.25 else 0)
            corner=a.checkbox('Corner plot',value=old.plot.corner if old else False)
            family=b.number_input('Family members',min_value=1,max_value=100,value=old.family_size if old else 1)
            budget=a.number_input('Budget PKR',min_value=1.,value=float(old.budget_pkr) if old else 1.)
            qualities=['Grey only','Economy','Standard','Premium','Luxury']
            quality=b.selectbox('Construction quality',qualities,index=qualities.index(old.quality) if old else 2)
            style=a.text_input('Architectural style',value=old.style if old else '')
            start=b.date_input('Intended start date',value=old.start_date if old else today())
            stairs=a.text_input('Stairs position / preference',value=old.stairs_position if old else '')
            parking=b.number_input('Car parking spaces',min_value=0,max_value=20,value=old.car_spaces if old else 0)
            dining=a.text_input('Drawing / dining arrangement',value=old.drawing_dining if old else '')
            accessibility=b.text_input('Accessibility needs (comma separated)',value=', '.join(old.accessibility_needs) if old else '')
            green=a.text_input('Green features (comma separated)',value=', '.join(old.green_features) if old else '')
            lift=a.checkbox('Lift',value=old.lift if old else False)
            lounge=b.checkbox('TV lounge',value=old.tv_lounge if old else False)
            servant=a.checkbox('Servant quarter',value=old.servant_quarter if old else False)
            lawn=b.checkbox('Lawn',value=old.lawn if old else False)
            st.write('Edit floors below; add/delete rows. Levels: basement −1, ground 0, first 1. Review the proposed 3.05 m height or change it.')
            rows=[f.model_dump(include={'id','name','level','height_m','bedrooms','bathrooms','kitchens'}) for f in old.floors] if old else [dict(id='g',name='Ground',level=0,height_m=3.05,bedrooms=0,bathrooms=0,kitchens=0)]
            floors=st.data_editor(rows,num_rows='dynamic',key='gh_floor_entry')
            reviewed=st.checkbox('I checked these form values, including dimensions, floor heights and room counts')
            submitted=st.form_submit_button('Save project draft',type='primary')
        if submitted:
            if not reviewed:st.error('Check the form values and tick the review box first.');return
            try:
                split=lambda s:[x.strip() for x in s.split(',') if x.strip()]
                req=Requirements(city=city.strip(),authority=authority.strip(),plot=Plot(width_m=width*.3048,depth_m=depth*.3048,facing=facing,corner=corner,marla_sqft=marla),
                    floors=[FloorRequest.model_validate({**(next((f.model_dump() for f in old.floors if f.id==row.get('id')), {}) if old else {}),**row}) for row in floors],family_size=family,car_spaces=parking,
                    accessibility_needs=split(accessibility),stairs_position=stairs.strip(),lift=lift,drawing_dining=dining.strip(),tv_lounge=lounge,
                    servant_quarter=servant,lawn=lawn,budget_pkr=budget,quality=quality,style=style.strip(),green_features=split(green),start_date=start,
                    assumptions=old.assumptions if old else [],soil_description=old.soil_description if old else None)
                save_draft(req.model_dump_json());st.rerun()
            except (ValueError,TypeError) as error:st.error('Complete required text and valid floor rows. '+str(error).split('\n')[0])
