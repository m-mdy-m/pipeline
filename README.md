# pipeline

[![CI](https://github.com/m-mdy-m/pipeline/actions/workflows/ci-main.yml/badge.svg)](https://github.com/m-mdy-m/pipeline/actions/workflows/ci-main.yml)
[![License](https://img.shields.io/github/license/m-mdy-m/pipeline)](LICENSE)

**pipeline** is a small task runner and reusable CI workflow toolkit. Define build, test, and release tasks once in `pipeline.toml`, then run the same task graph locally, in GitHub Actions, or in GitLab CI.

**Source of truth:** the authoritative implementation lives in `src/pipeline/`. Task validation and execution, release preparation, release-target execution, benchmarks, packaging checks, and shared utilities belong to this installable package. GitHub Actions, GitLab CI, and local execution are providers around that implementation; they must not duplicate its behavior.

GitHub and GitLab schedule jobs and provide CI-specific services such as runners, credentials, caches, artifact transfer, and publishing. Their workflow files are provider configuration, not a second implementation of pipeline.

## Install

Python 3.11 or newer is required. Install the package in editable mode:

~~~sh
git clone https://github.com/m-mdy-m/pipeline.git
cd pipeline
python -m pip install -e .
~~~

Inspect supported native and cross-platform release target descriptors with `pipeline-build-targets list`.

Run the task runner:

~~~sh
pipeline validate
pipeline list
pipeline run check
~~~

The source checkout can also be used without installing the package:

~~~sh
PYTHONPATH=src python -m pipeline validate
PYTHONPATH=src python -m pipeline run check
~~~

To run the repository's full local checks, install Make and run `make check`.

## Use it in your project

Create a `pipeline.toml` file in your repository. A task is a command represented as an argument array:

~~~toml
schema_version = 1

[project]
name = "my-project"

[tasks.test]
description = "Run the test suite"
command = ["python", "-m", "unittest", "discover", "-s", "tests"]
~~~

Run it with `pipeline run test`. Commands are not implicitly passed through a shell. Use `depends_on` to make one task wait for another. See the [configuration guide](docs/configuration.md) for all supported fields.

## Use it in CI

The same task configuration can run through a provider adapter:

~~~sh
pipeline-local run check --json
pipeline-github task check --json
pipeline-gitlab run check --json
~~~

### Call a reusable GitHub workflow

The workflow files can be called directly from another repository. For example, this invokes the reusable CI workflow in this repository:

~~~yaml
name: Project CI

on:
  pull_request:
  push:
    branches: [main]

permissions:
  contents: read

jobs:
  quality:
    uses: m-mdy-m/pipeline/.github/workflows/ci.yml@main
    with:
      language: python
      python-version: "3.12"
      build-command: python -m compileall -q src
      test-command: python -m unittest discover -s tests -p "test_*.py" -v
~~~

The referenced file must declare `on: workflow_call`, and the call must appear at the job level. `@main` is convenient while evaluating changes. For production projects, pin a reviewed release tag or full commit SHA so the workflow does not change unexpectedly.

Reusable workflows are also available for documentation checks, benchmarks, compiled releases, source releases, Docker, npm, Python packages, security scans, and GitHub Pages. Publishing/deployment workflows expose `dry-run` inputs where a non-publishing test is useful. See [Providers and reusable workflows](docs/providers.md) and [Releases](docs/releases.md).

## Documentation

Start with the [documentation index](docs/index.md), then read [Getting started](docs/getting-started.md), [Task configuration](docs/configuration.md), [Design](docs/design.md), [Providers](docs/providers.md), [Benchmarks](docs/benchmarking.md), [Releases](docs/releases.md), and [Development](docs/development.md).

## Requirements and license

The task runner uses the Python standard library. Benchmark commands are executed through Bash. Git is used by the local provider to detect repository metadata when available. Source-release security scanning uses Docker and Gitleaks in the GitHub workflow.

pipeline is licensed under the Mozilla Public License 2.0 ([MPL-2.0](https://www.mozilla.org/MPL/2.0/)). When distributing modified Pipeline-covered source files, those files and their modifications must be made available under MPL-2.0; separate files in a larger work may use other licenses. See [LICENSE](LICENSE) for the full terms.
