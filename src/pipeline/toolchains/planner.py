"""Turn a project directory (plus optional overrides) into a runnable task graph."""
from __future__ import annotations

import os
import shlex
from dataclasses import dataclass, field
from pathlib import Path
from typing import Mapping

from ..core.config import PipelineConfig
from ..core.errors import PipelineConfigError
from ..core.models import TaskDefinition
from .presets import PRESETS, REQUIRED_STAGES, STAGES, Step, matches, node_package_manager

DEFAULT_TIMEOUT_SECONDS = 1800


class CIPlanError(PipelineConfigError):
    """Raised when no usable plan can be built for the requested language."""


@dataclass(frozen=True)
class CIPlan:
    language: str
    steps: tuple[Step, ...]
    detected: tuple[str, ...] = ()
    package_manager: str = ""
    skipped: tuple[str, ...] = field(default_factory=tuple)

    def to_dict(self) -> dict:
        return {
            "schema_version": 1,
            "language": self.language,
            "detected": list(self.detected),
            "package_manager": self.package_manager,
            "skipped_stages": list(self.skipped),
            "steps": [
                {"stage": s.stage, "command": list(s.command), "description": s.description, "env": dict(s.env)}
                for s in self.steps
            ],
        }


def detect_toolchains(root: str | Path) -> list[str]:
    """Return every language whose marker files exist, best match first."""
    base = Path(root).expanduser().resolve()
    return [name for name, preset in PRESETS.items() if matches(base, preset)]


def _split(stage: str, text: str) -> tuple[str, ...]:
    try:
        parts = shlex.split(text, posix=os.name != "nt")
        if os.name == "nt":
            parts = [part[1:-1] if len(part) >= 2 and part[0] == part[-1] and part[0] in "\'\\"" else part for part in parts]
    except ValueError as exc:
        raise CIPlanError(f"--{stage}-command is not valid shell-style quoting: {exc}") from exc
    if not parts:
        raise CIPlanError(f"--{stage}-command must not be empty; use --skip {stage} to omit the stage")
    return tuple(parts)


def build_plan(
    root: str | Path,
    language: str = "auto",
    *,
    overrides: Mapping[str, str] | None = None,
    stages: list[str] | None = None,
    skip: list[str] | None = None,
    options: Mapping[str, str] | None = None,
) -> CIPlan:
    """Plan CI stages.

    ``overrides`` maps a stage to a command line. It is split with ``shlex`` and
    never handed to a shell; wrap in ``bash -c '...'`` when shell syntax is needed.
    """
    base = Path(root).expanduser().resolve()
    overrides = dict(overrides or {})
    skipped = list(skip or [])
    for name in [*overrides, *skipped, *(stages or [])]:
        if name not in STAGES:
            raise CIPlanError(f"Unknown stage {name!r}; choose from {', '.join(STAGES)}")

    detected = detect_toolchains(base)
    if language == "auto":
        if not detected:
            raise CIPlanError(
                f"Could not detect a toolchain in {base}. Pass --language ({', '.join(sorted(PRESETS))}, custom) "
                "and the stage commands explicitly."
            )
        language = detected[0]
    elif language != "custom" and language not in PRESETS:
        raise CIPlanError(f"Unsupported language {language!r}; choose from auto, custom, {', '.join(sorted(PRESETS))}")
    try:
        preset_steps = [] if language == "custom" else PRESETS[language].steps(base, dict(options or {}))
    except ValueError as exc:
        raise CIPlanError(str(exc)) from exc

    by_stage: dict[str, list[Step]] = {}
    for step in preset_steps:
        by_stage.setdefault(step.stage, []).append(step)
    for stage, text in overrides.items():
        by_stage[stage] = [Step(stage, _split(stage, text), "override")]

    selected = [s for s in STAGES if (not stages or s in stages) and s not in skipped]
    required = PRESETS[language].required if language in PRESETS else REQUIRED_STAGES
    for stage in required:
        if stage in selected and stage not in by_stage:
            raise CIPlanError(
                f"No {stage} command for language {language!r}. Provide --{stage}-command or pass --skip {stage}."
            )
    steps = tuple(step for stage in selected for step in by_stage.get(stage, []))
    if not steps:
        raise CIPlanError("The selected stages produced no commands")
    manager = node_package_manager(base, options) if language == "node" else ""
    return CIPlan(language, steps, tuple(detected), manager, tuple(s for s in STAGES if s not in selected))


def plan_to_config(plan: CIPlan, root: str | Path, *, timeout_seconds: int = DEFAULT_TIMEOUT_SECONDS) -> PipelineConfig:
    """Build an in-memory PipelineConfig: each step depends on the previous one."""
    base = Path(root).expanduser().resolve()
    tasks: dict[str, TaskDefinition] = {}
    previous = ""
    for step in plan.steps:
        name = step.stage
        n = 2
        while name in tasks:  # two steps in one stage keep unique names
            name = f"{step.stage}-{n}"
            n += 1
        tasks[name] = TaskDefinition(
            name, step.command, step.description, ".", (previous,) if previous else (), dict(step.env), timeout_seconds
        )
        previous = name
    return PipelineConfig(base / "<ci-preset>", base, f"ci-{plan.language}", f"{plan.language} CI preset", tasks, timeout_seconds, True)
