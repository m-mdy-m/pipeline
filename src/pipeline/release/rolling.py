"""Validated rolling development-release artifact preparation.

This module only prepares and verifies candidate assets. The workflow owns
GitHub tag/release mutation and freshness/rollback orchestration.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any, Callable, Iterable

FULL_SHA = re.compile(r"^[0-9a-f]{40}$")
RUN_ID = re.compile(r"^[0-9]+$")
DEFAULT_GROUPS = {
    ("Linux", "tui"),
    ("Linux", "gui-sdl"),
    ("macOS", "tui"),
    ("macOS", "gui-sdl"),
    ("Windows", "tui"),
    ("Windows", "gui-sdl"),
}
OS_NAMES = {"Linux": "linux", "macOS": "darwin", "Windows": "windows"}


class RollingReleaseError(RuntimeError):
    """Raised when a rolling release candidate is incomplete or inconsistent."""


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _read_json(path: Path, label: str) -> dict[str, Any]:
    if path.is_symlink() or not path.is_file():
        raise RollingReleaseError(f"{label} is missing or unsafe: {path}")
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise RollingReleaseError(f"{label} is not valid UTF-8 JSON: {error}") from error
    if not isinstance(value, dict):
        raise RollingReleaseError(f"{label} root must be a JSON object")
    return value


def _regular_files(root: Path) -> list[Path]:
    if root.is_symlink() or not root.is_dir():
        raise RollingReleaseError(f"artifact group is missing or unsafe: {root}")
    result: list[Path] = []
    for path in sorted(root.rglob("*"), key=lambda item: item.relative_to(root).as_posix()):
        if path.is_symlink():
            raise RollingReleaseError(f"artifact group contains a symlink: {path.relative_to(root)}")
        if path.is_file():
            result.append(path)
        elif not path.is_dir():
            raise RollingReleaseError(f"artifact group contains a special file: {path.relative_to(root)}")
    return result


def _check_checksum_sidecar(sidecar: Path, archive: Path, expected: str) -> None:
    try:
        actual = sidecar.read_text(encoding="ascii")
    except (OSError, UnicodeError) as error:
        raise RollingReleaseError(f"cannot read checksum sidecar {sidecar.name}: {error}") from error
    required = f"{expected}  {archive.name}\n"
    if actual != required:
        raise RollingReleaseError(f"checksum sidecar mismatch for {archive.name}")


def _validate_group(
    group_path: Path,
    *,
    runner_os: str,
    profile: str,
    source_commit: str,
    source_run_id: str,
    source_run_attempt: str,
) -> dict[str, Any]:
    files = _regular_files(group_path)
    archives = [path for path in files if path.name.endswith((".tar.gz", ".zip"))]
    sidecars = [path for path in files if path.name.endswith((".tar.gz.sha256", ".zip.sha256"))]
    manifests = [path for path in files if path.name.endswith(".manifest.json")]
    if len(archives) != 1 or len(sidecars) != 1 or len(manifests) != 1 or len(files) != 3:
        raise RollingReleaseError(
            f"{group_path.name} must contain exactly one archive, one .sha256 sidecar "
            "and one .manifest.json"
        )
    archive, sidecar, manifest_path = archives[0], sidecars[0], manifests[0]
    expected_extension = ".zip" if runner_os == "Windows" else ".tar.gz"
    if not archive.name.endswith(expected_extension):
        raise RollingReleaseError(
            f"{runner_os} {profile} archive must use {expected_extension}: {archive.name}"
        )
    manifest = _read_json(manifest_path, "distribution manifest")
    if manifest.get("product") != "com.cdin.editor" or manifest.get("schema_version") != 1:
        raise RollingReleaseError(f"unsupported distribution manifest: {manifest_path.name}")
    if manifest.get("source_commit") != source_commit:
        raise RollingReleaseError(f"source commit mismatch in {manifest_path.name}")
    if manifest.get("profile") != profile:
        raise RollingReleaseError(f"profile mismatch in {manifest_path.name}")
    workflow = manifest.get("workflow")
    if (
        not isinstance(workflow, dict)
        or str(workflow.get("run_id", "")) != source_run_id
        or str(workflow.get("run_attempt", "")) != source_run_attempt
    ):
        raise RollingReleaseError(f"source workflow run identity mismatch in {manifest_path.name}")
    target = manifest.get("target")
    if not isinstance(target, dict) or target.get("os") != OS_NAMES[runner_os]:
        raise RollingReleaseError(f"target OS mismatch in {manifest_path.name}")
    if target.get("architecture") not in {"x86_64", "arm64"} or not isinstance(target.get("abi"), str):
        raise RollingReleaseError(f"target ABI/architecture missing in {manifest_path.name}")
    archive_info = manifest.get("archive")
    if not isinstance(archive_info, dict):
        raise RollingReleaseError(f"archive record missing in {manifest_path.name}")
    expected_digest = archive_info.get("sha256")
    expected_size = archive_info.get("size_bytes")
    if archive_info.get("name") != archive.name:
        raise RollingReleaseError(f"archive filename mismatch in {manifest_path.name}")
    if not isinstance(expected_digest, str) or not re.fullmatch(r"[0-9a-f]{64}", expected_digest):
        raise RollingReleaseError(f"archive SHA-256 missing in {manifest_path.name}")
    if not isinstance(expected_size, int) or expected_size <= 0 or archive.stat().st_size != expected_size:
        raise RollingReleaseError(f"archive byte size mismatch in {manifest_path.name}")
    actual_digest = sha256_file(archive)
    if actual_digest != expected_digest:
        raise RollingReleaseError(f"archive SHA-256 mismatch in {manifest_path.name}")
    _check_checksum_sidecar(sidecar, archive, expected_digest)
    registry_digest = manifest.get("registry_manifest_sha256")
    if not isinstance(registry_digest, str) or not re.fullmatch(r"[0-9a-f]{64}", registry_digest):
        raise RollingReleaseError(f"Registry Manifest SHA-256 missing in {manifest_path.name}")
    components = manifest.get("components")
    if not isinstance(components, list) or not components:
        raise RollingReleaseError(f"selected component inventory missing in {manifest_path.name}")
    return {
        "runner_os": runner_os,
        "profile": profile,
        "target": target,
        "version": manifest.get("version"),
        "archive_path": archive,
        "archive_sha256": expected_digest,
        "archive_size_bytes": expected_size,
        "registry_manifest_sha256": registry_digest,
        "components": components,
        "source_commit": source_commit,
        "source_run_id": source_run_id,
        "source_run_attempt": workflow.get("run_attempt"),
    }


def _atomic_json(path: Path, value: dict[str, Any]) -> None:
    payload = (json.dumps(value, indent=2, sort_keys=True) + "\n").encode("utf-8")
    temporary = path.with_name(path.name + ".tmp")
    if temporary.exists() or temporary.is_symlink():
        raise RollingReleaseError(f"temporary output already exists: {temporary}")
    try:
        temporary.write_bytes(payload)
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def prepare_rolling_assets(
    *,
    downloaded_root: Path,
    output_root: Path,
    source_commit: str,
    source_run_id: str,
    source_run_attempt: str,
    expected_groups: Iterable[tuple[str, str]] = DEFAULT_GROUPS,
) -> dict[str, Any]:
    """Validate all expected CI artifacts and build uniquely named latest assets."""
    source_commit = source_commit.lower()
    if not FULL_SHA.fullmatch(source_commit):
        raise RollingReleaseError("source commit must be a full 40-character SHA")
    if not RUN_ID.fullmatch(source_run_id) or not RUN_ID.fullmatch(source_run_attempt):
        raise RollingReleaseError("source workflow run ID and attempt must be decimal integers")
    if downloaded_root.is_symlink() or not downloaded_root.is_dir():
        raise RollingReleaseError(f"downloaded artifacts are missing or unsafe: {downloaded_root}")
    if output_root.exists() or output_root.is_symlink():
        raise RollingReleaseError(f"rolling asset output already exists: {output_root}")
    output_root.mkdir(parents=True)
    expected = set(expected_groups)
    if expected != DEFAULT_GROUPS:
        if not expected or any((os_name not in OS_NAMES or profile not in {"tui", "gui-sdl"}) for os_name, profile in expected):
            raise RollingReleaseError("expected artifact groups contain an unsupported OS/profile")
    groups: dict[tuple[str, str], Path] = {}
    for path in sorted(downloaded_root.iterdir(), key=lambda item: item.name):
        if path.is_symlink() or not path.is_dir():
            raise RollingReleaseError(f"unexpected downloaded artifact entry: {path.name}")
        prefix = "cdin-installed-product-"
        if not path.name.startswith(prefix):
            raise RollingReleaseError(f"unexpected downloaded artifact name: {path.name}")
        label = path.name[len(prefix):]
        matched = [(os_name, profile) for os_name, profile in expected if label == f"{os_name}-{profile}"]
        if len(matched) != 1:
            raise RollingReleaseError(f"unexpected or duplicate product artifact group: {path.name}")
        groups[matched[0]] = path
    missing = sorted(expected - set(groups))
    if missing:
        raise RollingReleaseError(f"product matrix is incomplete; missing groups: {missing}")

    short_sha = source_commit[:12]
    artifact_rows: list[dict[str, Any]] = []
    asset_rows: list[dict[str, Any]] = []
    for runner_os, profile in sorted(expected):
        record = _validate_group(
            groups[(runner_os, profile)],
            runner_os=runner_os,
            profile=profile,
            source_commit=source_commit,
            source_run_id=source_run_id,
            source_run_attempt=source_run_attempt,
        )
        target = record["target"]
        slug = f"{target['os']}-{target['architecture']}-{profile}"
        suffix = ".zip" if target["os"] == "windows" else ".tar.gz"
        archive_name = f"cdin-latest-{slug}-{short_sha}-{source_run_id}{suffix}"
        archive_destination = output_root / archive_name
        shutil.copyfile(record["archive_path"], archive_destination)
        archive_digest = sha256_file(archive_destination)
        sidecar_name = archive_name + ".sha256"
        (output_root / sidecar_name).write_text(
            f"{archive_digest}  {archive_name}\n", encoding="ascii"
        )
        artifact_rows.append({
            "runner_os": runner_os,
            "target": target,
            "profile": profile,
            "product_version": record["version"],
            "archive": archive_name,
            "size_bytes": archive_destination.stat().st_size,
            "sha256": archive_digest,
            "registry_manifest_sha256": record["registry_manifest_sha256"],
            "components": record["components"],
        })
        asset_rows.extend([
            {"name": archive_name, "size": archive_destination.stat().st_size, "sha256": archive_digest},
            {"name": sidecar_name, "size": (output_root / sidecar_name).stat().st_size,
             "sha256": sha256_file(output_root / sidecar_name)},
        ])

    manifest_name = f"latest-manifest-{short_sha}-{source_run_id}.json"
    manifest = {
        "schema_version": 1,
        "product": "com.cdin.editor",
        "channel": "latest",
        "prerelease": True,
        "status": "development",
        "source_commit": source_commit,
        "source_run": {
            "id": source_run_id,
            "attempt": source_run_attempt,
            "workflow": "CI",
            "branch": "main",
        },
        "artifacts": artifact_rows,
    }
    manifest_path = output_root / manifest_name
    _atomic_json(manifest_path, manifest)
    asset_rows.append({
        "name": manifest_name, "size": manifest_path.stat().st_size,
        "sha256": sha256_file(manifest_path),
    })
    sums_name = f"SHA256SUMS-latest-{short_sha}-{source_run_id}.txt"
    sums_path = output_root / sums_name
    with sums_path.open("w", encoding="ascii", newline="\n") as stream:
        for item in sorted(asset_rows, key=lambda row: row["name"]):
            stream.write(f"{item['sha256']}  {item['name']}\n")
    asset_rows.append({
        "name": sums_name, "size": sums_path.stat().st_size,
        "sha256": sha256_file(sums_path),
    })
    inventory = {
        "schema_version": 1,
        "source_commit": source_commit,
        "source_run_id": source_run_id,
        "assets": sorted(asset_rows, key=lambda row: row["name"]),
        "manifest": manifest_name,
        "checksums": sums_name,
    }
    inventory_path = output_root.parent / "rolling-inventory.json"
    _atomic_json(inventory_path, inventory)
    return inventory


def verify_remote_assets(
    inventory: dict[str, Any],
    remote_assets: Iterable[dict[str, Any]],
) -> None:
    """Require every candidate asset to exist remotely with exact digest and size."""
    expected = {
        item["name"]: item
        for item in inventory.get("assets", [])
        if isinstance(item, dict) and isinstance(item.get("name"), str)
    }
    if not expected:
        raise RollingReleaseError("candidate asset inventory is empty")
    actual = {
        item.get("name"): item
        for item in remote_assets
        if isinstance(item, dict) and isinstance(item.get("name"), str)
    }
    missing = sorted(set(expected) - set(actual))
    if missing:
        raise RollingReleaseError(f"uploaded rolling assets are missing: {missing}")
    for name, expected_item in expected.items():
        remote = actual[name]
        digest = remote.get("digest")
        if digest != f"sha256:{expected_item['sha256']}" or remote.get("size") != expected_item["size"]:
            raise RollingReleaseError(f"remote asset digest/size mismatch: {name}")


def latest_action(
    *,
    current_latest: str | None,
    candidate: str,
    main_head: str,
    candidate_run_id: str,
    candidate_run_attempt: str,
    latest_successful_run_id: str,
    latest_successful_run_attempt: str,
    is_ancestor: Callable[[str, str], bool],
) -> str:
    """Decide whether a successful CI run may advance the rolling channel.

    A completed older run may not publish after a newer successful main-branch
    CI run, even when its commit is still an ancestor of main.
    """
    if not FULL_SHA.fullmatch(candidate) or not FULL_SHA.fullmatch(main_head):
        raise RollingReleaseError("candidate and main head must be full commit SHAs")
    if not is_ancestor(candidate, main_head):
        raise RollingReleaseError("candidate commit is not an ancestor of current main")
    if not RUN_ID.fullmatch(candidate_run_id) or not RUN_ID.fullmatch(latest_successful_run_id):
        raise RollingReleaseError("workflow run IDs must be decimal integers")
    if not RUN_ID.fullmatch(candidate_run_attempt) or not RUN_ID.fullmatch(latest_successful_run_attempt):
        raise RollingReleaseError("workflow run attempts must be decimal integers")
    if (candidate_run_id, candidate_run_attempt) != (
        latest_successful_run_id, latest_successful_run_attempt
    ):
        return "stale"
    if current_latest is None:
        return "publish"
    if not FULL_SHA.fullmatch(current_latest):
        raise RollingReleaseError("current latest tag does not resolve to a full commit SHA")
    if candidate == current_latest:
        return "already-current"
    if is_ancestor(candidate, current_latest):
        return "stale"
    if is_ancestor(current_latest, candidate):
        return "publish"
    raise RollingReleaseError("candidate and current latest are not on the same mainline")


def _load_remote_assets(path: Path) -> list[dict[str, Any]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(payload, list):
        if all(isinstance(page, list) for page in payload):
            return [item for page in payload for item in page]
        if all(isinstance(item, dict) for item in payload):
            return payload
    if isinstance(payload, dict) and isinstance(payload.get("assets"), list):
        return payload["assets"]
    raise RollingReleaseError("remote asset JSON must be an array or a paginated array")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    prepare = sub.add_parser("prepare", help="validate the successful CI run artifacts")
    prepare.add_argument("--downloaded-root", type=Path, required=True)
    prepare.add_argument("--output-root", type=Path, required=True)
    prepare.add_argument("--source-commit", required=True)
    prepare.add_argument("--source-run-id", required=True)
    prepare.add_argument("--source-run-attempt", required=True)
    verify = sub.add_parser("verify-remote", help="verify GitHub's published asset inventory")
    verify.add_argument("--inventory", type=Path, required=True)
    verify.add_argument("--remote-assets", type=Path, required=True)
    freshness = sub.add_parser("freshness", help="prevent stale successful CI runs from moving latest")
    freshness.add_argument("--current-latest", default="")
    freshness.add_argument("--candidate", required=True)
    freshness.add_argument("--main-head", required=True)
    freshness.add_argument("--candidate-run-id", required=True)
    freshness.add_argument("--candidate-run-attempt", required=True)
    freshness.add_argument("--latest-successful-run-id", required=True)
    freshness.add_argument("--latest-successful-run-attempt", required=True)
    args = parser.parse_args(argv)
    try:
        if args.command == "prepare":
            result = prepare_rolling_assets(
                downloaded_root=args.downloaded_root,
                output_root=args.output_root,
                source_commit=args.source_commit,
                source_run_id=args.source_run_id,
                source_run_attempt=args.source_run_attempt,
            )
            print(json.dumps(result, indent=2, sort_keys=True))
        elif args.command == "verify-remote":
            inventory = _read_json(args.inventory, "rolling inventory")
            remote = _load_remote_assets(args.remote_assets)
            verify_remote_assets(inventory, remote)
            print(f"Verified {len(inventory['assets'])} uploaded rolling assets.")
        else:
            def is_ancestor(parent: str, child: str) -> bool:
                result = subprocess.run(
                    ["git", "merge-base", "--is-ancestor", parent, child],
                    check=False,
                    capture_output=True,
                    text=True,
                )
                if result.returncode not in (0, 1):
                    raise RollingReleaseError(result.stderr.strip() or "git merge-base failed")
                return result.returncode == 0

            decision = latest_action(
                current_latest=args.current_latest or None,
                candidate=args.candidate,
                main_head=args.main_head,
                candidate_run_id=args.candidate_run_id,
                candidate_run_attempt=args.candidate_run_attempt,
                latest_successful_run_id=args.latest_successful_run_id,
                latest_successful_run_attempt=args.latest_successful_run_attempt,
                is_ancestor=is_ancestor,
            )
            print(json.dumps({"decision": decision}, sort_keys=True))
    except (OSError, ValueError, RollingReleaseError, KeyError) as error:
        print(f"rolling release: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
