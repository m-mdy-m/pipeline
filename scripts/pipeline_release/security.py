from __future__ import annotations
import tomllib
from .errors import ReleaseError
from .git_snapshot import read_blob
from .models import TreeEntry
from .paths import safe_repo_path


def validate_allowlist_path(config_path: str, by_path: dict[str, TreeEntry]) -> TreeEntry | None:
    if not config_path:
        return None
    normalized = safe_repo_path(config_path)
    entry = by_path.get(normalized)
    if entry is None or entry.mode == "120000":
        raise ReleaseError(f"source-gitleaks-allowlist-path must refer to a regular tracked file: {normalized}")
    return entry


def compose_gitleaks_config(allowlist_entry: TreeEntry | None) -> bytes:
    # Explicitly extend Gitleaks' embedded default rules. A caller-owned file may
    # contribute allowlist tables only; it cannot replace/disable detection rules.
    config = (
        'title = "pipeline source-release default rules"\n'
        '[extend]\n'
        'useDefault = true\n'
    )
    if allowlist_entry is None:
        return config.encode("utf-8")
    try:
        custom = read_blob(allowlist_entry).decode("utf-8-sig", "strict")
        parsed = tomllib.loads(custom)
    except (UnicodeDecodeError, tomllib.TOMLDecodeError) as exc:
        raise ReleaseError(f"Invalid TOML in source-gitleaks-allowlist-path: {allowlist_entry.path}") from exc
    if not parsed or set(parsed) - {"allowlist", "allowlists"}:
        raise ReleaseError(
            "The Gitleaks allowlist file may contain only [allowlist] or [[allowlists]] tables; "
            "it cannot replace the scanner's default rules."
        )
    allowed_keys = {"description", "regexes", "paths", "commits", "stopwords", "regexTarget"}
    tables = []
    if "allowlist" in parsed:
        tables.append(parsed["allowlist"])
    if "allowlists" in parsed:
        tables.extend(parsed["allowlists"])
    if not tables:
        raise ReleaseError("Gitleaks allowlist TOML contains no allowlist table")
    for table in tables:
        if not isinstance(table, dict) or set(table) - allowed_keys:
            raise ReleaseError("Unsupported field in Gitleaks allowlist table")
    if "allowlist" in parsed and "allowlists" in parsed:
        raise ReleaseError("Use either [allowlist] or [[allowlists]], not both")
    return (config + "\n" + custom.strip() + "\n").encode("utf-8")
