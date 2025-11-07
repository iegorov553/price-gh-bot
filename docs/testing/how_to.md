# How to Run Tests

This guide lists the commands and environments used to execute the test suite and quality checks.

## Local Execution (Poetry)
```bash
poetry run pytest           # Run all tests
poetry run pytest tests_new/unit -q
poetry run pytest tests_new/integration -q
poetry run pytest tests_new/e2e -q
```

> ℹ️ The real eBay listing scenario is temporarily skipped (`tests_new/e2e/test_real_urls.py`) while the upstream listing remains unstable. Grailed and currency end-to-end checks continue to run.

### Additional Checks
```bash
poetry run ruff format --check .
poetry run ruff check .
poetry run mypy app
poetry run bandit -c pyproject.toml -r app
poetry run pip-audit
poetry run pre-commit run --all-files
```

## Docker-Based Testing
```bash
docker build -t price-gh-bot-test --target test .
docker run --rm -it --env-file .env.pricebot price-gh-bot-test
```
Adjust the env file or environment variables to provide required tokens for integration tests. Use a dedicated test token; never reuse production credentials.

## Playwright Requirements
- Install Chromium before running tests that rely on Playwright:
  ```bash
  poetry run playwright install chromium
  ```
- For Docker containers, add `--shm-size=1g` to avoid shared memory exhaustion.

## Markers and Shortcuts
- Use `pytest -m "not e2e"` to skip long-running end-to-end tests during development.
- Use `pytest -k keyword` to run targeted subsets.
- Add custom markers in `pytest.ini` if new categories of tests are introduced.

## Reporting
- Generate coverage: `poetry run pytest --cov=app --cov-report=term-missing`.
- Generate JUnit XML for CI: `poetry run pytest --junitxml=reports/junit.xml`.
- Publish HTML coverage by adding `--cov-report=html` and reviewing the `htmlcov/` directory.

## Failing Tests
- Investigate failures with increased verbosity: `pytest -vv`.
- Reproduce flaky tests multiple times: `pytest <path>::<test_name> --maxfail=1 --count=10`.
- File an issue if a test consistently fails due to missing mocks or outdated fixtures.

Always run the full suite (tests + lint + typing + security) before committing or deploying changes.
