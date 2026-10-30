# How pipeline is put together

pipeline has one main idea: describe the work once, then let the place that runs it provide its own environment.

There are three parts.

## 1. The task file

`pipeline.toml` is the list of work. It names each task, the command to run, and any tasks that must finish first.

For example, the test task can depend on the build task. You ask pipeline to run `test`; it knows that `build` must run first.

## 2. The shared scripts

The scripts under `scripts/` do the work that should behave the same in every environment:

- `scripts/pipeline_core/` reads the task file, checks it, plans the task order, runs commands, handles timeouts, and writes reports.
- `scripts/benchmark.py` repeats a command and records how long it takes.
- `scripts/pipeline_release/` prepares release information and source-release archives.
- `scripts/build_release.py` prepares build-release notes and checksum files.

These scripts use the Python standard library. The core reads the common `PIPELINE_*` environment values; it does not read GitHub or GitLab variables directly.

## 3. Provider adapters and workflows

The adapters under `scripts/providers/` translate environment details:

- `local/` reads the local environment and optional Git metadata.
- `github/` reads GitHub Actions variables.
- `gitlab/` reads GitLab CI variables.

After translation, each adapter calls the same core command.

Workflow files are different. A file under `.github/workflows/` tells GitHub when to start a job, which runner to use, and how to use GitHub features such as Actions artifacts and Releases. The GitLab configuration does the same for GitLab CI.

This split is useful because uploading an Actions artifact is a GitHub operation, while deciding that tests must run after a build is a task-configuration rule. They belong in different places.

## What pipeline does not do

pipeline is not a hosted CI service. It does not create runners, start a GitHub or GitLab pipeline by itself, or store uploaded artifacts online.

It also does not run tasks in parallel. It plans the dependency order and runs one command at a time.

## Follow the flow

When a CI job runs a task, the sequence is:

1. The CI service starts the job.
2. The provider adapter reads the service's environment.
3. The adapter creates the common `PIPELINE_*` values.
4. The task runner reads `pipeline.toml` and validates the requested tasks.
5. The runner executes each task in dependency order.
6. The runner returns a report and a process exit code.
7. The CI service decides whether to upload files, display the report, or publish something.

The same flow works locally. Only the first two steps change: you start the command yourself and can use the local adapter instead of a CI adapter.
