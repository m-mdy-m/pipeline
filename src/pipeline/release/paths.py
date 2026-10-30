from __future__ import annotations
import fnmatch
import posixpath
import re
from pathlib import PurePosixPath
from typing import Iterable
from .errors import ReleaseError


def safe_repo_path(path: str) -> str:
    """Validate a Git path for portable ZIP extraction and return normalized path."""
    if not path or path.startswith("/") or path.startswith("\\") or "\\" in path:
        raise ReleaseError(f"Unsafe repository path: {path!r}")
    if re.match(r"^[A-Za-z]:", path):
        raise ReleaseError(f"Windows drive path is not allowed in source archives: {path!r}")
    if any(ord(ch) < 32 or ord(ch) == 127 for ch in path):
        raise ReleaseError(f"Control character in repository path: {path!r}")
    parts = path.split("/")
    if any(part in ("", ".", "..") for part in parts):
        raise ReleaseError(f"Path traversal or empty path segment: {path!r}")
    for part in parts:
        if part.endswith((".", " ")) or ":" in part:
            raise ReleaseError(f"Non-portable path segment: {part!r} in {path!r}")
        stem = part.split(".", 1)[0].upper()
        if stem in {"CON", "PRN", "AUX", "NUL", *(f"COM{i}" for i in range(1, 10)), *(f"LPT{i}" for i in range(1, 10))}:
            raise ReleaseError(f"Reserved Windows device name in source path: {path!r}")
    return "/".join(parts)


def glob_match(path: str, pattern: str) -> bool:
    pattern = pattern.strip()
    if not pattern:
        return False
    if pattern.startswith("!"):
        raise ReleaseError(f"Negated patterns are not supported; use an explicit allowlist instead: {pattern}")
    if pattern.startswith("/") or "\\" in pattern or ".." in PurePosixPath(pattern).parts:
        raise ReleaseError(f"Unsafe glob pattern: {pattern!r}")
    is_dir_pattern = pattern.endswith("/")
    clean = pattern.rstrip("/")
    if is_dir_pattern and (path == clean or path.startswith(clean + "/")):
        return True
    candidates = [path]
    if "/" not in clean:
        candidates.extend(path.split("/"))
    if clean.startswith("**/"):
        candidates.append(clean[3:])
    return any(fnmatch.fnmatchcase(candidate, clean) for candidate in candidates)


def validate_patterns(patterns: Iterable[str]) -> list[str]:
    normalized = [pattern.strip() for pattern in patterns if pattern.strip()]
    for pattern in normalized:
        # Run structural validation independently of whether the pattern matches a path.
        if pattern.startswith("!") or pattern.startswith("/") or "\\" in pattern or ".." in PurePosixPath(pattern).parts:
            raise ReleaseError(f"Unsafe or unsupported glob pattern: {pattern!r}")
    return normalized


def any_pattern(path: str, patterns: Iterable[str]) -> bool:
    return any(glob_match(path, pattern) for pattern in patterns)


def path_exists_as_directory(path: str, file_paths: set[str]) -> bool:
    if path == "":
        return True
    prefix = path.rstrip("/") + "/"
    return any(item.startswith(prefix) for item in file_paths)


def validate_symlinks(symlinks: dict[str, str], regular_paths: set[str], all_paths: set[str]) -> None:
    def resolve(path: str, chain: tuple[str, ...]) -> bool:
        if path in chain:
            raise ReleaseError(f"Symlink cycle detected: {' -> '.join((*chain, path))}")
        if path in symlinks:
            target = symlinks[path]
            if target.startswith("/") or re.match(r"^[A-Za-z]:", target) or "\\" in target:
                raise ReleaseError(f"Absolute or platform-ambiguous symlink target is forbidden: {path} -> {target}")
            if any(ord(ch) < 32 or ord(ch) == 127 for ch in target):
                raise ReleaseError(f"Control character in symlink target: {path}")
            resolved = posixpath.normpath(posixpath.join(posixpath.dirname(path), target))
            if resolved == ".":
                resolved = ""
            if resolved == ".." or resolved.startswith("../") or resolved.startswith("/"):
                raise ReleaseError(f"Symlink escapes source root: {path} -> {target}")
            if resolved == "":
                return True
            return resolve(resolved, (*chain, path)) if resolved in symlinks else (
                resolved in regular_paths or path_exists_as_directory(resolved, all_paths)
            )
        return path in regular_paths or path_exists_as_directory(path, all_paths)

    for path, target in symlinks.items():
        if not resolve(path, ()):
            raise ReleaseError(f"Broken symlink in release source: {path} -> {target}")
