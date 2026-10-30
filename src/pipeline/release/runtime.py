"""Shared paths and policy constants for reusable pipeline scripts."""
import os
import re
from dataclasses import dataclass, field
from pathlib import Path

REPO_ROOT = Path(os.environ.get("PIPELINE_WORKSPACE") or Path.cwd()).resolve()
WORK_DIR = Path(os.environ.get("SOURCE_WORK_DIR", str(REPO_ROOT / ".source-release-work"))).resolve()
SOURCE_TREE = WORK_DIR / "source-tree"
SCAN_TREE = WORK_DIR / "secret-scan"
RELEASE_ASSETS = WORK_DIR / "release-assets"
REPORTS = WORK_DIR / "reports"
VERSION_RE = re.compile(r"^v?(?P<version>\d+\.\d+\.\d+(?:-(?:alpha|beta|rc)\.\d+)?)$")
TAG_RE = re.compile(r"^v\d+\.\d+\.\d+(?:-(?:alpha|beta|rc)\.\d+)?$")
SEMVER_RE = r"\d+\.\d+\.\d+(?:-(?:alpha|beta|rc)\.\d+)?"

DEFAULT_SENSITIVE_PATTERNS = (
    ".env",
    ".env.*",
    "**/.env",
    "**/.env.*",
    "*.pem",
    "*.key",
    "*.p12",
    "*.pfx",
    "id_rsa",
    "id_dsa",
    "id_ecdsa",
    "id_ed25519",
    "*private_key*",
    "*private-key*",
    "credentials.json",
    "service-account*.json",
    "secrets.json",
    "secrets.yaml",
    "secrets.yml",
)

DEFAULT_SENSITIVE_ALLOWLIST = (
    ".env.example",
    ".env.sample",
    ".env.template",
    ".env.dist",
    "**/.env.example",
    "**/.env.sample",
    "**/.env.template",
    "**/.env.dist",
)

@dataclass
class RuntimeState:
    """Mutable process-scoped state; never persisted between workflow steps."""
    omitted_submodules: list[str] = field(default_factory=list)
    token_to_redact: str = ""

STATE = RuntimeState()
