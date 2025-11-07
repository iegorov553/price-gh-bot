"""Typed structures shared across bot components."""

from __future__ import annotations

from typing import TypedDict

from ..models import ItemData, SellerAdvisory, SellerData


class BaseScrapeResult(TypedDict, total=False):
    """Shared scrape result fields usable for both items and sellers."""

    success: bool
    platform: str
    url: str
    error: str | None
    processing_time_ms: int
    from_cache: bool
    item_data: ItemData | None
    seller_data: SellerData | None
    seller_advisory: SellerAdvisory | None


class ItemScrapeResult(BaseScrapeResult, total=False):
    """Scrape result that may include cache timing metadata."""

    cache_processing_time_ms: int


class SellerScrapeResult(BaseScrapeResult, total=False):
    """Scrape result tailored for seller profile responses."""


class CategorizedURLs(TypedDict):
    """URL buckets split by profile/listing/platform."""

    seller_profiles: list[str]
    item_listings: list[str]
    by_platform: dict[str, list[str]]


class ProcessedURLs(TypedDict):
    """URL validation outcome with additional metadata."""

    valid_urls: list[str]
    categorized: CategorizedURLs | None
    has_suspicious: bool
