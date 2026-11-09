# OCI packages and GitHub Container Registry

Pipeline can prepare deterministic package metadata, verify package bytes, and publish a package as an OCI artifact. The shared implementation lives in `src/pipeline/oci/`; GitHub Actions supplies the runner, short-lived `GITHUB_TOKEN`, and GHCR transport through ORAS.

This is package distribution, not Docker image construction. A package can be a tarball containing a native library, public headers, CMake exports, Lua modules, SDK files, or another project-defined install layout.

## Responsibilities

- The component repository owns its package contents, tests, version, source revision, target matrix, and release lifecycle.
- Pipeline validates package identity, records target and source provenance, calculates byte size and SHA-256, and verifies the payload against the descriptor.
- The GitHub reusable workflow uses ORAS to publish the payload and metadata to GHCR.
- OCI tags are discovery aliases. The registry manifest digest is the immutable package identity and is recorded in the publication receipt.
- A consumer such as Registry resolves the package from its own catalog/metadata contract, pulls by digest, and verifies the package before staging it. Pipeline does not own CDIN Product Definitions or component dependency resolution.

## Package descriptor

The `pipeline-oci prepare` command requires exactly one regular file. It rejects missing/ambiguous globs, symbolic links, non-regular files, non-SemVer versions, incomplete Git object IDs, and non-HTTPS source repository URLs.

Example:

~~~sh
python -m pipeline.oci.cli prepare \
  --artifact dist/kernel-linux-amd64.tar.gz \
  --output-directory .pipeline/oci \
  --package-name kernel \
  --component-id kernel \
  --version 1.2.1 \
  --source-repository https://github.com/cdin-editor/kernel \
  --source-revision "$GITHUB_SHA" \
  --target-id linux-amd64 \
  --target-os linux \
  --architecture x86_64 \
  --abi gnu
~~~

It writes `.pipeline/oci/package-metadata.json` with:

- Component ID and variant.
- Package name, SemVer version, and target-specific tag.
- Exact source repository and full Git commit.
- Target ID, OS, architecture, and ABI.
- Payload filename, media type, byte size, and SHA-256.

Verify the local package before publishing:

~~~sh
python -m pipeline.oci.cli verify \
  --metadata .pipeline/oci/package-metadata.json \
  --artifact dist/kernel-linux-amd64.tar.gz
~~~

For a multi-target release, each target produces its own descriptor and tag. The default tag form is `<version>-<target-id>`; a universal target (`any/any/none`) uses the version without a target suffix. OCI tags are not the integrity boundary: consumers must record the returned manifest digest.

## Publish to GHCR

Call the reusable workflow from the component repository. The component's own build command is responsible for creating one installable archive at the configured path.

~~~yaml
name: Publish Kernel package

on:
  push:
    tags: ["v*"]

permissions:
  contents: read

jobs:
  package:
    uses: m-mdy-m/pipeline/.github/workflows/oci-publish.yml@main
    permissions:
      contents: read
      packages: write
    with:
      pipeline-ref: main
      package-name: kernel
      component-id: kernel
      variant: default
      build-command: make package
      artifact-path: dist/kernel-*.tar.gz
      build-matrix-json: >-
        {"include":[
          {"id":"linux-amd64","os":"ubuntu-24.04","target_os":"linux","architecture":"x86_64","abi":"gnu"},
          {"id":"linux-arm64","os":"ubuntu-24.04-arm","target_os":"linux","architecture":"aarch64","abi":"gnu"},
          {"id":"darwin-arm64","os":"macos-15","target_os":"macos","architecture":"arm64","abi":"none"},
          {"id":"windows-amd64","os":"windows-2025","target_os":"windows","architecture":"x86_64","abi":"ucrt64","msys2_msystem":"UCRT64","msys2_packages":"mingw-w64-ucrt-x86_64-gcc make","shell":"msys2 {0}"}
        ]}
~~~

The Git tag `v1.2.1` supplies package version `1.2.1`. Each matrix job must create exactly one archive matching `artifact-path`; projects with different output names can override `artifact_path` per matrix entry.

For a no-publish test, call the workflow with `dry-run: true` and an explicit `version`. It still validates the matrix, runs tests/build, prepares metadata, verifies package bytes, and can run `artifact-test-command`; it does not log in or push to GHCR.

The publishing job requires `packages: write`. The workflow adds the standard `org.opencontainers.image.source`, `revision`, `version`, and `title` annotations so the GHCR package can be associated with its source repository. The resulting package appears under the repository owner's GitHub Packages. Repository/package visibility and access are still governed by GitHub's package permissions.

## Immutable publication receipt and round-trip

After ORAS pushes a package, Pipeline validates the ORAS JSON result and creates a receipt containing:

- The human-readable GHCR tag reference.
- The immutable `ghcr.io/<owner>/<package>@sha256:<manifest-digest>` reference.
- Component, variant, source revision, target, payload size, and payload SHA-256.
- The OCI artifact type.

The workflow then pulls the package again by that immutable digest and verifies the downloaded payload against the original descriptor. The receipt is uploaded as a GitHub Actions workflow artifact for catalog/release automation.

A tag is useful for discovery, but never use `latest` or a mutable tag as the authoritative identity in a product lock or Registry Manifest. Store the exact OCI digest and the package metadata identity.

## Security and boundaries

- Package creation and package verification are provider-neutral Python code. GHCR credentials and ORAS network operations stay in the GitHub workflow.
- The workflow only publishes on a `v*` tag unless `dry-run` is explicitly enabled.
- The package path must resolve to exactly one regular file. The descriptor stores its size and SHA-256.
- The publication receipt must match the digest and tag returned by ORAS.
- The downloaded package is checked again after the registry round-trip.
- A SHA-256 proves byte equality with the recorded descriptor; it does not independently authenticate who produced the descriptor. Use protected release workflows, reviewed source revisions, GitHub attestations/signing policy, and trusted Registry metadata for publisher authenticity.
- The package archive's internal layout and extraction safety remain the responsibility of the consumer's installer/Registry. A valid outer archive checksum does not make unsafe archive paths safe.

## Commands

~~~sh
# Prepare descriptor
python -m pipeline.oci.cli prepare --help

# Verify local package bytes
python -m pipeline.oci.cli verify --help

# Validate a release target matrix
python -m pipeline.oci.cli validate-matrix --value '{"include":[{"id":"linux-amd64","os":"ubuntu-24.04","target_os":"linux","architecture":"x86_64","abi":"gnu"}]}'

# Validate a version
python -m pipeline.oci.cli validate-version --value 1.2.1

# Validate the ORAS push result and produce a digest receipt
python -m pipeline.oci.cli receipt --help
~~~
