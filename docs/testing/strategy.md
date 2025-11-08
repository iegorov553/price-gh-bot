# Testing Strategy

Quality assurance for Price GH Bot follows a layered approach that balances speed with coverage.

## Test Pyramid
1. **Unit tests (`tests_new/unit/`)**
   - Validate individual services, utility functions, and models.
   - Use mocks or fakes for external dependencies (scrapers, network calls, Redis).
   - Fast feedback: aim for sub-second execution per module.
2. **Integration tests (`tests_new/integration/`)**
   - Exercise multiple components together (e.g., scraping orchestrator + shipping service).
   - Use real config values while mocking external HTTP endpoints.
   - Verify dependency injection wiring and edge-case handling.
3. **End-to-end tests (`tests_new/e2e/`)**
   - Run full flows with actual scrapers and Playwright where feasible.
   - Validate Telegram message formatting, analytics logging, and error boundaries.
   - The real eBay listing scenario is temporarily skipped while upstream data remains unstable; Grailed flows continue to run in CI.

## Coverage Goals
- Minimum 70 percent coverage overall; target 80 percent or higher for critical modules.
- Every new feature must add coverage for success and failure paths.
- Regression bugs trigger new tests that prevent recurrence.

## Tooling
- **Pytest** provides the execution framework.
- **Async fixtures** support coroutine-based tests.
- **Hypothesis or parameterised tests** can expand edge-case coverage where useful.
- Coverage reports can be generated with `pytest --cov=app --cov-report=term-missing`.

## Continuous Integration
- CI runs linting, type checks, security scans, and tests on every pull request.
- Failing tests block merges until resolved.
- Long-running E2E tests can be gated behind markers; use `pytest -m "not e2e"` for quicker feedback during local development.

## Data Management
- Keep fixtures deterministic and isolated; avoid writing to shared state unless tests clean up afterwards.
- Use temporary directories (`tmp_path`) for file operations.
- When a test requires analytics data, seed the SQLite database with fixture files or use in-memory SQLite.

## Expanding the Suite
- When adding major features, create integration or E2E tests that mirror real user flows.
- For modules without existing tests, schedule a follow-up task to add coverage and discuss the gaps with the team.
- Document any skipped tests and justify why they cannot run in CI.

Refer to `testing/how_to.md` for specific commands and environment setup required to run the suite.
