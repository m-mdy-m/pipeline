"""Translate GitLab CI variables, then invoke the same core CLI."""
from __future__ import annotations
import os,sys
from pathlib import Path
from typing import Mapping
SCRIPTS_ROOT=Path(__file__).resolve().parents[2]
if str(SCRIPTS_ROOT) not in sys.path:sys.path.insert(0,str(SCRIPTS_ROOT))
from pipeline_core.cli import main as core_main  # noqa: E402
from pipeline_core.provider import ProviderAdapter  # noqa: E402
class GitLabAdapter:
    name="gitlab"
    def normalize_environment(self,environ:Mapping[str,str])->dict[str,str]:
        root=str(Path(environ.get("CI_PROJECT_DIR",environ.get("PWD","."))).resolve());tag=environ.get("CI_COMMIT_TAG","")
        ref=tag or environ.get("CI_COMMIT_REF_NAME","");kind="tag" if tag else ("branch" if environ.get("CI_COMMIT_BRANCH") or ref else "")
        artifact_dir=environ.get("PIPELINE_ARTIFACT_DIR",str(Path(root)/".pipeline-artifacts"))
        return {"PIPELINE_PROVIDER":"gitlab","PIPELINE_EVENT":environ.get("CI_PIPELINE_SOURCE",""),
            "PIPELINE_REF_TYPE":kind,"PIPELINE_REF_NAME":ref,"PIPELINE_SHA":environ.get("CI_COMMIT_SHA",""),
            "PIPELINE_REPOSITORY":environ.get("CI_PROJECT_PATH",""),"PIPELINE_WORKSPACE":root,
            "PIPELINE_ARTIFACT_DIR":artifact_dir,
            "PIPELINE_OUTPUT_FILE":environ.get("PIPELINE_OUTPUT_FILE",str(Path(artifact_dir)/"outputs.env")),
            "PIPELINE_RUN_ID":environ.get("CI_PIPELINE_ID",""),"PIPELINE_RUN_ATTEMPT":environ.get("CI_JOB_RETRY","")}
def main(argv:list[str]|None=None)->int:
    os.environ.update(GitLabAdapter().normalize_environment(os.environ))
    return core_main(list(sys.argv[1:] if argv is None else argv))
if __name__=="__main__":raise SystemExit(main())
