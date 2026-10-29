# Publishing a source ZIP

A source release shares the files needed to read or build a project, without building a separate binary for each operating system.

Use [`source-release.yml`](../.github/workflows/source-release.yml) for this. Use [Build releases](RELEASES.md) when you need compiled or packaged output.

## Quick start

Add a workflow like this to the project you want to release:

```yaml
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
      pipeline-ref: main
      changelog-path: CHANGELOG.md
      changelog-missing-policy: fail
      source-archive-name: '{repository}-{tag}-source.zip'
      source-submodules: fail-if-present
```

For a real project, pin the workflow to a reviewed version tag or commit SHA. Set `pipeline-ref` to the same version so the helper code and workflow stay in sync.

## What happens?

The workflow takes the exact files tracked by the version tag, then checks and packages them. It creates a ZIP with one top-level project folder, a file manifest, and SHA-256 checksums. It also scans the files that will be published for secrets and rejects unsafe paths or invalid ZIP entries.

It does **not** run your project's build or test commands. Use the build-release workflow for that.

## Important settings

| Input | What it means |
| --- | --- |
| `changelog-path` | The changelog file to use. If empty, the workflow searches a small list of known names and requires one clear match. |
| `changelog-missing-policy` | `fail` stops if the changelog is missing or empty; `warn` allows the release to continue when the rules permit it. |
| `release-notes-mode` | Use the current version section, the full changelog, or a separate text file. |
| `changelog-asset-mode` | Choose whether the changelog is only used for notes, included as a release asset, or both. |
| `source-archive-name` | ZIP filename template. Supports `{repository}`, `{tag}`, and `{version}`. |
| `source-submodules` | Choose `fail-if-present`, `recursive`, or `omit`. Submodules are never handled silently. |
| `source-exclude-patterns` | Optional newline-separated patterns for files to leave out. Excluded files are listed in the logs. |
| `source-sensitive-path-patterns` | Add extra file-path patterns that should be treated as sensitive. Built-in checks always remain active. |
| `source-sensitive-allowlist-patterns` | Explicit exceptions to the path check. These do not bypass secret scanning. |
| `source-gitleaks-allowlist-path` | Optional tracked TOML file containing approved Gitleaks allowlist entries. It cannot turn off the scanner. |
| `dry-run` | Builds and checks the archive but does not publish a public GitHub Release. |

## Safety rules

- The ZIP contains tracked files from the exact tag snapshot, including tracked hidden files. Untracked and ignored files are not included.
- Git internals such as `.git` must not be present in the ZIP.
- Secret findings and unsafe paths stop publication unless a permitted, explicit exception applies.
- The ZIP is checked for invalid paths, path traversal, duplicate entries, and file corruption.
- Submodule behavior must be chosen explicitly.

Run a dry-run before publishing changes to your release settings. The repository's smoke workflow tests this path without creating a public release.
