"""TOML config loader, schema checks and task-graph planning."""
from __future__ import annotations
import tomllib
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from .errors import PipelineConfigError
from .models import TaskDefinition
from ..utils.paths import resolve_within
_ROOT={"schema_version","project","defaults","tasks"}
_PROJECT={"name","description"}
_DEFAULTS={"timeout_seconds","fail_fast"}
_TASK={"command","description","working_directory","depends_on","env","timeout_seconds"}
_RESERVED=("PIPELINE_",)

@dataclass(frozen=True)
class PipelineConfig:
    path:Path
    workspace:Path
    project_name:str
    project_description:str
    tasks:dict[str,TaskDefinition]
    default_timeout_seconds:int=300
    fail_fast:bool=True
    @classmethod
    def load(cls,path:str|Path="pipeline.toml",*,workspace:str|Path|None=None)->"PipelineConfig":
        root=Path(workspace or Path.cwd()).expanduser().resolve(); config=Path(path).expanduser()
        if not config.is_absolute(): config=root/config
        config=config.resolve()
        try:
            with config.open("rb") as stream: raw=tomllib.load(stream)
        except OSError as exc: raise PipelineConfigError(f"Cannot read {config}: {exc}") from exc
        except tomllib.TOMLDecodeError as exc: raise PipelineConfigError(f"Invalid TOML in {config}: {exc}") from exc
        if set(raw)-_ROOT: raise PipelineConfigError(f"Unknown top-level keys: {sorted(set(raw)-_ROOT)}")
        if type(raw.get("schema_version")) is not int or raw["schema_version"]!=1: raise PipelineConfigError("schema_version must be integer 1")
        project,defaults,data=raw.get("project",{}),raw.get("defaults",{}),raw.get("tasks")
        if not isinstance(project,dict) or set(project)-_PROJECT: raise PipelineConfigError("project may contain only name and description")
        if not isinstance(defaults,dict) or set(defaults)-_DEFAULTS: raise PipelineConfigError("defaults may contain only timeout_seconds and fail_fast")
        if not isinstance(data,dict) or not data: raise PipelineConfigError("tasks must be a non-empty table")
        dt=defaults.get("timeout_seconds",300); ff=defaults.get("fail_fast",True)
        if type(dt) is not int or dt<1: raise PipelineConfigError("timeout_seconds must be positive")
        if type(ff) is not bool: raise PipelineConfigError("fail_fast must be boolean")
        pname=project.get("name",root.name or "project"); desc=project.get("description","")
        if not isinstance(pname,str) or not pname.strip() or not isinstance(desc,str): raise PipelineConfigError("project name/description invalid")
        tasks={}
        for name,item in data.items():
            if not isinstance(name,str) or not name or any(c.isspace() for c in name): raise PipelineConfigError(f"Invalid task name: {name!r}")
            if not isinstance(item,dict): raise PipelineConfigError(f"Task {name!r} must be a table")
            if set(item)-_TASK: raise PipelineConfigError(f"Unknown fields in task {name!r}: {sorted(set(item)-_TASK)}")
            command=item.get("command")
            if not isinstance(command,list) or not command or not all(isinstance(a,str) and a for a in command):
                raise PipelineConfigError(f"Task {name!r}: command must be a non-empty string array; shell is not implicit")
            cwd=item.get("working_directory",".")
            if not isinstance(cwd,str) or not cwd or Path(cwd).is_absolute():
                raise PipelineConfigError(f"Task {name!r}: working_directory must stay inside workspace")
            try:
                resolve_within(root, cwd, label=f"Task {name!r} working_directory")
            except ValueError as exc:
                raise PipelineConfigError(f"Task {name!r}: working_directory must stay inside workspace") from exc
            deps,env_map=item.get("depends_on",[]),item.get("env",{})
            if not isinstance(deps,list) or not all(isinstance(x,str) and x for x in deps): raise PipelineConfigError(f"Task {name!r}: depends_on must be an array")
            if len(deps)!=len(set(deps)): raise PipelineConfigError(f"Task {name!r}: duplicate dependencies")
            if not isinstance(env_map,dict) or not all(isinstance(k,str) and isinstance(v,str) for k,v in env_map.items()): raise PipelineConfigError(f"Task {name!r}: env must be string-to-string")
            if any(k.startswith(_RESERVED) for k in env_map): raise PipelineConfigError(f"Task {name!r}: environment cannot override PIPELINE_* context")
            timeout=item.get("timeout_seconds",dt)
            if type(timeout) is not int or timeout<1: raise PipelineConfigError(f"Task {name!r}: timeout must be positive")
            description=item.get("description","")
            if not isinstance(description,str): raise PipelineConfigError(f"Task {name!r}: description must be a string")
            tasks[name]=TaskDefinition(name,tuple(command),description,cwd,tuple(deps),dict(env_map),timeout)
        for task in tasks.values():
            missing=[x for x in task.depends_on if x not in tasks]
            if missing: raise PipelineConfigError(f"Task {task.name!r}: unknown dependencies {missing}")
        obj=cls(config,root,pname,desc,tasks,dt,ff); obj._check_cycles(); return obj
    def _check_cycles(self):
        active=[]; done=set()
        def visit(name):
            if name in active: raise PipelineConfigError("Dependency cycle: "+" -> ".join(active[active.index(name):]+[name]))
            if name in done:return
            active.append(name)
            for dep in self.tasks[name].depends_on:visit(dep)
            active.pop();done.add(name)
        for name in self.tasks:visit(name)
    def plan(self,targets:list[str])->list[TaskDefinition]:
        if not targets:raise PipelineConfigError("At least one task is required")
        missing=[x for x in targets if x not in self.tasks]
        if missing:raise PipelineConfigError(f"Unknown tasks {missing}; available {sorted(self.tasks)}")
        out=[]; seen=set()
        def visit(name):
            if name in seen:return
            for dep in self.tasks[name].depends_on:visit(dep)
            seen.add(name);out.append(self.tasks[name])
        for target in targets:visit(target)
        return out
    def describe(self)->dict[str,Any]:
        return {"schema_version":1,"project":{"name":self.project_name,"description":self.project_description},"config":str(self.path),
        "tasks":[{"name":t.name,"description":t.description,"command":list(t.command),"working_directory":t.working_directory,
        "depends_on":list(t.depends_on),"timeout_seconds":t.timeout_seconds} for t in self.tasks.values()]}
