"""Portable preparation and verification for versioned OCI package artifacts.

The module deliberately does not authenticate to or publish to a registry.
Provider workflows own credentials and network publishing; this code owns the
provider-neutral package identity, target descriptor, and payload integrity.
"""
from __future__ import annotations

import glob
import hashlib
import json
import os
import re
import shutil
import stat
import tempfile
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit


ARTIFACT_TYPE = "application/vnd.pipeline.package.v1"
ARTIFACT_CONFIG_MEDIA_TYPE = "application/vnd.pipeline.package.config.v1+json"
ARTIFACT_LAYER_MEDIA_TYPE = "application/vnd.pipeline.package.layer.v1.tar+gzip"
_METADATA_FILENAME = "package-metadata.json"
_TOKEN_RE = re.compile(r"^[a-z0-9][a-z0-9._-]{0,127}$")
_TAG_RE = re.compile(r"^[A-Za-z0-9_][A-Za-z0-9_.-]{0,127}$")
_VERSION_RE = re.compile(
    r"^(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)"
    r"(?:-[0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*)?"
    r"(?:\+[0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*)?$"
)
_DIGEST_RE = re.compile(r"^[0-9a-f]{64}$")
_REVISION_RE = re.compile(r"^(?:[0-9a-f]{40}|[0-9a-f]{64})$")


class OciArtifactError(ValueError):
    """A safe-to-display OCI package validation error."""


def _token(value: object, field: str) -> str:
    if not isinstance(value, str) or not _TOKEN_RE.fullmatch(value):
        raise OciArtifactError(
            f"{field} must be a lowercase token containing letters, digits, '.', '_' or '-'"
        )
    return value


def _version(value: object) -> str:
    if not isinstance(value, str) or not _VERSION_RE.fullmatch(value):
        raise OciArtifactError("version must be a valid SemVer MAJOR.MINOR.PATCH value")
    semantic_part = value.split("+", 1)[0]
    if "-" in semantic_part:
        prerelease = semantic_part.split("-", 1)[1]
        for identifier in prerelease.split("."):
            if identifier.isdigit() and len(identifier) > 1 and identifier.startswith("0"):
                raise OciArtifactError("numeric SemVer prerelease identifiers must not contain leading zeroes")
    return value


def _source_repository(value: object) -> str:
    if not isinstance(value, str) or not value:
        raise OciArtifactError("source repository must be an HTTPS URL")
    parsed = urlsplit(value)
    if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password:
        raise OciArtifactError("source repository must be an HTTPS URL without credentials")
    if parsed.query or parsed.fragment:
        raise OciArtifactError("source repository URL must not contain a query or fragment")
    return value.rstrip("/")


def _revision(value: object) -> str:
    if not isinstance(value, str) or not _REVISION_RE.fullmatch(value):
        raise OciArtifactError("source revision must be a full 40- or 64-character lowercase Git object ID")
    return value


def _media_type(value: object) -> str:
    if not isinstance(value, str) or not re.fullmatch(
        r"[A-Za-z0-9!#$&^_.+-]+/[A-Za-z0-9!#$&^_.+-]+", value
    ):
        raise OciArtifactError("artifact media type must be a valid type/subtype token")
    return value


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _resolve_single_file(pattern: str) -> Path:
    if not isinstance(pattern, str) or not pattern.strip():
        raise OciArtifactError("artifact path/glob must not be empty")
    matches = sorted(Path(item) for item in glob.glob(pattern, recursive=False))
    if not matches:
        candidate = Path(pattern)
        if candidate.exists():
            matches = [candidate]
    if len(matches) != 1:
        raise OciArtifactError(
            f"artifact path must resolve to exactly one file; matched {len(matches)} files"
        )
    candidate = matches[0]
    if candidate.is_symlink():
        raise OciArtifactError("artifact must not be a symbolic link")
    try:
        mode = candidate.stat().st_mode
    except OSError as exc:
        raise OciArtifactError(f"cannot stat artifact: {exc}") from exc
    if not stat.S_ISREG(mode):
        raise OciArtifactError("artifact must be a regular file")
    return candidate.resolve(strict=True)


def _write_new_file(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.is_symlink() or path.exists():
        raise OciArtifactError(f"refusing to overwrite existing metadata file: {path}")
    descriptor, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as stream:
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    except Exception:
        try:
            temporary.unlink(missing_ok=True)
        except OSError:
            pass
        raise


def _target_tag(version: str, target_id: str) -> str:
    # OCI tags use the Docker tag grammar, which does not include SemVer '+'
    # build metadata. Retain it in the package descriptor and normalize it only
    # in the human-readable tag; the immutable manifest digest remains identity.
    tag_version = version.replace("+", "_")
    tag = tag_version if target_id == "any" else f"{tag_version}-{target_id}"
    if not _TAG_RE.fullmatch(tag):
        raise OciArtifactError("computed OCI tag is not valid or exceeds 128 characters")
    return tag


def _validate_metadata(metadata: object) -> dict[str, Any]:
    if not isinstance(metadata, dict) or metadata.get("schema_version") != 1:
        raise OciArtifactError("unsupported or malformed OCI package metadata schema")
    if metadata.get("artifact_type") != ARTIFACT_TYPE:
        raise OciArtifactError("unsupported OCI artifact type")

    component = metadata.get("component")
    package = metadata.get("package")
    source = metadata.get("source")
    target = metadata.get("target")
    artifact = metadata.get("artifact")
    if not all(isinstance(value, dict) for value in (component, package, source, target, artifact)):
        raise OciArtifactError("metadata must contain component, package, source, target, and artifact objects")

    _token(component.get("id"), "component.id")
    _token(component.get("variant"), "component.variant")
    _token(package.get("name"), "package.name")
    version = _version(package.get("version"))
    target_id = _token(target.get("id"), "target.id")
    _token(target.get("os"), "target.os")
    _token(target.get("architecture"), "target.architecture")
    _token(target.get("abi"), "target.abi")
    _source_repository(source.get("repository"))
    _revision(source.get("revision"))

    artifact_name = artifact.get("name")
    if (
        not isinstance(artifact_name, str)
        or not artifact_name
        or Path(artifact_name).name != artifact_name
        or "/" in artifact_name
        or "\\" in artifact_name
        or ":" in artifact_name
        or any(ord(character) < 32 for character in artifact_name)
    ):
        raise OciArtifactError("artifact.name must be a safe basename without path or control characters")
    if artifact_name in {".", ".."}:
        raise OciArtifactError("artifact.name is invalid")
    _media_type(artifact.get("media_type"))
    size = artifact.get("size")
    if isinstance(size, bool) or not isinstance(size, int) or size < 0:
        raise OciArtifactError("artifact.size must be a non-negative integer")
    digest = artifact.get("sha256")
    if not isinstance(digest, str) or not _DIGEST_RE.fullmatch(digest):
        raise OciArtifactError("artifact.sha256 must be a lowercase SHA-256 digest")
    expected_tag = _target_tag(version, target_id)
    if package.get("tag") != expected_tag:
        raise OciArtifactError("package.tag does not match package version and target")
    return metadata


def prepare_package_artifact(
    *,
    artifact_pattern: str,
    output_directory: str | Path,
    package_name: str,
    component_id: str,
    version: str,
    source_repository: str,
    source_revision: str,
    target_id: str,
    target_os: str,
    architecture: str,
    abi: str,
    variant: str = "default",
    media_type: str = ARTIFACT_LAYER_MEDIA_TYPE,
) -> dict[str, Any]:
    """Create deterministic JSON metadata for exactly one built package file."""
    artifact_path = _resolve_single_file(artifact_pattern)
    name = _token(package_name, "package name")
    component = _token(component_id, "component id")
    component_variant = _token(variant, "component variant")
    package_version = _version(version)
    repository = _source_repository(source_repository)
    revision = _revision(source_revision)
    platform_id = _token(target_id, "target id")
    platform_os = _token(target_os, "target os")
    platform_arch = _token(architecture, "target architecture")
    platform_abi = _token(abi, "target abi")
    payload_type = _media_type(media_type)
    size = artifact_path.stat().st_size
    digest = _sha256_file(artifact_path)
    tag = _target_tag(package_version, platform_id)

    metadata: dict[str, Any] = {
        "schema_version": 1,
        "artifact_type": ARTIFACT_TYPE,
        "component": {"id": component, "variant": component_variant},
        "package": {"name": name, "version": package_version, "tag": tag},
        "source": {"repository": repository, "revision": revision},
        "target": {
            "id": platform_id,
            "os": platform_os,
            "architecture": platform_arch,
            "abi": platform_abi,
        },
        "artifact": {
            "name": artifact_path.name,
            "media_type": payload_type,
            "size": size,
            "sha256": digest,
        },
    }
    _validate_metadata(metadata)

    output_dir = Path(output_directory)
    if output_dir.is_symlink():
        raise OciArtifactError("metadata output directory must not be a symbolic link")
    if output_dir.exists() and not output_dir.is_dir():
        raise OciArtifactError("metadata output path must be a directory")
    metadata_path = output_dir / _METADATA_FILENAME
    serialized = json.dumps(metadata, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    _write_new_file(metadata_path, serialized)
    return {
        "artifact_path": str(artifact_path),
        "artifact_sha256": digest,
        "artifact_size": size,
        "metadata_path": str(metadata_path.resolve()),
        "metadata_sha256": hashlib.sha256(serialized.encode("utf-8")).hexdigest(),
        "package_name": name,
        "version": package_version,
        "tag": tag,
        "target_id": platform_id,
    }


def verify_package_artifact(metadata_path: str | Path, artifact_path: str | Path) -> dict[str, Any]:
    """Verify a package file against its deterministic metadata descriptor."""
    descriptor_path = Path(metadata_path)
    if descriptor_path.is_symlink() or not descriptor_path.is_file():
        raise OciArtifactError("metadata path must be a regular file")
    try:
        metadata = json.loads(descriptor_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise OciArtifactError(f"package metadata is not valid UTF-8 JSON: {exc}") from exc
    metadata = _validate_metadata(metadata)

    payload = Path(artifact_path)
    if payload.is_symlink():
        raise OciArtifactError("artifact must not be a symbolic link")
    try:
        mode = payload.stat().st_mode
    except OSError as exc:
        raise OciArtifactError(f"cannot stat artifact: {exc}") from exc
    if not stat.S_ISREG(mode):
        raise OciArtifactError("artifact must be a regular file")
    if payload.name != metadata["artifact"]["name"]:
        raise OciArtifactError("artifact filename does not match package metadata")
    actual_size = payload.stat().st_size
    if actual_size != metadata["artifact"]["size"]:
        raise OciArtifactError(
            f"artifact size mismatch: expected {metadata['artifact']['size']}, got {actual_size}"
        )
    actual_digest = _sha256_file(payload)
    if actual_digest != metadata["artifact"]["sha256"]:
        raise OciArtifactError("artifact SHA-256 mismatch")
    return {
        "package_name": metadata["package"]["name"],
        "version": metadata["package"]["version"],
        "tag": metadata["package"]["tag"],
        "component_id": metadata["component"]["id"],
        "variant": metadata["component"]["variant"],
        "target_id": metadata["target"]["id"],
        "artifact": metadata["artifact"]["name"],
        "size": actual_size,
        "sha256": actual_digest,
        "metadata_sha256": _sha256_file(descriptor_path),
        "verified": True,
    }



def stage_package_artifact(
    *,
    metadata_path: str | Path,
    artifact_path: str | Path,
    output_directory: str | Path,
    expected_metadata_sha256: str,
) -> dict[str, Any]:
    """Copy a verified package to a private, read-only staging directory.

    The descriptor digest is checked before and after copying. The staged bytes
    are hashed before atomic publication so a post-test mutation of the build
    output can never be published under stale metadata.
    """
    descriptor_path = Path(metadata_path)
    if descriptor_path.is_symlink() or not descriptor_path.is_file():
        raise OciArtifactError("metadata path must be a regular file")
    if not isinstance(expected_metadata_sha256, str) or not _DIGEST_RE.fullmatch(expected_metadata_sha256):
        raise OciArtifactError("expected metadata SHA-256 must be a lowercase 64-character digest")

    try:
        descriptor_bytes = descriptor_path.read_bytes()
    except OSError as exc:
        raise OciArtifactError(f"cannot read package metadata: {exc}") from exc
    descriptor_digest = hashlib.sha256(descriptor_bytes).hexdigest()
    if descriptor_digest != expected_metadata_sha256:
        raise OciArtifactError("package metadata changed after preparation")
    try:
        metadata = json.loads(descriptor_bytes.decode("utf-8"))
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise OciArtifactError(f"package metadata is not valid UTF-8 JSON: {exc}") from exc
    metadata = _validate_metadata(metadata)

    source = Path(artifact_path)
    if source.is_symlink():
        raise OciArtifactError("artifact must not be a symbolic link")
    try:
        source_mode = source.stat().st_mode
    except OSError as exc:
        raise OciArtifactError(f"cannot stat package artifact: {exc}") from exc
    if not stat.S_ISREG(source_mode):
        raise OciArtifactError("artifact must be a regular file")
    if source.name != metadata["artifact"]["name"]:
        raise OciArtifactError("artifact filename does not match package metadata")

    destination_directory_path = Path(output_directory)
    if destination_directory_path.is_symlink():
        raise OciArtifactError("staging output directory must not be a symbolic link")
    if destination_directory_path.exists() and not destination_directory_path.is_dir():
        raise OciArtifactError("staging output path must be a directory")
    destination_directory_path.mkdir(parents=True, exist_ok=True)
    destination = destination_directory_path / metadata["artifact"]["name"]
    if destination.exists() or destination.is_symlink():
        raise OciArtifactError("refusing to overwrite an existing staged package")

    descriptor, temporary_name = tempfile.mkstemp(prefix=f".{destination.name}.", dir=destination_directory_path)
    temporary = Path(temporary_name)
    published = False
    try:
        with os.fdopen(descriptor, "wb") as writer, source.open("rb") as reader:
            shutil.copyfileobj(reader, writer, length=1024 * 1024)
            writer.flush()
            os.fsync(writer.fileno())

        actual_size = temporary.stat().st_size
        actual_digest = _sha256_file(temporary)
        expected_artifact = metadata["artifact"]
        if actual_size != expected_artifact["size"]:
            raise OciArtifactError(
                f"artifact size mismatch while staging: expected {expected_artifact['size']}, got {actual_size}"
            )
        if actual_digest != expected_artifact["sha256"]:
            raise OciArtifactError("artifact SHA-256 mismatch while staging")

        if hashlib.sha256(descriptor_path.read_bytes()).hexdigest() != expected_metadata_sha256:
            raise OciArtifactError("package metadata changed while staging")
        temporary.chmod(0o444)
        os.replace(temporary, destination)
        published = True

        if hashlib.sha256(descriptor_path.read_bytes()).hexdigest() != expected_metadata_sha256:
            raise OciArtifactError("package metadata changed before staging completed")
        return {
            "artifact_path": str(destination.resolve()),
            "artifact_name": destination.name,
            "artifact_size": actual_size,
            "artifact_sha256": actual_digest,
            "metadata_sha256": descriptor_digest,
            "staged": True,
        }
    except Exception:
        try:
            temporary.unlink(missing_ok=True)
            if published:
                destination.unlink(missing_ok=True)
        except OSError:
            pass
        raise


def build_publication_receipt(
    *,
    metadata_path: str | Path,
    push_result_path: str | Path,
    registry: str,
    owner: str,
) -> dict[str, Any]:
    """Bind the local package descriptor to the digest returned by ORAS."""
    descriptor_path = Path(metadata_path)
    if descriptor_path.is_symlink() or not descriptor_path.is_file():
        raise OciArtifactError("metadata path must be a regular file")
    try:
        metadata = json.loads(descriptor_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise OciArtifactError(f"package metadata is not valid UTF-8 JSON: {exc}") from exc
    metadata = _validate_metadata(metadata)

    result_path = Path(push_result_path)
    if result_path.is_symlink() or not result_path.is_file():
        raise OciArtifactError("ORAS push result must be a regular file")
    try:
        pushed = json.loads(result_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise OciArtifactError(f"ORAS push result is not valid UTF-8 JSON: {exc}") from exc
    if not isinstance(pushed, dict):
        raise OciArtifactError("ORAS push result must be a JSON object")
    digest = pushed.get("digest")
    if not isinstance(digest, str) or not re.fullmatch(r"sha256:[0-9a-f]{64}", digest):
        raise OciArtifactError("ORAS push result is missing a valid SHA-256 manifest digest")
    if pushed.get("artifactType") != ARTIFACT_TYPE:
        raise OciArtifactError("published OCI artifact type does not match the package descriptor")

    registry_host = registry.strip().lower()
    if not re.fullmatch(r"[a-z0-9.-]+(?::[0-9]{1,5})?", registry_host):
        raise OciArtifactError("registry must be a hostname with an optional port")
    repository_owner = _token(owner.lower(), "registry owner")
    package_name = metadata["package"]["name"]
    tag = metadata["package"]["tag"]
    tagged_reference = f"{registry_host}/{repository_owner}/{package_name}:{tag}"
    immutable_reference = f"{registry_host}/{repository_owner}/{package_name}@{digest}"
    pushed_reference = pushed.get("reference")
    if not isinstance(pushed_reference, str) or pushed_reference != immutable_reference:
        raise OciArtifactError("ORAS returned a manifest reference that does not match its digest")

    references_as_tags = pushed.get("referenceAsTags")
    if not isinstance(references_as_tags, list) or tagged_reference not in references_as_tags:
        raise OciArtifactError("ORAS result does not contain the expected package tag")

    return {
        "schema_version": 1,
        "published": True,
        "package": metadata["package"],
        "component": metadata["component"],
        "source": metadata["source"],
        "target": metadata["target"],
        "artifact": metadata["artifact"],
        "metadata": {
            "name": _METADATA_FILENAME,
            "sha256": _sha256_file(descriptor_path),
        },
        "oci": {
            "registry": registry_host,
            "reference": tagged_reference,
            "immutable_reference": immutable_reference,
            "digest": digest,
            "artifact_type": ARTIFACT_TYPE,
        },
    }


def validate_target_matrix(value: str) -> list[dict[str, Any]]:
    """Validate target entries used by the reusable OCI publish workflow."""
    try:
        document = json.loads(value)
    except json.JSONDecodeError as exc:
        raise OciArtifactError(f"target matrix is not valid JSON: {exc}") from exc
    if not isinstance(document, dict) or not isinstance(document.get("include"), list):
        raise OciArtifactError("target matrix must be an object containing an include array")
    entries = document["include"]
    if not entries or len(entries) > 32:
        raise OciArtifactError("target matrix must contain between 1 and 32 targets")
    seen: set[str] = set()
    normalized: list[dict[str, Any]] = []
    for index, entry in enumerate(entries):
        if not isinstance(entry, dict):
            raise OciArtifactError(f"target matrix entry {index} must be an object")
        target_id = _token(entry.get("id"), f"target[{index}].id")
        if target_id in seen:
            raise OciArtifactError(f"duplicate target matrix id: {target_id}")
        seen.add(target_id)
        runner = entry.get("os")
        if not isinstance(runner, str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_. -]{0,99}", runner):
            raise OciArtifactError(f"target[{index}].os must be a valid GitHub runner label")
        target_os = _token(entry.get("target_os"), f"target[{index}].target_os")
        architecture = _token(entry.get("architecture"), f"target[{index}].architecture")
        abi = _token(entry.get("abi"), f"target[{index}].abi")
        for optional in ("setup_command", "test_command", "build_command", "artifact_test_command", "artifact_path"):
            if optional in entry and not isinstance(entry[optional], str):
                raise OciArtifactError(f"target[{index}].{optional} must be a string")
        normalized.append({
            **entry,
            "id": target_id,
            "os": runner,
            "target_os": target_os,
            "architecture": architecture,
            "abi": abi,
        })
    return normalized
