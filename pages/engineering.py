"""Preliminary structural and MEP assumptions: no final engineering design."""
from __future__ import annotations
import json
import streamlit as st
from schemas import Stage
from agents.structural_agent import StructuralAgent,StructuralInput,SectionAssumptions,STRUCTURAL_NOTICE
from agents.mep_agent import MEPAgent,MEPInput,MEPAssumptions
from ui.components import back_to_home,hero,render_review_gate
from ui.workflow import selected_context,generation_control
from ui.state import WorkflowError
from ui.editors import schema_inputs


def main():
    back_to_home();hero('🔧 Engineering allowances','Preliminary structural coordination and explicit MEP estimation inputs.')
    try:workspace,req,layout,option,envelope=selected_context()
    except WorkflowError as error:st.info(str(error));return
    structural_tab,mep_tab=st.tabs(['Structural coordination','MEP allowances'])
    with structural_tab:
        st.warning(STRUCTURAL_NOTICE)
        spacing=st.number_input('Preferred grid spacing m (planning preference, not permissible span)',min_value=.5,max_value=20.,value=4.,step=.25)
        soil=st.selectbox('Reported soil category',['unknown','reported_competent','reported_soft_or_fill'])
        section_mode=st.radio('Structural information available',['Coordination only – section sizes unknown','I have supplied section assumptions','Advanced section JSON'])
        try:
            sections=None
            if section_mode=='I have supplied section assumptions':
                sections=schema_inputs(SectionAssumptions,key='gh_section_fields')
            elif section_mode=='Advanced section JSON':
                sizes=st.text_area('Optional supplied section assumptions JSON',value='null',height=130)
                data=json.loads(sizes);sections=SectionAssumptions.model_validate(data) if data is not None else None
            request=StructuralInput(requirements=req,layout=layout,envelope=envelope,access=option.access,
                preferred_grid_spacing_m=spacing,sections=sections,soil_category=soil)
            generation_control(Stage.STRUCTURAL,request,StructuralAgent.evaluate,'Generate preliminary coordination report')
        except (ValueError,TypeError):st.info('Complete the supplied section fields and source, or choose coordination-only mode to keep sizes unknown.')
        if workspace.record(Stage.STRUCTURAL).status in {'review','approved'}:
            report=workspace.outputs[Stage.STRUCTURAL]
            st.dataframe([r.model_dump() for r in report.floor_allowances],hide_index=True)
            for note in report.warnings:st.write(note)
            render_review_gate(Stage.STRUCTURAL)
    with mep_tab:
        st.caption('Supply coefficients, appliance scope and water/solar assumptions. These are not code-prescribed values. Detailed circuit, gas, pipe and HVAC design is excluded.')
        previous=getattr(workspace._input_requests.get(Stage.MEP),'assumptions',None)
        mode=st.radio('MEP input method',['Not supplied – professional review required','Guided assumption fields','Advanced JSON'],index=1 if previous else 0)
        st.caption('No engineering coefficients are prefilled. Use the values supplied by your MEP professional; required values cannot be guessed.')
        try:
            assumptions=None
            if mode=='Not supplied – professional review required':st.info('MEP values remain unknown. You can continue with modelling, BIM and other available tools, then return with supplied coefficients.')
            elif mode=='Guided assumption fields':assumptions=schema_inputs(MEPAssumptions,key='gh_mep_fields',current=previous.model_dump(mode='json') if previous else None)
            else:
                text=st.text_area('MEP assumptions JSON',value='{}',height=260)
                assumptions=MEPAssumptions.model_validate_json(text)
            if assumptions is not None:
                request=MEPInput(requirements=req,layout=layout,envelope=envelope,access=option.access,assumptions=assumptions)
                generation_control(Stage.MEP,request,MEPAgent.evaluate,'Calculate indicative MEP allowances')
        except ValueError:st.info('Complete the numerical MEP fields, source and acceptance before calculation. If these values are not available, continue with the other design tools and return after professional review.')
        if workspace.record(Stage.MEP).status in {'review','approved'}:
            report=workspace.outputs[Stage.MEP]
            st.dataframe([r.model_dump() for r in report.rooms],hide_index=True)
            for note in report.unresolved:st.write(note)
            render_review_gate(Stage.MEP)

    st.page_link('pages/model_3d.py',label='Continue to 3D modelling',icon='➡️')
    st.page_link('pages/bim_ifc.py',label='Continue to BIM when the model is approved',icon='➡️')

main()
