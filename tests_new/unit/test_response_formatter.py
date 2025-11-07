"""Tests for ResponseFormatter edge cases."""

from datetime import UTC, datetime
from decimal import Decimal

import pytest

from app.bot.messages import (
    CALCULATION_TIMESTAMP_FORMAT,
    CALCULATION_TIMESTAMP_LINE,
    ITEM_WARNING_NO_BUY_NOW,
    NEGOTIATION_NOTE_LINE,
)
from app.bot.response_formatter import ResponseFormatter
from app.models import ItemData, SellerData

FIXED_TIME = datetime(2025, 1, 2, 15, 45, tzinfo=UTC)


@pytest.mark.asyncio
async def test_offer_only_listing_includes_warning_and_breakdown() -> None:
    """Offer-only listings should return full breakdown plus warning."""
    formatter = ResponseFormatter(clock=lambda: FIXED_TIME)
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
    lines = response.splitlines()
    warning_index = lines.index(ITEM_WARNING_NO_BUY_NOW)
    note_index = lines.index(NEGOTIATION_NOTE_LINE)
    assert warning_index < note_index

    expected_timestamp = CALCULATION_TIMESTAMP_LINE.format(
        datetime=FIXED_TIME.strftime(CALCULATION_TIMESTAMP_FORMAT),
        offset="+00:00",
    )
    assert lines[-1] == expected_timestamp


@pytest.mark.asyncio
async def test_breakdown_without_warning_still_appends_note_and_timestamp() -> None:
    """Responses без предупреждений завершаются заметкой и временной меткой."""
    formatter = ResponseFormatter(clock=lambda: FIXED_TIME)
    item = ItemData(
        price=Decimal("200"),
        shipping_us=Decimal("20"),
        is_buyable=True,
        title="Full data item",
    )
    result = {
        "success": True,
        "platform": "grailed",
        "item_data": item,
        "seller_data": SellerData(num_reviews=10, avg_rating=4.9),
        "url": "https://example.com",
    }

    response = await formatter.format_item_response(result)
    lines = response.splitlines()
    note_index = lines.index(NEGOTIATION_NOTE_LINE)
    expected_timestamp = CALCULATION_TIMESTAMP_LINE.format(
        datetime=FIXED_TIME.strftime(CALCULATION_TIMESTAMP_FORMAT),
        offset="+00:00",
    )
    assert lines[-1] == expected_timestamp
    assert note_index == len(lines) - 3
