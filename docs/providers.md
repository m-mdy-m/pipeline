# Providers and reusable GitHub workflows

The task engine reads one `pipeline.toml` file. A provider adapter translates the host's environment into the portable `PIPELINE_*` contract; the core does not need to know whether a task started locally, in GitHub Actions, or in GitLab CI.

## Run locally

Install the package with `python -m pip install -e .`, then run `pipeline run check --json`. The `pipeline-local` command also adds Git-derived branch, tag, commit, and repository information when available.

## Use the adapter from GitHub Actions

When this repository is checked out as part of the calling project, use:

~~~yaml
- uses: actions/checkout@v7
- uses: actions/setup-python@v7
  with:
    python-version: "3.12"
- name: Run the shared task graph
  env:
    PYTHONPATH: src
  run: python -m pipeline.providers.github task check --json
~~~

When pipeline is checked out as a helper directory, keep the caller project as the working directory and add the helper's `src` directory to `PYTHONPATH`:

~~~yaml
- uses: actions/checkout@v7
- uses: actions/checkout@v7
  with:
    repository: m-mdy-m/pipeline
    ref: main
    path: .pipeline
    persist-credentials: false
- uses: actions/setup-python@v7
  with:
    python-version: "3.12"
- name: Run the caller project's tasks
  env:
    PYTHONPATH: .pipeline/src
  run: python -m pipeline.providers.github task check --json
~~~

For repeatable builds, replace `main` with a reviewed release tag or full commit SHA. The GitHub adapter also has a `bootstrap` mode that writes normalized context into `GITHUB_ENV` for later steps in the same job.

## Use the adapter from GitLab CI

~~~yaml
image: python:3.12

stages:
  - verify

pipeline:
  stage: verify
  script:
    - PYTHONPATH=src python -m pipeline.providers.gitlab run check --json
  artifacts:
    when: always
    paths:
      - .pipeline-artifacts/
    expire_in: 7 days
~~~

For a separate helper checkout, clone pipeline into `.pipeline` and set `PYTHONPATH=.pipeline/src` before running `python -m pipeline.providers.gitlab`.

## Shared provider context

| Variable | Meaning |
| --- | --- |
| `PIPELINE_PROVIDER` | `local`, `github`, or `gitlab` |
| `PIPELINE_EVENT` | Event that started the run, when known |
| `PIPELINE_REF_TYPE` | `branch`, `tag`, or provider ref type |
| `PIPELINE_REF_NAME` | Branch, tag, or ref name |
| `PIPELINE_SHA` | Commit checked out by the run |
| `PIPELINE_REPOSITORY` | Repository name or path, when known |
| `PIPELINE_WORKSPACE` | Project working directory |
| `PIPELINE_ARTIFACT_DIR` | Default artifact directory |
| `PIPELINE_OUTPUT_FILE` | Provider output file, when available |
| `PIPELINE_RUN_ID` | CI run or pipeline identifier |
| `PIPELINE_RUN_ATTEMPT` | Retry or attempt number |

## Reusable GitHub workflow catalog

Call a workflow from the `jobs` section of a caller's workflow. For example:

~~~yaml
jobs:
  checks:
    uses: m-mdy-m/pipeline/.github/workflows/ci.yml@main
    with:
      language: python
      build-command: python -m compileall -q src
      test-command: python -m unittest discover -s tests -v
~~~

### Run a caller's `pipeline.toml` from CI

The reusable CI workflow can execute a task from the calling repository's root
`pipeline.toml` directly. Set `pipeline-task` instead of defining separate
build and test shell commands. The workflow checks out the shared engine,
prepares Python, and invokes the GitHub provider adapter; callers do not need a
project-local wrapper script or a second copy of the task runner.

For a mixed Go and Node.js project:

~~~yaml
jobs:
  quality:
    uses: m-mdy-m/pipeline/.github/workflows/ci.yml@main
    with:
      language: go
      setup-node: true
      pnpm-version: "9.15.4"
      pipeline-task: ci
      pipeline-ref: main
~~~

The task graph remains portable: the same file can be run locally with
`pipeline run ci`, while GitHub Actions supplies the provider context through
the reusable workflow. Existing callers that use `build-command` and
`test-command` continue to work unchanged.

The available workflows are:

| Workflow | Purpose |
| --- | --- |
| `ci.yml` | Build, test, and optional lint for Go, Node.js, Rust, Python, Java, .NET, C, or custom projects. |
| `docs-check.yml` | Markdown lint and GitHub Actions syntax validation. |
| `security-check.yml` | Gitleaks scan of a selected project directory. |
| `benchmark.yml` | Repeated command timing and result artifact upload. |
| `release.yml` | Matrix build/test, checksum assembly, and GitHub Release publishing. |
| `source-release.yml` | Validated source ZIP from the exact tagged Git snapshot, with secret scanning. |
| `docker-publish.yml` | Multi-platform Docker image build and optional push. |
| `npm-publish.yml` | npm install, test, build, package check, and publish. |
| `python-publish.yml` | Python sdist/wheel build, Twine validation, and PyPI publishing. |
| `pages.yml` | Site build, Pages artifact upload, and optional deployment. |

The repository also has `reusable-smoke.yml`, a push/dispatch self-test that calls these reusable workflows with dry-run settings. It is a regular workflow for this repository, not a `workflow_call` endpoint for consumers.

### Dry-run behavior

Use `dry-run: true` for `release.yml`, `source-release.yml`, `docker-publish.yml`, `npm-publish.yml`, `python-publish.yml`, or `pages.yml` to validate a build without making the corresponding release, registry publish, Docker push, or Pages deployment. The smoke workflow calls these reusable workflows with dry-run enabled. A dry run still executes the meaningful build and validation steps and can upload temporary workflow artifacts.

### Pin helper workflows and scripts together

`benchmark.yml`, `release.yml`, and `source-release.yml` check out this repository to use the helper package from `src/`. Set their `pipeline-ref` input to a tag or commit in `m-mdy-m/pipeline`. Do not pass a commit SHA from a different caller repository: that SHA will not identify a commit in the helper repository.
