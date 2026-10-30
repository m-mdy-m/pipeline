# Contributing

Thanks for taking an interest in pipeline.

## Before you start

Use Python 3.11 or newer, Git, and Make. The repository CI currently runs Python 3.12. Create a focused branch from the current default branch before changing code.

## Where changes belong

- Put task planning and execution in `src/pipeline/core/`.
- Put behavior shared by multiple subsystems in `src/pipeline/common/` or `src/pipeline/utils/`.
- Put provider environment handling in `src/pipeline/providers/`.
- Keep benchmark and release domain logic in `src/pipeline/benchmark/` and `src/pipeline/release/`.
- Keep GitHub scheduling, artifact transfer, and publishing in `.github/workflows/`.
- Keep task definitions in `pipeline.toml` and GitLab scheduling in `.gitlab-ci.yml`.
- Update the matching guide and example when a command, input, or workflow changes.

Do not add new runtime entry points under a top-level `scripts/` directory. Use a module entry point or a console command declared in `pyproject.toml`.

## Before opening a pull request

Run the repository checks:

~~~sh
make check
~~~

When changing Actions files, check Markdown and workflow syntax in CI. For release or publishing workflows, verify the dry-run path; do not run a live publish as a test. Do not claim a provider, platform, or path was tested unless an actual run checked it.

Do not commit credentials, registry tokens, generated release artifacts, or real project secrets. Use the CI provider's secret store.
