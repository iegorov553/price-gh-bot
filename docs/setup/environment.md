# Environment Preparation

Follow these steps to prepare a development or production environment for Price GH Bot.

## Local Workstation
1. **Install Python 3.11+**  
   - Recommended: use pyenv or system packages.  
   - Ensure `python3 --version` reports 3.11 or newer.
2. **Install Poetry**  
   ```bash
   pipx install poetry
   ```
3. **Install project dependencies**  
   ```bash
   poetry install
   poetry run playwright install chromium
   poetry run pre-commit install
   ```
4. **Prepare environment variables**  
   - Copy `.env.example` to `.env` if available, or create a new `.env`.  
   - Populate `BOT_TOKEN`, `ADMIN_CHAT_ID`, `BOT_LISTEN_HOST`, and any optional integrations.
5. **Verify tooling**  
   ```bash
   poetry run ruff --version
   poetry run mypy --version
   poetry run pytest --version
   ```

## Docker Images
- **Production**: `Dockerfile` builds a slim Python image with Playwright dependencies.  
  ```bash
  docker build -t price-gh-bot:latest -f Dockerfile .
  docker run --env-file .env price-gh-bot:latest
  ```
- **Tests**: `Dockerfile.test` installs dev dependencies and testing tools.  
  ```bash
  docker build -t price-gh-bot-test -f Dockerfile.test .
  ```
- **Compose**: `docker-compose.test.yml` orchestrates the bot alongside its dependencies for integration testing.

## Headless Browser Requirements
- Playwright Chromium must be installed in the environment that runs the bot.  
- When running inside Docker, mount `/dev/shm` with at least 1 GB (`--shm-size=1g`) to avoid browser crashes.  
- Set `ENABLE_HEADLESS_BROWSER=false` if Playwright is unavailable; seller analysis will be disabled.

## Optional Services
- **Redis cache**: Configure connection details through the cache service if you need cached currency rates or scraper responses.  
- **Persistent storage**: Mount `data/` to preserve the SQLite analytics database across deployments.  
- **Logging stack**: Route container stdout to your log aggregation platform for long-term retention.

Double-check `docs/setup/configuration.md` after provisioning the environment to ensure all required variables are set.
