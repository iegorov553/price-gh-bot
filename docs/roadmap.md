# Roadmap

This roadmap captures ongoing improvements, known risks, and upcoming milestones. Update it whenever priorities change.

## Security
- Remove all legacy references to historical tokens and ensure secrets never appear in fixtures.  
- Harden URL validation to mitigate malicious link submissions.  
- Review file access patterns to prevent path traversal vulnerabilities.  
- Expand automated security testing in CI (Bandit, pip-audit, dependency update notifications).

## Architecture
- Continue breaking down large modules (e.g., legacy helpers under `app/scrapers/headless.py`) into focused components.  
- Introduce contract tests that enforce `ScraperProtocol` compatibility when adding new marketplaces.  
- Evaluate migration of analytics storage from SQLite to a managed database for better concurrency.
- **Strict typing rollout**:
  - ✅ Bot layer (`handlers`, `response_formatter`, `url_processor`, `scraping_orchestrator`) migrated to typed `TypedDict` contracts and passes mypy in strict mode.
  - ⏳ Legacy marketplace scrapers still rely on dynamic `Any`. Plan a dedicated refactor to:
    1. Split the large Grailed scrapers (`app/scrapers/grailed.py`, `app/scrapers/grailed_scraper.py`, `app/scrapers/headless.py`) into smaller helpers with explicit data models.
    2. Replace ad-hoc dictionaries with typed Pydantic models or dataclasses for parsed payloads.
    3. Add safe wrappers around Playwright/BeautifulSoup calls with explicit return types (`ElementHandle | None`, `str | None`, etc.).
    4. Cover the new structure with unit tests that validate parsing logic against fixture HTML/JSON.
    5. Restore mypy strictness once refactor is complete and ensure no `Any` leaks remain in the scraper layer.

## Performance
- Optimise Playwright startup by extending the browser pool and reusing contexts per request.  
- Add caching for currency exchange rates and frequently accessed listings.  
- Monitor scraping latency and consider proxy rotation when marketplaces throttle requests.

## Testing
- Increase coverage for modules that currently lack automated tests (highlighted in coverage reports).  
- Add performance or load tests to measure throughput under heavy usage.  
- Implement CI pipelines that run the full QA suite on every pull request.

## Documentation
- Keep README and `docs/` aligned with new features, configuration options, and operational procedures.  
- Publish short runbooks for incident response scenarios (scraper changes, analytics corruption, Redis outages).  
- Add diagrams illustrating architecture updates when major refactors land.

## Feature Ideas
- Support additional marketplaces by implementing new scrapers and integrating them into the orchestrator.  
- Enhance analytics dashboards with charts or external BI integrations.  
- Provide configurable commission and shipping rules per customer segment.

Contributors should sync with maintainers before starting large initiatives to avoid duplication of effort.
