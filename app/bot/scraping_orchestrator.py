"""Scraping orchestration and coordination for marketplace data extraction.

Coordinates scraping operations across different platforms, handles
concurrent processing, error recovery, and data aggregation.
"""

import asyncio
import logging
from datetime import datetime
from typing import cast

import aiohttp

from ..models import SearchAnalytics
from ..scrapers import scraper_registry
from ..services.analytics import analytics_service
from ..services.cache_service import CacheService, get_cache_service
from ..services.seller_assessment import evaluate_seller_advisory
from .types import BaseScrapeResult, ItemScrapeResult, SellerScrapeResult
from .utils import create_session

logger = logging.getLogger(__name__)


class ScrapingOrchestrator:
    """Orchestrates scraping operations across multiple platforms.

    Responsibilities:
    - Coordinate scraping across eBay/Grailed platforms
    - Handle concurrent URL processing
    - Manage error recovery and fallbacks
    - Aggregate and normalize data from different sources
    - Track analytics for all scraping operations
    """

    def __init__(self) -> None:
        """Initialize scraping orchestrator."""
        self.max_concurrent_urls: int = 5
        self.cache_service: CacheService | None = None

    async def _ensure_cache_service(self) -> None:
        """Ensures cache service is initialized."""
        if self.cache_service is None:
            self.cache_service = await get_cache_service()

    @staticmethod
    def _is_cached_result_valid(cached: ItemScrapeResult | None) -> bool:
        """Check if cached scraping result can be reused."""
        if not cached:
            return False

        if not cached.get("success"):
            return False

        item_data = cached.get("item_data")
        if not item_data:
            return False

        price = getattr(item_data, "price", None)
        if price is None:
            return False

        return True

    async def scrape_item_listing_with_cache(
        self, url: str, session: aiohttp.ClientSession
    ) -> ItemScrapeResult:
        """Scrape item listing with Redis caching for instant repeated requests.

        Ожидаемое ускорение: повторные запросы 8-10с → <1с (95%)

        Args:
            url: Item listing URL
            session: HTTP session for requests

        Returns:
            Dictionary with item data and cache metadata
        """
        await self._ensure_cache_service()
        cache_service = self.cache_service
        if cache_service is None:
            raise RuntimeError("Cache service unavailable")
        start_time = datetime.now()

        # Проверяем кэш
        cached_data_raw = await cache_service.get_item_data(url)
        cached_data = cast(ItemScrapeResult | None, cached_data_raw)
        if self._is_cached_result_valid(cached_data):
            if cached_data is None:
                logger.warning(
                    "Валидность кэша для %s подтверждена, но данные отсутствуют. Запрос повторно обработан.",
                    url,
                )
            else:
                processing_time = int((datetime.now() - start_time).total_seconds() * 1000)
                logger.info(f"Кэш попадание для {url} (время: {processing_time}мс)")

                # Добавляем информацию о кэше
                cached_result: ItemScrapeResult = cached_data.copy()
                cached_result["from_cache"] = True
                cached_result["cache_processing_time_ms"] = processing_time
                return cached_result
        elif cached_data:
            logger.info(f"Сбрасываем устаревший кэш для {url}")

        # Обычная обработка
        result = await self.scrape_item_listing(url, session)

        # Кэшируем успешные результаты
        if result["success"] and result["item_data"]:
            await cache_service.set_item_data(url, dict(result))
            logger.debug(f"Результат закэширован для {url}")

        result["from_cache"] = False
        return result

    async def scrape_item_listing(
        self, url: str, session: aiohttp.ClientSession
    ) -> ItemScrapeResult:
        """Scrape individual item listing from marketplace.

        Args:
            url: Item listing URL.
            session: HTTP session for requests.

        Returns:
            Dictionary with item data and metadata:
            {
                'success': bool,
                'platform': str,
                'item_data': ItemData | None,
                'seller_data': SellerData | None,
                'error': str | None,
                'processing_time_ms': int
            }
        """
        start_time = datetime.now()

        # Find appropriate scraper using registry
        scraper = scraper_registry.get_scraper_for_url(url)
        if not scraper:
            return cast(
                ItemScrapeResult,
                {
                    "success": False,
                    "platform": "unknown",
                    "item_data": None,
                    "seller_data": None,
                    "seller_advisory": None,
                    "error": "No scraper found for URL",
                    "processing_time_ms": 0,
                    "url": url,
                },
            )

        platform = scraper.get_platform_name()
        result: ItemScrapeResult = {
            "success": False,
            "platform": platform,
            "item_data": None,
            "seller_data": None,
            "seller_advisory": None,
            "error": None,
            "processing_time_ms": 0,
            "url": url,
        }

        try:
            logger.info(f"Scraping {platform} item: {url}")

            # Use unified scraper interface
            item_data = await scraper.scrape_item(url, session)

            if item_data:
                result["success"] = True
                result["item_data"] = item_data

                # Try to get seller data if scraper supports it
                try:
                    seller_profile_url = scraper.extract_seller_profile_url(item_data)
                    if seller_profile_url:
                        seller_data = await scraper.scrape_seller(seller_profile_url, session)
                        if seller_data:
                            result["seller_data"] = seller_data
                except Exception as e:
                    logger.warning(f"Failed to get seller data for {url}: {e}")

                logger.info(f"Successfully scraped {platform} item: {item_data.title}")
            else:
                result["error"] = f"No data extracted from {platform}"

        except Exception as e:
            result["error"] = str(e)
            logger.error(f"Failed to scrape {url}: {e}")

        finally:
            end_time = datetime.now()
            result["processing_time_ms"] = int((end_time - start_time).total_seconds() * 1000)

        return result

    async def scrape_seller_profile(
        self, url: str, session: aiohttp.ClientSession
    ) -> SellerScrapeResult:
        """Scrape seller profile data.

        Args:
            url: Seller profile URL.
            session: HTTP session for requests.

        Returns:
            Dictionary with seller analysis results.
        """
        start_time = datetime.now()

        result: SellerScrapeResult = {
            "success": False,
            "seller_data": None,
            "seller_advisory": None,
            "error": None,
            "processing_time_ms": 0,
            "url": url,
            "platform": "profile",
        }

        try:
            logger.info(f"Analyzing seller profile: {url}")

            # Find appropriate scraper for seller profile
            scraper = scraper_registry.get_scraper_for_url(url)
            if not scraper:
                result["error"] = "No scraper found for seller profile URL"
                return result

            # Check if scraper supports seller profiles
            if not scraper.is_seller_profile(url):
                result["error"] = "URL is not a seller profile"
                return result

            # Extract seller data using unified interface
            seller_data = await scraper.scrape_seller(url, session)

            if seller_data:
                result["success"] = True
                result["seller_data"] = seller_data

                seller_advisory = evaluate_seller_advisory(seller_data=seller_data)
                result["seller_advisory"] = seller_advisory

                if seller_advisory.message:
                    logger.info(f"Seller advisory triggered for profile: {seller_advisory.reason}")
                else:
                    logger.info("Seller profile has no advisory warnings")
            else:
                result["error"] = "No seller data found"

        except Exception as e:
            result["error"] = str(e)
            logger.error(f"Failed to analyze seller {url}: {e}")

        finally:
            end_time = datetime.now()
            result["processing_time_ms"] = int((end_time - start_time).total_seconds() * 1000)

        return result

    async def process_urls_concurrent(
        self, urls: list[str], user_id: int, username: str | None = None
    ) -> list[BaseScrapeResult]:
        """Process multiple URLs concurrently.

        Args:
            urls: List of URLs to process.
            user_id: User ID for analytics.
            username: Username for analytics.

        Returns:
            List of processing results for each URL.
        """
        if not urls:
            return []

        async with create_session() as session:
            # Create semaphore to limit concurrent requests
            semaphore = asyncio.Semaphore(self.max_concurrent_urls)

            async def process_single_url(url: str) -> BaseScrapeResult:
                async with semaphore:
                    # Find scraper for URL
                    scraper = scraper_registry.get_scraper_for_url(url)
                    if not scraper:
                        return {
                            "success": False,
                            "error": "No scraper found for URL",
                            "url": url,
                            "platform": "unknown",
                            "processing_time_ms": 0,
                        }

                    # Check if it's a seller profile or item listing
                    if scraper.is_seller_profile(url):
                        return await self.scrape_seller_profile(url, session)
                    else:
                        # Используем кэширование для товаров
                        return await self.scrape_item_listing_with_cache(url, session)

            # Process all URLs concurrently
            results = await asyncio.gather(
                *[process_single_url(url) for url in urls], return_exceptions=True
            )

            # Handle exceptions and log analytics
            processed_results: list[BaseScrapeResult] = []
            for i, raw_result in enumerate(results):
                url = urls[i]

                if isinstance(raw_result, Exception):
                    # Try to detect platform for error logging
                    scraper = scraper_registry.get_scraper_for_url(url)
                    platform = scraper.get_platform_name() if scraper else "unknown"

                    result_dict: BaseScrapeResult = {
                        "success": False,
                        "error": str(raw_result),
                        "url": url,
                        "platform": platform,
                        "processing_time_ms": 0,
                    }
                else:
                    result_dict = cast(BaseScrapeResult, raw_result)

                processed_results.append(result_dict)

                # Log to analytics
                await self._log_analytics(result_dict, user_id, username)

            return processed_results

    async def _log_analytics(
        self, result: BaseScrapeResult, user_id: int, username: str | None = None
    ) -> None:
        """Log scraping result to analytics.

        Args:
            result: Scraping result dictionary.
            user_id: User ID.
            username: Username.
        """
        try:
            item_data = result.get("item_data")
            seller_advisory = result.get("seller_advisory")

            analytics_data = SearchAnalytics(
                user_id=user_id,
                username=username,
                timestamp=datetime.now(),
                url=result.get("url", ""),
                platform=result.get("platform", "unknown"),
                success=result.get("success", False),
                processing_time_ms=result.get("processing_time_ms", 0),
                error_message=result.get("error"),
                item_title=getattr(item_data, "title", None),
                item_price=getattr(item_data, "price", None),
                shipping_us=getattr(item_data, "shipping_us", None),
                seller_score=None,
                seller_category=None,
                seller_warning_reason=getattr(seller_advisory, "reason", None),
                seller_warning_message=getattr(seller_advisory, "message", None),
                commission=None,
                final_price_usd=None,
                is_buyable=getattr(item_data, "is_buyable", None),
            )

            analytics_service.log_search(analytics_data)

        except Exception as e:
            logger.error(f"Failed to log analytics: {e}")


# Global orchestrator instance
scraping_orchestrator = ScrapingOrchestrator()
