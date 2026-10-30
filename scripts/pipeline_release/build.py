"""Provider-neutral preparation and assembly for compiled build releases."""
from __future__ import annotations

import hashlib
import json
import os
import re
import tempfile
from pathlib import Path
from typing import Any

_TAG_PATTERN = re.compile(r"v\d+\.\d+\.\d+(?:-(?:alpha|beta|rc)\.\d+)?$")
_HEADING_PATTERN = re.compile(r"^##\s+\[([^\]]+)\](?:\s|$)")


class BuildReleaseError(ValueError):
    """Raised when a build-release input or output is unsafe or invalid."""


def _atomic_write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            newline="\n",
            dir=path.parent,
            prefix=f".{path.name}.",
            suffix=".tmp",
            delete=False,
        ) as stream:
            temporary = Path(stream.name)
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        temporary.replace(path)
    finally:
        if temporary is not None and temporary.exists():
            temporary.unlink()


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
    notes = _section(changelog_text, version)
    if notes is None and prerelease and ref_type == "tag":
        notes = _section(changelog_text, version.split("-", 1)[0])
    if notes is None:
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


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def assemble_release_assets(assets_directory: str | Path) -> dict[str, Any]:
    """Create a deterministic SHA256SUMS file for downloaded build artifacts."""
    root = Path(assets_directory).expanduser().resolve()
    if not root.is_dir():
        raise BuildReleaseError(f"Release assets directory does not exist: {root}")

    files: list[Path] = []
    for path in root.rglob("*"):
        if path.is_symlink():
            raise BuildReleaseError(f"Release assets must not contain symlinks: {path.relative_to(root)}")
        if path.is_file() and path.name != "SHA256SUMS":
            files.append(path)

    files.sort(key=lambda item: item.relative_to(root).as_posix())
    if not files:
        raise BuildReleaseError("No release artifacts were downloaded")

    lines = [
        f"{_sha256(path)}  {path.relative_to(root).as_posix()}"
        for path in files
    ]
    checksum_path = root / "SHA256SUMS"
    _atomic_write(checksum_path, "\n".join(lines) + "\n")
    return {
        "assets_directory": str(root),
        "asset_count": len(files),
        "checksum_file": str(checksum_path),
    }
