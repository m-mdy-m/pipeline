"""``pipeline bench``: run a language's benchmarks and compare them with a baseline."""
from __future__ import annotations

import json
from pathlib import Path

from ..common.io import atomic_write_json, atomic_write_text, write_output_variables
from ..common.logging import logger
from ..core.context import PipelineContext
from ..core.ci_settings import load_ci_settings
from ..core.errors import PipelineConfigError
from ..toolchains.bench import bench_plan
from . import compare as cmp


def add_arguments(p) -> None:
    p.add_argument("--root", default=".")
    p.add_argument("--config", default="pipeline.toml")
    p.add_argument("--language", default=None)
    p.add_argument("--command", dest="bench_command", default="", help="Benchmark command (split like a shell line, not run by a shell)")
    p.add_argument("--parser", default="", choices=["", *("gobench", "time")], help="gobench reads `BenchmarkX N 123 ns/op` lines; time measures wall clock")
    p.add_argument("--count", type=int, default=0, help="Repetitions (-count for gobench, runs for time)")
    p.add_argument("--option", action="append", default=[], metavar="KEY=VALUE")
    p.add_argument("--against", default="", help="Git ref to benchmark in a temporary worktree and compare with")
    p.add_argument("--baseline", default="", help="Baseline JSON file to compare with")
    p.add_argument("--update-baseline", action="store_true", help="Write the current results to --baseline")
    p.add_argument("--threshold", type=float, default=None, help="Percent slower that counts as a regression (default 25)")
    p.add_argument("--report-only", action="store_true", help="Never fail because of a regression")
    p.add_argument("--strict", action="store_true", help="Fail when the baseline cannot be produced")
    p.add_argument("--result", default="", help="Write the JSON report here")
    p.add_argument("--markdown", default="", help="Write the Markdown report here")
    p.add_argument("--json", action="store_true")


def run(args) -> int:
    root = Path(args.root).expanduser().resolve()
    settings = load_ci_settings(root, args.config)
    options = dict(settings.options)
    for item in args.option:
        key, sep, value = item.partition("=")
        if not sep or not key:
            raise ValueError(f"--option expects KEY=VALUE, got {item!r}")
        options[key] = value
    bench = settings.bench
    count_override = args.count or bench.count
    command_text = args.bench_command or bench.command
    parser = args.parser or bench.parser
    plan = bench_plan(root, args.language or settings.language or "auto", options, command_text, parser, count_override)
    threshold = args.threshold if args.threshold is not None else (bench.threshold_percent or cmp.DEFAULT_THRESHOLD_PERCENT)
    baseline_file = args.baseline or bench.baseline

    logger.info(f"Benchmarking ({plan.parser}): {' '.join(plan.command)}", component="bench")
    try:
        current = cmp.run_benchmark_command(plan.command, plan.parser, root, plan.count)
        if not current:
            raise cmp.BenchmarkError("the benchmark produced no results; check the command and parser")
        baseline: dict[str, float] | None = None
        note = ""
        if args.against:
            try:
                subdir = str(root.relative_to(_git_top(root)))
                baseline = cmp.measure_at_ref(root, args.against, plan.command, plan.parser, subdir, plan.count)
                note = f"Compared with `{args.against}` measured on the same machine."
            except cmp.BenchmarkError as exc:
                if args.strict:
                    raise
                note = f"⚠️ Baseline `{args.against}` could not be measured, so nothing was compared: {exc}"
        elif baseline_file and not args.update_baseline:
            path = Path(baseline_file) if Path(baseline_file).is_absolute() else root / baseline_file
            if path.is_file():
                baseline = cmp.load_baseline(path)
                note = f"Compared with the committed baseline `{baseline_file}`."
            elif args.strict:
                raise cmp.BenchmarkError(f"baseline file not found: {path}")
            else:
                note = f"⚠️ Baseline file `{baseline_file}` does not exist yet; run with --update-baseline to create it."
    except cmp.BenchmarkError as exc:
        logger.error(str(exc), component="bench", status="failed")
        return 2

    rows = cmp.compare(baseline, current, threshold) if baseline is not None else [cmp.Row(n, None, v, None, "new") for n, v in sorted(current.items())]
    markdown = cmp.render_markdown(rows, threshold, note=note)
    regressions = [r for r in rows if r.status == "regression"]
    report = {"schema_version": 1, "language": plan.language, "parser": plan.parser, "command": list(plan.command), "threshold_percent": threshold,
              "compared": baseline is not None, "regressions": len(regressions), "results": [r.to_dict() for r in rows]}
    if args.update_baseline:
        if not baseline_file:
            raise ValueError("--update-baseline needs --baseline FILE (or [ci.bench] baseline)")
        target = Path(baseline_file) if Path(baseline_file).is_absolute() else root / baseline_file
        cmp.save_baseline(target, current)
        logger.info(f"Baseline written to {target}", component="bench")
    if args.result:
        atomic_write_json(Path(args.result) if Path(args.result).is_absolute() else root / args.result, report)
    if args.markdown:
        atomic_write_text(Path(args.markdown) if Path(args.markdown).is_absolute() else root / args.markdown, markdown)
    context = PipelineContext.from_environment(workspace=root)
    write_output_variables({"language": plan.language, "regressions": len(regressions), "compared": baseline is not None}, context.output_file)
    print(json.dumps(report, indent=2, sort_keys=True) if args.json else markdown, end="")
    return 1 if regressions and not args.report_only else 0


def _git_top(root: Path) -> Path:
    import subprocess

    done = subprocess.run(["git", "rev-parse", "--show-toplevel"], cwd=root, capture_output=True, text=True, check=False)
    if done.returncode != 0:
        raise cmp.BenchmarkError("--against needs a git repository")
    return Path(done.stdout.strip()).resolve()
