# Development Workflow

This workflow keeps changes reliable, testable, and ready for deployment.

## Branching & Environments
- Work always starts from `staging`. Direct pushes to `main` are prohibited.
- Use descriptive branch names (`feature/analytics-export`, `fix/grailed-timeout`).
- Rebase frequently to minimise merge conflicts.

| Environment | Location | Purpose | Who deploys/tests |
|-------------|----------|---------|-------------------|
| `dev`       | локально | Рабочее окружение агента (я). CI и автотесты гоняются здесь. | агент |
| `staging`   | Railway  | Тестовый бот для ручной проверки. По завершении задачи агент пушит изменения, вы тестируете. | агент → вы |
| `main`      | Railway  | Продакшен-бот для пользователей. Мержим из `staging` только после ручного теста. | вы |

После успешной проверки в dev → пуш в `staging`. После ручного теста в `staging` вы инициируете merge в `main` и деплой.

## Daily Routine
1. Sync dependencies: `poetry install` and `poetry run pre-commit install`.
2. Run `poetry run ruff format .` followed by `poetry run ruff check .` to ensure consistent style.
3. Execute `poetry run pytest` before committing. Add targeted tests for new features or bug fixes.
4. If typing or security-critical changes were made, run:
   ```bash
   poetry run mypy app
   poetry run bandit -c pyproject.toml -r app
   poetry run pip-audit
   ```
5. Commit with clear messages and include documentation updates relevant to the change.

## Pull Requests
- Include a summary of what changed, why, and how it was tested.
- Link to relevant issues or roadmap items.
- Highlight any migrations, config changes, or operational impacts.
- Wait for CI (lint, tests, security scans) to pass before requesting review.

## Testing Expectations
- New functionality must ship with automated tests in `tests_new/`.
- Existing untested areas should be flagged for follow-up; propose coverage improvements to maintainers.
- For complex flows, consider integration tests that exercise orchestrators and service interactions.

## Tooling
- Use the provided `Makefile` targets (`make test`, `make lint`, `make pre-commit`) as shortcuts.
- Run `mkdocs serve` when editing documentation to preview changes locally.
- Keep Playwright browsers up to date (`poetry run playwright install chromium`) after updating Playwright dependencies.

### Docker Targets
- Multi-stage `Dockerfile` содержит два таргета:
  - `runtime` — основной образ бота.
  - `test` — тот же базовый слой + dev зависимости для автотестов.
- Примеры:
  ```bash
  docker build --target runtime -t price-gh-bot .
  docker build --target test -t price-gh-bot-test .
  docker run --rm price-gh-bot-test
  ```
- Railway использует `runtime` таргет. Dev/staging/prod окружения получают одинаковые системные зависимости и Playwright.

## Before Merging
- Verify Docker builds: `docker build -t price-gh-bot:latest -f Dockerfile .`.
- Run the full quality suite inside the container if feasible.
- Confirm documentation reflects any new CLI commands, environment variables, or operational tasks.

Following this workflow ensures the bot remains stable while the feature set grows.
