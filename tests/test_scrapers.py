"""Tests for eBay and Grailed web scraping functionality.

This module contains tests for the web scrapers that:
- Extract item prices, shipping costs, and buyability from eBay and Grailed
- Detect and validate platform-specific URLs 
- Handle scraping failures and network errors
- Parse seller profile URLs and listing data
"""

from decimal import Decimal
from unittest.mock import AsyncMock, patch

import pytest

from app.scrapers.ebay import get_item_data as get_ebay_data
from app.scrapers.ebay import is_ebay_url
from app.scrapers.grailed import get_item_data as get_grailed_data
from app.scrapers.grailed import is_grailed_seller_profile, is_grailed_url


def test_is_ebay_url():
    """Test eBay URL detection."""
    assert is_ebay_url("https://www.ebay.com/itm/123456789")
    assert is_ebay_url("https://ebay.com/itm/123456789")
    assert not is_ebay_url("https://grailed.com/listings/123456")
    assert not is_ebay_url("https://example.com")


def test_is_grailed_url():
    """Test Grailed URL detection."""
    assert is_grailed_url("https://www.grailed.com/listings/123456")
    assert is_grailed_url("https://grailed.com/listings/123456")
    assert not is_grailed_url("https://ebay.com/itm/123456")
    assert not is_grailed_url("https://example.com")


def test_is_grailed_seller_profile():
    """Test Grailed seller profile URL detection."""
    assert is_grailed_seller_profile("https://www.grailed.com/username")
    assert is_grailed_seller_profile("https://grailed.com/users/username")
    assert is_grailed_seller_profile("https://grailed.com/sellers/username")
    assert not is_grailed_seller_profile("https://grailed.com/listings/123456")
    assert not is_grailed_seller_profile("https://grailed.com/sell")
    assert not is_grailed_seller_profile("https://ebay.com/usr/seller")


@pytest.mark.asyncio
async def test_ebay_scraper_success():
    """Test successful eBay scraping."""
    mock_session = AsyncMock()

    # Mock HTML response with price
    html_content = """
    <html>
        <meta itemprop="price" content="29.99">
        <span id="fshippingCost">$5.00</span>
        <meta property="og:title" content="Test Item">
    </html>
    """

    mock_response = AsyncMock()
    mock_response.text.return_value = html_content
    mock_session.get.return_value.__aenter__ = AsyncMock(return_value=mock_response)

    item_data = await get_ebay_data("https://ebay.com/itm/123", mock_session)

    assert item_data.price == Decimal("29.99")
    assert item_data.shipping_us == Decimal("5.00")
    assert item_data.is_buyable is True
    assert item_data.title == "Test Item"


@pytest.mark.asyncio
async def test_ebay_scraper_failure():
    """Test eBay scraper with network failure."""
    mock_session = AsyncMock()
    mock_session.get.side_effect = Exception("Network error")

    item_data = await get_ebay_data("https://ebay.com/itm/123", mock_session)

    assert item_data.price is None
    assert item_data.is_buyable is False


@pytest.mark.asyncio
async def test_grailed_scraper_success():
    """Test successful Grailed scraping."""
    mock_session = AsyncMock()

    # Mock HTML response with buyable item
    html_content = """
    <html>
        <span class="price">$99.99</span>
        <script>{"buyNow": true}</script>
        <meta property="og:title" content="Grailed Item">
    </html>
    """

    mock_response = AsyncMock()
    mock_response.text.return_value = html_content
    mock_session.get.return_value.__aenter__ = AsyncMock(return_value=mock_response)

    with patch('app.scrapers.grailed._extract_seller_data') as mock_seller:
        mock_seller.return_value = None

        item_data, seller_data = await get_grailed_data("https://grailed.com/listings/123", mock_session)

        assert item_data.price == Decimal("99.99")
        assert item_data.is_buyable is True
        assert item_data.title == "Grailed Item"
        assert seller_data is None
