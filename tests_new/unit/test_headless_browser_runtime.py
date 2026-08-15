"""Runtime configuration tests for the shared Chromium instance."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.scrapers import headless
from app.scrapers.headless import HeadlessBrowser


@pytest.mark.asyncio
async def test_headless_browser_uses_stock_new_headless_chromium() -> None:
    playwright_manager = MagicMock()
    playwright = MagicMock()
    browser = MagicMock()
    browser.version = "140.0.0.0"
    context = AsyncMock()
    page = AsyncMock()
    context.new_page.return_value = page
    browser.new_context = AsyncMock(return_value=context)
    playwright.chromium.launch = AsyncMock(return_value=browser)
    playwright_manager.start = AsyncMock(return_value=playwright)

    with patch("app.scrapers.headless.async_playwright", return_value=playwright_manager):
        runtime = HeadlessBrowser()
        await runtime.start()
        returned_page = await runtime.get_page()

    playwright.chromium.launch.assert_awaited_once_with(
        channel="chromium",
        headless=True,
        args=["--no-sandbox", "--disable-dev-shm-usage"],
    )
    browser.new_context.assert_awaited_once_with()
    assert returned_page is page
    page.add_init_script.assert_not_awaited()
    context.route.assert_not_awaited()

    await runtime.stop()


@pytest.mark.asyncio
async def test_headless_browser_reuses_context_between_pages() -> None:
    playwright_manager = MagicMock()
    playwright = MagicMock()
    browser = MagicMock()
    browser.version = "140.0.0.0"
    first_page = AsyncMock()
    second_page = AsyncMock()
    context = AsyncMock()
    context.new_page.side_effect = [first_page, second_page]
    browser.new_context = AsyncMock(return_value=context)
    playwright.chromium.launch = AsyncMock(return_value=browser)
    playwright_manager.start = AsyncMock(return_value=playwright)

    with patch("app.scrapers.headless.async_playwright", return_value=playwright_manager):
        runtime = HeadlessBrowser()
        await runtime.start()
        assert await runtime.get_page() is first_page
        assert await runtime.get_page() is second_page

    browser.new_context.assert_awaited_once_with()
    assert context.new_page.await_count == 2

    await runtime.stop()


@pytest.mark.asyncio
async def test_global_browser_restarts_after_disconnect() -> None:
    stale = MagicMock()
    stale.is_connected.return_value = False
    stale.stop = AsyncMock()
    fresh = MagicMock()
    fresh.is_connected.return_value = True
    fresh.start = AsyncMock()

    with patch.object(headless, "HeadlessBrowser", return_value=fresh):
        headless._global_browser = stale
        try:
            result = await headless.get_global_browser()
        finally:
            headless._global_browser = None

    assert result is fresh
    stale.stop.assert_awaited_once_with()
    fresh.start.assert_awaited_once_with()
