# pipeline

Reusable GitHub Actions workflows for building, testing, benchmarking, packaging, and publishing projects.

![CI](https://github.com/m-mdy-m/pipeline/actions/workflows/ci-main.yml/badge.svg)
![License](https://img.shields.io/github/license/m-mdy-m/pipeline)

## What it provides

| Workflow | Purpose |
|---|---|
| [ci.yml](.github/workflows/ci.yml) | Configurable build, test, lint, and toolchain setup |
| [benchmark.yml](.github/workflows/benchmark.yml) | Repeatable measurements, timing summaries, environment details, and artifacts |
| [release.yml](.github/workflows/release.yml) | Matrix builds, changelog-derived release notes, SHA-256 checksums, and GitHub Releases |
| [docker-publish.yml](.github/workflows/docker-publish.yml) | Multi-architecture Docker Hub publishing |
| [npm-publish.yml](.github/workflows/npm-publish.yml) | npm package validation and publishing |
| [pages.yml](.github/workflows/pages.yml) | Static site build and GitHub Pages deployment |
| [docs-check.yml](.github/workflows/docs-check.yml) | Markdown checks and GitHub Actions workflow linting |

The workflows are reusable: a project calls the workflow it needs and passes its own build/test commands and secrets. The catalog does not assume that every project uses the same language or build system.

## Quick start: CI

Add a caller workflow to your project:

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

Supported toolchain values are go, node, rust, python, c, and custom. Tool setup is provided for Go, Node.js, Rust, and Python; C/custom projects can use the runner's tools or add setup to their caller workflow.

## Quick start: GitHub Release

The release workflow is designed around a version tag such as v1.2.0. It validates the tag, checks the matching CHANGELOG.md section for stable releases, runs tests and builds for every matrix entry, collects the artifacts, creates checksums, and publishes release notes with the assets attached.

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
          {"id":"macos-arm64","os":"macos-15","artifact_path":"dist/*.tar.gz"},
          {"id":"windows-x64","os":"windows-latest","artifact_path":"dist/*.zip"}
        ]}
~~~

Each matrix entry can override build_command, test_command, and artifact_path. Use the [release guide](docs/RELEASES.md) for the full contract and CHANGELOG.md handling. The repository also has a release dry-run that exercises artifact creation without publishing a release.

For production, pin @main to a reviewed commit SHA or a published tag.

## Benchmarks

Use benchmark.yml to run a command several times. The uploaded artifact contains the raw logs, iteration CSV, timing summary, and runner environment information. Categories are micro, throughput, latency, memory, startup, scalability, regression, and size.

This repository runs a small self-benchmark on workflow/catalog changes. It measures the repeatability and runtime of make check, plus tracked source-size metrics; these are pipeline-maintenance measurements, not claims about application performance. See [benchmark methodology](docs/BENCHMARKS.md).

## Publishing workflows

- Docker Hub publishing expects the caller to map its own secrets to username and token; stable tags can publish latest, prerelease tags cannot.
- npm publishing uses the npm-token secret and publishes prereleases to the next dist-tag.
- Pages deployment is intentionally only a reusable workflow. Call it from a project workflow that controls when deployment is allowed.
- Publishing permissions should be granted only to the relevant caller/job. Never store tokens in workflow files.

See [workflow documentation](docs/WORKFLOWS.md), [secrets and permissions](docs/SECRETS.md), and [contributing](CONTRIBUTING.md).

## Repository flow

The repository follows the branch convention configured in [.gix/config](.gix/config): main, develop, and short-lived topic branches. The project structure is also described in [psx.yml](psx.yml).

## License

MIT. See [LICENSE](LICENSE).
