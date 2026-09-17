.DEFAULT_GOAL := help

UV := uv run --extra dev
QUIET := sh scripts/quiet_step.sh$(if $(VERBOSE), --verbose)
PYTEST_QUIET := $(if $(VERBOSE),,-x --tb=short --no-header)
# IfcOpenShell's geometry layer can terminate xdist workers under concurrent
# tessellation. The suite is small enough to favor deterministic serial runs.
PYTEST_WORKERS ?= 0
SUITE_BUDGET ?= 420
BUDGET := timeout --foreground

.PHONY: help sync-dev ensure-dev-deps test check check-fix check-ship build check-dist \
	publish-test publish publish-local uvx-info bump-patch clean

help: ## Show this help.
	@awk 'BEGIN{FS=":.*## "} /^[a-zA-Z0-9_-]+:.*## / {printf "  \033[36m%-20s\033[0m %s\n", $$1, $$2}' $(MAKEFILE_LIST)

sync-dev: ## Install the locked development toolchain.
	uv sync --extra dev

ensure-dev-deps:
	@$(UV) python -c "import pytest_timeout" >/dev/null

test: ensure-dev-deps ## Run the test suite.
	$(UV) pytest -q -n $(PYTEST_WORKERS)

check: ensure-dev-deps ## Run the complete read-only quality gate.
	@$(QUIET) file-sizes $(UV) python scripts/check_file_sizes.py
	@$(QUIET) ruff $(UV) ruff check src tests scripts
	@$(QUIET) ruff-format $(UV) ruff format --check src tests scripts
	@$(QUIET) mypy $(UV) mypy src
	@$(QUIET) vulture $(UV) vulture
	@$(QUIET) deptry $(UV) deptry .
	@$(QUIET) bandit $(UV) bandit -q -r src scripts
	@$(QUIET) pytest $(BUDGET) $(SUITE_BUDGET) $(UV) pytest -q $(PYTEST_QUIET) -n $(PYTEST_WORKERS)

check-fix: ensure-dev-deps ## Format, lint, and run the complete quality gate.
	@$(QUIET) file-sizes $(UV) python scripts/check_file_sizes.py --fix
	@$(QUIET) ruff $(UV) ruff check --fix src tests scripts
	@$(QUIET) ruff-format $(UV) ruff format src tests scripts
	@$(QUIET) mypy $(UV) mypy src
	@$(QUIET) vulture $(UV) vulture
	@$(QUIET) deptry $(UV) deptry .
	@$(QUIET) bandit $(UV) bandit -q -r src scripts
	@$(QUIET) pytest $(BUDGET) $(SUITE_BUDGET) $(UV) pytest -q $(PYTEST_QUIET) -n $(PYTEST_WORKERS)

check-ship: check-fix build check-dist ## Validate source, tests, and release artifacts.

build: ensure-dev-deps ## Build wheel and source distributions.
	$(UV) python -m build

check-dist: ensure-dev-deps ## Validate the current version's distributions.
	@version="$$(python -c 'import tomllib; print(tomllib.load(open("pyproject.toml", "rb"))["project"]["version"])')"; \
	$(UV) twine check "dist/ifc_mcp-$$version-py3-none-any.whl" "dist/ifc_mcp-$$version.tar.gz"

publish-test: check-ship ## Publish the current version to TestPyPI.
	@version="$$(python -c 'import tomllib; print(tomllib.load(open("pyproject.toml", "rb"))["project"]["version"])')"; \
	$(UV) twine upload --repository testpypi "dist/ifc_mcp-$$version-py3-none-any.whl" "dist/ifc_mcp-$$version.tar.gz"

publish: check-ship ## Publish the current version to PyPI.
	@version="$$(python -c 'import tomllib; print(tomllib.load(open("pyproject.toml", "rb"))["project"]["version"])')"; \
	$(UV) twine upload "dist/ifc_mcp-$$version-py3-none-any.whl" "dist/ifc_mcp-$$version.tar.gz"

bump-patch: ## Increment the project patch version.
	python -c "from pathlib import Path; import re; p=Path('pyproject.toml'); s=p.read_text(); m=re.search(r'^version\s*=\s*\"(\d+)\.(\d+)\.(\d+)\"\s*$$', s, re.M); assert m, 'Could not find project version in pyproject.toml'; major, minor, patch = map(int, m.groups()); new=f'{major}.{minor}.{patch+1}'; p.write_text(s[:m.start()] + f'version = \"{new}\"' + s[m.end():]); print(f'Bumped version: {major}.{minor}.{patch} -> {new}')"

publish-local: ## Install this checkout as the uv tool.
	uv tool install --editable . --force

uvx-info: ## Run `ifc-mcp info`; pass FILE=/path/to/model.ifc.
	uvx --from . ifc-mcp info $(FILE)

clean: ## Remove package build outputs.
	rm -rf build dist *.egg-info
