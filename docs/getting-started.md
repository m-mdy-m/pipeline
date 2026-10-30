# Getting started

This guide gets pipeline running on your computer and shows how to run a small task.

## 1. What you need

- Python 3.12 or newer. The repository's CI uses Python 3.12.
- Git, to clone the project.
- Make, only if you want to use the `make check` shortcut.

The task runner itself uses Python's standard library. You do not need to install a Python package or third-party dependency.

## 2. Get the project

Clone the repository and move into it:

~~~sh
git clone https://github.com/m-mdy-m/pipeline.git
cd pipeline
~~~

Run the configuration check:

~~~sh
python scripts/pipeline.py validate
~~~

A valid configuration prints a success message. If the file has a typo or an unknown field, pipeline reports the problem and exits with a non-zero status.

## 3. See and run the tasks

List the tasks in the repository's `pipeline.toml`:

~~~sh
python scripts/pipeline.py list
~~~

Run the full check sequence:

~~~sh
python scripts/pipeline.py run check
~~~

For this repository, `check` depends on `test`, and `test` depends on `validate`. The result is:

1. Python checks that the scripts compile.
2. Python runs the unit and provider-contract tests.
3. The final task prints that the checks completed.

The last task is deliberately simple. In your own project, you choose what each task does.

## 4. Try a small example

The file `examples/pipeline.toml` contains a tiny task configuration. Run it without replacing the repository's main configuration:

~~~sh
python scripts/pipeline.py validate --config examples/pipeline.toml
python scripts/pipeline.py run greet --config examples/pipeline.toml
~~~

The `greet` task prints a message. Open the file and change the message or add another task to see how the configuration works.

## 5. Save a machine-readable result

Use `--json` when another tool needs to read the result:

~~~sh
python scripts/pipeline.py run check --json
~~~

To also save the report to a file:

~~~sh
python scripts/pipeline.py run check \
  --json \
  --result .pipeline-artifacts/pipeline-result.json
~~~

The report includes the provider, workspace, requested tasks, each task's status, its exit code, and its duration.

## 6. Run the repository's full checks

If Make is installed, use:

~~~sh
make check
~~~

This checks the required documentation files, checks the workflow inventory, validates `pipeline.toml`, compiles the scripts, and runs the tests.

Without Make, run the main checks directly:

~~~sh
python scripts/pipeline.py validate
python -m unittest discover -s tests -p "test_*.py" -v
~~~

## Where to go next

- Read [Task configuration](configuration.md) to add tasks, dependencies, timeouts, and environment variables.
- Read [Providers](providers.md) to run the same configuration on GitHub Actions or GitLab CI.
- Read [Development guide](development.md) before changing pipeline itself.
