"""Generate the synthetic 10-marla G+2 export package without an API key."""
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from tools.demo import build_sample
from schemas import Stage

if __name__=='__main__':
    state,inputs=build_sample(include_reports=True,progress=print)
    target=Path(__file__).resolve().parent/'sample_outputs'
    target.mkdir(exist_ok=True)
    result=state.outputs[Stage.REPORT]
    (target/'GharBuilder_Demonstration_Exports.zip').write_bytes(result.zip_bytes)
    (target/'GharBuilder_Demonstration_Report.pdf').write_bytes(result.pdf_bytes)
    (target/'GharBuilder_Demonstration_BOQ.xlsx').write_bytes(result.xlsx_bytes)
    (target/'sample_project.json').write_text(state.project.model_dump_json(indent=2),encoding='utf-8')
    print('Synthetic sample exports written to',target)
