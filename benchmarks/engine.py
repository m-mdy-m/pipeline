"""In-process micro benchmarks of the pipeline engine.

Prints Go-style lines (``BenchmarkName  N  X ns/op``), which ``pipeline bench``
reads with ``--parser gobench``. Run it directly:

    python benchmarks/engine.py [--rounds 3]

Because the script imports the engine from the checkout it lives in, running it
inside a ``git worktree`` of another ref measures that ref's engine, which is how
``pipeline bench --against <ref>`` finds regressions on the same machine.
"""
from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path
from typing import Callable

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from pipeline.core.config import PipelineConfig  # noqa: E402
from pipeline.toolchains import build_plan, detect_toolchains, plan_to_config  # noqa: E402

FIXTURES = ROOT / "examples" / "toolchains"
TARGET_SECONDS = 0.15


def measure(function: Callable[[], object]) -> tuple[int, float]:
    """Run ``function`` until about TARGET_SECONDS elapsed; return (iterations, ns per iteration)."""
    function()  # warm-up
    iterations = 1
    while True:
        started = time.perf_counter_ns()
        for _ in range(iterations):
            function()
        elapsed = time.perf_counter_ns() - started
        if elapsed >= TARGET_SECONDS * 1e9 or iterations >= 1 << 20:
            return iterations, elapsed / iterations
        iterations *= 4


def scenarios() -> dict[str, Callable[[], object]]:
    names = sorted(p.name for p in FIXTURES.iterdir() if p.is_dir()) if FIXTURES.is_dir() else []
    found: dict[str, Callable[[], object]] = {
        "ConfigLoad": lambda: PipelineConfig.load(ROOT / "pipeline.toml", workspace=ROOT),
    }
    for name in names:
        root = FIXTURES / name
        found[f"Detect/{name}"] = lambda root=root: detect_toolchains(root)
        found[f"Plan/{name}"] = lambda root=root: plan_to_config(build_plan(root), root)
    return found


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--rounds", type=int, default=3, help="Lines printed per benchmark (like go test -count)")
    args = parser.parse_args(argv)
    print("goos: python")
    print("pkg: pipeline/engine")
    for name, function in scenarios().items():
        for _ in range(args.rounds):
            iterations, ns = measure(function)
            print(f"Benchmark{name.replace('/', '_')}  {iterations}  {ns:.1f} ns/op")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
