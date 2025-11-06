"""Tests for ResponseFormatter edge cases."""

from decimal import Decimal

import pytest

from app.bot.messages import ITEM_WARNING_NO_BUY_NOW
from app.bot.response_formatter import ResponseFormatter
from app.models import ItemData


@pytest.mark.asyncio
async def test_offer_only_listing_includes_warning_and_breakdown() -> None:
    """Offer-only listings should return full breakdown plus warning."""
    formatter = ResponseFormatter()
    item = ItemData(
        price=Decimal("120"), shipping_us=Decimal("0"), is_buyable=False, title="Test item"
    )

    result = {
        "success": True,
        "platform": "grailed",
        "item_data": item,
        "seller_data": None,
        "url": "https://example.com",
    }

    response = await formatter.format_item_response(result)

    assert "$120" in response
    assert ITEM_WARNING_NO_BUY_NOW in response
