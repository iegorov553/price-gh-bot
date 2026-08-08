# Grailed Production Incident Remediation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make Grailed listing handling deterministic when Railway receives blocked or incomplete pages, prevent false seller data, and stop Telegram credentials and user payloads from leaking into logs.

**Architecture:** Introduce a small Grailed page classifier shared by static and Playwright fetch paths, replace the fixed browser sleep with condition-based readiness, and retry only incomplete responses once. Keep URL normalization separate from page acquisition. Centralize logging setup in a dedicated module that redacts secrets and lowers third-party HTTP verbosity; validate everything in staging before production promotion.

**Tech Stack:** Python 3.11+, aiohttp, Playwright async API, BeautifulSoup/lxml, python-telegram-bot 21.x, pytest, pytest-asyncio, Railway.

## Global Constraints

- Perform implementation from the `staging` branch; production remains on `main` until staging verification passes.
- Follow TDD: every behavioral change starts with a failing test.
- Do not add proxying, CAPTCHA bypass, or anti-bot evasion.
- Never log `BOT_TOKEN`, the token-bearing webhook path, raw Telegram updates, chat IDs, usernames, or full incoming messages.
- Retry only incomplete Grailed pages, at most once; do not retry explicit access-denied pages.
- Do not deploy or rotate credentials without explicit user confirmation at execution time.
- Keep eBay behavior and public scraper protocol unchanged.

---

## File Map

- Create `app/scrapers/grailed_page.py`: classify HTML as a valid listing, access denied, or incomplete.
- Modify `app/scrapers/headless.py`: wait for a listing/block signal and retry one incomplete page.
- Modify `app/scrapers/grailed_scraper.py`: validate both static and headless HTML and never extract seller data before item price validation.
- Modify `tests_new/unit/test_grailed_headless_fallback.py`: regression tests for blocked/incomplete/valid headless responses and seller extraction ordering.
- Create `tests_new/unit/test_grailed_page.py`: focused classifier tests.
- Create `app/logging_config.py`: production-safe log level setup and credential redaction.
- Modify `app/config.py`: add typed `LOG_LEVEL` configuration.
- Modify `app/main.py`: use centralized logging and stop logging the token-bearing webhook URL.
- Create `tests_new/unit/test_logging_config.py`: redaction and logger-level tests.
- Modify `tests_new/unit/test_config_bot.py`: `LOG_LEVEL` default and environment override tests.
- Modify `docs/TESTING.md`: staging incident verification procedure and expected log events.

### Task 1: Deterministic Grailed HTML classification

**Files:**
- Create: `app/scrapers/grailed_page.py`
- Create: `tests_new/unit/test_grailed_page.py`

**Interfaces:**
- Consumes: raw `str | None` HTML returned by aiohttp or Playwright.
- Produces: `GrailedPageState` and `classify_grailed_html(html: str | None) -> GrailedPageState`.

- [ ] **Step 1: Write classifier tests**

```python
from app.scrapers.grailed_page import GrailedPageState, classify_grailed_html


def test_classifies_next_data_listing() -> None:
    html = '<html><script id="__NEXT_DATA__">{"props":{"pageProps":{"listing":{"price":120}}}}</script></html>'
    assert classify_grailed_html(html) is GrailedPageState.LISTING


def test_classifies_access_denied_page() -> None:
    html = "<html><body>You are unable to access grailed.com</body></html>"
    assert classify_grailed_html(html) is GrailedPageState.BLOCKED


def test_classifies_cloudflare_challenge_page() -> None:
    html = '<html><body><div id="challenge-running">Checking your browser</div></body></html>'
    assert classify_grailed_html(html) is GrailedPageState.BLOCKED


def test_classifies_missing_listing_data_as_incomplete() -> None:
    assert classify_grailed_html("<html><body>Grailed</body></html>") is GrailedPageState.INCOMPLETE
    assert classify_grailed_html(None) is GrailedPageState.INCOMPLETE
```

- [ ] **Step 2: Run tests and confirm the missing module failure**

Run: `pytest tests_new/unit/test_grailed_page.py -q`

Expected: FAIL during collection with `ModuleNotFoundError: app.scrapers.grailed_page`.

- [ ] **Step 3: Implement the minimal classifier**

```python
from enum import StrEnum


class GrailedPageState(StrEnum):
    LISTING = "listing"
    BLOCKED = "blocked"
    INCOMPLETE = "incomplete"


_BLOCK_MARKERS = (
    "you are unable to access grailed.com",
    "checking your browser",
    "cf-chl-",
    "challenge-running",
)

_LISTING_MARKERS = (
    'id="__NEXT_DATA__"',
    "id='__NEXT_DATA__'",
    'property="product:price:amount"',
    'type="application/ld+json"',
)


def classify_grailed_html(html: str | None) -> GrailedPageState:
    if not html:
        return GrailedPageState.INCOMPLETE
    lowered = html.lower()
    if any(marker in lowered for marker in _BLOCK_MARKERS):
        return GrailedPageState.BLOCKED
    if any(marker.lower() in lowered for marker in _LISTING_MARKERS):
        return GrailedPageState.LISTING
    return GrailedPageState.INCOMPLETE
```

- [ ] **Step 4: Run focused tests**

Run: `pytest tests_new/unit/test_grailed_page.py -q`

Expected: 4 passed.

- [ ] **Step 5: Commit classifier**

```bash
git add app/scrapers/grailed_page.py tests_new/unit/test_grailed_page.py
git commit -m "test(scrapers): classify Grailed listing responses"
```

### Task 2: Condition-based Playwright fetch and bounded retry

**Files:**
- Modify: `app/scrapers/headless.py`
- Modify: `tests_new/unit/test_grailed_headless_fallback.py`

**Interfaces:**
- Consumes: `classify_grailed_html` and `GrailedPageState` from Task 1.
- Produces: unchanged public signature `fetch_page_html_headless(url: str) -> str | None`.

- [ ] **Step 1: Add failing tests for retry policy**

Use `AsyncMock` pages where the first `content()` result is incomplete and the second contains `__NEXT_DATA__`. Assert two calls to `browser.get_page()`. Add a separate blocked-page test asserting only one call and a `None` result. Keep the existing successful HTML test.

```python
@pytest.mark.asyncio
async def test_fetch_retries_incomplete_page_once() -> None:
    browser = MagicMock()
    first = AsyncMock()
    first.content.return_value = "<html><body>Grailed</body></html>"
    second = AsyncMock()
    second.content.return_value = '<html><script id="__NEXT_DATA__">{}</script></html>'
    browser.get_page = AsyncMock(side_effect=[first, second])

    result = await headless._fetch_html("https://www.grailed.com/listings/1", browser)

    assert "__NEXT_DATA__" in result
    assert browser.get_page.await_count == 2


@pytest.mark.asyncio
async def test_fetch_does_not_retry_blocked_page() -> None:
    browser = MagicMock()
    page = AsyncMock()
    page.content.return_value = "<html><body>You are unable to access grailed.com</body></html>"
    browser.get_page = AsyncMock(return_value=page)

    result = await headless._fetch_html("https://www.grailed.com/listings/1", browser)

    assert result is None
    assert browser.get_page.await_count == 1
```

- [ ] **Step 2: Run the focused tests and confirm failure**

Run: `pytest tests_new/unit/test_grailed_headless_fallback.py -q`

Expected: retry test FAIL because `_fetch_html` currently performs one attempt; blocked test FAIL because blocked HTML is returned.

- [ ] **Step 3: Replace the fixed 1.5-second delay**

In `_fetch_html`, make two attempts. After `page.goto(..., wait_until="domcontentloaded", timeout=25_000)`, use `page.wait_for_function` with a 10-second timeout to wait until the DOM contains `__NEXT_DATA__`, a product price meta tag, JSON-LD, or a known block marker. Classify `page.content()` after the wait. Return valid listing HTML, return `None` immediately for `BLOCKED`, and retry once for `INCOMPLETE`. Always close each page in `finally`.

Do not swallow navigation exceptions silently: log `attempt`, exception class, and canonical listing URL without query parameters or user identifiers.

- [ ] **Step 4: Run headless and classifier tests**

Run: `pytest tests_new/unit/test_grailed_headless_fallback.py tests_new/unit/test_grailed_page.py -q`

Expected: all tests pass; no real browser or network access is used.

- [ ] **Step 5: Commit browser behavior**

```bash
git add app/scrapers/headless.py tests_new/unit/test_grailed_headless_fallback.py
git commit -m "fix(scrapers): wait for Grailed listing readiness"
```

### Task 3: Validate scraper input and prevent false seller extraction

**Files:**
- Modify: `app/scrapers/grailed_scraper.py`
- Modify: `tests_new/unit/test_grailed_headless_fallback.py`

**Interfaces:**
- Consumes: `classify_grailed_html` and the existing headless fetch function.
- Produces: unchanged `GrailedScraper.scrape_item(...) -> ItemData | None`.

- [ ] **Step 1: Add failing scraper regression tests**

Add one test where static HTTP returns 403 and headless returns an access-denied page. Patch `_extract_seller_data` and assert it is not awaited. Add a second test where headless returns valid listing HTML and seller extraction occurs exactly once after price extraction.

```python
mock_headless.return_value = "<html><body>You are unable to access grailed.com</body></html>"
result = await scraper.scrape_item(url, mock_session)
assert result is None
mock_seller.assert_not_awaited()
```

- [ ] **Step 2: Run the regression tests and confirm failure**

Run: `pytest tests_new/unit/test_grailed_headless_fallback.py -q`

Expected: blocked test FAIL because current code accepts HTML by length/contents and calls seller extraction before validating price.

- [ ] **Step 3: Apply the classifier at both fetch boundaries**

For an aiohttp 200 response, accept HTML only when `classify_grailed_html(text) is LISTING`; otherwise trigger headless fallback. After headless fetch, return `None` with a state-specific warning unless the result is `LISTING`. Remove the `len(html) < 1000` heuristic.

- [ ] **Step 4: Validate item fields before seller scraping**

Parse price, title, shipping, and image first. If price is `None`, return `None` before `_extract_seller_data`. Only then resolve seller data and construct `ItemData`. This prevents the access-denied page from creating the observed false `rating=2.5, reviews=0` advisory.

- [ ] **Step 5: Run the Grailed unit suite**

Run: `pytest tests_new/unit/test_grailed_url_resolver.py tests_new/unit/test_grailed_buyability.py tests_new/unit/test_grailed_page.py tests_new/unit/test_grailed_headless_fallback.py -q`

Expected: all tests pass.

- [ ] **Step 6: Commit scraper validation**

```bash
git add app/scrapers/grailed_scraper.py tests_new/unit/test_grailed_headless_fallback.py
git commit -m "fix(scrapers): reject blocked Grailed pages"
```

### Task 4: Centralize safe logging and redact secrets

**Files:**
- Create: `app/logging_config.py`
- Modify: `app/config.py`
- Modify: `app/main.py`
- Create: `tests_new/unit/test_logging_config.py`
- Modify: `tests_new/unit/test_config_bot.py`

**Interfaces:**
- Produces: `configure_logging(level: str) -> None` and `SensitiveDataFilter(logging.Filter)`.
- Consumes: `config.bot.log_level`, defaulting to `INFO`.

- [ ] **Step 1: Add failing configuration and redaction tests**

Test that `BotConfig().log_level == "INFO"`, `LOG_LEVEL=DEBUG` overrides it, and a `LogRecord` containing `https://api.telegram.org/bot123456:ABC_secret/sendMessage` is formatted with `bot<REDACTED>`. Test that `httpx`, `httpcore`, and `telegram.ext.ExtBot` effective levels are at least `WARNING` after configuration.

- [ ] **Step 2: Run logging tests and confirm failure**

Run: `pytest tests_new/unit/test_logging_config.py tests_new/unit/test_config_bot.py -q`

Expected: FAIL because `log_level`, `configure_logging`, and `SensitiveDataFilter` do not exist.

- [ ] **Step 3: Add typed log-level configuration**

Add to `BotConfig`:

```python
log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = Field(
    default="INFO", validation_alias="LOG_LEVEL"
)
```

Import `Literal` from `typing`.

- [ ] **Step 4: Implement centralized logging**

Create a root stream handler with the existing timestamp/level/message format. Attach `SensitiveDataFilter` to the handler. Redact Telegram tokens with `r"bot\d+:[A-Za-z0-9_-]+"` and token-bearing webhook paths using the configured bot token when present. Set third-party network loggers `httpx`, `httpcore`, `telegram.ext.ExtBot`, and `telegram.ext._application` to `WARNING`.

- [ ] **Step 5: Remove explicit secret-bearing logs from startup**

Replace `logging.basicConfig(...)` in `app/main.py` with `configure_logging(config.bot.log_level)`. Replace `logger.info(f"Starting webhook at {webhook_url}")` with a parameterized message containing only `config.bot.webhook_domain`; do not include `path`, `webhook_url`, or the token.

- [ ] **Step 6: Run logging tests**

Run: `pytest tests_new/unit/test_logging_config.py tests_new/unit/test_config_bot.py -q`

Expected: all tests pass and captured output contains neither the test token nor `/123456:ABC_secret`.

- [ ] **Step 7: Commit logging hardening**

```bash
git add app/logging_config.py app/config.py app/main.py tests_new/unit/test_logging_config.py tests_new/unit/test_config_bot.py
git commit -m "security(logging): redact Telegram credentials"
```

### Task 5: Full local verification and documentation

**Files:**
- Modify: `docs/TESTING.md`

**Interfaces:**
- Consumes: all behavior from Tasks 1-4.
- Produces: documented staging smoke-test commands and acceptance criteria.

- [ ] **Step 1: Run format, lint, and focused unit tests**

Run the repository-supported commands from `pyproject.toml`/Makefile, then:

```bash
pytest tests_new/unit -q
```

Expected: zero failures. If an unrelated pre-existing failure appears, record its exact test and traceback separately; do not weaken or skip it as part of this incident fix.

- [ ] **Step 2: Run integration tests**

Run: `pytest tests_new/integration -q`

Expected: zero new failures relative to the current staging baseline.

- [ ] **Step 3: Document staging smoke cases**

Add these incident-derived cases to `docs/TESTING.md` without user IDs or tokens:

- payload shortlink resolving to listing `100324065`;
- canonical listings `87485016`, `99406229`, and `102514433`;
- expected valid outcome: one successful item calculation and no blocked-page seller advisory;
- expected blocked outcome: `Grailed page blocked` warning, no seller extraction, no token/raw Telegram update in logs;
- expected retry outcome: at most two headless page attempts for an incomplete page.

- [ ] **Step 4: Commit documentation**

```bash
git add docs/TESTING.md
git commit -m "docs: add Grailed staging incident checks"
```

### Task 6: Staging deployment and production safety gate

**Files:**
- No repository changes unless verification finds a reproducible defect.

**Interfaces:**
- Consumes: Railway staging service on branch `staging`.
- Produces: evidence-backed go/no-go decision for production.

- [ ] **Step 1: Push staging only after local verification**

Run: `git push origin staging`

Expected: Railway creates a staging deployment for the verified commit. Do not promote to `main` in this step.

- [ ] **Step 2: Confirm deployment identity and health**

Verify Railway staging reports `SUCCESS` and its commit hash equals local `git rev-parse staging`. Review build logs for dependency/browser installation errors and runtime logs for startup exceptions.

- [ ] **Step 3: Execute staging smoke cases**

Send the four documented Grailed URLs to the staging bot. For each request, capture only timestamp, listing ID, outcome state, and duration. Do not copy chat IDs, usernames, message bodies, or bot tokens into the report.

- [ ] **Step 4: Apply the production gate**

Proceed only if all conditions hold:

- shortlink payload resolves to its canonical listing;
- valid listing HTML produces correct price/title;
- blocked HTML never produces a seller rating or item calculation;
- an incomplete page is retried no more than once;
- Railway logs contain no Telegram token or raw update payload;
- unit and integration suites remain green.

- [ ] **Step 5: Rotate Telegram credentials before production promotion**

With explicit user confirmation, revoke the exposed production token in BotFather, update Railway `BOT_TOKEN`, redeploy production, and verify webhook startup without printing the token. Rotate the staging token as well if its logs ever contained the same secret-bearing HTTP traces.

- [ ] **Step 6: Promote through the normal branch workflow**

Merge `staging` into `main`, verify that Railway production deploys the merge commit, and repeat one payload shortlink plus one canonical listing smoke test.

- [ ] **Step 7: Monitor the first production window**

Review production logs after the first real Grailed requests. Acceptance criteria are explicit `listing`, `blocked`, or `incomplete` states, no generic `No data extracted` without preceding state, no false seller metrics, and no sensitive log content.

---

## Final Verification Checklist

- [ ] `pytest tests_new/unit -q` passes.
- [ ] `pytest tests_new/integration -q` has no new failures.
- [ ] No fixed `wait_for_timeout(1500)` remains in Grailed listing fetch.
- [ ] No HTML-length heuristic decides whether a Grailed page is valid.
- [ ] Seller extraction occurs only after a valid item price is present.
- [ ] Root production logging defaults to `INFO`; third-party HTTP clients use `WARNING`.
- [ ] Token and raw Telegram update searches return no runtime-log matches.
- [ ] Staging commit hash matches the Railway deployment tested.
- [ ] Production token is rotated before promotion.
