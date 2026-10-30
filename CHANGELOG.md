# Changelog

All notable changes to Pipeline are documented in this file.

The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and release versions follow [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

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
