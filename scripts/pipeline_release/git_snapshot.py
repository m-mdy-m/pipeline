from __future__ import annotations
from pathlib import Path
from typing import Sequence
from .errors import ReleaseError
from .logger import logger
from .models import TreeEntry
from .paths import safe_repo_path
from .runtime import STATE
from .tools import git_output, run_git


def parse_ls_tree(raw: bytes, repo_dir: Path, prefix: str = "") -> list[TreeEntry]:
    entries: list[TreeEntry] = []
    for record in raw.split(b"\0"):
        if not record:
            continue
        try:
            metadata, raw_path = record.split(b"\t", 1)
            mode_b, kind_b, sha_b = metadata.split(b" ", 2)
            path_part = raw_path.decode("utf-8", "strict")
            mode, kind, sha = mode_b.decode("ascii"), kind_b.decode("ascii"), sha_b.decode("ascii")
        except (ValueError, UnicodeDecodeError) as exc:
            raise ReleaseError("Git tree contains a path or entry that cannot be represented safely as UTF-8") from exc
        path_part = safe_repo_path(path_part)
        path = f"{prefix}/{path_part}" if prefix else path_part
        safe_repo_path(path)
        # Git metadata directories are never shipped. Do not quietly skip them:
        # seeing one as a tracked entry is an invalid repository layout.
        if any(part.lower() == ".git" for part in path.split("/")):
            raise ReleaseError(f"Tracked .git metadata path is forbidden in a source snapshot: {path}")
        entries.append(TreeEntry(mode=mode, kind=kind, sha=sha, path=path, repo_dir=repo_dir))
    return entries


def collect_entries(repo_dir: Path, commit: str, prefix: str, submodule_mode: str, *, depth: int = 0) -> list[TreeEntry]:
    if depth > 16:
        raise ReleaseError("Submodule nesting exceeds the safety limit of 16 levels")
    raw = run_git(["ls-tree", "-r", "-z", "--full-tree", commit], cwd=repo_dir, text=False)
    assert isinstance(raw, bytes)
    parsed = parse_ls_tree(raw, repo_dir, prefix)
    output: list[TreeEntry] = []
    for entry in parsed:
        if entry.mode != "160000" or entry.kind != "commit":
            if entry.kind != "blob" or entry.mode not in {"100644", "100755", "120000"}:
                raise ReleaseError(f"Unsupported Git tree entry ({entry.mode} {entry.kind}): {entry.path}")
            output.append(entry)
            continue

        if submodule_mode == "fail-if-present":
            raise ReleaseError(
                f"Submodule detected at '{entry.path}'. Set source-submodules: recursive or omit explicitly."
            )
        if submodule_mode == "omit":
            STATE.omitted_submodules.append(entry.path)
            logger.warning(f"Submodule content intentionally omitted: {entry.path}", component="submodules")
            continue
        if submodule_mode != "recursive":
            raise ReleaseError(f"Unsupported source-submodules policy: {submodule_mode!r}")

        parent_prefix = prefix
        local_path = entry.path[len(parent_prefix) + 1:] if parent_prefix else entry.path
        sub_path = (repo_dir / local_path).resolve()
        try:
            sub_path.relative_to(repo_dir.resolve())
        except ValueError as exc:
            raise ReleaseError(f"Submodule path escapes checkout: {entry.path}") from exc
        if not sub_path.is_dir():
            raise ReleaseError(f"Submodule did not initialize: {entry.path}")
        actual_commit = git_output(["rev-parse", "HEAD^{commit}"], cwd=sub_path)
        if actual_commit != entry.sha:
            raise ReleaseError(
                f"Submodule '{entry.path}' is at {actual_commit}, but the parent pins {entry.sha}"
            )
        # recurse at the actual submodule root; nested gitlinks are resolved relative to it.
        nested_prefix = entry.path
        nested = collect_entries(sub_path, entry.sha, nested_prefix, submodule_mode, depth=depth + 1)
        output.extend(nested)
    return output


def read_blob(entry: TreeEntry) -> bytes:
    raw = run_git(["cat-file", "blob", entry.sha], cwd=entry.repo_dir, text=False)
    assert isinstance(raw, bytes)
    return raw
