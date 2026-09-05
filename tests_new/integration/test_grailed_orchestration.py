"""Integration tests for Grailed orchestration via Algolia backend.

Validates the complete chain:
ScrapingOrchestrator -> GrailedScraper -> GrailedAlgoliaClient -> SellerAdvisory evaluation.
"""

from __future__ import annotations

import base64
import json
from decimal import Decimal
from typing import Any
from unittest.mock import AsyncMock, patch

import aiohttp
import pytest

from app.bot.response_formatter import response_formatter
from app.bot.scraping_orchestrator import scraping_orchestrator
from app.models import ItemData, SellerData
from app.services.seller_assessment import evaluate_seller_advisory


@pytest.mark.asyncio
async def test_orchestrator_grailed_item_and_advisory_flow() -> None:
    """Test standard item listing scraping and advisory evaluation flow."""
    mock_item = ItemData(
        price=Decimal("45.00"),
        shipping_us=Decimal("10.00"),
        is_buyable=True,
        title="Vintage Hoodie",
        image_url="https://example.com/img.jpg",
    )
    mock_seller = SellerData(
        num_reviews=15,
        avg_rating=4.2,  # Low rating threshold <= 4.6
        trusted_badge=False,
    )

    with patch(
        "app.scrapers.grailed_scraper.grailed_algolia_client.get_listing_by_id",
        new_callable=AsyncMock,
        return_value=(mock_item, mock_seller),
    ) as mock_algolia:
        async with aiohttp.ClientSession() as session:
            url = "https://www.grailed.com/listings/99406229-vintage-hoodie"
            result = await scraping_orchestrator.scrape_item_listing(url, session)

            mock_algolia.assert_called_once_with("99406229", session)
            assert result["success"] is True
            assert result["platform"] == "grailed"
            assert result["item_data"] == mock_item
            assert result["seller_data"] == mock_seller
            assert result["error"] is None

            # Evaluate advisory for the scraped item and seller
            advisory = evaluate_seller_advisory(
                seller_data=result["seller_data"], item_data=result["item_data"]
            )
            assert advisory.reason == "low_rating"
            assert advisory.message is not None


@pytest.mark.asyncio
async def test_orchestrator_grailed_item_with_cache_flow() -> None:
    """Test cached item scraping with instant response on repeated requests."""
    mock_item = ItemData(
        price=Decimal("75.00"),
        shipping_us=Decimal("12.00"),
        is_buyable=True,
        title="Designer Jacket",
        image_url="https://example.com/jacket.jpg",
    )
    mock_seller = SellerData(
        num_reviews=120,
        avg_rating=4.95,
        trusted_badge=True,
    )

    cache_storage: dict[str, Any] = {}

    mock_cache = AsyncMock()
    mock_cache.get_item_data.side_effect = lambda url: cache_storage.get(url)
    mock_cache.set_item_data.side_effect = lambda url, data: cache_storage.update({url: data})

    with (
        patch(
            "app.scrapers.grailed_scraper.grailed_algolia_client.get_listing_by_id",
            new_callable=AsyncMock,
            return_value=(mock_item, mock_seller),
        ) as mock_algolia,
        patch.object(scraping_orchestrator, "_ensure_cache_service", new_callable=AsyncMock),
    ):
        scraping_orchestrator.cache_service = mock_cache
        async with aiohttp.ClientSession() as session:
            url = "https://www.grailed.com/listings/88881234-designer-jacket"

            # First call - cache miss
            result1 = await scraping_orchestrator.scrape_item_listing_with_cache(url, session)
            assert result1["success"] is True
            assert result1["from_cache"] is False
            assert result1["item_data"] == mock_item
            assert mock_algolia.call_count == 1

            # Second call - cache hit
            result2 = await scraping_orchestrator.scrape_item_listing_with_cache(url, session)
            assert result2["success"] is True
            assert result2["from_cache"] is True
            assert result2["item_data"] == mock_item
            assert mock_algolia.call_count == 1  # Not called again


@pytest.mark.asyncio
async def test_orchestrator_grailed_seller_profile_flow() -> None:
    """Test seller profile scraping and automatic advisory generation."""
    mock_seller = SellerData(
        num_reviews=220,
        avg_rating=4.88,
        trusted_badge=True,
    )

    with patch(
        "app.scrapers.grailed_scraper.grailed_algolia_client.get_seller_by_username",
        new_callable=AsyncMock,
        return_value=mock_seller,
    ) as mock_seller_algolia:
        async with aiohttp.ClientSession() as session:
            url = "https://www.grailed.com/eraluxe"
            result = await scraping_orchestrator.scrape_seller_profile(url, session)

            mock_seller_algolia.assert_called_once_with("eraluxe", session)
            assert result["success"] is True
            assert result["platform"] == "profile"
            assert result["seller_data"] == mock_seller
            assert result["seller_advisory"] is not None
            assert result["seller_advisory"].reason is None  # High rating, no warning


@pytest.mark.asyncio
async def test_orchestrator_grailed_seller_profile_not_found_fallback() -> None:
    """Test fallback advisory when seller is not found."""
    with patch(
        "app.scrapers.grailed_scraper.grailed_algolia_client.get_seller_by_username",
        new_callable=AsyncMock,
        return_value=None,
    ) as mock_seller_algolia:
        async with aiohttp.ClientSession() as session:
            url = "https://www.grailed.com/nonexistent_seller_shop"
            result = await scraping_orchestrator.scrape_seller_profile(url, session)

            mock_seller_algolia.assert_called_once_with("nonexistent_seller_shop", session)
            assert result["success"] is True
            assert result["seller_data"] is not None
            assert result["seller_data"].technical_issue is True
            assert result["seller_advisory"] is not None
            assert result["seller_advisory"].reason == "technical_issue"


@pytest.mark.asyncio
async def test_orchestrator_grailed_shortlink_flow() -> None:
    """Test shortlink decoding and resolution through the orchestrator flow."""
    mock_item = ItemData(
        price=Decimal("34.00"),
        shipping_us=Decimal("9.00"),
        is_buyable=True,
        title="Vissla Board Shorts",
        image_url="https://example.com/shorts.jpg",
    )
    mock_seller = SellerData(
        num_reviews=118,
        avg_rating=4.87,
        trusted_badge=True,
    )

    # Encode payload in grailed.app.link
    payload = {"$canonical_url": "https://www.grailed.com/listings/99406229-vissla-board-shorts"}
    encoded = base64.urlsafe_b64encode(json.dumps(payload).encode("utf-8")).decode("utf-8")
    shortlink_url = f"https://grailed.app.link/share?data={encoded}"

    with patch(
        "app.scrapers.grailed_scraper.grailed_algolia_client.get_listing_by_id",
        new_callable=AsyncMock,
        return_value=(mock_item, mock_seller),
    ) as mock_algolia:
        async with aiohttp.ClientSession() as session:
            result = await scraping_orchestrator.scrape_item_listing(shortlink_url, session)

            mock_algolia.assert_called_once_with("99406229", session)
            assert result["success"] is True
            assert result["platform"] == "grailed"
            assert result["item_data"] == mock_item
            assert result["seller_data"] == mock_seller


@pytest.mark.asyncio
async def test_orchestrator_process_urls_concurrent_grailed_batch() -> None:
    """Test concurrent processing of items and seller profiles in batch."""
    mock_item = ItemData(
        price=Decimal("110.00"),
        shipping_us=Decimal("15.00"),
        is_buyable=True,
        title="Supreme Tee",
    )
    mock_item_seller = SellerData(
        num_reviews=50,
        avg_rating=4.9,
        trusted_badge=True,
    )
    mock_profile_seller = SellerData(
        num_reviews=5,
        avg_rating=3.5,  # Low rating
        trusted_badge=False,
    )

    payload = {"$canonical_url": "https://www.grailed.com/listings/101466749-arcteryx-fleece"}
    encoded = base64.urlsafe_b64encode(json.dumps(payload).encode("utf-8")).decode("utf-8")
    shortlink_url = f"https://grailed.app.link/share?data={encoded}"

    urls = [
        "https://www.grailed.com/listings/99406229-vissla-board-shorts",
        "https://www.grailed.com/low_rating_seller",
        shortlink_url,
    ]

    async def mock_get_listing(listing_id: str, session: aiohttp.ClientSession):
        return mock_item, mock_item_seller

    async def mock_get_seller(username: str, session: aiohttp.ClientSession):
        return mock_profile_seller

    with (
        patch(
            "app.scrapers.grailed_scraper.grailed_algolia_client.get_listing_by_id",
            side_effect=mock_get_listing,
        ),
        patch(
            "app.scrapers.grailed_scraper.grailed_algolia_client.get_seller_by_username",
            side_effect=mock_get_seller,
        ),
        patch("app.bot.scraping_orchestrator.analytics_service.log_search") as mock_log_analytics,
    ):
        results = await scraping_orchestrator.process_urls_concurrent(
            urls, user_id=12345, username="tester"
        )

        assert len(results) == 3
        assert all(r["success"] is True for r in results)

        # 1st: regular item
        assert results[0]["platform"] == "grailed"
        assert results[0]["item_data"] == mock_item
        assert results[0]["seller_data"] == mock_item_seller

        # 2nd: seller profile
        assert results[1]["platform"] == "profile"
        assert results[1]["seller_data"] == mock_profile_seller
        assert results[1]["seller_advisory"].reason == "low_rating"

        # 3rd: shortlink item
        assert results[2]["platform"] == "grailed"
        assert results[2]["item_data"] == mock_item
        assert results[2]["seller_data"] == mock_item_seller

        # Verify analytics logged for all 3 operations
        assert mock_log_analytics.call_count == 3


@pytest.mark.asyncio
async def test_orchestrator_grailed_sold_listing_flow() -> None:
    """Test full orchestrator flow for sold listing on Grailed."""
    mock_sold_item = ItemData(
        price=Decimal("117.00"),
        shipping_us=Decimal("25.00"),
        is_buyable=False,
        is_sold=True,
        title="Tornado Mart Flared Jeans",
        image_url="https://example.com/sold.jpg",
    )
    mock_seller = SellerData(
        num_reviews=80,
        avg_rating=4.95,
        trusted_badge=True,
    )

    with patch(
        "app.scrapers.grailed_scraper.grailed_algolia_client.get_listing_by_id",
        new_callable=AsyncMock,
        return_value=(mock_sold_item, mock_seller),
    ) as mock_algolia:
        async with aiohttp.ClientSession() as session:
            url = "https://www.grailed.com/listings/94370655-tornado-mart"
            result = await scraping_orchestrator.scrape_item_listing(url, session)

            mock_algolia.assert_called_once_with("94370655", session)
            assert result["success"] is True
            assert result["platform"] == "grailed"
            assert result["item_data"].is_sold is True
            assert result["item_data"].is_buyable is False

            # Format response and verify advisory
            response = await response_formatter.format_item_response(result)
            assert "уже продан на Grailed" in response
            assert "$117" in response


@pytest.mark.parametrize(
    ("seller_data", "item_data", "expected_reason"),
    [
        (
            SellerData(num_reviews=10, avg_rating=4.1, trusted_badge=False),
            ItemData(price=Decimal("50"), is_buyable=True),
            "low_rating",
        ),
        (
            SellerData(num_reviews=0, avg_rating=0.0, trusted_badge=False),
            ItemData(price=Decimal("50"), is_buyable=True),
            "no_reviews",
        ),
        (
            SellerData(num_reviews=50, avg_rating=4.9, trusted_badge=True),
            ItemData(price=Decimal("50"), is_buyable=False),
            "no_buy_now_price",
        ),
        (
            SellerData(num_reviews=50, avg_rating=4.9, trusted_badge=True),
            ItemData(price=Decimal("50"), is_buyable=False, is_sold=True),
            "item_sold",
        ),
        (
            SellerData(num_reviews=50, avg_rating=4.9, trusted_badge=True),
            ItemData(price=Decimal("50"), is_buyable=True),
            None,
        ),
    ],
)
def test_seller_advisory_variations(
    seller_data: SellerData, item_data: ItemData, expected_reason: str | None
) -> None:
    """Test seller advisory rule evaluation across different seller and item states."""
    advisory = evaluate_seller_advisory(seller_data=seller_data, item_data=item_data)
    assert advisory.reason == expected_reason
    if expected_reason:
        assert advisory.message is not None
    else:
        assert advisory.message is None


@pytest.mark.asyncio
async def test_orchestrator_resolves_onelink_listing_and_profile() -> None:
    """Test orchestrator correctly routes onelink shortlinks for both listings and seller profiles."""
    mock_item = ItemData(
        price=Decimal("35.00"),
        shipping_us=Decimal("10.00"),
        is_buyable=True,
        title="Stussy Shoulder Bag",
    )
    mock_item_seller = SellerData(
        num_reviews=19,
        avg_rating=5.0,
        trusted_badge=True,
    )
    mock_profile_seller = SellerData(
        num_reviews=42,
        avg_rating=4.9,
        trusted_badge=True,
    )

    onelink_item = "https://grailed.onelink.me/1LT8/item123"
    onelink_profile = "https://grailed.onelink.me/1LT8/seller456"

    async def mock_normalize(url: str, session: Any = None) -> str:
        if url == onelink_item:
            return "https://www.grailed.com/listings/103877007-stussy-bag"
        elif url == onelink_profile:
            return "https://www.grailed.com/users/999-grailedseller"
        return url

    from unittest.mock import ANY

    with (
        patch(
            "app.bot.scraping_orchestrator.async_normalize_grailed_url",
            side_effect=mock_normalize,
        ),
        patch(
            "app.scrapers.grailed_scraper.grailed_algolia_client.get_listing_by_id",
            new_callable=AsyncMock,
            return_value=(mock_item, mock_item_seller),
        ) as mock_get_listing,
        patch(
            "app.scrapers.grailed_scraper.grailed_algolia_client.get_seller_by_username",
            new_callable=AsyncMock,
            return_value=mock_profile_seller,
        ) as mock_get_seller,
        patch("app.bot.scraping_orchestrator.analytics_service.log_search"),
    ):
        results = await scraping_orchestrator.process_urls_concurrent(
            [onelink_item, onelink_profile], user_id=12345, username="tester"
        )

        assert len(results) == 2
        assert results[0]["success"] is True
        assert results[0]["platform"] == "grailed"
        assert results[0]["item_data"] == mock_item
        mock_get_listing.assert_called_once_with("103877007", ANY)

        assert results[1]["success"] is True
        assert results[1]["platform"] == "profile"
        assert results[1]["seller_data"] == mock_profile_seller
        mock_get_seller.assert_called_once_with("grailedseller", ANY)
