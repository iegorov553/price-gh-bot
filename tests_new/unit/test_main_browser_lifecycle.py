"""Application lifecycle tests for the active scraper browser."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.main import cleanup_resources, initialize_resources


@pytest.mark.asyncio
async def test_startup_warms_only_active_browser_when_enabled() -> None:
    cache = MagicMock(_connected=False)

    with (
        patch("app.main.config.bot.enable_headless_browser", True),
        patch(
            "app.scrapers.headless.get_global_browser", new=AsyncMock()
        ) as get_global_browser,
        patch(
            "app.services.browser_pool.get_browser_pool", new=AsyncMock()
        ) as get_browser_pool,
        patch(
            "app.services.cache_service.get_cache_service",
            new=AsyncMock(return_value=cache),
        ),
    ):
        await initialize_resources()

    get_global_browser.assert_awaited_once_with()
    get_browser_pool.assert_not_awaited()


@pytest.mark.asyncio
async def test_startup_does_not_launch_browser_when_disabled() -> None:
    cache = MagicMock(_connected=False)

    with (
        patch("app.main.config.bot.enable_headless_browser", False),
        patch(
            "app.scrapers.headless.get_global_browser", new=AsyncMock()
        ) as get_global_browser,
        patch(
            "app.services.cache_service.get_cache_service",
            new=AsyncMock(return_value=cache),
        ),
    ):
        await initialize_resources()

    get_global_browser.assert_not_awaited()


@pytest.mark.asyncio
async def test_shutdown_closes_active_browser_without_browser_pool() -> None:
    with (
        patch(
            "app.services.cache_service.shutdown_cache_service", new=AsyncMock()
        ),
        patch(
            "app.services.browser_pool.shutdown_browser_pool", new=AsyncMock()
        ) as shutdown_browser_pool,
        patch(
            "app.scrapers.headless.cleanup_global_browser", new=AsyncMock()
        ) as cleanup_global_browser,
    ):
        await cleanup_resources()

    cleanup_global_browser.assert_awaited_once_with()
    shutdown_browser_pool.assert_not_awaited()
