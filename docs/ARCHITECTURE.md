# How pipeline is built

This page explains the main parts of pipeline in plain language.

## The big picture

pipeline separates **what should run** from **where it runs**.

- The task list describes the work.
- The core runs that work.
- An adapter connects the core to a particular environment.
- A CI workflow handles platform features such as uploading files or publishing a release.

That means the same task list can be used on a developer's computer, in GitHub Actions, or in GitLab CI.

## The main files

### 1. `pipeline.toml` — the task list

This is where tasks are named and connected. A task can run a command, and it can depend on another task. For example, tests can depend on validation, so invalid configuration is caught first.

### 2. `scripts/pipeline.py` — the command you run

This is the simple entry point for everyday use:

```sh
python scripts/pipeline.py validate
python scripts/pipeline.py list
python scripts/pipeline.py run check
```

### 3. `scripts/pipeline_core/` — the engine

The core checks the task list, figures out the correct order, runs commands, handles failures and timeouts, and writes result reports. It uses a shared set of environment names beginning with `PIPELINE_`; it does not read GitHub- or GitLab-specific variables directly.

### 4. `scripts/providers/` — adapters

An adapter converts the environment's information into the shared format.

- `local/` works on your computer.
- `github/` translates GitHub Actions information and handles GitHub-only setup when needed.
- `gitlab/` translates GitLab CI information.

### 5. `.github/workflows/` and `.gitlab-ci.yml` — automation entry points

These files tell a CI service when to run something. GitHub workflow files also use GitHub-specific features for artifacts, releases, Docker Hub, npm, and Pages. Those features belong in the provider layer; they are not part of the shared task engine.

## What happens when a task runs?

1. pipeline reads `pipeline.toml`.
2. It checks that task names, commands, and dependencies are valid.
3. It works out which tasks must run first.
4. It runs each command and records its result.
5. If a task fails, tasks that depend on it are skipped.
6. It can save a JSON report and collect files as artifacts.

Commands are written as lists of arguments, not as shell strings. This helps pipeline run commands predictably.

## Try the same task through different adapters

```sh
python scripts/pipeline.py run check --json
python scripts/providers/local/adapter.py run check --json
python scripts/providers/github/adapter.py task check --json
python scripts/providers/gitlab/adapter.py run check --json
```

The adapter examples share the same task graph. The GitHub and GitLab adapters can be tested with simulated environment variables, but that does not prove that every hosted CI feature has been tested on those services.

## Tests

The test suite checks task ordering, invalid configurations, timeouts, failures, artifact checksums, and adapter behavior. It also runs one task graph through all three adapters to check that they follow the same core contract.
