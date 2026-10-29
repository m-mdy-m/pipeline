# Release lifecycle

1. CI validates the candidate on pull requests and pushes.
2. Use `gix release start <version>` from `develop`.
3. Update changelog and version metadata; run tests and relevant benchmarks.
4. Finish the release branch and create an annotated version tag according to gix configuration.
5. Tag-triggered release workflows build artifacts, checksums, and publish only the explicitly configured registries.
6. Verify GitHub Release assets, Docker image tags, npm dist-tags, and deployment status after publication.

Prerelease tags must not be promoted to Docker `latest` or npm `latest`.
