"""Local provider with optional Git-derived ref/SHA/repository metadata."""
from __future__ import annotations
import os,subprocess,sys
from pathlib import Path
from urllib.parse import urlparse
from typing import Mapping
from ...core.cli import main as core_main  # noqa: E402
from ...core.provider import ProviderAdapter  # noqa: E402
def _git(root:Path,*args:str)->str:
    r=subprocess.run(["git",*args],cwd=root,stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,text=True,check=False)
    return r.stdout.strip() if r.returncode==0 else ""
def _repo(root:Path)->str:
    remote=_git(root,"remote","get-url","origin").removesuffix(".git")
    if remote.startswith("git@") and ":" in remote:return remote.split(":",1)[1]
    return urlparse(remote).path.lstrip("/") if remote else ""
class LocalAdapter:
    name="local"
    def normalize_environment(self,environ:Mapping[str,str])->dict[str,str]:
        root=Path(environ.get("PIPELINE_WORKSPACE",environ.get("PWD","."))).resolve()
        v={"PIPELINE_PROVIDER":"local","PIPELINE_EVENT":environ.get("PIPELINE_EVENT","manual"),
           "PIPELINE_REF_TYPE":environ.get("PIPELINE_REF_TYPE",""),"PIPELINE_REF_NAME":environ.get("PIPELINE_REF_NAME",""),
           "PIPELINE_SHA":environ.get("PIPELINE_SHA",""),"PIPELINE_REPOSITORY":environ.get("PIPELINE_REPOSITORY",""),
           "PIPELINE_WORKSPACE":str(root),"PIPELINE_ARTIFACT_DIR":environ.get("PIPELINE_ARTIFACT_DIR",str(root/".pipeline-artifacts")),
           "PIPELINE_OUTPUT_FILE":environ.get("PIPELINE_OUTPUT_FILE",""),"PIPELINE_RUN_ID":environ.get("PIPELINE_RUN_ID",""),
           "PIPELINE_RUN_ATTEMPT":environ.get("PIPELINE_RUN_ATTEMPT","1")}
        if not v["PIPELINE_SHA"]:v["PIPELINE_SHA"]=_git(root,"rev-parse","HEAD")
        if not v["PIPELINE_REF_TYPE"]:
            tag=_git(root,"describe","--tags","--exact-match","HEAD");branch=_git(root,"branch","--show-current")
            if tag:v["PIPELINE_REF_TYPE"],v["PIPELINE_REF_NAME"]="tag",tag
            elif branch:v["PIPELINE_REF_TYPE"],v["PIPELINE_REF_NAME"]="branch",branch
        if not v["PIPELINE_REPOSITORY"]:v["PIPELINE_REPOSITORY"]=_repo(root)
        return v
def main(argv:list[str]|None=None)->int:
    os.environ.update(LocalAdapter().normalize_environment(os.environ))
    return core_main(list(sys.argv[1:] if argv is None else argv))
if __name__=="__main__":raise SystemExit(main())
