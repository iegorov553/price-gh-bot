# Coding Guidelines

These guidelines keep the codebase modular, maintainable, and aligned with the bot's architecture.

## General Principles
- **Single responsibility**: Each module or class should handle one concern. Split files when a component grows beyond its original scope.  
- **Dependency injection**: Prefer constructor or factory injection. Use the global service locator only when wiring is impractical.  
- **Async first**: Scraping and network-bound operations must remain asynchronous. Avoid blocking calls inside async functions.  
- **Type hints everywhere**: All functions and methods require explicit type annotations. This improves readability and enables strict mypy checks.  
- **Keep strings external**: User-facing text belongs in resource files such as `app/bot/messages.py`. Avoid hardcoding interface strings in logic.

## File and Function Size
- Any file exceeding 400 lines or function exceeding 50 lines should be refactored. Break the code into smaller modules or helper functions. Flag oversized areas in reviews to maintain shared awareness.

## Error Handling
- Avoid broad `except Exception` blocks. Catch specific exceptions and provide actionable log messages.  
- Always log errors with enough context (URL, user ID, operation) to aid debugging without leaking sensitive data.  
- Surface user-friendly messages via the error boundary while preserving stack traces in logs.

## Logging and Analytics
- Use structured logging (`logger.info("...", extra={...})`) when possible.  
- When adding new analytics events, extend the `SearchAnalytics` model and ensure admin commands handle the additional fields gracefully.  
- Respect privacy: do not store personal data beyond what is necessary for analytics.

## Testing Rules
- Add unit tests for new services or helpers.  
- Add integration tests when multiple layers interact.  
- Keep test data deterministic and avoid live external calls unless explicitly marked as E2E.  
- When discovering untested code, suggest coverage improvements to maintainers even if it is outside the current scope.

## Documentation
- Update README and relevant docs under `docs/` whenever functionality, configuration, or operational steps change.  
- Keep documentation in English and ensure examples are accurate.  
- Mention follow-up work if an area still lacks tests or requires future refactoring.

## Code Style
- Follow Ruff formatting decisions (`poetry run ruff format .`).  
- Use snake_case for functions and variables, PascalCase for classes.  
- Prefer dataclasses or Pydantic models for structured data rather than loose dictionaries.  
- Maintain alphabetical imports where practical and group standard library, third-party, and local imports separately.

Refer back to this guide during reviews to make consistent decisions across the team.
