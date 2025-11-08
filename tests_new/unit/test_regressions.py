"""Regression tests covering recent bug fixes in price-gh-bot."""

from __future__ import annotations

import sqlite3
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from types import SimpleNamespace
from typing import Any

import pytest

from app.bot import utils
from app.bot.analytics_tracker import AnalyticsTracker
from app.bot.messages import SELLER_OK_MESSAGE, SELLER_WARNING_LOW_RATING
from app.bot.response_formatter import response_formatter
from app.bot.scraping_orchestrator import ScrapingOrchestrator
from app.models import ItemData, PriceCalculation, SellerAdvisory, SellerData
from app.scrapers.grailed_scraper import GrailedScraper
from app.services.analytics import AnalyticsService
from app.services.cache_service import CacheConfig, CacheService

pytest.importorskip("pydantic_settings")


class _DummySession:
    """Lightweight stand-in for aiohttp.ClientSession used in tests."""

    def __init__(self) -> None:
        self.closed = False

    async def close(self) -> None:
        self.closed = True


@pytest.mark.asyncio
async def test_calculate_final_price_includes_customs(monkeypatch: pytest.MonkeyPatch) -> None:
    """Customs duty must be applied even when utils creates its own session."""

    dummy_session = _DummySession()

    monkeypatch.setattr(utils, "create_session", lambda: dummy_session)

    async def fake_customs(
        item_price: Decimal,
        shipping_us: Decimal,
        session: Any,
    ) -> Decimal:
        assert session is dummy_session
        return Decimal("12.34")

    monkeypatch.setattr(utils, "calculate_rf_customs_duty", fake_customs)

    result = await utils.calculate_final_price_async(
        item_price=Decimal("250"),
        shipping_us=Decimal("20"),
        shipping_russia=Decimal("0"),
    )

    assert isinstance(result, PriceCalculation)
    assert result.customs_duty == Decimal("12.34")
    assert dummy_session.closed is True


def test_format_seller_profile_response_handles_models() -> None:
    """Ensure seller profile formatter works with SellerData and SellerAdvisory objects."""

    seller = SellerData(
        num_reviews=120,
        avg_rating=4.9,
        trusted_badge=True,
        last_updated=datetime.now(UTC),
    )
    message = response_formatter.format_seller_profile_response(
        {
            "success": True,
            "seller_data": seller,
            "seller_advisory": SellerAdvisory(),
        }
    )

    assert message == SELLER_OK_MESSAGE


def test_cache_service_serialization_roundtrip() -> None:
    """CacheService should preserve Pydantic models when serializing/deserializing."""

    service = CacheService(CacheConfig(enabled=False))
    payload = {
        "success": True,
        "platform": "grailed",
        "item_data": ItemData(
            price=Decimal("199.99"),
            shipping_us=Decimal("15.00"),
            is_buyable=True,
            title="Sample Item",
            image_url=None,
        ),
        "seller_data": SellerData(
            num_reviews=42,
            avg_rating=4.7,
            trusted_badge=False,
            last_updated=datetime.now(UTC),
        ),
        "processing_time_ms": 321,
    }

    serialized = service._serialize_scraping_result(payload)
    restored = service._deserialize_scraping_result(serialized)

    assert isinstance(restored["item_data"], ItemData)
    assert restored["item_data"].price == Decimal("199.99")
    assert isinstance(restored["seller_data"], SellerData)
    assert restored["seller_data"].num_reviews == 42


class _FakeResponse:
    """Minimal async response used to simulate aiohttp.ClientResponse."""

    def __init__(self, headers: dict[str, str], body: str) -> None:
        self.headers = headers
        self._body = body

    async def __aenter__(self) -> _FakeResponse:
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:  # noqa: D401
        return None

    async def text(self) -> str:
        return self._body

    def raise_for_status(self) -> None:
        return None


class _FakeSession:
    """Session stub returning predefined responses."""

    def __init__(self, response: _FakeResponse) -> None:
        self._response = response

    def get(self, url: str) -> _FakeResponse:
        return self._response


@pytest.mark.asyncio
async def test_grailed_scraper_returns_none_for_json_payload() -> None:
    """Grailed scraper must fail gracefully when endpoint returns JSON instead of HTML."""

    scraper = GrailedScraper()
    fake_response = _FakeResponse(
        headers={"content-type": "application/json"},
        body='{"error": "not found"}',
    )
    session = _FakeSession(fake_response)

    result = await scraper.scrape_item("https://www.grailed.com/listings/invalid", session)

    assert result is None


def test_analytics_tracker_maps_fields_correctly() -> None:
    """Tracker should populate SearchAnalytics fields using the new schema."""

    recorded = {}

    class DummyAnalytics:
        def log_search(self, analytics: Any) -> None:
            recorded["payload"] = analytics

    tracker = AnalyticsTracker(DummyAnalytics())
    item = ItemData(
        price=Decimal("80.00"),
        shipping_us=Decimal("10.00"),
        is_buyable=True,
        title="Vintage Jacket",
        image_url=None,
    )

    tracker.log_url_processing(
        user_id=1,
        username="tester",
        url="https://www.ebay.com/itm/123",
        platform="ebay",
        success=True,
        processing_time_ms=250,
        error_type="timeout",
        item_data=item,
    )

    analytics = recorded["payload"]
    assert analytics.item_price == Decimal("80.00")
    assert analytics.shipping_us == Decimal("10.00")
    assert analytics.error_message == "timeout"
    assert analytics.item_title == "Vintage Jacket"
    assert analytics.seller_warning_reason is None
    assert analytics.seller_warning_message is None


@pytest.mark.asyncio
async def test_orchestrator_log_analytics_uses_new_schema(monkeypatch: pytest.MonkeyPatch) -> None:
    """Scraping orchestrator must log analytics compatible with SearchAnalytics."""

    recorded: dict[str, Any] = {}

    def fake_log_search(analytics: Any) -> None:
        recorded["payload"] = analytics

    monkeypatch.setattr(
        "app.bot.scraping_orchestrator.analytics_service",
        SimpleNamespace(log_search=fake_log_search),
    )

    orchestrator = ScrapingOrchestrator()
    result = {
        "url": "https://www.grailed.com/listings/456",
        "platform": "grailed",
        "success": True,
        "processing_time_ms": 500,
        "item_data": ItemData(
            price=Decimal("150.00"),
            shipping_us=Decimal("20.00"),
            is_buyable=True,
            title="Rare Hoodie",
            image_url=None,
        ),
        "seller_advisory": SellerAdvisory(reason="low_rating", message=SELLER_WARNING_LOW_RATING),
    }

    await orchestrator._log_analytics(result, user_id=10, username="tester")

    analytics = recorded["payload"]
    assert analytics.item_price == Decimal("150.00")
    assert analytics.shipping_us == Decimal("20.00")
    assert analytics.seller_score is None
    assert analytics.seller_category is None
    assert analytics.seller_warning_reason == "low_rating"
    assert analytics.seller_warning_message == SELLER_WARNING_LOW_RATING


def test_get_user_stats_supports_day_filter(tmp_path: pytest.TempPathFactory) -> None:
    """AnalyticsService.get_user_stats should filter results by days parameter."""

    analytics_dir = tmp_path / "analytics"
    analytics_dir.mkdir()
    db_path = analytics_dir / "analytics.db"
    service = AnalyticsService(str(db_path))

    now = datetime.now()
    older = now - timedelta(days=10)

    with sqlite3.connect(service.db_path) as conn:
        conn.execute(
            """
            INSERT INTO search_analytics
            (url, user_id, username, timestamp, platform, success, item_price,
             shipping_us, item_title, error_message, processing_time_ms,
             seller_score, seller_category, seller_warning_reason, seller_warning_message,
             final_price_usd, commission, is_buyable)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "https://example.com/recent",
                999,
                "tester",
                now,
                "grailed",
                1,
                100.0,
                10.0,
                "Recent item",
                None,
                200,
                None,
                None,
                None,
                None,
                120.0,
                12.0,
                1,
            ),
        )
        conn.execute(
            """
            INSERT INTO search_analytics
            (url, user_id, username, timestamp, platform, success, item_price,
             shipping_us, item_title, error_message, processing_time_ms,
             seller_score, seller_category, seller_warning_reason, seller_warning_message,
             final_price_usd, commission, is_buyable)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "https://example.com/old",
                999,
                "tester",
                older,
                "grailed",
                1,
                200.0,
                15.0,
                "Old item",
                None,
                300,
                None,
                None,
                None,
                None,
                230.0,
                20.0,
                1,
            ),
        )
        conn.commit()

    stats = service.get_user_stats(user_id=999, days=7, limit=10)

    assert stats["total_searches"] == 1
    assert stats["last_search"] == stats["first_search"]
