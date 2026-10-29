# Secrets and permissions

Some workflows need passwords or tokens to publish a package or release. These are called **secrets**.

## Keep secrets private

- Add secrets in your repository or organization settings.
- Never put a real token in a workflow file, source file, or commit.
- Give each token only the access it needs.
- Do not print secrets in logs.

A workflow can pass a secret to a reusable workflow by mapping it under `secrets:`.

## Which secret is used?

| Workflow | Secret input | Common caller secret | What it is for |
| --- | --- | --- | --- |
| GitHub Release | `release-token` (optional) | `RELEASE_TOKEN` | Optional token for creating a release |
| Docker Hub | `username` and `token` | `DOCKERHUB_USERNAME`, `DOCKERHUB_TOKEN` | Login before pushing an image |
| npm | `npm-token` | `NPM_TOKEN` | Publish a package to npm |
| Source release | `submodule-token` (optional) | `SUBMODULE_TOKEN` | Read private GitHub submodules when recursive mode is enabled |

Example:

```yaml
jobs:
  publish:
    uses: m-mdy-m/pipeline/.github/workflows/docker-publish.yml@main
    with:
      image: owner/project
    secrets:
      username: ${{ secrets.DOCKERHUB_USERNAME }}
      token: ${{ secrets.DOCKERHUB_TOKEN }}
```

## Permissions matter too

The caller workflow must allow the permissions that a job needs. Use the smallest set possible:

- Normal checks and benchmarks usually need `contents: read`.
- Publishing a GitHub Release needs `contents: write`.
- GitHub Pages deployment needs `pages: write` and `id-token: write`.

A reusable workflow cannot grant its caller a higher permission level than the caller allows.
