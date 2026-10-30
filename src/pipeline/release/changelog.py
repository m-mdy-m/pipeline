from __future__ import annotations
import re
from typing import Sequence
from .errors import ReleaseError
from .git_snapshot import read_blob
from .models import TreeEntry
from .paths import safe_repo_path
from .runtime import SEMVER_RE


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


def extract_dry_run_section(changelog: str, path: str) -> str:
    """Resolve branch dry-run notes without requiring an Unreleased heading.

    Keep an explicit Unreleased section authoritative. For release-only
    changelogs, use the first versioned section (Keep a Changelog order is
    newest first) as the informational dry-run notes.
    """
    unreleased_count = sum(
        bool(re.match(r"^\\s{0,3}(#{1,6})\\s+\\[?Unreleased\\]?\\s*$", line, re.IGNORECASE))
        for line in changelog.splitlines()
    )
    if unreleased_count:
        return extract_unreleased_section(changelog, path)

    for line in changelog.splitlines():
        _, version = heading_info(line)
        if version is not None:
            return extract_version_section(changelog, version, path)

    raise ReleaseError(
        f"Dry-run changelog '{path}' must contain an 'Unreleased' section "
        "or at least one version-specific section."
    )
