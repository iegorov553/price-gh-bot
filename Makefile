.PHONY: help install test lint docs docs-serve docs-build clean

help:		## Show this help message
	@echo "Available commands:"
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-20s\033[0m %s\n", $$1, $$2}'

install:	## Install dependencies
	pip install -r requirements.txt

test:		## Run tests
	pytest -q

lint:		## Run linting and code quality checks
	ruff .
	pydocstyle . --convention=google

type-check:	## Run type checking
	mypy app/

docs:		## Alias for docs-serve
	mkdocs serve

docs-serve:	## Serve documentation locally
	mkdocs serve

docs-build:	## Build documentation
	mkdocs build

clean:		## Clean build artifacts
	rm -rf site/
	rm -rf .pytest_cache/
	rm -rf __pycache__/
	find . -name "*.pyc" -delete
	find . -name "*.pyo" -delete

pre-commit:	## Run pre-commit hooks
	pre-commit run --all-files

check-all:	## Run all quality checks
	@echo "Running linting..."
	ruff .
	@echo "Running docstring checks..."
	pydocstyle . --convention=google || true
	@echo "Running type checks..."
	mypy app/ || true
	@echo "Running tests..."
	pytest -q || true
	@echo "Building documentation..."
	mkdocs build || true