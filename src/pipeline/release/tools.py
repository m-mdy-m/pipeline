from __future__ import annotations
import hashlib
import os
import subprocess
import tempfile
from pathlib import Path
from typing import Mapping, Sequence


from .errors import ReleaseError
from ..common.logging import logger
from ..common.hashing import sha256_file
from ..common.io import atomic_write_text, write_output_variables
from .runtime import REPO_ROOT, STATE


def env(name: str, default: str = "") -> str:
    return os.environ.get(name, default)


def run_git(args: Sequence[str], *, cwd: Path = REPO_ROOT, text: bool = True) -> str | bytes:
    try:
        result = subprocess.run(
            ["git", *args], cwd=cwd, check=True,
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=text,
        )
    except subprocess.CalledProcessError as exc:
        stderr = exc.stderr.decode("utf-8", "replace") if isinstance(exc.stderr, bytes) else (exc.stderr or "")
        cmd = "git " + " ".join(args)
        if STATE.token_to_redact:
            cmd = cmd.replace(STATE.token_to_redact, "[REDACTED]")
        if STATE.token_to_redact:
            stderr = stderr.replace(STATE.token_to_redact, "[REDACTED]")
        raise ReleaseError(f"Command failed: {cmd}\n{stderr.strip()}") from exc
    return result.stdout


def git_output(args: Sequence[str], *, cwd: Path = REPO_ROOT) -> str:
    value = run_git(args, cwd=cwd, text=True)
    assert isinstance(value, str)
    return value.strip()


def write_outputs(values: dict[str, object]) -> None:
    try:
        write_output_variables(values, env("PIPELINE_OUTPUT_FILE"))
    except ValueError as exc:
        raise ReleaseError(str(exc)) from exc
    for key, value in values.items():
        rendered = str(value).lower() if isinstance(value, bool) else value
        logger.info(f"{key}={rendered}", component="workflow-output")

def parse_lines(value: str) -> list[str]:
    return [line.strip() for line in value.splitlines() if line.strip() and not line.lstrip().startswith("#")]



def run_command(args: Sequence[str], *, cwd: Path | None = None, extra_env: Mapping[str, str] | None = None, text: bool = True) -> str | bytes:
    """Run an argument-vector command without a shell, redacting secrets from errors."""
    command_env = os.environ.copy()
    if extra_env:
        command_env.update(extra_env)
    try:
        result = subprocess.run(list(args), cwd=cwd or REPO_ROOT, env=command_env, check=True,
                                stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=text)
    except (OSError, subprocess.CalledProcessError) as exc:
        stderr = getattr(exc, "stderr", "") or str(exc)
        if isinstance(stderr, bytes):
            stderr = stderr.decode("utf-8", "replace")
        if STATE.token_to_redact:
            stderr = stderr.replace(STATE.token_to_redact, "[REDACTED]")
        command = " ".join(args)
        if STATE.token_to_redact:
            command = command.replace(STATE.token_to_redact, "[REDACTED]")
        raise ReleaseError(f"Command failed: {command}\n{stderr.strip()}") from exc
    return result.stdout

def ensure_directory(path: Path, *, clean: bool = False) -> Path:
    """Create a directory and optionally clear that specific directory first."""
    if clean and path.exists():
        if path.is_symlink() or not path.is_dir():
            raise ReleaseError(f"Refusing to clean a non-directory path: {path}")
        import shutil
        shutil.rmtree(path)
    path.mkdir(parents=True, exist_ok=True)
    return path
