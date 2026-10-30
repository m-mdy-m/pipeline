# Publishing a source ZIP

A source release shares the files needed to read or build a project. It does not compile binaries for different operating systems.

Use [`source-release.yml`](../.github/workflows/source-release.yml) for this. Use [Build releases](RELEASES.md) when you need compiled or packaged output.

## Quick start

Add a workflow to the project you want to release:

~~~yaml
name: Source Release

on:
  push:
    tags: ["v*"]

permissions:
  contents: write

jobs:
  source-release:
    uses: m-mdy-m/pipeline/.github/workflows/source-release.yml@main
    with:
      pipeline-ref: main
      changelog-path: CHANGELOG.md
      changelog-missing-policy: fail
      source-archive-name: "{repository}-{tag}-source.zip"
      source-submodules: fail-if-present
~~~

For production, pin the workflow to a reviewed version tag or commit SHA. Set `pipeline-ref` to the same value so the workflow and helper code stay aligned.

## What happens?

The workflow checks out the exact commit named by the tag. The shared code in `scripts/pipeline_release/` reads the tracked files, applies path and secret checks, builds the ZIP, and verifies its contents.

The GitHub workflow supplies the provider context, runs the secret scanner, uploads the prepared bundle, and publishes the GitHub Release. The shared source packaging rules do not depend on GitHub Actions.

It does **not** run your project's build or test commands. Use the build-release workflow for that.

## Important settings

| Input | Meaning |
| --- | --- |
| `changelog-path` | Explicit tracked changelog file. When empty, the helper looks for one unambiguous supported candidate. |
| `changelog-missing-policy` | `fail` stops when the changelog is missing or empty; `warn` allows omission when the other rules permit it. |
| `release-notes-mode` | Use the current version section, the full changelog, or a separate text file. |
| `changelog-asset-mode` | Choose whether the changelog is only used for notes, included as an asset, or both. |
| `source-archive-name` | ZIP filename template. Supports `{repository}`, `{tag}`, and `{version}`. |
| `source-submodules` | Choose `fail-if-present`, `recursive`, or `omit`. |
| `source-exclude-patterns` | Optional newline-separated patterns for files to leave out. Excluded paths are listed in the logs. |
| `source-sensitive-path-patterns` | Extra path patterns that should be treated as sensitive. Built-in checks remain active. |
| `source-sensitive-allowlist-patterns` | Explicit path-pattern exceptions. These do not bypass secret scanning. |
| `source-gitleaks-allowlist-path` | Optional tracked TOML file containing approved Gitleaks allowlist entries. |
| `dry-run` | Build and verify the archive without publishing a public GitHub Release. |

## Safety rules

- Only tracked files from the exact tagged commit are included. Untracked and ignored files are not included.
- Git internals such as `.git` must not appear in the ZIP.
- Secret findings, unsafe paths, and invalid ZIP entries stop publication.
- Submodule behavior must be chosen explicitly.
- Exclusions are shown in the logs so that omitted files are not hidden.

Run a dry-run before publishing changes to your release settings. The repository's smoke workflow tests this path without creating a public release.
