"""Unit tests for Grailed headless fallback and async shortlink resolution."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from playwright.async_api import TimeoutError as PlaywrightTimeoutError

from app.models import ItemData
from app.scrapers import headless
from app.scrapers.grailed_page import GrailedPageState
from app.scrapers.grailed_scraper import GrailedScraper
from app.scrapers.grailed_url_resolver import async_normalize_grailed_url
from app.scrapers.headless import GrailedHeadlessFetchResult


def _static_forbidden_session() -> MagicMock:
    session = MagicMock()
    response = MagicMock()
    response.status = 403
    session.get.return_value.__aenter__ = AsyncMock(return_value=response)
    return session


@pytest.mark.asyncio
async def test_grailed_scraper_records_blocked_headless_outcome_before_seller_extraction(
    caplog: pytest.LogCaptureFixture,
) -> None:
    scraper = GrailedScraper()
    url = "https://www.grailed.com/listings/123456"

    with patch(
        "app.scrapers.headless.fetch_grailed_page_headless", new_callable=AsyncMock
    ) as mock_headless, patch.object(
        scraper, "_extract_seller_data", new_callable=AsyncMock
    ) as mock_seller:
        mock_headless.return_value = GrailedHeadlessFetchResult(
            html=None, state=GrailedPageState.BLOCKED
        )

        result = await scraper.scrape_item(url, _static_forbidden_session())

    assert result is None
    mock_seller.assert_not_awaited()
    assert "Headless browser response was classified as blocked" in caplog.text


@pytest.mark.asyncio
async def test_grailed_scraper_extracts_seller_once_after_price_from_headless_listing() -> None:
    scraper = GrailedScraper()
    url = "https://www.grailed.com/listings/123456"
    listing_html = """<!DOCTYPE html>
<html><head>
<script id="__NEXT_DATA__" type="application/json">{"props":{"pageProps":{"listing":{"title":"Test Grailed Hoodie","price":250,"buyNowPrice":250,"shipping":{"us":{"amount":15}}}}}}</script>
</head><body></body></html>"""
    extraction_order: list[str] = []

    def extract_price(url: str, soup: object) -> tuple[int, bool]:
        extraction_order.append("price")
        return 250, True

    async def extract_seller(soup: object, session: object) -> None:
        extraction_order.append("seller")
        return None

    with patch(
        "app.scrapers.headless.fetch_grailed_page_headless", new_callable=AsyncMock
    ) as mock_headless, patch(
        "app.scrapers.grailed_scraper._extract_price_and_buyability", side_effect=extract_price
    ), patch.object(
        scraper, "_extract_seller_data", side_effect=extract_seller
    ) as mock_seller:
        mock_headless.return_value = GrailedHeadlessFetchResult(
            html=listing_html, state=GrailedPageState.LISTING
        )

        result = await scraper.scrape_item(url, _static_forbidden_session())

    assert result is not None
    assert result.price == 250
    assert extraction_order == ["price", "seller"]
    mock_seller.assert_awaited_once()


@pytest.mark.asyncio
async def test_async_normalize_grailed_url_static_payload() -> None:
    url = (
        "https://grailed.app.link?channel=Pasteboard&data=eyIkY2Fub25pY2FsX3VybCI6Imh0dHBzOi8vd3d3LmdyYWlsZWQuY29tL2xpc3RpbmdzLzEyMzQ1NiJ9"
    )
    res = await async_normalize_grailed_url(url)
    assert res == "https://www.grailed.com/listings/123456"


@pytest.mark.asyncio
async def test_async_normalize_grailed_url_http_head_redirect() -> None:
    url = "https://grailed.app.link/abc1234"
    mock_session = MagicMock()
    mock_response = MagicMock()
    mock_response.url = "https://www.grailed.com/listings/999999"
    mock_session.head.return_value.__aenter__ = AsyncMock(return_value=mock_response)

    res = await async_normalize_grailed_url(url, mock_session)
    assert res == "https://www.grailed.com/listings/999999"


@pytest.mark.asyncio
async def test_grailed_scraper_headless_fallback_on_http_error() -> None:
    scraper = GrailedScraper()
    url = "https://www.grailed.com/listings/123456"

    mock_session = MagicMock()
    # Simulate aiohttp session raising an exception on HTTP GET
    mock_session.get.return_value.__aenter__ = AsyncMock(side_effect=Exception("HTTP 403 Forbidden"))

    # Construct HTML with > 1000 characters to pass length check
    padding = "<!-- " + ("x" * 1000) + " -->"
    sample_html = f"""<!DOCTYPE html>
<html>
  <head>
    <script id="__NEXT_DATA__" type="application/json">{{"props":{{"pageProps":{{"listing":{{"title":"Test Grailed Hoodie","price":250,"buyNowPrice":250,"shipping":{{"us":{{"amount":15}}}}}}}}}}}}</script>
  </head>
  <body>{padding}</body>
</html>"""

    with patch("app.scrapers.headless.fetch_grailed_page_headless", new_callable=AsyncMock) as mock_headless, \
         patch("app.scrapers.headless.get_grailed_seller_data_headless", new_callable=AsyncMock) as mock_seller:
        mock_headless.return_value = GrailedHeadlessFetchResult(
            html=sample_html, state=GrailedPageState.LISTING
        )
        mock_seller.return_value = None
        result = await scraper.scrape_item(url, mock_session)

        mock_headless.assert_called_once_with(url)
        assert result is not None
        assert isinstance(result, ItemData)
        assert result.title == "Test Grailed Hoodie"
        assert result.price == 250
        assert result.shipping_us == 15


@pytest.mark.asyncio
async def test_fetch_retries_incomplete_page_once() -> None:
    browser = MagicMock()
    first = AsyncMock()
    first.content.return_value = "<html><body>Grailed</body></html>"
    second = AsyncMock()
    second.content.return_value = '<html><script id="__NEXT_DATA__">{}</script></html>'
    browser.get_page = AsyncMock(side_effect=[first, second])

    result = await headless._fetch_html("https://www.grailed.com/listings/1", browser)

    assert result is not None
    assert "__NEXT_DATA__" in result
    assert browser.get_page.await_count == 2


@pytest.mark.asyncio
async def test_fetch_retries_incomplete_content_after_readiness_timeout() -> None:
    browser = MagicMock()
    first = AsyncMock()
    first.wait_for_function.side_effect = PlaywrightTimeoutError("readiness timed out")
    first.content.return_value = "<html><body>Grailed</body></html>"
    second = AsyncMock()
    second.content.return_value = '<html><script id="__NEXT_DATA__">{}</script></html>'
    browser.get_page = AsyncMock(side_effect=[first, second])

    result = await headless._fetch_grailed_page_html(
        "https://www.grailed.com/listings/1", browser
    )

    assert result.state is GrailedPageState.LISTING
    assert result.html == '<html><script id="__NEXT_DATA__">{}</script></html>'
    first.content.assert_awaited_once_with()
    assert browser.get_page.await_count == 2


@pytest.mark.asyncio
async def test_fetch_exposes_blocked_page_state() -> None:
    browser = MagicMock()
    page = AsyncMock()
    page.content.return_value = "<html><body>You are unable to access grailed.com</body></html>"
    browser.get_page = AsyncMock(return_value=page)

    result = await headless._fetch_grailed_page_html(
        "https://www.grailed.com/listings/1", browser
    )

    assert result.html is None
    assert result.state is GrailedPageState.BLOCKED
    assert browser.get_page.await_count == 1


@pytest.mark.asyncio
async def test_fetch_logs_navigation_failure_without_url_credentials(caplog: pytest.LogCaptureFixture) -> None:
    browser = MagicMock()
    page = AsyncMock()
    page.goto.side_effect = RuntimeError("navigation failed")
    browser.get_page = AsyncMock(return_value=page)

    result = await headless._fetch_html(
        "https://buyer:secret@grailed.com/listings/1?session=private", browser
    )

    assert result is None
    assert "https://grailed.com/listings/1" in caplog.text
    assert "buyer:secret" not in caplog.text
    assert "session=private" not in caplog.text


@pytest.mark.asyncio
@pytest.mark.parametrize("failing_operation", ["goto", "wait_for_function", "content"])
async def test_fetch_does_not_retry_page_operation_exceptions(failing_operation: str) -> None:
    browser = MagicMock()
    page = AsyncMock()
    getattr(page, failing_operation).side_effect = RuntimeError("page operation failed")
    browser.get_page = AsyncMock(return_value=page)

    result = await headless._fetch_html("https://www.grailed.com/listings/1", browser)

    assert result is None
    assert browser.get_page.await_count == 1
