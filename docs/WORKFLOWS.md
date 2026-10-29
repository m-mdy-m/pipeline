# Which workflow should I use?

A workflow is a set of steps that a CI service runs for you. The workflows in this repository are reusable: another repository can call them instead of copying all their steps.

## Pick a workflow

| If you want to… | Use |
| --- | --- |
| Build your project and run tests | [`ci.yml`](../.github/workflows/ci.yml) |
| Publish compiled or packaged files for a version | [`release.yml`](../.github/workflows/release.yml) |
| Publish a ZIP of the source code | [`source-release.yml`](../.github/workflows/source-release.yml) |
| Run a command repeatedly and compare its timing | [`benchmark.yml`](../.github/workflows/benchmark.yml) |
| Publish a Docker image | [`docker-publish.yml`](../.github/workflows/docker-publish.yml) |
| Publish a package to npm | [`npm-publish.yml`](../.github/workflows/npm-publish.yml) |
| Build and deploy a website | [`pages.yml`](../.github/workflows/pages.yml) |
| Check Markdown and workflow syntax | [`docs-check.yml`](../.github/workflows/docs-check.yml) |

## How to call a reusable workflow

Create a workflow in your own repository and call the shared workflow with `uses`. For example:

```yaml
name: CI

on:
  pull_request:
  push:
    branches: [main, develop]

permissions:
  contents: read

jobs:
  checks:
    uses: m-mdy-m/pipeline/.github/workflows/ci.yml@main
    with:
      language: go
      build-command: go build ./...
      test-command: go test ./...
      lint-command: go vet ./...
```

The commands must match your project. The CI workflow supports `go`, `node`, `rust`, `python`, `c`, and `custom`. For production, pin `uses` to a reviewed release tag or commit SHA.

## How the workflows fit the new architecture

The task engine lives in `scripts/pipeline_core/`; the task graph lives in `pipeline.toml`. Provider adapters translate environment details before the core runs. The workflows in `.github/workflows/` are GitHub-specific wrappers and can also upload artifacts or publish packages.

The repository's own CI runs the shared task graph through `scripts/providers/github/adapter.py`. The GitLab example in `.gitlab-ci.yml` calls the same task graph through the GitLab adapter.

## Testing without publishing

The `github-release-smoke.yml` and `source-release-smoke.yml` workflows exercise release preparation and artifact checks without creating a public release. They are intended to catch problems before a real version tag is published.
