# Changelog

Notable changes to this project are documented here. Stable release tags must have a matching version heading.

## [Unreleased]

### Added

- Provider-neutral repeated benchmark runner with CSV, JSON, Markdown, raw logs, and environment reports.
- Provider-neutral build-release helper for tag validation, changelog notes, and SHA-256 artifact manifests.
- Unit tests for benchmark execution, release-note preparation, and checksum generation.

### Changed

- GitHub benchmark and build-release workflows now call shared scripts instead of reimplementing measurement, version parsing, changelog extraction, or checksum generation in YAML.
- GitHub workflows now keep provider-only work such as runner setup, artifact transfer, and publishing separate from shared script behavior.
- Workflow helper checkouts accept an explicit `pipeline-ref` so a reusable workflow and its scripts can be pinned to the same revision.
- The main README and guides now explain the configuration, shared scripts, and provider-adapter boundary without a long repository map.
- The task validation command now compiles the complete `scripts/` directory, and the test task covers all discovered unit and provider-contract tests.
