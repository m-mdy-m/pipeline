#!/usr/bin/env python3
"""Prepare immutable, SHA-bound assets for a mutable rolling product release."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import stat
import sys
from pathlib import Path
from typing import Any

FULL_SHA = re.compile(r"^[0-9a-f]{40}$")
HEX_SHA256 = re.compile(r"^[0-9a-f]{64}$")
ARCHIVE_SUFFIXES = (".tar.gz", ".zip")


class RollingReleaseError(RuntimeError):
    """Raised when rolling-release inputs do not form one complete verified build."""


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _json_object(path: Path, label: str) -> dict[str, Any]:
    if path.is_symlink() or not path.is_file():
        raise RollingReleaseError(f"{label} is missing or unsafe: {path}")
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise RollingReleaseError(f"{label} is not valid UTF-8 JSON: {error}") from error
    if not isinstance(value, dict):
        raise RollingReleaseError(f"{label} root must be a JSON object")
    return value


def _safe_component(value: str, label: str) -> str:
    if not isinstance(value, str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._+-]{0,63}", value):
        raise RollingReleaseError(f"{label} is not a safe filename component: {value!r}")
    return value


def _target_id(target: Any) -> str:
    if not isinstance(target, dict):
        raise RollingReleaseError("package manifest has no target identity")
    os_name = target.get("os")
    architecture = target.get("architecture")
    abi = target.get("abi")
    if not all(isinstance(value, str) and value for value in (os_name, architecture, abi)):
        raise RollingReleaseError("package manifest target must identify OS, architecture and ABI")
    normalized_os = {"darwin": "macos"}.get(os_name, os_name)
    if normalized_os not in {"linux", "macos", "windows"}:
        raise RollingReleaseError(f"unsupported rolling-release target OS: {os_name}")
    if architecture not in {"x86_64", "arm64"}:
        raise RollingReleaseError(f"unsupported rolling-release architecture: {architecture}")
    if normalized_os == "windows" and (architecture != "x86_64" or abi != "windows-ucrt64"):
        raise RollingReleaseError("Windows rolling assets must use the x86_64 UCRT64 ABI")
    return f"{normalized_os}-{architecture}"


def _expected_pairs(value: str) -> set[tuple[str, str]]:
    try:
        raw = json.loads(value)
    except json.JSONDecodeError as error:
        raise RollingReleaseError(f"expected target/profile matrix is invalid JSON: {error}") from error
    if not isinstance(raw, list) or not raw:
        raise RollingReleaseError("expected target/profile matrix must be a non-empty JSON array")
    result: set[tuple[str, str]] = set()
    for item in raw:
        if not isinstance(item, dict):
            raise RollingReleaseError("expected target/profile matrix entries must be objects")
        target = item.get("target")
        profile = item.get("profile")
        if not isinstance(target, str) or not re.fullmatch(r"(linux|macos|windows)-(x86_64|arm64)", target):
            raise RollingReleaseError(f"invalid expected native target: {target!r}")
        if profile not in {"tui", "gui-sdl"}:
            raise RollingReleaseError(f"invalid expected product profile: {profile!r}")
        pair = (target, profile)
        if pair in result:
            raise RollingReleaseError(f"duplicate expected target/profile: {target}/{profile}")
        result.add(pair)
    return result


def _artifact_files(directory: Path) -> tuple[Path, Path, Path]:
    if directory.is_symlink() or not directory.is_dir():
        raise RollingReleaseError(f"artifact directory is missing or unsafe: {directory}")
    entries = sorted(directory.iterdir(), key=lambda path: path.name)
    if any(path.is_symlink() or not path.is_file() for path in entries):
        raise RollingReleaseError(f"artifact contains a symlink, directory or special file: {directory}")
    archives = [path for path in entries if path.name.endswith(ARCHIVE_SUFFIXES)]
    checksums = [path for path in entries if path.name.endswith(".sha256")]
    manifests = [path for path in entries if path.name.endswith(".manifest.json")]
    if len(entries) != 3 or len(archives) != 1 or len(checksums) != 1 or len(manifests) != 1:
        raise RollingReleaseError(
            f"artifact {directory.name} must contain exactly one archive, checksum and package manifest"
        )
    archive, checksum, manifest = archives[0], checksums[0], manifests[0]
    if checksum.name != archive.name + ".sha256":
        raise RollingReleaseError(f"checksum sidecar does not match archive name in {directory.name}")
    return archive, checksum, manifest


def prepare_rolling_assets(
    *,
    artifact_root: str | Path,
    output_directory: str | Path,
    repository: str,
    source_sha: str,
    source_run_id: str,
    source_run_attempt: str,
    product_prefix: str,
    expected_target_profiles: str,
) -> dict[str, Any]:
    """Verify every downloaded target artifact and create commit-qualified assets."""
    if not FULL_SHA.fullmatch(source_sha):
        raise RollingReleaseError("source SHA must be a full lowercase 40-character commit SHA")
    if not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", repository):
        raise RollingReleaseError("repository must use owner/name form")
    if not source_run_id.isdigit() or not source_run_attempt.isdigit():
        raise RollingReleaseError("workflow run ID and attempt must be positive decimal integers")
    product = _safe_component(product_prefix, "product prefix")
    expected = _expected_pairs(expected_target_profiles)
    root = Path(artifact_root)
    output = Path(output_directory)
    if root.is_symlink() or not root.is_dir():
        raise RollingReleaseError(f"downloaded artifact root is missing or unsafe: {root}")
    if output.exists() or output.is_symlink():
        if output.is_symlink() or not output.is_dir() or any(output.iterdir()):
            raise RollingReleaseError(f"rolling output directory must be empty: {output}")
    else:
        output.mkdir(parents=True, exist_ok=False)

    artifact_directories = sorted(root.iterdir(), key=lambda path: path.name)
    if len(artifact_directories) != len(expected):
        raise RollingReleaseError(
            f"expected {len(expected)} downloaded artifacts, found {len(artifact_directories)}"
        )

    seen: set[tuple[str, str]] = set()
    packages: list[dict[str, Any]] = []
    assets: list[dict[str, Any]] = []
    for directory in artifact_directories:
        archive, checksum, package_manifest_path = _artifact_files(directory)
        package_manifest = _json_object(package_manifest_path, "installed package manifest")
        package_sha = package_manifest.get("source_commit")
        target = package_manifest.get("target")
        target_id = _target_id(target)
        profile = package_manifest.get("profile")
        if profile not in {"tui", "gui-sdl"}:
            raise RollingReleaseError(f"unsupported package profile in {directory.name}: {profile!r}")
        pair = (target_id, profile)
        if pair not in expected:
            raise RollingReleaseError(f"unexpected target/profile artifact: {target_id}/{profile}")
        if pair in seen:
            raise RollingReleaseError(f"duplicate target/profile artifact: {target_id}/{profile}")
        seen.add(pair)
        if package_sha != source_sha:
            raise RollingReleaseError(
                f"{directory.name} was built from {package_sha!r}, expected {source_sha}"
            )

        archive_metadata = package_manifest.get("archive")
        if not isinstance(archive_metadata, dict):
            raise RollingReleaseError(f"{directory.name} package manifest has no archive object")
        digest = archive_metadata.get("sha256")
        size = archive_metadata.get("size_bytes")
        if (
            archive_metadata.get("name") != archive.name
            or not isinstance(digest, str)
            or not HEX_SHA256.fullmatch(digest)
            or not isinstance(size, int)
            or isinstance(size, bool)
            or size <= 0
        ):
            raise RollingReleaseError(f"{directory.name} package archive identity is incomplete")
        actual_size = archive.stat().st_size
        actual_digest = sha256_file(archive)
        if actual_size != size or actual_digest != digest:
            raise RollingReleaseError(f"{directory.name} archive size/digest does not match its manifest")
        try:
            sidecar = checksum.read_text(encoding="ascii").strip()
        except (OSError, UnicodeError) as error:
            raise RollingReleaseError(f"cannot read {checksum.name}: {error}") from error
        if sidecar != f"{digest}  {archive.name}":
            raise RollingReleaseError(f"{directory.name} checksum sidecar does not match its archive")

        version = package_manifest.get("version")
        if not isinstance(version, str) or not version:
            raise RollingReleaseError(f"{directory.name} package manifest has no product version")
        version_component = _safe_component(version, "product version")
        stem = f"rolling-{product}-{version_component}-{target_id}-{profile}-{source_sha}"
        archive_name = stem + (".zip" if archive.name.endswith(".zip") else ".tar.gz")
        checksum_name = archive_name + ".sha256"
        manifest_name = stem + ".manifest.json"

        updated_manifest = dict(package_manifest)
        updated_archive = dict(archive_metadata)
        updated_archive["name"] = archive_name
        updated_manifest["archive"] = updated_archive
        manifest_bytes = (json.dumps(updated_manifest, indent=2, sort_keys=True) + "\n").encode("utf-8")

        archive_destination = output / archive_name
        checksum_destination = output / checksum_name
        manifest_destination = output / manifest_name
        for source, destination in (
            (archive, archive_destination),
            (checksum, checksum_destination),
            (package_manifest_path, manifest_destination),
        ):
            if destination.exists() or destination.is_symlink():
                raise RollingReleaseError(f"duplicate rolling asset destination: {destination.name}")
        archive_destination.write_bytes(archive.read_bytes())
        checksum_destination.write_text(f"{digest}  {archive_name}\n", encoding="ascii")
        manifest_destination.write_bytes(manifest_bytes)

        for path, kind in (
            (archive_destination, "application-archive"),
            (checksum_destination, "sha256-checksum"),
            (manifest_destination, "package-manifest"),
        ):
            assets.append({
                "name": path.name,
                "kind": kind,
                "target": target_id,
                "profile": profile,
                "size_bytes": path.stat().st_size,
                "sha256": sha256_file(path),
            })

        registry_digest = package_manifest.get("registry_manifest_sha256")
        packages.append({
            "target": target_id,
            "target_identity": target,
            "profile": profile,
            "product_version": version,
            "registry_version": package_manifest.get("registry_version"),
            "registry_manifest_sha256": registry_digest,
            "archive": {
                "name": archive_name,
                "size_bytes": actual_size,
                "sha256": actual_digest,
            },
            "checksum": checksum_name,
            "package_manifest": manifest_name,
            "components": package_manifest.get("components", []),
            "environment_contracts": package_manifest.get("environment_contracts", []),
            "build_dependencies": package_manifest.get("build_dependencies", {}),
        })

    missing = expected - seen
    if missing:
        formatted = ", ".join(f"{target}/{profile}" for target, profile in sorted(missing))
        raise RollingReleaseError(f"rolling build is missing required target/profile artifacts: {formatted}")

    manifest_name = f"rolling-{product}-latest-manifest-{source_sha}.json"
    manifest = {
        "schema_version": 1,
        "channel": "latest",
        "prerelease": True,
        "product": product,
        "repository": repository,
        "source_commit": source_sha,
        "workflow_run": {
            "id": int(source_run_id),
            "attempt": int(source_run_attempt),
        },
        "target_profiles": [
            {"target": target, "profile": profile}
            for target, profile in sorted(expected)
        ],
        "packages": sorted(packages, key=lambda item: (item["target"], item["profile"])),
        "assets": sorted(assets, key=lambda item: item["name"]),
    }
    manifest_path = output / manifest_name
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    manifest_digest = sha256_file(manifest_path)
    sidecar_path = output / (manifest_name + ".sha256")
    sidecar_path.write_text(f"{manifest_digest}  {manifest_name}\n", encoding="ascii")
    manifest["manifest_asset"] = {
        "name": manifest_name,
        "size_bytes": manifest_path.stat().st_size,
        "sha256": manifest_digest,
        "checksum": sidecar_path.name,
    }
    # Rewriting the manifest after adding its own identity would be recursive;
    # the sidecar and manifest_asset are therefore emitted in a small envelope.
    # Keep the asset's own digest in the workflow output/Release body, not inside itself.
    return {
        "manifest": str(manifest_path),
        "manifest_name": manifest_name,
        "manifest_sha256": manifest_digest,
        "manifest_size_bytes": manifest_path.stat().st_size,
        "manifest_checksum": str(sidecar_path),
        "source_commit": source_sha,
        "repository": repository,
        "asset_count": len(assets) + 2,
        "assets": sorted(assets, key=lambda item: item["name"]),
        "packages": sorted(packages, key=lambda item: (item["target"], item["profile"])),
        "output_directory": str(output),
    }


def verify_rolling_assets(
    *,
    output_directory: str | Path,
    manifest_name: str,
    source_sha: str,
    repository: str,
    expected_target_profiles: str,
) -> dict[str, Any]:
    """Recheck the complete local publication bundle immediately before upload."""
    if not FULL_SHA.fullmatch(source_sha):
        raise RollingReleaseError("source SHA must be a full lowercase 40-character commit SHA")
    root = Path(output_directory)
    manifest_path = root / manifest_name
    manifest = _json_object(manifest_path, "rolling release manifest")
    if (
        manifest.get("channel") != "latest"
        or manifest.get("prerelease") is not True
        or manifest.get("source_commit") != source_sha
        or manifest.get("repository") != repository
    ):
        raise RollingReleaseError("rolling release manifest identity does not match this promotion")
    expected = _expected_pairs(expected_target_profiles)
    actual = {
        (item.get("target"), item.get("profile"))
        for item in manifest.get("target_profiles", [])
        if isinstance(item, dict)
    }
    if actual != expected:
        raise RollingReleaseError("rolling release manifest target/profile inventory is incomplete or unexpected")
    records = manifest.get("assets")
    if not isinstance(records, list) or not records:
        raise RollingReleaseError("rolling release manifest has no asset inventory")
    seen: set[str] = set()
    for record in records:
        if not isinstance(record, dict):
            raise RollingReleaseError("rolling release manifest contains an invalid asset record")
        name = record.get("name")
        digest = record.get("sha256")
        size = record.get("size_bytes")
        if (
            not isinstance(name, str)
            or Path(name).name != name
            or name in {".", ".."}
            or not isinstance(digest, str)
            or not HEX_SHA256.fullmatch(digest)
            or not isinstance(size, int)
            or isinstance(size, bool)
            or size <= 0
            or name in seen
        ):
            raise RollingReleaseError("rolling release manifest contains an unsafe or duplicate asset")
        seen.add(name)
        path = root / name
        if path.is_symlink() or not path.is_file():
            raise RollingReleaseError(f"rolling release asset is missing or unsafe: {name}")
        if path.stat().st_size != size or sha256_file(path) != digest:
            raise RollingReleaseError(f"rolling release asset digest/size mismatch: {name}")
    checksum_path = root / (manifest_name + ".sha256")
    expected_manifest_digest = sha256_file(manifest_path)
    if checksum_path.is_symlink() or not checksum_path.is_file():
        raise RollingReleaseError("rolling release manifest checksum is missing or unsafe")
    if checksum_path.read_text(encoding="ascii").strip() != f"{expected_manifest_digest}  {manifest_name}":
        raise RollingReleaseError("rolling release manifest checksum does not match its bytes")
    expected_files = seen | {manifest_name, manifest_name + ".sha256"}
    actual_files = {
        path.name for path in root.iterdir()
        if path.is_file() and not path.is_symlink()
    }
    if actual_files != expected_files:
        raise RollingReleaseError(
            f"rolling output contains untracked or missing files: expected={sorted(expected_files)}, actual={sorted(actual_files)}"
        )
    return {
        "source_commit": source_sha,
        "asset_count": len(actual_files),
        "manifest_sha256": expected_manifest_digest,
        "asset_names": sorted(actual_files),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    prepare = commands.add_parser("prepare", help="verify downloaded target artifacts and prepare rolling assets")
    for name, required in (
        ("artifact-root", True),
        ("output-directory", True),
        ("repository", True),
        ("source-sha", True),
        ("source-run-id", True),
        ("source-run-attempt", True),
        ("product-prefix", True),
        ("expected-target-profiles", True),
    ):
        prepare.add_argument(f"--{name}", required=required)
    verify = commands.add_parser("verify", help="verify the prepared rolling publication bundle")
    for name in ("output-directory", "manifest-name", "source-sha", "repository", "expected-target-profiles"):
        verify.add_argument(f"--{name}", required=True)
    args = parser.parse_args(argv)
    try:
        if args.command == "prepare":
            result = prepare_rolling_assets(
                artifact_root=args.artifact_root,
                output_directory=args.output_directory,
                repository=args.repository,
                source_sha=args.source_sha,
                source_run_id=args.source_run_id,
                source_run_attempt=args.source_run_attempt,
                product_prefix=args.product_prefix,
                expected_target_profiles=args.expected_target_profiles,
            )
        else:
            result = verify_rolling_assets(
                output_directory=args.output_directory,
                manifest_name=args.manifest_name,
                source_sha=args.source_sha,
                repository=args.repository,
                expected_target_profiles=args.expected_target_profiles,
            )
    except (RollingReleaseError, OSError, ValueError) as error:
        print(f"rolling release preparation failed: {error}", file=sys.stderr)
        return 1
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
