# Why source releases have safety checks

A source ZIP should contain only the files a project meant to publish. It should not contain Git history, temporary CI files, private keys, or credentials.

The reusable rules live in `scripts/pipeline_release/`. The GitHub workflow supplies the tag context, runs the scanner, transfers the resulting files, and publishes the release.

## Rules used by the source packager

- **Use the exact tag snapshot.** The archive is made from files tracked by the tagged commit, not from whatever happens to be in the CI working directory.
- **Keep one project folder at the top of the ZIP.** This makes the archive easier to extract.
- **Do not include Git internals.** A source archive must not contain repository history or metadata.
- **Make submodule behavior explicit.** The workflow can stop when submodules exist, include their pinned contents, or omit them.
- **Show exclusions.** When a project excludes tracked files, the logs list those paths.
- **Check sensitive paths and file contents.** Likely credentials and private material stop the release unless a narrow, explicit exception applies.
- **Validate the finished ZIP.** The helper checks path traversal, duplicate entries, unsafe paths, and archive layout.
- **Require stable-release notes.** A stable tag must have a matching changelog section unless the caller has deliberately selected a warning policy where permitted.

## Why source and build releases are separate

A build release runs project-specific test and build commands and collects the generated outputs. A source release packages a tagged source snapshot and checks what will be published.

Keeping these paths separate makes each release type easier to understand and reduces the chance of publishing the wrong files.

These checks lower risk, but they do not prove that every file is safe. Review the final archive and every allowlist exception before publishing.
