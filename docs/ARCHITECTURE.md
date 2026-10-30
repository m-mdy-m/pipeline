# How pipeline works

pipeline separates **the work to do** from **the service that runs it**. This lets the same task configuration work on a developer's computer, in GitHub Actions, or in GitLab CI.

## The three layers

### 1. Describe the work

`pipeline.toml` is the task list. Each task has a name, a command, and optionally a list of tasks that must finish first.

For example, the `test` task depends on `validate`. When you run `check`, pipeline follows those dependencies and runs the required tasks in order.

### 2. Run the shared scripts

`scripts/pipeline_core/` is the task engine. It reads the configuration, checks task definitions, plans the order, runs commands, applies timeouts, records failures, and writes result reports.

Other shared tools live beside the core:

- `scripts/benchmark.py` runs a command repeatedly and writes timing reports.
- `scripts/pipeline_release/` prepares and validates release data, including source archives and build-release metadata.
- `scripts/build_release.py` is the command-line entry point for build-release preparation and checksum generation.

These scripts use Python's standard library and the common `PIPELINE_*` context. They do not read provider-specific variables directly.

### 3. Connect a provider

`scripts/providers/` contains small adapters:

- `local/` reads the local environment and, when possible, Git metadata.
- `github/` translates GitHub Actions variables and can export provider context for later steps.
- `gitlab/` translates GitLab CI variables.

An adapter normalizes the environment, then calls the same task engine. It does not implement another copy of the task graph.

## What belongs in a workflow?

Files under `.github/workflows/` are GitHub integration. They decide when jobs run, prepare a runner, call shared scripts, and use GitHub-only features such as Actions artifacts, GitHub Releases, Docker Hub credentials, npm publishing, or Pages deployment.

The GitLab entry point is `.gitlab-ci.yml`. It calls the GitLab adapter, which runs the same configured task graph.

Keep the boundary simple:

- Put reusable task behavior and data processing in `scripts/`.
- Put environment translation in `scripts/providers/`.
- Keep scheduling, runner setup, artifact transport, and service publishing in the provider's workflow or CI configuration.

Some reusable GitHub workflows intentionally accept ordinary build and test commands. They are convenience wrappers for repositories that do not use `pipeline.toml`; they do not change the provider-neutral core.

## Run the same task through each adapter

~~~sh
python scripts/pipeline.py run check --json
python scripts/providers/local/adapter.py run check --json
python scripts/providers/github/adapter.py task check --json
python scripts/providers/gitlab/adapter.py run check --json
~~~

The first command runs directly. The other commands first normalize the provider environment. All four use the same task configuration and task runner.

## How failures are reported

A task that fails returns a non-zero exit code. Tasks that depend on a failed task are skipped. The run report records each task's status, duration, exit code, and error message. Use `--result` to save the report as JSON.

The automated tests cover task ordering, invalid configuration, timeouts, failure handling, artifact checksums, benchmark output, release metadata, and provider adapter behavior.
