# GitHub Releases

The reusable release workflow is .github/workflows/release.yml. It is based on the tag-validation, per-platform build, changelog parsing, artifact aggregation, and checksum pattern used by [cdin-editor/kernel](https://github.com/cdin-editor/kernel/blob/main/.github/workflows/release.yml), but exposes those decisions as caller inputs rather than hard-coding one project's ABI or packaging commands.

## Release contract

1. Run the caller workflow on a tag that matches vMAJOR.MINOR.PATCH or vMAJOR.MINOR.PATCH-(alpha|beta|rc).N.
2. For a stable tag, CHANGELOG.md must contain a matching heading such as ## [1.2.0]. A stable release without the matching section is rejected.
3. Every build-matrix entry runs tests before the build and must upload at least one artifact. One failed target blocks the release.
4. The assemble job collects each target's artifacts without flattening them into a shared directory, generates SHA256SUMS, and uploads a release bundle. The publish job then attaches the release notes and bundle assets to GitHub Releases.
5. Prerelease tags are marked prerelease and cannot become GitHub's latest stable release.
6. Set dry-run: true to exercise tag/changelog preparation, tests, builds, artifact upload, checksum generation, and release-bundle assembly without publishing. Only the final GitHub Release publishing job is skipped. The repository's github-release-smoke.yml invokes this on catalog changes.

## Example caller

~~~yaml
name: Release

on:
  push:
    tags: ['v*']

permissions:
  contents: write

jobs:
  release:
    uses: m-mdy-m/pipeline/.github/workflows/release.yml@main
    with:
      test-command: make check
      build-command: make release
      artifact-path: dist/*
      build-matrix-json: >-
        {"include":[
          {"id":"linux-x64","os":"ubuntu-24.04","artifact_path":"dist/*.tar.gz"},
          {"id":"linux-arm64","os":"ubuntu-24.04-arm","artifact_path":"dist/*.tar.gz"},
          {"id":"macos-arm64","os":"macos-15","artifact_path":"dist/*.tar.gz"},
          {"id":"windows-x64","os":"windows-latest","artifact_path":"dist/*.zip"}
        ]}
~~~

Each matrix entry requires an id and os. Optional build_command, test_command, and artifact_path values override the workflow defaults for that target. Artifact paths are relative to the checked-out repository root. Configure the relevant build toolchains in your project or in a project-specific caller before using the release workflow.

## Changelog format

~~~markdown
## [Unreleased]

## [1.2.0]

### Added
- Added the new feature.

### Fixed
- Fixed the reported issue.
~~~

For prereleases, the workflow first looks for an exact section, then the base stable version, then [Unreleased]. A prerelease can therefore use a draft section such as ## [1.3.0-rc.1], while a stable release always requires its exact version heading.

## Permissions

The caller must grant contents: write for the actual publish job. A dry-run does not publish a release. Keep any optional release-token secret scoped to the intended repository; otherwise the workflow uses the caller's GITHUB_TOKEN.
