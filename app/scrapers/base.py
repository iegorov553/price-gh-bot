"""Base scraper protocol and abstractions for marketplace data extraction.

Defines the unified interface that all marketplace scrapers must implement
to ensure consistency, testability, and easy extensibility.
"""

import logging
from typing import Protocol

import aiohttp

from ..models import ItemData, SellerData

logger = logging.getLogger(__name__)


class ScraperProtocol(Protocol):
    """Protocol defining the interface for all marketplace scrapers.

    This protocol ensures that all scrapers (eBay, Grailed, future platforms)
    implement a consistent interface, enabling polymorphism and easy testing.

    Methods:
        scrape_item: Extract item data from listing URL.
        scrape_seller: Extract seller data from profile URL.
        supports_url: Check if scraper can handle given URL.
        get_platform_name: Get platform identifier.
        is_seller_profile: Check if URL is a seller profile.
        extract_seller_profile_url: Get seller profile URL from item data.
    """

    async def scrape_item(self, url: str, session: aiohttp.ClientSession) -> ItemData | None:
        """Extract item data from marketplace listing URL.

        Args:
            url: Item listing URL.
            session: HTTP session for requests.

        Returns:
            ItemData object if successful, None if failed.
        """
        ...

    async def scrape_seller(self, url: str, session: aiohttp.ClientSession) -> SellerData | None:
        """Extract seller data from marketplace profile URL.

        Args:
            url: Seller profile URL.
            session: HTTP session for requests.

        Returns:
            SellerData object if successful, None if failed.
        """
        ...

    def supports_url(self, url: str) -> bool:
        """Check if this scraper can handle the given URL.

        Args:
            url: URL to check.

        Returns:
            True if scraper supports this URL, False otherwise.
        """
        ...

    def get_platform_name(self) -> str:
        """Get the platform name identifier.

        Returns:
            Platform name (e.g., 'ebay', 'grailed').
        """
        ...

    def is_seller_profile(self, url: str) -> bool:
        """Check if URL is a seller profile page.

        Args:
            url: URL to check.

        Returns:
            True if URL is a seller profile, False if item listing.
        """
        ...

    def extract_seller_profile_url(self, item_data: ItemData) -> str | None:
        """Extract seller profile URL from item data.

        Args:
            item_data: Item data containing seller information.

        Returns:
            Seller profile URL if available, None otherwise.
        """
        ...


class BaseScraper:
    """Base class providing common functionality for all scrapers.

    Provides shared utilities and default implementations that can be
    inherited by concrete scraper implementations.
    """

    def __init__(self, platform_name: str):
        """Initialize base scraper.

        Args:
            platform_name: Name of the platform (e.g., 'ebay', 'grailed').
        """
        self.platform_name = platform_name
        self.logger = logging.getLogger(f"{__name__}.{platform_name}")

    def get_platform_name(self) -> str:
        """Get the platform name identifier."""
        return self.platform_name

    async def scrape_seller(self, url: str, session: aiohttp.ClientSession) -> SellerData | None:
        """Default implementation for platforms without seller support.

        Override this method in scrapers that support seller analysis.

        Args:
            url: Seller profile URL.
            session: HTTP session for requests.

        Returns:
            None (no seller support by default).
        """
        self.logger.info(f"{self.platform_name} does not support seller analysis")
        return None

    def extract_seller_profile_url(self, item_data: ItemData) -> str | None:
        """Default implementation for seller URL extraction.

        Override this method in scrapers that provide seller URLs.

        Args:
            item_data: Item data object.

        Returns:
            None (no seller URL by default).
        """
        return None

    def _log_scraping_start(self, url: str, operation: str) -> None:
        """Log the start of a scraping operation.

        Args:
            url: URL being scraped.
            operation: Type of operation (item, seller).
        """
        self.logger.info(f"Starting {operation} scraping for {self.platform_name}: {url}")

    def _log_scraping_success(self, url: str, operation: str, result: str) -> None:
        """Log successful scraping operation.

        Args:
            url: URL that was scraped.
            operation: Type of operation (item, seller).
            result: Brief description of result.
        """
        self.logger.info(f"Successfully scraped {operation} from {self.platform_name}: {result}")

    def _log_scraping_error(self, url: str, operation: str, error: Exception) -> None:
        """Log scraping error.

        Args:
            url: URL that failed to scrape.
            operation: Type of operation (item, seller).
            error: Exception that occurred.
        """
        self.logger.error(
            f"Failed to scrape {operation} from {self.platform_name} ({url}): {error}"
        )


class ScraperRegistry:
    """Registry for managing marketplace scrapers.

    Provides centralized management of all available scrapers with
    automatic URL routing and platform detection.
    """

    def __init__(self) -> None:
        """Initialize empty scraper registry."""
        self._scrapers: dict[str, ScraperProtocol] = {}
        self.logger = logging.getLogger(f"{__name__}.registry")

    def register(self, scraper: ScraperProtocol) -> None:
        """Register a new scraper.

        Args:
            scraper: Scraper instance implementing ScraperProtocol.
        """
        platform = scraper.get_platform_name()
        self._scrapers[platform] = scraper
        self.logger.info(f"Registered scraper for platform: {platform}")

    def get_scraper_for_url(self, url: str) -> ScraperProtocol | None:
        """Find appropriate scraper for given URL.

        Args:
            url: URL to find scraper for.

        Returns:
            Scraper instance if found, None otherwise.
        """
        for scraper in self._scrapers.values():
            if scraper.supports_url(url):
                return scraper

        self.logger.warning(f"No scraper found for URL: {url}")
        return None

    def get_scraper_by_platform(self, platform: str) -> ScraperProtocol | None:
        """Get scraper by platform name.

        Args:
            platform: Platform name (e.g., 'ebay', 'grailed').

        Returns:
            Scraper instance if found, None otherwise.
        """
        return self._scrapers.get(platform)

    def get_all_platforms(self) -> list[str]:
        """Get list of all registered platform names.

        Returns:
            List of platform names.
        """
        return list(self._scrapers.keys())

    def get_scrapers_count(self) -> int:
        """Get number of registered scrapers.

        Returns:
            Number of registered scrapers.
        """
        return len(self._scrapers)


# Global scraper registry instance
scraper_registry = ScraperRegistry()
