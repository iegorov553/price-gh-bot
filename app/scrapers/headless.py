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
from datetime import UTC, datetime
from typing import Any

from playwright.async_api import Browser, BrowserContext, Page, async_playwright

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
        try:
            self.playwright = await async_playwright().start()
            
            # Launch browser with minimal overhead
            self.browser = await self.playwright.chromium.launch(
                headless=True,
                args=[
                    '--no-sandbox',
                    '--disable-setuid-sandbox',
                    '--disable-dev-shm-usage',
                    '--disable-gpu',
                    '--no-first-run',
                    '--no-default-browser-check',
                    '--disable-background-timer-throttling',
                    '--disable-backgrounding-occluded-windows',
                    '--disable-renderer-backgrounding'
                ]
            )
            
            # Create context with realistic user agent
            self.context = await self.browser.new_context(
                user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                viewport={'width': 1920, 'height': 1080}
            )
            
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
    
    async def get_page(self) -> Page:
        """Get a new page from the browser context."""
        if not self.context:
            raise RuntimeError("Browser not started. Call start() first.")
        return await self.context.new_page()


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
        
        # Navigate to the page
        logger.debug(f"Loading page with headless browser: {url}")
        await page.goto(url, wait_until='networkidle', timeout=30000)
        
        # Wait for potential dynamic content to load
        await asyncio.sleep(2)
        
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
        seller_selectors = [
            '[data-testid*="rating"]',
            '[data-testid*="review"]', 
            '[data-testid*="seller"]',
            '.rating',
            '.review-count',
            '.seller-rating',
            '.feedback',
            '.trusted-badge',
            '.verified-seller'
        ]
        
        avg_rating = 0.0
        num_reviews = 0
        trusted_badge = False
        
        # Wait for any seller-related elements to load
        try:
            await page.wait_for_selector('text=/rating|review|seller|feedback/i', timeout=10000)
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
        
        # Return results if we found any data
        if avg_rating > 0 or num_reviews > 0 or trusted_badge:
            return SellerData(
                num_reviews=num_reviews,
                avg_rating=avg_rating,
                trusted_badge=trusted_badge,
                last_updated=datetime.now(UTC)
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
    async with HeadlessBrowser() as browser:
        return await extract_seller_data_headless(url, browser)