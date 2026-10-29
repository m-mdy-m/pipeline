# Workflow catalog

The files below are reusable workflows, intended to be invoked from a workflow in the consuming project. Use the smoke/test workflows in this repository to see those contracts exercised.

## CI and workflow validation

Use .github/workflows/ci.yml for build, test, and optional lint commands. The caller chooses its toolchain and commands. .github/workflows/docs-check.yml checks Markdown and runs actionlint against executable workflow files.

## Benchmarks

Use .github/workflows/benchmark.yml for repeated performance commands. It preserves raw output, environment information, iteration duration, and min/median/mean/max summary. .github/workflows/benchmark-self.yml benchmarks this repository's own validation and tracked source footprint.

## GitHub Release

Use .github/workflows/release.yml for tag-driven multi-OS/multi-architecture packaging, validation against CHANGELOG.md, changelog-derived release notes, per-target artifact uploads, checksums, and publishing. .github/workflows/github-release-smoke.yml exercises test/build/artifact collection in dry-run mode without publishing.

## Source-only GitHub Release

Use `.github/workflows/source-release.yml` when the intended deliverable is a source archive rather than compiled artifacts. The workflow validates the exact tag snapshot, changelog policy, file paths, symlinks, secrets, ZIP structure, and checksums before publishing. All inputs and security defaults are documented in [Source Release contract](SOURCE-RELEASES.md). The local `source-release-smoke.yml` exercises this path without creating a public release.

## Docker Hub

Use .github/workflows/docker-publish.yml on version tags. Map your own Docker Hub account credentials to its username and token secrets. The reusable workflow builds Linux AMD64 and ARM64 images. For SDKs, publish a documented build environment; do not add a server entrypoint unless the project is actually a service.

A non-executable caller example is in examples/docker-sdk-caller.yml.

## npm

Use .github/workflows/npm-publish.yml on version tags. Map the project's NPM_TOKEN to the npm-token secret. Stable versions are published with the default latest dist-tag; versions with a hyphen are published to next.

## GitHub Pages

Use .github/workflows/pages.yml to build a static site and deploy it to GitHub Pages. It is reusable only; the consuming project controls when the deploy job is called and grants pages: write and id-token: write for deployment.
