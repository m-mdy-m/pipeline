# Why source releases have safety checks

This page explains the main decisions behind the source ZIP workflow. The full implementation is in `scripts/pipeline_release/` and `scripts/source_release.py`.

## The goal

A source release should contain the files a project intended to publish—no temporary CI files, no Git history, and no accidentally included credentials.

## Rules we chose

- **Use the exact tag snapshot.** The archive is made from files tracked by the tagged commit, not whatever happens to be in the CI working directory.
- **Keep one project folder at the top of the ZIP.** This makes the archive easier to extract and avoids scattering files into the destination directory.
- **Do not include Git internals.** A source archive must not contain the repository's `.git` data.
- **Make submodule behavior explicit.** The workflow can stop if submodules exist, include their pinned contents, or omit them. It never silently guesses.
- **Make exclusions visible.** If a project asks to exclude files, the logs show which tracked paths were left out.
- **Stop on likely secrets or sensitive paths.** The workflow scans the actual files that would be published and checks file names and paths. Approved exceptions must be explicit.
- **Validate the finished ZIP.** The workflow checks for broken archives, duplicate paths, path traversal, and invalid layout before publishing.
- **Require a matching changelog for stable tags by default.** This keeps the published version and release notes aligned.

## Why separate source and build releases?

A build release runs project-specific test/build commands and collects output for configured targets. A source release packages a tagged source snapshot and checks its contents. Keeping them separate makes each workflow easier to understand and reduces the chance of publishing the wrong files.

These checks reduce risk, but they do not guarantee that every project file is safe. Review the archive and any allowlist exceptions before publishing.
