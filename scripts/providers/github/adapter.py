"""Translate GitHub Actions variables into the portable PIPELINE_* contract."""
from __future__ import annotations
import os,re,sys
from pathlib import Path
from typing import Mapping
SCRIPTS_ROOT=Path(__file__).resolve().parents[2]
if str(SCRIPTS_ROOT) not in sys.path:sys.path.insert(0,str(SCRIPTS_ROOT))
from pipeline_core.provider import ProviderAdapter  # noqa: E402

def _ref_parts(source:Mapping[str,str])->tuple[str,str]:
    kind=source.get("GITHUB_REF_TYPE","");name=source.get("GITHUB_REF_NAME","");ref=source.get("GITHUB_REF","")
    if not kind:
        if ref.startswith("refs/tags/"):kind="tag"
        elif ref.startswith("refs/heads/"):kind="branch"
        elif ref.startswith("refs/pull/"):kind="pull_request"
    if not name:
        if ref.startswith("refs/tags/"):name=ref.removeprefix("refs/tags/")
        elif ref.startswith("refs/heads/"):name=ref.removeprefix("refs/heads/")
        elif ref.startswith("refs/pull/"):name=ref.split("/")[2] if len(ref.split("/"))>2 else ref
    return kind,name

class GitHubAdapter:
    name="github"
    def normalize_environment(self,environ:Mapping[str,str])->dict[str,str]:
        workspace=str(Path(environ.get("GITHUB_WORKSPACE",environ.get("PWD","."))).resolve());kind,name=_ref_parts(environ)
        return {"PIPELINE_PROVIDER":"github","PIPELINE_EVENT":environ.get("GITHUB_EVENT_NAME",""),
            "PIPELINE_REF_TYPE":kind,"PIPELINE_REF_NAME":name,"PIPELINE_SHA":environ.get("GITHUB_SHA",""),
            "PIPELINE_REPOSITORY":environ.get("GITHUB_REPOSITORY",""),"PIPELINE_WORKSPACE":workspace,
            "PIPELINE_ARTIFACT_DIR":environ.get("PIPELINE_ARTIFACT_DIR",str(Path(workspace)/".pipeline-artifacts")),
            "PIPELINE_OUTPUT_FILE":environ.get("GITHUB_OUTPUT",""),"PIPELINE_RUN_ID":environ.get("GITHUB_RUN_ID",""),
            "PIPELINE_RUN_ATTEMPT":environ.get("GITHUB_RUN_ATTEMPT","")}
    def bootstrap_values(self,environ:Mapping[str,str])->dict[str,str]:
        values=self.normalize_environment(environ);token=environ.get("SOURCE_SUBMODULE_TOKEN","")
        if token and environ.get("SOURCE_SUBMODULE_MODE","")=="recursive":
            if "\n" in token or "\r" in token:raise ValueError("submodule token contains unsupported newline")
            try:count=int(environ.get("GIT_CONFIG_COUNT","0") or "0")
            except ValueError as exc:raise ValueError("GIT_CONFIG_COUNT must be integer") from exc
            values["GIT_CONFIG_COUNT"]=str(count+1)
            values[f"GIT_CONFIG_KEY_{count}"]=f"url.https://x-access-token:{token}@github.com/.insteadOf"
            values[f"GIT_CONFIG_VALUE_{count}"]="https://github.com/"
            values["PIPELINE_SECRET_REDACTIONS"]=token
        return values
    @staticmethod
    def write_environment_file(path:str|Path,values:Mapping[str,str])->None:
        target=Path(path);target.parent.mkdir(parents=True,exist_ok=True);lines=[]
        for key,value in values.items():
            if not re.fullmatch(r"[A-Z][A-Z0-9_]*",key):raise ValueError(f"Invalid environment key: {key!r}")
            if "\n" in value or "\r" in value:raise ValueError(f"Environment value for {key} contains newline")
            lines.append(f"{key}={value}")
        with target.open("a",encoding="utf-8",newline="\n") as stream:stream.write("\n".join(lines)+"\n")
def main(argv:list[str]|None=None)->int:
    args=list(sys.argv[1:] if argv is None else argv)
    if not args or args[0]!="bootstrap":
        print("Usage: python scripts/providers/github/adapter.py bootstrap",file=sys.stderr);return 2
    path=os.environ.get("GITHUB_ENV","")
    if not path:print("GITHUB_ENV is required for bootstrap mode",file=sys.stderr);return 2
    try:GitHubAdapter.write_environment_file(path,GitHubAdapter().bootstrap_values(os.environ))
    except (OSError,ValueError) as exc:print(f"GitHub adapter failed: {exc}",file=sys.stderr);return 1
    print("GitHub provider context exported as PIPELINE_* variables.");return 0
if __name__=="__main__":raise SystemExit(main())
