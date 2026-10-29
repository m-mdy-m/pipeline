# Source-only GitHub Releases

Use `.github/workflows/source-release.yml` when a project needs to publish its source snapshot without compiling or testing a platform-specific build. It is separate from `.github/workflows/release.yml`, which runs project commands and gathers build artifacts.

## Quick start

Create `.github/workflows/source-release.yml` in the consuming repository:

~~~yaml
name: Source Release

on:
  push:
    tags: ['v*']

permissions:
  contents: write

jobs:
  source-release:
    uses: m-mdy-m/pipeline/.github/workflows/source-release.yml@main
    with:
      # Match this to the ref after @ above. Use a release tag/SHA for production.
      pipeline-ref: main
      changelog-path: CHANGELOG.md
      changelog-missing-policy: fail
      changelog-asset-mode: archive-only
      source-archive-name: '{repository}-{tag}-source.zip'
      source-submodules: fail-if-present
~~~

Pin the reusable workflow to a reviewed commit SHA or version tag for production use. Keep `pipeline-ref` aligned with that same ref so the helper code is versioned with the workflow. If the reusable workflow is called from `@main`, the default `pipeline-ref: main` is correct.

The workflow does not run build or test commands. It takes the exact commit associated with the version tag, generates a custom ZIP with a single top-level directory, validates the contents, scans the files that will be published with Gitleaks, writes a manifest and checksums, and only then publishes a GitHub Release. `dry-run: true` exercises the same packaging/validation path but skips public Release creation. A branch dry-run uses the `Unreleased` changelog section; real tag releases must match their exact version section.

## Inputs

| Input | Default | Meaning |
| --- | --- | --- |
| `pipeline-ref` | `main` | Ref of this repository containing the helper script; align it with the reusable workflow ref. |
| `changelog-path` | empty | Exact changelog path. Empty means automatic detection, which requires exactly one candidate. |
| `changelog-missing-policy` | `fail` | `fail` stops on missing/empty changelog; `warn` continues without a changelog. |
| `release-notes-mode` | `section` | `section` extracts the version section; `full` uses the whole changelog; `file` uses `release-notes-path`. |
| `release-notes-path` | empty | Required tracked text file when `release-notes-mode: file`. |
| `changelog-asset-mode` | `archive-only` | `archive-only`, `archive-and-asset`, or `asset-only`. |
| `source-archive-name` | `{repository}-{tag}-source.zip` | ZIP basename template. Supports `{repository}`, `{tag}`, and `{version}`; no paths allowed. |
| `source-submodules` | `fail-if-present` | `fail-if-present`, `recursive`, or `omit`. No submodule behavior is implicit. |
| `source-exclude-patterns` | empty | Newline-separated glob patterns. Every excluded tracked path is printed in the log. Negated patterns are rejected. |
| `source-sensitive-path-patterns` | built-ins only | Additional path globs considered sensitive. Built-in patterns always apply. |
| `source-sensitive-allowlist-patterns` | safe `.env.*` examples | Explicit path exceptions to the path-based check. Keep exceptions narrow. These do not bypass Gitleaks. |
| `source-gitleaks-allowlist-path` | empty | Optional tracked TOML file with allowlist tables only. This does not allow changing or disabling Gitleaks rules. |
| `dry-run` | `false` | Assemble and verify assets, but do not create/update a public GitHub Release. |

The reusable workflow has an optional `submodule-token` secret for private GitHub submodules in `recursive` mode. It is used only for HTTPS GitHub URL authentication; only grant read access to the required repositories.

## Changelog discovery and validation

With an explicit `changelog-path`, only that path is checked. No fallback occurs when the requested file is missing. With automatic detection, exactly one of these tracked paths must exist:

- `CHANGELOG`, `CHANGELOG.md`, `CHANGELOG.txt`
- `docs/CHANGELOG`, `docs/CHANGELOG.md`, `docs/CHANGELOG.txt`

Zero candidates and multiple candidates are errors unless `changelog-missing-policy: warn` permits the missing/empty case. A non-empty changelog must still contain the exact tag version. `v1.2.3` maps to version `1.2.3`; for example, `## [1.2.3]`, `## 1.2.3`, `## v1.2.3`, and `Version 1.2.3` are recognized. Duplicate version sections are rejected. Real stable releases and real prerelease tags do not fall back to `Unreleased` or a base version. Only a branch smoke run uses `Unreleased` because its synthetic version does not exist in the changelog.

A blank or whitespace-only changelog follows `changelog-missing-policy`, matching the missing-file behavior. `asset-only` requires a non-empty changelog because that mode intentionally removes the changelog from the ZIP and promises it as a separate asset.

## Source ZIP contract

The archive is made from the Git tree for the exact tagged commit, not from the current runner workspace. It contains tracked files, including tracked hidden files, and excludes untracked or ignored workspace files. `.git` metadata is never packaged. The ZIP has one top-level directory such as `project-v1.2.3/` and is written deterministically where practical.

`source-exclude-patterns` removes matched tracked paths from the ZIP only; every removed path appears in the workflow log and the exclusion count is in `manifest.json`. The workflow never silently deletes a path to make a release pass. If the chosen changelog mode requires the changelog inside the ZIP, excluding that path is an error.

### Submodules

- `fail-if-present` is the safest default and stops when any submodule exists.
- `recursive` initializes the submodules recursively and exports only the exact commits pinned by the tagged parent tree. Failure to access a private module or fetch the pinned commit blocks release.
- `omit` excludes submodule content and emits a warning for every omitted submodule.

### Symlinks and path validation

Only relative symlinks whose targets resolve inside the effective source snapshot are accepted. Absolute, escaping, broken, cyclic, or platform-ambiguous links fail validation. Non-portable paths, traversal paths, reserved Windows device names, unsupported Git modes, `.git` metadata, duplicate ZIP member names, paths outside the single ZIP root, and CRC failures also block publication.

## Security checks

1. Built-in sensitive-path patterns cover common environment files, private keys, certificate/key containers, and likely credentials filenames. Additional patterns may be added. A match stops the job and reports the path; it is never auto-deleted. Safe sample files such as `.env.example` are explicitly allowlisted by default.
2. Gitleaks `v8.30.1` scans the actual staged source tree, not Git history. This keeps the scan aligned with the bytes intended for publication. Findings fail the job, and output is redacted.
3. A project may set `source-gitleaks-allowlist-path` to a tracked TOML file containing only `[allowlist]` or `[[allowlists]]` tables. The workflow composes these allowlists with Gitleaks' embedded default rules; it rejects extra top-level configuration so a caller cannot replace the detector rules through this input. Allowlisting a finding is an explicit maintainer decision and should be narrow.
4. The ZIP is reopened and validated, its member paths and CRCs are checked, then `manifest.json` and `SHA256SUMS` are generated and verified. No Release is published if any earlier step fails.

Path checks and Gitleaks are defense-in-depth, not a mathematical guarantee that every secret will be detected. Review release contents before introducing broad allowlists.

## Release assets

- The generated source ZIP, with the selected source snapshot.
- `manifest.json`, including tag, source commit, archive root, file count, changelog mode, submodule policy, and archive SHA-256.
- `SHA256SUMS`, containing SHA-256 digests for the downloadable assets other than the checksum file itself.
- The changelog's original basename when `archive-and-asset` or `asset-only` is selected and a changelog is present.

`release-notes.md` is used as the GitHub Release body, not published as a separate asset. Asset filename collisions stop publication. The workflow also refuses to overwrite an existing GitHub Release and uses `overwrite_files: false` to protect assets from accidental replacement.

## Local tests

Run:

~~~sh
make check
~~~

The tests cover common changelog headings, exact version section extraction, duplicate/missing sections, path safety, exclusion patterns, symlink containment, and integration tests for each changelog asset mode. `source-release-smoke.yml` runs those tests and performs an end-to-end dry run without publishing a Release.

## Modular implementation and logging

The CLI entry point remains \`scripts/source_release.py\`; implementation components live under \`scripts/pipeline_release/\`:

- \`runtime.py\`: shared paths, version expressions and process-local state.
- \`logger.py\`: structured logger facade using \`m-mdy-m/log.c\` through its stable C ABI.
- \`tools.py\`: environment/Git commands, safe command execution, SHA-256 and atomic filesystem helpers.
- \`git_snapshot.py\` and \`paths.py\`: Git tree/submodule handling, path policy and symlink validation.
- \`changelog.py\`, \`release_meta.py\`, \`security.py\`: changelog parsing, tag/name validation and Gitleaks config.
- \`prepare.py\`, \`archive.py\`, \`package.py\`: staging, deterministic ZIP validation and asset assembly.
- \`verify.py\`: post-download manifest/checksum/ZIP verifier.
- \`cli.py\`: command routing and top-level error reporting.

The workflow checks out \`m-mdy-m/log.c\` at commit \`c9b53e9901dc7103eb50be282ae055fe16e98f9a\`, compiles it, and sets \`PIPELINE_LOG_LIBRARY\`. The Python facade uses \`mmlog_logger_write()\`, the stable non-variadic ABI. A stderr fallback is used for isolated local tests only when no native library path is configured; a configured but missing library is an error.

### Verify a downloaded Source Release

Download the source ZIP, \`manifest.json\`, \`SHA256SUMS\`, and any separate changelog asset into one directory, then run:

~~~sh
python scripts/tools/verify_source_release.py ./downloaded-release
~~~

The verifier checks asset checksums, the manifest archive hash, ZIP CRC, member inventory and unlisted files. It is read-only and never publishes anything.

### Adding new components

Put reusable operations in a focused module under \`scripts/pipeline_release/\`; use \`prepare.py\`, \`package.py\` and \`cli.py\` for orchestration. Shared command and filesystem operations belong in \`tools.py\`, not copied into every script. Keep \`scripts/source_release.py\` as the stable compatibility entry point, add tests under \`tests/\`, and run \`make check\`.
