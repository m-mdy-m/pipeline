from __future__ import annotations
import hashlib
import os
import subprocess
import tempfile
from pathlib import Path
from typing import Mapping, Sequence


from .errors import ReleaseError
from .logger import logger
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
    output_file = env("PIPELINE_OUTPUT_FILE")
    lines = [f"{key}={str(value).lower() if isinstance(value, bool) else value}" for key, value in values.items()]
    if output_file:
        target = Path(output_file)
        target.parent.mkdir(parents=True, exist_ok=True)
        if any("\n" in line or "\r" in line for line in lines):
            raise ReleaseError("Output values must not contain newline characters")
        with target.open("a", encoding="utf-8", newline="\n") as stream:
            stream.write("\n".join(lines) + "\n")
    for line in lines:
        logger.info(line, component="workflow-output")


def parse_lines(value: str) -> list[str]:
    return [line.strip() for line in value.splitlines() if line.strip() and not line.lstrip().startswith("#")]


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


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

def atomic_write_text(path: Path, content: str) -> None:
    """Atomically write UTF-8 text; readers never see a partial file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", newline="\n",
                dir=path.parent, prefix=f".{path.name}.", suffix=".tmp", delete=False) as stream:
            temporary = Path(stream.name)
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        temporary.replace(path)
    finally:
        if temporary is not None and temporary.exists():
            temporary.unlink()
