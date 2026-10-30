# pipeline documentation

pipeline helps you describe the checks and other commands for a project once, then run those commands from a terminal or a CI service.

A simple example is a project with three checks:

1. Compile the source code.
2. Run the tests.
3. Report that the checks are complete.

You write those tasks in `pipeline.toml`. pipeline reads the file, works out the required order, runs each command, and reports the result.

GitHub Actions and GitLab CI do not need their own copy of that task logic. A small provider adapter translates the CI service's environment into the common format used by pipeline.

## Start here

| I want to… | Read |
| --- | --- |
| Run pipeline for the first time | [Getting started](getting-started.md) |
| Write or change `pipeline.toml` | [Task configuration](configuration.md) |
| Use pipeline locally, on GitHub, or on GitLab | [Providers](providers.md) |
| Measure a command several times | [Benchmarks](benchmarking.md) |
| Build or publish a release | [Releases](releases.md) |
| Understand the design | [How it fits together](design.md) |
| Change pipeline or run its tests | [Development guide](development.md) |

New users can start with **Getting started**, then read **Task configuration** when they want to add their own commands.

## A few words used in these guides

- **Task**: one command that pipeline can run, such as compiling code or running tests.
- **Dependency**: another task that must finish before this task can start.
- **Workspace**: the project directory pipeline is working in.
- **Provider**: the service or environment that starts the work, such as a local terminal, GitHub Actions, or GitLab CI.
- **Adapter**: a small Python module that reads provider-specific variables and converts them into the common `PIPELINE_*` environment.
- **Artifact**: a file you want to keep after a task or CI run, such as a test report or a packaged build.

## Rules worth knowing

- A task command is an array of arguments. pipeline does not silently pass it through a shell.
- Tasks run one after another. Dependencies decide their order; pipeline does not run tasks in parallel.
- A task's working directory must stay inside the project workspace.
- `PIPELINE_*` names are reserved for information supplied by pipeline and its adapters.
- A failed task stops later independent tasks by default. Tasks that depend on a failed task are skipped.
- GitHub and GitLab are responsible for their own features, such as uploading CI artifacts or publishing a release. The shared Python package handles the work that can be shared.

The examples and commands in these guides match the package modules and workflows in this repository. When a command needs an optional tool, such as Bash for the benchmark runner, that requirement is called out where it is used.
