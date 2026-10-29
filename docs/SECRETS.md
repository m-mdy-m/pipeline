# Secrets and permissions

Configure secrets only in GitHub Actions settings. Never commit tokens.

| Secret | Used by | Notes |
|---|---|---|
| `DOCKERHUB_USERNAME` | Docker publish | Docker Hub account or robot user |
| `DOCKERHUB_TOKEN` | Docker publish | Access token with minimum required permissions |
| `NPM_TOKEN` | npm publish | Prefer npm trusted publishing/OIDC where available |
| `GITHUB_TOKEN` | GitHub Release / Pages | Provided by Actions; grant only required permissions |

Workflows should use read-only permissions by default. Grant `contents: write` only to release jobs, `packages: write` only where needed, and `pages: write` plus `id-token: write` only to Pages deployment jobs.
