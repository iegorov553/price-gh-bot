"""Unit tests for GrailedAlgoliaClient."""

from decimal import Decimal
from unittest.mock import AsyncMock

import aiohttp
import pytest

from app.services import GrailedAlgoliaClient, grailed_algolia_client

SAMPLE_ACTIVE_HIT = {
    "id": 99406229,
    "title": "Vissla Board Shorts",
    "price": 34,
    "buynow": True,
    "makeoffer": True,
    "sold": False,
    "deleted": False,
    "shipping": {"us": {"amount": 9, "enabled": True}},
    "user": {
        "id": 13535449,
        "username": "EraLuxe",
        "seller_score": {"rating_average": 4.87, "rating_count": 118},
        "trusted_seller": True,
    },
    "cover_photo": {"image_url": "https://media-assets.grailed.com/prd/listing/temp/sample.jpg"},
}

SAMPLE_OFFER_ONLY_HIT = {
    "id": 103179342,
    "title": "Nike Sweatpant",
    "price": 50,
    "buynow": False,
    "makeoffer": True,
    "sold": False,
    "deleted": False,
    "shipping": {"us": {"amount": 18.99, "enabled": True}},
    "user": {
        "id": 2204,
        "username": "secondlifeinc",
        "seller_score": {"rating_average": 4.85, "rating_count": 2204},
        "trusted_seller": False,
    },
    "cover_photo": {"url": "https://media-assets.grailed.com/prd/listing/temp/sample2.jpg"},
}

SAMPLE_FREE_SHIPPING_HIT = {
    "id": 101466749,
    "title": "Vintage T-Shirt",
    "price": 25,
    "buynow": True,
    "makeoffer": False,
    "shipping": {"us": {"amount": 0, "enabled": False}},
    "user": {
        "id": 555,
        "username": "vintageshop",
        "seller_score": {"rating_average": 5.0, "rating_count": 10},
        "trusted_seller": False,
    },
    "cover_photo": {"image_url": "https://media-assets.grailed.com/prd/listing/temp/sample3.jpg"},
}

SAMPLE_SOLD_HIT = {
    "id": 88776655,
    "title": "Arc'teryx Beta LT Jacket",
    "price": 350,
    "buynow": True,
    "makeoffer": False,
    "sold": True,
    "deleted": False,
    "shipping": {"us": {"amount": 15, "enabled": True}},
    "user": {
        "id": 998877,
        "username": "gorpcore_seller",
        "seller_score": {"rating_average": 5.0, "rating_count": 42},
        "trusted_seller": True,
    },
    "cover_photo": {
        "image_url": "https://media-assets.grailed.com/prd/listing/temp/sold_sample.jpg"
    },
}


@pytest.mark.asyncio
async def test_get_listing_by_id_success():
    client = GrailedAlgoliaClient()
    mock_resp_data = {"results": [{"hits": [SAMPLE_ACTIVE_HIT], "nbHits": 1}]}

    mock_session = AsyncMock(spec=aiohttp.ClientSession)
    mock_post_ctx = AsyncMock()
    mock_post_ctx.status = 200
    mock_post_ctx.json = AsyncMock(return_value=mock_resp_data)
    mock_session.post.return_value.__aenter__.return_value = mock_post_ctx

    item, seller = await client.get_listing_by_id(99406229, mock_session)

    assert item is not None
    assert item.title == "Vissla Board Shorts"
    assert item.price == Decimal("34")
    assert item.shipping_us == Decimal("9")
    assert item.is_sold is False
    assert item.is_buyable is True
    assert item.image_url == "https://media-assets.grailed.com/prd/listing/temp/sample.jpg"

    assert seller is not None
    assert seller.num_reviews == 118
    assert seller.avg_rating == 4.87
    assert seller.trusted_badge is True
    assert seller.technical_issue is False


@pytest.mark.asyncio
async def test_get_listing_by_id_sold_listing_fallback():
    client = GrailedAlgoliaClient()
    mock_resp_data = {
        "results": [
            {"hits": [], "nbHits": 0},
            {"hits": [SAMPLE_SOLD_HIT], "nbHits": 1},
        ]
    }

    mock_session = AsyncMock(spec=aiohttp.ClientSession)
    mock_post_ctx = AsyncMock()
    mock_post_ctx.status = 200
    mock_post_ctx.json = AsyncMock(return_value=mock_resp_data)
    mock_session.post.return_value.__aenter__.return_value = mock_post_ctx

    item, seller = await client.get_listing_by_id(88776655, mock_session)

    assert item is not None
    assert item.title == "Arc'teryx Beta LT Jacket"
    assert item.price == Decimal("350")
    assert item.shipping_us == Decimal("15")
    assert item.is_sold is True
    assert item.is_buyable is False
    assert item.image_url == "https://media-assets.grailed.com/prd/listing/temp/sold_sample.jpg"

    assert seller is not None
    assert seller.num_reviews == 42
    assert seller.avg_rating == 5.0
    assert seller.trusted_badge is True


@pytest.mark.asyncio
async def test_get_listing_by_id_multi_query_payload_structure():
    client = GrailedAlgoliaClient()
    mock_resp_data = {
        "results": [
            {"hits": [SAMPLE_ACTIVE_HIT], "nbHits": 1},
            {"hits": [], "nbHits": 0},
        ]
    }

    mock_session = AsyncMock(spec=aiohttp.ClientSession)
    mock_post_ctx = AsyncMock()
    mock_post_ctx.status = 200
    mock_post_ctx.json = AsyncMock(return_value=mock_resp_data)
    mock_session.post.return_value.__aenter__.return_value = mock_post_ctx

    await client.get_listing_by_id(99406229, mock_session)

    mock_session.post.assert_called_once()
    call_kwargs = mock_session.post.call_args.kwargs
    payload = call_kwargs["json"]
    assert "requests" in payload
    assert len(payload["requests"]) == 2
    assert payload["requests"][0]["indexName"] == "Listing_production"
    assert payload["requests"][0]["params"] == "filters=id%3D99406229&hitsPerPage=1"
    assert payload["requests"][1]["indexName"] == "Listing_sold_production"
    assert payload["requests"][1]["params"] == "filters=id%3D99406229&hitsPerPage=1"


@pytest.mark.asyncio
async def test_get_listing_by_id_offer_only():
    client = GrailedAlgoliaClient()
    mock_resp_data = {"results": [{"hits": [SAMPLE_OFFER_ONLY_HIT], "nbHits": 1}]}

    mock_session = AsyncMock(spec=aiohttp.ClientSession)
    mock_post_ctx = AsyncMock()
    mock_post_ctx.status = 200
    mock_post_ctx.json = AsyncMock(return_value=mock_resp_data)
    mock_session.post.return_value.__aenter__.return_value = mock_post_ctx

    item, seller = await client.get_listing_by_id("103179342", mock_session)

    assert item is not None
    assert item.is_buyable is False
    assert item.shipping_us == Decimal("18.99")
    assert item.image_url == "https://media-assets.grailed.com/prd/listing/temp/sample2.jpg"

    assert seller is not None
    assert seller.num_reviews == 2204
    assert seller.avg_rating == 4.85
    assert seller.trusted_badge is False


@pytest.mark.asyncio
async def test_get_listing_by_id_shipping_disabled_is_zero():
    client = GrailedAlgoliaClient()
    mock_resp_data = {"results": [{"hits": [SAMPLE_FREE_SHIPPING_HIT], "nbHits": 1}]}

    mock_session = AsyncMock(spec=aiohttp.ClientSession)
    mock_post_ctx = AsyncMock()
    mock_post_ctx.status = 200
    mock_post_ctx.json = AsyncMock(return_value=mock_resp_data)
    mock_session.post.return_value.__aenter__.return_value = mock_post_ctx

    item, seller = await client.get_listing_by_id(101466749, mock_session)

    assert item is not None
    assert item.shipping_us == Decimal("0")


@pytest.mark.asyncio
async def test_get_listing_by_id_not_found():
    client = GrailedAlgoliaClient()
    mock_resp_data = {"results": [{"hits": [], "nbHits": 0}]}

    mock_session = AsyncMock(spec=aiohttp.ClientSession)
    mock_post_ctx = AsyncMock()
    mock_post_ctx.status = 200
    mock_post_ctx.json = AsyncMock(return_value=mock_resp_data)
    mock_session.post.return_value.__aenter__.return_value = mock_post_ctx

    item, seller = await client.get_listing_by_id(99999999, mock_session)
    assert item is None
    assert seller is None


@pytest.mark.asyncio
async def test_get_listing_by_id_http_403_or_error():
    client = GrailedAlgoliaClient()
    mock_session = AsyncMock(spec=aiohttp.ClientSession)
    mock_post_ctx = AsyncMock()
    mock_post_ctx.status = 403
    mock_post_ctx.text = AsyncMock(return_value='{"message":"Invalid key"}')
    mock_session.post.return_value.__aenter__.return_value = mock_post_ctx

    item, seller = await client.get_listing_by_id(99406229, mock_session)
    assert item is None
    assert seller is None


@pytest.mark.asyncio
async def test_get_listing_by_id_timeout():
    client = GrailedAlgoliaClient()
    mock_session = AsyncMock(spec=aiohttp.ClientSession)
    mock_session.post.side_effect = TimeoutError("Request timed out")

    item, seller = await client.get_listing_by_id(99406229, mock_session)
    assert item is None
    assert seller is None


@pytest.mark.asyncio
async def test_get_listing_by_id_missing_price():
    client = GrailedAlgoliaClient()
    malformed_hit = {
        "id": 12345,
        "title": "Item Without Price",
        "price": None,
    }
    mock_resp_data = {"results": [{"hits": [malformed_hit], "nbHits": 1}]}

    mock_session = AsyncMock(spec=aiohttp.ClientSession)
    mock_post_ctx = AsyncMock()
    mock_post_ctx.status = 200
    mock_post_ctx.json = AsyncMock(return_value=mock_resp_data)
    mock_session.post.return_value.__aenter__.return_value = mock_post_ctx

    item, seller = await client.get_listing_by_id(12345, mock_session)
    assert item is None
    assert seller is None


@pytest.mark.asyncio
async def test_get_seller_by_username_success():
    client = GrailedAlgoliaClient()
    mock_resp_data = {"results": [{"hits": [SAMPLE_ACTIVE_HIT], "nbHits": 1}]}

    mock_session = AsyncMock(spec=aiohttp.ClientSession)
    mock_post_ctx = AsyncMock()
    mock_post_ctx.status = 200
    mock_post_ctx.json = AsyncMock(return_value=mock_resp_data)
    mock_session.post.return_value.__aenter__.return_value = mock_post_ctx

    seller = await client.get_seller_by_username("eraluxe", mock_session)
    assert seller is not None
    assert seller.num_reviews == 118
    assert seller.avg_rating == 4.87
    assert seller.trusted_badge is True


@pytest.mark.asyncio
async def test_get_seller_by_username_mismatch():
    client = GrailedAlgoliaClient()
    mock_resp_data = {"results": [{"hits": [SAMPLE_ACTIVE_HIT], "nbHits": 1}]}

    mock_session = AsyncMock(spec=aiohttp.ClientSession)
    mock_post_ctx = AsyncMock()
    mock_post_ctx.status = 200
    mock_post_ctx.json = AsyncMock(return_value=mock_resp_data)
    mock_session.post.return_value.__aenter__.return_value = mock_post_ctx

    seller = await client.get_seller_by_username("other_seller", mock_session)
    assert seller is None


@pytest.mark.asyncio
async def test_get_seller_by_username_not_found():
    client = GrailedAlgoliaClient()
    mock_resp_data = {"results": [{"hits": [], "nbHits": 0}]}

    mock_session = AsyncMock(spec=aiohttp.ClientSession)
    mock_post_ctx = AsyncMock()
    mock_post_ctx.status = 200
    mock_post_ctx.json = AsyncMock(return_value=mock_resp_data)
    mock_session.post.return_value.__aenter__.return_value = mock_post_ctx

    seller = await client.get_seller_by_username("nonexistent", mock_session)
    assert seller is None


@pytest.mark.asyncio
async def test_get_seller_by_username_http_error():
    client = GrailedAlgoliaClient()
    mock_session = AsyncMock(spec=aiohttp.ClientSession)
    mock_post_ctx = AsyncMock()
    mock_post_ctx.status = 500
    mock_post_ctx.text = AsyncMock(return_value="Internal Server Error")
    mock_session.post.return_value.__aenter__.return_value = mock_post_ctx

    seller = await client.get_seller_by_username("eraluxe", mock_session)
    assert seller is None


@pytest.mark.asyncio
async def test_get_seller_by_username_timeout():
    client = GrailedAlgoliaClient()
    mock_session = AsyncMock(spec=aiohttp.ClientSession)
    mock_session.post.side_effect = TimeoutError("Timeout")

    seller = await client.get_seller_by_username("eraluxe", mock_session)
    assert seller is None


def test_global_grailed_algolia_client_instance():
    assert isinstance(grailed_algolia_client, GrailedAlgoliaClient)
