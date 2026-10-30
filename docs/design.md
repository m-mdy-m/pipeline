# How pipeline is put together

pipeline separates task definitions, shared execution logic, provider integration, and CI orchestration. Each part owns one kind of responsibility.

## 1. Task configuration

`pipeline.toml` describes each task, its command, dependencies, environment, working directory, and timeout. It is provider-neutral: the same task graph works from a terminal, GitHub Actions, or GitLab CI.

## 2. Installable source package

All runtime code lives in `src/pipeline/` and is installable through `pyproject.toml`.

| Package | Responsibility |
| --- | --- |
| `core/` | TOML validation, dependency planning, task execution, context, and artifact collection. |
| `providers/` | GitHub, GitLab, and local environment adapters. |
| `benchmark/` | Repeated command execution and benchmark reports. |
| `release/` | Source snapshots, release notes, archive creation, verification, and checksums. |
| `common/` | Shared logging, hashing, atomic writes, and provider-output helpers. |
| `utils/` | Small reusable helpers such as safe workspace path resolution. |

A behavior used by more than one subsystem belongs in `common/` or `utils/`, not in a provider adapter or copied helper. Subsystems can still keep domain-specific validation and workflow behavior in their own package.

## 3. Provider adapters and workflows

Adapters under `src/pipeline/providers/` translate environment details:

- `local/` reads the local environment and optional Git metadata.
- `github/` reads GitHub Actions variables and can export normalized context to `GITHUB_ENV`.
- `gitlab/` reads GitLab CI variables.

After translation, each adapter calls the same task core. It does not duplicate task scheduling or execution logic.

Workflow files under `.github/workflows/` tell GitHub when to start a job, which runner to use, and how to use GitHub features such as Actions artifacts, Releases, Docker publishing, npm/PyPI publishing, or Pages deployment. Reusable workflows declare `on: workflow_call` and can be referenced by another repository. GitLab uses `.gitlab-ci.yml` for its scheduling and artifact rules.

## What pipeline does not do

pipeline is not a hosted CI service. It does not create runners, start a GitHub or GitLab pipeline by itself, or store uploaded artifacts online.

It also does not run tasks in parallel. It plans the dependency order and runs one command at a time.

## Follow the flow

When a CI job runs a task, the sequence is:

1. The CI service starts the job.
2. The provider adapter reads the service's environment.
3. The adapter creates the common `PIPELINE_*` values.
4. The core reads `pipeline.toml` and validates the requested tasks.
5. The runner executes each task in dependency order.
6. The runner returns a report and a process exit code.
7. The CI service decides whether to upload files, display the report, or publish something.

The same flow works locally. Only the first two steps change: you start the command yourself and can use the local adapter.
