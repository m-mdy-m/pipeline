"""Provider-neutral preparation and assembly for compiled build releases."""
from __future__ import annotations

import json
import re
import shutil
import tarfile
from collections import Counter
from pathlib import Path
from typing import Any

from ..common.hashing import sha256_file as _sha256
from ..common.io import atomic_write_text as _atomic_write

_TAG_PATTERN = re.compile(r"v\d+\.\d+\.\d+(?:-(?:alpha|beta|rc)\.\d+)?$")
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


def assemble_release_assets(assets_directory: str | Path) -> dict[str, Any]:
    """Normalize downloaded artifacts into unique, flat GitHub Release assets.

    GitHub Release assets do not preserve directory structure and require unique
    asset names. A selected directory is archived as a .tar.gz unless a sibling
    archive with the same stem already represents it. This supports artifact
    patterns such as dist/* without uploading a redundant unpacked package tree.
    """
    root = Path(assets_directory).expanduser().resolve()
    if not root.is_dir():
        raise BuildReleaseError(f"Release assets directory does not exist: {root}")

    staging = root / ".pipeline-release-assets"
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

    return {
        "assets_directory": str(root),
        "asset_count": len(records),
        "checksum_file": str(root / "SHA256SUMS"),
    }
