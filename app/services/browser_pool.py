"""Пул браузеров для оптимизации headless browser операций.

Этот модуль предоставляет BrowserPool для переиспользования браузеров
вместо создания нового экземпляра для каждого запроса.
"""

import asyncio
import logging
from typing import TYPE_CHECKING, Any

from playwright.async_api import Browser, BrowserContext, Page, Playwright, async_playwright

if TYPE_CHECKING:
    from playwright.async_api import Route
else:
    Route = Any

logger = logging.getLogger(__name__)


class BrowserPool:
    """Пул браузеров для переиспользования с оптимизированными настройками.

    Сокращает время инициализации с 3-5 секунд до <1 секунды
    за счет предварительного прогрева браузеров.
    """

    def __init__(self, max_size: int = 3, max_contexts_per_browser: int = 5):
        """Инициализирует пул браузеров.

        Args:
            max_size: Максимальное количество браузеров в пуле
            max_contexts_per_browser: Максимальное количество контекстов на браузер
        """
        self.max_size = max_size
        self.max_contexts_per_browser = max_contexts_per_browser
        self._browsers: list[Browser] = []
        self._contexts: list[BrowserContext] = []
        self._lock = asyncio.Lock()
        self._warm_pool_ready = asyncio.Event()
        self._playwright: Playwright | None = None
        self._browser_stats = {"created": 0, "reused": 0}

    async def initialize(self) -> None:
        """Предварительный прогрев пула браузеров."""
        async with self._lock:
            if self._warm_pool_ready.is_set():
                return

            try:
                self._playwright = await async_playwright().start()

                for i in range(self.max_size):
                    browser = await self._create_optimized_browser()
                    self._browsers.append(browser)
                    logger.info(f"Браузер {i + 1}/{self.max_size} инициализирован")

                    # Создаем контексты заранее
                    for _j in range(self.max_contexts_per_browser):
                        context = await self._create_optimized_context(browser)
                        self._contexts.append(context)

                self._warm_pool_ready.set()
                logger.info(
                    f"Пул браузеров готов: {self.max_size} браузеров, {len(self._contexts)} контекстов"
                )

            except Exception as e:
                logger.error(f"Ошибка инициализации пула браузеров: {e}")
                raise

    async def _create_optimized_browser(self) -> Browser:
        """Создает браузер с оптимизированными настройками для скорости.

        Returns:
            Настроенный экземпляр Browser
        """
        if not self._playwright:
            raise RuntimeError("Playwright не инициализирован")

        return await self._playwright.chromium.launch(
            headless=True,
            args=[
                "--disable-dev-shm-usage",
                "--disable-gpu",
                "--disable-background-timer-throttling",
                "--disable-renderer-backgrounding",
                "--disable-backgrounding-occluded-windows",
                "--disable-ipc-flooding-protection",
                "--disable-background-media-suspend",
                "--no-sandbox",
                "--disable-setuid-sandbox",
                "--disable-web-security",
                "--disable-features=TranslateUI",
                "--disable-extensions",
                "--memory-pressure-off",
            ],
        )

    async def _create_optimized_context(self, browser: Browser) -> BrowserContext:
        """Создает контекст с блокировкой ресурсов для ускорения.

        Args:
            browser: Экземпляр браузера

        Returns:
            Настроенный BrowserContext
        """
        context = await browser.new_context(
            viewport={"width": 1280, "height": 720},
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            java_script_enabled=True,
            accept_downloads=False,
        )

        # Блокируем тяжелые ресурсы для ускорения
        def _should_block(url: str) -> bool:
            return any(
                ext in url.lower()
                for ext in [
                    ".jpg",
                    ".jpeg",
                    ".png",
                    ".gif",
                    ".svg",
                    ".webp",
                    ".woff",
                    ".woff2",
                    ".ttf",
                    ".eot",
                    ".mp4",
                    ".mp3",
                    ".avi",
                    ".mov",
                    "google-analytics",
                    "googletagmanager",
                    "facebook.net",
                ]
            )

        async def _abort_route(route: Route) -> None:
            await route.abort()

        await context.route(_should_block, _abort_route)

        return context

    async def acquire_page(self) -> Page:
        """Получает готовую страницу из пула.

        Returns:
            Готовая к использованию страница
        """
        await self._warm_pool_ready.wait()

        async with self._lock:
            if self._contexts:
                context = self._contexts.pop()
                page = await context.new_page()
                self._browser_stats["reused"] += 1
                return page

            # Fallback: создаем новую страницу
            if self._browsers:
                browser = self._browsers[0]
                context = await self._create_optimized_context(browser)
                page = await context.new_page()
                self._browser_stats["created"] += 1
                return page

            # Экстренный fallback
            browser = await self._create_optimized_browser()
            context = await self._create_optimized_context(browser)
            page = await context.new_page()
            self._browser_stats["created"] += 1
            return page

    async def release_page(self, page: Page) -> None:
        """Возвращает страницу в пул.

        Args:
            page: Страница для освобождения
        """
        try:
            context = page.context
            await page.close()

            # Если контекст не слишком загружен, возвращаем в пул
            if len(self._contexts) < self.max_size * self.max_contexts_per_browser:
                async with self._lock:
                    self._contexts.append(context)
            else:
                await context.close()

        except Exception as e:
            logger.warning(f"Ошибка при освобождении страницы: {e}")

    def get_stats(self) -> dict[str, Any]:
        """Получает статистику использования пула.

        Returns:
            Словарь со статистикой
        """
        return {
            "browsers_in_pool": len(self._browsers),
            "contexts_available": len(self._contexts),
            "pages_reused": self._browser_stats["reused"],
            "pages_created": self._browser_stats["created"],
            "reuse_ratio": (
                self._browser_stats["reused"]
                / (self._browser_stats["reused"] + self._browser_stats["created"])
                if (self._browser_stats["reused"] + self._browser_stats["created"]) > 0
                else 0
            ),
        }

    async def shutdown(self) -> None:
        """Закрывает все браузеры и освобождает ресурсы."""
        async with self._lock:
            logger.info("Закрытие пула браузеров...")

            # Закрываем контексты
            for context in self._contexts:
                try:
                    await context.close()
                except Exception as e:
                    logger.warning(f"Ошибка закрытия контекста: {e}")

            # Закрываем браузеры
            for browser in self._browsers:
                try:
                    await browser.close()
                except Exception as e:
                    logger.warning(f"Ошибка закрытия браузера: {e}")

            # Закрываем playwright
            if self._playwright:
                try:
                    await self._playwright.stop()
                except Exception as e:
                    logger.warning(f"Ошибка закрытия playwright: {e}")

            self._contexts.clear()
            self._browsers.clear()
            self._warm_pool_ready.clear()

            stats = self.get_stats()
            logger.info(f"Пул браузеров закрыт. Итоговая статистика: {stats}")


# Глобальный пул для переиспользования
_browser_pool: BrowserPool | None = None


async def get_browser_pool() -> BrowserPool:
    """Получает глобальный пул браузеров, создавая его при необходимости.

    Returns:
        Инициализированный BrowserPool
    """
    global _browser_pool
    if _browser_pool is None:
        _browser_pool = BrowserPool()
        await _browser_pool.initialize()
    return _browser_pool


async def shutdown_browser_pool() -> None:
    """Закрывает глобальный пул браузеров."""
    global _browser_pool
    if _browser_pool:
        await _browser_pool.shutdown()
        _browser_pool = None
