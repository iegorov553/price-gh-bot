# Security Auditing

Automated audits help catch vulnerabilities early. This guide explains the required tools and how to interpret their output.

## Ruff Security Lints
- Runs lightweight security checks alongside style rules.
- Command:
  ```bash
  poetry run ruff check .
  ```
- Fix actionable findings immediately; document accepted risks if they cannot be resolved quickly.

## Bandit
- Static analysis for Python security issues (injection, insecure usage of system calls, etc.).
- Command:
  ```bash
  poetry run bandit -c pyproject.toml -r app
  ```
- Treat findings with severity `HIGH` or confidence `HIGH` as blockers. Medium findings require triage.

## pip-audit
- Scans installed packages for known vulnerabilities.
- Command:
  ```bash
  poetry run pip-audit
  ```
- If a vulnerability appears, upgrade or replace the affected package. Document mitigation steps in the pull request.

## mypy
- While not strictly a security tool, strict typing prevents many classes of bugs.
- Command:
  ```bash
  poetry run mypy app
  ```

## Pre-commit
- Executes configured hooks (formatting, linting, security) before commits.
- Command:
  ```bash
  poetry run pre-commit run --all-files
  ```

## Scheduling Audits
- Run the full security suite before every commit and deployment.
- Integrate these checks into CI to block vulnerable code paths.
- After dependency upgrades, rerun all tools and review change logs for breaking security updates.

## Reporting
- File an issue for any unresolved findings, referencing tool output and proposed remediation.
- Update `docs/security/practices.md` or `roadmap.md` if findings require long-term tracking or architectural changes.

Consistent auditing reduces the chance of regressions and keeps the bot compliant with security best practices.
