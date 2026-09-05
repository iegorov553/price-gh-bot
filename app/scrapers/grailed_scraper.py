"""Grailed scraper implementing the unified ScraperProtocol interface via Algolia backend.

Provides Grailed-specific implementation of item and seller data extraction
using Grailed's Algolia search index for fast and reliable extraction.
"""

from __future__ import annotations

import logging
import re
from datetime import UTC, datetime
from urllib.parse import urlparse

import aiohttp

from ..models import ItemData, SellerData
from ..services.grailed_algolia import grailed_algolia_client
from .base import BaseScraper
from .grailed_url_resolver import async_normalize_grailed_url

logger = logging.getLogger(__name__)


def extract_grailed_listing_id(url: str) -> str | None:
    """Extract numeric listing ID from a Grailed listing URL.

    Args:
        url: Grailed listing URL (e.g. https://www.grailed.com/listings/99406229-vissla-board-shorts).

    Returns:
        Numeric listing ID as string, or None if not found.
    """
    try:
        parsed = urlparse(url)
        path = parsed.path or url
        match = re.search(r"/listings/(\d+)", path)
        if match:
            return match.group(1)
        return None
    except Exception:
        return None


def _fallback_seller_data(reason: str) -> SellerData:
    """Return safe default seller payload when extraction fails."""
    logger.warning("Using fallback seller data due to: %s", reason)
    return SellerData(
        num_reviews=0,
        avg_rating=0.0,
        trusted_badge=False,
        last_updated=datetime.now(UTC),
        technical_issue=True,
    )


class GrailedScraper(BaseScraper):
    """Grailed scraper implementing ScraperProtocol via Algolia index queries.

    Fetches structured item and seller profile data directly from Grailed's
    Algolia backend for fast, reliable extraction without browser automation.

    Features:
    - Item data extraction from Grailed listings via Algolia
    - Seller data extraction from Grailed profiles via Algolia
    - Caching of seller data retrieved during item search
    - URL validation for Grailed domains
    - Seller profile URL extraction from item data
    """

    def __init__(self) -> None:
        """Initialize Grailed scraper."""
        super().__init__("grailed")
        self._cached_seller_data: SellerData | None = None

    async def scrape_item(self, url: str, session: aiohttp.ClientSession) -> ItemData | None:
        """Extract item data from Grailed listing URL using Algolia.

        Args:
            url: Grailed item listing URL.
            session: HTTP session for requests.

        Returns:
            ItemData object if successful, None if failed.
        """
        self._log_scraping_start(url, "item")

        try:
            normalized_url = await async_normalize_grailed_url(url, session)
            if normalized_url != url:
                self.logger.debug("Normalized Grailed URL %s → %s", url, normalized_url)
                url = normalized_url

            listing_id = extract_grailed_listing_id(url)
            if not listing_id:
                self.logger.warning("Could not extract listing ID from Grailed URL: %s", url)
                return None

            item_data, seller_data = await grailed_algolia_client.get_listing_by_id(
                listing_id, session
            )
            if not item_data:
                self.logger.warning("No item data returned from Algolia for listing %s", listing_id)
                return None

            self._cached_seller_data = seller_data
            self._log_scraping_success(url, "item", f"'{item_data.title}' - ${item_data.price}")
            return item_data

        except Exception as exc:
            self._log_scraping_error(url, "item", exc)
            return None

    async def scrape_seller(self, url: str, session: aiohttp.ClientSession) -> SellerData | None:
        """Extract seller data from Grailed profile URL or cached item search.

        Args:
            url: Grailed seller profile URL or cached seller URL.
            session: HTTP session for requests.

        Returns:
            SellerData object if successful, or fallback SellerData if failed.
        """
        self._log_scraping_start(url, "seller")

        # Check for cached seller data first
        if self._cached_seller_data and url == "https://www.grailed.com/cached_seller":
            seller_data = self._cached_seller_data
            self._cached_seller_data = None  # Clear cache after use
            trusted_status = "trusted" if seller_data.trusted_badge else "standard"
            self._log_scraping_success(
                url,
                "seller",
                f"Rating: {seller_data.avg_rating:.1f}, Reviews: {seller_data.num_reviews}, Status: {trusted_status}",
            )
            return seller_data

        try:
            normalized_url = await async_normalize_grailed_url(url, session)
            if normalized_url != url:
                self.logger.debug("Normalized Grailed seller URL %s → %s", url, normalized_url)
                url = normalized_url

            parsed = urlparse(url)
            path = parsed.path.strip("/")

            if path.startswith("users/") or path.startswith("sellers/") or path.startswith("user/"):
                username = path.split("/")[-1]
                if "-" in username:
                    username_parts = username.split("-", 1)
                    if username_parts[0].isdigit() and len(username_parts) > 1:
                        username = username_parts[1]
            else:
                username = path

            if not username:
                self.logger.warning("Could not extract username from URL: %s", url)
                return _fallback_seller_data("invalid_seller_url")

            seller_data = await grailed_algolia_client.get_seller_by_username(username, session)
            if seller_data:
                trusted_status = "trusted" if seller_data.trusted_badge else "standard"
                self._log_scraping_success(
                    url,
                    "seller",
                    f"Rating: {seller_data.avg_rating:.1f}, Reviews: {seller_data.num_reviews}, Status: {trusted_status}",
                )
                return seller_data

            self.logger.warning("No seller data extracted from Grailed profile: %s", url)
            return _fallback_seller_data("seller_not_found")

        except Exception as exc:
            self._log_scraping_error(url, "seller", exc)
            return _fallback_seller_data("algolia_error")

    def supports_url(self, url: str) -> bool:
        """Check if URL is from Grailed."""
        try:
            parsed = urlparse(url)
            domain = parsed.netloc.lower().split(":")[0]
            return "grailed" in domain.split(".")
        except Exception:
            return False

    def is_seller_profile(self, url: str) -> bool:
        """Check if URL is a Grailed seller profile."""
        try:
            parsed = urlparse(url)
            if "grailed.com" not in parsed.netloc.lower():
                return False

            path = parsed.path.lower().strip("/")

            # Direct username pattern
            if path and "/" not in path and not path.startswith("listings"):
                excluded_pages = {
                    "sell",
                    "buy",
                    "search",
                    "help",
                    "about",
                    "terms",
                    "privacy",
                    "brands",
                    "designers",
                    "categories",
                    "login",
                    "signup",
                    "settings",
                    "notifications",
                    "feed",
                }
                if path not in excluded_pages:
                    return True

            # Legacy patterns
            if path.startswith("users/") or path.startswith("sellers/") or path.startswith("user/"):
                return True

            return False
        except Exception:
            return False

    def extract_seller_profile_url(self, item_data: ItemData) -> str | None:
        """Extract seller profile URL from Grailed item data."""
        try:
            if self._cached_seller_data:
                return "https://www.grailed.com/cached_seller"
            self.logger.info("No cached seller data available")
            return None
        except Exception as exc:
            self.logger.error("Failed to extract seller profile URL: %s", exc)
            return None


# Create and export Grailed scraper instance
grailed_scraper = GrailedScraper()
