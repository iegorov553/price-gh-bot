# Component Reference

This document drills into the main modules that make up Price GH Bot. Each section lists responsibilities, notable dependencies, and extension hooks.

## app/bot
- `handlers.py`: Telegram command and message handlers. Delegates URL parsing to `url_processor`, scraping to `scraping_orchestrator`, and response formatting to `response_formatter`. Maintains admin-only analytics commands and feedback flow integration.
- `analytics_tracker.py`: Buffers analytics events before they are persisted by `app/services/analytics.py`.
- `url_processor.py`: Extracts URLs from free-form text, filters supported marketplaces, and flags suspicious content.
- `scraping_orchestrator.py`: Runs concurrent scraping tasks, applies timeouts, and merges results with pricing calculations.
- `response_formatter.py`: Builds Markdown responses and loading messages in Russian. Text constants live in `messages.py` to avoid hardcoded UI strings in logic.
- `feedback.py`: Manages the `/feedback` conversation and ensures normal scraping waits until user input is fully collected.
- `utils.py`: Shared helpers for safe file access, image handling, and text utilities.

## app/services
- `shipping.py`, `commission.py`, `customs.py`: Implement the pricing rules configured through YAML and environment variables.
- `currency.py`: Fetches USD<->RUB and EUR<->USD rates from the Central Bank of Russia API with optional caching and markup.
- `analytics.py`: Persists search statistics, surfaces aggregate reports, and exports CSVs.
- `browser_pool.py`: Manages reusable Playwright browser instances for Grailed scraping.
- `cache_service.py`: Optional Redis cache for currency and scraper results.
- `feedback_service.py`: Records feedback payloads for follow-up.
- `seller_assessment.py`: Applies seller advisory rules based on rating, reviews, and buy-now availability.
- Dependency contracts live alongside implementations so tests can substitute mocks.

## app/scrapers
- `ebay_scraper.py`: Extracts listing price, shipping, seller info, and item state using aiohttp requests and parsing logic resilient to minor layout changes.
- `grailed_scraper.py`: Uses Playwright to fetch dynamic data, seller reviews, and recent activity.
- `headless.py`: Legacy helper retained for compatibility; new code should prefer the browser pool abstraction.
- Base protocols define required methods for marketplace scrapers (`supports_url`, `scrape_item`, `scrape_seller`).

## app/core
- `container.py`: Configures the dependency injection container, registering services, scrapers, and utility singletons.
- `service_locator.py`: Offers a global accessor when constructor injection is not feasible (keep usage minimal).
- `interfaces.py`: Protocol definitions used across services and tests.

## app/models.py
Contains Pydantic models for:
- `PriceCalculation`: All components of the final price (commission, customs, shipping).
- `ItemData` and `SellerData`: Normalised outputs from scrapers.
- `SearchAnalytics`: Schema for analytics persistence and reporting.
- Error payloads: Provide consistent formatting between layers.

## Configuration (app/config)
- `config.py`: Loads environment variables into typed settings, reads YAML files (`fees.yml`, `shipping_table.yml`), and exposes derived properties such as `use_webhook`.
- `config/fees.yml`: Controls commission thresholds, per-kilogram shipping rates, and currency markup.
- `config/shipping_table.yml`: Maps product categories (regex patterns) to default package weights.

## Tests (tests_new)
- `unit`: Validates services and helpers with mocks.
- `integration`: Exercises multiple layers (e.g., scraping orchestrator + services) with controlled dependencies.
- `e2e`: Spins up near-production flows hitting real scrapers and ensuring Telegram messages are composed correctly.

When extending the bot, ensure new modules have dedicated tests and, if user-facing strings are introduced, keep them inside a messages or resources file.
