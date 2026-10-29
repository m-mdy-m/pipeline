# Changelog

Notable changes to this project are documented here. Stable release tags must have a matching version heading.

## [Unreleased]

### Added

- Modular Source Release implementation with reusable Git, path, changelog, security, archive, logger and bundle-verification components.
- Native structured logging through the pinned m-mdy-m/log.c C ABI and a post-download asset verifier.

- A dedicated source-only GitHub Release workflow with strict tag snapshots, configurable changelog handling, secret/path checks, and validated ZIP packaging.
- Source release contract tests, a dry-run smoke workflow, machine-readable manifest, and SHA-256 checksum manifest.
- Reusable GitHub Actions workflows for CI, benchmarks, release packaging, Docker Hub, npm, and GitHub Pages.
- Tag validation and release notes generated from this changelog.
- A release dry-run that builds and verifies assets without publishing.
- Timing summaries and environment metadata for repeated benchmarks.
- Workflow syntax validation as part of repository CI.
- Release smoke coverage for artifact bundle assembly and SHA-256 checksum generation.

### Changed

- README now documents concrete caller examples and workflow contracts.
- Workflow inventory and validation now distinguish catalog checks from actual YAML/action syntax validation.
- GitHub Actions updated to Node 24-compatible versions after actionlint exposed retired runtime references.
- Benchmark CSV output now records distinct rows and valid min/median/mean/max summaries.
