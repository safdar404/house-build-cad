"""Typed table and calendar editors used in place of mandatory JSON entry."""
from datetime import date,datetime
import math
import pandas as pd
import streamlit as st
from tools.schedule_4d import WorkCalendar

DAYS=['Monday','Tuesday','Wednesday','Thursday','Friday','Saturday','Sunday']


def records(value):
    rows=value.to_dict('records') if hasattr(value,'to_dict') else value
    def clean(v):
        if v is None or v is pd.NaT or isinstance(v,float) and math.isnan(v):return None
        if isinstance(v,datetime):return v.date().isoformat()
        if isinstance(v,date):return v.isoformat()
        return v
    return [{k:clean(v) for k,v in row.items()} for row in rows if any(clean(v) is not None and clean(v)!='' for v in row.values())]


def table(label,rows,columns,*,key,config=None,disabled=None):
    st.write('**'+label+'**')
    frame=pd.DataFrame(rows,columns=columns)
    configuration=dict(config or {})
    for name in columns:
        field=name.split('.')[-1]
        if field=='verified':configuration.setdefault(name,st.column_config.CheckboxColumn('Evidence verified',default=False))
        if field=='quality':
            from schemas import Quality
            configuration.setdefault(name,st.column_config.SelectboxColumn('Quality',options=[v.value for v in Quality]))
        if field=='trade':
            from typing import get_args
            from tools.labour import Trade
            configuration.setdefault(name,st.column_config.SelectboxColumn('Trade',options=list(get_args(Trade))))
        if field in {'value_pkr','daily_wage_pkr','grey_pkr_sqft','finishing_pkr_sqft','multiplier','input_usd_per_million','cached_input_usd_per_million','output_usd_per_million'}:
            frame[name]=pd.to_numeric(frame[name],errors='coerce')
            configuration.setdefault(name,st.column_config.NumberColumn(name.replace('_',' ').title(),min_value=0.))
        if name.split('.')[-1] in {'effective_date','start','end_inclusive','valid_until','reviewed_on'}:
            frame[name]=pd.to_datetime(frame[name],errors='coerce').dt.date
            configuration.setdefault(name,st.column_config.DateColumn(name.replace('_',' ').title()))
    return records(st.data_editor(frame,num_rows='dynamic',hide_index=True,key=key,
        column_config=configuration,disabled=disabled or []))


def parsed_rows(schema,rows):
    output=[]
    for row in rows:
        values={k:v for k,v in row.items() if v is not None or k not in schema.model_fields or schema.model_fields[k].is_required() or schema.model_fields[k].default is None}
        output.append(schema.model_validate(values))
    return output


def calendar_editor(current,*,key):
    days=st.multiselect('Working weekdays',DAYS,default=[DAYS[d] for d in current.working_weekdays],key=key+'_days')
    st.caption('Add only confirmed holiday or reduced-productivity periods. Factor 0 means no work; factor 1 means normal productivity. Dates use YYYY-MM-DD.')
    rows=table('Calendar exceptions',[r.model_dump(mode='json') for r in current.exceptions],
        ['name','start','end_inclusive','productivity_factor','source'],key=key+'_exceptions',
        config={'productivity_factor':st.column_config.NumberColumn('Productivity factor',min_value=0.,max_value=1.)})
    return WorkCalendar(working_weekdays=[DAYS.index(day) for day in days],exceptions=rows)


def flatten(row,prefix=''):
    result={}
    for key,value in row.items():
        name=prefix+key
        if isinstance(value,dict):result.update(flatten(value,name+'.'))
        else:result[name]=value
    return result


def unflatten(row):
    result={}
    for key,value in row.items():
        cursor=result;parts=key.split('.')
        for part in parts[:-1]:cursor=cursor.setdefault(part,{})
        cursor[parts[-1]]=value
    return result


def config_form(data,*,key):
    """Edit existing nested profiles and flat record lists; full schema stays validated on save."""
    result=dict(data)
    for name,value in data.items():
        label=name.replace('_',' ').title()
        widget=key+'_'+name
        if isinstance(value,list):
            if name=='working_weekdays':
                picked=st.multiselect('Working weekdays',DAYS,default=[DAYS[d] for d in value],key=widget)
                result[name]=[DAYS.index(d) for d in picked]
            elif value and isinstance(value[0],dict) and any(isinstance(v,list) for row in value for v in row.values()):
                index=st.selectbox(label+' to edit',list(range(len(value))),format_func=lambda i:str(value[i].get('id',i+1)),key=widget)
                with st.expander('Edit '+label,expanded=True):
                    edited=list(value);edited[index]=config_form(value[index],key=widget+'_'+str(index));result[name]=edited
            else:
                templates={'prices':['model','input_usd_per_million','cached_input_usd_per_million','output_usd_per_million','evidence.source','evidence.effective_date','evidence.source_url','evidence.verified','evidence.verified_by','evidence.notes'],
                    'exceptions':['name','start','end_inclusive','productivity_factor','source']}
                flat=[flatten(r) for r in value]
                columns=list(dict.fromkeys(k for row in flat for k in row)) if flat else templates.get(name,[])
                if columns:result[name]=[unflatten(row) for row in table(label,flat,columns,key=widget)]
                else:st.caption(label+': no records. Use advanced JSON to introduce a new record type.')
        elif isinstance(value,dict):result[name]=config_form(value,key=widget)
        elif name in {'schema_version','currency'}:st.caption(label+': '+str(value))
        elif name in {'last_updated','effective_from'} and value:
            result[name]=st.date_input(label,value=date.fromisoformat(value),key=widget).isoformat()
        elif isinstance(value,bool):result[name]=st.checkbox(label,value=value,key=widget)
        elif isinstance(value,(float,int)):
            result[name]=st.number_input(label,value=value,key=widget)
        elif value is None:
            if name=='corner':
                result[name]=st.selectbox(label,[None,True,False],format_func=lambda v:'Any / not specified' if v is None else 'Corner plot' if v else 'Non-corner plot',key=widget)
            elif name in {'valid_until','reviewed_on','effective_date'}:
                picked=st.date_input(label+' (optional)',value=None,key=widget);result[name]=picked.isoformat() if picked else None
            elif name in {'plot_max_m2'}:result[name]=st.number_input(label+' (optional)',value=None,min_value=0.,key=widget)
            else:st.caption(label+': not supplied. Use advanced JSON to set this optional field.')
        else:result[name]=st.text_area(label,value=str(value),key=widget) if name=='notes' else st.text_input(label,value=str(value),key=widget)
    return result


def schema_inputs(schema,*,key,current=None):
    """Guided numerical assumptions, with unknowns left unset until supplied."""
    from ui.choices import source_choice
    data=dict(current or {});properties=schema.model_json_schema()['properties'];columns=st.columns(3);count=0
    for name,prop in properties.items():
        label=name.replace('_',' ').title()
        if name=='source':data[name]=source_choice(label,current=data.get(name),key=key+'_source');continue
        if prop.get('type')=='boolean':data[name]=st.checkbox(label,value=bool(data.get(name,False)),key=key+'_'+name);continue
        if name=='cooled_room_kinds':
            data[name]=st.multiselect('Rooms included in cooling allowance',['bedroom','lounge','drawing','dining','kitchen','other'],default=data.get(name,[]),key=key+'_'+name);continue
        if name=='appliances':
            data[name]=table('Supplied appliance allowances',data.get(name,[]),['name','quantity','watts_each','hours_per_day','demand_factor'],key=key+'_appliances');continue
        if prop.get('type') in {'number','integer'}:
            integer=prop['type']=='integer';value=data.get(name)
            if value is not None:value=int(value) if integer else float(value)
            data[name]=columns[count%3].number_input(label,value=value,min_value=0 if integer else 0.,
                step=1 if integer else .1,key=key+'_'+name,help='Enter the supplied assumption; leave unset if unknown. Units are shown in the field name.')
            count+=1
    return schema.model_validate(data)


def fill_missing_recipes(rows,productive_days=None,crew_size=None,curing_days=None):
    supplied={'productive_days':productive_days,'crew_size':crew_size,'curing_days':curing_days}
    return [{**row,**{key:value for key,value in supplied.items() if value is not None and row.get(key) is None}} for row in rows]
