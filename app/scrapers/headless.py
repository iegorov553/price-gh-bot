"""Headless browser scraper for dynamic content extraction.

This module provides headless browser functionality using Playwright to extract
seller data that is loaded dynamically via JavaScript on Grailed listing and
profile pages. Used as a fallback when static HTML parsing fails to find
seller metrics.

Key features:
- Playwright-based browser automation for dynamic content
- Seller data extraction after JavaScript execution
- Configurable wait times for dynamic loading
- Error handling and resource cleanup
- Performance optimization with minimal browser overhead
"""

import asyncio
import logging
import re
import shlex
import time
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from secrets import randbelow
from typing import TYPE_CHECKING, Any, cast
from urllib.parse import urlsplit, urlunsplit

from ..models import SellerData
from .grailed_page import GrailedPageState, classify_grailed_html

PlaywrightTimeoutError: type[BaseException]

try:
    from playwright.async_api import TimeoutError as _PlaywrightTimeoutError
    from playwright.async_api import async_playwright

    PlaywrightTimeoutError = _PlaywrightTimeoutError
    PLAYWRIGHT_AVAILABLE = True
except ImportError:
    async_playwright = None  # type: ignore[assignment]
    PlaywrightTimeoutError = TimeoutError
    PLAYWRIGHT_AVAILABLE = False

if TYPE_CHECKING:
    from playwright.async_api import Browser, BrowserContext, ElementHandle, Page, Playwright
else:
    Browser = BrowserContext = ElementHandle = Page = Playwright = Any  # type: ignore

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class GrailedHeadlessFetchResult:
    """Classified result of a headless Grailed page acquisition."""

    html: str | None
    state: GrailedPageState


def _random_delay(min_seconds: float, max_seconds: float) -> float:
    """Generate a cryptographically strong pseudo-random delay between bounds."""
    if max_seconds <= min_seconds:
        return min_seconds
    span_ms = int((max_seconds - min_seconds) * 1000)
    return min_seconds + randbelow(span_ms + 1) / 1000


def _random_timeout(min_ms: int, max_ms: int) -> int:
    """Generate a timeout using cryptographically strong randomness."""
    if max_ms <= min_ms:
        return min_ms
    return min_ms + randbelow(max_ms - min_ms + 1)


def _safe_target(url: str) -> tuple[str, str]:
    """Return a credential-free URL and public listing identifier for logs."""
    try:
        parsed_url = urlsplit(url)
        hostname = parsed_url.hostname or ""
        authority = f"[{hostname}]" if ":" in hostname else hostname
        if parsed_url.port is not None:
            authority = f"{authority}:{parsed_url.port}"
        canonical_url = urlunsplit((parsed_url.scheme, authority, parsed_url.path, "", ""))
        match = re.search(r"/listings/(\d+)", parsed_url.path)
        return canonical_url, match.group(1) if match else "unknown"
    except ValueError:
        return "<invalid-url>", "unknown"


class HeadlessBrowser:
    """Headless browser manager for dynamic content extraction."""

    def __init__(self) -> None:
        """Initialize headless browser placeholders."""
        self.browser: Browser | None = None
        self.context: BrowserContext | None = None
        self.playwright: Playwright | None = None
        self._install_attempted: bool = False

    async def __aenter__(self) -> "HeadlessBrowser":
        """Async context manager entry."""
        await self.start()
        return self

    async def __aexit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        """Async context manager exit."""
        await self.stop()

    async def start(self) -> None:
        """Start the headless browser."""
        if not PLAYWRIGHT_AVAILABLE or async_playwright is None:
            raise ImportError("Playwright not available - install with: pip install playwright")

        try:
            playwright_context = await async_playwright().start()
            self.playwright = playwright_context

            # Use Playwright's regular Chromium build in new headless mode.
            self.browser = await playwright_context.chromium.launch(
                channel="chromium",
                headless=True,
                args=[
                    "--no-sandbox",
                    "--disable-dev-shm-usage",
                ],
            )

            # Keep one stock context for the process lifetime so cookies persist.
            browser_instance = self.browser
            self.context = await browser_instance.new_context()

            logger.info(
                "Chromium browser started (mode=new-headless, version=%s)",
                browser_instance.version,
            )

        except Exception as e:
            logger.error(f"Failed to start headless browser: {e}")

            if not self._install_attempted and _needs_browser_install(str(e)):
                logger.warning("Playwright browsers missing; attempting automatic installation...")
                self._install_attempted = True
                success = await _ensure_playwright_browsers_installed()
                if success:
                    logger.info("Playwright browsers installed successfully, retrying launch.")
                    await self.stop()
                    await self.start()
                    return

            await self.stop()
            raise

    async def stop(self) -> None:
        """Stop the headless browser and cleanup resources."""
        context, browser, playwright = self.context, self.browser, self.playwright
        self.context = None
        self.browser = None
        self.playwright = None

        for resource_name, resource, close_method in (
            ("browser context", context, "close"),
            ("browser", browser, "close"),
            ("Playwright", playwright, "stop"),
        ):
            if resource is None:
                continue
            try:
                await getattr(resource, close_method)()
            except Exception as exc:
                logger.warning("Error during %s cleanup: %s", resource_name, exc)

        logger.debug("Headless browser stopped and cleaned up")

    async def get_page(self) -> Page:
        """Get a new page from the persistent stock browser context."""
        if self.context is None:
            raise RuntimeError("Browser not started. Call start() first.")

        return await self.context.new_page()

    def is_connected(self) -> bool:
        """Return whether the underlying Chromium process is connected."""
        if self.browser is None:
            return False
        try:
            return bool(self.browser.is_connected())
        except Exception:
            return False


# Global browser instance for reuse
_global_browser: HeadlessBrowser | None = None
_browser_lock = asyncio.Lock()
_browser_operation_lock = asyncio.Lock()


async def extract_seller_data_headless(
    url: str, headless_browser: HeadlessBrowser
) -> SellerData | None:
    """Extract seller data using headless browser for dynamic content.

    Args:
        url: Grailed listing or profile URL to scrape
        headless_browser: Configured headless browser instance

    Returns:
        SellerData object with extracted metrics, or None if extraction fails
    """
    page: Page | None = None
    try:
        page = await headless_browser.get_page()

        # Navigate to the page with human-like behavior
        logger.debug(f"Loading page with optimized headless browser: {url}")

        # Add human-like randomness to loading
        # Random delay before navigation (0.1-0.5s)
        await asyncio.sleep(_random_delay(0.1, 0.5))

        await page.goto(url, wait_until="domcontentloaded", timeout=15000)

        # Human-like wait with slight randomness (0.8-1.2s)
        await asyncio.sleep(_random_delay(0.8, 1.2))

        # Try to find seller data in the rendered page
        seller_data = await _extract_dynamic_seller_data(page)

        if seller_data:
            logger.info(f"Successfully extracted seller data with headless browser: {seller_data}")
            return seller_data
        else:
            logger.warning(f"No seller data found with headless browser for: {url}")
            return None

    except Exception as e:
        logger.error(f"Headless browser extraction failed for {url}: {e}")
        return None
    finally:
        if page:
            await page.close()


async def _extract_dynamic_seller_data(page: Page) -> SellerData | None:
    """Extract seller data from a rendered page."""
    try:
        # Strategy 1: Wait for seller elements to appear and extract data

        avg_rating = 0.0
        num_reviews = 0
        trusted_badge = False

        # Quick check for seller elements - reduced timeout
        try:
            await page.wait_for_selector("text=/rating|review|seller|feedback/i", timeout=3000)
        except Exception:
            logger.debug("No seller elements detected within timeout")

        # Extract rating
        rating_selectors = [
            '[data-testid*="rating"]',
            ".rating",
            ".seller-rating",
            "text=/[0-5]\\.[0-9]/",
            '[aria-label*="rating"]',
        ]

        for selector in rating_selectors:
            try:
                rating_elements = await page.query_selector_all(selector)
                for element in rating_elements:
                    text = await element.text_content()
                    if text:
                        rating_match = re.search(r"([0-5]\.[0-9])", text)
                        if rating_match:
                            rating_val = float(rating_match.group(1))
                            if 0 <= rating_val <= 5:
                                avg_rating = rating_val
                                logger.debug(f"Found rating with headless: {avg_rating}")
                                break
                if avg_rating > 0:
                    break
            except Exception as selector_error:
                logger.debug(
                    "Failed to extract rating via selector %s: %s", selector, selector_error
                )

        # Extract review count
        review_selectors = [
            '[data-testid*="review"]',
            ".review-count",
            ".feedback-count",
            "text=/\\d+ review/i",
            '[aria-label*="review"]',
        ]

        for selector in review_selectors:
            try:
                review_elements = await page.query_selector_all(selector)
                for element in review_elements:
                    text = await element.text_content()
                    if text:
                        review_match = re.search(r"(\d+)", text)
                        if review_match:
                            review_val = int(review_match.group(1))
                            if review_val >= 0:
                                num_reviews = review_val
                                logger.debug(f"Found review count with headless: {num_reviews}")
                                break
                if num_reviews > 0:
                    break
            except Exception as selector_error:
                logger.debug(
                    "Failed to extract review count via selector %s: %s", selector, selector_error
                )

        # Extract trusted badge
        trusted_selectors = [
            ".trusted-badge",
            ".verified-seller",
            '[data-testid*="trusted"]',
            '[data-testid*="verified"]',
            "text=/trusted|verified/i",
            '[aria-label*="trusted"]',
        ]

        for selector in trusted_selectors:
            try:
                handle = await page.query_selector(selector)
                if handle is not None:
                    trusted_badge = True
                    logger.debug("Found trusted badge with headless")
                    break
            except Exception as selector_error:
                logger.debug(
                    "Failed to detect trusted badge via selector %s: %s", selector, selector_error
                )

        # Strategy 2: Extract from JavaScript variables/state
        if avg_rating == 0.0 and num_reviews == 0:
            try:
                # Execute JavaScript to extract data from window objects
                js_result = cast(
                    dict[str, Any] | None,
                    await page.evaluate(
                        """
                        () => {
                            // Look for common JavaScript data structures
                        const sources = [
                            window.__PRELOADED_STATE__,
                            window.__INITIAL_STATE__,
                            window.__APOLLO_STATE__,
                            window.grailed,
                            window.APP_STATE
                        ];

                        for (const source of sources) {
                            if (source && typeof source === 'object') {
                                const jsonStr = JSON.stringify(source);

                                // Look for seller data patterns
                                const ratingMatch = jsonStr.match(/"(?:rating|averageRating|sellerRating)"\\s*:\\s*([0-5]\\.[0-9]+)/);
                                const reviewMatch = jsonStr.match(/"(?:reviewCount|totalReviews|reviews)"\\s*:\\s*(\\d+)/);
                                const trustedMatch = jsonStr.match(/"(?:trusted|trustedSeller|verified)"\\s*:\\s*true/);

                                if (ratingMatch || reviewMatch || trustedMatch) {
                                    return {
                                        rating: ratingMatch ? parseFloat(ratingMatch[1]) : 0,
                                        reviews: reviewMatch ? parseInt(reviewMatch[1]) : 0,
                                        trusted: !!trustedMatch
                                    };
                                }
                            }
                        }

                        return null;
                    }
                """
                    ),
                )

                if js_result:
                    avg_rating = float(js_result.get("rating", 0.0))
                    num_reviews = int(js_result.get("reviews", 0))
                    trusted_badge = bool(js_result.get("trusted", False))
                    logger.debug(
                        f"Found seller data via JavaScript: rating={avg_rating}, reviews={num_reviews}, trusted={trusted_badge}"
                    )

            except Exception as e:
                logger.debug(f"JavaScript extraction failed: {e}")

        # Extract last activity timestamp from seller profile page
        last_updated = datetime.now(UTC)  # fallback
        try:
            # Human-like scrolling to trigger content loading

            # Gradual scroll down like a human
            await page.evaluate("window.scrollTo(0, document.body.scrollHeight / 2)")
            await page.wait_for_timeout(_random_timeout(400, 600))
            await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
            await page.wait_for_timeout(_random_timeout(800, 1200))

            # Scroll back up gradually
            await page.evaluate("window.scrollTo(0, document.body.scrollHeight / 2)")
            await page.wait_for_timeout(_random_timeout(200, 400))
            await page.evaluate("window.scrollTo(0, 0)")
            await page.wait_for_timeout(_random_timeout(300, 500))

            # Look for "X days/weeks/months ago" text patterns in the page
            activity_text = cast(
                dict[str, Any] | None,
                await page.evaluate(
                    """
                    () => {
                        // Look for relative time patterns like "5 days ago"
                    const timeAgoPattern = /\\b(\\d+)\\s+(second|minute|hour|day|week|month|year)s?\\s*ago\\b/gi;
                    const bodyText = document.body.innerText || document.body.textContent || '';

                    // Find all matches
                    const matches = [];
                    let match;
                    while ((match = timeAgoPattern.exec(bodyText)) !== null) {
                        matches.push({
                            fullMatch: match[0],
                            number: parseInt(match[1]),
                            unit: match[2].toLowerCase()
                        });
                    }

                    return {
                        allMatches: matches,
                        firstMatch: matches.length > 0 ? matches[0] : null,
                        bodyTextSample: bodyText.substring(0, 300)
                    };
                }
            """
                ),
            )

            if activity_text and activity_text.get("firstMatch"):
                first_match = cast(dict[str, Any], activity_text["firstMatch"])
                logger.debug(f"Found activity text: {first_match['fullMatch']}")
                all_matches = cast(list[dict[str, Any]], activity_text.get("allMatches", []))
                logger.debug(f"All matches: {[m.get('fullMatch') for m in all_matches]}")

                # Convert relative time to actual datetime
                now = datetime.now(UTC)
                number = first_match["number"]
                unit = first_match["unit"]

                if unit in ["second", "seconds"]:
                    last_updated = now - timedelta(seconds=number)
                elif unit in ["minute", "minutes"]:
                    last_updated = now - timedelta(minutes=number)
                elif unit in ["hour", "hours"]:
                    last_updated = now - timedelta(hours=number)
                elif unit in ["day", "days"]:
                    last_updated = now - timedelta(days=number)
                elif unit in ["week", "weeks"]:
                    last_updated = now - timedelta(weeks=number)
                elif unit in ["month", "months"]:
                    # Approximate: 1 month = 30 days
                    last_updated = now - timedelta(days=number * 30)
                elif unit in ["year", "years"]:
                    # Approximate: 1 year = 365 days
                    last_updated = now - timedelta(days=number * 365)

                logger.debug(f"Converted '{first_match['fullMatch']}' to timestamp: {last_updated}")
            else:
                logger.debug(
                    f"No activity text found. Sample: {activity_text.get('bodyTextSample', 'No text') if activity_text else 'No data'}"
                )

        except Exception as e:
            logger.debug(f"Failed to extract activity timestamp: {e}")

        # Return results even if there are zero reviews so caller can show "no reviews" warning.
        return SellerData(
            num_reviews=num_reviews,
            avg_rating=avg_rating,
            trusted_badge=trusted_badge,
            last_updated=last_updated,
            technical_issue=False,
        )

    except Exception as e:
        logger.error(f"Error extracting dynamic seller data: {e}")
        return None


async def get_grailed_seller_data_headless(url: str) -> SellerData | None:
    """High-level function to extract Grailed seller data using headless browser.

    Args:
        url: Grailed listing or profile URL to scrape

    Returns:
        SellerData object with extracted metrics, or None if extraction fails
    """
    async with _browser_operation_lock:
        browser: HeadlessBrowser | None = None
        try:
            browser = await get_global_browser()
            return await extract_seller_data_headless(url, browser)
        except Exception as exc:
            logger.error("Global browser extraction failed (exception=%s)", type(exc).__name__)
            if browser is not None and browser.is_connected():
                return None
            try:
                await cleanup_global_browser()
                browser = await get_global_browser()
                return await extract_seller_data_headless(url, browser)
            except Exception as recovery_exc:
                logger.error(
                    "Headless browser recovery failed (exception=%s)",
                    type(recovery_exc).__name__,
                )
                return None


async def fetch_page_html_headless(url: str) -> str | None:
    """Fetch raw page HTML through the generic compatibility API.

    Args:
        url: Page URL to fetch.

    Returns:
        Acquired HTML text without Grailed classification, or None if fetching fails.
    """
    async with _browser_operation_lock:
        browser: HeadlessBrowser | None = None
        try:
            browser = await get_global_browser()
            return await _fetch_html(url, browser)
        except Exception as exc:
            logger.error(
                "Global browser compatibility HTML fetch failed (exception=%s)",
                type(exc).__name__,
            )
            if browser is not None and browser.is_connected():
                return None
            try:
                await cleanup_global_browser()
                browser = await get_global_browser()
                return await _fetch_html(url, browser)
            except Exception as recovery_exc:
                logger.error(
                    "Compatibility HTML fetch failed (exception=%s)",
                    type(recovery_exc).__name__,
                )
                return None


async def fetch_grailed_page_headless(url: str) -> GrailedHeadlessFetchResult:
    """Acquire a Grailed page while retaining its classified terminal state."""
    _canonical_url, listing_id = _safe_target(url)
    async with _browser_operation_lock:
        browser: HeadlessBrowser | None = None
        try:
            browser = await get_global_browser()
            return await _fetch_grailed_page_html(url, browser)
        except Exception as exc:
            logger.error(
                "Global browser HTML fetch failed (listing_id=%s, exception=%s)",
                listing_id,
                type(exc).__name__,
            )
            if browser is not None and browser.is_connected():
                return GrailedHeadlessFetchResult(None, GrailedPageState.INCOMPLETE)
            try:
                await cleanup_global_browser()
                browser = await get_global_browser()
                return await _fetch_grailed_page_html(url, browser)
            except Exception as recovery_exc:
                logger.error(
                    "Headless browser HTML fallback failed (listing_id=%s, exception=%s)",
                    listing_id,
                    type(recovery_exc).__name__,
                )
                return GrailedHeadlessFetchResult(None, GrailedPageState.INCOMPLETE)


async def _fetch_html(url: str, browser: HeadlessBrowser) -> str | None:
    """Fetch unclassified HTML for generic compatibility callers."""
    page = await browser.get_page()
    try:
        await page.goto(url, wait_until="domcontentloaded", timeout=25_000)
        await page.wait_for_timeout(1500)
        return await page.content()
    finally:
        await page.close()


async def _fetch_grailed_page_html(
    url: str, browser: HeadlessBrowser
) -> GrailedHeadlessFetchResult:
    """Fetch a Grailed listing only after its DOM reaches a known state."""
    canonical_url, listing_id = _safe_target(url)
    started_at = time.monotonic()
    last_http_status: int | None = None

    def finish(
        state: GrailedPageState,
        html: str | None,
        attempt: int,
        http_status: int | None,
    ) -> GrailedHeadlessFetchResult:
        browser_process = getattr(browser, "browser", None)
        browser_version = getattr(browser_process, "version", "unknown")
        logger.info(
            "Grailed browser acquisition finished (listing_id=%s, state=%s, "
            "http_status=%s, elapsed_ms=%s, chromium=%s, attempt=%s)",
            listing_id,
            state,
            http_status,
            int((time.monotonic() - started_at) * 1000),
            browser_version,
            attempt,
        )
        return GrailedHeadlessFetchResult(html, state)

    listing_ready_script = """() => document.querySelector(
        '#__NEXT_DATA__, meta[property="product:price:amount"], '
        + 'script[type="application/ld+json"]'
    ) !== null"""
    known_state_script = """() => {
        const html = document.documentElement.innerHTML.toLowerCase();
        const title = document.title.toLowerCase();
        return document.querySelector(
            '#__NEXT_DATA__, meta[property="product:price:amount"], '
            + 'script[type="application/ld+json"], #challenge-running, [class*="cf-chl-"]'
        ) !== null
            || title === 'just a moment...'
            || html.includes('you are unable to access grailed.com')
            || html.includes('checking your browser')
            || html.includes('performing security verification')
            || html.includes('this website uses a security service to protect against malicious bots')
            || html.includes('cf-chl-')
            || html.includes('challenge-running');
    }"""

    for attempt in range(1, 3):
        page: Page | None = None
        http_status: int | None = None
        try:
            page = await browser.get_page()
            response = await page.goto(url, wait_until="domcontentloaded", timeout=25_000)
            raw_status = getattr(response, "status", None)
            if isinstance(raw_status, int):
                http_status = raw_status
                last_http_status = raw_status

            initial_html = await page.content()
            initial_state = classify_grailed_html(initial_html)
            challenge_seen = initial_state is GrailedPageState.BLOCKED

            if initial_state is GrailedPageState.BLOCKED:
                # Keep the same page and cookies while a non-interactive challenge
                # has a chance to complete. A resolved challenge exposes listing data.
                try:
                    await page.wait_for_function(listing_ready_script, timeout=12_000)
                except PlaywrightTimeoutError:
                    pass
            elif initial_state is GrailedPageState.INCOMPLETE:
                try:
                    await page.wait_for_function(known_state_script, timeout=10_000)
                except PlaywrightTimeoutError:
                    pass

            html = await page.content()
        except Exception as exc:
            logger.warning(
                "Grailed headless fetch failed (attempt=%s, exception=%s, target=%s)",
                attempt,
                type(exc).__name__,
                canonical_url,
            )
            return finish(GrailedPageState.INCOMPLETE, None, attempt, http_status)
        finally:
            if page is not None:
                await page.close()

        state = classify_grailed_html(html)
        if state is GrailedPageState.LISTING:
            return finish(state, html, attempt, http_status)
        if challenge_seen:
            return finish(GrailedPageState.BLOCKED, None, attempt, http_status)
        if state is GrailedPageState.BLOCKED:
            return finish(state, None, attempt, http_status)

    return finish(GrailedPageState.INCOMPLETE, None, 2, last_http_status)


async def resolve_shortlink_headless(url: str) -> str | None:
    """Resolve a shortlink (e.g. grailed.app.link) by navigating with headless browser.

    Args:
        url: Shortlink URL.

    Returns:
        Final target URL after redirects, or None if failed.
    """
    async with _browser_operation_lock:
        browser: HeadlessBrowser | None = None
        try:
            browser = await get_global_browser()
            return await _resolve_redirect(url, browser)
        except Exception as exc:
            logger.error(
                "Global browser shortlink resolution failed (exception=%s)",
                type(exc).__name__,
            )
            if browser is not None and browser.is_connected():
                return None
            try:
                await cleanup_global_browser()
                browser = await get_global_browser()
                return await _resolve_redirect(url, browser)
            except Exception as recovery_exc:
                logger.error(
                    "Headless browser shortlink recovery failed (exception=%s)",
                    type(recovery_exc).__name__,
                )
                return None


async def _resolve_redirect(url: str, browser: HeadlessBrowser) -> str | None:
    page = await browser.get_page()
    try:
        await page.goto(url, wait_until="domcontentloaded", timeout=20000)
        final_url = page.url
        if final_url and final_url != url:
            return final_url
        return None
    finally:
        await page.close()


async def get_global_browser() -> HeadlessBrowser:
    """Get or create a global browser instance for reuse."""
    global _global_browser

    async with _browser_lock:
        if _global_browser is not None and not _global_browser.is_connected():
            await _global_browser.stop()
            _global_browser = None
        if _global_browser is None:
            _global_browser = HeadlessBrowser()
            await _global_browser.start()
        return _global_browser


async def cleanup_global_browser() -> None:
    """Cleanup the global browser instance."""
    global _global_browser

    async with _browser_lock:
        if _global_browser is not None:
            await _global_browser.stop()
            _global_browser = None


def _needs_browser_install(message: str) -> bool:
    lowered = message.lower()
    return "executable doesn't exist" in lowered or "playwright install" in lowered


async def _ensure_playwright_browsers_installed() -> bool:
    """Attempt to install Playwright Chromium binaries on demand."""
    try:
        cmd = ["playwright", "install", "--no-shell", "chromium"]
        logger.info("Running %s", " ".join(shlex.quote(part) for part in cmd))
        process = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
        )
        stdout, _ = await process.communicate()
        if stdout:
            logger.info(stdout.decode(errors="ignore"))
        if process.returncode == 0:
            return True

        logger.error("playwright install chromium exited with %s", process.returncode)
        return False
    except Exception as exc:
        logger.error(f"Automatic Playwright installation failed: {exc}")
        return False
