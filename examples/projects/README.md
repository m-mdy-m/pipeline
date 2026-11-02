# Per-project examples

Each directory holds two files for one repository:

- `pipeline.ci.toml` – the `[ci]` table to add to that repository's `pipeline.toml` (or save as `pipeline.toml`). It holds the real choices: language, options, commands.
- `ci.yml` – a thin GitHub workflow. It installs runtimes through the shared actions and calls the engine; it contains no build or test commands.

| Directory | Repository type | Highlights |
| --- | --- | --- |
| `psx`, `gix` | Go CLIs | gofmt, vet, tidy, race, golangci-lint, PR benchmark, OS build matrix |
| `idios` | Go server + web client | Go preset, Node preset on `clients/web`, the repository's own `check` task graph |
| `log.c` | C library | `make check`, compiler matrix, AddressSanitizer/UBSan with CMake |
| `ftx.vim` | Vim plugin | Vim stable and nightly, feature and `:helptags` checks |
| `shelf` | pnpm workspace | pnpm install through the engine, then the project task graph |
| `agas` | Bun | `bun install --frozen-lockfile`, build, test |
| `trk` | pnpm | format check, typecheck, build |
| `site` | Static site | lint and build, then the shared `pages.yml` deploy |

The workflows reference `m-mdy-m/pipeline/...@main`; pin a tag or commit SHA for repeatable builds. These files were validated for structure (YAML, declared action inputs, parseable `[ci]` tables). They have **not** been run on GitHub against those repositories.
