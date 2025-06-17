"""Grailed scraper implementing the unified ScraperProtocol interface.

Provides Grailed-specific implementation of item and seller data extraction
with consistent interface for use in the scraping orchestrator.
"""

import logging
from typing import Optional

import aiohttp

from ..models import ItemData, SellerData
from .base import BaseScraper, ScraperProtocol
from .grailed import (
    get_item_data,
    analyze_seller_profile,
    is_grailed_url,
    is_grailed_seller_profile
)

logger = logging.getLogger(__name__)


class GrailedScraper(BaseScraper):
    """Grailed scraper implementing ScraperProtocol.
    
    Wraps existing Grailed scraping functionality in a standardized interface
    that can be used polymorphically with other marketplace scrapers.
    
    Features:
    - Item data extraction from Grailed listings
    - Seller data extraction from Grailed profiles
    - URL validation for Grailed domains
    - Seller profile URL extraction from item data
    - Support for both Next.js and legacy Grailed formats
    """
    
    def __init__(self):
        """Initialize Grailed scraper."""
        super().__init__("grailed")
        self._cached_seller_data = None
    
    async def scrape_item(
        self, 
        url: str, 
        session: aiohttp.ClientSession
    ) -> Optional[ItemData]:
        """Extract item data from Grailed listing URL.
        
        Args:
            url: Grailed item listing URL.
            session: HTTP session for requests.
            
        Returns:
            ItemData object if successful, None if failed.
        """
        self._log_scraping_start(url, "item")
        
        try:
            # Grailed returns tuple (item_data, seller_data)
            result = await get_item_data(url, session)
            
            if result and result[0]:
                item_data = result[0]
                seller_data = result[1]  # Save seller data
                buyable_status = "buyable" if item_data.is_buyable else "offer-only"
                self._log_scraping_success(
                    url, "item", 
                    f"'{item_data.title}' - ${item_data.price} ({buyable_status})"
                )
                
                # Store seller data for later retrieval
                self._cached_seller_data = seller_data
                
                return item_data
            else:
                self.logger.warning(f"No item data extracted from Grailed URL: {url}")
                return None
                
        except Exception as e:
            self._log_scraping_error(url, "item", e)
            return None
    
    async def scrape_seller(
        self, 
        url: str, 
        session: aiohttp.ClientSession
    ) -> Optional[SellerData]:
        """Extract seller data from Grailed profile URL.
        
        Args:
            url: Grailed seller profile URL.
            session: HTTP session for requests.
            
        Returns:
            SellerData object if successful, None if failed.
        """
        self._log_scraping_start(url, "seller")
        
        # Check for cached seller data first
        if self._cached_seller_data and url == "https://www.grailed.com/cached_seller":
            seller_data = self._cached_seller_data
            self._cached_seller_data = None  # Clear cache after use
            trusted_status = "trusted" if seller_data.trusted_badge else "standard"
            self._log_scraping_success(
                url, "seller",
                f"Rating: {seller_data.avg_rating:.1f}, Reviews: {seller_data.num_reviews}, Status: {trusted_status}"
            )
            return seller_data
        
        try:
            # Use analyze_seller_profile which returns full analysis
            seller_analysis = await analyze_seller_profile(url, session)
            
            if seller_analysis and 'seller_data' in seller_analysis:
                seller_data = seller_analysis['seller_data']
                trusted_status = "trusted" if seller_data.trusted_badge else "standard"
                self._log_scraping_success(
                    url, "seller",
                    f"Rating: {seller_data.avg_rating:.1f}, Reviews: {seller_data.num_reviews}, Status: {trusted_status}"
                )
                return seller_data
            else:
                self.logger.warning(f"No seller data extracted from Grailed profile: {url}")
                return None
                
        except Exception as e:
            self._log_scraping_error(url, "seller", e)
            return None
    
    def supports_url(self, url: str) -> bool:
        """Check if URL is from Grailed.
        
        Args:
            url: URL to check.
            
        Returns:
            True if URL is from Grailed, False otherwise.
        """
        return is_grailed_url(url) or is_grailed_seller_profile(url)
    
    def is_seller_profile(self, url: str) -> bool:
        """Check if Grailed URL is a seller profile.
        
        Args:
            url: URL to check.
            
        Returns:
            True if URL is a Grailed seller profile, False if item listing.
        """
        return is_grailed_seller_profile(url)
    
    def extract_seller_profile_url(self, item_data: ItemData) -> Optional[str]:
        """Extract seller profile URL from Grailed item data.
        
        Args:
            item_data: Grailed item data containing seller information.
            
        Returns:
            Seller profile URL if available, None otherwise.
        """
        try:
            # If we have cached seller data, return a dummy URL to trigger scrape_seller
            if self._cached_seller_data:
                return "https://www.grailed.com/cached_seller"
            else:
                self.logger.info("No cached seller data available")
                return None
        except Exception as e:
            self.logger.error(f"Failed to extract seller profile URL: {e}")
            return None


# Create and export Grailed scraper instance
grailed_scraper = GrailedScraper()