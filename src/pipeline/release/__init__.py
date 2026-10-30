"""Composable source and build release tooling."""

from .archive import validate_zip, zip_add_file
from .changelog import decode_changelog, detect_changelog, extract_unreleased_section, extract_version_section, heading_info
from .cli import main
from .build import BuildReleaseError, assemble_release_assets, prepare_release
from .errors import ReleaseError
from .git_snapshot import collect_entries, parse_ls_tree, read_blob
from .models import TreeEntry
from .package import package
from .paths import any_pattern, glob_match, path_exists_as_directory, safe_repo_path, validate_patterns, validate_symlinks
from .prepare import prepare
from .release_meta import build_names, validate_tag_and_version
from .security import compose_gitleaks_config, validate_allowlist_path
from .tools import atomic_write_text, env, git_output, run_command, run_git, sha256_file, write_outputs

__all__ = [
    "ReleaseError", "BuildReleaseError", "TreeEntry", "main", "prepare", "package", "prepare_release", "assemble_release_assets", "decode_changelog",
    "detect_changelog", "extract_unreleased_section", "extract_version_section", "heading_info",
    "collect_entries", "parse_ls_tree", "read_blob", "any_pattern", "glob_match",
    "path_exists_as_directory", "safe_repo_path", "validate_patterns", "validate_symlinks",
    "build_names", "validate_tag_and_version", "compose_gitleaks_config", "validate_allowlist_path",
    "validate_zip", "zip_add_file", "atomic_write_text", "env", "git_output", "run_command",
    "run_git", "sha256_file", "write_outputs",
]
