# Development guide

This guide explains the local test loop, where behavior belongs, and what to check before contributing.

## Before you change code

Use Python 3.11 or newer, Git, and Make. From the repository root, run:

~~~sh
make check
~~~

Without Make:

~~~sh
PYTHONPATH=src python -m pipeline validate
PYTHONPATH=src python -m unittest discover -s tests -p "test_*.py" -v
~~~

The test suite covers configuration, task execution, all provider adapters, shared helpers, benchmarks, release preparation, source packaging, and bundle verification.

## Where to put a change

| Change | Put it here |
| --- | --- |
| Task configuration or execution | `src/pipeline/core/` |
| Shared cross-cutting helpers | `src/pipeline/common/` |
| Safe reusable utilities | `src/pipeline/utils/` |
| Provider environment translation | `src/pipeline/providers/` |
| Benchmark behavior | `src/pipeline/benchmark/` |
| Build and source release behavior | `src/pipeline/release/` |
| GitHub CI/CD integration (scheduling, runner setup, artifact transport, publish APIs) | `.github/workflows/` |
| GitLab job orchestration | `.gitlab-ci.yml` |
| User-facing explanations and examples | `docs/` and `examples/` |

The source-first rule is mandatory: implement shared behavior in `src/pipeline/` first, add tests for it, and then make each provider call that implementation. Provider adapters may translate CI variables into `PIPELINE_*` values; provider workflows may schedule jobs, install runner toolchains, handle credentials, transfer artifacts, and call the provider's publishing APIs. Do not put task, release, packaging, or verification logic directly into GitHub/GitLab workflow YAML or duplicate it between providers.

## Run focused tests

~~~sh
PYTHONPATH=src python -m unittest discover -s tests -p "test_pipeline_core.py" -v
PYTHONPATH=src python -m unittest discover -s tests -p "test_benchmark.py" -v
PYTHONPATH=src python -m unittest discover -s tests -p "test_build_release.py" -v
~~~

Run the complete test suite before committing:

~~~sh
PYTHONPATH=src python -m unittest discover -s tests -p "test_*.py" -v
~~~

Compile the source package:

~~~sh
python -m compileall -q src
~~~

## Keep the examples honest

When a command, input, or workflow changes, update the matching guide and example in the same change. Prefer examples that can be copied and run. Do not claim that a provider, operating system, or release path was tested unless a run actually checked it.

## Documentation and workflow checks

`make check` verifies required documents and workflow inventory, validates `pipeline.toml`, compiles the source package, and runs the test suite. The reusable docs workflow also runs Markdown linting and `actionlint` against the Actions files.

## Before a release

1. Update `CHANGELOG.md` with the exact version and date.
2. Check that the release helper accepts the version and finds the matching changelog section.
3. Run `make check`.
4. Run the release dry-run workflow.
5. Create and push the version tag only after the intended commit is ready.

See [Releases](releases.md) for the tag format and workflow inputs.
