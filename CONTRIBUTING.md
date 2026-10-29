# Contributing

1. Start from an up-to-date `develop` branch.
2. Create a branch with gix, for example `gix feature start reusable-ci`.
3. Keep workflows reusable, least-privilege, and secret-safe.
4. Validate changes locally with `make check` and inspect generated workflow YAML.
5. Open a pull request to `develop`; releases are promoted through a `release/*` branch.

Do not commit credentials, registry tokens, generated release artifacts, or real project secrets.
