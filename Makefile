.PHONY: check docs-check workflow-inventory pipeline-config-check source-release-tests

check: docs-check workflow-inventory pipeline-config-check source-release-tests

docs-check:
	@test -s README.md
	@test -s LICENSE
	@test -s CHANGELOG.md
	@test -s docs/WORKFLOWS.md
	@test -s docs/SECRETS.md
	@test -s docs/BENCHMARKS.md
	@test -s docs/RELEASES.md
	@test -s docs/SOURCE-RELEASES.md
	@test -s docs/SOURCE-RELEASE-DECISIONS.md

workflow-inventory:
	@python -c "import pathlib; files=list(pathlib.Path('.github/workflows').glob('*.yml')); required={'ci-main.yml','ci.yml','docs-check.yml','benchmark.yml','benchmark-self.yml','release.yml','github-release-smoke.yml','source-release.yml','source-release-smoke.yml','docker-publish.yml','npm-publish.yml','pages.yml'}; missing=required-{p.name for p in files}; assert not missing, f'missing workflow files: {sorted(missing)}'; print(f'workflow inventory OK: {len(files)} executable workflows found')"

pipeline-config-check:
	@python scripts/pipeline.py validate --json

source-release-tests:
	@python scripts/pipeline.py run test --json
