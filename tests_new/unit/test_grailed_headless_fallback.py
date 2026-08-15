"""Unit tests for Grailed headless module and async shortlink resolution."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from playwright.async_api import TimeoutError as PlaywrightTimeoutError

from app.scrapers import headless
from app.scrapers.grailed_page import GrailedPageState, classify_grailed_html
from app.scrapers.grailed_url_resolver import async_normalize_grailed_url
from app.scrapers.headless import GrailedHeadlessFetchResult


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
async def test_fetch_page_html_headless_waits_before_returning_raw_blocked_html() -> None:
    url = "https://www.grailed.com/listings/1"
    blocked_html = "<html><body>You are unable to access grailed.com</body></html>"
    acquisition_events: list[tuple[str, int | None]] = []

    async def record_wait(timeout: int) -> None:
        acquisition_events.append(("wait", timeout))

    async def record_content() -> str:
        acquisition_events.append(("content", None))
        return blocked_html

    browser = MagicMock()
    page = AsyncMock()
    page.wait_for_timeout.side_effect = record_wait
    page.content.side_effect = record_content
    browser.get_page = AsyncMock(return_value=page)

    with patch(
        "app.scrapers.headless.get_global_browser",
        new=AsyncMock(return_value=browser),
    ):
        result = await headless.fetch_page_html_headless(url)

    assert result == blocked_html
    assert acquisition_events == [("wait", 1500), ("content", None)]
    page.goto.assert_awaited_once_with(url, wait_until="domcontentloaded", timeout=25_000)
    page.close.assert_awaited_once_with()


@pytest.mark.asyncio
async def test_fetch_retries_incomplete_page_once() -> None:
    browser = MagicMock()
    first = AsyncMock()
    first.content.return_value = "<html><body>Grailed</body></html>"
    second = AsyncMock()
    second.content.return_value = '<html><script id="__NEXT_DATA__">{}</script></html>'
    browser.get_page = AsyncMock(side_effect=[first, second])

    result = await headless._fetch_grailed_page_html("https://www.grailed.com/listings/1", browser)

    assert result.state is GrailedPageState.LISTING
    assert result.html == '<html><script id="__NEXT_DATA__">{}</script></html>'
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

    result = await headless._fetch_grailed_page_html("https://www.grailed.com/listings/1", browser)

    assert result.state is GrailedPageState.LISTING
    assert result.html == '<html><script id="__NEXT_DATA__">{}</script></html>'
    assert first.content.await_count == 2
    assert browser.get_page.await_count == 2


@pytest.mark.asyncio
async def test_fetch_stops_on_blocked_content_after_readiness_timeout() -> None:
    browser = MagicMock()
    page = AsyncMock()
    page.wait_for_function.side_effect = PlaywrightTimeoutError("readiness timed out")
    page.content.return_value = "<html><body>You are unable to access grailed.com</body></html>"
    browser.get_page = AsyncMock(return_value=page)

    result = await headless._fetch_grailed_page_html("https://www.grailed.com/listings/1", browser)

    assert result.state is GrailedPageState.BLOCKED
    assert result.html is None
    assert page.content.await_count == 2
    assert browser.get_page.await_count == 1


@pytest.mark.asyncio
async def test_fetch_exposes_blocked_page_state() -> None:
    browser = MagicMock()
    page = AsyncMock()
    page.content.return_value = "<html><body>You are unable to access grailed.com</body></html>"
    browser.get_page = AsyncMock(return_value=page)

    result = await headless._fetch_grailed_page_html("https://www.grailed.com/listings/1", browser)

    assert result.html is None
    assert result.state is GrailedPageState.BLOCKED
    assert browser.get_page.await_count == 1


@pytest.mark.parametrize(
    "html",
    [
        "<html><head><title>Just a moment...</title></head></html>",
        "<html><body><h2>Performing security verification</h2></body></html>",
        (
            "<html><body>This website uses a security service to protect against "
            "malicious bots.</body></html>"
        ),
    ],
)
def test_classifies_current_cloudflare_challenge_markers(html: str) -> None:
    assert classify_grailed_html(html) is GrailedPageState.BLOCKED


@pytest.mark.asyncio
async def test_fetch_waits_for_challenge_to_resolve_in_same_page() -> None:
    blocked_html = "<html><head><title>Just a moment...</title></head></html>"
    listing_html = '<html><script id="__NEXT_DATA__">{}</script></html>'
    browser = MagicMock()
    page = AsyncMock()
    response = MagicMock(status=403)
    page.goto.return_value = response
    page.content.side_effect = [blocked_html, listing_html]
    browser.get_page = AsyncMock(return_value=page)

    result = await headless._fetch_grailed_page_html(
        "https://www.grailed.com/listings/1", browser
    )

    assert result.state is GrailedPageState.LISTING
    assert result.html == listing_html
    page.wait_for_function.assert_awaited_once()
    assert page.wait_for_function.await_args.kwargs["timeout"] == 12_000
    assert browser.get_page.await_count == 1


@pytest.mark.asyncio
async def test_fetch_returns_blocked_after_challenge_grace_without_retry() -> None:
    blocked_html = "<html><head><title>Just a moment...</title></head></html>"
    browser = MagicMock()
    page = AsyncMock()
    page.content.side_effect = [blocked_html, blocked_html]
    page.wait_for_function.side_effect = PlaywrightTimeoutError("challenge remained")
    browser.get_page = AsyncMock(return_value=page)

    result = await headless._fetch_grailed_page_html(
        "https://www.grailed.com/listings/1", browser
    )

    assert result.state is GrailedPageState.BLOCKED
    assert result.html is None
    assert browser.get_page.await_count == 1


@pytest.mark.asyncio
async def test_fetch_does_not_retry_after_challenge_becomes_incomplete() -> None:
    blocked_html = "<html><head><title>Just a moment...</title></head></html>"
    incomplete_html = "<html><body>Grailed shell</body></html>"
    browser = MagicMock()
    page = AsyncMock()
    page.content.side_effect = [blocked_html, incomplete_html]
    browser.get_page = AsyncMock(return_value=page)

    result = await headless._fetch_grailed_page_html(
        "https://www.grailed.com/listings/1", browser
    )

    assert result.state is GrailedPageState.BLOCKED
    assert result.html is None
    assert browser.get_page.await_count == 1


@pytest.mark.asyncio
async def test_global_browser_operations_are_serialized() -> None:
    browser = MagicMock()
    active = 0
    peak_active = 0

    async def record_fetch(url: str, current_browser: object) -> str:
        nonlocal active, peak_active
        assert current_browser is browser
        active += 1
        peak_active = max(peak_active, active)
        await asyncio.sleep(0)
        active -= 1
        return url

    with (
        patch(
            "app.scrapers.headless.get_global_browser",
            new=AsyncMock(return_value=browser),
        ),
        patch("app.scrapers.headless._fetch_html", side_effect=record_fetch),
    ):
        results = await asyncio.gather(
            headless.fetch_page_html_headless("https://grailed.com/listings/1"),
            headless.fetch_page_html_headless("https://grailed.com/listings/2"),
        )

    assert results == [
        "https://grailed.com/listings/1",
        "https://grailed.com/listings/2",
    ]
    assert peak_active == 1


@pytest.mark.asyncio
async def test_fetch_logs_navigation_failure_without_url_credentials(
    caplog: pytest.LogCaptureFixture,
) -> None:
    browser = MagicMock()
    page = AsyncMock()
    page.goto.side_effect = RuntimeError("navigation failed")
    browser.get_page = AsyncMock(return_value=page)

    result = await headless._fetch_grailed_page_html(
        "https://buyer:secret@grailed.com/listings/1?session=private", browser
    )

    assert result.html is None
    assert "https://grailed.com/listings/1" in caplog.text
    assert "buyer:secret" not in caplog.text
    assert "session=private" not in caplog.text


@pytest.mark.asyncio
@pytest.mark.parametrize("failing_operation", ["goto", "wait_for_function", "content"])
async def test_fetch_does_not_retry_page_operation_exceptions(failing_operation: str) -> None:
    browser = MagicMock()
    page = AsyncMock()
    page.content.return_value = "<html><body>Grailed</body></html>"
    getattr(page, failing_operation).side_effect = RuntimeError("page operation failed")
    browser.get_page = AsyncMock(return_value=page)

    result = await headless._fetch_grailed_page_html("https://www.grailed.com/listings/1", browser)

    assert result.html is None
    assert browser.get_page.await_count == 1
