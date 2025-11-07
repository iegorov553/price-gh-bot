# Troubleshooting Guide

Use this guide to resolve common operational issues with Price GH Bot.

## Bot Does Not Start
- **Missing `BOT_TOKEN`**: Ensure the environment variable is set. The application raises `RuntimeError` if the token is absent.
- **Playwright dependencies**: Run `playwright install chromium` **и** `playwright install-deps` в том же окружении. В Docker всё делает многостадийный `Dockerfile`; при ручном запуске убедитесь, что системные библиотеки Playwright установлены, иначе Chromium не стартует.
- **Permission denied**: Confirm the process can write to `data/` (for analytics) and read configuration files under `app/config/`.

## Webhook Errors
- **HTTP 403 from Telegram**: Verify `RAILWAY_PUBLIC_DOMAIN` or `RAILWAY_URL` matches the deployed domain and that HTTPS is reachable.
- **TLS/Certificate issues**: Hosting providers must supply valid certificates. For local testing, prefer long polling.
- **Unexpected polling fallback**: The bot defaults to polling when no public domain is configured; double-check environment variables.
- **No incoming updates**: Ensure `BOT_LISTEN_HOST` is set to `0.0.0.0` inside containers so Telegram can reach the webhook port.

## Slow Responses
- **Playwright queueing**: Increase the browser pool size in `app/services/browser_pool.py` or provision more CPU.
- **Currency API delays**: Enable caching via Redis to avoid repeated CBR requests.
- **Marketplace throttling**: Introduce backoff or rotate proxies if scraping is rate-limited.

## Missing Images in Replies
- Some listings restrict hotlinking. Logs will show `Failed to send image`. The bot gracefully falls back to text, but you may retry with a different network or fetch the image manually.

## Analytics Database Locked
- SQLite locks can appear if multiple processes access `data/analytics.db`. Ensure only one bot instance writes to the file.
- For high-availability setups, migrate analytics to a remote database (requires code changes).
- Use `/analytics_download_db` outside business hours to avoid long locks.

## Redis Connection Warnings
- The cache service logs a warning when Redis is unavailable but continues without caching.
- Verify network connectivity, authentication, and database selection.
- The default endpoint is `redis://localhost:6379`. Point `CacheConfig.redis_url` to your managed Redis instance (or ensure one is running locally) to enable caching; otherwise the warning is harmless.

## Frequent Scraper Failures
- Inspect logs for HTML parsing errors or selector mismatches. Marketplace layouts may have changed.
- Update scraper logic and add regression tests before redeploying.
- Temporarily disable headless scraping (`ENABLE_HEADLESS_BROWSER=false`) to keep other functionality available.

## Telegram Rate Limits
- Reduce message frequency or batch replies if users send many URLs at once.
- Consider enabling per-user cooldowns in the handler if abuse is detected.
- Monitor the analytics error reports for `RetryAfter` exceptions.

Document and share novel incidents in the repository (issues or `docs/operations/troubleshooting.md`) so future operators can respond faster.
