"""Shared safe and atomic filesystem/output helpers."""
from __future__ import annotations
import json
import os
import tempfile
from pathlib import Path
from typing import Mapping

def atomic_write_text(path: str | Path, content: str) -> Path:
    target = Path(path).expanduser()
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", newline="\n", dir=target.parent, prefix=f".{target.name}.", suffix=".tmp", delete=False) as stream:
            temporary = Path(stream.name)
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        temporary.replace(target)
    finally:
        if temporary is not None and temporary.exists():
            temporary.unlink()
    return target

def atomic_write_json(path: str | Path, value: object) -> Path:
    return atomic_write_text(path, json.dumps(value, indent=2, sort_keys=True) + "\n")

def write_output_variables(values: Mapping[str, object], output_file: str | Path | None = None) -> None:
    lines = []
    for key, value in values.items():
        if not key or any(ch not in "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789_" for ch in key):
            raise ValueError(f"Invalid output key: {key!r}")
        rendered = str(value).lower() if isinstance(value, bool) else str(value)
        if "\n" in rendered or "\r" in rendered:
            raise ValueError(f"Output value for {key} must not contain newlines")
        lines.append(f"{key}={rendered}")
    if output_file:
        target = Path(output_file)
        target.parent.mkdir(parents=True, exist_ok=True)
        with target.open("a", encoding="utf-8", newline="\n") as stream:
            stream.write("\n".join(lines) + ("\n" if lines else ""))
