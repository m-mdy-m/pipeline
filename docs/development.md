# Development guide

This guide is for someone changing pipeline itself. It explains the local test loop, where behavior belongs, and what to check before opening a pull request.

## Before you change code

Use Python 3.12, Git, and Make. From the repository root, run the current checks:

~~~sh
make check
~~~

If Make is not available:

~~~sh
python scripts/pipeline.py validate
python -m unittest discover -s tests -p "test_*.py" -v
~~~

The test suite includes configuration and task-runner tests, local/GitHub/GitLab adapter tests, benchmark tests, source-release tests, and build-release tests.

## Where to put a change

| Change | Put it here |
|---|---|
| Task configuration or task execution | `scripts/pipeline_core/` |
| Shared benchmark behavior | `scripts/benchmark.py` |
| Shared build-release behavior | `scripts/pipeline_release/build.py` |
| Source-release behavior | `scripts/pipeline_release/` |
| GitHub environment translation | `scripts/providers/github/` |
| GitLab environment translation | `scripts/providers/gitlab/` |
| Local environment translation | `scripts/providers/local/` |
| GitHub scheduling, artifact upload, or publishing | `.github/workflows/` |
| GitLab job scheduling | `.gitlab-ci.yml` |
| User-facing explanation or example | `docs/` or `examples/` |

A useful rule is: if the behavior should be the same on a local machine, GitHub, and GitLab, it probably belongs in a shared script. If it uses a feature owned by one CI service, it belongs in that provider's workflow or configuration.

## Run focused tests

Run one test file while working on a small change:

~~~sh
python -m unittest tests.test_pipeline_core -v
python -m unittest tests.test_benchmark -v
python -m unittest tests.test_build_release -v
~~~

Run the complete suite before committing:

~~~sh
python -m unittest discover -s tests -p "test_*.py" -v
~~~

Compile the scripts separately when changing Python code:

~~~sh
python -m compileall -q scripts
~~~

## Keep the examples honest

When a command, input, or workflow changes, update the matching guide and example in the same change. Prefer examples that can be copied and run. Do not claim that a provider, operating system, or release path was tested unless a run actually checked it.

## Documentation and workflow checks

`make check` verifies the required documentation files and workflow inventory, validates `pipeline.toml`, compiles the scripts, and runs the test suite.

The GitHub documentation workflow additionally runs Markdown linting and `actionlint` against the Actions files. These are separate checks: a valid task configuration does not prove that a GitHub workflow is valid YAML or has valid expressions.

## Before a release

1. Update `CHANGELOG.md` with the exact version and date.
2. Check that the release helper accepts the version and finds its changelog section.
3. Run `make check`.
4. Review the build or source-release dry-run.
5. Create and push the version tag only after the intended commit is ready.

See [Releases](releases.md) for the tag format and release workflow.
