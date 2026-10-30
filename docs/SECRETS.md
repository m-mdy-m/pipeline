# Secrets and permissions

Some workflows publish files to GitHub Releases, Docker Hub, or npm. These services require credentials called **secrets**. Keep those credentials in repository or organization settings, never in a workflow file or source code.

## Safe handling

- Give each token only the permissions it needs.
- Never print a secret in a log.
- Pass a secret only to the job that uses it.
- Use the built-in repository token when it has enough access.
- Review the permissions requested by the caller workflow as well as the reusable workflow.

## Which secret is used?

| Workflow | Secret input | Example caller secret | Purpose |
| --- | --- | --- | --- |
| Build release | `release-token` (optional) | `RELEASE_TOKEN` | Optional token for publishing a GitHub Release |
| Docker Hub | `username` and `token` | `DOCKERHUB_USERNAME`, `DOCKERHUB_TOKEN` | Authenticate before pushing an image |
| npm | `npm-token` | `NPM_TOKEN` | Publish a package |
| Source release | `submodule-token` (optional) | `SUBMODULE_TOKEN` | Read private GitHub submodules when recursive mode is enabled |

Example:

~~~yaml
jobs:
  publish:
    uses: m-mdy-m/pipeline/.github/workflows/docker-publish.yml@main
    with:
      image: owner/project
    secrets:
      username: ${{ secrets.DOCKERHUB_USERNAME }}
      token: ${{ secrets.DOCKERHUB_TOKEN }}
~~~

## Choose the smallest permissions

The caller workflow must allow the permissions required by the reusable workflow. A called workflow cannot grant itself more access than the caller permits.

- Checks and benchmarks normally need `contents: read`.
- Publishing a GitHub Release needs `contents: write`.
- GitHub Pages deployment needs `pages: write` and `id-token: write`.

The reusable workflow's publishing job requests write access only for the step that publishes. Keep other jobs read-only.
