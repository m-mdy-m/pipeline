#!/usr/bin/env python3
"""Provider-neutral repeated command benchmark runner.

The CI provider is responsible only for supplying inputs and publishing the
result directory. This module owns execution, timing, CSV output and summaries.
"""
from __future__ import annotations

import argparse
import csv
import json
import os
import platform
import statistics
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

CATEGORIES = (
    "micro",
    "throughput",
    "latency",
    "memory",
    "startup",
    "scalability",
    "regression",
    "size",
)


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def _run_shell(command: str, cwd: Path, env: dict[str, str], log_path: Path) -> int:
    with log_path.open("w", encoding="utf-8", newline="\n") as log:
        result = subprocess.run(
            ["bash", "-euo", "pipefail", "-c", command],
            cwd=cwd,
            env=env,
            stdout=log,
            stderr=subprocess.STDOUT,
            check=False,
        )
    return result.returncode


def _write_csv(path: Path, headers: list[str], rows: list[dict[str, Any]]) -> None:
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=headers)
        writer.writeheader()
        writer.writerows(rows)


def _environment_report() -> str:
    return "\n".join(
        (
            f"platform: {platform.platform()}",
            f"system: {platform.system()}",
            f"release: {platform.release()}",
            f"machine: {platform.machine()}",
            f"processor: {platform.processor() or 'unknown'}",
            f"cpu_count: {os.cpu_count() or 'unknown'}",
            f"python: {platform.python_version()}",
        )
    ) + "\n"


def run_benchmark(
    *,
    command: str,
    category: str,
    repetitions: int,
    working_directory: str | Path = ".",
    output_directory: str | Path = "benchmark-results",
    setup_command: str = "",
) -> dict[str, Any]:
    """Run a command repeatedly and write a portable result bundle."""
    if category not in CATEGORIES:
        raise ValueError(f"Unsupported category {category!r}; choose from: {', '.join(CATEGORIES)}")
    if not command.strip():
        raise ValueError("benchmark command must not be empty")
    if type(repetitions) is not int or not 1 <= repetitions <= 1000:
        raise ValueError("repetitions must be an integer between 1 and 1000")

    workspace = Path(working_directory).expanduser().resolve()
    if not workspace.is_dir():
        raise ValueError(f"Working directory does not exist: {workspace}")

    output = Path(output_directory).expanduser()
    if not output.is_absolute():
        output = workspace / output
    output = output.resolve()
    output.mkdir(parents=True, exist_ok=True)

    base_env = os.environ.copy()
    base_env["PIPELINE_BENCHMARK_CATEGORY"] = category
    exit_code = 0

    if setup_command.strip():
        setup_env = {**base_env, "PIPELINE_BENCHMARK_PHASE": "setup"}
        exit_code = _run_shell(setup_command, workspace, setup_env, output / "setup.log")

    iterations: list[dict[str, Any]] = []
    durations: list[float] = []

    if exit_code == 0:
        for number in range(1, repetitions + 1):
            started = _utc_now()
            start_ns = time.perf_counter_ns()
            run_env = {
                **base_env,
                "PIPELINE_BENCHMARK_PHASE": "measurement",
                "PIPELINE_BENCHMARK_ITERATION": str(number),
            }
            code = _run_shell(
                command,
                workspace,
                run_env,
                output / f"{category}-{number}.log",
            )
            duration_ms = (time.perf_counter_ns() - start_ns) / 1_000_000
            durations.append(duration_ms)
            iterations.append(
                {
                    "category": category,
                    "iteration": number,
                    "started_utc": started,
                    "duration_ms": f"{duration_ms:.3f}",
                    "exit_code": code,
                }
            )
            if code != 0:
                exit_code = code
                break

    _write_csv(
        output / "iterations.csv",
        ["category", "iteration", "started_utc", "duration_ms", "exit_code"],
        iterations,
    )

    ordered = sorted(durations)
    (output / "durations.txt").write_text(
        "".join(f"{value:.3f}\n" for value in durations),
        encoding="utf-8",
    )
    (output / "durations.sorted.txt").write_text(
        "".join(f"{value:.3f}\n" for value in ordered),
        encoding="utf-8",
    )

    summary: dict[str, Any] = {
        "category": category,
        "runs": len(durations),
        "min_ms": round(min(durations), 3) if durations else None,
        "median_ms": round(statistics.median(durations), 3) if durations else None,
        "mean_ms": round(statistics.fmean(durations), 3) if durations else None,
        "max_ms": round(max(durations), 3) if durations else None,
        "exit_code": exit_code,
    }
    summary_row = {
        key: "" if value is None else value
        for key, value in summary.items()
    }
    _write_csv(
        output / "summary.csv",
        ["category", "runs", "min_ms", "median_ms", "mean_ms", "max_ms", "exit_code"],
        [summary_row],
    )
    (output / "summary.json").write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    (output / "environment.txt").write_text(_environment_report(), encoding="utf-8")

    values = [
        "" if summary[key] is None else f"{summary[key]:.3f}"
        for key in ("min_ms", "median_ms", "mean_ms", "max_ms")
    ]
    markdown = [
        "## Benchmark summary",
        "",
        "| Category | Runs | Min ms | Median ms | Mean ms | Max ms |",
        "| --- | ---: | ---: | ---: | ---: | ---: |",
        f"| {category} | {len(durations)} | {values[0]} | {values[1]} | {values[2]} | {values[3]} |",
        "",
        f"Command exit code: {exit_code}",
        "",
    ]
    (output / "summary.md").write_text("\n".join(markdown), encoding="utf-8")

    return {
        **summary,
        "output_directory": str(output),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Run a command repeatedly and write portable benchmark results."
    )
    parser.add_argument("--command", required=True, help="Command to measure; executed by Bash.")
    parser.add_argument("--category", required=True, choices=CATEGORIES)
    parser.add_argument("--repetitions", required=True, type=int)
    parser.add_argument("--working-directory", default=".")
    parser.add_argument("--output-directory", default="benchmark-results")
    parser.add_argument("--setup-command", default="")
    args = parser.parse_args(argv)

    try:
        result = run_benchmark(
            command=args.command,
            category=args.category,
            repetitions=args.repetitions,
            working_directory=args.working_directory,
            output_directory=args.output_directory,
            setup_command=args.setup_command,
        )
    except (OSError, ValueError) as exc:
        print(f"benchmark failed: {exc}", file=sys.stderr)
        return 2

    print(json.dumps(result, indent=2, sort_keys=True))
    return int(result["exit_code"])


if __name__ == "__main__":
    raise SystemExit(main())
