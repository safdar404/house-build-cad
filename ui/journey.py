"""One explicit next action, based on reviewed project state rather than a key."""
from schemas import Stage
from ui.state import WorkflowError
from agents.project_context import STAGE_PAGES


def next_action(workspace,session):
    try:workspace.get_output(Stage.REQUIREMENTS)
    except WorkflowError:return 'Enter and confirm house details','pages/requirements_chat.py','Tell us the plot, floors, rooms, budget and priorities. An API key does not create this brief automatically.'
    if workspace.record(Stage.COMPLIANCE).status!='approved':
        return 'Review planning constraints','pages/floor_plans.py','Generate and acknowledge the bylaw evidence review for your confirmed brief.'
    if session.get('gh_planning_envelope') is None:
        return 'Set the concept envelope','pages/floor_plans.py','Enter and review the proposed setbacks before asking the LLM for layouts.'
    if workspace.record(Stage.PLANNING).status!='approved':
        return 'Generate or review floor alternatives','pages/floor_plans.py','Use your connected LLM to create alternatives, then review the geometry.'
    try:workspace.selected_layout()
    except WorkflowError:return 'Choose a floor alternative','pages/floor_plans.py','Select one reviewed alternative to coordinate the drawings and model.'
    for stage in [Stage.CAD,Stage.MODEL,Stage.STRUCTURAL,Stage.MEP,Stage.BIM,Stage.SCHEDULE,Stage.COST,Stage.LABOUR,Stage.TWIN,Stage.REPORT]:
        status=workspace.record(stage).status
        if status!='approved':
            verb='Review' if status=='review' else 'Configure and generate'
            return verb+' '+stage.value.title(),'pages/'+STAGE_PAGES[stage]+'.py','Open this tool, review its inputs and generate the next project output.'
    return 'Download project exports','pages/downloads.py','All stages have reviewed outputs. Download the current package or revise a stage.'
