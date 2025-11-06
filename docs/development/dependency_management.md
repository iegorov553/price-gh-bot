# Dependency Management

Price GH Bot uses Poetry to manage dependencies. Follow this guide to keep the environment reproducible and secure.

## Installing Dependencies
```bash
poetry install
poetry run playwright install chromium
```
Poetry reads `pyproject.toml` for dependency declarations and locks versions in `poetry.lock`. Commit both files whenever dependencies change.

## Adding or Updating Packages
```bash
poetry add <package-name>
poetry update <package-name>
```
- Use `--group dev` for development-only tools.  
- After updating, run the QA suite (lint, mypy, bandit, pip-audit, pytest) to catch regressions.  
- Update documentation if new tooling introduces workflow changes.

## Removing Packages
```bash
poetry remove <package-name>
```
Ensure you clean up imports, configuration entries, and tests that relied on the package.

## Auditing Dependencies
- Security: `poetry run bandit -c pyproject.toml -r app` and `poetry run pip-audit`.  
- License checks: review Poetry output after `poetry update` for license summaries.  
- Pinning: avoid wildcard versions in `pyproject.toml`; use compatible release specifiers (`^`, `~`) to receive patch updates without breaking changes.

## Synchronising With Docker
- Multi-stage `Dockerfile` installs both runtime and dev dependencies; the `test` target shares the same base layers. Regenerate `requirements*.txt` when dependencies change:  
  ```bash
  poetry export -f requirements.txt --output requirements.txt --without-hashes
  poetry export -f requirements.txt --output requirements-dev.txt --without-hashes --with dev
  ```
- Rebuild images after updates to confirm builds remain reproducible.

## Caching Playwright Binaries
- After dependency updates that touch Playwright, reinstall the browser: `poetry run playwright install chromium`.  
- For Docker builds, ensure the install step remains in the Dockerfile to avoid runtime failures.

## Handling Optional Integrations
- When enabling Redis or GitHub integrations, add the necessary packages to the appropriate Poetry groups.  
- Document any new environment variables in `docs/setup/configuration.md`.

Keep dependency changes small, tested, and documented to avoid surprises in production environments.
