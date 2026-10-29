"""Build a reviewed report and consolidated geometry package from current stages."""
from __future__ import annotations
import streamlit as st
from agents.report_agent import ReportAgent
from schemas import Stage,content_hash
from tools.report import ReportInput,ExportAttachment,report_fingerprint
from agents.modeling_agent import ModelingAgent
from ui.components import back_to_home,hero,render_review_gate,tr
from ui.workflow import selected_context,approved_output,generation_control,today
from ui.state import WorkflowError


def main():
    back_to_home();hero('📦 '+tr('downloads'),'Combine only current reviewed stages and supplied geometry exports.')
    try:workspace,req,layout,option,envelope=selected_context()
    except WorkflowError as error:st.info(str(error));return
    stages={'cost':Stage.COST,'schedule':Stage.SCHEDULE,'labour':Stage.LABOUR,
            'monitoring':Stage.TWIN,'structural':Stage.STRUCTURAL,'mep':Stage.MEP}
    values={name:approved_output(stage) for name,stage in stages.items()}
    st.dataframe([{'Stage':name,'Included':value is not None} for name,value in values.items()],hide_index=True)
    st.caption('Unreviewed, stale and absent stages are excluded. A partial package is not represented as completed design work.')
    attachments=[]
    cad=approved_output(Stage.CAD);model=approved_output(Stage.MODEL);bim=approved_output(Stage.BIM)
    if cad:attachments.append(ExportAttachment('Drawings.zip',cad.archive_bytes))
    if model:
        export_key='gh_report_mesh_'+model.input_hash
        if export_key not in st.session_state:st.session_state[export_key]=ModelingAgent.export(model)
        attachments.append(ExportAttachment('Meshes.zip',st.session_state[export_key]))
    if bim:attachments.append(ExportAttachment(bim.filename,bim.content))
    date_report=st.date_input('Report date',value=today())
    kwargs={name:value for name,value in values.items()}
    kwargs.update({name+'_hash':content_hash(value) if value is not None else None for name,value in values.items()})
    request=ReportInput(project_name=workspace.project.name,report_date=date_report,requirements=req,layout=layout,
                        reviewed_layout_hash=content_hash(layout),**kwargs)
    st.write('Geometry attachments: '+(', '.join(a.name for a in attachments) or 'none'))
    st.caption('PDF text currently supports Latin/English labels. Excel preserves Unicode. Overview values are report snapshots; re-run the app after edits.')
    # Attachment bytes are bound into a typed wrapper so input approval covers the
    # exact export set, as well as report metadata and source-stage hashes.
    from schemas import Contract
    class BoundReport(Contract):
        report_json: str
        export_digest: str
    bound=BoundReport(report_json=request.model_dump_json(),export_digest=report_fingerprint(request,attachments))
    generation_control(Stage.REPORT,bound,lambda v:ReportAgent.generate(request,attachments,
        reviewed_hash=report_fingerprint(request,attachments),user_approved=True),'Generate report and complete available exports')
    render_review_gate(Stage.REPORT)
    result=approved_output(Stage.REPORT)
    if result:
        columns=st.columns(3)
        columns[0].download_button('PDF report',result.pdf_bytes,file_name='GharBuilder_Report.pdf',mime='application/pdf')
        columns[1].download_button('Excel BOQ',result.xlsx_bytes,file_name='GharBuilder_BOQ.xlsx',mime='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
        columns[2].download_button('All available exports ZIP',result.zip_bytes,file_name='GharBuilder_Project_Exports.zip',mime='application/zip')
    st.download_button('Project review metadata JSON',workspace.project.model_dump_json(indent=2),
        file_name='GharBuilder_Project_Metadata.json',mime='application/json',help='No API key or binary models. This is not a complete session backup.')

main()
