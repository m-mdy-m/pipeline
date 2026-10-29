# Architecture

## Core and provider boundary

The task graph is stored in `pipeline.toml`. `scripts/pipeline_core/` owns schema validation, dependency planning, safe command execution, structured results and local artifact collection. It reads only the canonical `PIPELINE_*` context and does not import provider implementations.

Provider adapters live in `scripts/providers/`:

- `local/adapter.py` infers local Git ref, SHA and origin metadata when available.
- `github/adapter.py` maps GitHub Actions event/ref/output information and configures GitHub-only submodule credentials.
- `gitlab/adapter.py` maps GitLab CI variables and invokes the same core CLI.

The `.github/workflows/` files are provider wrappers: they run the engine, upload artifacts, or publish to GitHub. `.gitlab-ci.yml` provides a second-provider integration example. The same `pipeline.toml` tasks can run locally, through GitHub Actions, or through GitLab CI.

## Contracts and safety

- Commands are arrays of arguments; shell execution is never implicit.
- Unknown task names, dependencies, cycles, workspace escapes and invalid timeouts fail validation before tasks run.
- Dependencies run in topological order. Failed dependencies skip dependants; fail-fast is the default.
- Run reports use versioned JSON; logs go to stderr.
- The local artifact store copies regular files atomically, computes SHA-256 and writes `artifacts.json`.
- Provider adapters translate runner variables and output-file locations; business logic never reads `GITHUB_*` or `CI_*`.

Run locally:

~~~sh
python scripts/pipeline.py validate
python scripts/pipeline.py list --json
python scripts/pipeline.py run check --json --result .pipeline-artifacts/pipeline-result.json
python scripts/providers/local/adapter.py run check --json
python scripts/providers/github/adapter.py task check --json
python scripts/providers/gitlab/adapter.py run check --json
~~~

Tests in `tests/test_pipeline_core.py` cover context isolation, provider mappings, graph validation, execution order, failure/timeout semantics, CLI end-to-end execution and artifact integrity.

## Provider adapter end-to-end acceptance

The unit suite runs the same generated task graph through executable Local, GitHub and GitLab adapters. It verifies that each runs dependency tasks in order, propagates the portable workspace/provider context, emits the same versioned JSON report contract and records the correct provider. Repository CI also executes the committed `pipeline.toml` task graph through the GitHub adapter rather than invoking task logic directly.
