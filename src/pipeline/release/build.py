"""Provider-neutral preparation and assembly for compiled build releases."""
from __future__ import annotations

import hashlib
import json
import lzma
import re
import shutil
import tarfile
from collections import Counter
from pathlib import Path
from typing import Any

from ..common.hashing import sha256_file as _sha256
from ..common.io import atomic_write_text as _atomic_write

_TAG_PATTERN = re.compile(r"v\d+\.\d+\.\d+(?:-(?:dev(?:\.\d+)?|(?:alpha|beta|rc)\.\d+))?$")
_HEADING_PATTERN = re.compile(r"^##\s+\[([^\]]+)\](?:\s|$)")


class BuildReleaseError(ValueError):
    """Raised when a build-release input or output is unsafe or invalid."""


def _section(changelog: str, label: str) -> str | None:
    lines = changelog.splitlines()
    matches = [
        index
        for index, line in enumerate(lines)
        if (match := _HEADING_PATTERN.match(line)) and match.group(1) == label
    ]
    if len(matches) > 1:
        raise BuildReleaseError(f"CHANGELOG contains more than one section for {label!r}")
    if not matches:
        return None

    start = matches[0]
    end = len(lines)
    for index in range(start + 1, len(lines)):
        if lines[index].startswith("## "):
            end = index
            break
    return "\n".join(lines[start:end]).strip() + "\n"


def _as_bool(value: str | bool) -> bool:
    if isinstance(value, bool):
        return value
    normalized = value.strip().lower()
    if normalized in {"true", "1", "yes"}:
        return True
    if normalized in {"false", "0", "no", ""}:
        return False
    raise BuildReleaseError("dry-run must be true or false")


def prepare_release(
    *,
    changelog_path: str | Path,
    output_directory: str | Path,
    ref_type: str,
    ref_name: str,
    commit_sha: str,
    dry_run: bool | str = False,
) -> dict[str, Any]:
    """Resolve a version and write release notes plus machine-readable metadata."""
    dry_run_value = _as_bool(dry_run)
    if ref_type == "tag":
        if not _TAG_PATTERN.fullmatch(ref_name):
            raise BuildReleaseError(
                f"Unsupported release tag {ref_name!r}; expected vMAJOR.MINOR.PATCH "
                "or vMAJOR.MINOR.PATCH-(alpha|beta|rc).N"
            )
        version = ref_name[1:]
    else:
        if not dry_run_value:
            raise BuildReleaseError("A build release requires a version tag unless dry-run is enabled")
        if not commit_sha:
            raise BuildReleaseError("A commit SHA is required for a branch dry-run")
        version = f"0.0.0-dev.{commit_sha[:7]}"

    changelog = Path(changelog_path).expanduser().resolve()
    if not changelog.is_file():
        raise BuildReleaseError(f"Missing changelog: {changelog}")
    try:
        changelog_text = changelog.read_text(encoding="utf-8-sig")
    except (OSError, UnicodeError) as exc:
        raise BuildReleaseError(f"Cannot read changelog {changelog}: {exc}") from exc

    prerelease = "-" in version
    # Keep artifact identity independent from the provider ref (for example,
    # a branch dry-run on "main"). This is the canonical source-owned release tag.
    release_tag = ref_name if ref_type == "tag" else f"v{version}"
    notes = _section(changelog_text, version)
    if notes is None and prerelease and ref_type == "tag":
        notes = _section(changelog_text, version.split("-", 1)[0])
    if notes is None and (dry_run_value or prerelease):
        notes = _section(changelog_text, "Unreleased")

    if notes is None:
        if not dry_run_value and not prerelease:
            raise BuildReleaseError(f"CHANGELOG has no section for stable release {version}")
        notes = (
            f"## Development build {version}\n\n"
            "See CHANGELOG.md for the changes included in this build.\n"
        )

    notes = notes.rstrip() + (
        "\n\n---\n\n"
        "## Assets\n\n"
        "This release attaches the files produced by each configured build target "
        "and a SHA256SUMS file. Verify downloaded files with "
        "sha256sum -c SHA256SUMS.\n"
    )

    output = Path(output_directory).expanduser().resolve()
    output.mkdir(parents=True, exist_ok=True)
    notes_path = output / "release-notes.md"
    metadata_path = output / "release-meta.json"
    metadata = {
        "schema_version": 1,
        "version": version,
        "tag": ref_name if ref_type == "tag" else "",
        "release_tag": release_tag,
        "ref_type": ref_type,
        "ref_name": ref_name,
        "commit_sha": commit_sha,
        "prerelease": prerelease,
        "dry_run": dry_run_value,
    }
    _atomic_write(notes_path, notes)
    _atomic_write(metadata_path, json.dumps(metadata, indent=2, sort_keys=True) + "\n")
    return {
        **metadata,
        "release_notes": str(notes_path),
        "metadata_file": str(metadata_path),
    }


_ARCHIVE_SUFFIXES = (
    ".tar.gz",
    ".tar.xz",
    ".tar.bz2",
    ".tgz",
    ".zip",
    ".tar",
    ".7z",
)
_WRAPPER_DIRECTORIES = frozenset({"artifacts", "dist", "out", "release"})


def _safe_asset_component(value: str) -> str:
    """Turn a target or directory label into a portable filename component."""
    normalized = re.sub(r"[^A-Za-z0-9._+-]+", "-", value).strip(".-")
    return normalized or "artifact"


def _has_sibling_archive(directory: Path) -> bool:
    """Return whether a sibling archive already represents this directory."""
    return any(
        directory.with_name(directory.name + suffix).is_file()
        for suffix in _ARCHIVE_SUFFIXES
    )


def _deterministic_tar_info(info: tarfile.TarInfo) -> tarfile.TarInfo:
    """Remove host-specific ownership and timestamps from generated archives."""
    info.uid = 0
    info.gid = 0
    info.uname = ""
    info.gname = ""
    info.mtime = 0
    return info



def _ensure_asset_sidecar(path: Path) -> Path:
    """Create or validate a sha256sum-compatible sidecar for one asset."""
    digest = _sha256(path)
    sidecar = path.with_name(path.name + ".sha256")
    if sidecar.exists():
        try:
            text = sidecar.read_text(encoding="ascii").strip()
        except (OSError, UnicodeError) as exc:
            raise BuildReleaseError(f"Cannot read checksum sidecar {sidecar.name}: {exc}") from exc
        match = re.fullmatch(r"([0-9a-f]{64})  (.+)", text)
        if not match or match.group(1) != digest or match.group(2) != path.name:
            raise BuildReleaseError(
                f"Checksum sidecar does not match its asset: {sidecar.name}"
            )
        return sidecar
    _atomic_write(sidecar, f"{digest}  {path.name}\n")
    return sidecar


def _compress_xz(source: Path, destination: Path) -> None:
    """Create a deterministic XZ stream without loading the whole asset in memory."""
    try:
        with source.open("rb") as reader, lzma.open(
            destination, "wb", format=lzma.FORMAT_XZ, preset=6
        ) as writer:
            shutil.copyfileobj(reader, writer, length=1024 * 1024)
    except (OSError, lzma.LZMAError) as exc:
        raise BuildReleaseError(f"Could not create XZ asset {destination.name}: {exc}") from exc


def _verify_xz_matches(source: Path, compressed: Path) -> None:
    """Reject a pre-existing .xz file unless it is exactly the source asset."""
    digest = hashlib.sha256()
    try:
        with lzma.open(compressed, "rb") as reader:
            while chunk := reader.read(1024 * 1024):
                digest.update(chunk)
    except (OSError, lzma.LZMAError) as exc:
        raise BuildReleaseError(
            f"Existing compressed asset is not a valid XZ stream: {compressed.name}"
        ) from exc
    if digest.hexdigest() != _sha256(source):
        raise BuildReleaseError(
            f"Existing .xz asset does not contain {source.name}: {compressed.name}"
        )


def _write_gitea_profile(
    root: Path,
    records: list[dict[str, Any]],
    metadata_path: str | Path | None,
) -> int:
    """Add XZ variants, per-file checksums, and a release manifest."""
    reserved = {"manifest.json", "release-attestation.json", "SHA256SUMS"}
    payload_records = [
        record for record in records
        if not str(record["final_name"]).endswith(".sha256")
    ]
    payload_names = [str(record["final_name"]) for record in payload_records]
    collisions = sorted(name for name in payload_names if name in reserved)
    if collisions:
        raise BuildReleaseError(
            "Release artifacts use reserved Gitea profile names: " + ", ".join(collisions)
        )

    rows: list[dict[str, Any]] = []
    for record in payload_records:
        source = root / str(record["final_name"])
        if not source.is_file() or source.is_symlink():
            raise BuildReleaseError(f"Release asset is missing or unsafe: {source.name}")
        compressed_info: dict[str, Any] | None = None
        if not source.name.endswith(".xz"):
            compressed = root / (source.name + ".xz")
            if compressed.exists():
                if compressed.is_symlink() or not compressed.is_file():
                    raise BuildReleaseError(f"Existing XZ asset is not a regular file: {compressed.name}")
                _verify_xz_matches(source, compressed)
            else:
                _compress_xz(source, compressed)
            compressed_info = {
                "format": "xz",
                "name": compressed.name,
                "size": compressed.stat().st_size,
                "sha256": _sha256(compressed),
            }
            _ensure_asset_sidecar(compressed)
        _ensure_asset_sidecar(source)
        rows.append({
            "name": source.name,
            "target": str(record["target"]),
            "size": source.stat().st_size,
            "sha256": _sha256(source),
            "compressed": compressed_info,
        })

    metadata: dict[str, Any] = {}
    if metadata_path is not None:
        metadata_file = Path(metadata_path).expanduser().resolve()
        if not metadata_file.is_file() or metadata_file.is_symlink():
            raise BuildReleaseError(f"Release metadata file does not exist or is unsafe: {metadata_file}")
        try:
            loaded = json.loads(metadata_file.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError) as exc:
            raise BuildReleaseError(f"Cannot read release metadata JSON: {exc}") from exc
        if not isinstance(loaded, dict):
            raise BuildReleaseError("Release metadata must be a JSON object")
        metadata = loaded

    manifest = {
        "schema_version": 1,
        "asset_profile": "gitea",
        "version": metadata.get("version"),
        "tag": metadata.get("release_tag") or metadata.get("tag") or "",
        "commit_sha": metadata.get("commit_sha") or "",
        "prerelease": bool(metadata.get("prerelease", False)),
        "assets": rows,
    }
    manifest_path = root / "manifest.json"
    _atomic_write(manifest_path, json.dumps(manifest, indent=2, sort_keys=True) + "\n")
    _ensure_asset_sidecar(manifest_path)

    files = sorted(
        (path for path in root.iterdir() if path.is_file() and path.name != "SHA256SUMS"),
        key=lambda path: path.name,
    )
    _atomic_write(
        root / "SHA256SUMS",
        "\n".join(f"{_sha256(path)}  {path.name}" for path in files) + "\n",
    )
    return len(files) + 1


def verify_release_assets(assets_directory: str | Path) -> dict[str, Any]:
    """Verify a flattened build-release bundle, its checksums, and optional XZ manifest."""
    root = Path(assets_directory).expanduser().resolve()
    if not root.is_dir():
        raise BuildReleaseError(f"Release assets directory does not exist: {root}")
    sums_path = root / "SHA256SUMS"
    if not sums_path.is_file():
        raise BuildReleaseError("Release bundle is missing SHA256SUMS")

    checksums: dict[str, str] = {}
    try:
        lines = sums_path.read_text(encoding="utf-8").splitlines()
    except (OSError, UnicodeError) as exc:
        raise BuildReleaseError(f"Cannot read SHA256SUMS: {exc}") from exc
    for line_number, line in enumerate(lines, 1):
        parts = line.split("  ", 1)
        if len(parts) != 2:
            raise BuildReleaseError(f"Malformed SHA256SUMS line {line_number}")
        digest, name = parts
        if not re.fullmatch(r"[0-9a-f]{64}", digest) or not name or Path(name).name != name:
            raise BuildReleaseError(f"Unsafe SHA256SUMS entry on line {line_number}")
        if name == "SHA256SUMS" or name in checksums:
            raise BuildReleaseError(f"Duplicate or recursive SHA256SUMS entry: {name}")
        checksums[name] = digest

    actual = {
        path.name for path in root.iterdir()
        if path.is_file() and path.name != "SHA256SUMS"
    }
    if set(checksums) != actual:
        missing = sorted(actual - set(checksums))
        absent = sorted(set(checksums) - actual)
        raise BuildReleaseError(
            f"SHA256SUMS inventory mismatch; unlisted={missing}, missing={absent}"
        )
    for name, expected in checksums.items():
        candidate = root / name
        if candidate.is_symlink() or _sha256(candidate) != expected:
            raise BuildReleaseError(f"SHA256 validation failed for release asset: {name}")

    manifest_path = root / "manifest.json"
    asset_count = len(actual)
    if manifest_path.is_file():
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError) as exc:
            raise BuildReleaseError(f"manifest.json is invalid: {exc}") from exc
        if (
            not isinstance(manifest, dict)
            or manifest.get("schema_version") != 1
            or manifest.get("asset_profile") != "gitea"
            or not isinstance(manifest.get("assets"), list)
        ):
            raise BuildReleaseError("manifest.json has an unsupported release manifest schema")
        seen: set[str] = set()
        for row in manifest["assets"]:
            if not isinstance(row, dict):
                raise BuildReleaseError("manifest.json contains an invalid asset record")
            name, expected = row.get("name"), row.get("sha256")
            if (
                not isinstance(name, str)
                or Path(name).name != name
                or name in {".", ".."}
                or "/" in name
                or "\\" in name
                or not isinstance(expected, str)
                or not re.fullmatch(r"[0-9a-f]{64}", expected)
                or name in seen
            ):
                raise BuildReleaseError("manifest.json contains an unsafe or duplicate asset")
            seen.add(name)
            asset = root / name
            if not asset.is_file() or asset.is_symlink():
                raise BuildReleaseError(f"Manifest asset is missing: {name}")
            if _sha256(asset) != expected or row.get("size") != asset.stat().st_size:
                raise BuildReleaseError(f"Manifest metadata mismatch for asset: {name}")
            sidecar = root / (name + ".sha256")
            if not sidecar.is_file():
                raise BuildReleaseError(f"Manifest asset has no checksum sidecar: {name}")
            try:
                sidecar_text = sidecar.read_text(encoding="ascii").strip()
            except (OSError, UnicodeError) as exc:
                raise BuildReleaseError(f"Cannot read checksum sidecar for {name}: {exc}") from exc
            if sidecar_text != f"{expected}  {name}":
                raise BuildReleaseError(f"Checksum sidecar mismatch for asset: {name}")

            compressed_meta = row.get("compressed")
            if compressed_meta is not None:
                if not isinstance(compressed_meta, dict) or compressed_meta.get("format") != "xz":
                    raise BuildReleaseError(f"Unsupported compressed representation for asset: {name}")
                compressed_name = compressed_meta.get("name")
                compressed_digest = compressed_meta.get("sha256")
                if (
                    not isinstance(compressed_name, str)
                    or Path(compressed_name).name != compressed_name
                    or compressed_name in {".", ".."}
                    or "/" in compressed_name
                    or "\\" in compressed_name
                    or compressed_name == "SHA256SUMS"
                    or not isinstance(compressed_digest, str)
                    or not re.fullmatch(r"[0-9a-f]{64}", compressed_digest)
                ):
                    raise BuildReleaseError(f"Invalid XZ metadata for asset: {name}")
                compressed_path = root / compressed_name
                if (
                    not compressed_path.is_file()
                    or compressed_path.is_symlink()
                    or compressed_path.stat().st_size != compressed_meta.get("size")
                    or _sha256(compressed_path) != compressed_digest
                ):
                    raise BuildReleaseError(f"Compressed asset metadata mismatch: {compressed_name}")
                compressed_sidecar = root / (compressed_name + ".sha256")
                if not compressed_sidecar.is_file():
                    raise BuildReleaseError(f"Compressed asset has no checksum sidecar: {compressed_name}")
                try:
                    compressed_sidecar_text = compressed_sidecar.read_text(encoding="ascii").strip()
                except (OSError, UnicodeError) as exc:
                    raise BuildReleaseError(f"Cannot read compressed asset checksum sidecar: {compressed_name}") from exc
                if compressed_sidecar_text != f"{compressed_digest}  {compressed_name}":
                    raise BuildReleaseError(f"Compressed asset checksum sidecar mismatch: {compressed_name}")
                try:
                    digest = hashlib.sha256()
                    with lzma.open(compressed_path, "rb") as stream:
                        while chunk := stream.read(1024 * 1024):
                            digest.update(chunk)
                except (OSError, lzma.LZMAError) as exc:
                    raise BuildReleaseError(f"Cannot decompress XZ asset {compressed_name}: {exc}") from exc
                if digest.hexdigest() != expected:
                    raise BuildReleaseError(f"XZ asset does not reproduce its source: {compressed_name}")

    return {
        "assets_directory": str(root),
        "file_count": len(actual),
        "asset_count": len(seen) if manifest_path.is_file() else len(actual),
        "checksum_file": str(sums_path),
        "manifest": str(manifest_path) if manifest_path.is_file() else None,
    }


def _selected_artifact_entries(target_root: Path) -> list[Path]:
    """Return selected paths, removing a single conventional output wrapper."""
    entries = sorted(target_root.iterdir(), key=lambda item: item.name)
    while (
        len(entries) == 1
        and entries[0].is_dir()
        and entries[0].name.lower() in _WRAPPER_DIRECTORIES
    ):
        entries = sorted(entries[0].iterdir(), key=lambda item: item.name)
    return entries


def assemble_release_assets(
    assets_directory: str | Path,
    *,
    profile: str = "standard",
    metadata_path: str | Path | None = None,
) -> dict[str, Any]:
    """Normalize downloaded artifacts into unique, flat GitHub Release assets.

    GitHub Release assets do not preserve directory structure and require unique
    asset names. A selected directory is archived as a .tar.gz unless a sibling
    archive with the same stem already represents it. This supports artifact
    patterns such as dist/* without uploading a redundant unpacked package tree.
    """
    if profile not in {"standard", "gitea"}:
        raise BuildReleaseError("Release asset profile must be standard or gitea")
    root = Path(assets_directory).expanduser().resolve()
    if not root.is_dir():
        raise BuildReleaseError(f"Release assets directory does not exist: {root}")

    staging = root.parent / f".{root.name}.pipeline-release-assets"
    if staging.is_symlink():
        raise BuildReleaseError("Release assets contain a symlink at .pipeline-release-assets")
    if staging.exists():
        shutil.rmtree(staging)

    # Reject symlinks before archiving or copying any input. This also checks
    # trees that may later be skipped because an adjacent archive represents them.
    for path in root.rglob("*"):
        if path.is_symlink():
            raise BuildReleaseError(
                f"Release assets must not contain symlinks: {path.relative_to(root)}"
            )

    target_roots = [
        path
        for path in sorted(root.iterdir(), key=lambda item: item.name)
        if path.is_dir() and path.name.startswith("release-build-")
    ]
    if target_roots:
        targets = [
            (path.name.removeprefix("release-build-") or "target", path)
            for path in target_roots
        ]
    else:
        targets = [(root.name or "release", root)]

    staging.mkdir()
    records: list[dict[str, Any]] = []
    try:
        for target_name, target_root in targets:
            safe_target = _safe_asset_component(target_name)
            for entry in _selected_artifact_entries(target_root):
                if entry.name == "SHA256SUMS":
                    # Generate one combined checksum manifest below.
                    continue
                if entry.is_symlink():
                    raise BuildReleaseError(
                        f"Release assets must not contain symlinks: {entry.relative_to(root)}"
                    )
                if entry.is_dir():
                    if _has_sibling_archive(entry):
                        # The archive is the distributable; omit its unpacked tree.
                        continue
                    archive_name = (
                        f"{safe_target}-{_safe_asset_component(entry.name)}.tar.gz"
                    )
                    archive_path = staging / archive_name
                    if archive_path.exists():
                        raise BuildReleaseError(
                            f"Directory artifacts produce a duplicate archive name: {archive_name}"
                        )
                    with tarfile.open(archive_path, mode="w:gz", compresslevel=9) as archive:
                        archive.add(
                            entry,
                            arcname=entry.name,
                            recursive=True,
                            filter=_deterministic_tar_info,
                        )
                    records.append(
                        {
                            "source": archive_path,
                            "target": target_name,
                            "name": archive_name,
                            "generated": True,
                        }
                    )
                elif entry.is_file():
                    records.append(
                        {
                            "source": entry,
                            "target": target_name,
                            "name": entry.name,
                            "generated": False,
                        }
                    )

        # Project-owned release metadata may be prepared after matrix artifacts
        # have been downloaded. When target directories exist, include regular
        # files at the asset root as shared release assets instead of silently
        # dropping them from the assembled bundle.
        if target_roots:
            for entry in sorted(root.iterdir(), key=lambda item: item.name):
                if entry.is_file() and entry.name != "SHA256SUMS":
                    records.append(
                        {
                            "source": entry,
                            "target": "shared",
                            "name": entry.name,
                            "generated": False,
                        }
                    )

        if not records:
            raise BuildReleaseError("No release artifacts were downloaded")

        name_counts = Counter(record["name"] for record in records)
        used_names: set[str] = set()
        renames_by_target: dict[str, dict[str, str]] = {}
        for record in records:
            original_name = record["name"]
            final_name = original_name
            if name_counts[original_name] > 1:
                final_name = (
                    f"{_safe_asset_component(record['target'])}-{original_name}"
                )
            if final_name in used_names:
                source = record["source"]
                relative_parent = (
                    source.relative_to(root).parent.as_posix()
                    if not record["generated"]
                    else original_name
                )
                final_name = (
                    f"{_safe_asset_component(record['target'])}-"
                    f"{_safe_asset_component(relative_parent)}-{original_name}"
                )
            if final_name in used_names:
                raise BuildReleaseError(
                    f"Release assets still have a duplicate name after normalization: {final_name}"
                )
            record["final_name"] = final_name
            used_names.add(final_name)
            if final_name != original_name:
                renames_by_target.setdefault(record["target"], {})[
                    original_name
                ] = final_name

        for record in records:
            source = record["source"]
            destination = staging / record["final_name"]
            if record["generated"]:
                if source != destination:
                    shutil.move(str(source), str(destination))
                continue

            if source.name.endswith(".sha256"):
                try:
                    checksum_text = source.read_text(encoding="utf-8")
                except (OSError, UnicodeError):
                    checksum_text = None
                if checksum_text is not None:
                    for old_name, new_name in renames_by_target.get(
                        record["target"], {}
                    ).items():
                        if old_name.endswith(_ARCHIVE_SUFFIXES):
                            checksum_text = checksum_text.replace(old_name, new_name)
                    destination.write_text(checksum_text, encoding="utf-8")
                    continue
            shutil.copy2(source, destination)

        publish_files = sorted(
            (path for path in staging.iterdir() if path.is_file()),
            key=lambda item: item.name,
        )
        if not publish_files:
            raise BuildReleaseError("No publishable release assets remain after normalization")

        checksum_lines = [
            f"{_sha256(path)}  {path.name}" for path in publish_files
        ]
        _atomic_write(staging / "SHA256SUMS", "\n".join(checksum_lines) + "\n")

        # Replace the downloaded nested artifact tree with the flat directory
        # consumed by the GitHub Release publishing action.
        for path in list(root.iterdir()):
            if path == staging:
                continue
            if path.is_dir():
                shutil.rmtree(path)
            else:
                path.unlink()
        for path in sorted(staging.iterdir(), key=lambda item: item.name):
            shutil.move(str(path), str(root / path.name))
        staging.rmdir()
    except Exception:
        if staging.exists():
            shutil.rmtree(staging)
        raise

    bundle_file_count = 0
    if profile == "gitea":
        bundle_file_count = _write_gitea_profile(root, records, metadata_path)
    return {
        "assets_directory": str(root),
        "asset_count": len(records),
        "asset_profile": profile,
        "bundle_file_count": bundle_file_count or len(list(root.iterdir())),
        "checksum_file": str(root / "SHA256SUMS"),
    }
