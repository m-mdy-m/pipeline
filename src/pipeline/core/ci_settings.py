"""Repository-owned CI settings: the optional ``[ci]`` table of ``pipeline.toml``."""
from __future__ import annotations

import tomllib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping

from .errors import PipelineConfigError

_STAGES = ("install", "configure", "lint", "build", "test")
_CI_KEYS = {"language", "stages", "skip", "timeout_seconds", "options", "commands", "bench"}
_BENCH_KEYS = {"command", "parser", "count", "threshold_percent", "baseline"}
PARSERS = ("gobench", "time")


@dataclass(frozen=True)
class BenchSettings:
    command: str = ""
    parser: str = ""
    count: int = 0
    threshold_percent: float = 0.0
    baseline: str = ""


@dataclass(frozen=True)
class CISettings:
    language: str = ""
    stages: tuple[str, ...] = ()
    skip: tuple[str, ...] = ()
    timeout_seconds: int = 0
    options: Mapping[str, str] = field(default_factory=dict)
    commands: Mapping[str, str] = field(default_factory=dict)
    bench: BenchSettings = field(default_factory=BenchSettings)


def _stage_list(name: str, value: Any) -> tuple[str, ...]:
    if not isinstance(value, list) or not all(isinstance(x, str) for x in value):
        raise PipelineConfigError(f"[ci] {name} must be an array of stage names")
    unknown = [x for x in value if x not in _STAGES]
    if unknown:
        raise PipelineConfigError(f"[ci] {name} has unknown stages {unknown}; choose from {', '.join(_STAGES)}")
    return tuple(value)


def parse_ci_table(raw: Any) -> CISettings:
    """Validate the ``[ci]`` table. Raises PipelineConfigError with a precise message."""
    if not isinstance(raw, dict):
        raise PipelineConfigError("[ci] must be a table")
    extra = set(raw) - _CI_KEYS
    if extra:
        raise PipelineConfigError(f"Unknown keys in [ci]: {sorted(extra)}")
    language = raw.get("language", "")
    if not isinstance(language, str):
        raise PipelineConfigError("[ci] language must be a string")
    timeout = raw.get("timeout_seconds", 0)
    if type(timeout) is not int or timeout < 0:
        raise PipelineConfigError("[ci] timeout_seconds must be a positive integer")
    options = raw.get("options", {})
    if not isinstance(options, dict) or not all(isinstance(k, str) and isinstance(v, (str, bool, int)) for k, v in options.items()):
        raise PipelineConfigError("[ci.options] values must be strings, booleans or integers")
    commands = raw.get("commands", {})
    if not isinstance(commands, dict) or not all(isinstance(k, str) and isinstance(v, str) and v.strip() for k, v in commands.items()):
        raise PipelineConfigError("[ci.commands] values must be non-empty strings")
    bad = [k for k in commands if k not in _STAGES]
    if bad:
        raise PipelineConfigError(f"[ci.commands] has unknown stages {bad}; choose from {', '.join(_STAGES)}")
    bench_raw = raw.get("bench", {})
    if not isinstance(bench_raw, dict) or set(bench_raw) - _BENCH_KEYS:
        raise PipelineConfigError(f"[ci.bench] may only contain {sorted(_BENCH_KEYS)}")
    parser = bench_raw.get("parser", "")
    if parser and parser not in PARSERS:
        raise PipelineConfigError(f"[ci.bench] parser must be one of {', '.join(PARSERS)}")
    count = bench_raw.get("count", 0)
    threshold = bench_raw.get("threshold_percent", 0)
    if type(count) is not int or count < 0 or isinstance(threshold, bool) or not isinstance(threshold, (int, float)) or threshold < 0:
        raise PipelineConfigError("[ci.bench] count and threshold_percent must be non-negative numbers")
    for key in ("command", "baseline"):
        if not isinstance(bench_raw.get(key, ""), str):
            raise PipelineConfigError(f"[ci.bench] {key} must be a string")
    return CISettings(
        language=language,
        stages=_stage_list("stages", raw.get("stages", [])),
        skip=_stage_list("skip", raw.get("skip", [])),
        timeout_seconds=timeout,
        options={k: (str(v).lower() if isinstance(v, bool) else str(v)) for k, v in options.items()},
        commands=dict(commands),
        bench=BenchSettings(bench_raw.get("command", ""), parser, count, float(threshold), bench_raw.get("baseline", "")),
    )


def load_ci_settings(root: str | Path, config: str | Path = "pipeline.toml") -> CISettings:
    """Read ``[ci]`` from the project's task file. A missing file or table yields defaults."""
    base = Path(root).expanduser().resolve()
    path = Path(config).expanduser()
    path = path if path.is_absolute() else base / path
    if not path.is_file():
        return CISettings()
    try:
        with path.open("rb") as stream:
            raw = tomllib.load(stream)
    except (OSError, tomllib.TOMLDecodeError) as exc:
        raise PipelineConfigError(f"Cannot read {path}: {exc}") from exc
    return parse_ci_table(raw["ci"]) if "ci" in raw else CISettings()
