# Architecture Overview

Price GH Bot applies clean architecture and SOLID principles to isolate concerns, simplify testing, and enable new marketplaces or delivery routes without rewriting core logic.

## Layered Design
1. **Presentation** (`app/bot`): Telegram handlers, message formatting, loading screens, and admin commands. This layer never performs business logic directly; it delegates to orchestrators and services.
2. **Domain Services** (`app/services`): Shipping, customs, commission rules, currency conversion, feedback flow, analytics logging, caching, and browser pooling. Services are resolved through dependency injection and operate on Pydantic models.
3. **Data Access** (`app/scrapers`): eBay and Grailed scrapers implemented with Playwright and aiohttp. Each scraper adheres to the shared `ScraperProtocol` interface so they can be swapped or extended.
4. **Core Infrastructure** (`app/core`): Service locator, dependency container, protocol definitions, and shared utilities that glue the layers together.
5. **Shared Models** (`app/models.py`): Validated data contracts for items, sellers, calculations, analytics entries, and error boundaries.

```text
Telegram Bot (presentation)
        |
        v
Domain Services (shipping, customs, commission, analytics)
        |
        v
Marketplace Scrapers (eBay, Grailed, headless browsing)
        |
        v
Core Infrastructure (DI container, service locator, protocols)
        |
        v
Shared Models and Config (Pydantic models, YAML-driven settings)
```

## Key Principles
- **Dependency inversion**: Handlers depend on protocols and services registered in the container rather than concrete implementations.
- **Single responsibility**: Each component handles one job (e.g., `response_formatter` only assembles reply text).
- **Open for extension**: Adding a new marketplace scraper requires implementing the protocol and registering it in the container without touching handlers.
- **Isolation for testing**: Layer boundaries let the test suite swap heavy integrations (Playwright, network calls) with mocks or fakes.
- **Asynchronous flow**: Scrapers and orchestrators use asyncio to parallelise marketplace calls and browser interactions.

## Runtime Composition
- `app/main.py` initialises the Telegram application, sets up resource hooks, and registers handlers.
- `app/core/container.py` registers services and scrapers. Factories accept configuration from `app/config.py`.
- `app/services/browser_pool.py` and `app/services/cache_service.py` expose singleton pools that are initialised during startup and gracefully shut down on exit.
- Analytics, logging, and error handling are centralised so that business logic stays free of presentation details.

## Supporting Tooling
- **Dependency management**: Poetry (`pyproject.toml`, `poetry.lock`).
- **Static analysis**: Ruff (lint and format), mypy, Bandit, pip-audit, pre-commit hooks.
- **Testing**: Pytest suite under `tests_new/`, organised by unit, integration, and end-to-end tiers.
- **Documentation**: MkDocs site generated from the files in `docs/`.

Review `architecture/components.md` for component-level details and `architecture/data_flow.md` for a concrete request walk-through.
