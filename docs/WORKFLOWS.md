# Workflow catalog

All workflows are designed for `workflow_call`, with optional `workflow_dispatch` only where manual operation is safe.

## Quality / CI

Use `.github/workflows/ci.yml` for pull requests and pushes. Configure explicit build, test, lint, and quality commands for the language. A release must not be considered valid when the test command is omitted.

## Benchmarks

Use `.github/workflows/benchmark.yml` for performance runs. Run multiple iterations, retain raw output as an artifact, and compare like-for-like runners. Avoid failing a PR on noisy timing deltas unless thresholds have been calibrated.

## GitHub Release

Use `.github/workflows/release.yml` to build a matrix of OS/architecture artifacts and generate SHA-256 checksums. Release publishing is triggered by a version tag and requires CI to pass first.

## Docker Hub

Use `.github/workflows/docker-publish.yml`. For SDKs, publish a build/development environment image with documented usage; do not add a server entrypoint unless the project is actually a service.

## npm

Use `.github/workflows/npm-publish.yml`. Keep `NPM_TOKEN` in repository or organization Actions secrets and use trusted publishing when configured.

## GitHub Pages

Use `.github/workflows/pages.yml` for static documentation and project websites. Keep build and deployment permissions separate; deploy only from the configured default branch.
