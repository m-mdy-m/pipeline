# Examples

These examples are small starting points. Copy the file you need into your project, then change the task names and commands to match that project.

| File | Use it for |
| --- | --- |
| [`pipeline.toml`](pipeline.toml) | A tiny task graph with one dependency |
| [`github-actions.yml`](github-actions.yml) | Running a project's task graph from GitHub Actions |
| [`gitlab-ci.yml`](gitlab-ci.yml) | Running a project's task graph from GitLab CI |
| [`docker-sdk-caller.yml`](docker-sdk-caller.yml) | Calling the reusable Docker SDK publishing workflow |
| [`github-toolchain.yml`](github-toolchain.yml) | Running install, lint, build and test for a project in any supported language on every push |
| [`gitlab-toolchain.yml`](gitlab-toolchain.yml) | The same language presets from GitLab CI |
| [`projects/`](projects/) | A `pipeline.ci.toml` and workflow for each of the maintainer's repositories |
| [`toolchains/`](toolchains/) | Tiny complete projects (Python, Node.js, Go, Rust, Java, .NET, C, Vim, Docker) used to test every preset on every push |

The CI examples check out the shared package from `main`. For repeatable project builds, replace `main` with a reviewed release tag or full commit SHA in both the helper checkout and reusable workflow reference.
