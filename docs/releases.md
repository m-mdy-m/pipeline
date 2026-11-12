# Build and publish a release

pipeline provides two different release workflows. Choose the one that matches what you want to publish.

- **Build release**: run your build and test commands, collect the files they produce, and attach those files to a GitHub Release.
- **Source release**: make a ZIP from the exact files tracked by a Git tag, then check the ZIP and its contents.

A source ZIP does not compile your project. A build release does not replace the source-release safety checks. For installable package publication to GHCR/OCI registries, use the separate [OCI package workflow](oci-packages.md); GitHub Release assets and OCI packages are different distribution contracts.

## Release this repository

A push of a version tag such as `v1.1.1` starts `.github/workflows/release-on-tag.yml`.

That workflow calls the reusable build-release workflow in this repository. It:

1. Checks out the tagged commit.
2. Uses the shared release helper to validate the tag and prepare the matching changelog section.
3. Runs the repository's task checks.
4. Creates a compressed source archive from the tagged Git commit.
5. Generates a SHA-256 checksum file for the release assets.
6. Publishes the notes, archive, and checksums as a GitHub Release.

The workflow does not publish a release from a normal branch push. To publish version `1.1.1`, the tag must be named `v1.1.1` and pushed to GitHub after the version section has been added to `CHANGELOG.md`.

From a checkout that contains the release commit:

~~~sh
git tag -a v1.1.1 -m "pipeline 1.1.1"
git push origin v1.1.1
~~~

The tag points to the current commit. If you change the changelog or code after creating the tag, create a new version tag rather than moving the old one.

## Use the build-release workflow in another project

~~~yaml
name: Release

on:
  push:
    tags: ["v*"]

permissions:
  contents: write

jobs:
  release:
    uses: m-mdy-m/pipeline/.github/workflows/release.yml@main
    with:
      pipeline-ref: main
      go-version: "1.25.0"
      setup-node: true
      node-version: "22"
      pnpm-version: "9.15.4"
      test-command: make check
      build-command: make release
      artifact-path: dist/*
      changelog-path: CHANGELOG.md
~~~

The reusable build workflow can provision optional toolchains before running the caller's test and build commands:

- `go-version` installs the requested Go version when the release uses Go.
- `setup-node`, `node-version`, and `pnpm-version` prepare Node.js and optionally activate pnpm for frontend builds.
- Windows matrix entries may set `msys2_msystem` and `msys2_packages`. This installs the requested MSYS2 compiler environment without running a full in-place MSYS2 system upgrade, and runs that matrix entry's test/build commands with the MSYS2 shell.

For example, add native Windows compiler environments to the matrix:

~~~yaml
build-matrix-json: >-
  {"include":[
    {"id":"windows-amd64","os":"windows-2025","msys2_msystem":"UCRT64","msys2_packages":"mingw-w64-ucrt-x86_64-gcc"},
    {"id":"windows-arm64","os":"windows-11-arm","msys2_msystem":"CLANGARM64","msys2_packages":"mingw-w64-clang-aarch64-clang"}
  ]}
~~~

For multi-platform releases, pass a JSON `build-matrix-json` value. Each matrix entry needs an `id` and an `os`. An entry can also override `test_command`, `build_command`, or `artifact_path`. Matrix-specific MSYS2 fields are optional and only needed when a Windows build requires an MSYS2 toolchain.

A release build must create at least one file matching `artifact-path`. A failed test or build prevents publication.

### Prepare project-owned metadata from the complete target set

Some component publishers need to create one release metadata document only after every native matrix target has produced its archive and checksum. Set the optional `asset-preparation-command` to run a project-owned generator in the tagged source checkout after all target artifacts have been downloaded and before the shared assembler creates the flat asset set, `SHA256SUMS`, optional manifest, signatures and attestations.

The command runs once on the Ubuntu assemble runner. Pipeline checks out the exact selected `source-ref` (or triggering ref) into `component-source/` with full tag history and passes:

- `PIPELINE_RELEASE_TAG`: validated release tag.
- `PIPELINE_RELEASE_VERSION`: parsed SemVer.
- `PIPELINE_SOURCE_SHA`: exact commit resolved by the prepare job.
- `RELEASE_ASSETS_DIRECTORY`: absolute path to the downloaded per-target artifacts.

The project-owned generator must verify every input artifact and write any additional asset into a top-level directory under `$RELEASE_ASSETS_DIRECTORY` whose name begins with `release-build-` (for example, `release-build-metadata/`). The shared assembler then includes it in the same normalized asset set and computes the final checksum/manifest. The hook is not run unless configured; existing release workflows remain unchanged.

~~~yaml
asset-preparation-command: >-
  python scripts/generate-release-metadata.py
  --tag "$PIPELINE_RELEASE_TAG"
  --source-revision "$PIPELINE_SOURCE_SHA"
  --artifact-dir "$RELEASE_ASSETS_DIRECTORY"
  --output "$RELEASE_ASSETS_DIRECTORY/release-build-metadata/component-$PIPELINE_RELEASE_VERSION.json"
~~~

Set `asset-profile: gitea` to opt into a richer, Gitea-style asset layout without changing the default output of existing consumers. The profile preserves each original artifact and adds an XZ-compressed `.xz` variant, a `.sha256` sidecar for every payload, a machine-readable `manifest.json` with version/tag/commit and per-target artifact metadata, and a top-level `SHA256SUMS`. Existing `.xz` siblings are reused only when they decompress to the exact original bytes; collisions or stale sidecars fail the release rather than silently publishing ambiguous files.

The shared verifier is provider-neutral and can be used by GitHub Actions, GitLab CI, or a local release script:

~~~sh
PYTHONPATH=.pipeline/src python -m pipeline.release.build_cli verify --assets-directory release-assets
~~~

The `release-assets-smoke.yml` workflow exercises the composite action end to end: it assembles a deterministic fixture, checks the XZ payload and checksum sidecars, verifies the bundle, then tampers with an asset and confirms verification fails.

The reusable GitHub release workflow also supports optional asset signing and provenance. Set `sign-assets: true` to create keyless Sigstore bundles for the release files. Set `gpg-signing: true` and supply `gpg-private-key` (plus `gpg-passphrase` when needed) to add detached armored `.asc` signatures. Set `attest-release: true` to create a GitHub artifact attestation for `manifest.json` and attach its bundle as `release-attestation.json`; this requires the caller to grant `id-token: write` and `attestations: write`, and GitHub's artifact-attestation feature must be available for the repository. These options are off by default for backwards compatibility.

For cryptographically verified tags, create an annotated signed tag with `git tag -s` and set `require-signed-tag: true` with the corresponding armored public key in the `tag-verification-key` secret. This verifies the signature against the key supplied to CI. GitHub's **Verified** badge also depends on GitHub recognizing that signing key on the account that owns it; a CI verification alone cannot manufacture that badge.

The artifact pattern may match both files and directories. The assemble step normalizes the downloaded results into flat, uniquely named GitHub Release assets:

- A selected directory with a sibling archive of the same name (for example, `dist/app/` and `dist/app.zip`) is treated as an unpacked copy; the existing archive is published and the directory contents are omitted.
- A selected directory without a matching sibling archive is packaged as a `.tar.gz` asset.
- Files with the same basename from different build targets are renamed with their target ID as a prefix. SHA-256 sidecar references are updated when an asset is renamed.
- The pipeline writes one top-level `SHA256SUMS` manifest for the normalized files.

This means a common pattern such as `artifact-path: dist/*` works when `dist` contains a ready-made archive, its unpacked package directory, or both. GitHub Release assets are flat, so the pipeline removes the downloaded artifact folder structure before publishing.

### Test the packaged artifact on its native runner

The optional `artifact-test-command` runs after the target's build artifacts have been uploaded and downloaded again on that same native runner. The reusable workflow passes the command to the provider-neutral release target runner as the `artifact-test` stage; it does not execute or interpret the test command itself. The downloaded files are exposed to the test command through `PIPELINE_ARTIFACT_TEST_DIR`; the provider owns the temporary directory and download transport. GitHub downloads are attempted up to three times in isolated temporary directories to tolerate transient artifact-storage failures.

~~~yaml
artifact-path: dist/release/*
artifact-test-command: bash scripts/release/test-artifacts.sh
build-matrix-json: >-
  {"include":[
    {"id":"linux-amd64","os":"ubuntu-24.04"},
    {"id":"windows-amd64","os":"windows-2025","artifact_test_command":"pwsh -NoProfile -File scripts/release/test-artifacts.ps1"}
  ]}
~~~

Each stage is recorded as `.pipeline-artifacts/release-targets/<target>/<stage>.json` and included in the shared target summary. An artifact-test failure fails that target and prevents release assembly and publication. A project using another CI host can download its own artifact and invoke the same core stage with `python -m pipeline.release.target_cli run --target <target> --stage artifact-test`, setting `PIPELINE_RELEASE_COMMAND` to the project-owned test command. The CI provider is responsible only for its own artifact transfer and native-runner setup.

### Configure native E2E checks per target

The release workflow separates artifact inspection from end-to-end behavior. Configure either workflow-level defaults or per-target commands:

~~~yaml
e2e-setup-command: bash scripts/e2e/prepare.sh
e2e-test-command: bash scripts/e2e/run.sh
build-matrix-json: >-
  {"include":[
    {
      "id":"android-arm64-v8a",
      "os":"ubuntu-24.04",
      "target_os":"android",
      "architecture":"arm64",
      "abi":"arm64-v8a",
      "platform":"mobile",
      "e2e_setup_command":"bash scripts/e2e/start-android-emulator.sh",
      "e2e_test_command":"bash scripts/e2e/android.sh"
    },
    {
      "id":"ios-simulator-arm64",
      "os":"macos-15",
      "target_os":"ios-simulator",
      "architecture":"arm64",
      "abi":"simulator",
      "platform":"mobile",
      "e2e_setup_command":"bash scripts/e2e/boot-ios-simulator.sh",
      "e2e_test_command":"bash scripts/e2e/ios.sh"
    }
  ]}
~~~

Each target can override the global commands using `e2e_setup_command` and `e2e_test_command`. An E2E setup command without a matching test command is rejected. Both commands execute through the shared `target_cli` runner, and the E2E test runs only after the build artifact has been downloaded again on the same matrix runner. The downloaded files are available as `PIPELINE_ARTIFACT_TEST_DIR`; target metadata is exposed through `PIPELINE_TARGET_OS`, `PIPELINE_TARGET_ARCH`, `PIPELINE_TARGET_ABI`, and `PIPELINE_TARGET_PLATFORM`.

The setup command is where the project chooses how to start a real device, simulator or emulator, install SDKs, configure test credentials, or start a test service. The E2E command is project-owned and may use Playwright, WebdriverIO, Appium, XCTest, Espresso, Maestro, or a custom harness. Pipeline does not invent an E2E command or pretend that a cross-compiled binary has run on the target. Set the matrix `os` to the native target runner where available; for a different runner architecture, boot a compatible emulator/device in setup and test the downloaded artifact there.

List built-in target descriptors with `pipeline-build-targets list` (or `python -m pipeline.release.matrix_cli list --format json`). The catalogue includes Windows x86 (386), x86_64 and ARM64; Android `armeabi-v7a`, `arm64-v8a`, `x86` and `x86_64`; iOS device ARM64 and simulator ARM64/x86_64; plus PWA/web. These are target descriptors, not a promise that every project or hosted runner can build or execute every architecture without its required SDK, signing, or emulation toolchain.

The provider-neutral core also exposes the stages directly:

~~~sh
PYTHONPATH=.pipeline/src python -m pipeline.release.target_cli run \
  --target android-arm64-v8a --stage e2e-test \
  --target-os android --architecture arm64 --abi arm64-v8a --platform mobile
~~~

## Publish a rolling product prerelease

Use `.github/workflows/rolling-release.yml` when a project needs one mutable development channel for the newest fully verified `main` build. This is deliberately separate from both the immutable SemVer build-release workflow and the source-only contributor workflow.

The reusable workflow accepts the ID and SHA of an already successful `push` workflow run, downloads that run's artifacts, verifies that every required target/profile pair was built from the exact commit, and prepares a commit-qualified asset set. It then:

1. Serializes publication per repository with a non-cancelling concurrency group.
2. Confirms the source workflow run is successful, belongs to the caller repository, is a push to `main`, and identifies the supplied 40-character SHA.
3. Rechecks that the candidate is still the current `main` commit before promotion.
4. Verifies each package archive against its sidecar and package manifest, including source SHA, target, profile, size and SHA-256.
5. Uploads commit-qualified assets without replacing an existing same-name asset; a retry reuses an existing asset only when its size and SHA-256 are identical.
6. Uploads the commit-bound rolling manifest after the package assets and verifies the GitHub Release API inventory.
7. Advances the fixed `latest` tag, marks the Release as a prerelease, and only then removes older assets from this workflow's own `rolling-<product>-` namespace.

The manifest is the authoritative inventory. Consumers must use only the assets it lists, not every file that may temporarily be visible while a candidate is being staged. The asset filenames include the full source commit SHA so a retry is idempotent and a different commit never overwrites those bytes. If a newer commit reaches `main` while an older run is waiting or uploading, the older run stops before moving the tag. If publication is interrupted, rerunning the same source run verifies and reuses matching assets rather than replacing them.

A caller should trigger the reusable workflow only after its complete CI/native matrix **and product acceptance gates** have succeeded. Do not invoke the rolling product channel from a build-only or non-interactive smoke workflow. For example, this is the shape of a product-owned `workflow_run` orchestrator (the target list and artifact pattern belong to the caller):

~~~yaml
name: Rolling product prerelease

on:
  workflow_run:
    workflows: ["Product Acceptance"]
    types: [completed]
    branches: [main]

permissions:
  actions: read
  contents: read

jobs:
  rolling-release:
    if: >-
      github.event.workflow_run.event == 'push' &&
      github.event.workflow_run.conclusion == 'success' &&
      github.event.workflow_run.head_branch == 'main' &&
      github.event.workflow_run.head_repository.full_name == github.repository
    permissions:
      actions: read
      contents: write
    uses: m-mdy-m/pipeline/.github/workflows/rolling-release.yml@<pipeline-commit>
    with:
      pipeline-ref: <same-pipeline-commit>
      repository: ${{ github.repository }}
      source-run-id: ${{ github.event.workflow_run.id }}
      source-branch: ${{ github.event.workflow_run.head_branch }}
      source-sha: ${{ github.event.workflow_run.head_sha }}
      artifact-pattern: "cdin-installed-product-*"
      product-prefix: cdin
      expected-target-profiles: >-
        [{"target":"linux-x86_64","profile":"tui"},
         {"target":"linux-x86_64","profile":"gui-sdl"},
         {"target":"linux-arm64","profile":"tui"},
         {"target":"linux-arm64","profile":"gui-sdl"},
         {"target":"macos-x86_64","profile":"tui"},
         {"target":"macos-x86_64","profile":"gui-sdl"},
         {"target":"macos-arm64","profile":"tui"},
         {"target":"macos-arm64","profile":"gui-sdl"},
         {"target":"windows-x86_64","profile":"tui"},
         {"target":"windows-x86_64","profile":"gui-sdl"}]
    secrets:
      release-token: ${{ secrets.CDIN_RELEASE_TOKEN }}
~~~

The caller must grant `actions: read` for retrieving the successful run's artifacts and `contents: write` for the reusable publication job. The supplied release token must be permitted to create/update the `latest` ref and manage Release assets; do not put it in logs. Keep the called workflow's `@<pipeline-commit>` ref and its `pipeline-ref` input aligned to the same exact Pipeline commit, not a floating helper version.

The rolling channel always uses Git tag `latest` and `prerelease: true`. It is not GitHub's stable `/releases/latest` selector, not a SemVer component version, and must never be used as a Registry pin. Versioned product and component releases remain immutable tags such as `v1.1.1` or `v1.1.1-rc.1`.

## Try a build release without publishing

Set `dry-run: true` when calling the workflow. It still validates the tag or development version, runs tests and builds, collects assets, and creates checksums. It skips the GitHub Release publishing job.

The source package resolves one canonical `release_tag` in `release-meta.json`. A tag build keeps its validated tag (for example, `v1.2.3`); a branch dry-run gets a deterministic development tag such as `v0.0.0-dev.abcdef0`. The reusable workflow forwards that value as `PIPELINE_RELEASE_TAG` to each build command. Build scripts should use this value for artifact names rather than reading the CI branch name themselves.

The repository's `github-release-smoke.yml` workflow uses this mode on branch changes.

## Publish a source-only release

Use `source-release.yml` when you want a ZIP of the exact tagged source instead of compiled build files:

~~~yaml
name: Source release

on:
  push:
    tags: ["v*"]

permissions:
  contents: write

jobs:
  source:
    uses: m-mdy-m/pipeline/.github/workflows/source-release.yml@main
    with:
      pipeline-ref: main
      changelog-path: CHANGELOG.md
      changelog-missing-policy: fail
      source-archive-name: "{repository}-{tag}-source.zip"
      source-submodules: fail-if-present
~~~

The source workflow can include pinned submodule contents, omit submodules, or stop when submodules are present. Choose the behavior explicitly. It also checks sensitive paths, scans the published files with Gitleaks, validates the ZIP, and writes `manifest.json` and `SHA256SUMS`.

The optional `source-ref` input lets an orchestration workflow publish a tag that it created for a previously completed branch push. The helper checks out that exact tag and binds its provider-neutral context to the tag's commit before reading any source files. This keeps generated development releases attached to the commit that passed CI, rather than to the current default-branch head.

Use `dry-run: true` to test the packaging path without publishing.

## Version and changelog rules

Tags use this format:

- Stable: `vMAJOR.MINOR.PATCH`, for example `v1.1.1`.
- Prerelease: `vMAJOR.MINOR.PATCH-alpha.N`, `-beta.N`, or `-rc.N`.

- Development snapshots: `v0.0.0-dev.N`. CI assigns a unique numeric identifier to each successful pushed-branch run.

For a development tag, the source-release helper uses the exact `[Unreleased]` changelog section when present. If the project has no `[Unreleased]` section yet, it falls back to the newest version-specific section so the release still contains project-authored notes.

Before creating a stable tag, add a matching heading to the changelog:

~~~markdown
## [1.1.1] - 2026-10-30

### Added

- Describe what is new.
~~~

A stable release without its matching changelog section is rejected. Release notes preserve the selected section and all of its categories (for example `Added`, `Changed`, `Fixed`, `Performance`, and `Documentation`); the release workflow does not flatten them into a generic bullet list. Prerelease builds and dry-runs prefer the `[Unreleased]` section. For source-release branch dry-runs, when `[Unreleased]` is absent, the helper uses the newest version-specific section as informational release notes.

## Permissions and secrets

The job that calls `release.yml` must grant the permissions needed by its nested jobs:

~~~yaml
jobs:
  release:
    uses: m-mdy-m/pipeline/.github/workflows/release.yml@main
    permissions:
      contents: write
      id-token: write
      attestations: write
~~~

All three permissions are required when calling this reusable workflow. GitHub validates the permissions of nested jobs while resolving the reusable workflow, before evaluating job-level `if` conditions. Consequently, `id-token: write` and `attestations: write` must be granted even when `sign-assets` and `attest-release` are left at their default `false` values and the `sign-and-attest` job is skipped. Those two permissions are used only when signing or provenance attestation is enabled. The `contents: write` permission is used by the publishing job to create the GitHub Release.

The source-only `source-release.yml` workflow does not create an OIDC-backed attestation and needs only `contents: write` on its calling job.

The default `GITHUB_TOKEN` is enough for ordinary GitHub Releases. However, GitHub requires the authenticating token to have **Workflows: write** when the release/tag points to a commit that adds or changes files under `.github/workflows/` relative to the repository's default branch; the Actions `GITHUB_TOKEN` cannot be granted that permission. For those cases, pass the optional `release-token` secret: use a fine-grained token with `Contents: Read and write` and `Workflows: Read and write`. The source-release workflow uses it for the tag-backed release operation. Projects whose mobile build commands require an application endpoint may pass it through the optional `mobile-server-url` secret; the reusable workflow exposes it to project commands as `IDIOS_MOBILE_SERVER_URL` and never commits the endpoint. Source releases need `submodule-token` only when they must read private GitHub submodules.

Do not put tokens in `pipeline.toml`, command strings, or committed workflow files.
