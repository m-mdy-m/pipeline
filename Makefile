.PHONY: check docs-check workflow-inventory pipeline-config-check pipeline-tests

check: docs-check workflow-inventory pipeline-config-check pipeline-tests

docs-check:
	@test -s README.md
	@test -s LICENSE
	@test -s CHANGELOG.md
	@test -s pyproject.toml
	@test -s docs/index.md
	@test -s docs/getting-started.md
	@test -s docs/configuration.md
	@test -s docs/design.md
	@test -s docs/providers.md
	@test -s docs/benchmarking.md
	@test -s docs/releases.md
	@test -s docs/development.md
	@test -s examples/README.md

workflow-inventory:
	@python -c "import pathlib; files=list(pathlib.Path('.github/workflows').glob('*.yml')); required={'ci-main.yml','ci.yml','docs-check.yml','benchmark.yml','benchmark-matrix.yml','benchmark-self.yml','release.yml','release-on-tag.yml','github-release-smoke.yml','source-release.yml','source-release-smoke.yml','docker-publish.yml','npm-publish.yml','pages.yml','python-publish.yml','security-check.yml','reusable-smoke.yml'}; missing=required-{p.name for p in files}; assert not missing, f'missing workflow files: {sorted(missing)}'; print(f'workflow inventory OK: {len(files)} workflows found')"

pipeline-config-check:
	@PYTHONPATH=src python -m pipeline validate --json

pipeline-tests:
	@PYTHONPATH=src python -m pipeline run test --json
