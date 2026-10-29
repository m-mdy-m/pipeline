#!/usr/bin/env python3
"""Build and validate a safe source-only GitHub Release archive.

The workflow calls `prepare` before secret scanning and `package` only after the
scanner succeeds. All input comes from SOURCE_* environment variables so caller
values are not interpolated into shell source.
"""
from __future__ import annotations

import fnmatch
import hashlib
import json
import os
import posixpath
import re
import shutil
import stat
import subprocess
import sys
import zipfile
import tomllib
from collections import Counter
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Iterable, Sequence

REPO_ROOT = Path.cwd().resolve()
WORK_DIR = Path(os.environ.get("SOURCE_WORK_DIR", str(REPO_ROOT / ".source-release-work"))).resolve()
SOURCE_TREE = WORK_DIR / "source-tree"
SCAN_TREE = WORK_DIR / "secret-scan"
RELEASE_ASSETS = WORK_DIR / "release-assets"
REPORTS = WORK_DIR / "reports"
VERSION_RE = re.compile(r"^v?(?P<version>\d+\.\d+\.\d+(?:-(?:alpha|beta|rc)\.\d+)?)$")
TAG_RE = re.compile(r"^v\d+\.\d+\.\d+(?:-(?:alpha|beta|rc)\.\d+)?$")
SEMVER_RE = r"\d+\.\d+\.\d+(?:-(?:alpha|beta|rc)\.\d+)?"

DEFAULT_SENSITIVE_PATTERNS = (
    ".env",
    ".env.*",
    "**/.env",
    "**/.env.*",
    "*.pem",
    "*.key",
    "*.p12",
    "*.pfx",
    "id_rsa",
    "id_dsa",
    "id_ecdsa",
    "id_ed25519",
    "*private_key*",
    "*private-key*",
    "credentials.json",
    "service-account*.json",
    "secrets.json",
    "secrets.yaml",
    "secrets.yml",
)
OMITTED_SUBMODULES: list[str] = []
TOKEN_TO_REDACT = ""

DEFAULT_SENSITIVE_ALLOWLIST = (
    ".env.example",
    ".env.sample",
    ".env.template",
    ".env.dist",
    "**/.env.example",
    "**/.env.sample",
    "**/.env.template",
    "**/.env.dist",
)


class ReleaseError(RuntimeError):
    """A safe-to-display validation failure."""


@dataclass(frozen=True)
class TreeEntry:
    mode: str
    kind: str
    sha: str
    path: str
    repo_dir: Path


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
        if TOKEN_TO_REDACT:
            stderr = stderr.replace(TOKEN_TO_REDACT, "[REDACTED]")
        raise ReleaseError(f"Command failed: {cmd}\n{stderr.strip()}") from exc
    return result.stdout


def git_output(args: Sequence[str], *, cwd: Path = REPO_ROOT) -> str:
    value = run_git(args, cwd=cwd, text=True)
    assert isinstance(value, str)
    return value.strip()


def write_outputs(values: dict[str, object]) -> None:
    output_file = env("GITHUB_OUTPUT")
    lines = [f"{key}={str(value).lower() if isinstance(value, bool) else value}" for key, value in values.items()]
    if output_file:
        with open(output_file, "a", encoding="utf-8", newline="\n") as stream:
            stream.write("\n".join(lines) + "\n")
    for line in lines:
        print(f"::notice title=Source Release output::{line}")


def parse_lines(value: str) -> list[str]:
    return [line.strip() for line in value.splitlines() if line.strip() and not line.lstrip().startswith("#")]


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
            OMITTED_SUBMODULES.append(entry.path)
            print(f"::warning title=Source Release::Submodule content intentionally omitted: {entry.path}")
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


def read_blob(entry: TreeEntry) -> bytes:
    raw = run_git(["cat-file", "blob", entry.sha], cwd=entry.repo_dir, text=False)
    assert isinstance(raw, bytes)
    return raw


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


def detect_changelog(entries: Sequence[TreeEntry], explicit_path: str) -> TreeEntry | None:
    by_path = {entry.path: entry for entry in entries}
    if explicit_path:
        path = safe_repo_path(explicit_path)
        found = by_path.get(path)
        if found is None:
            return None
        if found.mode == "120000":
            raise ReleaseError(f"Changelog must be a regular tracked file, not a symlink: {path}")
        return found

    candidates = (
        "CHANGELOG", "CHANGELOG.md", "CHANGELOG.txt",
        "docs/CHANGELOG", "docs/CHANGELOG.md", "docs/CHANGELOG.txt",
    )
    found = [by_path[path] for path in candidates if path in by_path]
    if len(found) > 1:
        raise ReleaseError(
            "Automatic changelog detection is ambiguous. Set changelog-path explicitly. Candidates: "
            + ", ".join(item.path for item in found)
        )
    if found and found[0].mode == "120000":
        raise ReleaseError(f"Automatically detected changelog must be a regular tracked file, not a symlink: {found[0].path}")
    return found[0] if found else None


def decode_changelog(entry: TreeEntry | None) -> str | None:
    if entry is None:
        return None
    try:
        return read_blob(entry).decode("utf-8-sig", "strict")
    except UnicodeDecodeError as exc:
        raise ReleaseError(f"Changelog is not valid UTF-8 text: {entry.path}") from exc


def heading_info(line: str) -> tuple[int | None, str | None]:
    stripped = line.strip()
    level: int | None = None
    match = re.match(r"^\s{0,3}(#{1,6})\s+(.+?)\s*#*\s*$", stripped)
    if match:
        level, title = len(match.group(1)), match.group(2).strip()
    else:
        # Common text-only headings are accepted too, but section boundaries for
        # these are detected by the next recognized version heading.
        title = stripped
    title = re.sub(r"^(?:release|version|changes\s+in\s+version)\s*[:#-]?\s+", "", title, flags=re.IGNORECASE)
    pattern = re.compile(
        rf"^\[?v?(?P<version>{SEMVER_RE})\]?(?:\s*(?:[-–—:]\s*.*)?)?$",
        re.IGNORECASE,
    )
    version_match = pattern.match(title)
    if version_match:
        return level, version_match.group("version")
    return level, None


def extract_unreleased_section(changelog: str, path: str) -> str:
    lines = changelog.splitlines()
    matches: list[tuple[int, int | None]] = []
    for idx, line in enumerate(lines):
        match = re.match(r"^\s{0,3}(#{1,6})\s+\[?Unreleased\]?\s*$", line, re.IGNORECASE)
        if match:
            matches.append((idx, len(match.group(1))))
    if len(matches) != 1:
        raise ReleaseError(
            f"Dry-run changelog '{path}' must contain exactly one 'Unreleased' section when "
            "there is no version-specific section."
        )
    start, level = matches[0]
    end = len(lines)
    for idx in range(start + 1, len(lines)):
        match = re.match(r"^\s{0,3}(#{1,6})\s+", lines[idx])
        if match and len(match.group(1)) <= level:
            end = idx
            break
    section = "\n".join(lines[start:end]).strip()
    if not section:
        raise ReleaseError(f"The Unreleased section in '{path}' is empty")
    return section + "\n"


def extract_version_section(changelog: str, version: str, path: str) -> str:
    lines = changelog.splitlines()
    matches: list[tuple[int, int | None]] = []
    infos: list[tuple[int | None, str | None]] = []
    for idx, line in enumerate(lines):
        info = heading_info(line)
        infos.append(info)
        if info[1] == version:
            matches.append((idx, info[0]))
    if not matches:
        accepted = "## [1.2.3], ## 1.2.3, ## v1.2.3, or Version 1.2.3"
        raise ReleaseError(f"Changelog '{path}' has no section for exact version {version}. Supported forms include {accepted}.")
    if len(matches) > 1:
        lines_num = ", ".join(str(idx + 1) for idx, _ in matches)
        raise ReleaseError(f"Changelog '{path}' has duplicate sections for version {version} at lines {lines_num}")

    start, level = matches[0]
    end = len(lines)
    for idx in range(start + 1, len(lines)):
        next_level, next_version = infos[idx]
        if next_version is not None:
            end = idx
            break
        if level is not None and next_level is not None and next_level <= level:
            end = idx
            break
        if level is None and re.match(r"^\s{0,3}#{1,2}\s+", lines[idx]):
            end = idx
            break
    section = "\n".join(lines[start:end]).strip()
    if not section:
        raise ReleaseError(f"Version section {version} in '{path}' is empty")
    return section + "\n"


def validate_tag_and_version() -> tuple[str, str, str, bool, str]:
    dry_run = env("SOURCE_DRY_RUN", "false").lower() == "true"
    ref_type = env("GITHUB_REF_TYPE")
    ref_name = env("GITHUB_REF_NAME")
    sha = env("GITHUB_SHA") or git_output(["rev-parse", "HEAD"])
    repo = env("GITHUB_REPOSITORY", "local/project")
    repository = repo.rsplit("/", 1)[-1]

    if ref_type == "tag":
        if not TAG_RE.fullmatch(ref_name):
            raise ReleaseError(
                f"Unsupported release tag: {ref_name!r}. Use vMAJOR.MINOR.PATCH or "
                "vMAJOR.MINOR.PATCH-(alpha|beta|rc).N."
            )
        version = ref_name[1:]
        tag_label = ref_name
        tag_commit = git_output(["rev-parse", f"{ref_name}^{{commit}}"])
        event_commit = git_output(["rev-parse", f"{sha}^{{commit}}"])
        if tag_commit != event_commit:
            raise ReleaseError(f"Tag {ref_name} resolves to {tag_commit}, not event commit {event_commit}")
        snapshot_ref = event_commit
    elif dry_run:
        short_sha = sha[:7]
        version = f"0.0.0-dev.{short_sha}"
        tag_label = f"dry-run-{short_sha}"
        snapshot_ref = git_output(["rev-parse", f"{sha}^{{commit}}"])
    else:
        raise ReleaseError("Source Release requires a version tag; use dry-run: true for a branch smoke test")

    prerelease = "-" in version
    return repository, version, tag_label, prerelease, snapshot_ref


def build_names(repository: str, version: str, tag_label: str) -> tuple[str, str]:
    template = env("SOURCE_ARCHIVE_NAME", "{repository}-{tag}-source.zip").strip()
    if not template:
        raise ReleaseError("source-archive-name must not be empty")
    replacements = {"repository": repository, "tag": tag_label, "version": version}
    result = template
    for key, value in replacements.items():
        result = result.replace("{" + key + "}", value)
    if "{" in result or "}" in result:
        raise ReleaseError(f"Unknown placeholder in source-archive-name: {template!r}")
    if result.startswith(".") or "/" in result or "\\" in result or not result.endswith(".zip"):
        raise ReleaseError("source-archive-name must be a basename ending in .zip (no paths)")
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._+-]*\.zip", result):
        raise ReleaseError(f"Invalid source archive filename: {result!r}")
    root = f"{repository}-{tag_label}"
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._+-]*", root):
        raise ReleaseError(f"Invalid ZIP root directory name: {root!r}")
    return result, root


def validate_allowlist_path(config_path: str, by_path: dict[str, TreeEntry]) -> TreeEntry | None:
    if not config_path:
        return None
    normalized = safe_repo_path(config_path)
    entry = by_path.get(normalized)
    if entry is None or entry.mode == "120000":
        raise ReleaseError(f"source-gitleaks-allowlist-path must refer to a regular tracked file: {normalized}")
    return entry


def compose_gitleaks_config(allowlist_entry: TreeEntry | None) -> bytes:
    # Explicitly extend Gitleaks' embedded default rules. A caller-owned file may
    # contribute allowlist tables only; it cannot replace/disable detection rules.
    config = (
        'title = "pipeline source-release default rules"\n'
        '[extend]\n'
        'useDefault = true\n'
    )
    if allowlist_entry is None:
        return config.encode("utf-8")
    try:
        custom = read_blob(allowlist_entry).decode("utf-8-sig", "strict")
        parsed = tomllib.loads(custom)
    except (UnicodeDecodeError, tomllib.TOMLDecodeError) as exc:
        raise ReleaseError(f"Invalid TOML in source-gitleaks-allowlist-path: {allowlist_entry.path}") from exc
    if not parsed or set(parsed) - {"allowlist", "allowlists"}:
        raise ReleaseError(
            "The Gitleaks allowlist file may contain only [allowlist] or [[allowlists]] tables; "
            "it cannot replace the scanner's default rules."
        )
    allowed_keys = {"description", "regexes", "paths", "commits", "stopwords", "regexTarget"}
    tables = []
    if "allowlist" in parsed:
        tables.append(parsed["allowlist"])
    if "allowlists" in parsed:
        tables.extend(parsed["allowlists"])
    if not tables:
        raise ReleaseError("Gitleaks allowlist TOML contains no allowlist table")
    for table in tables:
        if not isinstance(table, dict) or set(table) - allowed_keys:
            raise ReleaseError("Unsupported field in Gitleaks allowlist table")
    if "allowlist" in parsed and "allowlists" in parsed:
        raise ReleaseError("Use either [allowlist] or [[allowlists]], not both")
    return (config + "\n" + custom.strip() + "\n").encode("utf-8")


def clear_staging() -> None:
    WORK_DIR.mkdir(parents=True, exist_ok=True)
    for folder in (SOURCE_TREE, SCAN_TREE, RELEASE_ASSETS, REPORTS):
        if folder.exists():
            shutil.rmtree(folder)
        folder.mkdir(parents=True, exist_ok=True)


def prepare() -> None:
    repository, version, tag_label, prerelease, snapshot_ref = validate_tag_and_version()
    archive_name, root_folder = build_names(repository, version, tag_label)
    submodule_mode = env("SOURCE_SUBMODULES", "fail-if-present")
    if submodule_mode not in {"fail-if-present", "recursive", "omit"}:
        raise ReleaseError("source-submodules must be one of: fail-if-present, recursive, omit")
    if submodule_mode == "recursive":
        # Optional token is used only for submodule HTTPS clones and is never echoed.
        global TOKEN_TO_REDACT
        token = env("SOURCE_SUBMODULE_TOKEN")
        if token:
            TOKEN_TO_REDACT = token
            try:
                count = int(os.environ.get("GIT_CONFIG_COUNT", "0"))
            except ValueError:
                raise ReleaseError("GIT_CONFIG_COUNT has an invalid value")
            os.environ[f"GIT_CONFIG_KEY_{count}"] = f"url.https://x-access-token:{token}@github.com/.insteadOf"
            os.environ[f"GIT_CONFIG_VALUE_{count}"] = "https://github.com/"
            os.environ["GIT_CONFIG_COUNT"] = str(count + 1)
            os.environ.pop("SOURCE_SUBMODULE_TOKEN", None)
        print("Initializing submodules at the exact commits pinned by the tag...")
        run_git(["submodule", "update", "--init", "--recursive"])

    entries = collect_entries(REPO_ROOT, snapshot_ref, "", submodule_mode)
    by_path = {entry.path: entry for entry in entries}
    changelog_entry = detect_changelog(entries, env("SOURCE_CHANGELOG_PATH"))
    changelog_text = decode_changelog(changelog_entry)
    changelog_nonempty = bool(changelog_text and changelog_text.strip())
    missing_policy = env("SOURCE_CHANGELOG_MISSING_POLICY", "fail")
    if missing_policy not in {"fail", "warn"}:
        raise ReleaseError("changelog-missing-policy must be fail or warn")
    asset_mode = env("SOURCE_CHANGELOG_ASSET_MODE", "archive-only")
    if asset_mode not in {"archive-only", "archive-and-asset", "asset-only"}:
        raise ReleaseError("changelog-asset-mode must be archive-only, archive-and-asset, or asset-only")

    section_for_notes: str | None = None
    dry_run_branch = env("SOURCE_DRY_RUN", "false").lower() == "true" and env("GITHUB_REF_TYPE") != "tag"
    if not changelog_nonempty:
        reason = "not found" if changelog_entry is None else "empty or whitespace-only"
        if missing_policy == "fail":
            raise ReleaseError(f"Changelog is {reason}; configure changelog-missing-policy: warn to allow omission")
        if asset_mode == "asset-only":
            raise ReleaseError("changelog-asset-mode: asset-only requires a non-empty changelog")
        print(f"::warning title=Source Release::Changelog {reason}; continuing because policy is warn")
        changelog_entry = None
        changelog_text = None
    else:
        assert changelog_text is not None and changelog_entry is not None
        try:
            section_for_notes = extract_version_section(changelog_text, version, changelog_entry.path)
        except ReleaseError:
            # Only fall back when the synthetic branch version has no heading at all;
            # duplicate or malformed sections must still fail closed.
            has_exact_heading = any(heading_info(line)[1] == version for line in changelog_text.splitlines())
            if not dry_run_branch or has_exact_heading:
                raise
            section_for_notes = extract_unreleased_section(changelog_text, changelog_entry.path)

    # Release notes are prepared independently from the ZIP. Even if changelog is
    # optional, a configured release-notes file must be a tracked UTF-8 regular file.
    notes_mode = env("SOURCE_RELEASE_NOTES_MODE", "section")
    if notes_mode not in {"section", "full", "file"}:
        raise ReleaseError("release-notes-mode must be section, full, or file")
    notes_text: str
    notes_source_entry: TreeEntry | None = None
    if notes_mode == "file":
        notes_path = safe_repo_path(env("SOURCE_RELEASE_NOTES_PATH")) if env("SOURCE_RELEASE_NOTES_PATH") else ""
        if not notes_path:
            raise ReleaseError("release-notes-mode: file requires release-notes-path")
        notes_entry = by_path.get(notes_path)
        if notes_entry is None or notes_entry.mode == "120000":
            raise ReleaseError(f"release-notes-path must be a regular tracked file: {notes_path}")
        notes_source_entry = notes_entry
        try:
            notes_text = read_blob(notes_entry).decode("utf-8-sig", "strict").strip() + "\n"
        except UnicodeDecodeError as exc:
            raise ReleaseError(f"Release notes file is not valid UTF-8 text: {notes_path}") from exc
        if not notes_text.strip():
            raise ReleaseError(f"Release notes file is empty: {notes_path}")
    elif changelog_text and changelog_entry:
        notes_text = changelog_text.strip() + "\n" if notes_mode == "full" else (section_for_notes or extract_version_section(changelog_text, version, changelog_entry.path))
    else:
        notes_text = f"## Source release {version}\n\nNo changelog was published for this source release.\n"

    notes_text += (
        "\n---\n\n"
        "## Assets\n\n"
        f"- `{archive_name}`: source snapshot from `{tag_label}`.\n"
        "- `manifest.json`: archive metadata and SHA-256 hashes.\n"
        "- `SHA256SUMS`: SHA-256 checksums for downloadable assets.\n"
    )

    exclude_patterns = validate_patterns(parse_lines(env("SOURCE_EXCLUDE_PATTERNS")))
    all_paths = {entry.path for entry in entries if entry.mode != "160000"}
    filtered_entries: list[TreeEntry] = []
    excluded: list[str] = []
    for entry in entries:
        if entry.mode == "160000":
            # Gitlinks are represented in the manifest by omit policy, not as empty files.
            continue
        if any_pattern(entry.path, exclude_patterns):
            excluded.append(entry.path)
        else:
            filtered_entries.append(entry)

    if excluded:
        print("The following tracked paths were excluded by source-exclude-patterns:")
        for path in sorted(excluded):
            print(f"  - {path}")
    if not filtered_entries:
        raise ReleaseError("All tracked files were excluded; refusing to create an empty source archive")

    # asset-only means the changelog is published separately and intentionally omitted
    # from the archive. Other archive modes must preserve it in the source tree.
    if changelog_entry:
        is_excluded = changelog_entry.path in excluded
        if asset_mode in {"archive-only", "archive-and-asset"} and is_excluded:
            raise ReleaseError(
                f"source-exclude-patterns removes changelog '{changelog_entry.path}', which the selected "
                f"changelog-asset-mode ({asset_mode}) requires inside the ZIP"
            )
        if asset_mode == "asset-only":
            filtered_entries = [item for item in filtered_entries if item.path != changelog_entry.path]

    # Check all files that will actually be published by path. A separately attached
    # changelog is still subject to path policy even if absent from the ZIP.
    archived_entries = filtered_entries
    published_paths = {entry.path for entry in archived_entries}
    if changelog_entry and asset_mode in {"archive-and-asset", "asset-only"}:
        published_paths.add(changelog_entry.path)
    sensitive_patterns = validate_patterns(list(DEFAULT_SENSITIVE_PATTERNS) + parse_lines(env("SOURCE_SENSITIVE_PATH_PATTERNS")))
    safe_patterns = validate_patterns(list(DEFAULT_SENSITIVE_ALLOWLIST) + parse_lines(env("SOURCE_SENSITIVE_ALLOWLIST_PATTERNS")))
    sensitive_found: list[str] = []
    for path in sorted(published_paths):
        if any_pattern(path, sensitive_patterns) and not any_pattern(path, safe_patterns):
            sensitive_found.append(path)
    if sensitive_found:
        report = "\n".join(f"  - {path}" for path in sensitive_found)
        raise ReleaseError(
            "Sensitive-path policy rejected the source snapshot. No file was deleted automatically; "
            "remove/relocate it, adjust explicit patterns, or add a narrow allowlist.\n" + report
        )

    # Validate symlinks against the effective ZIP payload, not the working tree.
    file_paths = {entry.path for entry in archived_entries if entry.mode != "120000"}
    symlink_map: dict[str, str] = {}
    for entry in archived_entries:
        if entry.mode == "120000":
            target = read_blob(entry).decode("utf-8", "strict")
            symlink_map[entry.path] = target
    validate_symlinks(symlink_map, file_paths, file_paths)

    allowlist_entry = validate_allowlist_path(env("SOURCE_GITLEAKS_ALLOWLIST_PATH"), by_path)
    gitleaks_config = compose_gitleaks_config(allowlist_entry)

    # Reject collisions before writing any staged assets.
    changelog_asset_name = ""
    if changelog_entry and asset_mode in {"archive-and-asset", "asset-only"}:
        changelog_asset_name = PurePosixPath(changelog_entry.path).name
        reserved_names = {archive_name.casefold(), "manifest.json", "sha256sums", "release-notes.md"}
        if changelog_asset_name.casefold() in reserved_names:
            raise ReleaseError(f"Changelog asset name collides with a reserved release asset: {changelog_asset_name}")

    clear_staging()
    (REPORTS / "gitleaks.toml").write_bytes(gitleaks_config)

    for entry in archived_entries:
        destination = SOURCE_TREE.joinpath(*entry.path.split("/"))
        destination.parent.mkdir(parents=True, exist_ok=True)
        content = read_blob(entry)
        if entry.mode == "120000":
            target = content.decode("utf-8", "strict")
            os.symlink(target, destination)
        else:
            destination.write_bytes(content)
            destination.chmod(0o755 if entry.mode == "100755" else 0o644)

    # Preserve separate asset source as exact bytes from the tagged blob.
    if changelog_entry and changelog_asset_name:
        (RELEASE_ASSETS / changelog_asset_name).write_bytes(read_blob(changelog_entry))

    # Gitleaks scans the effective published payload. In asset-only mode the changelog
    # is intentionally absent from the ZIP but remains a public release asset, so mirror
    # it into the scan tree at its original path rather than leaving it unscanned.
    shutil.copytree(SOURCE_TREE, SCAN_TREE, symlinks=True, dirs_exist_ok=True)
    if changelog_entry and asset_mode == "asset-only":
        scan_changelog = SCAN_TREE.joinpath(*changelog_entry.path.split("/"))
        scan_changelog.parent.mkdir(parents=True, exist_ok=True)
        scan_changelog.write_bytes(read_blob(changelog_entry))
    if notes_source_entry is not None:
        scan_notes_source = SCAN_TREE.joinpath(*notes_source_entry.path.split("/"))
        if not scan_notes_source.is_file():
            scan_notes_source.parent.mkdir(parents=True, exist_ok=True)
            scan_notes_source.write_bytes(read_blob(notes_source_entry))
    (WORK_DIR / "release-notes.md").write_text(notes_text, encoding="utf-8", newline="\n")

    write_outputs({
        "version": version,
        "prerelease": prerelease,
        "tag_label": tag_label,
        "snapshot_sha": snapshot_ref,
        "archive_name": archive_name,
        "root_folder": root_folder,
        "changelog_found": bool(changelog_entry),
        "changelog_path": changelog_entry.path if changelog_entry else "",
        "changelog_asset_name": changelog_asset_name,
        "excluded_path_count": len(excluded),
        "archived_file_count": len(archived_entries),
        "omitted_submodule_count": len(OMITTED_SUBMODULES),
    })
    print(f"Prepared source snapshot: {snapshot_ref}; {len(archived_entries)} archived files; root={root_folder}/")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def zip_add_file(archive: zipfile.ZipFile, source: Path, archive_name: str) -> None:
    info = zipfile.ZipInfo(archive_name, date_time=(1980, 1, 1, 0, 0, 0))
    info.create_system = 3
    info.compress_type = zipfile.ZIP_DEFLATED
    if source.is_symlink():
        info.external_attr = (stat.S_IFLNK | 0o777) << 16
        archive.writestr(info, os.readlink(source).encode("utf-8"))
    else:
        mode = 0o755 if os.stat(source, follow_symlinks=False).st_mode & stat.S_IXUSR else 0o644
        info.external_attr = (stat.S_IFREG | mode) << 16
        archive.writestr(info, source.read_bytes())


def validate_zip(archive_path: Path, root_folder: str, archive_name: str, expected_changelog: str | None, expected_members: set[str]) -> int:
    if not archive_path.is_file() or archive_path.stat().st_size == 0:
        raise ReleaseError("Source ZIP is missing or empty")
    with zipfile.ZipFile(archive_path, "r") as archive:
        names = [item.filename for item in archive.infolist()]
        counts = Counter(names)
        if len(names) != len(counts):
            duplicates = sorted(name for name, count in counts.items() if count > 1)
            raise ReleaseError("Duplicate ZIP member names: " + ", ".join(duplicates))
        casefold_counts = Counter(name.casefold() for name in names)
        if len(casefold_counts) != len(names):
            duplicates = sorted(name for name, count in casefold_counts.items() if count > 1)
            raise ReleaseError("Case-insensitive ZIP filename collisions: " + ", ".join(duplicates))
        if archive.testzip() is not None:
            raise ReleaseError(f"ZIP CRC validation failed at member: {archive.testzip()}")
        for item in archive.infolist():
            name = item.filename
            if name.startswith("/") or "\\" in name or any(part in {"", ".", ".."} for part in name.rstrip("/").split("/")):
                raise ReleaseError(f"Unsafe ZIP member path: {name!r}")
            if not name.startswith(root_folder + "/"):
                raise ReleaseError(f"ZIP member is outside expected root folder {root_folder}/: {name}")
            relative_name = name[len(root_folder) + 1:]
            safe_repo_path(relative_name)
            if any(part.lower() == ".git" for part in name.split("/")):
                raise ReleaseError(f".git metadata found in ZIP: {name}")
            mode = (item.external_attr >> 16) & 0o170000
            if mode == stat.S_IFLNK:
                target = archive.read(name).decode("utf-8", "strict")
                if target.startswith("/") or "\\" in target or re.match(r"^[A-Za-z]:", target):
                    raise ReleaseError(f"Unsafe symlink in ZIP: {name} -> {target}")
                resolved = posixpath.normpath(posixpath.join(posixpath.dirname(name), target))
                if resolved == ".." or resolved.startswith("../") or resolved.startswith("/"):
                    raise ReleaseError(f"Symlink escapes archive root: {name} -> {target}")
                if resolved != root_folder and not resolved.startswith(root_folder + "/"):
                    raise ReleaseError(f"Symlink escapes the source root folder: {name} -> {target}")
        non_metadata = [name for name in names if not name.endswith("/")]
        if not non_metadata:
            raise ReleaseError("Source ZIP contains no files")
        if set(non_metadata) != expected_members:
            missing = sorted(expected_members - set(non_metadata))
            unexpected = sorted(set(non_metadata) - expected_members)
            raise ReleaseError(f"ZIP contents differ from the staged snapshot; missing={missing}, unexpected={unexpected}")
        if expected_changelog and expected_changelog not in {name[len(root_folder) + 1:] for name in non_metadata}:
            raise ReleaseError(f"Changelog path missing from ZIP despite archive policy: {expected_changelog}")
        return len(non_metadata)


def package() -> None:
    # Recompute deterministic names from the same validated ref context.
    repository, version, tag_label, prerelease, snapshot_ref = validate_tag_and_version()
    archive_name, root_folder = build_names(repository, version, tag_label)
    asset_mode = env("SOURCE_CHANGELOG_ASSET_MODE", "archive-only")
    changelog_path = env("SOURCE_CHANGELOG_PATH")
    changelog_path = safe_repo_path(changelog_path) if changelog_path else ""
    archive_path = RELEASE_ASSETS / archive_name
    if SOURCE_TREE.exists() is False:
        raise ReleaseError("source-tree staging directory is missing; prepare must run first")
    files = sorted(path for path in SOURCE_TREE.rglob("*") if path.is_file() or path.is_symlink())
    if not files:
        raise ReleaseError("Source tree is empty after exclusions")
    RELEASE_ASSETS.mkdir(parents=True, exist_ok=True)
    expected_members: set[str] = set()
    with zipfile.ZipFile(archive_path, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for path in files:
            rel = path.relative_to(SOURCE_TREE).as_posix()
            member_name = f"{root_folder}/{rel}"
            expected_members.add(member_name)
            zip_add_file(archive, path, member_name)

    expected_changelog = None
    if changelog_path and asset_mode in {"archive-only", "archive-and-asset"}:
        expected_changelog = changelog_path
    file_count = validate_zip(archive_path, root_folder, archive_name, expected_changelog, expected_members)

    changelog_asset_name = ""
    if changelog_path and asset_mode in {"archive-and-asset", "asset-only"}:
        changelog_asset_name = PurePosixPath(changelog_path).name
        changelog_asset_path = RELEASE_ASSETS / changelog_asset_name
        if not changelog_asset_path.is_file():
            raise ReleaseError(f"Separate changelog asset was expected but not staged: {changelog_asset_name}")
        if changelog_asset_path.resolve() == archive_path.resolve():
            raise ReleaseError("Changelog and source archive asset names collide")

    asset_paths = sorted(path for path in RELEASE_ASSETS.iterdir() if path.is_file() and path.name not in {"manifest.json", "SHA256SUMS"})
    if len({path.name.casefold() for path in asset_paths}) != len(asset_paths):
        raise ReleaseError("Case-insensitive release asset filename collision detected")
    reserved_asset_keys = {"manifest.json", "sha256sums", "release-notes.md"}
    colliding_reserved = sorted(path.name for path in asset_paths if path.name.casefold() in reserved_asset_keys)
    if colliding_reserved:
        raise ReleaseError("A release asset collides with a reserved filename: " + ", ".join(colliding_reserved))
    for path in asset_paths:
        if path.name == "release-notes.md":
            raise ReleaseError("release-notes.md is reserved for the release body and must not be an asset")

    archive_hash = sha256_file(archive_path)
    manifest = {
        "schema_version": 1,
        "project": env("GITHUB_REPOSITORY", repository),
        "version": version,
        "tag": tag_label,
        "snapshot_commit": snapshot_ref,
        "prerelease": prerelease,
        "archive": {
            "name": archive_name,
            "root_directory": root_folder,
            "sha256": archive_hash,
            "file_count": file_count,
            "files": sorted(member[len(root_folder) + 1:] for member in expected_members),
        },
        "changelog": {
            "path": changelog_path or None,
            "asset_mode": asset_mode,
            "separate_asset": changelog_asset_name or None,
        },
        "submodules": env("SOURCE_SUBMODULES", "fail-if-present"),
        "excluded_path_count": int(env("SOURCE_EXCLUDED_PATH_COUNT", "0") or "0"),
        "omitted_submodule_count": int(env("SOURCE_OMITTED_SUBMODULE_COUNT", "0") or "0"),
    }
    manifest_path = RELEASE_ASSETS / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    # Deterministic checksum list, using only release assets that are meant to be downloaded.
    checksum_targets = sorted(path for path in RELEASE_ASSETS.iterdir() if path.is_file() and path.name != "SHA256SUMS")
    checksum_lines = [f"{sha256_file(path)}  {path.name}" for path in checksum_targets]
    (RELEASE_ASSETS / "SHA256SUMS").write_text("\n".join(checksum_lines) + "\n", encoding="utf-8")

    # Re-open and verify the final checksum manifest and all asset hashes.
    for line in (RELEASE_ASSETS / "SHA256SUMS").read_text(encoding="utf-8").splitlines():
        expected, name = line.split("  ", 1)
        candidate = RELEASE_ASSETS / name
        if not candidate.is_file() or sha256_file(candidate) != expected:
            raise ReleaseError(f"SHA256 validation failed for release asset: {name}")
    print(f"Source archive validated: {archive_path} ({archive_path.stat().st_size} bytes, {file_count} files)")
    print("Release assets:")
    for path in sorted(RELEASE_ASSETS.iterdir()):
        if path.is_file():
            print(f"  - {path.name} ({path.stat().st_size} bytes)")
    write_outputs({"package_file_count": file_count, "archive_sha256": archive_hash})


def main() -> int:
    if len(sys.argv) != 2 or sys.argv[1] not in {"prepare", "package"}:
        print("Usage: scripts/source_release.py prepare|package", file=sys.stderr)
        return 2
    try:
        prepare() if sys.argv[1] == "prepare" else package()
    except ReleaseError as exc:
        message = str(exc).replace("%", "%25").replace("\r", "%0D").replace("\n", "%0A")
        print(f"::error title=Source Release validation failed::{message}", file=sys.stderr)
        print(f"Source Release failed: {exc}", file=sys.stderr)
        return 1
    except (OSError, zipfile.BadZipFile, UnicodeError) as exc:
        print(f"Source Release failed safely: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
