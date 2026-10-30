"""Typed task and result models."""
from __future__ import annotations
from dataclasses import dataclass
from typing import Any
@dataclass(frozen=True)
class TaskDefinition:
    name:str
    command:tuple[str,...]
    description:str=""
    working_directory:str="."
    depends_on:tuple[str,...]=()
    environment:dict[str,str]|None=None
    timeout_seconds:int=300
@dataclass
class TaskResult:
    name:str
    status:str
    command:list[str]
    return_code:int|None=None
    duration_seconds:float=0.0
    started_at:str=""
    finished_at:str=""
    error:str=""
    def to_dict(self)->dict[str,Any]:
        return {"name":self.name,"status":self.status,"command":self.command,"return_code":self.return_code,
        "duration_seconds":round(self.duration_seconds,6),"started_at":self.started_at,"finished_at":self.finished_at,"error":self.error}
@dataclass
class RunReport:
    provider:str
    workspace:str
    requested_tasks:list[str]
    results:list[TaskResult]
    @property
    def succeeded(self)->bool:return bool(self.results) and all(x.status=="succeeded" for x in self.results)
    @property
    def exit_code(self)->int:return 0 if self.succeeded else 1
    def to_dict(self)->dict[str,Any]:
        return {"schema_version":1,"provider":self.provider,"workspace":self.workspace,"requested_tasks":self.requested_tasks,
        "succeeded":self.succeeded,"exit_code":self.exit_code,"tasks":[x.to_dict() for x in self.results]}
