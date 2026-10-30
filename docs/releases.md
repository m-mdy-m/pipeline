# Build and publish a release

pipeline provides two different release workflows. Choose the one that matches what you want to publish.

- **Build release**: run your build and test commands, collect the files they produce, and attach those files to a GitHub Release.
- **Source release**: make a ZIP from the exact files tracked by a Git tag, then check the ZIP and its contents.

A source ZIP does not compile your project. A build release does not replace the source-release safety checks.

## Release this repository

A push of a version tag such as `v1.1.1` starts `.github/workflows/release-on-tag.yml`.

That workflow calls the reusable build-release workflow in this repository. It:

1. Checks out the tagged commit.
2. Uses the shared release helper to validate the tag and prepare the matching changelog section.
3. Runs the repository's task checks.
4. Creates a compressed source archive from the tagged Git commit.
5. Generates a SHA-256 checksum file for the release assets.
6. Publishes the notes, archive, and checksums as a GitHub Release.

The workflow does not publish a release from a normal branch push. To publish version `1.1.1`, the tag must be named `v1.1.1` and pushed to GitHub after the version section has been added to `CHANGELOG.md`.

From a checkout that contains the release commit:

~~~sh
git tag -a v1.1.1 -m "pipeline 1.1.1"
git push origin v1.1.1
~~~

The tag points to the current commit. If you change the changelog or code after creating the tag, create a new version tag rather than moving the old one.

## Use the build-release workflow in another project

~~~yaml
name: Release

on:
  push:
    tags: ["v*"]

permissions:
  contents: write

jobs:
  release:
    uses: m-mdy-m/pipeline/.github/workflows/release.yml@main
    with:
      pipeline-ref: main
      test-command: make check
      build-command: make release
      artifact-path: dist/*
      changelog-path: CHANGELOG.md
~~~

Replace the commands and artifact path with the ones used by your project. A release build must create at least one file matching `artifact-path`. A failed test or build prevents publication.

For multi-platform releases, pass a JSON `build-matrix-json` value. Each matrix entry needs an `id` and an `os`. An entry can also override `test_command`, `build_command`, or `artifact_path`.

## Try a build release without publishing

Set `dry-run: true` when calling the workflow. It still validates the tag or development version, runs tests and builds, collects assets, and creates checksums. It skips the GitHub Release publishing job.

The repository's `github-release-smoke.yml` workflow uses this mode on branch changes.

## Publish a source-only release

Use `source-release.yml` when you want a ZIP of the exact tagged source instead of compiled build files:

~~~yaml
name: Source release

on:
  push:
    tags: ["v*"]

permissions:
  contents: write

jobs:
  source:
    uses: m-mdy-m/pipeline/.github/workflows/source-release.yml@main
    with:
      pipeline-ref: main
      changelog-path: CHANGELOG.md
      changelog-missing-policy: fail
      source-archive-name: "{repository}-{tag}-source.zip"
      source-submodules: fail-if-present
~~~

The source workflow can include pinned submodule contents, omit submodules, or stop when submodules are present. Choose the behavior explicitly. It also checks sensitive paths, scans the published files with Gitleaks, validates the ZIP, and writes `manifest.json` and `SHA256SUMS`.

Use `dry-run: true` to test the packaging path without publishing.

## Version and changelog rules

Tags use this format:

- Stable: `vMAJOR.MINOR.PATCH`, for example `v1.1.1`.
- Prerelease: `vMAJOR.MINOR.PATCH-alpha.N`, `-beta.N`, or `-rc.N`.

Before creating a stable tag, add a matching heading to the changelog:

~~~markdown
## [1.1.1] - 2026-10-30

### Added

- Describe what is new.
~~~

A stable release without its matching changelog section is rejected. Prerelease builds and dry-runs prefer the `[Unreleased]` section. For source-release branch dry-runs, when `[Unreleased]` is absent, the helper uses the newest version-specific section as informational release notes.

## Permissions and secrets

The workflow that calls a publishing workflow must allow `contents: write`. The publishing job uses that permission to create the GitHub Release.

The default `GITHUB_TOKEN` is enough for ordinary GitHub Releases. The build-release workflow also accepts an optional `release-token` secret when a project needs a different token. Source releases need `submodule-token` only when they must read private GitHub submodules.

Do not put tokens in `pipeline.toml`, command strings, or committed workflow files.
