"""Session-local workflow state, input approvals and stale-output protection.

An approved stage means the user reviewed a concept snapshot; it never signifies
professional engineering or authority approval. No API keys/clients belong here.
"""
from __future__ import annotations

import copy
import hashlib
import json
import numpy as np
from datetime import date, datetime
from dataclasses import dataclass, field, fields, is_dataclass
from typing import Any, MutableMapping

from pydantic import BaseModel

from config import DEPENDENCIES
from schemas import Contract, Project, Requirements, Stage, StageRecord, content_hash

# Conservative invalidation includes optional source links; mandatory execution
# prerequisites reflect what each deterministic tool actually needs.
EDGES={stage:set(children) for stage,children in DEPENDENCIES.items()}
EDGES[Stage.PLANNING].update({Stage.MODEL,Stage.COST,Stage.TWIN,Stage.REPORT})
EDGES[Stage.MODEL].update({Stage.SCHEDULE,Stage.BIM,Stage.REPORT})
EDGES[Stage.STRUCTURAL].add(Stage.REPORT)
EDGES[Stage.MEP].add(Stage.REPORT)
REQUIRED={
    Stage.REQUIREMENTS:(),Stage.COMPLIANCE:(Stage.REQUIREMENTS,),
    Stage.PLANNING:(Stage.REQUIREMENTS,Stage.COMPLIANCE),
    Stage.CAD:(Stage.PLANNING,),Stage.MODEL:(Stage.PLANNING,),
    Stage.STRUCTURAL:(Stage.PLANNING,),Stage.MEP:(Stage.PLANNING,),
    Stage.BIM:(Stage.MODEL,),Stage.SCHEDULE:(Stage.MODEL,),
    Stage.COST:(Stage.PLANNING,),Stage.LABOUR:(Stage.SCHEDULE,Stage.COST),
    Stage.TWIN:(Stage.PLANNING,Stage.SCHEDULE),Stage.REPORT:(Stage.PLANNING,),
}


class WorkflowError(ValueError):
    """Actionable state conflict without private payloads."""


def output_hash(value: Any) -> str:
    """Hash typed results, binary exports and mesh geometry without serialization to disk."""
    def normalize(item):
        if isinstance(item,BaseModel):
            return item.model_dump(mode='json')
        if isinstance(item,np.ndarray):
            return normalize(item.tolist())
        if isinstance(item,np.generic):
            return normalize(item.item())
        if isinstance(item,(date,datetime)):
            return item.isoformat()
        if isinstance(item,bytes):
            return {'binary_sha256':hashlib.sha256(item).hexdigest(),'size':len(item)}
        # trimesh objects are deliberately represented by geometry and metadata,
        # not by unstable repr(), executable pickle or process addresses.
        if hasattr(item,'vertices') and hasattr(item,'faces'):
            return {'vertices':item.vertices.tolist(),'faces':item.faces.tolist(),
                    'metadata':normalize(item.metadata)}
        if is_dataclass(item):
            return {f.name:normalize(getattr(item,f.name)) for f in fields(item)}
        if isinstance(item,dict):
            return {str(k):normalize(v) for k,v in item.items()}
        if isinstance(item,(tuple,list)):
            return [normalize(v) for v in item]
        if item is None or isinstance(item,(str,int,float,bool)):
            return item
        raise WorkflowError('Unsupported workflow output type; supply a stable fingerprint adapter.')
    return content_hash({'value':normalize(value)})


@dataclass
class WorkspaceState:
    project: Project = field(default_factory=Project)
    outputs: dict[Stage,Any] = field(default_factory=dict,repr=False)
    authorized_inputs: dict[Stage,str] = field(default_factory=dict)
    source_hashes: dict[Stage,dict[Stage,str]] = field(default_factory=dict)
    revision_notes: dict[Stage,str] = field(default_factory=dict)
    # Application-controlled fingerprints may be supplied for specialized outputs.
    _fingerprinters: dict[Stage,Any] = field(default_factory=dict,repr=False)
    _input_requests: dict[Stage,Contract] = field(default_factory=dict,repr=False)

    def record(self,stage: Stage) -> StageRecord:
        return self.project.stages.setdefault(stage,StageRecord())

    def affected(self,stage: Stage) -> set[Stage]:
        found=set();pending=[stage]
        while pending:
            current=pending.pop()
            if current not in found:
                found.add(current);pending.extend(EDGES[current])
        return found

    def invalidate(self,stage: Stage) -> None:
        """Keep old artifacts internally for review, but immediately block their use/download."""
        for current in self.affected(stage):
            record=self.record(current)
            record.status='stale' if current in self.outputs else 'pending'
            record.revision+=1;record.message='Inputs changed; regenerate and review this stage.'
            self.authorized_inputs.pop(current,None)
        if Stage.PLANNING in self.affected(stage):
            # Project validators require clearing selection before alternatives.
            self.project.selected_layout_id=None
            self.project.alternatives=[]

    def authorize(self,stage: Stage,request: Contract,*,reviewed_hash: str,
                  user_approved: bool=False) -> str:
        fingerprint=content_hash(request)
        if not user_approved or fingerprint!=reviewed_hash:
            raise WorkflowError('Review the current stage inputs before authorizing generation.')
        previous=self.record(stage).input_hash
        if previous is not None and previous!=fingerprint:
            self.invalidate(stage)
        self.authorized_inputs[stage]=fingerprint
        return fingerprint

    def ensure_ready(self,stage: Stage,request: Contract) -> None:
        if self.record(stage).status=='running':
            raise WorkflowError('This stage is already running.')
        if self.authorized_inputs.get(stage)!=content_hash(request):
            raise WorkflowError('Current inputs require user review before generation.')
        for dependency in REQUIRED[stage]:
            self.get_output(dependency)

    def get_output(self,stage: Stage) -> Any:
        record=self.record(stage)
        if record.status!='approved' or stage not in self.outputs:
            raise WorkflowError('Required source stage is not approved or is stale: '+stage.value)
        if stage==Stage.REQUIREMENTS and (self.project.requirements is None or
            content_hash(self.project.requirements)!=content_hash(self.outputs[stage])):
            self.invalidate(stage)
            raise WorkflowError('The project brief changed outside its reviewed source stage.')
        fingerprinter=self._fingerprinters.get(stage,output_hash)
        if fingerprinter(self.outputs[stage])!=record.output_hash:
            self.invalidate(stage)
            raise WorkflowError('A source output changed in memory. Regenerate and review it.')
        for upstream,expected in self.source_hashes.get(stage,{}).items():
            self.get_output(upstream)
            if self.record(upstream).output_hash!=expected:
                self.invalidate(stage)
                raise WorkflowError('Upstream revision changed. Regenerate the dependent stage.')
        return self.outputs[stage]

    def start(self,stage: Stage,request: Contract) -> None:
        self.ensure_ready(stage,request)
        # Regeneration invalidates all downstream outputs, even if inputs match.
        authorization=self.authorized_inputs[stage]
        self.invalidate(stage);self.authorized_inputs[stage]=authorization
        self._input_requests[stage]=request.model_copy(deep=True)
        record=self.record(stage);record.input_hash=content_hash(request)
        record.status='running';record.message='Generating '+stage.value+'...'
        # Capture approved upstream outputs only. Never capture downstream outputs.
        ancestors={s for s in Stage if s!=stage and stage in self.affected(s)}
        self.source_hashes[stage]={s:self.record(s).output_hash for s in ancestors
            if self.record(s).status=='approved' and s in self.outputs}

    def complete(self,stage: Stage,request: Contract,result: Any,*,fingerprinter=None) -> str:
        record=self.record(stage)
        if record.status!='running' or record.input_hash!=content_hash(request):
            raise WorkflowError('Stage inputs changed during generation; discard the result.')
        function=fingerprinter or output_hash
        fingerprint=function(result)
        self.outputs[stage]=copy.deepcopy(result)
        self._fingerprinters[stage]=function
        record.output_hash=fingerprint;record.status='review';record.message='Review generated '+stage.value+'.'
        return fingerprint

    def fail(self,stage: Stage) -> None:
        self.record(stage).status='failed'
        self.record(stage).message='Generation failed. Review inputs before retrying.'

    def approve(self,stage: Stage,*,reviewed_hash: str,user_approved: bool=False) -> None:
        record=self.record(stage)
        if not user_approved or record.status!='review' or reviewed_hash!=record.output_hash:
            raise WorkflowError('Review the current output before approving this stage.')
        if self._fingerprinters[stage](self.outputs[stage])!=reviewed_hash:
            self.invalidate(stage);raise WorkflowError('Output changed after review.')
        for upstream,expected in self.source_hashes.get(stage,{}).items():
            self.get_output(upstream)
            if self.record(upstream).output_hash!=expected:
                raise WorkflowError('A source stage changed after generation.')
        if stage==Stage.REQUIREMENTS:
            brief=Requirements.model_validate(self.outputs[stage].model_dump(mode='json'))
            self.project.requirements=brief
        record.status='approved';record.message='Concept output reviewed by user.'

    def selected_layout(self):
        planning=self.get_output(Stage.PLANNING)
        selected=self.project.selected_layout_id
        approved=next((a.layout for a in planning.alternatives if a.layout.id==selected),None)
        saved=next((a for a in self.project.alternatives if a.id==selected),None)
        if approved is None or saved is None or content_hash(approved)!=content_hash(saved):
            raise WorkflowError('Select a current reviewed planning alternative before continuing.')
        return saved.model_copy(deep=True)

    def select_layout(self,option,requirements,envelope,*,reviewed_hash: str,user_approved: bool=False):
        """Select an alternative from the approved PlanningOutput; preserve access metadata."""
        from agents.planning_agent import PlanningAgent
        planning=self.get_output(Stage.PLANNING)
        if content_hash(requirements)!=content_hash(self.get_output(Stage.REQUIREMENTS)):
            raise WorkflowError('Layout selection uses a different project brief.')
        prepared=self._input_requests.get(Stage.PLANNING)
        if prepared is not None:
            payload=json.loads(prepared.payload_json) if hasattr(prepared,'payload_json') else prepared.model_dump(mode='json')
            if 'envelope' in payload and content_hash(payload['envelope'])!=content_hash(envelope):
                raise WorkflowError('Planning envelope differs from the reviewed generation inputs.')
        matching=[a for a in planning.alternatives if content_hash(a)==content_hash(option)]
        if not matching: raise WorkflowError('Alternative is absent from the approved planning output.')
        layout=PlanningAgent.select(option,requirements,envelope,reviewed_hash=reviewed_hash,user_approved=user_approved)
        if self.project.selected_layout_id!=layout.id:
            for downstream in EDGES[Stage.PLANNING]:
                self.invalidate(downstream)
        self.project.alternatives=[a.layout.model_copy(deep=True) for a in planning.alternatives]
        self.project.selected_layout_id=layout.id
        return layout

    def public_status(self) -> dict:
        """Small state description for the model: no raw outputs, keys or binary exports."""
        return {'project_id':self.project.id,'selected_layout_id':self.project.selected_layout_id,
                'stages':{s.value:{'status':self.record(s).status,'revision':self.record(s).revision,
                                   'input_authorized':s in self.authorized_inputs} for s in Stage}}


def get_workspace(session: MutableMapping[str,Any]) -> WorkspaceState:
    """Pass st.session_state; no module-global cache or cross-user state."""
    if 'gharbuilder_workspace' not in session:
        session['gharbuilder_workspace']=WorkspaceState()
    workspace=session['gharbuilder_workspace']
    if not isinstance(workspace,WorkspaceState):
        raise WorkflowError('Invalid session workspace. Restart this session.')
    return workspace
