from __future__ import annotations
import re
from .errors import ReleaseError
from .runtime import REPO_ROOT, TAG_RE
from .tools import env, git_output
from ..core.context import PipelineContext


def validate_tag_and_version() -> tuple[str, str, str, bool, str]:
    dry_run = env("SOURCE_DRY_RUN", "false").lower() == "true"
    context = PipelineContext.from_environment(workspace=REPO_ROOT)
    ref_type = context.ref_type
    ref_name = context.ref_name
    sha = context.sha or git_output(["rev-parse", "HEAD"])
    repo = context.repository or env("SOURCE_REPOSITORY", "local/project")
    repository = repo.rsplit("/", 1)[-1]

    if ref_type == "tag":
        if not TAG_RE.fullmatch(ref_name):
            raise ReleaseError(
                f"Unsupported release tag: {ref_name!r}. Use vMAJOR.MINOR.PATCH or "
                "vMAJOR.MINOR.PATCH-(alpha|beta|rc).N."
            )
        version = ref_name[1:]
        tag_label = ref_name
        tag_commit = git_output(["rev-parse", f"{ref_name}^{{commit}}"])
        event_commit = git_output(["rev-parse", f"{sha}^{{commit}}"])
        if tag_commit != event_commit:
            raise ReleaseError(f"Tag {ref_name} resolves to {tag_commit}, not event commit {event_commit}")
        snapshot_ref = event_commit
    elif dry_run:
        short_sha = sha[:7]
        version = f"0.0.0-dev.{short_sha}"
        tag_label = f"dry-run-{short_sha}"
        snapshot_ref = git_output(["rev-parse", f"{sha}^{{commit}}"])
    else:
        raise ReleaseError("Source Release requires a version tag; use dry-run: true for a branch smoke test")

    prerelease = "-" in version
    return repository, version, tag_label, prerelease, snapshot_ref


def build_names(repository: str, version: str, tag_label: str) -> tuple[str, str]:
    template = env("SOURCE_ARCHIVE_NAME", "{repository}-{tag}-source.zip").strip()
    if not template:
        raise ReleaseError("source-archive-name must not be empty")
    replacements = {"repository": repository, "tag": tag_label, "version": version}
    result = template
    for key, value in replacements.items():
        result = result.replace("{" + key + "}", value)
    if "{" in result or "}" in result:
        raise ReleaseError(f"Unknown placeholder in source-archive-name: {template!r}")
    if result.startswith(".") or "/" in result or "\\" in result or not result.endswith(".zip"):
        raise ReleaseError("source-archive-name must be a basename ending in .zip (no paths)")
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._+-]*\.zip", result):
        raise ReleaseError(f"Invalid source archive filename: {result!r}")
    root = f"{repository}-{tag_label}"
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._+-]*", root):
        raise ReleaseError(f"Invalid ZIP root directory name: {root!r}")
    return result, root
