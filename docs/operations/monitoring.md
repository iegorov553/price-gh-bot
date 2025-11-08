# Monitoring and Analytics

Price GH Bot ships with built-in observability features that help operators understand usage patterns and diagnose issues.

## Logging
- Logs are emitted to stdout with timestamp, level, and message (configured in `app/main.py`).
- Use your container platform or hosting provider to aggregate and persist logs.
- Important log messages include:
  - Startup and shutdown of Playwright browser pools.
  - Redis cache availability.
  - Suspicious URL detection.
  - Scraper errors and timeout warnings.

## Analytics Subsystem
- Implemented in `app/services/analytics.py` with the `SearchAnalytics` Pydantic model.
- Records every processed URL, including success flag, calculation results, processing time, and seller scoring.
- Stored in SQLite (default `data/analytics.db`). Location is configurable via `ANALYTICS_DB_PATH`.

### Admin Commands
- `/analytics_daily`: Summary for the past 24 hours (total searches, success rate, unique users, average processing time, platform breakdown).
- `/analytics_week`: Same metrics across seven days.
- `/analytics_user <user_id>`: Usage history for a specific user (platform preference, average prices, recent searches).
- `/analytics_errors [days]`: Aggregated errors by platform and message.
- `/analytics_export [days]`: Sends a CSV export covering the selected window.
- `/analytics_download_db`: Sends the raw SQLite database for offline analysis.

### Data Retention
- Controlled by `ANALYTICS_RETENTION_DAYS`. Implement cleanup jobs if the database grows beyond expectations.
- Analytics can be disabled entirely by setting `ANALYTICS_ENABLED=false`.

## Health Indicators
- Monitor for repeated scraper failures or Playwright restarts. Frequent errors may indicate layout changes or throttling by the marketplaces.
- Track the average processing time. Significant increases could mean network issues or headless browser contention.
- Keep an eye on error messages returned to users to spot regressions promptly.

## External Monitoring
- Consider adding uptime checks against your webhook endpoint or long-polling runners.
- Use alerting to notify operators if the bot stops responding or if error rates surpass agreed thresholds.
- If Redis is enabled, monitor connection health and memory usage.

## Backups
- Schedule backups of `data/analytics.db` if long-term analytics are important.
- Rotate CSV exports stored outside the bot to comply with privacy requirements.

Regular monitoring helps maintain reliable service and catch scraping changes before they impact users.
