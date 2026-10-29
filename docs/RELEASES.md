# Publishing a build release

Use [`release.yml`](../.github/workflows/release.yml) when your project needs to build files—such as binaries, archives, or packages—and attach them to a GitHub Release.

If you only want to share the source code as a ZIP, use [Source releases](SOURCE-RELEASES.md) instead.

## What the build release does

1. Checks the version tag.
2. Checks that `CHANGELOG.md` contains a section for a stable release.
3. Runs your test and build commands for each configured target.
4. Collects the files produced by each target.
5. Creates SHA-256 checksums and a release bundle.
6. Publishes the files and release notes on GitHub, unless dry-run mode is enabled.

If a build target fails, the release does not continue to publishing.

## Example

Create a workflow in your project:

```yaml
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
          {"id":"windows-x64","os":"windows-latest","artifact_path":"dist/*.zip"}
        ]}
```

Change the commands, operating systems, and artifact paths to match your project. Every target needs an `id` and an `os`. See the workflow file for all available inputs.

## Version tags and changelog

Use tags like `v1.2.3` for stable releases or `v1.2.3-rc.1` for a release candidate. For a stable release, add a matching heading to `CHANGELOG.md` before creating the tag:

```markdown
## [1.2.3]

### Added
- Describe the new feature.
```

## Try it safely

Set `dry-run: true` to test the release steps without creating a public GitHub Release. The repository's release smoke workflow uses this mode.
