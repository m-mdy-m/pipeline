"""Which command measures performance for a language, and how to read its output."""
from __future__ import annotations

from ..utils.commands import split_command_line
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping

from .planner import CIPlanError, detect_toolchains
from .presets import PRESETS, node_package_manager, _package_json


@dataclass(frozen=True)
class BenchPlan:
    language: str
    command: tuple[str, ...]
    parser: str
    count: int


def bench_plan(root: Path, language: str, options: Mapping[str, str], command: str = "", parser: str = "", count: int = 0) -> BenchPlan:
    if language == "auto":
        found = detect_toolchains(root)
        if not found and not command:
            raise CIPlanError(f"Could not detect a toolchain in {root}; pass --language or --command")
        language = found[0] if found else "custom"
    elif language != "custom" and language not in PRESETS:
        raise CIPlanError(f"Unsupported language {language!r}")
    if command:
        try:
            parts = split_command_line(command)
        except ValueError as exc:
            raise CIPlanError(f"invalid benchmark command: {exc}") from exc
        if not parts:
            raise CIPlanError("benchmark command must not be empty")
        chosen = parser or ("gobench" if language == "go" else "time")
        return BenchPlan(language, parts, chosen, count or (3 if chosen == "gobench" else 5))
    if language == "go":
        n = count or 3
        pattern = options.get("bench", ".")
        return BenchPlan(language, ("go", "test", "-run", "^$", "-bench", pattern, "-benchmem", "-count", str(n), "./..."), parser or "gobench", n)
    if language == "node" and "bench" in (_package_json(root).get("scripts") or {}):
        return BenchPlan(language, (node_package_manager(root, options), "run", "bench"), parser or "time", count or 5)
    if language == "rust":
        return BenchPlan(language, ("cargo", "bench"), parser or "time", count or 3)
    raise CIPlanError(f"No benchmark command known for {language!r}. Pass --command (and --parser) or set [ci.bench] command in pipeline.toml.")
