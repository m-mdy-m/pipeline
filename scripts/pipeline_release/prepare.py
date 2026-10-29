from __future__ import annotations
import os
import shutil
from pathlib import Path, PurePosixPath
from typing import Iterable, Sequence


from .changelog import decode_changelog, detect_changelog, extract_unreleased_section, extract_version_section, heading_info
from .errors import ReleaseError
from .git_snapshot import collect_entries, read_blob
from .logger import logger
from .models import TreeEntry
from .paths import any_pattern, safe_repo_path, validate_patterns, validate_symlinks
from .release_meta import build_names, validate_tag_and_version
from .runtime import DEFAULT_SENSITIVE_ALLOWLIST, DEFAULT_SENSITIVE_PATTERNS, REPO_ROOT, RELEASE_ASSETS, REPORTS, SCAN_TREE, SOURCE_TREE, STATE, WORK_DIR
from .security import compose_gitleaks_config, validate_allowlist_path
from .tools import atomic_write_text, env, git_output, parse_lines, run_git, write_outputs
from pipeline_core.context import PipelineContext


def clear_staging() -> None:
    WORK_DIR.mkdir(parents=True, exist_ok=True)
    for folder in (SOURCE_TREE, SCAN_TREE, RELEASE_ASSETS, REPORTS):
        if folder.exists():
            shutil.rmtree(folder)
        folder.mkdir(parents=True, exist_ok=True)


def prepare() -> None:
    STATE.token_to_redact = env("PIPELINE_SECRET_REDACTIONS")
    STATE.omitted_submodules.clear()
    repository, version, tag_label, prerelease, snapshot_ref = validate_tag_and_version()
    archive_name, root_folder = build_names(repository, version, tag_label)
    submodule_mode = env("SOURCE_SUBMODULES", "fail-if-present")
    if submodule_mode not in {"fail-if-present", "recursive", "omit"}:
        raise ReleaseError("source-submodules must be one of: fail-if-present, recursive, omit")
    if submodule_mode == "recursive":
        # Authentication is configured by the selected provider adapter. Core
        # only inherits standard Git configuration environment variables.
        logger.info("Initializing submodules at the exact commits pinned by the tag", component="submodules")
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
    dry_run_branch = env("SOURCE_DRY_RUN", "false").lower() == "true" and PipelineContext.from_environment(workspace=REPO_ROOT).ref_type != "tag"
    if not changelog_nonempty:
        reason = "not found" if changelog_entry is None else "empty or whitespace-only"
        if missing_policy == "fail":
            raise ReleaseError(f"Changelog is {reason}; configure changelog-missing-policy: warn to allow omission")
        if asset_mode == "asset-only":
            raise ReleaseError("changelog-asset-mode: asset-only requires a non-empty changelog")
        logger.warning(f"Changelog {reason}; continuing because policy is warn", component="changelog")
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
        logger.warning("Tracked paths excluded by source-exclude-patterns:", component="exclusions")
        for path in sorted(excluded):
            logger.warning(f"Excluded tracked path: {path}", component="exclusions")
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
    atomic_write_text(WORK_DIR / "release-notes.md", notes_text)

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
        "omitted_submodule_count": len(STATE.omitted_submodules),
    })
    logger.info(f"Prepared source snapshot {snapshot_ref}; {len(archived_entries)} archived files; root={root_folder}/", component="prepare")
