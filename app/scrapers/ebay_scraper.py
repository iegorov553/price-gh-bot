"""eBay scraper implementing the unified ScraperProtocol interface.

Provides eBay-specific implementation of item data extraction with
consistent interface for use in the scraping orchestrator.
"""

import logging

import aiohttp

from ..models import ItemData, SellerData
from .base import BaseScraper
from .ebay import get_item_data, is_ebay_url

logger = logging.getLogger(__name__)


class EbayScraper(BaseScraper):
    """eBay scraper implementing ScraperProtocol.

    Wraps existing eBay scraping functionality in a standardized interface
    that can be used polymorphically with other marketplace scrapers.

    Features:
    - Item data extraction from eBay listings
    - URL validation for eBay domains
    - No seller analysis support (eBay limitation)
    - Integration with existing eBay scraping functions
    """

    def __init__(self) -> None:
        """Initialize eBay scraper."""
        super().__init__("ebay")

    async def scrape_item(self, url: str, session: aiohttp.ClientSession) -> ItemData | None:
        """Extract item data from eBay listing URL.

        Args:
            url: eBay item listing URL.
            session: HTTP session for requests.

        Returns:
            ItemData object if successful, None if failed.
        """
        self._log_scraping_start(url, "item")

        try:
            item_data = await get_item_data(url, session)

            if item_data:
                self._log_scraping_success(url, "item", f"'{item_data.title}' - ${item_data.price}")
                return item_data
            else:
                self.logger.warning(f"No item data extracted from eBay URL: {url}")
                return None

        except Exception as e:
            self._log_scraping_error(url, "item", e)
            return None

    async def scrape_seller(self, url: str, session: aiohttp.ClientSession) -> SellerData | None:
        """eBay does not support seller analysis.

        Args:
            url: Seller profile URL (ignored).
            session: HTTP session (ignored).

        Returns:
            Always None - eBay doesn't provide seller analysis.
        """
        self.logger.info("eBay scraper does not support seller analysis")
        return None

    def supports_url(self, url: str) -> bool:
        """Check if URL is from eBay.

        Args:
            url: URL to check.

        Returns:
            True if URL is from eBay, False otherwise.
        """
        return is_ebay_url(url)

    def is_seller_profile(self, url: str) -> bool:
        """Check if eBay URL is a seller profile.

        Args:
            url: URL to check.

        Returns:
            Always False - eBay seller profiles not supported.
        """
        return False

    def extract_seller_profile_url(self, item_data: ItemData) -> str | None:
        """Extract seller profile URL from eBay item data.

        Args:
            item_data: eBay item data.

        Returns:
            Always None - eBay doesn't provide seller profile URLs.
        """
        return None


# Create and export eBay scraper instance
ebay_scraper = EbayScraper()
