# Provider adapters and reusable workflows

The authoritative implementation is the installable `src/pipeline/` package. It reads one `pipeline.toml` file and owns task planning, execution, shared release/benchmark behavior, and validation. A provider adapter only translates host environment into the portable `PIPELINE_*` contract and invokes that package; it does not implement the task or release logic. GitHub Actions and GitLab CI supply scheduling, runner setup, credentials, artifact transport, and provider publishing APIs.

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

## Provider-owned workflow sources

The provider adapter implementation lives under `src/pipeline/providers/`.
Workflow files follow each CI host's discovery rules:

- **GitHub Actions:** reusable workflows are kept in the repository's
  `.github/workflows/` directory. GitHub requires reusable workflow files to
  live there, so `ci.yml`, `release.yml`, and the other GitHub workflow
  entry points are maintained in that directory in this repository. Callers
  reference those canonical files directly; do not copy their logic into an
  application repository.
- **GitLab CI:** the reusable template is maintained at
  `src/pipeline/providers/gitlab/workflows/ci.yml`. The root
  `.gitlab-ci.yml` is only a thin local include so this repository tests the
  same source that downstream projects consume.

### Use the shared CI workflow from GitLab

For this repository, `.gitlab-ci.yml` includes the provider template from the
current checkout:

~~~yaml
include:
  - local: /src/pipeline/providers/gitlab/workflows/ci.yml
~~~

For another GitLab project, include the canonical template from the shared
repository instead of copying it:

~~~yaml
include:
  - remote: https://raw.githubusercontent.com/m-mdy-m/pipeline/main/src/pipeline/providers/gitlab/workflows/ci.yml
~~~

To run a language preset instead of `pipeline.toml`, set `PIPELINE_CI_LANGUAGE`, `PIPELINE_CI_IMAGE` and optionally `PIPELINE_CI_ROOT` / `PIPELINE_CI_ARGS`; see [Language toolchains](toolchains.md#gitlab-ci). The hidden job `.pipeline:toolchain` can be reused with `parallel: matrix`.

The template uses the local `src/pipeline` checkout when the current project
is the pipeline repository. For downstream projects it checks out the shared
helper repository at `PIPELINE_HELPER_REF` (default: `main`), then runs the
calling project's root `pipeline.toml` through
`python -m pipeline.providers.gitlab run check --json`. Set
`PIPELINE_HELPER_REF` to a reviewed tag or full commit SHA for reproducible
builds.

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

Release matrix entries may declare an optional `java_version` string.
The reusable release workflow provisions Eclipse Temurin through
`actions/setup-java` only for entries that request it; Android/Gradle targets
commonly use `java_version: "21"`. Targets without that field do not install
Java.

| Workflow | Purpose |
| --- | --- |
| `ci.yml` | Build, test, and optional lint for Go, Node.js, Rust, Python, Java, .NET, C, Docker, or custom projects. Runs your commands, a `pipeline.toml` task, or the engine's language preset (`toolchain-preset: true`). |
| `ci-main.yml` | This repository's push gate: runs on every push to every branch, every pull request and the merge queue, and ends in one `gate` job suitable as the single required check. |
| `toolchain-smoke.yml` | Runs every composite action and the reusable `ci.yml` presets against the fixture projects in `examples/toolchains/`, plus a negative control that must fail. |
| `docs-check.yml` | Markdown lint and GitHub Actions syntax validation. |
| `security-check.yml` | Gitleaks scan of a selected project directory. |
| `dependency-review.yml` | Review dependency changes in pull requests and block high-severity vulnerable updates. |
| `codeql.yml` | Scheduled and change-triggered CodeQL analysis of the Python source tree. |
| `zizmor.yml` | Static security analysis of GitHub Actions workflows and local composite actions. |
| `yamllint.yml` | YAML syntax/style checks across GitHub and GitLab provider files and the examples. |
| `typos.yml` | Spelling checks for source, documentation, and workflow files. |
| `python-compatibility.yml` | Compiles source and runs the complete unit suite on Python 3.11, 3.12, and 3.13 (plus non-blocking macOS and Windows runs) through the `python-quality` composite action. |
| `pr-title.yml` | Validates pull request titles against Conventional Commits. |
| `scorecard.yml` | Runs scheduled OSSF Scorecard analysis and stores its SARIF report as a workflow artifact. |
| `benchmark.yml` | Repeated command timing and result artifact upload. |
| `benchmark-regression.yml` | Runs `pipeline bench --against <base>` on pull requests; writes a Markdown table to the job summary. Report-only unless `fail-on-regression` is set. |
| `release.yml` | Matrix build/test, checksum assembly, and GitHub Release publishing. |
| `source-release.yml` | Validated source ZIP from the exact tagged Git snapshot, with secret scanning. |
| `docker-publish.yml` | Multi-platform Docker image build and optional push. |
| `oci-publish.yml` | Target-matrix package build, metadata/hash verification, ORAS push to GHCR, immutable digest receipt, and registry round-trip verification. |
| `npm-publish.yml` | npm install, test, build, package check, and publish. |
| `python-publish.yml` | Python sdist/wheel build, Twine validation, and PyPI publishing. |
| `pages.yml` | Site build, Pages artifact upload, and optional deployment. |

The repository also has `reusable-smoke.yml`, a pull-request/push/dispatch self-test that calls these reusable workflows with dry-run settings.

### Repository-level quality workflows

The `dependency-review.yml` workflow uses GitHub's Dependency Review API.
Enable the repository Dependency graph under Settings → Security → Code security
and analysis, then set the Actions variable
`PIPELINE_DEPENDENCY_REVIEW_ENABLED=true`. Until enabled, its optional job is
skipped so repositories without the feature do not receive a false CI failure.

The `zizmor.yml` workflow scans the new workflow entry points and local
`python-quality` action. Root `zizmor.yml` explicitly accepts version-tag refs
(`ref-pin`) rather than enforcing commit-SHA pins. Dependabot keeps GitHub Action
tags and Python package metadata updated through weekly pull requests.

The Python matrix runs the same unit suite on each supported interpreter.
The `python-quality` composite action is shared by the matrix workflow so its
setup and test steps are exercised by CI rather than existing as unused YAML.

The dependency-review, CodeQL, zizmor, yamllint, and typos workflows are repository automation rather than reusable `workflow_call` endpoints. Dependency review and CodeQL use GitHub security services; zizmor audits GitHub-specific workflow/action configuration; yamllint deliberately covers both `.github/` and the canonical GitLab YAML entry points. They do not move task execution or release rules out of `src/pipeline/`. GitLab consumers can keep invoking the same provider-neutral Python commands from their own CI jobs. It is a regular workflow for this repository, not a `workflow_call` endpoint for consumers.

### Language presets in the reusable workflow

Set `toolchain-preset: true` to let the engine run install, lint, build and test for the language instead of passing commands. The workflow only provisions the runtime and then calls `python -m pipeline.providers.github ci`:

~~~yaml
jobs:
  api:
    uses: m-mdy-m/pipeline/.github/workflows/ci.yml@main
    with:
      language: go
      toolchain-preset: true
      working-directory: api
      skip-stages: lint
~~~

`toolchain-preset` cannot be combined with `pipeline-task`. Commands passed as `build-command`, `test-command` and `lint-command` are only used when neither `toolchain-preset` nor `pipeline-task` is set (the legacy mode); they run as `bash -e -o pipefail -c "$COMMAND"` through environment variables (never interpolated into the script). For per-stage overrides use the composite actions below, which accept `install-command`, `lint-command`, `build-command` and `test-command`.

The workflow always checks out `m-mdy-m/pipeline` at `pipeline-ref` into `.pipeline/` because dependency installation for Node.js and Python (`requirements.txt`) now goes through the engine too.

### Composite actions

Composite actions live in `.github/actions/` and can be used from another repository as `m-mdy-m/pipeline/.github/actions/<name>@<ref>`. They install a runtime, then call the same engine; they contain no build or test commands. The complete input/output list and examples are in [Language toolchains](toolchains.md#github-actions).

| Action | Purpose |
| --- | --- |
| `toolchain-quality` | Any language, including auto-detection |
| `node-quality`, `go-quality`, `rust-quality`, `java-quality`, `dotnet-quality` | Language-specific runtime setup plus the engine's stages |
| `python-quality` | Python setup, byte-compile and the unit suite |
| `run-pipeline` | Run named tasks from `pipeline.toml` and upload the JSON report |
| `python-setup`, `release-assets` | Helpers used by release workflows |

When the GitHub adapter runs `ci`, `run` or `task`, it also writes a Markdown table to the job summary and `::error` annotations for failed tasks. These GitHub-only presentation features live in `src/pipeline/providers/github/adapter.py`; the core produces the report.

### What runs on every push

`ci-main.yml` runs unit tests (Python 3.11–3.13), workflow and action contract tests, repository checks, the reusable-workflow smoke test for `pipeline.toml`, YAML lint, spelling, documentation lint, and the language toolchain smoke tests. The `gate` job fails unless all of them succeed. Path-filtered workflows (`reusable-smoke.yml`, `zizmor.yml`) additionally run on every branch when workflow, action or source files change.

### Dry-run behavior

Use `dry-run: true` for `release.yml`, `source-release.yml`, `docker-publish.yml`, `npm-publish.yml`, `python-publish.yml`, or `pages.yml` to validate a build without making the corresponding release, registry publish, Docker push, or Pages deployment. The smoke workflow calls these reusable workflows with dry-run enabled. A dry run still executes the meaningful build and validation steps and can upload temporary workflow artifacts.

### Pin helper workflows and scripts together

`benchmark.yml`, `release.yml`, and `source-release.yml` check out this repository to use the helper package from `src/`. Set their `pipeline-ref` input to a tag or commit in `m-mdy-m/pipeline`. Do not pass a commit SHA from a different caller repository: that SHA will not identify a commit in the helper repository.

## Toolchain action inputs added for benchmarks and extra runtimes

`toolchain-quality` accepts `mode: bench` together with `bench-against`, `bench-baseline`, `bench-update-baseline`, `bench-command`, `bench-parser`, `bench-count`, `bench-threshold` and `bench-report-only`; it exposes a `regressions` output. It also installs Bun (`bun-version`) and Vim (`vim-version`) when the detected toolchain needs them, and caches package-manager downloads (`cache`). These inputs only install runtimes or pass flags; the behaviour is in `src/pipeline`.
