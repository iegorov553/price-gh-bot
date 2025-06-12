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
from datetime import UTC, datetime, timedelta

try:
    from playwright.async_api import Browser, BrowserContext, Page, async_playwright
    PLAYWRIGHT_AVAILABLE = True
except ImportError:
    # Fallback types when playwright is not available
    Browser = None
    BrowserContext = None
    Page = None
    async_playwright = None
    PLAYWRIGHT_AVAILABLE = False

from ..models import SellerData

logger = logging.getLogger(__name__)


class HeadlessBrowser:
    """Headless browser manager for dynamic content extraction."""

    def __init__(self):
        self.browser: Browser | None = None
        self.context: BrowserContext | None = None
        self.playwright = None

    async def __aenter__(self):
        """Async context manager entry."""
        await self.start()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit."""
        await self.stop()

    async def start(self) -> None:
        """Start the headless browser."""
        if not PLAYWRIGHT_AVAILABLE:
            raise ImportError("Playwright not available - install with: pip install playwright")

        try:
            self.playwright = await async_playwright().start()

            # Launch browser with human-like configuration
            self.browser = await self.playwright.chromium.launch(
                headless=True,
                args=[
                    '--no-sandbox',
                    '--disable-setuid-sandbox',
                    '--disable-dev-shm-usage',
                    '--no-first-run',
                    '--no-default-browser-check',
                    '--disable-background-timer-throttling',
                    '--disable-backgrounding-occluded-windows',
                    '--disable-renderer-backgrounding',
                    '--disable-extensions',
                    '--disable-plugins',
                    '--disable-javascript-harmony-shipping',
                    '--disable-ipc-flooding-protection',
                    '--aggressive-cache-discard',
                    '--memory-pressure-off',
                    # More human-like flags
                    '--disable-blink-features=AutomationControlled',
                    '--disable-features=VizDisplayCompositor'
                ]
            )

            # Create context with human-like behavior
            self.context = await self.browser.new_context(
                user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36',
                viewport={'width': 1366, 'height': 768},  # Common desktop resolution
                java_script_enabled=True,
                locale='en-US',
                timezone_id='America/New_York',
                extra_http_headers={
                    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7',
                    'Accept-Language': 'en-US,en;q=0.9',
                    'Accept-Encoding': 'gzip, deflate, br',
                    'Cache-Control': 'max-age=0',
                    'Connection': 'keep-alive',
                    'Upgrade-Insecure-Requests': '1',
                    'Sec-Fetch-Dest': 'document',
                    'Sec-Fetch-Mode': 'navigate',
                    'Sec-Fetch-Site': 'none',
                    'Sec-Fetch-User': '?1',
                    'sec-ch-ua': '"Google Chrome";v="131", "Chromium";v="131", "Not_A Brand";v="24"',
                    'sec-ch-ua-mobile': '?0',
                    'sec-ch-ua-platform': '"Windows"'
                }
            )

            # Block unnecessary resources to speed up loading
            await self.context.route('**/*', self._route_handler)

            logger.info("Headless browser started successfully")

        except Exception as e:
            logger.error(f"Failed to start headless browser: {e}")
            await self.stop()
            raise

    async def stop(self) -> None:
        """Stop the headless browser and cleanup resources."""
        try:
            if self.context:
                await self.context.close()
                self.context = None

            if self.browser:
                await self.browser.close()
                self.browser = None

            if self.playwright:
                await self.playwright.stop()
                self.playwright = None

            logger.debug("Headless browser stopped and cleaned up")

        except Exception as e:
            logger.warning(f"Error during browser cleanup: {e}")

    async def _route_handler(self, route):
        """Block unnecessary resources to speed up page loading."""
        resource_type = route.request.resource_type
        url = route.request.url

        # Block heavy media but keep essential resources for human-like appearance
        if resource_type in ['image', 'media', 'font']:
            await route.abort()
        # Block analytics and tracking - these are obviously bot-like
        elif any(domain in url for domain in ['google-analytics', 'googletagmanager', 'facebook', 'twitter', 'doubleclick', 'adsystem', 'siftscience', 'pinterest']):
            await route.abort()
        # Allow CSS for proper rendering (important for human-like behavior)
        # Allow JS for dynamic content
        # Allow XHR/fetch for data loading
        else:
            await route.continue_()

    async def get_page(self) -> Page:
        """Get a new page from the browser context with stealth settings."""
        if not self.context:
            raise RuntimeError("Browser not started. Call start() first.")

        page = await self.context.new_page()

        # Hide automation markers
        await page.add_init_script("""
            // Hide webdriver property
            Object.defineProperty(navigator, 'webdriver', {
                get: () => undefined,
            });

            // Mock chrome property
            window.chrome = {
                runtime: {},
                loadTimes: function() {},
                csi: function() {},
                app: {}
            };

            // Mock permissions
            const originalQuery = window.navigator.permissions.query;
            window.navigator.permissions.query = (parameters) => (
                parameters.name === 'notifications' ?
                    Promise.resolve({ state: Notification.permission }) :
                    originalQuery(parameters)
            );

            // Mock plugins
            Object.defineProperty(navigator, 'plugins', {
                get: () => [1, 2, 3, 4, 5],
            });

            // Mock languages
            Object.defineProperty(navigator, 'languages', {
                get: () => ['en-US', 'en'],
            });
        """)

        return page


# Global browser instance for reuse
_global_browser: HeadlessBrowser | None = None
_browser_lock = asyncio.Lock()


async def extract_seller_data_headless(url: str, headless_browser: HeadlessBrowser) -> SellerData | None:
    """Extract seller data using headless browser for dynamic content.

    Args:
        url: Grailed listing or profile URL to scrape
        headless_browser: Configured headless browser instance

    Returns:
        SellerData object with extracted metrics, or None if extraction fails
    """
    page = None
    try:
        page = await headless_browser.get_page()

        # Navigate to the page with human-like behavior
        logger.debug(f"Loading page with optimized headless browser: {url}")

        # Add human-like randomness to loading
        import random

        # Random delay before navigation (0.1-0.5s)
        await asyncio.sleep(random.uniform(0.1, 0.5))

        await page.goto(url, wait_until='domcontentloaded', timeout=15000)

        # Human-like wait with slight randomness (0.8-1.2s)
        await asyncio.sleep(random.uniform(0.8, 1.2))

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
            await page.wait_for_selector('text=/rating|review|seller|feedback/i', timeout=3000)
        except Exception:
            logger.debug("No seller elements detected within timeout")

        # Extract rating
        rating_selectors = [
            '[data-testid*="rating"]',
            '.rating',
            '.seller-rating',
            'text=/[0-5]\\.[0-9]/',
            '[aria-label*="rating"]'
        ]

        for selector in rating_selectors:
            try:
                elements = await page.query_selector_all(selector)
                for element in elements:
                    text = await element.text_content()
                    if text:
                        # Try to extract rating value
                        import re
                        rating_match = re.search(r'([0-5]\.[0-9])', text)
                        if rating_match:
                            rating_val = float(rating_match.group(1))
                            if 0 <= rating_val <= 5:
                                avg_rating = rating_val
                                logger.debug(f"Found rating with headless: {avg_rating}")
                                break
                if avg_rating > 0:
                    break
            except Exception:
                continue

        # Extract review count
        review_selectors = [
            '[data-testid*="review"]',
            '.review-count',
            '.feedback-count',
            'text=/\\d+ review/i',
            '[aria-label*="review"]'
        ]

        for selector in review_selectors:
            try:
                elements = await page.query_selector_all(selector)
                for element in elements:
                    text = await element.text_content()
                    if text:
                        # Try to extract review count
                        import re
                        review_match = re.search(r'(\d+)', text)
                        if review_match:
                            review_val = int(review_match.group(1))
                            if review_val >= 0:
                                num_reviews = review_val
                                logger.debug(f"Found review count with headless: {num_reviews}")
                                break
                if num_reviews > 0:
                    break
            except Exception:
                continue

        # Extract trusted badge
        trusted_selectors = [
            '.trusted-badge',
            '.verified-seller',
            '[data-testid*="trusted"]',
            '[data-testid*="verified"]',
            'text=/trusted|verified/i',
            '[aria-label*="trusted"]'
        ]

        for selector in trusted_selectors:
            try:
                element = await page.query_selector(selector)
                if element:
                    trusted_badge = True
                    logger.debug("Found trusted badge with headless")
                    break
            except Exception:
                continue

        # Strategy 2: Extract from JavaScript variables/state
        if avg_rating == 0.0 and num_reviews == 0:
            try:
                # Execute JavaScript to extract data from window objects
                js_result = await page.evaluate("""
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
                """)

                if js_result:
                    avg_rating = js_result.get('rating', 0.0)
                    num_reviews = js_result.get('reviews', 0)
                    trusted_badge = js_result.get('trusted', False)
                    logger.debug(f"Found seller data via JavaScript: rating={avg_rating}, reviews={num_reviews}, trusted={trusted_badge}")

            except Exception as e:
                logger.debug(f"JavaScript extraction failed: {e}")

        # Extract last activity timestamp from seller profile page
        last_updated = datetime.now(UTC)  # fallback
        try:
            # Human-like scrolling to trigger content loading
            import random

            # Gradual scroll down like a human
            await page.evaluate('window.scrollTo(0, document.body.scrollHeight / 2)')
            await page.wait_for_timeout(random.randint(400, 600))
            await page.evaluate('window.scrollTo(0, document.body.scrollHeight)')
            await page.wait_for_timeout(random.randint(800, 1200))

            # Scroll back up gradually
            await page.evaluate('window.scrollTo(0, document.body.scrollHeight / 2)')
            await page.wait_for_timeout(random.randint(200, 400))
            await page.evaluate('window.scrollTo(0, 0)')
            await page.wait_for_timeout(random.randint(300, 500))

            # Look for "X days/weeks/months ago" text patterns in the page
            activity_text = await page.evaluate("""
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
            """)

            if activity_text and activity_text['firstMatch']:
                first_match = activity_text['firstMatch']
                logger.debug(f"Found activity text: {first_match['fullMatch']}")
                logger.debug(f"All matches: {[m['fullMatch'] for m in activity_text['allMatches']]}")

                # Convert relative time to actual datetime
                now = datetime.now(UTC)
                number = first_match['number']
                unit = first_match['unit']

                if unit in ['second', 'seconds']:
                    last_updated = now - timedelta(seconds=number)
                elif unit in ['minute', 'minutes']:
                    last_updated = now - timedelta(minutes=number)
                elif unit in ['hour', 'hours']:
                    last_updated = now - timedelta(hours=number)
                elif unit in ['day', 'days']:
                    last_updated = now - timedelta(days=number)
                elif unit in ['week', 'weeks']:
                    last_updated = now - timedelta(weeks=number)
                elif unit in ['month', 'months']:
                    # Approximate: 1 month = 30 days
                    last_updated = now - timedelta(days=number * 30)
                elif unit in ['year', 'years']:
                    # Approximate: 1 year = 365 days
                    last_updated = now - timedelta(days=number * 365)

                logger.debug(f"Converted '{first_match['fullMatch']}' to timestamp: {last_updated}")
            else:
                logger.debug(f"No activity text found. Sample: {activity_text.get('bodyTextSample', 'No text') if activity_text else 'No data'}")

        except Exception as e:
            logger.debug(f"Failed to extract activity timestamp: {e}")

        # Return results if we found any data
        if avg_rating > 0 or num_reviews > 0 or trusted_badge:
            return SellerData(
                num_reviews=num_reviews,
                avg_rating=avg_rating,
                trusted_badge=trusted_badge,
                last_updated=last_updated
            )

        return None

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
    try:
        browser = await get_global_browser()
        return await extract_seller_data_headless(url, browser)
    except Exception as e:
        logger.error(f"Global browser extraction failed: {e}")
        # Fallback to new browser instance
        async with HeadlessBrowser() as browser:
            return await extract_seller_data_headless(url, browser)


async def get_global_browser() -> HeadlessBrowser:
    """Get or create a global browser instance for reuse."""
    global _global_browser

    async with _browser_lock:
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
