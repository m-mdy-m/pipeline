# Changelog

All notable changes to pipeline are documented here.

The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and release versions follow [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

- Installable `src/pipeline` package with CLI entry points for task execution, provider adapters, benchmarking, releases, and source-bundle verification.
- Shared logging, hashing, atomic file-writing, output, and path-boundary utilities.
- Reusable Python package publishing and Gitleaks security-check workflows.
- A reusable-workflow smoke workflow covering CI, docs, security, benchmarks, release preparation, Docker, npm, Python packaging, and Pages without publishing or deploying.

### Changed

- Moved runtime modules from `scripts/` into `src/pipeline/` and updated imports, tests, examples, documentation, Makefile, and provider workflows.
- Expanded reusable CI support to Java and .NET and added lockfile-aware npm, pnpm, and Yarn setup.
- Added dry-run modes for Docker, npm, and GitHub Pages workflows.
- Consolidated duplicate logger, SHA-256, atomic-write, and workflow-output implementations into `pipeline.common`.

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
