# pipeline

[![CI](https://github.com/m-mdy-m/pipeline/actions/workflows/ci-main.yml/badge.svg)](https://github.com/m-mdy-m/pipeline/actions/workflows/ci-main.yml)
[![License](https://img.shields.io/github/license/m-mdy-m/pipeline)](LICENSE)

**pipeline** helps you run the same project tasks in a consistent way. You can use it on your computer, in GitHub Actions, or in GitLab CI.

You do not need to know CI/CD to get started. Think of pipeline as a list of named tasks—such as checking the code, running tests, or preparing files—and a small runner that executes those tasks in the right order.

## How it works

There are three main parts:

1. **Task list — `pipeline.toml`**  
   This file says which tasks exist, what each task does, and which tasks must run first.
2. **Core — `scripts/pipeline_core/`**  
   The core reads the task list, checks it, runs commands, and records results. It does not depend on GitHub or GitLab.
3. **Provider adapters — `scripts/providers/`**  
   An adapter translates information from your computer or CI service into the format the core understands.

GitHub Actions workflows still handle GitHub-specific jobs such as uploading artifacts and publishing GitHub Releases. They call the shared core for tasks instead of defining a second copy of the task graph.

## Try it locally

You need Python 3.12 or newer. From the repository root, run:

```sh
python scripts/pipeline.py validate
python scripts/pipeline.py list
python scripts/pipeline.py run check
```

- `validate` checks the task configuration before anything runs.
- `list` shows the tasks that are available.
- `run check` runs the task named `check` and its required tasks first.

To save a machine-readable result report:

```sh
python scripts/pipeline.py run check --json --result .pipeline-artifacts/pipeline-result.json
```

You can also run through an adapter:

```sh
python scripts/providers/local/adapter.py run check --json
python scripts/providers/github/adapter.py task check --json
python scripts/providers/gitlab/adapter.py run check --json
```

The GitHub and GitLab adapters can be tested locally with suitable environment variables, but a local test is not the same as running on a hosted GitLab runner.

## Use pipeline in your own project

You can start by using the reusable GitHub Actions workflow. Create `.github/workflows/ci.yml` in your project:

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
      language: python
      build-command: python -m compileall -q .
      test-command: python -m unittest discover -s tests
```

Change the language and commands to match your project. Supported language values are `go`, `node`, `rust`, `python`, `c`, and `custom`. For production use, pin the workflow to a reviewed version tag or commit SHA rather than a moving branch.

## Workflows you can reuse

| Workflow | What it does |
| --- | --- |
| [CI](.github/workflows/ci.yml) | Runs your build, tests, and optional lint command |
| [Build release](.github/workflows/release.yml) | Builds release files for one or more targets, checks the changelog, and publishes a GitHub Release |
| [Source release](.github/workflows/source-release.yml) | Checks and packages a source ZIP without compiling the project |
| [Benchmark](.github/workflows/benchmark.yml) | Runs a command several times and saves timing results and logs |
| [Docker Hub](.github/workflows/docker-publish.yml) | Builds and publishes a multi-architecture Docker image |
| [npm](.github/workflows/npm-publish.yml) | Tests and publishes an npm package |
| [GitHub Pages](.github/workflows/pages.yml) | Builds and deploys a static website |
| [Documentation checks](.github/workflows/docs-check.yml) | Checks Markdown and GitHub Actions workflow syntax |

These are reusable GitHub Actions workflows: your project calls them from its own workflow. The repository also has separate smoke-test workflows that check release preparation without publishing a public release.

## Repository map

```text
pipeline.toml                 Shared task list
scripts/pipeline.py           Simple command-line entry point
scripts/pipeline_core/        Provider-neutral task runner
scripts/providers/local/      Local adapter
scripts/providers/github/     GitHub Actions adapter
scripts/providers/gitlab/     GitLab CI adapter
scripts/pipeline_release/     Shared source-release helper code
.github/workflows/            GitHub-specific automation and reusable workflows
.gitlab-ci.yml                Example GitLab CI configuration
tests/                        Automated tests
docs/                         Guides and workflow details
```

## Read next

- [Architecture](docs/ARCHITECTURE.md) — how the parts fit together.
- [Workflow guide](docs/WORKFLOWS.md) — choose the workflow for your project.
- [Secrets and permissions](docs/SECRETS.md) — how to handle publishing credentials.
- [Benchmarks](docs/BENCHMARKS.md) — understand benchmark output.
- [Build releases](docs/RELEASES.md) — publish compiled or built files.
- [Source releases](docs/SOURCE-RELEASES.md) — publish a source ZIP safely.
- [Source-release design notes](docs/SOURCE-RELEASE-DECISIONS.md) — why the source archive follows these rules.

## Project status

The shared task runner and local/GitHub/GitLab adapters have automated tests. The GitHub Actions workflows are exercised by this repository's CI. The GitLab configuration is an example and has not yet been verified on an actual GitLab-hosted runner.

See [CHANGELOG.md](CHANGELOG.md) for changes and [LICENSE](LICENSE) for the license.
