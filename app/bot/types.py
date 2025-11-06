"""Typed structures shared across bot components."""

from __future__ import annotations

from typing import TypedDict

from ..models import ItemData, ReliabilityScore, SellerData


class BaseScrapeResult(TypedDict, total=False):
    success: bool
    platform: str
    url: str
    error: str | None
    processing_time_ms: int
    from_cache: bool
    item_data: ItemData | None
    seller_data: SellerData | None
    reliability_score: ReliabilityScore | None


class ItemScrapeResult(BaseScrapeResult, total=False):
    cache_processing_time_ms: int


class SellerScrapeResult(BaseScrapeResult, total=False):
    pass


class CategorizedURLs(TypedDict):
    seller_profiles: list[str]
    item_listings: list[str]
    by_platform: dict[str, list[str]]


class ProcessedURLs(TypedDict):
    valid_urls: list[str]
    categorized: CategorizedURLs | None
    has_suspicious: bool
