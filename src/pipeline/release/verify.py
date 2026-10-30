"""Post-download verifier for source-release assets."""
from __future__ import annotations

import json
import re
import zipfile
from pathlib import Path
from typing import Any

from .archive import validate_zip
from .errors import ReleaseError
from ..common.logging import logger


def verify_bundle(directory: Path) -> dict[str, Any]:
    """Validate manifest, checksum inventory and source ZIP member list."""
    root = directory.resolve()
    if not root.is_dir():
        raise ReleaseError(f"Bundle directory does not exist: {root}")
    manifest_path, sums_path = root / "manifest.json", root / "SHA256SUMS"
    if not manifest_path.is_file() or not sums_path.is_file():
        raise ReleaseError("Bundle must contain manifest.json and SHA256SUMS")
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ReleaseError(f"manifest.json is not valid UTF-8 JSON: {exc}") from exc
    if manifest.get("schema_version") != 1:
        raise ReleaseError(f"Unsupported source manifest schema: {manifest.get('schema_version')!r}")
    archive_meta = manifest.get("archive")
    if not isinstance(archive_meta, dict):
        raise ReleaseError("manifest.json is missing the archive object")
    name, root_folder = archive_meta.get("name"), archive_meta.get("root_directory")
    recorded_hash, recorded_files = archive_meta.get("sha256"), archive_meta.get("files")
    if not isinstance(name, str) or Path(name).name != name or not name.endswith(".zip"):
        raise ReleaseError("Manifest archive name is not a ZIP basename")
    if not isinstance(root_folder, str) or not root_folder or "/" in root_folder or "\\" in root_folder:
        raise ReleaseError("Manifest ZIP root_directory is invalid")
    if not isinstance(recorded_hash, str) or not re.fullmatch(r"[0-9a-f]{64}", recorded_hash):
        raise ReleaseError("Manifest archive SHA-256 is invalid")
    if not isinstance(recorded_files, list) or not all(isinstance(value, str) for value in recorded_files):
        raise ReleaseError("Manifest archive files must be a list of paths")
    if len({value.casefold() for value in recorded_files}) != len(recorded_files):
        raise ReleaseError("Manifest contains duplicate case-insensitive paths")
    archive_path = root / name
    if not archive_path.is_file():
        raise ReleaseError(f"Source ZIP is missing: {name}")
    if _sha256(archive_path) != recorded_hash:
        raise ReleaseError(f"Manifest SHA-256 mismatch for {name}")

    checksums: dict[str, str] = {}
    for line_no, line in enumerate(sums_path.read_text(encoding="utf-8").splitlines(), 1):
        parts = line.split("  ", 1)
        if len(parts) != 2:
            raise ReleaseError(f"Malformed SHA256SUMS line {line_no}")
        digest, asset_name = parts
        if not re.fullmatch(r"[0-9a-f]{64}", digest):
            raise ReleaseError(f"Malformed SHA-256 on SHA256SUMS line {line_no}")
        if not asset_name or Path(asset_name).name != asset_name or asset_name in {".", "..", "SHA256SUMS"}:
            raise ReleaseError(f"Unsafe asset name in SHA256SUMS line {line_no}: {asset_name!r}")
        if asset_name.casefold() in {existing.casefold() for existing in checksums}:
            raise ReleaseError(f"Duplicate checksum entry: {asset_name}")
        checksums[asset_name] = digest
    actual_assets = {path.name for path in root.iterdir() if path.is_file() and path.name != "SHA256SUMS"}
    if set(checksums) != actual_assets:
        raise ReleaseError(
            f"Asset inventory differs from SHA256SUMS; unlisted={sorted(actual_assets-set(checksums))}, "
            f"missing={sorted(set(checksums)-actual_assets)}"
        )
    for asset_name, expected in checksums.items():
        if _sha256(root / asset_name) != expected:
            raise ReleaseError(f"SHA256 validation failed for asset: {asset_name}")
    if checksums.get(name) != recorded_hash or "manifest.json" not in checksums:
        raise ReleaseError("SHA256SUMS must cover the source ZIP and manifest.json")

    members: set[str] = set()
    for relative in recorded_files:
        if not relative or relative.startswith("/") or "\\" in relative or any(part in {"", ".", ".."} for part in relative.split("/")):
            raise ReleaseError(f"Unsafe relative path in manifest: {relative!r}")
        members.add(f"{root_folder}/{relative}")
    count = validate_zip(archive_path, root_folder, name, None, members)
    result = {
        "project": manifest.get("project"), "tag": manifest.get("tag"), "version": manifest.get("version"),
        "archive": name, "archive_sha256": recorded_hash, "archive_file_count": count,
        "verified_assets": len(checksums),
    }
    logger.info(f"Verified source bundle {name}: {count} files, {len(checksums)} assets",
                component="bundle-verifier", status="ok")
    return result


def main(argv: list[str] | None = None) -> int:
    import argparse
    parser = argparse.ArgumentParser(description="Verify a downloaded pipeline Source Release bundle")
    parser.add_argument("directory", nargs="?", default=".", help="directory containing release assets and SHA256SUMS")
    args = parser.parse_args(argv)
    try:
        result = verify_bundle(Path(args.directory))
    except (ReleaseError, OSError, UnicodeError, zipfile.BadZipFile, json.JSONDecodeError) as exc:
        logger.error(str(exc), component="bundle-verifier", status="failed")
        return 1
    for key, value in result.items():
        logger.info(f"{key}: {value}", component="bundle-verifier")
    return 0
