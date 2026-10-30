# pipeline

[![CI](https://github.com/m-mdy-m/pipeline/actions/workflows/ci-main.yml/badge.svg)](https://github.com/m-mdy-m/pipeline/actions/workflows/ci-main.yml)
[![License](https://img.shields.io/github/license/m-mdy-m/pipeline)](LICENSE)

**pipeline** is a small task runner and CI workflow collection. It gives a project one place to describe commands such as building, testing, and checking documentation, then runs those commands in the right order.

You write the tasks in `pipeline.toml`. The same task file can be used from a local terminal, GitHub Actions, or GitLab CI.

pipeline is not a hosted CI service. GitHub and GitLab still start the jobs and store the artifacts. pipeline keeps the task definitions and the shared work out of provider-specific YAML.

## Run it

You need Python 3.12 or newer.

~~~sh
git clone https://github.com/m-mdy-m/pipeline.git
cd pipeline

python scripts/pipeline.py validate
python scripts/pipeline.py list
python scripts/pipeline.py run check
~~~

To run the repository's complete local check, install Make and run:

~~~sh
make check
~~~

## Use it in your project

Create a `pipeline.toml` file in your project. A task is just a command:

~~~toml
schema_version = 1

[project]
name = "my-project"

[tasks.test]
description = "Run the test suite"
command = ["python", "-m", "unittest", "discover", "-s", "tests"]
~~~

Run it with:

~~~sh
python scripts/pipeline.py run test
~~~

Commands are lists of arguments, not shell strings. Tasks run one at a time. Use `depends_on` when one task must finish before another.

See the [configuration guide](docs/configuration.md) for the full format and [examples](examples/README.md) for files you can copy.

## Use it in CI

Use the matching provider adapter to run the same task file:

~~~sh
# Local terminal
python scripts/providers/local/adapter.py run check --json

# GitHub Actions
python scripts/providers/github/adapter.py task check --json

# GitLab CI
python scripts/providers/gitlab/adapter.py run check --json
~~~

When pipeline is kept in a separate helper checkout, call the adapter from that checkout. The adapter still reads `pipeline.toml` from the calling project's workspace.

This repository also provides reusable GitHub workflows for build/test jobs, benchmarks, build releases, source releases, Docker, npm, and GitHub Pages. See the [provider guide](docs/providers.md) and [release guide](docs/releases.md).

## Documentation

Start with the [documentation index](docs/index.md). It explains where to go next:

- [Getting started](docs/getting-started.md)
- [Task configuration](docs/configuration.md)
- [How pipeline is put together](docs/design.md)
- [Providers and reusable workflows](docs/providers.md)
- [Benchmarks](docs/benchmarking.md)
- [Releases](docs/releases.md)
- [Development](docs/development.md)

## Requirements and license

The task runner uses the Python standard library. The benchmark runner also needs Bash because it executes the measured command through Bash. Git is used by the local adapter when it is available.

pipeline is released under the license in [LICENSE](LICENSE).
