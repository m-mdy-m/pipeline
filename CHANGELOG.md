# Changelog

Notable changes to this project are documented here. Stable release tags must have a matching version heading.

## [Unreleased]

### Added

- Reusable GitHub Actions workflows for CI, benchmarks, release packaging, Docker Hub, npm, and GitHub Pages.
- Tag validation and release notes generated from this changelog.
- A release dry-run that builds and verifies assets without publishing.
- Timing summaries and environment metadata for repeated benchmarks.
- Workflow syntax validation as part of repository CI.

### Changed

- README now documents concrete caller examples and workflow contracts.
- Workflow inventory and validation now distinguish catalog checks from actual YAML/action syntax validation.
