# Task configuration

pipeline reads a TOML file named `pipeline.toml` by default. That file tells it which commands exist and which commands must run first.

You do not need to write a separate CI script for every provider. Keep the task definitions in this file, then call them through the local, GitHub, or GitLab adapter.

## A small working example

~~~toml
schema_version = 1

[project]
name = "hello-project"
description = "A small example"

[defaults]
timeout_seconds = 60
fail_fast = true

[tasks.greet]
description = "Print a greeting"
command = ["python", "-c", "print('Hello from pipeline')"]
~~~

Save this as `pipeline.toml` and run:

~~~sh
python scripts/pipeline.py validate
python scripts/pipeline.py run greet
~~~

The command is written as a list: `python` is the program, and the remaining strings are its arguments. This is intentional. pipeline starts the program directly; it does not interpret shell operators such as `|`, `&&`, or `>`.

## Add a task

A task lives in a table whose name is its task name:

~~~toml
[tasks.test]
description = "Run the test suite"
command = ["python", "-m", "unittest", "discover", "-s", "tests"]
timeout_seconds = 180
~~~

The supported task fields are:

| Field | Required? | Meaning |
|---|---|---|
| `command` | Yes | Program and arguments as a non-empty array of strings |
| `description` | No | A short explanation shown by `list` |
| `working_directory` | No | Directory where the command runs; defaults to `.` |
| `depends_on` | No | Tasks that must succeed first |
| `env` | No | Extra environment variables for this task |
| `timeout_seconds` | No | Maximum run time for this task |

The command must not be empty. Every array item must be a non-empty string.

## Connect tasks with dependencies

Suppose a project must compile before its tests run, and the final check should run only after the tests:

~~~toml
[tasks.build]
description = "Compile the application"
command = ["make", "build"]

[tasks.test]
description = "Run the tests"
command = ["make", "test"]
depends_on = ["build"]

[tasks.check]
description = "Run the complete check"
command = ["make", "check-report"]
depends_on = ["test"]
~~~

When you run:

~~~sh
python scripts/pipeline.py run check
~~~

pipeline follows the dependencies and runs `build`, then `test`, then `check`. You can also request more than one target:

~~~sh
python scripts/pipeline.py run build test
~~~

A task is planned only once, even when more than one requested target depends on it. Dependencies are checked for missing task names and cycles before anything is run.

Tasks run sequentially. A dependency means “run this first”, not “run these two tasks at the same time”.

## Set defaults

The `[defaults]` table applies to tasks that do not specify their own timeout:

~~~toml
[defaults]
timeout_seconds = 300
fail_fast = true
~~~

- `timeout_seconds` must be a positive integer. The default is 300 seconds.
- `fail_fast` must be a boolean. It is `true` by default.

With `fail_fast = true`, pipeline stops starting unrelated tasks after a task fails. Tasks that depend on the failed task are skipped either way.

You can override fail-fast for one run:

~~~sh
python scripts/pipeline.py run check --no-fail-fast
~~~

This lets independent later tasks run after a failure. It does not allow a task to run when one of its dependencies failed.

## Choose a working directory

A task can run from a folder inside the workspace:

~~~toml
[tasks.frontend-test]
command = ["npm", "test"]
working_directory = "web"
~~~

The path is relative to the project root. Absolute paths and paths that escape the workspace are rejected. The directory must exist when the task runs.

## Pass environment variables

Use the `env` table for task-specific values:

~~~toml
[tasks.test]
command = ["python", "-m", "pytest"]
env = { APP_MODE = "test", LOG_LEVEL = "warning" }
~~~

Values must be strings. Environment variables beginning with `PIPELINE_` are reserved and cannot be set here. The provider adapter supplies those values so that a task cannot accidentally replace the run's provider or workspace information.

Do not put passwords or API tokens in `pipeline.toml`. Use the secret store provided by GitHub Actions or GitLab CI.

## What validation checks

Run:

~~~sh
python scripts/pipeline.py validate
~~~

Validation checks the TOML syntax, supported fields, command format, positive timeouts, working-directory safety, dependency names, and dependency cycles. An unknown key is an error rather than something pipeline silently ignores.

## Configuration reference

The top-level file supports:

| Section | Purpose |
|---|---|
| `schema_version` | Must be the integer `1` |
| `[project]` | Optional `name` and `description` |
| `[defaults]` | Optional `timeout_seconds` and `fail_fast` |
| `[tasks.<name>]` | One or more task definitions |

For a complete small file, see [`examples/pipeline.toml`](../examples/pipeline.toml).
