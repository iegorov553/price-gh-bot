# Project Overview

This repository contains **price-gh-bot**, a modern Telegram bot for calculating total purchase costs of eBay and Grailed listings with shipping to Russia. The bot uses a clean architecture based on SOLID principles with heavy emphasis on dependency injection and modular design.

## Key Features
- Price breakdown with commission, customs duty, and shipping.
- Multi-platform support: eBay and Grailed listings + Grailed seller profiles.
- Seller advisory engine flagging low ratings, missing reviews, and absent buy-now prices.
- Centralized error boundary with Russian user messages and admin alerts.
- Analytics subsystem logging usage and errors to SQLite with admin commands.

## Repository Layout
```
app/
├── core/            # DI container, service locator, interface protocols
├── bot/             # Telegram handlers, formatting, analytics tracker, utilities
├── services/        # Business logic (currency, shipping, customs, seller advisory)
├── scrapers/        # Marketplace scraping implementations (eBay, Grailed)
└── models.py        # Pydantic models used throughout the project
```
Other notable directories:
- `tests_new/`: Three-level test suite (unit, integration, e2e).
- `docs/`: MkDocs documentation with architecture, analytics, and testing guides.
- `data/`: Default location of the analytics SQLite database.

## Architecture Highlights
- **Layered design** separating presentation (bot), business logic (services), and data access (scrapers).
- **Dependency injection** via `app/core/container.py`; services are resolved through the global service locator.
- **ScraperProtocol** defines common interface for marketplace scrapers.
- **ErrorBoundary** ensures consistent user messaging and admin notifications.
- **Async** implementation using `aiohttp` and Playwright for headless scraping.

## Development Notes
- Python 3.11+ project managed with `pyproject.toml`.
- Dependencies listed in `requirements.txt` and `requirements-dev.txt`.
- Environment variables: `BOT_TOKEN`, `ADMIN_CHAT_ID`, optional `PORT`, `RAILWAY_PUBLIC_DOMAIN`, and `ENABLE_HEADLESS_BROWSER`.
- Run locally with `python -m app.main` after installing dependencies and Playwright browsers (`playwright install chromium`).
- Tests executed via `make test-all` or `pytest` commands under `tests_new/`.

## Documentation
Key documentation files include:
- `README.md` – feature overview and usage instructions.
- `docs/PROJECT_ANALYSIS.md` – in-depth architecture analysis and planned improvements.
- `docs/ANALYTICS.md` – analytics subsystem design and admin commands.
- `docs/TESTING.md` – testing framework and commands.
- `CLAUDE.md` – contributor guide emphasising SOLID architecture and DI.

## Known Issues and TODOs
The project currently has several open issues highlighted in `docs/PROJECT_ANALYSIS.md` and previous audits:
1. **Leaked Bot Token** – remove hardcoded token from docs and configs.
2. **Analytics model mismatches** – align logged fields with `SearchAnalytics` model.
3. **Duplicate `detect_platform` implementations** in `app/bot/utils.py`.
Future work should address these along with other security and architecture improvements documented in `PROJECT_ANALYSIS.md`.
