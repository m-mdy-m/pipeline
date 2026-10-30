# Contributing

1. Start from an up-to-date `develop` branch.
2. Create a focused branch with gix, for example `gix feature start reusable-ci`.
3. Put reusable task behavior in `scripts/`. Keep provider-specific environment handling in `scripts/providers/`.
4. Keep GitHub workflow YAML focused on scheduling, runner setup, artifact transport, and GitHub publishing.
5. Update the relevant guide when a script, input, or workflow contract changes.
6. Run `make check` and inspect the generated benchmark or release reports when changing those helpers.
7. Open a pull request to `develop`.

Do not commit credentials, registry tokens, generated release artifacts, or real project secrets.
