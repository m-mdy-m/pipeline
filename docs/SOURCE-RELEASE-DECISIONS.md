# Source Release: decisions and rationale

This document records the Source Release contract for `m-mdy-m/pipeline`. It distinguishes requirements explicitly chosen in the discussion from implementation defaults selected to close remaining gaps safely.

## Requirements explicitly selected

| Area | Decision |
| --- | --- |
| Release type | Source-only release is a distinct reusable workflow, not a variation of the existing multi-platform build release. Each project chooses its asset layout. |
| ZIP filename | Caller-configurable `source-archive-name` template; supports `{repository}`, `{tag}`, and `{version}`. |
| Changelog selection | An explicit `changelog-path` checks only that path. Without it, automatic discovery must find exactly one candidate or fail on zero/multiple matches. |
| Missing/empty changelog | Configurable workflow policy; an empty file follows the same policy as a missing file. |
| Changelog syntax | Several documented common heading forms are supported. A non-empty changelog for a real tag must have the exact matching version section. |
| Release notes | Extract only the current version's section by default. |
| Changelog asset layout | Configurable `archive-only`, `archive-and-asset`, or `asset-only`. |
| Snapshot basis | Files tracked by the exact Git tag commit only, including tracked hidden files; no untracked, ignored, or transient CI workspace files. |
| `.git` data | Always excluded from the published ZIP. An attempted tracked `.git` path is treated as an invalid layout and fails rather than being silently discarded. |
| Submodules | Per-project setting required. |
| Exclusions | Newline-separated configurable patterns; no silent deletion of paths. Excluded paths are reported. |
| Secret findings | Block publication unless an explicitly approved allowlist covers the finding. |
| Sensitive paths | Built-in plus configurable patterns; a match blocks with a report, and files are not removed automatically. |
| ZIP layout | One top-level directory, e.g. `repository-v1.2.3/`. |
| ZIP validation | Validate CRC, path containment, traversal, duplicate names, `.git` absence, and changelog-mode consistency; any violation blocks publication. |

## Additional implementation decisions

| Decision | Implementation choice | Why |
| --- | --- | --- |
| Stable and prerelease tags | Accept `vMAJOR.MINOR.PATCH` and `vMAJOR.MINOR.PATCH-(alpha, beta, or rc).N`. Real tags must point to the exact event commit. | Avoid ambiguous version formats or packaging a different commit than the release tag. |
| Branch dry-run | Use `0.0.0-dev.<short-sha>` and, if no exact synthetic-version section exists, use `Unreleased` only for a branch smoke run. A real tag always requires the exact version heading. | Lets CI exercise packaging without relaxing the real release contract. |
| Changelog missing policy values | `fail` or `warn`; `fail` is the default. With `warn`, a missing/blank changelog yields generated generic notes. `asset-only` still requires a non-empty changelog. | A requested separate changelog asset cannot be supplied when no source file exists. |
| Candidate filenames | Auto-detect only `CHANGELOG`, `CHANGELOG.md`, `CHANGELOG.txt`, and their `docs/` equivalents. Symlink changelog candidates are rejected. | A small deterministic set avoids unexpectedly selecting unrelated documents. |
| Heading variants | Recognize semver forms with optional `v`, brackets, date suffix, and common `Version`/`Release` prefixes, including markdown heading forms. Duplicate exact-version headings fail. | Balances compatibility with a deterministic parser. |
| Source archive root name | Use `<repository>-<tag>` independently of the ZIP filename. | Stable and readable root path in downstream extractions. |
| Filename safety | Result must be a `.zip` basename matching a conservative portable-character set; unknown placeholders and path separators fail. | Avoids traversal and cross-platform extraction ambiguity. |
| Exclusion matching | Standard glob-style matching, comments/blank lines ignored, negative (`!`) patterns rejected. | Prevents order-dependent include/exclude behavior. Explicit sensitive-path exceptions use a separate allowlist input. |
| Default sensitive names | Fail for common `.env*`, private key/certificate extensions, SSH private-key names, credential/service-account filenames, and `secrets.*`; common `.env.example`, `.env.sample`, `.env.template`, `.env.dist` are allowed by default. | Useful baseline with an explicit escape hatch for safe sample configs. These checks complement, not replace, content scanning. |
| Secret scanner | Gitleaks `v8.30.1` directory mode scans the staged files that will be published, with redaction enabled. Default rules cannot be replaced through the allowlist input. | Scans the actual asset rather than historical commits and avoids unreviewed configuration silently disabling the detector. |
| Gitleaks allowlist | Optional tracked TOML file accepts allowlist tables only; all other config fields are rejected, then the input is composed with embedded default rules. | A specific, reviewable exception without allowing a custom file to redefine the detector. |
| Path-sensitive allowlist | Built-in and custom sensitive path patterns can be excepted through a separate explicit pattern input; it never bypasses Gitleaks findings. | Keeps path naming exceptions independent from secret-content exceptions. |
| Submodule default | `fail-if-present`. `recursive` exports the exact SHA pinned by each parent and fails on access/missing-commit errors; `omit` skips with a warning. Maximum recursive nesting is 16 levels. | Fails closed unless the maintainer has intentionally selected a policy. |
| Private submodules | Optional `submodule-token` secret; token-based rewrite is scoped to HTTPS GitHub URLs and never printed by the workflow. | Supports private GitHub modules without hard-coding credentials. Keep the token read-only and narrowly scoped. |
| Symlinks | Preserve only relative links that resolve inside the emitted tree. Reject absolute, escaping, broken, cyclic, and platform-ambiguous targets. | Prevents an archive from exposing runner files or behaving differently across extraction tools. |
| Supported file modes | Only regular blobs and symlinks are packaged. Unsupported Git tree modes fail. Executable bits are preserved; archive timestamps are normalized. | Predictable cross-platform artifacts and fewer surprising extraction behaviors. |
| Asset list | ZIP, optional separate original changelog, `manifest.json`, and `SHA256SUMS`; release notes are used as the body but not attached as an asset. | Keeps the public asset list compact and machine-verifiable. |
| Manifest | Include the source commit, tag/version, ZIP root/name, archive SHA-256, file count, changelog mode, submodule mode, and excluded/omitted counts. | Captures enough provenance and policy metadata to inspect the artifact later. |
| Publication | Package and scan before publish; separate publish job has `contents: write`. Refuse an existing Release and set `overwrite_files: false`. | Makes all validation fail-closed and avoids accidental replacement of an existing published asset. |
| Reusable workflow versioning | `pipeline-ref` defaults to `main`; callers pin both workflow reference and helper-code reference to the same tag/SHA. Self-smoke passes the active branch. | A reusable workflow cannot dynamically infer the exact source repository ref used to load its own workflow file, so the helper ref is made explicit rather than silently drifting. |
| Build artifacts | No compilation, tests, platform matrices, Docker, npm, or Pages publishing in Source Release. | Keeps this workflow purpose-specific; use the existing reusable build release for binary artifacts. |

## Known limitations

- Gitleaks is heuristic: a clean scan is not a guarantee that every secret was detected. Keep project-specific scanning and human review for sensitive repositories.
- Recursive private submodules must be reachable from the runner. The optional token currently supports HTTPS URLs on `github.com`; custom hosts or SSH-only URLs need project-specific credentials.
- ZIP and manifest generation targets a Linux GitHub-hosted runner for consistent path and permission handling.
- The workflow refuses to overwrite a release it can already see. As with any separate API pre-check, a race with another independently running publisher cannot be made fully atomic; the pre-check plus `overwrite_files: false` reduces that risk.
- Asset checksums are integrity checks, not cryptographic publisher signatures. Add signing/attestation if a project's threat model requires authenticity beyond GitHub's release permissions.
