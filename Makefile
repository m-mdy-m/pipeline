.PHONY: check docs-check yaml-check

check: docs-check yaml-check

docs-check:
	@test -s README.md
	@test -s LICENSE
	@test -s docs/WORKFLOWS.md
	@test -s docs/SECRETS.md

yaml-check:
	@python -c "import pathlib; files=list(pathlib.Path('.github/workflows').glob('*.yml')); assert files, 'no workflows'; print(f'{len(files)} workflow files found; install yamllint/actionlint for full syntax checks')"
