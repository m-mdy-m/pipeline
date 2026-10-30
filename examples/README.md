# Examples

These examples are small starting points. Copy the file you need into your project, then change the task names and commands to match that project.

| File | Use it for |
| --- | --- |
| [`pipeline.toml`](pipeline.toml) | A tiny task graph with one dependency |
| [`github-actions.yml`](github-actions.yml) | Running a project's task graph from GitHub Actions |
| [`gitlab-ci.yml`](gitlab-ci.yml) | Running a project's task graph from GitLab CI |
| [`docker-sdk-caller.yml`](docker-sdk-caller.yml) | Calling the reusable Docker SDK publishing workflow |

The CI examples check out the shared package from `main`. For repeatable project builds, replace `main` with a reviewed release tag or full commit SHA in both the helper checkout and reusable workflow reference.
