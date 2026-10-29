"""Choice controls with typed custom entries; no generated facts or rates."""
import streamlit as st

CITIES=['Lahore','Islamabad','Rawalpindi','Karachi','Faisalabad','Multan','Vehari','Peshawar','Quetta','Other / authority to be confirmed']
AUTHORITIES=['LDA','CDA','RDA','SBCA','PHATA','DHA','Bahria Town','Local municipal authority','Not sure – authority verification required']
STYLES=['Modern','Contemporary','Minimalist','Traditional','Courtyard house','Islamic-inspired','Colonial-inspired','Architect to advise']
STAIRS=['Front right','Front left','Centre','Rear right','Rear left','External / separate access','Architect to advise']
DINING=['Separate drawing and dining','Combined drawing / dining','Drawing room only','Dining space only','Open-plan lounge and dining','Architect to advise']
ACCESS=['Step-free entrance','Wheelchair access','Accessible bathroom','Ground-floor bedroom for elderly family','Wider doors / circulation','Lift access']
GREEN=['Solar panels','Rainwater harvesting','Natural cross-ventilation','Daylight optimisation','Roof / wall insulation','Water-efficient fixtures','Greywater reuse']
SOURCES=['User-provided scenario (unverified)','Contractor-provided estimate / programme','Architect / engineer-provided information','Dated supplier quotation','Site measurement / progress record','Authority document – reference required']


def choose(container,label,options,current=None,*,key=None,placeholder='Choose an option or type your own'):
    options=list(dict.fromkeys([*options,*([current] if current and current not in options else [])]))
    return container.selectbox(label,options,index=options.index(current) if current in options else None,
        accept_new_options=True,placeholder=placeholder,key=key) or ''


def multi(container,label,options,current=None,*,key=None):
    current=list(current or []);choices=list(dict.fromkeys([*options,*current]))
    return container.multiselect(label,choices,default=current,accept_new_options=True,key=key,
        placeholder='None selected – select any that apply, or type your own')


def source_choice(label,*,current=None,key=None):
    return choose(st,label,SOURCES,current,key=key,placeholder='Select the source type or enter the actual reference')
