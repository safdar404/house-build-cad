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


def main():
    back_to_home();hero('🔧 Engineering allowances','Preliminary structural coordination and explicit MEP estimation inputs.')
    try:workspace,req,layout,option,envelope=selected_context()
    except WorkflowError as error:st.info(str(error));return
    structural_tab,mep_tab=st.tabs(['Structural coordination','MEP allowances'])
    with structural_tab:
        st.warning(STRUCTURAL_NOTICE)
        spacing=st.number_input('Preferred grid spacing m (planning preference, not permissible span)',min_value=.5,max_value=20.,value=4.,step=.25)
        soil=st.selectbox('Reported soil category',['unknown','reported_competent','reported_soft_or_fill'])
        sizes=st.text_area('Optional supplied section assumptions JSON',value='null',height=130,
            help='Leave null when sizes are unknown. No concrete volume is returned without accepted supplied sizes.')
        st.json(SectionAssumptions.model_json_schema(),expanded=False)
        try:
            data=json.loads(sizes);sections=SectionAssumptions.model_validate(data) if data is not None else None
            request=StructuralInput(requirements=req,layout=layout,envelope=envelope,access=option.access,
                preferred_grid_spacing_m=spacing,sections=sections,soil_category=soil)
            generation_control(Stage.STRUCTURAL,request,StructuralAgent.evaluate,'Generate preliminary coordination report')
        except (ValueError,TypeError):st.info('Correct the optional section JSON before calculation.')
        if workspace.record(Stage.STRUCTURAL).status in {'review','approved'}:
            report=workspace.outputs[Stage.STRUCTURAL]
            st.dataframe([r.model_dump() for r in report.floor_allowances],hide_index=True)
            for note in report.warnings:st.write(note)
            render_review_gate(Stage.STRUCTURAL)
    with mep_tab:
        st.caption('Supply coefficients, appliance scope and water/solar assumptions. These are not code-prescribed values. Detailed circuit, gas, pipe and HVAC design is excluded.')
        text=st.text_area('MEP assumptions JSON',value='{}',height=260)
        st.json(MEPAssumptions.model_json_schema(),expanded=False)
        try:
            assumptions=MEPAssumptions.model_validate_json(text)
            request=MEPInput(requirements=req,layout=layout,envelope=envelope,access=option.access,assumptions=assumptions)
            generation_control(Stage.MEP,request,MEPAgent.evaluate,'Calculate indicative MEP allowances')
        except ValueError:st.info('Provide all MEP assumptions, including their source and acceptance, before calculation.')
        if workspace.record(Stage.MEP).status in {'review','approved'}:
            report=workspace.outputs[Stage.MEP]
            st.dataframe([r.model_dump() for r in report.rooms],hide_index=True)
            for note in report.unresolved:st.write(note)
            render_review_gate(Stage.MEP)

main()
