# Examples

These examples are small starting points. Copy the file you need into your project, then change the task names and commands to match that project.

| File | Use it for |
|---|---|
| [`pipeline.toml`](pipeline.toml) | A tiny task graph with one dependency |
| [`github-actions.yml`](github-actions.yml) | Running a project's task graph from GitHub Actions |
| [`gitlab-ci.yml`](gitlab-ci.yml) | Running a project's task graph from GitLab CI |
| [`docker-sdk-caller.yml`](docker-sdk-caller.yml) | Calling the reusable Docker SDK publishing workflow |

The CI examples check out the shared scripts at `v1.0.0`. For another release, use the same reviewed tag in the helper checkout and in any reusable workflow reference.
