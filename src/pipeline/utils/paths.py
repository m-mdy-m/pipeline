"""Filesystem path boundary helpers."""
from __future__ import annotations

from pathlib import Path


def resolve_within(root: str | Path, path: str | Path, *, label: str = "path") -> Path:
    # Keep the caller's lexical spelling (notably /var vs /private/var on
    # macOS and 8.3 aliases on Windows) while checking containment against
    # canonical paths so symlinks cannot escape the workspace.
    base = Path(root).expanduser().absolute()
    candidate = Path(path).expanduser()
    lexical = candidate if candidate.is_absolute() else base / candidate

    canonical_base = base.resolve()
    canonical_candidate = lexical.resolve()
    try:
        canonical_candidate.relative_to(canonical_base)
    except ValueError as exc:
        raise ValueError(f"{label} must stay inside {canonical_base}: {path}") from exc
    return lexical
