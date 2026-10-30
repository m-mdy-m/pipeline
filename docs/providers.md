# Run pipeline in different places

The same task file can be used from a terminal, GitHub Actions, or GitLab CI. The task runner does not need to know which service started it.

A provider adapter handles the difference. It reads the provider's environment variables, translates them into the common `PIPELINE_*` names, and starts the regular pipeline command.

## Run it on your computer

Use the normal entry point:

~~~sh
python scripts/pipeline.py run check --json
~~~

Or use the local adapter:

~~~sh
python scripts/providers/local/adapter.py run check --json
~~~

The local adapter uses Git to fill in the current commit, branch or exact tag, and repository name when that information is available. If the directory is not a Git checkout, it still runs with a local workspace.

## Run it in GitHub Actions

When the adapter is part of your checkout, the task command is:

~~~yaml
- uses: actions/checkout@v7
- uses: actions/setup-python@v7
  with:
    python-version: "3.12"
- name: Run the task graph
  run: python scripts/providers/github/adapter.py task check --json
~~~

To use pipeline from another project, check out this repository as a helper directory. The task configuration is still read from the calling project's workspace:

~~~yaml
name: Project checks

on:
  pull_request:
  push:
    branches: [main]

permissions:
  contents: read

jobs:
  check:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v7
      - uses: actions/checkout@v7
        with:
          repository: m-mdy-m/pipeline
          ref: v1.0.0
          path: .pipeline
          persist-credentials: false
      - uses: actions/setup-python@v7
        with:
          python-version: "3.12"
      - name: Run the caller project's tasks
        run: python .pipeline/scripts/providers/github/adapter.py task check --json
~~~

Replace `check` with the task you want to run. The helper checkout is pinned to `v1.0.0` in this example; use a reviewed tag or commit in your own workflow.

The GitHub adapter also has a `bootstrap` command. It writes the normalized context to `GITHUB_ENV` so later steps in the same job can read `PIPELINE_*` values. Use `task` or `run` when you only need to execute pipeline immediately.

## Run it in GitLab CI

If pipeline is checked out inside the project, use:

~~~yaml
image: python:3.12

stages:
  - test

pipeline:
  stage: test
  script:
    - python scripts/providers/gitlab/adapter.py run check --json
~~~

If you keep pipeline in a separate helper directory, clone it before running the adapter:

~~~yaml
before_script:
  - git clone --depth 1 --branch v1.0.0 https://github.com/m-mdy-m/pipeline.git .pipeline

check:
  image: python:3.12
  script:
    - python .pipeline/scripts/providers/gitlab/adapter.py run check --json
  artifacts:
    when: always
    paths:
      - .pipeline-artifacts/
    expire_in: 7 days
~~~

The GitLab adapter reads values such as `CI_COMMIT_SHA`, `CI_COMMIT_TAG`, and `CI_PROJECT_PATH`. It does not use GitHub variables.

## The shared environment

The adapters translate provider variables into a small set of common values:

| Common value | What it describes |
| --- | --- |
| `PIPELINE_PROVIDER` | `local`, `github`, or `gitlab` |
| `PIPELINE_EVENT` | Event that started the run, when known |
| `PIPELINE_REF_TYPE` | `branch`, `tag`, or another provider ref type |
| `PIPELINE_REF_NAME` | Name of the branch, tag, or ref |
| `PIPELINE_SHA` | Commit checked out by the run |
| `PIPELINE_REPOSITORY` | Repository name or path, when known |
| `PIPELINE_WORKSPACE` | Project directory |
| `PIPELINE_ARTIFACT_DIR` | Default directory for pipeline artifacts |
| `PIPELINE_OUTPUT_FILE` | Provider output file, when available |
| `PIPELINE_RUN_ID` | CI run or pipeline ID, when available |
| `PIPELINE_RUN_ATTEMPT` | Retry or attempt number, when available |

The core reads these common values. It does not read `GITHUB_*` or `CI_*` variables directly.

## Reusable GitHub workflows

This repository also publishes ready-made GitHub Actions workflows. These are useful when a project wants a standard GitHub job without writing the setup steps itself.

| Workflow | What it does |
| --- | --- |
| `ci.yml` | Prepares a Go, Node.js, Rust, Python, C, or custom environment, then runs the build, test, and optional lint commands supplied by the caller. |
| `benchmark.yml` | Checks out the shared benchmark script, runs it, and uploads the result directory. |
| `release.yml` | Builds for one or more targets, creates checksums, and publishes a GitHub Release. |
| `source-release.yml` | Packages and checks the exact source snapshot from a tag. |
| `docker-publish.yml` | Builds and publishes a multi-architecture Docker image. |
| `npm-publish.yml` | Tests and publishes an npm package. |
| `pages.yml` | Builds and deploys a GitHub Pages site. |
| `docs-check.yml` | Checks Markdown and GitHub Actions workflow syntax. |

These reusable workflows are GitHub-specific by design. For example, GitHub owns the artifact upload and Release publishing steps. The scripts that measure commands or prepare release metadata remain separate and provider-neutral.

See [Releases](releases.md) for examples and the inputs each release workflow needs.
