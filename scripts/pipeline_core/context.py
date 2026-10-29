"""Portable context. Core reads only PIPELINE_* variables."""
from __future__ import annotations
import os,re
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping
_PROVIDER=re.compile(r"^[a-z][a-z0-9_-]*$")
@dataclass(frozen=True)
class PipelineContext:
    provider:str
    event:str
    ref_type:str
    ref_name:str
    sha:str
    repository:str
    workspace:Path
    artifact_dir:Path
    output_file:Path|None=None
    run_id:str=""
    attempt:str=""
    @classmethod
    def from_environment(cls,environ:Mapping[str,str]|None=None,*,workspace:str|Path|None=None)->"PipelineContext":
        env=os.environ if environ is None else environ
        root=Path(workspace or env.get("PIPELINE_WORKSPACE") or Path.cwd()).expanduser().resolve()
        provider=(env.get("PIPELINE_PROVIDER") or "local").lower().strip()
        if not _PROVIDER.fullmatch(provider): raise ValueError(f"Invalid PIPELINE_PROVIDER: {provider!r}")
        ad=env.get("PIPELINE_ARTIFACT_DIR","").strip(); out=env.get("PIPELINE_OUTPUT_FILE","").strip()
        return cls(provider,env.get("PIPELINE_EVENT",""),env.get("PIPELINE_REF_TYPE",""),env.get("PIPELINE_REF_NAME",""),
                   env.get("PIPELINE_SHA",""),env.get("PIPELINE_REPOSITORY",""),root,
                   Path(ad).expanduser().resolve() if ad else root/".pipeline-artifacts",
                   Path(out).expanduser().resolve() if out else None,env.get("PIPELINE_RUN_ID",""),env.get("PIPELINE_RUN_ATTEMPT",""))
    def to_environment(self)->dict[str,str]:
        return {"PIPELINE_PROVIDER":self.provider,"PIPELINE_EVENT":self.event,"PIPELINE_REF_TYPE":self.ref_type,
        "PIPELINE_REF_NAME":self.ref_name,"PIPELINE_SHA":self.sha,"PIPELINE_REPOSITORY":self.repository,
        "PIPELINE_WORKSPACE":str(self.workspace),"PIPELINE_ARTIFACT_DIR":str(self.artifact_dir),
        "PIPELINE_OUTPUT_FILE":str(self.output_file) if self.output_file else "",
        "PIPELINE_RUN_ID":self.run_id,"PIPELINE_RUN_ATTEMPT":self.attempt}
    def to_dict(self)->dict[str,str]:
        return {"provider":self.provider,"event":self.event,"ref_type":self.ref_type,"ref_name":self.ref_name,
        "sha":self.sha,"repository":self.repository,"workspace":str(self.workspace),"artifact_dir":str(self.artifact_dir),
        "output_file":str(self.output_file) if self.output_file else "","run_id":self.run_id,"attempt":self.attempt}
