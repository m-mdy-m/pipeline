# Secrets and permissions

Configure registry credentials in GitHub Actions settings or organization secrets. Never commit tokens or include them in workflow YAML.

| Reusable workflow secret input | Map from caller secret | Purpose |
| --- | --- | --- |
| release-token (optional) | RELEASE_TOKEN (optional) | Release creation; otherwise the caller's GITHUB_TOKEN is used |
| username | DOCKERHUB_USERNAME | Docker Hub login |
| token | DOCKERHUB_TOKEN | Docker Hub access token |
| npm-token | NPM_TOKEN | npm publishing token |

Example mapping for Docker Hub:

~~~yaml
jobs:
  publish:
    uses: m-mdy-m/pipeline/.github/workflows/docker-publish.yml@main
    with:
      image: owner/project-sdk
      dockerfile: Dockerfile.sdk
      sdk-image: true
    secrets:
      username: ${{ secrets.DOCKERHUB_USERNAME }}
      token: ${{ secrets.DOCKERHUB_TOKEN }}
~~~

Keep permissions narrow. CI and benchmark callers typically need only contents: read; GitHub Release needs contents: write; Pages deployment needs pages: write and id-token: write. The calling workflow must grant the permissions required by a reusable workflow; a called workflow cannot elevate the caller's token permissions.
