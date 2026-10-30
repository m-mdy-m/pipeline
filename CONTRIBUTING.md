# Contributing

Thanks for taking an interest in pipeline.

## Before you start

Use Python 3.12, Git, and Make. Start from an up-to-date `develop` branch and make a focused branch for your change.

## Where changes belong

- Put behavior shared by local, GitHub, and GitLab runs in `scripts/`.
- Keep provider-specific environment handling in `scripts/providers/`.
- Keep GitHub scheduling, artifact upload, and publishing in `.github/workflows/`.
- Keep task definitions in `pipeline.toml`.
- Update the relevant guide and example when a command or workflow input changes.

## Before opening a pull request

Run the full local check:

~~~sh
make check
~~~

When changing GitHub Actions files, make sure the Markdown and workflow checks pass in CI. Do not claim a test or platform was verified unless it was actually run.

Do not commit credentials, registry tokens, generated release artifacts, or real project secrets. Use the CI provider's secret store.
