# Getting started

This guide shows the quickest way to install pipeline and run its task graph.

## Requirements

Use Python 3.11 or newer. Git is needed to clone the repository; Make is optional and is only used for the `make check` shortcut.

## Install

~~~sh
git clone https://github.com/m-mdy-m/pipeline.git
cd pipeline
python -m pip install -e .
~~~

The editable install exposes `pipeline`, `pipeline-local`, `pipeline-github`, and `pipeline-gitlab` commands.

## Validate and run tasks

~~~sh
pipeline validate
pipeline list
pipeline run check
~~~

For this repository, `check` depends on `test`, while `test` depends on `validate`. The validation task compiles the source package, and the test task runs the unit and integration tests.

You can use the source tree without installing it by setting `PYTHONPATH=src`:

~~~sh
PYTHONPATH=src python -m pipeline validate
PYTHONPATH=src python -m pipeline run check
~~~

## Try the example configuration

The file `examples/pipeline.toml` contains a small dependency graph:

~~~sh
pipeline validate --config examples/pipeline.toml
pipeline run finish --config examples/pipeline.toml
~~~

The `finish` task depends on `greet`, so pipeline runs them in order.

## Save a machine-readable report

~~~sh
pipeline run check --json --result .pipeline-artifacts/pipeline-result.json
~~~

The report records the provider, workspace, requested tasks, each task's status, exit code, and duration.

## Run repository checks

~~~sh
make check
~~~

This verifies the required documentation and workflow inventory, validates the task configuration, compiles the source package, and runs the test suite.

## Next steps

Read [Task configuration](configuration.md) to add tasks and dependencies, [Providers](providers.md) to use GitHub Actions or GitLab CI, and [Development](development.md) before changing pipeline itself.
