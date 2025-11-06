# Configuration Reference

The bot reads configuration from environment variables and YAML files under `app/config/`. This page lists required values, optional toggles, and file-based settings.

## Environment Variables

| Variable | Required | Description |
|----------|----------|-------------|
| `BOT_TOKEN` | Yes | Telegram bot token issued by @BotFather. |
| `ADMIN_CHAT_ID` | Yes | Telegram chat ID allowed to run admin commands. |
| `ENABLE_HEADLESS_BROWSER` | No (default `true`) | Enables Playwright scraping for Grailed data. |
| `BOT_LISTEN_HOST` | No (default `127.0.0.1`) | Host interface to bind the webhook server. Override to `0.0.0.0` only when exposing the bot publicly. |
| `PORT` | No (default `8000`) | Port for webhook mode. |
| `RAILWAY_PUBLIC_DOMAIN` / `RAILWAY_URL` | No | Public domain used to register the webhook. Without this, the bot uses long polling. |
| `ANALYTICS_ENABLED` | No (default `true`) | Toggles analytics collection. |
| `ANALYTICS_DB_PATH` | No (default `data/analytics.db`) | SQLite file path for analytics. |
| `ANALYTICS_EXPORT_ENABLED` | No (default `true`) | Enables `/analytics_export` command. |
| `ANALYTICS_RETENTION_DAYS` | No (default `365`) | Retention period for analytics cleanup jobs. |
| `GITHUB_TOKEN` | No | Token for creating GitHub issues from admin commands. |
| `GITHUB_OWNER` / `GITHUB_REPO` | No | Target repository for automated issue filing. Defaults to `iegorov553` / `price-gh-bot`. |

Provide these variables through `.env`, your container orchestrator, or a secret manager. Never commit actual values to source control.

## YAML Files (`app/config/`)

| File | Purpose |
|------|---------|
| `fees.yml` | Commission thresholds, Shopfans shipping rates, and currency markup percentage. |
| `shipping_table.yml` | Maps regex patterns (e.g., footwear, outerwear) to default package weights used when item weight is unknown. |

The `Config` class (`app/config.py`) reads the YAML files at startup. If files are missing, sane defaults are applied:
- Commission: flat 15 USD below 150 USD, 10 percent otherwise.  
- Shipping: 13.99 USD minimum, per-kilogram rates of 30.86 (Europe), 35.27 (Turkey), 41.89 (Kazakhstan).  
- Shipping weight: 0.60 kg fallback.  
- Currency markup: 5 percent.

## Analytics Storage
- Default path: `data/analytics.db`. Ensure the directory is writable by the bot process.  
- To relocate the database, set `ANALYTICS_DB_PATH` and mount the target directory in Docker.  
- Use `/analytics_download_db` to retrieve the file for investigation or backup.

## Webhook vs Polling
- If `RAILWAY_PUBLIC_DOMAIN` or `RAILWAY_URL` is populated, the bot runs in webhook mode and binds to `BOT_LISTEN_HOST:<PORT>` (defaults to `127.0.0.1`). Use `BOT_LISTEN_HOST=0.0.0.0` when running inside containers that require public binding.  
- Without a public domain, the bot falls back to long polling. Ensure outbound connectivity to Telegram endpoints.

## Secret Management Tips
- Use `.env` only for local development; production deployments should load secrets from a vault or runtime environment.  
- Rotate `BOT_TOKEN` regularly and immediately after any suspected leak.  
- Keep `ADMIN_CHAT_ID` up to date when onboarding or offboarding operators.

Revisit this page whenever you introduce new features that depend on additional configuration.
