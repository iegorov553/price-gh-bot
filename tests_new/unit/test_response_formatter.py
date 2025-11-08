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


def _find_subsequence(lines: list[str], block: list[str]) -> int:
    """Return the start index of the block inside lines or raise AssertionError."""
    for idx in range(len(lines) - len(block) + 1):
        if lines[idx : idx + len(block)] == block:
            return idx
    raise AssertionError(f"Subsequence {block} not found in response")


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
    lines = response.splitlines()
    warning_lines = ITEM_WARNING_NO_BUY_NOW.splitlines()
    note_lines = NEGOTIATION_NOTE_LINE.splitlines()
    warning_index = _find_subsequence(lines, warning_lines)
    note_index = _find_subsequence(lines, note_lines)
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
    note_lines = NEGOTIATION_NOTE_LINE.splitlines()
    note_index = _find_subsequence(lines, note_lines)
    expected_timestamp = CALCULATION_TIMESTAMP_LINE.format(
        datetime=FIXED_TIME.strftime(CALCULATION_TIMESTAMP_FORMAT),
        offset="+00:00",
    )
    assert lines[-1] == expected_timestamp
    assert note_index + len(note_lines) <= len(lines) - 2
