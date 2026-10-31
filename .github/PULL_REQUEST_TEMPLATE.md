<!-- Keep the PR focused. Remove sections that do not apply; never mark a check as passed unless it ran. -->

# Pull Request

## Summary

<!-- User-visible outcome and reason. -->
Closes #

## Change type

- [ ] Bug fix
- [ ] Feature
- [ ] Refactor
- [ ] Documentation / CI
- [ ] Breaking change

## Implementation

- [ ] Runtime behavior lives in `src/pipeline/`
- [ ] GitHub/GitLab files only orchestrate runners, credentials, caches, artifacts, or publishing
- [ ] Public CLI/configuration contracts are documented
- [ ] CHANGELOG updated

## Trigger and publication policy

- [ ] Every branch push validates with `dry-run: true`
- [ ] Only version-tag pushes use `dry-run: false`
- [ ] Branch filters and tag filters are separate; a tag cannot enter a branch dry-run
- [ ] Release secrets are injected only into the matching production build step

## Native store signing (when applicable)

- [ ] Android production artifact is a signed AAB
- [ ] iOS production artifact is an App Store signed IPA
- [ ] Store signing keys and profiles remain in CI secrets
- [ ] Store metadata, bundle ID, versioning, SDK and signing have been validated

## Build targets and E2E (when applicable)

- Target IDs / OS / architectures:
- Runner OS / architecture:
- Toolchains / SDKs / signing requirements:
- Artifact format and output path:
- E2E setup command:
- E2E test command:
- Device / simulator / emulator used:
- Are the downloaded artifacts tested on the same target runner? Explain any emulation.

## Validation

- [ ] `python -m compileall -q src`
- [ ] `python -m unittest discover -s tests -p "test_*.py" -v`
- [ ] `make check`
- [ ] Reusable workflow smoke test
- [ ] Native artifact test
- [ ] E2E test
- [ ] Documentation / Markdown validation

Paste actual commands and results:

```text

```

## Risk and rollback

- Impact: low / medium / high
- Compatibility or migration notes:
- Rollback:

## Reviewer notes

<!-- Key files, known limitations, untested runner/toolchain combinations. -->
