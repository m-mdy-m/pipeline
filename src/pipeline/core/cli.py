"""CLI for task graph validation, local execution and artifact collection."""
from __future__ import annotations
import argparse,json
from pathlib import Path
from typing import Sequence
from .artifacts import LocalArtifactStore
from .config import PipelineConfig
from .context import PipelineContext
from .errors import ArtifactError,PipelineConfigError,PipelineError
from ..common.logging import logger
from .runner import TaskRunner
from ..common.io import atomic_write_json,write_output_variables
def _common(p):p.add_argument("--root",default=".");p.add_argument("--config",default="pipeline.toml")
def _load(args):
    root=Path(args.root).expanduser().resolve();path=Path(args.config).expanduser()
    if not path.is_absolute():path=root/path
    return PipelineConfig.load(path,workspace=root)
def _json(v):print(json.dumps(v,indent=2,sort_keys=True))
def _write_json(path,value):
    atomic_write_json(path,value)

def _csv(text):return [x.strip() for x in text.split(",") if x.strip()]
def _ci(args):
    from ..toolchains import build_plan,plan_to_config
    from ..core.ci_settings import load_ci_settings
    root=Path(args.root).expanduser().resolve()
    settings=load_ci_settings(root,args.config)
    overrides={**settings.commands,**{st:getattr(args,f"{st}_command") for st in ("install","configure","lint","build","test") if getattr(args,f"{st}_command")}}
    options=dict(settings.options)
    for item in args.option:
        key,sep,value=item.partition("=")
        if not sep or not key:raise ValueError(f"--option expects KEY=VALUE, got {item!r}")
        options[key]=value
    plan=build_plan(root,args.language or settings.language or "auto",overrides=overrides,stages=_csv(args.stages) or list(settings.stages),skip=_csv(args.skip) or list(settings.skip),options=options)
    if args.dry_run:
        _json(plan.to_dict());return 0
    config=plan_to_config(plan,root,timeout_seconds=args.timeout or settings.timeout_seconds or 1800)
    context=PipelineContext.from_environment(workspace=root)
    report=TaskRunner(config,context,fail_fast=False if args.no_fail_fast else None).run([t for t in config.tasks][-1:])
    write_output_variables({"language":plan.language,"package_manager":plan.package_manager,"succeeded":report.succeeded},context.output_file)
    if args.result:
        dest=Path(args.result);_write_json(dest if dest.is_absolute() else root/dest,{**report.to_dict(),"language":plan.language})
    if args.json:_json({**report.to_dict(),"language":plan.language})
    else:
        for item in report.results:logger.info(f"{item.name}: {item.status}, exit={item.return_code}, {item.duration_seconds:.3f}s"+(f" ({item.error})" if item.error else ""),component="ci",status=item.status)
    return report.exit_code
def build_parser():
    parser=argparse.ArgumentParser(prog="pipeline",description="Provider-neutral automation engine");subs=parser.add_subparsers(dest="command",required=True)
    for name in ("validate","list"):
        p=subs.add_parser(name);_common(p);p.add_argument("--json",action="store_true")
    p=subs.add_parser("run");_common(p);p.add_argument("targets",nargs="+");p.add_argument("--result",default="");p.add_argument("--no-fail-fast",action="store_true");p.add_argument("--json",action="store_true")
    p=subs.add_parser("context");p.add_argument("--root",default=".");p.add_argument("--json",action="store_true")
    p=subs.add_parser("detect");p.add_argument("--root",default=".");p.add_argument("--json",action="store_true")
    p=subs.add_parser("ci",help="Run install/lint/build/test for a detected or chosen language")
    p.add_argument("--root",default=".");p.add_argument("--config",default="pipeline.toml");p.add_argument("--language",default=None)
    p.add_argument("--stages",default="",help="Comma separated subset of: install,configure,lint,build,test")
    p.add_argument("--skip",default="",help="Comma separated stages to skip")
    for stage in ("install","configure","lint","build","test"):p.add_argument(f"--{stage}-command",default="",help=f"Override the {stage} command (split like a shell, not run by one)")
    p.add_argument("--option",action="append",default=[],metavar="KEY=VALUE",help="Preset option, e.g. package_manager=pnpm, source=lib, tests=spec, runner=pytest, build_tool=gradle")
    p.add_argument("--timeout",type=int,default=None);p.add_argument("--result",default="");p.add_argument("--dry-run",action="store_true");p.add_argument("--no-fail-fast",action="store_true");p.add_argument("--json",action="store_true")
    p=subs.add_parser("bench",help="Run benchmarks and compare them with a git ref or baseline file")
    from ..benchmark.bench_cli import add_arguments as _bench_args;_bench_args(p)
    p=subs.add_parser("artifacts");p.add_argument("--directory",default=".pipeline-artifacts");p.add_argument("--overwrite",action="store_true");p.add_argument("files",nargs="+")
    return parser
def main(argv:Sequence[str]|None=None)->int:
    args=build_parser().parse_args(argv)
    try:
        if args.command=="context":
            value=PipelineContext.from_environment(workspace=Path(args.root).resolve()).to_dict()
            _json(value) if args.json else logger.info(json.dumps(value,sort_keys=True),component="context")
            return 0
        if args.command=="detect":
            from ..toolchains import detect_toolchains
            found=detect_toolchains(args.root)
            from ..toolchains.presets import node_package_manager
            root=Path(args.root).expanduser().resolve();pm=node_package_manager(root) if "node" in found else ""
            lock={"npm":("package-lock.json","npm-shrinkwrap.json"),"pnpm":("pnpm-lock.yaml",),"yarn":("yarn.lock",)}.get(pm,())
            cache=pm if any((root/x).exists() for x in lock) else ""
            _json({"schema_version":1,"detected":found,"primary":found[0] if found else "","package_manager":pm,"node_cache":cache}) if args.json else logger.info("Detected: "+(", ".join(found) or "nothing"),component="detect")
            return 0
        if args.command=="ci":return _ci(args)
        if args.command=="bench":
            from ..benchmark.bench_cli import run as _bench_run
            return _bench_run(args)
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
