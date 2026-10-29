from __future__ import annotations
import json
import os
import re
import zipfile
from pathlib import Path, PurePosixPath
from .archive import sha256_file, validate_zip, zip_add_file
from .errors import ReleaseError
from .logger import logger
from .paths import safe_repo_path
from .release_meta import build_names, validate_tag_and_version
from .runtime import RELEASE_ASSETS, SOURCE_TREE, STATE
from .tools import atomic_write_text, env, write_outputs
from pipeline_core.context import PipelineContext


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
        "project": PipelineContext.from_environment().repository or repository,
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
    atomic_write_text(manifest_path, json.dumps(manifest, indent=2, sort_keys=True) + "\n")

    # Deterministic checksum list, using only release assets that are meant to be downloaded.
    checksum_targets = sorted(path for path in RELEASE_ASSETS.iterdir() if path.is_file() and path.name != "SHA256SUMS")
    checksum_lines = [f"{sha256_file(path)}  {path.name}" for path in checksum_targets]
    atomic_write_text(RELEASE_ASSETS / "SHA256SUMS", "\n".join(checksum_lines) + "\n")

    # Re-open and verify the final checksum manifest and all asset hashes.
    for line in (RELEASE_ASSETS / "SHA256SUMS").read_text(encoding="utf-8").splitlines():
        expected, name = line.split("  ", 1)
        candidate = RELEASE_ASSETS / name
        if not candidate.is_file() or sha256_file(candidate) != expected:
            raise ReleaseError(f"SHA256 validation failed for release asset: {name}")
    logger.info(f"Source archive validated: {archive_path} ({archive_path.stat().st_size} bytes, {file_count} files)", component="archive")
    logger.info("Release assets:", component="archive")
    for path in sorted(RELEASE_ASSETS.iterdir()):
        if path.is_file():
            logger.info(f"{path.name} ({path.stat().st_size} bytes)", component="asset")
    write_outputs({"package_file_count": file_count, "archive_sha256": archive_hash})
