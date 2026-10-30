# pipeline

[![CI](https://github.com/m-mdy-m/pipeline/actions/workflows/ci-main.yml/badge.svg)](https://github.com/m-mdy-m/pipeline/actions/workflows/ci-main.yml)
[![License](https://img.shields.io/github/license/m-mdy-m/pipeline)](LICENSE)

**pipeline** is a small automation engine for running the same project tasks locally and in different CI services.

You describe the work once, then choose where it runs. The task engine does not need to know whether the caller is GitHub Actions, GitLab CI, or a local terminal.

## How it works

pipeline has three main layers:

1. **Task configuration — `pipeline.toml`**  
   Names each task, its command, and the tasks that must run before it.
2. **Shared scripts — `scripts/`**  
   Validates the configuration, runs tasks, collects results, prepares release data, and measures commands. This code does not depend on a CI provider.
3. **Provider adapters — `scripts/providers/`**  
   Translate provider-specific environment variables into the common `PIPELINE_*` context before calling the shared scripts.

GitHub workflows and the GitLab configuration are entry points. They decide when to run the scripts and handle service-specific features such as uploading artifacts or publishing a release. They should not contain a second implementation of task, benchmark, or release-preparation logic.

## Run it locally

You need Python 3.12 or newer. Run these commands from the repository root:

~~~sh
python scripts/pipeline.py validate
python scripts/pipeline.py list
python scripts/pipeline.py run check
~~~

- `validate` checks `pipeline.toml` without running project tasks.
- `list` shows the configured tasks.
- `run check` runs the full task sequence, including validation and tests.

To save the result as JSON:

~~~sh
python scripts/pipeline.py run check --json --result .pipeline-artifacts/pipeline-result.json
~~~

## Use a provider adapter

Adapters keep provider variables out of the shared task engine. Each adapter creates the same `PIPELINE_*` context and then calls the core.

~~~sh
# Local terminal
python scripts/providers/local/adapter.py run check --json

# GitHub Actions
python scripts/providers/github/adapter.py task check --json

# GitLab CI
python scripts/providers/gitlab/adapter.py run check --json
~~~

The GitHub and GitLab adapters can also be tested with simulated environment variables. That checks the adapter contract; it does not replace a run on the actual CI service.

## Reuse a GitHub workflow

For a project that uses ordinary build and test commands, call the reusable CI workflow from your own repository:

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
      language: python
      build-command: python -m compileall -q .
      test-command: python -m unittest discover -s tests
~~~

The reusable CI workflow prepares the requested toolchain and runs your commands. It is a GitHub integration, not a replacement for the provider-neutral task engine. Pin the workflow to a reviewed tag or commit SHA for production use.

## Available workflows

| Workflow | Purpose |
| --- | --- |
| [CI](.github/workflows/ci.yml) | Prepare a language toolchain and run caller-provided build, test, and lint commands |
| [Build release](.github/workflows/release.yml) | Build for one or more targets and publish verified artifacts |
| [Source release](.github/workflows/source-release.yml) | Package and check the exact tagged source snapshot |
| [Benchmark](.github/workflows/benchmark.yml) | Run the shared benchmark script and upload its reports |
| [Docker Hub](.github/workflows/docker-publish.yml) | Publish a multi-architecture Docker image |
| [npm](.github/workflows/npm-publish.yml) | Test and publish an npm package |
| [GitHub Pages](.github/workflows/pages.yml) | Build and deploy a static website |
| [Documentation checks](.github/workflows/docs-check.yml) | Check Markdown and workflow syntax |

The benchmark and build-release workflows check out their helper scripts from this repository. Set `pipeline-ref` to the same tag or commit used in the reusable workflow reference so the YAML and scripts stay compatible.

## Read the guides

- [Architecture](docs/ARCHITECTURE.md) explains how tasks, scripts, and provider adapters work together.
- [Workflow guide](docs/WORKFLOWS.md) shows when to use each reusable workflow.
- [Benchmarks](docs/BENCHMARKS.md) explains benchmark inputs and output files.
- [Build releases](docs/RELEASES.md) explains version validation and artifact publishing.
- [Source releases](docs/SOURCE-RELEASES.md) explains source ZIP rules and options.
- [Secrets and permissions](docs/SECRETS.md) explains how to publish safely.

## Project status

The shared task engine, benchmark runner, build-release helpers, source-release helpers, and local/GitHub/GitLab adapters have automated tests. GitHub workflows are checked by the repository CI. The GitLab configuration is an example and has not yet been verified on a GitLab-hosted runner.

See [CHANGELOG.md](CHANGELOG.md) for project changes and [LICENSE](LICENSE) for license terms.
