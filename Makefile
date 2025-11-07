.PHONY: help install test lint docs docs-serve docs-build clean

help:		## Show this help message
	@echo "Available commands:"
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-20s\033[0m %s\n", $$1, $$2}'

POETRY := poetry

install:	## Install dependencies
	$(POETRY) install

test:		## Run tests
	$(POETRY) run pytest -q

lint:		## Run linting and code quality checks
	$(POETRY) run ruff check .
	$(POETRY) run ruff format --check .
	$(POETRY) run pydocstyle . --convention=google

type-check:	## Run type checking
	$(POETRY) run mypy app/

docs:		## Alias for docs-serve
	mkdocs serve

docs-serve:	## Serve documentation locally
	$(POETRY) run mkdocs serve

docs-build:	## Build documentation
	$(POETRY) run mkdocs build

clean:		## Clean build artifacts
	rm -rf site/
	rm -rf .pytest_cache/
	rm -rf __pycache__/
	find . -name "*.pyc" -delete
	find . -name "*.pyo" -delete

pre-commit:	## Run pre-commit hooks
	$(POETRY) run pre-commit run --all-files

check-all:	## Run all quality checks
	@echo "Running linting..."
	$(POETRY) run ruff check .
	$(POETRY) run ruff format --check .
	@echo "Running docstring checks..."
	$(POETRY) run pydocstyle . --convention=google || true
	@echo "Running type checks..."
	$(POETRY) run mypy app/ || true
	@echo "Running tests..."
	$(POETRY) run pytest -q || true
	@echo "Building documentation..."
	$(POETRY) run mkdocs build || true
