# pipeline

Reusable CI/CD pipelines and project workflow templates for the m-mdy-m ecosystem.

![CI](https://github.com/m-mdy-m/pipeline/actions/workflows/ci.yml/badge.svg)
![License](https://img.shields.io/github/license/m-mdy-m/pipeline)
![GitHub release](https://img.shields.io/github/v/release/m-mdy-m/pipeline)

> A collection of reusable GitHub Actions workflows for build, test, benchmark, documentation, release, Docker Hub, npm, and GitHub Pages projects.

## Goals

- Reusable workflows called by other repositories with `workflow_call`.
- Separate validation from publishing; publish only on explicit release events.
- Support C/C++ libraries and SDKs, Go/Rust CLIs, npm packages, and documentation websites.
- Treat Docker images as SDK/build environments when appropriate, not always as long-running services.
- Keep credentials in GitHub Actions secrets; never put tokens in repository files.

## Workflow catalog

| Workflow | Purpose |
|---|---|
| `ci.yml` | General build, test, lint, and quality gates |
| `benchmark.yml` | Repeatable benchmark runs and artifact upload |
| `release.yml` | Cross-platform release archives and checksums |
| `docker-publish.yml` | Multi-architecture Docker Hub image publishing |
| `npm-publish.yml` | npm package validation and publishing |
| `pages.yml` | Build and deploy documentation websites to GitHub Pages |
| `docs-check.yml` | Markdown/link checks and documentation validation |

## Usage

Call a reusable workflow from a project:

```yaml
name: CI
on:
  pull_request:
  push:
    branches: [main, develop]
jobs:
  quality:
    uses: m-mdy-m/pipeline/.github/workflows/ci.yml@main
    with:
      language: go
      build-command: make build
      test-command: make test
```

Pin `@main` to a reviewed tag or commit SHA for production-critical projects.

## Branch flow

```text
main
 └── develop
      ├── feature/*
      ├── bugfix/*
      ├── hotfix/*
      └── release/*
```

The branch flow is managed by [gix](https://github.com/m-mdy-m/gix). This repository uses `.gix/config`.

## Local development

See [CONTRIBUTING.md](CONTRIBUTING.md), [docs/WORKFLOWS.md](docs/WORKFLOWS.md), and [docs/SECRETS.md](docs/SECRETS.md).

## License

MIT — see [LICENSE](LICENSE).
