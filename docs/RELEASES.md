# Publishing a build release

Use [`release.yml`](../.github/workflows/release.yml) when a project needs to build binaries, archives, packages, or other downloadable files and attach them to a GitHub Release.

Use [Source releases](SOURCE-RELEASES.md) when you only need a ZIP of the source code and do not need to build the project.

## What happens?

1. The GitHub adapter normalizes the tag, commit, and repository context.
2. The shared release helper validates the version and reads the matching changelog section.
3. Each build-matrix target runs the project's test and build commands.
4. GitHub Actions collects the files produced by each target.
5. The shared release helper creates a SHA-256 checksum list for the collected files.
6. The GitHub workflow publishes the notes and files, unless dry-run mode is enabled.

The version and changelog rules and checksum generation live in `scripts/pipeline_release/build.py`. The workflow only coordinates runners, transfers artifacts, and publishes the GitHub Release.

## Example

Create a workflow in the project you want to release:

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
      build-matrix-json: >-
        {"include":[
          {"id":"linux-x64","os":"ubuntu-24.04","artifact_path":"dist/*.tar.gz"},
          {"id":"windows-x64","os":"windows-latest","artifact_path":"dist/*.zip"}
        ]}
~~~

Every matrix entry needs an `id` and an `os`. You can override the test command, build command, or artifact path for an individual target. See the workflow file for all available inputs.

For production, pin the `uses` reference to a reviewed release tag or commit SHA. Set `pipeline-ref` to that same value; this keeps the workflow and its helper scripts on the same version.

## Tags and changelog

Use tags such as `v1.2.3` for stable releases and `v1.2.3-rc.1` for release candidates. The supported prerelease labels are `alpha`, `beta`, and `rc`.

A real stable release requires a matching section in the changelog before the tag is published:

~~~markdown
## [1.2.3]

### Added
- Describe the new feature.
~~~

Prerelease notes use the matching version section when present. Otherwise, the helper can fall back to the matching stable section or `[Unreleased]`. A stable release without its version section is rejected.

## Test safely

Set `dry-run: true` to prepare release notes, build all targets, collect artifacts, and generate checksums without creating a GitHub Release. The repository's release smoke workflow uses this mode.
