"""Filesystem path boundary helpers."""
from __future__ import annotations
from pathlib import Path

def resolve_within(root: str | Path, path: str | Path, *, label: str = "path") -> Path:
    base = Path(root).expanduser().resolve()
    candidate = Path(path).expanduser()
    resolved = (candidate if candidate.is_absolute() else base / candidate).resolve()
    try:
        resolved.relative_to(base)
    except ValueError as exc:
        raise ValueError(f"{label} must stay inside {base}: {path}") from exc
    return resolved
