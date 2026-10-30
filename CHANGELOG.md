# Changelog

All notable changes to pipeline are documented here.

The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and release versions follow [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [1.0.0] - 2026-10-30

### Added

- Provider-neutral task runner with TOML configuration, task dependencies, timeouts, working-directory checks, environment variables, and structured run reports.
- Local, GitHub Actions, and GitLab CI adapters that translate provider context into the shared `PIPELINE_*` environment.
- Local artifact collection with safe file checks, atomic copies, an inventory manifest, and SHA-256 hashes.
- Reusable benchmark runner that records each attempt, raw command logs, environment information, and CSV, JSON, and Markdown summaries.
- Shared build-release helpers for version validation, changelog extraction, release metadata, and SHA-256 checksum generation.
- Source-release tooling that packages the exact tagged source snapshot, checks paths and sensitive files, validates ZIP contents, and verifies published assets.
- Reusable GitHub Actions workflows for CI, benchmarks, build releases, source releases, Docker Hub, npm, GitHub Pages, and documentation checks.
- GitLab CI example that runs the same task graph through the GitLab adapter.
- Unit and integration tests for task execution, provider contracts, benchmarking, release preparation, source packaging, and bundle verification.
- Beginner-focused documentation and runnable GitHub Actions, GitLab CI, and task-configuration examples.

### Changed

- Moved shared benchmark, build-release, and source-release behavior into scripts so GitHub workflow YAML only coordinates runners, provider context, artifact transfer, and publishing.
- Made the workflow helper revision explicit through `pipeline-ref` inputs, so callers can pin workflow definitions and their helper scripts to the same tag or commit.
- Reworked the README and documentation around practical tasks: getting started, configuration, providers, benchmarks, releases, and development.
- Added a tag-triggered release workflow for publishing versioned build archives and checksums.
