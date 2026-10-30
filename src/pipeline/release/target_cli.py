"""CLI for executing and summarizing provider-neutral release targets."""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

from .target import ReleaseTargetError, execute_target_stage, render_target_summary


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Stream release matrix target output and record stage results."
    )
    commands = parser.add_subparsers(dest="command", required=True)

    run = commands.add_parser("run", help="run one test or build stage")
    run.add_argument("--target", required=True)
    run.add_argument("--stage", required=True, choices=("test", "build"))
    run.add_argument("--command-env", default="PIPELINE_RELEASE_COMMAND")
    run.add_argument("--working-directory", default=".")
    run.add_argument("--report-directory", default=".pipeline-artifacts/release-targets")
    run.add_argument("--shell", default=os.environ.get("PIPELINE_RELEASE_SHELL", "bash"))

    report = commands.add_parser("report", help="render a Markdown summary for one target")
    report.add_argument("--target", required=True)
    report.add_argument("--report-directory", default=".pipeline-artifacts/release-targets")
    report.add_argument("--output", default="")

    args = parser.parse_args(argv)
    try:
        if args.command == "run":
            command = os.environ.get(args.command_env, "")
            if not command:
                raise ReleaseTargetError(f"Environment variable {args.command_env} is empty")
            result = execute_target_stage(
                target=args.target,
                stage=args.stage,
                command=command,
                working_directory=args.working_directory,
                report_directory=args.report_directory,
                shell=args.shell,
            )
            return 0 if result["status"] == "succeeded" else 1

        summary = render_target_summary(target=args.target, report_directory=args.report_directory)
        if args.output:
            output = Path(args.output).expanduser().resolve()
            output.parent.mkdir(parents=True, exist_ok=True)
            output.write_text(summary, encoding="utf-8")
        sys.stdout.write(summary)
        sys.stdout.flush()
        return 0
    except (OSError, ReleaseTargetError) as exc:
        print(f"release target runner: {exc}", file=sys.stderr, flush=True)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
