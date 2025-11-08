"""URL processing and validation for marketplace links.

Provides high-level helpers used by Telegram handlers to extract, validate,
and categorise marketplace URLs. All public methods are fully typed to
support strict mypy settings.
"""

from __future__ import annotations

import logging
import re
from collections import defaultdict
from typing import Final

from ..scrapers import scraper_registry
from .types import CategorizedURLs, ProcessedURLs
from .utils import validate_marketplace_url

logger = logging.getLogger(__name__)


class URLProcessor:
    """Handles URL detection, validation and categorisation."""

    URL_PATTERN: Final[re.Pattern[str]] = re.compile(r"(https?://[^\s\)\]\}]+)")

    def extract_urls(self, text: str | None) -> list[str]:
        """Extract URLs from free-form text."""
        if not text:
            return []

        raw_urls = self.URL_PATTERN.findall(text)
        urls = [url.rstrip(".,);?!") for url in raw_urls]
        logger.debug("Extracted %d URLs from text", len(urls))
        return urls

    def validate_urls(self, urls: list[str]) -> list[str]:
        """Keep only URLs that belong to supported marketplaces."""
        valid_urls: list[str] = []
        invalid_urls: list[str] = []

        for url in urls:
            if validate_marketplace_url(url):
                valid_urls.append(url)
            else:
                invalid_urls.append(url)

        if invalid_urls:
            logger.warning("Filtered out invalid URLs: %s", invalid_urls)

        logger.info("Validated %d/%d URLs", len(valid_urls), len(urls))
        return valid_urls

    def categorize_urls(self, urls: list[str]) -> CategorizedURLs:
        """Split URLs by platform and type (seller profile vs listing)."""
        seller_profiles: list[str] = []
        item_listings: list[str] = []
        by_platform: defaultdict[str, list[str]] = defaultdict(list)

        for url in urls:
            scraper = scraper_registry.get_scraper_for_url(url)
            if scraper is None:
                by_platform["unknown"].append(url)
                continue

            platform = scraper.get_platform_name()
            by_platform[platform].append(url)

            if scraper.is_seller_profile(url):
                seller_profiles.append(url)
            else:
                item_listings.append(url)

        # Ensure eBay/Grailed keys exist for downstream formatting consistency
        for key in ("ebay", "grailed", "unknown"):
            by_platform.setdefault(key, [])

        return CategorizedURLs(
            seller_profiles=seller_profiles,
            item_listings=item_listings,
            by_platform=dict(by_platform),
        )

    def process_message(self, text: str | None, user_id: int | None = None) -> ProcessedURLs:
        """Full URL processing pipeline used by message handlers."""
        raw_urls = self.extract_urls(text)
        if not raw_urls:
            return ProcessedURLs(valid_urls=[], categorized=None, has_suspicious=False)

        valid_urls = self.validate_urls(raw_urls)
        has_suspicious = len(valid_urls) < len(raw_urls)

        if has_suspicious and user_id is not None:
            suspicious_urls = [url for url in raw_urls if url not in valid_urls]
            logger.warning("User %s sent suspicious URLs: %s", user_id, suspicious_urls)

        categorized = self.categorize_urls(valid_urls) if valid_urls else None
        return ProcessedURLs(
            valid_urls=valid_urls,
            categorized=categorized,
            has_suspicious=has_suspicious,
        )


url_processor = URLProcessor()
