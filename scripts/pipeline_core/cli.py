"""CLI for task graph validation, local execution and artifact collection."""
from __future__ import annotations
import argparse,json,os,tempfile
from pathlib import Path
from typing import Sequence
from .artifacts import LocalArtifactStore
from .config import PipelineConfig
from .context import PipelineContext
from .errors import ArtifactError,PipelineConfigError,PipelineError
from .logger import logger
from .runner import TaskRunner
def _common(p):p.add_argument("--root",default=".");p.add_argument("--config",default="pipeline.toml")
def _load(args):
    root=Path(args.root).expanduser().resolve();path=Path(args.config).expanduser()
    if not path.is_absolute():path=root/path
    return PipelineConfig.load(path,workspace=root)
def _json(v):print(json.dumps(v,indent=2,sort_keys=True))
def _write_json(path,value):
    path=Path(path).expanduser().resolve();path.parent.mkdir(parents=True,exist_ok=True);temp=None
    try:
        with tempfile.NamedTemporaryFile(mode="w",encoding="utf-8",newline="\n",dir=path.parent,prefix=f".{path.name}.",suffix=".tmp",delete=False) as out:
            temp=Path(out.name);json.dump(value,out,indent=2,sort_keys=True);out.write("\n");out.flush();os.fsync(out.fileno())
        temp.replace(path)
    finally:
        if temp and temp.exists():temp.unlink()
def build_parser():
    parser=argparse.ArgumentParser(prog="pipeline",description="Provider-neutral automation engine");subs=parser.add_subparsers(dest="command",required=True)
    for name in ("validate","list"):
        p=subs.add_parser(name);_common(p);p.add_argument("--json",action="store_true")
    p=subs.add_parser("run");_common(p);p.add_argument("targets",nargs="+");p.add_argument("--result",default="");p.add_argument("--no-fail-fast",action="store_true");p.add_argument("--json",action="store_true")
    p=subs.add_parser("context");p.add_argument("--root",default=".");p.add_argument("--json",action="store_true")
    p=subs.add_parser("artifacts");p.add_argument("--directory",default=".pipeline-artifacts");p.add_argument("--overwrite",action="store_true");p.add_argument("files",nargs="+")
    return parser
def main(argv:Sequence[str]|None=None)->int:
    args=build_parser().parse_args(argv)
    try:
        if args.command=="context":
            value=PipelineContext.from_environment(workspace=Path(args.root).resolve()).to_dict()
            _json(value) if args.json else logger.info(json.dumps(value,sort_keys=True),component="context")
            return 0
        if args.command=="artifacts":
            store=LocalArtifactStore(args.directory);items=store.publish(args.files,overwrite=args.overwrite)
            _json({"schema_version":1,"artifacts":[x.to_dict() for x in items],"manifest":str(store.directory/"artifacts.json")});return 0
        config=_load(args)
        if args.command=="validate":
            value={"valid":True,**config.describe()}
            _json(value) if args.json else logger.info(f"Valid config: {config.path} ({len(config.tasks)} tasks)",component="config")
            return 0
        if args.command=="list":
            if args.json:_json(config.describe())
            else:
                for item in config.tasks.values():logger.info(f"{item.name}: {item.description or 'no description'}",component="task-list")
            return 0
        context=PipelineContext.from_environment(workspace=config.workspace)
        report=TaskRunner(config,context,fail_fast=False if args.no_fail_fast else None).run(args.targets)
        if args.result:
            dest=Path(args.result);_write_json(dest if dest.is_absolute() else config.workspace/dest,report.to_dict())
        if args.json:_json(report.to_dict())
        else:
            for item in report.results:logger.info(f"{item.name}: {item.status}, exit={item.return_code}, {item.duration_seconds:.3f}s"+(f" ({item.error})" if item.error else ""),component="summary",status=item.status)
        return report.exit_code
    except (PipelineConfigError,PipelineError,ArtifactError,ValueError,OSError) as exc:
        logger.error(str(exc),component="pipeline-cli",status="failed");return 2
if __name__=="__main__":raise SystemExit(main())
