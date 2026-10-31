"""Portable build target catalogue and validation for release matrices.

A build target describes the output platform/architecture separately from the
runner that builds and tests it. This distinction is important for mobile
emulators and cross-compilation.
"""
from __future__ import annotations

import json
import re
from typing import Any

_TARGET_ID = re.compile(r"^[a-z0-9][a-z0-9-]{0,63}$")

# These are target descriptors, not mandatory runner labels. Projects choose
# compatible hosted/self-hosted runners and may add custom target IDs.
TARGET_CATALOG: dict[str, dict[str, str]] = {
    "linux-amd64": {"target_os": "linux", "architecture": "x86_64", "platform": "desktop", "abi": ""},
    "linux-arm64": {"target_os": "linux", "architecture": "aarch64", "platform": "desktop", "abi": ""},
    "linux-386": {"target_os": "linux", "architecture": "x86", "platform": "desktop", "abi": ""},
    "darwin-amd64": {"target_os": "macos", "architecture": "x86_64", "platform": "desktop", "abi": ""},
    "darwin-arm64": {"target_os": "macos", "architecture": "arm64", "platform": "desktop", "abi": ""},
    "windows-amd64": {"target_os": "windows", "architecture": "x86_64", "platform": "desktop", "abi": ""},
    "windows-386": {"target_os": "windows", "architecture": "x86", "platform": "desktop", "abi": ""},
    "windows-arm64": {"target_os": "windows", "architecture": "arm64", "platform": "desktop", "abi": ""},
    "android-armeabi-v7a": {"target_os": "android", "architecture": "arm", "platform": "mobile", "abi": "armeabi-v7a"},
    "android-arm64-v8a": {"target_os": "android", "architecture": "arm64", "platform": "mobile", "abi": "arm64-v8a"},
    "android-x86": {"target_os": "android", "architecture": "x86", "platform": "mobile", "abi": "x86"},
    "android-x86_64": {"target_os": "android", "architecture": "x86_64", "platform": "mobile", "abi": "x86_64"},
    "ios-arm64": {"target_os": "ios", "architecture": "arm64", "platform": "mobile", "abi": "device"},
    "ios-simulator-arm64": {"target_os": "ios-simulator", "architecture": "arm64", "platform": "mobile", "abi": "simulator"},
    "ios-simulator-x86_64": {"target_os": "ios-simulator", "architecture": "x86_64", "platform": "mobile", "abi": "simulator"},
    "pwa-web": {"target_os": "web", "architecture": "any", "platform": "pwa", "abi": ""},
}


class BuildMatrixError(ValueError):
    """Raised when a configured release matrix is malformed."""


def target_catalog() -> dict[str, dict[str, str]]:
    """Return a copy of the built-in target catalogue."""
    return {name: dict(values) for name, values in TARGET_CATALOG.items()}


def validate_build_matrix(
    value: str | dict[str, Any], *, default_e2e_test_command: str = ""
) -> list[dict[str, Any]]:
    """Parse and validate a project-owned GitHub-style {include: [...]} matrix.

    The runner field 'os' intentionally remains project-defined; target_os,
    architecture and abi describe the produced artifact, not the CI host.
    Custom target IDs are accepted so the catalogue can be extended safely.
    """
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except json.JSONDecodeError as exc:
            raise BuildMatrixError(f"Build matrix is not valid JSON: {exc}") from exc
    if not isinstance(value, dict) or set(value) - {"include"}:
        raise BuildMatrixError("Build matrix must be an object containing only 'include'")
    entries = value.get("include")
    if not isinstance(entries, list) or not entries:
        raise BuildMatrixError("Build matrix 'include' must be a non-empty array")

    normalized: list[dict[str, Any]] = []
    seen: set[str] = set()
    command_fields = {
        "test_command", "build_command", "artifact_test_command",
        "e2e_setup_command", "e2e_test_command",
    }
    for index, item in enumerate(entries):
        if not isinstance(item, dict):
            raise BuildMatrixError(f"Build matrix entry {index} must be an object")
        target_id = item.get("id")
        runner = item.get("os")
        if not isinstance(target_id, str) or not _TARGET_ID.fullmatch(target_id):
            raise BuildMatrixError(f"Build matrix entry {index} has an invalid id")
        if target_id in seen:
            raise BuildMatrixError(f"Duplicate build target id: {target_id}")
        seen.add(target_id)
        if not isinstance(runner, str) or not runner.strip():
            raise BuildMatrixError(f"Build matrix entry {target_id!r} requires a runner 'os'")

        known = TARGET_CATALOG.get(target_id, {})
        row = dict(item)
        row["target_os"] = item.get("target_os", item.get("platform_os", known.get("target_os", "")))
        row["architecture"] = item.get("architecture", item.get("arch", known.get("architecture", "")))
        row["abi"] = item.get("abi", known.get("abi", ""))
        row["platform"] = item.get("platform", known.get("platform", ""))
        for field in command_fields:
            command = item.get(field, "")
            if command is not None and not isinstance(command, str):
                raise BuildMatrixError(f"{target_id}.{field} must be a string")
            row[field] = command or ""
        if row["e2e_setup_command"] and not (row["e2e_test_command"] or default_e2e_test_command):
            raise BuildMatrixError(f"{target_id} configures e2e_setup_command without e2e_test_command")
        for field in ("target_os", "architecture", "abi", "platform"):
            if not isinstance(row[field], str):
                raise BuildMatrixError(f"{target_id}.{field} must be a string")
        normalized.append(row)
    return normalized
