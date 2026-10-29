"""Task graph executor with timeouts, failure propagation and structured reports."""
from __future__ import annotations
import os,subprocess,time
from datetime import datetime,timezone
from .config import PipelineConfig
from .context import PipelineContext
from .errors import PipelineError
from .logger import logger
from .models import RunReport,TaskDefinition,TaskResult
def _now():return datetime.now(timezone.utc).isoformat().replace("+00:00","Z")
class TaskRunner:
    def __init__(self,config:PipelineConfig,context:PipelineContext|None=None,*,fail_fast:bool|None=None):
        self.config=config;self.context=context or PipelineContext.from_environment(workspace=config.workspace)
        self.fail_fast=config.fail_fast if fail_fast is None else fail_fast
    def _execute(self,task:TaskDefinition)->TaskResult:
        cwd=(self.config.workspace/task.working_directory).resolve()
        if not cwd.is_relative_to(self.config.workspace):raise PipelineError(f"Task {task.name} working directory escapes workspace")
        if not cwd.is_dir():
            now=_now();return TaskResult(task.name,"failed",list(task.command),started_at=now,finished_at=now,error=f"Working directory missing: {cwd}")
        env=os.environ.copy();env.update(self.context.to_environment());env.update(task.environment or {})
        start_label=_now();start=time.monotonic()
        logger.info(f"Starting task {task.name}: {' '.join(task.command)}",component="task-runner")
        try:
            result=subprocess.run(list(task.command),cwd=cwd,env=env,check=False,timeout=task.timeout_seconds,shell=False)
            code=result.returncode;status="succeeded" if code==0 else "failed";error="" if code==0 else f"Command exited with {code}"
        except subprocess.TimeoutExpired:code,status,error=124,"failed",f"Timeout after {task.timeout_seconds}s"
        except OSError as exc:code,status,error=127,"failed",f"Could not start command: {exc}"
        duration=time.monotonic()-start
        (logger.info if status=="succeeded" else logger.error)(f"Task {task.name} {status}: exit={code}, {duration:.3f}s",component="task-runner",status=status)
        return TaskResult(task.name,status,list(task.command),code,duration,start_label,_now(),error)
    @staticmethod
    def _skip(task:TaskDefinition,reason:str)->TaskResult:
        now=_now();return TaskResult(task.name,"skipped",list(task.command),started_at=now,finished_at=now,error=reason)
    def run(self,targets:list[str])->RunReport:
        results=[];by_name={};stop=False
        for task in self.config.plan(targets):
            failed=next((dep for dep in task.depends_on if dep in by_name and by_name[dep].status!="succeeded"),None)
            if failed:result=self._skip(task,f"Dependency {failed} did not succeed")
            elif stop:result=self._skip(task,"Skipped after an earlier failure (fail_fast=true)")
            else:result=self._execute(task)
            results.append(result);by_name[task.name]=result
            if result.status=="failed" and self.fail_fast:stop=True
        return RunReport(self.context.provider,str(self.config.workspace),list(targets),results)
