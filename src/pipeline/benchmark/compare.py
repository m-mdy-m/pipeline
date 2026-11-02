"""Benchmark parsing, baseline handling and regression detection.

Everything here is provider-neutral: a provider only chooses the runner and
shows the Markdown report. Values are nanoseconds (lower is better).
"""
from __future__ import annotations

import json
import os
import re
import shlex
import statistics
import subprocess
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping, Sequence

from ..common.io import atomic_write_json

SCHEMA_VERSION = 1
DEFAULT_THRESHOLD_PERCENT = 25.0
# `Benchmark<Name>[-GOMAXPROCS]   <iterations>   <value> ns/op` (Go, and any tool that prints the same line).
_GOBENCH = re.compile(r"^(Benchmark\S*?)(?:-\d+)?\s+\d+\s+([0-9]+(?:\.[0-9]+)?)\s+ns/op\b")
_PKG = re.compile(r"^pkg:\s+(\S+)")


class BenchmarkError(RuntimeError):
    """The benchmark could not be run or its output could not be understood."""


def parse_gobench(text: str) -> dict[str, float]:
    """Median ns/op per benchmark; repeated ``-count`` lines are collapsed."""
    samples: dict[str, list[float]] = {}
    package = ""
    for line in text.splitlines():
        found = _PKG.match(line)
        if found:
            package = found.group(1)
            continue
        match = _GOBENCH.match(line.strip())
        if match:
            name = f"{package}.{match.group(1)}" if package else match.group(1)
            samples.setdefault(name, []).append(float(match.group(2)))
    return {name: statistics.median(values) for name, values in samples.items()}


def measure_time(command: Sequence[str], cwd: Path, count: int, env: Mapping[str, str] | None = None) -> dict[str, float]:
    """Wall-clock median of ``count`` runs of a command, under the name ``command``."""
    durations: list[float] = []
    for _ in range(count):
        started = time.perf_counter_ns()
        done = subprocess.run(list(command), cwd=cwd, env=dict(env) if env else None, capture_output=True, text=True, check=False)
        durations.append(float(time.perf_counter_ns() - started))
        if done.returncode != 0:
            raise BenchmarkError(f"benchmark command failed with exit code {done.returncode}: {done.stderr.strip()[:500]}")
    return {"command": statistics.median(durations)}


def run_benchmark_command(command: Sequence[str], parser: str, cwd: Path, count: int) -> dict[str, float]:
    if parser == "time":
        return measure_time(command, cwd, count)
    if parser == "gobench":
        try:
            done = subprocess.run(list(command), cwd=cwd, capture_output=True, text=True, check=False)
        except OSError as exc:
            raise BenchmarkError(f"cannot run {command[0]}: {exc}") from exc
        if done.returncode != 0:
            raise BenchmarkError(f"benchmark command failed with exit code {done.returncode}:\n{(done.stdout + done.stderr)[-1500:]}")
        return parse_gobench(done.stdout)
    raise BenchmarkError(f"unknown parser {parser!r}")


@dataclass(frozen=True)
class Row:
    name: str
    baseline: float | None
    current: float | None
    delta_percent: float | None
    status: str  # ok | improved | regression | new | removed

    def to_dict(self) -> dict:
        return {"name": self.name, "baseline_ns": self.baseline, "current_ns": self.current,
                "delta_percent": None if self.delta_percent is None else round(self.delta_percent, 2), "status": self.status}


def compare(baseline: Mapping[str, float], current: Mapping[str, float], threshold_percent: float = DEFAULT_THRESHOLD_PERCENT) -> list[Row]:
    """A benchmark regresses when it is more than ``threshold_percent`` slower than the baseline."""
    rows: list[Row] = []
    for name in sorted(set(baseline) | set(current)):
        base, cur = baseline.get(name), current.get(name)
        if base is None:
            rows.append(Row(name, None, cur, None, "new"))
        elif cur is None:
            rows.append(Row(name, base, None, None, "removed"))
        else:
            delta = (cur - base) / base * 100 if base else 0.0
            status = "regression" if delta > threshold_percent else ("improved" if delta < -threshold_percent else "ok")
            rows.append(Row(name, base, cur, delta, status))
    return rows


def _human(ns: float | None) -> str:
    if ns is None:
        return "–"
    for unit, size in (("s", 1e9), ("ms", 1e6), ("µs", 1e3)):
        if ns >= size:
            return f"{ns / size:.2f} {unit}"
    return f"{ns:.1f} ns"


def render_markdown(rows: Sequence[Row], threshold_percent: float, *, title: str = "Benchmarks", note: str = "") -> str:
    regressions = [r for r in rows if r.status == "regression"]
    head = f"### {title}: " + (f"{len(regressions)} regression(s) over {threshold_percent:g}%" if regressions else "no regressions")
    lines = [head, ""]
    if note:
        lines += [note, ""]
    lines += ["| Benchmark | Baseline | Current | Change | Status |", "| --- | --- | --- | --- | --- |"]
    icon = {"regression": "❌", "improved": "🚀", "ok": "✅", "new": "🆕", "removed": "➖"}
    for r in rows:
        change = "–" if r.delta_percent is None else f"{r.delta_percent:+.1f}%"
        lines.append(f"| `{r.name}` | {_human(r.baseline)} | {_human(r.current)} | {change} | {icon[r.status]} {r.status} |")
    return "\n".join(lines) + "\n"


def load_baseline(path: Path) -> dict[str, float]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        values = data["benchmarks"]
        return {str(k): float(v) for k, v in values.items()}
    except (OSError, ValueError, KeyError, TypeError, AttributeError) as exc:
        raise BenchmarkError(f"invalid baseline file {path}: {exc}") from exc


def save_baseline(path: Path, values: Mapping[str, float]) -> None:
    atomic_write_json(path, {"schema_version": SCHEMA_VERSION, "unit": "ns", "benchmarks": dict(sorted(values.items()))})


def measure_at_ref(root: Path, ref: str, command: Sequence[str], parser: str, subdir: str, count: int) -> dict[str, float]:
    """Check ``ref`` out into a temporary worktree and run the same benchmark there."""
    if ref.startswith("-"):
        raise BenchmarkError("ref must not start with '-'")
    top = subprocess.run(["git", "rev-parse", "--show-toplevel"], cwd=root, capture_output=True, text=True, check=False)
    if top.returncode != 0:
        raise BenchmarkError("--against needs a git repository")
    repo = Path(top.stdout.strip())
    with tempfile.TemporaryDirectory(prefix="pipeline-bench-") as tmp:
        worktree = Path(tmp) / "base"
        added = subprocess.run(["git", "worktree", "add", "--detach", str(worktree), ref], cwd=repo, capture_output=True, text=True, check=False)
        if added.returncode != 0:
            raise BenchmarkError(f"cannot check out {ref!r}: {added.stderr.strip()}")
        try:
            return run_benchmark_command(command, parser, worktree / subdir, count)
        finally:
            subprocess.run(["git", "worktree", "remove", "--force", str(worktree)], cwd=repo, capture_output=True, check=False)


def split_command(text: str) -> tuple[str, ...]:
    try:
        parts = shlex.split(text, posix=os.name != "nt")
        if os.name == "nt":
            parts = [part[1:-1] if len(part) >= 2 and part[0] == part[-1] and part[0] in ("'", '"' ) else part for part in parts]
    except ValueError as exc:
        raise BenchmarkError(f"invalid benchmark command: {exc}") from exc
    if not parts:
        raise BenchmarkError("benchmark command must not be empty")
    return tuple(parts)
