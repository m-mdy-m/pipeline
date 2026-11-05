# Changelog

## [Unreleased]

### Fixed

- Make the reusable YAML lint workflow ignore optional provider/configuration paths that are absent from consumer repositories.
- Add a regression test that executes the reusable lint script in a minimal consumer layout.


## [1.2.0] - 2026-11-03

### Added

- Added `src/pipeline/toolchains/`: provider-neutral language presets for Go, Rust, Java (Maven/Gradle), .NET, Node.js (npm/pnpm/yarn/bun), Python, C/C++ (CMake/Make) and Docker, with detection, per-stage overrides, preset options, and stage selection.
- Added the `pipeline ci` and `pipeline detect` commands. `pipeline ci` runs install, configure, lint, build and test through the existing task runner, writes the same JSON report, and exports `language`, `package_manager` and `succeeded` to the provider output file.
- Added GitHub composite actions `toolchain-quality`, `node-quality`, `go-quality`, `rust-quality`, `java-quality`, `dotnet-quality` and `run-pipeline`. They install a runtime and call the engine; they contain no build or test commands.
- Added GitHub job summaries and `::error` annotations to the GitHub adapter for `ci`, `run` and `task`.
- Added a `toolchain-preset` mode (with `stages` and `skip-stages`) to the reusable `ci.yml`, and Docker as a supported language.
- Added GitLab variables `PIPELINE_CI_LANGUAGE`, `PIPELINE_CI_IMAGE`, `PIPELINE_CI_ROOT` and `PIPELINE_CI_ARGS` with a reusable `.pipeline:toolchain` job.
- Added complete fixture projects under `examples/toolchains/` and a `toolchain-smoke.yml` workflow that runs every action against them, plus a negative control that must fail.
- Added structural workflow contract tests (valid YAML, resolvable `inputs`/`steps`/`needs` references, declared action inputs, push-gate coverage) and tests proving providers contain no toolchain commands.
- Added `docs/toolchains.md`.
- Added a `vim` preset, Go options (`gofmt`, `tidy`, `golangci`, `race`, `cover`), C/CMake options (`generator`, `build_type`, `sanitize`), `make check` detection, and Node `format:check`/`typecheck` lint scripts. Docker no longer requires a test stage.
- Added the optional `[ci]` table to `pipeline.toml` (`language`, `stages`, `skip`, `timeout_seconds`, `[ci.options]`, `[ci.commands]`, `[ci.bench]`). Precedence is CLI flags, then `[ci]`, then preset defaults.
- Added portable checks (`python -m pipeline.toolchains.checks`) so the presets need no shell syntax.
- Added `pipeline bench`: language-aware benchmarks compared against a git ref (temporary worktree) or a baseline JSON, with a threshold, `--report-only`, `--strict`, JSON and Markdown reports, and a GitHub step summary.
- Added `benchmarks/engine.py`, `benchmark-regression.yml`, `mode: bench` for `toolchain-quality`, and Bun/Vim runtime setup with dependency caching.
- Added `examples/projects/` with configuration and workflows for individual repositories, validated by a contract test.

- Added an opt-in Gitea-style build-release asset profile with XZ variants, per-file SHA-256 sidecars, a machine-readable manifest, and a provider-neutral bundle verifier.
- Added optional Sigstore signing, GPG detached signatures, GitHub release attestations, and signed-tag verification to the reusable GitHub release workflow.
- Added reusable Python setup and release-assets composite actions, plus an end-to-end smoke workflow that proves assembly, verification, and tamper rejection.
- Added a provider-neutral build-target catalogue for Linux, macOS, Windows x86/x86_64/ARM64, Android ABIs, iOS device/simulator architectures, and PWA outputs.
- Added separate `e2e-setup` and `e2e-test` release-target stages. Projects supply their own emulator/simulator provisioning and E2E commands; the shared runner records target OS, architecture, ABI, and results.
- Added repository-level dependency review, CodeQL, zizmor, YAML lint, and typo checks.
- Added Python 3.11–3.13 compatibility CI, Conventional Commit pull request title validation, and scheduled OSSF Scorecard analysis.
- Added a reusable Python quality composite action and workflow contract tests for version-tagged actions, permissions, and workflow inventory.
- Added Dependabot schedules for GitHub Actions and Python project metadata.

### Changed

- `ci-main.yml` now runs on every push to every branch, pull requests and the merge queue, and ends in a single `gate` job. It calls the Python matrix, toolchain smoke, YAML lint, spelling and documentation workflows, and tests the pushed commit's engine instead of `main`.
- `python-compatibility.yml`, `yamllint.yml` and `typos.yml` are now reusable (`workflow_call`) so the push gate can call them; the Python matrix also reports on macOS and Windows without blocking.
- The `python-quality` action now runs through the shared engine (`pipeline ci --language python`) instead of embedding `compileall` and `unittest` commands. It skips `install` by default.
- `ci.yml` installs Node.js and `requirements.txt` dependencies through the engine, sets up Rust with `rustup`, uses `actions/setup-java@v6`, and runs user-supplied commands through environment variables instead of interpolating them into the script.
- The GitLab template is split into a reusable bootstrap and two jobs, and installs `python3` when the selected image has none.
- `reusable-smoke.yml` runs on pushes to every branch when workflow, action or source files change.

- Kept the existing standard release asset layout as the default; richer release assets are opt-in so existing reusable-workflow callers remain compatible.
- Extended the reusable release workflow to download artifacts back onto each build target runner and run optional E2E setup/tests there, keeping GitHub Actions as orchestration only.
- Added merge-queue support to repository CI.
- Configured zizmor to accept version-tag references without requiring commit-SHA pins, matching the repository's tag-based action policy.

### Fixed

- Fixed Python compatibility checks across Windows and macOS by removing host-specific assumptions from the test suite.
- Preserved Windows path separators and quoted executable paths when parsing benchmark and toolchain commands.
- Fixed task execution for Windows `.cmd` and `.bat` shims by using native subprocess shell handling for verified batch files while keeping regular commands shell-free.
- Fixed Windows Bash discovery to prefer Git for Windows or the configured MSYS2 installation instead of selecting the WSL launcher from `System32`.
- Made Windows shell-resolution checks deterministic and benchmark command-parser tests independent of the host operating system.

## [1.1.2] - 2026-10-31

### Added

- Added a provider-neutral `artifact-test` release-target stage to `src/pipeline/release/target.py` and its CLI. CI providers transfer the per-target artifact and invoke the shared target runner; the core records and reports artifact-test results.

### Changed

- Resolve a canonical release tag in the shared release builder for both tag builds and branch dry-runs. Store it in `release-meta.json` and pass it to release scripts as `PIPELINE_RELEASE_TAG`, keeping artifact names consistent across release environments.
- Expose downloaded native-test artifacts through the provider-neutral `PIPELINE_ARTIFACT_TEST_DIR` contract instead of a project-specific environment variable.
- Retry GitHub native artifact downloads up to three times, using isolated temporary directories for each attempt, and report download and artifact-test outcomes separately.
- Extend the Pipeline release smoke test to exercise the complete artifact upload, download, and verification path.

All notable changes to Pipeline are documented in this file.

The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and release versions follow [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [1.1.1] - 2026-10-30

### Changed

- Replaced the MIT license with Mozilla Public License 2.0 (MPL-2.0), adding file-level copyleft and an explicit contributor patent grant.
- Updated Python package metadata to use the SPDX `MPL-2.0` expression.

### Fixed

- Fixed source-release branch dry-runs for changelogs that contain only versioned sections and no `[Unreleased]` heading.
- Source-release dry-runs now prefer `[Unreleased]` when present and otherwise use the newest version-specific section.
- Added regression coverage for release-only changelogs and invalid `Unreleased` sections.

---

## [1.1.0] - 2026-10-30

### Added

- Introduced an installable Python package under `src/pipeline/`.
- Added dedicated CLI entry points for:
  - Core task execution.
  - Local, GitHub Actions, and GitLab CI providers.
  - Benchmark execution.
  - Build release preparation.
  - Source release preparation and verification.
- Added shared utilities for hashing, atomic file operations, logging, and path handling.
- Added reusable Python package publishing workflow with PyPI distribution validation.
- Added reusable security-check workflow with Gitleaks integration.
- Added reusable workflow smoke tests covering CI, documentation, security, benchmarks, releases, Docker, npm, Python packaging, and GitHub Pages.
- Added Java and .NET support to the reusable CI workflow.
- Added lockfile-aware dependency installation for npm, pnpm, and Yarn.
- Added dry-run support for Docker publishing, npm publishing, and GitHub Pages deployment.
- Added Java and .NET version configuration inputs.
- Added common utility tests and expanded integration coverage.

### Changed

- Reorganized the runtime into a modular `src/pipeline/` package.
- Moved runtime modules from `scripts/` into dedicated package modules:
  - `core/` — task execution, configuration, context, and runtime contracts.
  - `providers/` — GitHub, GitLab, and local execution adapters.
  - `benchmark/` — benchmark execution and reporting.
  - `release/` — build releases, source archives, metadata, and verification.
  - `common/` — shared logging, hashing, and I/O functionality.
  - `utils/` — shared path and filesystem utilities.
- Removed the old `scripts/` runtime layout and updated imports and execution paths.
- Added `pyproject.toml` for package metadata, installation, and CLI entry-point registration.
- Updated `pipeline.toml` to validate and test the new `src/` package structure.
- Updated GitHub Actions workflows to execute package modules instead of legacy script paths.
- Expanded reusable CI configuration and validation for additional languages and package managers.
- Consolidated duplicated logging, SHA-256 hashing, atomic-write, and workflow-output implementations.
- Improved release tooling by centralizing shared helpers and strengthening source-bundle verification.
- Updated benchmark execution paths and self-benchmark configuration.
- Updated Makefile, examples, tests, and development instructions to follow the new package structure.
- Reworked README and documentation to reflect the updated architecture and workflows.

### Fixed

- Corrected GitHub Actions workflow expressions and benchmark output paths.
- Fixed Docker workflow smoke-test configuration.
- Improved release helper validation and source-bundle verification.
- Required matching changelog sections for stable releases.
- Scoped write permissions to the jobs that require them.
- Improved reusable workflow input validation and error handling.
- Fixed Markdown lint configuration for repeated headings.
- Updated workflow smoke tests to validate the modular package execution paths.

### Migration

- Runtime modules are now located under `src/pipeline/` instead of `scripts/`.
- Use the installed `pipeline` command or Python module execution instead of invoking legacy script paths directly.
- For source-based execution, configure `PYTHONPATH=src`.
- Update custom automation that references old script paths.
- Update custom reusable workflow integrations to use the new workflow inputs and dry-run options where applicable.
- Install the package using the project's Python packaging configuration when using the registered CLI commands.

---

## [1.0.0] - 2026-10-30

### Added

- Provider-neutral task runner with TOML configuration, dependencies, timeouts, workspace checks, environment variables, and structured reports.
- Local, GitHub Actions, and GitLab CI adapters for the shared `PIPELINE_*` environment contract.
- Local artifact collection with safe file checks, atomic copies, manifests, and SHA-256 hashes.
- Reusable benchmark runner with logs, environment information, and CSV, JSON, and Markdown summaries.
- Build-release helpers for version validation, changelog extraction, release metadata, and checksums.
- Source-release tooling for exact tagged snapshots, path and sensitive-file checks, ZIP validation, and bundle verification.
- Reusable GitHub workflows for CI, benchmarks, build releases, source releases, Docker Hub, npm, GitHub Pages, and documentation checks.
- GitLab CI example, integration tests, and beginner-focused documentation and runnable examples.

### Changed

- Moved benchmark, build-release, and source-release logic into reusable scripts, keeping provider YAML focused on orchestration.
- Added `pipeline-ref` inputs so callers can pin the workflow helper revision.
- Reworked the README and guides around getting started, configuration, providers, benchmarking, releases, and development.
- Added a tag-triggered workflow for versioned build archives and checksums.
