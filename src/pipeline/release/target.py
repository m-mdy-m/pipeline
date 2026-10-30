"""Provider-neutral execution and reporting for release matrix targets."""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

_TARGET = re.compile(r"^[a-z0-9][a-z0-9-]{0,63}$")
_STAGES = {"test", "build"}


class ReleaseTargetError(ValueError):
    """Raised when a release target execution request is invalid."""


def _timestamp() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _inside(root: Path, candidate: Path, *, label: str) -> Path:
    resolved = candidate.expanduser().resolve()
    try:
        resolved.relative_to(root)
    except ValueError as exc:
        raise ReleaseTargetError(f"{label} must stay inside the release workspace: {resolved}") from exc
    return resolved


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    os.replace(temporary, path)


def _write_chunk(chunk: bytes) -> None:
    """Forward output immediately, without waiting for complete text lines."""
    buffer = getattr(sys.stdout, "buffer", None)
    if buffer is not None:
        buffer.write(chunk)
        buffer.flush()
    else:
        sys.stdout.write(chunk.decode("utf-8", errors="replace"))
        sys.stdout.flush()


def execute_target_stage(
    *,
    target: str,
    stage: str,
    command: str,
    working_directory: str | Path = ".",
    workspace: str | Path | None = None,
    report_directory: str | Path = ".pipeline-artifacts/release-targets",
    shell: str = "bash",
) -> dict[str, Any]:
    """Run a stage through Bash, stream combined output live, and save its result."""
    if not _TARGET.fullmatch(target):
        raise ReleaseTargetError(f"Invalid release target identifier: {target!r}")
    if stage not in _STAGES:
        raise ReleaseTargetError(f"Release stage must be one of: {', '.join(sorted(_STAGES))}")
    if not command.strip():
        raise ReleaseTargetError("Release target command must not be empty")
    if not shell.strip():
        raise ReleaseTargetError("Release target shell must not be empty")

    root = Path(workspace or Path.cwd()).expanduser().resolve()
    if not root.is_dir():
        raise ReleaseTargetError(f"Release workspace does not exist: {root}")
    cwd = _inside(root, root / working_directory, label="Working directory")
    if not cwd.is_dir():
        raise ReleaseTargetError(f"Release working directory does not exist: {cwd}")
    reports = _inside(root, root / report_directory, label="Report directory")
    result_path = reports / target / f"{stage}.json"

    started_at = _timestamp()
    started = time.monotonic()
    print(
        f"[release-target] {started_at} START target={target} stage={stage} cwd={cwd}",
        flush=True,
    )

    exit_code = 127
    error = ""
    argv = [shell, "--noprofile", "--norc", "-e", "-o", "pipefail", "-c", command]
    try:
        process = subprocess.Popen(
            argv,
            cwd=cwd,
            env=os.environ.copy(),
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            bufsize=0,
        )
        if process.stdout is None:
            raise OSError("could not open release command output stream")
        while True:
            chunk = os.read(process.stdout.fileno(), 65536)
            if not chunk:
                break
            _write_chunk(chunk)
        exit_code = process.wait()
        if exit_code != 0:
            error = f"{stage} command exited with status {exit_code}"
    except OSError as exc:
        error = f"could not start {stage} command using {shell!r}: {exc}"

    duration = time.monotonic() - started
    status = "succeeded" if exit_code == 0 and not error else "failed"
    finished_at = _timestamp()
    result = {
        "schema_version": 1,
        "target": target,
        "stage": stage,
        "status": status,
        "exit_code": exit_code,
        "duration_seconds": round(duration, 3),
        "started_at": started_at,
        "finished_at": finished_at,
        "working_directory": str(cwd),
        "error": error,
    }
    _write_json(result_path, result)

    if status == "succeeded":
        print(
            f"[release-target] {finished_at} PASS target={target} stage={stage} "
            f"duration={duration:.3f}s",
            flush=True,
        )
    else:
        print(
            f"[release-target] {finished_at} FAIL target={target} stage={stage} "
            f"exit={exit_code}: {error}; report={result_path}",
            file=sys.stderr,
            flush=True,
        )
    return result


def render_target_summary(
    *,
    target: str,
    report_directory: str | Path = ".pipeline-artifacts/release-targets",
    workspace: str | Path | None = None,
) -> str:
    """Render Markdown for the status summary of one matrix target."""
    if not _TARGET.fullmatch(target):
        raise ReleaseTargetError(f"Invalid release target identifier: {target!r}")
    root = Path(workspace or Path.cwd()).expanduser().resolve()
    reports = _inside(root, root / report_directory, label="Report directory") / target
    rows: list[dict[str, Any]] = []
    for stage in ("test", "build"):
        path = reports / f"{stage}.json"
        if not path.is_file():
            continue
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise ReleaseTargetError(f"Cannot read {stage} report {path}: {exc}") from exc
        if payload.get("target") != target or payload.get("stage") != stage:
            raise ReleaseTargetError(f"Unexpected report identity in {path}")
        rows.append(payload)

    lines = [
        f"## Release target: `{target}`",
        "",
        "| Stage | Result | Exit code | Duration |",
        "| --- | --- | ---: | ---: |",
    ]
    for row in rows:
        lines.append(
            f"| {row['stage']} | {row['status']} | {row['exit_code']} | "
            f"{row['duration_seconds']:.3f}s |"
        )
    if not rows:
        lines.extend(["| — | No stage report was produced | — | — |", "", "The target runner did not record a test or build stage."])
    failures = [row for row in rows if row["status"] != "succeeded"]
    if failures:
        lines.extend(["", "### Failure details"])
        for row in failures:
            lines.append(f"- **{row['stage']}**: {row['error'] or 'command failed'}")
    elif len(rows) == 2:
        lines.extend(["", "All recorded target stages completed successfully."])
    lines.append("")
    return "\n".join(lines)
