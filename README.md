# pipeline

[![CI](https://github.com/m-mdy-m/pipeline/actions/workflows/ci-main.yml/badge.svg)](https://github.com/m-mdy-m/pipeline/actions/workflows/ci-main.yml)
[![License](https://img.shields.io/github/license/m-mdy-m/pipeline)](LICENSE)

**pipeline** is a catalog of reusable GitHub Actions workflows for project CI, multi-platform releases, benchmarks, and publishing. A consuming repository adds a small caller workflow and supplies its own commands, build matrix, and secrets.

It is designed to reuse the same workflow logic across repositories without forcing every project into one language, build system, or release layout.

## Features

- **CI:** configure build, test, and optional lint commands for Go, Node.js, Rust, Python, C, or custom projects.
- **Build Releases:** validate version tags, run tests and matrix builds, collect artifacts, generate SHA-256 checksums, and publish a release.
- **Source Releases:** package the exact Git-tag snapshot into a configurable source ZIP, validate changelog/version rules, scan published content with Gitleaks, and generate a manifest plus checksums.
- **Benchmarks:** repeat a command, retain per-run logs, capture runner details, and export min/median/mean/max timing summaries.
- **Publishing:** reusable workflows for Docker Hub, npm, and GitHub Pages.
- **Validation:** Markdown lint, GitHub Actions syntax/expression lint, and a repository workflow inventory check.

## Quick start

Create a workflow in the consuming project, for example `.github/workflows/ci.yml`:

~~~yaml
name: CI

on:
  pull_request:
  push:
    branches: [main, develop]

permissions:
  contents: read

jobs:
  quality:
    uses: m-mdy-m/pipeline/.github/workflows/ci.yml@main
    with:
      language: go
      build-command: go build ./...
      test-command: go test ./...
      lint-command: go vet ./...
~~~

The supported `language` values are `go`, `node`, `rust`, `python`, `c`, and `custom`. Go, Node.js, Rust, and Python toolchain setup is provided; C and custom projects can prepare their own toolchain in the caller workflow.

For production repositories, pin the reusable workflow to a reviewed commit SHA or a version tag instead of relying on a moving `@main` reference.

## Available workflows

| Workflow | Purpose |
| --- | --- |
| [`ci.yml`](.github/workflows/ci.yml) | Build, test, and optional lint |
| [`release.yml`](.github/workflows/release.yml) | Tag and changelog validation, matrix builds, checksums, and GitHub Releases |
| [`source-release.yml`](.github/workflows/source-release.yml) | Source-only ZIP, changelog policy, secret/path checks, manifest, and checksums |
| [`benchmark.yml`](.github/workflows/benchmark.yml) | Repeated commands and timing artifacts |
| [`docker-publish.yml`](.github/workflows/docker-publish.yml) | Multi-architecture Docker Hub publishing |
| [`npm-publish.yml`](.github/workflows/npm-publish.yml) | npm package validation and publication |
| [`pages.yml`](.github/workflows/pages.yml) | Static-site build and GitHub Pages deployment |
| [`docs-check.yml`](.github/workflows/docs-check.yml) | Markdown and workflow validation |

All entries above are reusable workflows. Repository-specific test and smoke workflows are kept separate so they do not accidentally publish packages, containers, or a public release.

## GitHub Release example

The release workflow follows the useful pattern from [`cdin-editor/kernel`](https://github.com/cdin-editor/kernel/blob/main/.github/workflows/release.yml): version tags drive the release, stable versions must have a matching `CHANGELOG.md` section, and each configured build target uploads its own assets.

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

Each matrix target can override `build_command`, `test_command`, and `artifact_path`. Adjust commands and artifact patterns to match the consuming project's actual package layout. A failed test/build or missing artifact blocks publication.

For a stable tag such as `v1.2.0`, include a `## [1.2.0]` section in `CHANGELOG.md`. The workflow marks supported prerelease tags as prereleases and never promotes them to the stable `latest` release.

See [Release guide](docs/RELEASES.md) for the full contract and dry-run behavior.

## Source-only Release example

Use `source-release.yml` when the deliverable is the source snapshot itself, not compiled binaries. This workflow does not build or test the project; run CI before tagging it.

~~~yaml
name: Source Release

on:
  push:
    tags: ['v*']

permissions:
  contents: write

jobs:
  source:
    uses: m-mdy-m/pipeline/.github/workflows/source-release.yml@main
    with:
      # Keep this aligned with the ref in `uses` (pin both to the same SHA/tag in production).
      pipeline-ref: main
      changelog-path: CHANGELOG.md
      changelog-missing-policy: fail
      release-notes-mode: section
      changelog-asset-mode: archive-and-asset
      source-archive-name: "{repository}-{tag}-source.zip"
      source-submodules: fail-if-present
~~~

The default archive is built from files tracked by the exact tag commit, contains one top-level directory, and excludes `.git` metadata and workspace-only files. The release bundle includes `manifest.json` and `SHA256SUMS`. See [Source Release contract](docs/SOURCE-RELEASES.md) for changelog modes, exclusions, submodules, Gitleaks allowlists, and security behavior.

## Benchmarks

Use `benchmark.yml` to run a command multiple times. It uploads raw per-iteration logs, `iterations.csv`, `summary.csv`, and runner environment information. Supported categories are `micro`, `throughput`, `latency`, `memory`, `startup`, `scalability`, `regression`, and `size`.

This repository also benchmarks itself: five runs of `make check` and five samples of tracked source size. Those are pipeline-maintenance measurements, not claims about application performance.

See [Benchmark methodology](docs/BENCHMARKS.md) and the [latest benchmark run](https://github.com/m-mdy-m/pipeline/actions/workflows/benchmark-self.yml).

## Publishing

- **Docker Hub:** configure the `username` and `token` reusable-workflow secrets. Stable tags may publish `latest`; prereleases must not.
- **npm:** map the project's `NPM_TOKEN` to `npm-token`. Prereleases publish using the `next` dist-tag.
- **GitHub Pages:** configure the build command and output directory, then grant `pages: write` and `id-token: write` in the calling workflow.

Publishing workflows are not run against external registries from this repository's test runs. They are syntax-checked here; consumers must configure their own credentials and targets.

See [Secrets and permissions](docs/SECRETS.md) and [Workflow catalog](docs/WORKFLOWS.md).

## Development

Run the repository checks locally:

~~~sh
make check
~~~

The main workflows run the same documentation/workflow checks. `github-release-smoke.yml` exercises the build-release bundle; `source-release-smoke.yml` runs the source archive contract tests, Gitleaks scan, ZIP validation, manifest, and checksums. Both skip public release creation.

Contribution instructions are in [CONTRIBUTING.md](CONTRIBUTING.md). The repository flow is defined in [`.gix/config`](.gix/config), and its project structure rules are in [`psx.yml`](psx.yml).

## License

MIT. See [LICENSE](LICENSE).
