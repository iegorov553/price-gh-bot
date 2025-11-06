## Project Overview
Price GH Bot is a Telegram assistant that estimates the full cost of eBay and Grailed purchases delivered to Russia. The bot resolves marketplace links, calculates shipping, customs duty, and commission, and produces admin-only analytics that help operators understand usage patterns. This repository contains everything required to run the bot in production, including Docker images, dependency management, CI tooling, and documentation.

## Feature Highlights
- **Marketplace coverage**: Resolves eBay and Grailed listings, plus Grailed seller profiles and shortened links.
- **Total cost breakdown**: Combines item price, domestic shipping, commission rules, currency conversion, and tiered international shipping (Shopfans-based routes for Europe, Turkey, Kazakhstan).
- **Customs and currency**: Applies the current EUR->USD threshold (200 EUR) and USD->RUB exchange rate retrieved through the Central Bank of Russia API with configurable markup.
- **Seller reliability scoring**: Runs a Playwright-powered scrape of Grailed profiles, scoring activity, rating, reviews, and trust badge to categorise sellers (Diamond -> Ghost).
- **User messaging**: Produces Russian-language responses with detailed breakdowns, optional item photos, and clear error messages.
- **Security and abuse controls**: Detects suspicious URLs, guards admin-only commands, isolates text resources, and supports feedback collection.
- **Analytics subsystem**: Logs searches and errors to SQLite, exposes admin commands for daily/weekly stats, user insights, error reports, and CSV export.
- **Deployment flexibility**: Works via long polling for local setups or webhooks for Railway and other hosted environments.

## Architecture Snapshot
The bot follows a layered, dependency-injected architecture:
- `app/core`: Service locator, dependency container, shared interfaces.
- `app/bot`: Telegram handlers, response formatting, URL detection, analytics tracking, user messaging.
- `app/services`: Business logic for shipping, customs, commission, currency, analytics, caching, and browser management.
- `app/scrapers`: Marketplace scrapers using Playwright/aiohttp, plus helpers for headless execution.
- `app/models.py`: Pydantic models shared across layers.
- `tests_new`: Unit/integration/e2e suites aligned with the service boundaries.

Refer to `docs/architecture/overview.md` and `docs/architecture/components.md` for a comprehensive design tour.

## Prerequisites
- Python 3.11+
- Docker 24+ (for production builds) and Docker Compose (for test harnesses)
- Telegram Bot Token created via @BotFather
- Playwright Chromium binaries (`playwright install chromium`)
- (Optional) Redis instance for caching, SQLite write permissions for analytics

## Installation
### Local development with Poetry
```bash
poetry install
poetry run playwright install chromium
poetry run pre-commit install
```

### Docker image (production)
```bash
docker build -t price-gh-bot:latest -f Dockerfile .
docker run --env-file .env price-gh-bot:latest
```

### Test image
```bash
docker build -t price-gh-bot-test -f Dockerfile.test .
```

## Configuration
Set the required environment variables (see `docs/setup/configuration.md` for the full list):
- `BOT_TOKEN`: Telegram bot token (required)
- `ADMIN_CHAT_ID`: Telegram chat ID that receives analytics and admin alerts
- `ENABLE_HEADLESS_BROWSER`: Enable Playwright extraction (default: `true`)
- `BOT_LISTEN_HOST`: Host interface for webhook binding (default: `127.0.0.1`)
- `RAILWAY_PUBLIC_DOMAIN` or `RAILWAY_URL`: Public URL for webhook mode
- `ANALYTICS_*`: Control analytics storage, export, and retention
- `GITHUB_*`: Optional GitHub integration for automated issue filing

When running inside a container or PaaS (Railway, Render, Fly.io), set `BOT_LISTEN_HOST=0.0.0.0` so Telegram can reach the webhook endpoint. The default `127.0.0.1` is meant for local development.

Additional configuration is loaded from `app/config/config.yml` files (commission tiers, shipping routes, currency markup). Shipping weights default to 0.60 kg unless a pattern match is found in `app/config/shipping_table.yml`.

## Running the Bot
### Local polling mode
```bash
export BOT_TOKEN=...
poetry run python -m app.main
```
Without a public domain the bot falls back to long polling.

### Webhook mode (e.g., Railway)
```bash
export BOT_TOKEN=...
export RAILWAY_PUBLIC_DOMAIN=your-app.up.railway.app
poetry run python -m app.main
```
The application will register a webhook at `https://<domain>/<BOT_TOKEN>`.

### Via Docker Compose (tests)
```bash
docker compose -f docker-compose.test.yml up
```

Refer to `Makefile` for convenience targets (`make install`, `make test`, `make lint`, `make docs-serve`).

## Operational Guide
- **Logging**: Structured logs go to stdout; configure Docker or hosting provider to persist them.
- **Analytics database**: Stored at `data/analytics.db` by default. Back up or rotate this file if long-term retention is required.
- **Persistent storage**: Mount a volume to `/app/data` (or adjust `ANALYTICS_DB_PATH`) in production to keep analytics across deployments.
- **Resource lifecycle**: `app.main` initialises a Playwright browser pool and Redis cache (if configured) on startup and tears them down on shutdown.
- **Redis cache (optional)**: The bot automatically degrades to in-memory mode if Redis is absent. To enable caching, ensure a Redis instance is reachable at `redis://localhost:6379` (default) or adjust `CacheConfig.redis_url` to your managed Redis endpoint before deploying.
- **Admin commands**:
  - `/analytics_daily`, `/analytics_week`: Usage metrics
  - `/analytics_user <id>`: Per-user insights
  - `/analytics_errors [days]`: Error breakdown
  - `/analytics_export [days]`: CSV export
  - `/analytics_download_db`: Raw SQLite dump
- **Feedback loop**: `/feedback` initiates a conversation that collects user comments while blocking scraper execution until the feedback is handled.

More operational guidance is available in `docs/operations/monitoring.md`.

## Testing & QA
Mandatory quality gates before every commit or deployment:
- `poetry run ruff check .` and `poetry run ruff format --check .`
- `poetry run mypy app`
- `poetry run bandit -c pyproject.toml -r app`
- `poetry run pip-audit`
- `poetry run pytest`
- `poetry run pre-commit run --all-files`
- End-to-end coverage currently excludes the real eBay listing scenario (`tests_new/e2e/test_real_urls.py`) which is temporarily marked as skipped due to upstream listing instability.

The test strategy, tooling, and fixtures are documented in `docs/testing/strategy.md` and `docs/testing/how_to.md`.

## Deployment Checklist
1. Ensure `.env` contains production-ready secrets (no defaults or placeholders).
2. Run the full QA suite (see above) inside the production Docker image.
3. Build the Docker image (`Dockerfile`) and push it to your registry.
4. Populate Playwright browsers in the target environment (`playwright install chromium`).
5. Configure persistent storage for `data/analytics.db` if analytics are enabled.
6. Verify webhook reachability or polling connectivity.
7. Rotate and securely store the Telegram token and any GitHub credentials after deployment.

## Troubleshooting
- **Playwright fails to launch**: Ensure `ENABLE_HEADLESS_BROWSER=true`, chromium binaries are installed, and the container has shared memory (`--shm-size=1g`).
- **Telegram timeouts**: Increase `BotConfig.timeout` or check network egress.
- **Analytics database locked**: Confirm no competing process holds the SQLite file; consider moving to a managed database for high throughput.
- **Missing replies or photos**: Check that the bot has message permissions; inspect logs for failed photo uploads.
- **Redis unavailable**: The cache layer degrades gracefully; warnings appear in logs.

Detailed troubleshooting scenarios live in `docs/operations/troubleshooting.md`.

## Security Notes
- Never commit tokens or secrets. Load them from environment variables or secret managers.
- Restrict write access to `data/` and rotate analytics exports regularly.
- Use distinct Redis databases or prefixes when sharing infrastructure.
- Keep Playwright binaries patched; rebuild the Docker image monthly to apply base image updates.
- Enforce admin command restrictions by keeping `ADMIN_CHAT_ID` up to date.
- Review `docs/security/practices.md` and `docs/security/auditing.md` for hardening steps.

## Support & Contributions
- Read `docs/CONTRIBUTING.md` before opening a pull request.
- File issues with reproducible steps and anonymised logs.
- Update documentation alongside code changes and accompany new functionality with automated tests (`pytest`).
- All pushes must target the `staging` branch; use protected branches for production.

For a guided tour of the documentation set, start with `docs/index.md`.
