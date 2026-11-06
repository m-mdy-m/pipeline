# Language toolchains

pipeline can run the usual **install → lint → build → test** sequence for a project without a `pipeline.toml`. The knowledge of *what to run* for each language lives in the installable package (`src/pipeline/toolchains/`). GitHub Actions, GitLab CI and your terminal only provide the runtime (Node, Go, Rust, …) and then call the same command:

~~~sh
pipeline detect            # which languages does this directory look like?
pipeline ci                # detect the language, then run every stage
pipeline ci --dry-run      # print the plan as JSON, execute nothing
pipeline ci --language go --skip lint
~~~

GitHub and GitLab are providers. They schedule the job, install the runtime and keep the report. They never contain a copy of `npm ci`, `go test` or `cargo test`; adding or fixing a language means changing the Python package once, for every provider.

## Stages

| Stage | Meaning | Required |
| --- | --- | --- |
| `install` | Fetch dependencies | no |
| `configure` | Generate build files (CMake) | no |
| `lint` | Static checks | no |
| `build` | Compile or package | no |
| `test` | Run the tests | **yes** |

Stages run in that order and each depends on the one before it, so a failed `build` marks `test` as skipped. If a language has no test command and you do not pass `--test-command` or `--skip test`, `pipeline ci` stops with exit code 2 instead of silently reporting success.

## Built-in presets

| Language | Detected from | Install | Lint | Build | Test |
| --- | --- | --- | --- | --- | --- |
| `go` | `go.mod` | `go mod download` | `gofmt` check, `go vet ./...`, optional `go mod tidy` check and `golangci-lint` | `go build ./...` | `go test ./...` (optionally `-race`, `-cover`) |
| `rust` | `Cargo.toml` | `cargo fetch` | `cargo clippy --all-targets -- -D warnings` | `cargo build` | `cargo test` |
| `java` | `pom.xml`, `build.gradle[.kts]` | – | – | Maven `package` or Gradle `assemble` | Maven `verify` or Gradle `check` |
| `dotnet` | `*.sln`, `*.csproj`, `*.fsproj` | `dotnet restore` | – | `dotnet build -c Release` | `dotnet test -c Release` |
| `node` | `package.json` | `npm ci`, `pnpm`, `yarn` or `bun` install (frozen lockfile) | `<pm> run` for each of `format:check`, `lint`, `typecheck` that exists | `<pm> run build` if the script exists | `<pm> run test` if the script exists |
| `python` | `pyproject.toml`, `setup.py`, `requirements.txt` | `pip install -r requirements.txt` or `pip install -e .` | – | `compileall` on `src/` or `app/` | `pytest` if configured, otherwise `unittest discover` |
| `vim` | `plugin/*.vim`, `autoload/*.vim` | – | feature check (`+job`, `+timers`), a clean load of every `plugin/*.vim`, and `:helptags` | – | `make test` when the Makefile has a `test:` target, otherwise a headless load of every plugin file |
| `c` | `CMakeLists.txt`, `Makefile` | – | – | CMake configure + build, or `make` | `ctest`, or `make check` / `make test` when the Makefile has that target |
| `latex` | root `main.tex`, `*.tex`, or a LaTeX Makefile | Installed by the GitHub action on Ubuntu | – | `make build` when present, otherwise `latexmk` with the selected engine | Validate that generated PDFs are complete |
| `docker` | `Dockerfile` | – | – | `docker build` | – (no test stage is required) |
| `custom` | – | you supply every command | | | |

Details worth knowing:

- Node picks the package manager from the lockfile (`pnpm-lock.yaml`, `bun.lock`/`bun.lockb`, `yarn.lock`, otherwise npm). Yarn Berry (`.yarnrc.yml`) uses `--immutable`. The placeholder `npm init` test script ("no test specified") does not count as a test.
- Rust adds `--locked` when `Cargo.lock` exists. The lint stage needs the `clippy` component.
- Java prefers a wrapper (`./mvnw`, `./gradlew`) when it is committed.
- With `--language auto` (the default) the first match in this order wins: go, rust, java, dotnet, node, python, vim, c, latex, docker. `pipeline detect` lists every match, so a mixed repository can pick explicitly with `--language`.
- The LaTeX preset prefers a project-owned `make build` target when one exists. That target intentionally owns multi-document or bilingual orchestration, including the selection of individual engines. When a Makefile build target is present, `source` and `engine` options are not used; put those choices in the Makefile. Without that target, set `--option source=main.tex` and optionally `--option engine=xelatex`. The `output` option defaults to `build`; the final stage checks for a PDF header and EOF marker, not just a file name. The GitHub action provisions TeX Live and verifies that `biblatex.sty`, Chicago Notes, `algorithm.sty` and `algpseudocode.sty` are discoverable before building.

## Toolchain caches and lock files

GitHub-hosted runners are fresh machines for every job. Pipeline can reuse downloaded packages, but it cannot preserve an installed TeX Live tree between hosted jobs.

- Node.js package caches are keyed by the detected package-manager lockfile.
- The `toolchain-quality` action can cache pip downloads when `python-cache-dependency-path` names a requirements or project metadata file.
- For LaTeX, pass `latex-packages-file` with one Debian package (or `package=version`) per line. Pipeline caches the downloaded `.deb` archives by runner OS, architecture and manifest content. Changing the package manifest invalidates that cache. Package indexes are still refreshed and dpkg still installs packages on a fresh hosted runner.
- `latex-setup-mode: verify` checks the required executables and TeX packages without invoking apt. Use it only when the runner image already contains the complete toolchain. A persistent self-hosted runner can therefore skip package installation; do not send untrusted public pull-request code to a persistent runner with secrets or access to sensitive networks.

Example:

~~~yaml
- uses: m-mdy-m/pipeline/.github/actions/toolchain-quality@main
  with:
    language: latex
    cache: "true"
    latex-packages-file: .ci/locks/texlive-packages.ubuntu-24.04.lock
    python-cache-dependency-path: workspace/pyproject.toml
    # Set to verify only on a runner that already has the locked toolchain.
    latex-setup-mode: install
~~~

The first cold hosted run still has to download and install TeX Live. Subsequent runs can reuse matching package archives, while a pre-provisioned persistent runner can use `verify` to avoid that installation entirely. A sub-10-second toolchain setup is not guaranteed on GitHub-hosted runners; the actual build and tests take additional time.

## Overrides and options

Any stage can be replaced. The text is split like a shell line but **never run by a shell**, which keeps behaviour identical on every provider:

~~~sh
pipeline ci --language node --test-command "npm run test:ci"
pipeline ci --language go --test-command "go test -race ./..."
pipeline ci --language custom --test-command "make verify"
pipeline ci --stages build,test
pipeline ci --skip install,lint
~~~

If you really need shell syntax, say so explicitly: `--test-command "bash -c 'make && make check'"`.

`--option KEY=VALUE` tunes a preset:

| Option | Applies to | Values |
| --- | --- | --- |
| `package_manager` | node | `npm`, `pnpm`, `yarn`, `bun` |
| `build_tool` | java | `maven`, `gradle` |
| `source` | python | directory compiled by `build` and placed on `PYTHONPATH` for tests (default `src` or `app`) |
| `tests` | python | test directory (default `tests`) |
| `test_pattern` | python | unittest filename pattern (default `test_*.py`) |
| `runner` | python | `pytest` or `unittest` |
| `gofmt` | go | `true` (default) fails when `gofmt -l` lists files |
| `tidy` | go | `true` fails when `go mod tidy` would change `go.mod`/`go.sum` (the files are restored) |
| `golangci` | go | `true` runs `golangci-lint run` (the tool must be installed) |
| `race`, `cover` | go | `true` adds `-race` / `-cover` to `go test` |
| `generator`, `build_type`, `sanitize` | c (CMake) | CMake generator, `CMAKE_BUILD_TYPE`, and a sanitizer list such as `address,undefined` |
| `vim` | vim | Vim executable (default `vim`) |

Other flags: `--timeout SECONDS` per stage (default 1800), `--result FILE` for the JSON report, `--no-fail-fast`, `--json`.

When a provider output file is available (`PIPELINE_OUTPUT_FILE`), the run writes `language`, `package_manager` and `succeeded` to it. In GitHub Actions these become step outputs.

## Repository-owned configuration: the `[ci]` table

A project can keep its CI choices next to the code, so every provider and every developer machine uses the same ones. Add a `[ci]` table to `pipeline.toml`; a file that contains only `[ci]` is valid.

~~~toml
[ci]
language = "go"
skip = ["install"]
timeout_seconds = 900

[ci.options]
race = true
tidy = true

[ci.commands]
test = "make check"

[ci.bench]
command = "go test -run ^$ -bench . -count 5 ./..."
parser = "gobench"
threshold_percent = 30
~~~

Precedence is: command-line flags, then `[ci]`, then preset defaults. Unknown keys, unknown stage names and wrong types are configuration errors. See `examples/projects/` for tables written for real repositories.

## Portable checks

Steps that would otherwise need shell syntax (`test -z "$(gofmt -l .)"`) are implemented once in Python and called as `python -m pipeline.toolchains.checks {gofmt,go-mod-tidy,vim-features,vim-load,vim-helptags}`. They behave the same on Linux, macOS and Windows.

## GitHub Actions

Each action installs the runtime with the official `setup-*` action (or `rustup`), sets up Python for the engine, and calls `python -m pipeline.providers.github ci`. The adapter then adds a **job summary table** and `::error` **annotations** for failed stages; those are presentation details owned by GitHub, the results come from the core.

| Action | Use it for |
| --- | --- |
| `toolchain-quality` | Any language, including `language: auto` detection |
| `node-quality` | Node.js (`node-version`, `pnpm-version`) |
| `go-quality` | Go (`go-version`) |
| `rust-quality` | Rust (`rust-toolchain`; installs clippy and rustfmt) |
| `java-quality` | Java with Maven or Gradle (`java-version`) |
| `dotnet-quality` | .NET (`dotnet-version`) |
| `python-quality` | Python (`python-version`, `source-path`, `tests-path`, `test-pattern`, `runner`) |
| `run-pipeline` | Run named tasks from your own `pipeline.toml` and upload the report |

Every language action shares these inputs: `working-directory`, `install-command`, `lint-command`, `build-command`, `test-command`, `stages`, `skip`, `options`, `timeout-seconds`, `python-version`. Outputs: `language`, `package-manager`, `succeeded`.

~~~yaml
name: CI
on:
  push:
  pull_request:

permissions:
  contents: read

jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v7
      - uses: m-mdy-m/pipeline/.github/actions/toolchain-quality@main   # pin a tag or SHA in production
        with:
          language: auto
~~~

Monorepo, several languages:

~~~yaml
jobs:
  web:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v7
      - uses: m-mdy-m/pipeline/.github/actions/node-quality@main
        with:
          working-directory: web
          pnpm-version: "9.15.4"
  api:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v7
      - uses: m-mdy-m/pipeline/.github/actions/go-quality@main
        with:
          working-directory: api
          test-command: go test -race ./...
~~~

The reusable workflow `ci.yml` offers the same presets with `toolchain-preset: true`; see [Providers](providers.md).

## GitLab CI

The canonical template exposes the same engine. Set `PIPELINE_CI_LANGUAGE` (and an image that contains the runtime) and the `pipeline:toolchain` job runs `pipeline ci`:

~~~yaml
include:
  - remote: https://raw.githubusercontent.com/m-mdy-m/pipeline/main/src/pipeline/providers/gitlab/workflows/ci.yml

variables:
  PIPELINE_CI_LANGUAGE: node
  PIPELINE_CI_IMAGE: node:22
  PIPELINE_CI_ARGS: "--skip lint"
~~~

If the image has no Python 3.11+, the template installs `python3` with `apt-get` (Debian-based images such as `node`, `golang`, `rust` and `maven` work out of the box). Use the hidden job `.pipeline:toolchain` with `parallel: matrix` to cover several languages, as this repository's own `.gitlab-ci.yml` does.

## Benchmarks and regressions

`pipeline bench` runs a language's benchmarks and compares them. See [Benchmarks](benchmarking.md#detect-regressions-with-pipeline-bench). In GitHub, `toolchain-quality` with `mode: bench` calls it, and `benchmark-regression.yml` runs it on pull requests against the base commit.

## Per-project examples

[`examples/projects/`](../examples/projects/) has a `pipeline.ci.toml` and a workflow for each of the maintainer's repositories (Go, C, Vim, Node with npm/pnpm/bun, and a Pages site). Their workflow inputs are checked against the real action definitions by a contract test.

## How this repository tests it

Every push to every branch runs [`ci-main.yml`](../.github/workflows/ci-main.yml). Its `toolchain-smoke.yml` job executes the actions above against the complete example projects in [`examples/toolchains/`](../examples/toolchains/) (Python, Node.js, Go, Rust, Java/Maven, .NET, C with Make, C with CMake, Docker), asserts the detected language, and includes a negative control that must fail. The Python test suite additionally plans every fixture and runs the Node.js, Go, Rust, C and Python ones when their toolchains are installed. See [Development](development.md#what-runs-on-every-push).

## Add a language

1. Add a preset function and a `Preset(...)` entry in `src/pipeline/toolchains/presets.py`.
2. Add a fixture project under `examples/toolchains/` and list it in `tests/test_toolchains.py` (`DetectionTests.EXPECTED`) and in `.github/workflows/toolchain-smoke.yml`.
3. If the provider needs a runtime installed, add it to the GitHub actions and `ci.yml`. Do not add build or test commands there.
