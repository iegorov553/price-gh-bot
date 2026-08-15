"""Unit tests for GrailedScraper Algolia integration."""

from decimal import Decimal
from unittest.mock import AsyncMock, patch

import aiohttp
import pytest

from app.models import ItemData, SellerData
from app.scrapers.grailed_scraper import (
    GrailedScraper,
    extract_grailed_listing_id,
)


def test_extract_grailed_listing_id() -> None:
    """Test extraction of numeric listing ID from various Grailed URL formats."""
    # Standard listing URL with slug
    assert (
        extract_grailed_listing_id("https://www.grailed.com/listings/99406229-vissla-board-shorts")
        == "99406229"
    )
    # URL without slug
    assert extract_grailed_listing_id("https://www.grailed.com/listings/123456") == "123456"
    # URL with trailing slash
    assert extract_grailed_listing_id("https://grailed.com/listings/789/") == "789"
    # HTTP URL
    assert extract_grailed_listing_id("http://grailed.com/listings/555-shirt") == "555"
    # Invalid listing URL (non-numeric)
    assert extract_grailed_listing_id("https://www.grailed.com/listings/invalid") is None
    # Profile URL
    assert extract_grailed_listing_id("https://www.grailed.com/eraluxe") is None
    # Empty / non-URL string
    assert extract_grailed_listing_id("not-a-url") is None


@pytest.mark.asyncio
async def test_grailed_scraper_scrape_item_success() -> None:
    """Test successful scraping of an item via Algolia client."""
    scraper = GrailedScraper()
    mock_session = AsyncMock(spec=aiohttp.ClientSession)

    mock_item = ItemData(
        price=Decimal("34"),
        shipping_us=Decimal("9"),
        is_buyable=True,
        title="Vissla Board Shorts",
        image_url="https://example.com/img.jpg",
    )
    mock_seller = SellerData(
        num_reviews=100,
        avg_rating=4.9,
        trusted_badge=True,
    )

    with patch(
        "app.scrapers.grailed_scraper.grailed_algolia_client.get_listing_by_id",
        new_callable=AsyncMock,
        return_value=(mock_item, mock_seller),
    ) as mock_get:
        url = "https://www.grailed.com/listings/99406229-vissla-board-shorts"
        result = await scraper.scrape_item(url, mock_session)

        mock_get.assert_called_once_with("99406229", mock_session)
        assert result == mock_item
        assert scraper.extract_seller_profile_url(result) == "https://www.grailed.com/cached_seller"

        # Check cached seller retrieval
        cached_seller = await scraper.scrape_seller(
            "https://www.grailed.com/cached_seller", mock_session
        )
        assert cached_seller == mock_seller

        # After retrieving cached seller, cache is cleared
        assert scraper.extract_seller_profile_url(result) is None


@pytest.mark.asyncio
async def test_grailed_scraper_scrape_item_not_found() -> None:
    """Test scraping an item that is not found in Algolia."""
    scraper = GrailedScraper()
    mock_session = AsyncMock(spec=aiohttp.ClientSession)

    with patch(
        "app.scrapers.grailed_scraper.grailed_algolia_client.get_listing_by_id",
        new_callable=AsyncMock,
        return_value=(None, None),
    ) as mock_get:
        url = "https://www.grailed.com/listings/99999999-missing-item"
        result = await scraper.scrape_item(url, mock_session)

        mock_get.assert_called_once_with("99999999", mock_session)
        assert result is None
        assert scraper.extract_seller_profile_url(ItemData(price=Decimal("10"))) is None


@pytest.mark.asyncio
async def test_grailed_scraper_scrape_item_invalid_url() -> None:
    """Test scraping an invalid URL returns None without calling Algolia."""
    scraper = GrailedScraper()
    mock_session = AsyncMock(spec=aiohttp.ClientSession)

    with patch(
        "app.scrapers.grailed_scraper.grailed_algolia_client.get_listing_by_id",
        new_callable=AsyncMock,
    ) as mock_get:
        url = "https://www.grailed.com/not_a_listing"
        result = await scraper.scrape_item(url, mock_session)

        assert result is None
        mock_get.assert_not_called()


@pytest.mark.asyncio
async def test_grailed_scraper_scrape_seller_by_username() -> None:
    """Test fetching seller profile directly by username URL."""
    scraper = GrailedScraper()
    mock_session = AsyncMock(spec=aiohttp.ClientSession)

    mock_seller = SellerData(
        num_reviews=50,
        avg_rating=4.8,
        trusted_badge=False,
    )

    with patch(
        "app.scrapers.grailed_scraper.grailed_algolia_client.get_seller_by_username",
        new_callable=AsyncMock,
        return_value=mock_seller,
    ) as mock_get_user:
        url = "https://www.grailed.com/best_seller_shop"
        result = await scraper.scrape_seller(url, mock_session)

        mock_get_user.assert_called_once_with("best_seller_shop", mock_session)
        assert result == mock_seller


@pytest.mark.asyncio
async def test_grailed_scraper_scrape_seller_not_found_fallback() -> None:
    """Test fallback seller data when seller is not found."""
    scraper = GrailedScraper()
    mock_session = AsyncMock(spec=aiohttp.ClientSession)

    with patch(
        "app.scrapers.grailed_scraper.grailed_algolia_client.get_seller_by_username",
        new_callable=AsyncMock,
        return_value=None,
    ):
        url = "https://www.grailed.com/nonexistent_seller"
        result = await scraper.scrape_seller(url, mock_session)

        assert result is not None
        assert result.technical_issue is True
        assert result.num_reviews == 0
        assert result.avg_rating == 0.0


def test_grailed_scraper_supports_url() -> None:
    """Test supports_url detection for Grailed URLs."""
    scraper = GrailedScraper()
    assert scraper.supports_url("https://www.grailed.com/listings/123") is True
    assert scraper.supports_url("https://grailed.app.link/abc") is True
    assert scraper.supports_url("https://www.ebay.com/itm/123") is False
    assert scraper.supports_url("invalid-url") is False


def test_grailed_scraper_is_seller_profile() -> None:
    """Test is_seller_profile detection."""
    scraper = GrailedScraper()
    assert scraper.is_seller_profile("https://www.grailed.com/eraluxe") is True
    assert scraper.is_seller_profile("https://www.grailed.com/users/123-seller") is True
    assert scraper.is_seller_profile("https://www.grailed.com/listings/123") is False
    assert scraper.is_seller_profile("https://www.grailed.com/about") is False
    assert scraper.is_seller_profile("https://www.grailed.com/sell") is False
