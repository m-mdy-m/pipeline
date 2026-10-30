# Choosing a workflow

A workflow tells GitHub Actions when to run a job and which runner or GitHub service to use. The reusable workflows in this repository help other projects avoid copying common CI/CD setup.

## Which workflow should I use?

| What you need | Workflow |
| --- | --- |
| Build and test a project with your own commands | [`ci.yml`](../.github/workflows/ci.yml) |
| Build files for several operating systems and publish a GitHub Release | [`release.yml`](../.github/workflows/release.yml) |
| Publish a ZIP of the exact source snapshot | [`source-release.yml`](../.github/workflows/source-release.yml) |
| Repeat a command and save timing data | [`benchmark.yml`](../.github/workflows/benchmark.yml) |
| Publish a Docker image | [`docker-publish.yml`](../.github/workflows/docker-publish.yml) |
| Publish a package to npm | [`npm-publish.yml`](../.github/workflows/npm-publish.yml) |
| Build and deploy a website | [`pages.yml`](../.github/workflows/pages.yml) |
| Check Markdown and workflow syntax | [`docs-check.yml`](../.github/workflows/docs-check.yml) |

## Call a reusable workflow

Create a workflow in the project that should be built. Call the shared workflow with `uses` and provide the commands for that project.

~~~yaml
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
~~~

Change the language and commands to match the project. The CI workflow supports `go`, `node`, `rust`, `python`, `c`, and `custom`. For production, pin `uses` to a reviewed release tag or commit SHA.

## How the workflow and scripts share responsibility

The shared task engine is in `scripts/pipeline_core/` and the task graph is in `pipeline.toml`. Provider adapters in `scripts/providers/` translate the runner's variables before the core is called.

The repository's own CI uses the GitHub adapter to run `python scripts/providers/github/adapter.py task check --json`. GitLab uses the same task graph through `scripts/providers/gitlab/adapter.py`.

The benchmark and build-release workflows check out the helper code from this repository and call `scripts/benchmark.py` or `scripts/build_release.py`. Their YAML handles runner setup, input wiring, artifact upload, and publication. Set `pipeline-ref` to the same tag or commit used in the reusable workflow reference.

Publishing to GitHub Releases, Docker Hub, npm, and GitHub Pages remains in GitHub workflows because those steps use provider-specific actions, permissions, and credentials.

## Test a release without publishing

The `github-release-smoke.yml` and `source-release-smoke.yml` workflows run the release preparation paths in dry-run mode. They validate packaging and checksums without creating a public release.

For real publishing, use a version tag and the smallest permissions and secrets required by the destination service.
