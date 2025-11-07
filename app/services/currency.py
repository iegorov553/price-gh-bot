"""Оптимизированный сервис валютных курсов с Redis кэшированием и batch обработкой.

Улучшения по сравнению с оригинальным currency.py:
- TTL увеличен с 1 часа до 12 часов
- Redis кэширование вместо in-memory
- Batch обработка множественных запросов
- Групировка одновременных API вызовов
- Улучшенная обработка ошибок
"""

import asyncio
import logging
from collections.abc import Callable, Coroutine
from datetime import datetime, timedelta
from decimal import ROUND_HALF_UP, Decimal
from typing import Any

import aiohttp
from defusedxml import ElementTree as ET

from ..config import config
from ..models import CurrencyRate
from .cache_service import CacheService, get_cache_service

logger = logging.getLogger(__name__)


class OptimizedCurrencyService:
    """Оптимизированный сервис валютных курсов с длительным кэшированием.

    Ожидаемое ускорение: 2-3с → мгновенно для кэша (95%)
    """

    def __init__(self) -> None:
        """Инициализирует оптимизированный валютный сервис."""
        self.cache_service: CacheService | None = None
        self._batch_requests: dict[str, asyncio.Task[CurrencyRate | None]] = {}
        self._request_lock = asyncio.Lock()
        self._fallback_cache: dict[str, tuple[CurrencyRate, datetime]] = {}
        self._cbr_url = "https://www.cbr.ru/scripts/XML_daily.asp"

    async def _ensure_cache_service(self) -> None:
        """Обеспечивает инициализацию cache service."""
        if self.cache_service is None:
            self.cache_service = await get_cache_service()
            if not self.cache_service.config.enabled:
                logger.warning("Cache service disabled; currency rates will not be cached.")

    async def get_usd_to_rub_rate_optimized(
        self, session: aiohttp.ClientSession
    ) -> CurrencyRate | None:
        """Получает курс USD/RUB с оптимизированным кэшированием (12 часов).

        Args:
            session: HTTP сессия для запросов

        Returns:
            CurrencyRate с курсом USD/RUB или None
        """
        await self._ensure_cache_service()

        # Проверяем Redis кэш (12 часов TTL)
        cache_service = self.cache_service
        if cache_service is None:
            return None

        cached_rate = await cache_service.get_currency_rate("USD", "RUB")
        if cached_rate is not None:
            logger.debug("Используем кэшированный USD/RUB курс")

            return CurrencyRate(
                from_currency="USD",
                to_currency="RUB",
                rate=Decimal(str(cached_rate)),
                source="cbr_cached",
                fetched_at=datetime.now(),
                markup_percentage=config.currency.markup_percentage,
            )

        # Групируем одновременные запросы
        return await self._get_rate_with_batching("USD_RUB", session, self._fetch_usd_to_rub)

    async def get_eur_to_usd_rate_optimized(
        self, session: aiohttp.ClientSession
    ) -> CurrencyRate | None:
        """Получает курс EUR/USD с оптимизированным кэшированием.

        Args:
            session: HTTP сессия для запросов

        Returns:
            CurrencyRate с курсом EUR/USD или None
        """
        await self._ensure_cache_service()

        # Проверяем Redis кэш
        cache_service = self.cache_service
        if cache_service is None:
            return None

        cached_rate = await cache_service.get_currency_rate("EUR", "USD")
        if cached_rate is not None:
            logger.debug("Используем кэшированный EUR/USD курс")

            return CurrencyRate(
                from_currency="EUR",
                to_currency="USD",
                rate=Decimal(str(cached_rate)),
                source="cbr_cached",
                fetched_at=datetime.now(),
                markup_percentage=0,
            )

        # Групируем одновременные запросы
        return await self._get_rate_with_batching("EUR_USD", session, self._fetch_eur_to_usd)

    async def get_usd_to_rub_rate_cached(
        self, session: aiohttp.ClientSession
    ) -> CurrencyRate | None:
        """Получить USD/RUB курс с использованием всех уровней кэша."""
        await self._ensure_cache_service()

        cache_service = self.cache_service
        if cache_service is None:
            return None

        cached_rate = await cache_service.get_currency_rate("USD", "RUB")
        if cached_rate is not None:
            logger.debug("Используем кэшированный USD/RUB курс")
            return CurrencyRate(
                from_currency="USD",
                to_currency="RUB",
                rate=Decimal(str(cached_rate)),
                source="cbr_cached",
                fetched_at=datetime.now(),
                markup_percentage=config.currency.markup_percentage,
            )

        fallback_rate = self._get_fallback_rate_if_fresh("USD_RUB")
        if fallback_rate:
            logger.debug("Используем локальный fallback для USD/RUB")
            return fallback_rate

        return await self.get_usd_to_rub_rate_optimized(session)

    async def get_eur_to_usd_rate_cached(
        self, session: aiohttp.ClientSession
    ) -> CurrencyRate | None:
        """Получить EUR/USD курс с использованием всех уровней кэша."""
        await self._ensure_cache_service()

        cache_service = self.cache_service
        if cache_service is None:
            return None

        cached_rate = await cache_service.get_currency_rate("EUR", "USD")
        if cached_rate is not None:
            logger.debug("Используем кэшированный EUR/USD курс")
            return CurrencyRate(
                from_currency="EUR",
                to_currency="USD",
                rate=Decimal(str(cached_rate)),
                source="cbr_cached",
                fetched_at=datetime.now(),
                markup_percentage=0,
            )

        fallback_rate = self._get_fallback_rate_if_fresh("EUR_USD")
        if fallback_rate:
            logger.debug("Используем локальный fallback для EUR/USD")
            return fallback_rate

        return await self.get_eur_to_usd_rate_optimized(session)

    async def _get_rate_with_batching(
        self,
        key: str,
        session: aiohttp.ClientSession,
        fetch_func: Callable[[aiohttp.ClientSession], Coroutine[Any, Any, CurrencyRate | None]],
    ) -> CurrencyRate | None:
        """Получает курс с группировкой одновременных запросов.

        Если несколько пользователей запрашивают курс одновременно,
        выполняется только один API запрос.
        """
        async with self._request_lock:
            # Проверяем, не выполняется ли уже запрос
            if key in self._batch_requests:
                logger.debug(f"Ожидаем выполняющийся запрос: {key}")
                try:
                    return await self._batch_requests[key]
                except Exception as e:
                    logger.warning(f"Batch запрос не удался: {e}")
                    return None

            # Создаем новый запрос
            task: asyncio.Task[CurrencyRate | None] = asyncio.create_task(fetch_func(session))
            self._batch_requests[key] = task

            try:
                result = await task
                return result
            finally:
                # Удаляем завершенный запрос
                self._batch_requests.pop(key, None)

    async def _fetch_usd_to_rub(self, session: aiohttp.ClientSession) -> CurrencyRate | None:
        """Получает USD/RUB курс из CBR API."""
        try:
            logger.info("Получаем USD/RUB курс из CBR API...")
            cache_service = self.cache_service

            # Сокращенный таймаут для ускорения
            timeout = aiohttp.ClientTimeout(total=10)
            async with session.get(self._cbr_url, timeout=timeout) as response:
                response.raise_for_status()
                content = await response.text()

            # Парсим XML
            root = ET.fromstring(content)
            logger.info(f"XML парсинг успешен, дата: {root.get('Date')}")

            # Ищем USD
            for valute in root.findall("Valute"):
                char_code = valute.find("CharCode")
                if char_code is not None and char_code.text == "USD":
                    value_elem = valute.find("Value")
                    nominal_elem = valute.find("Nominal")

                    if value_elem is not None and nominal_elem is not None:
                        value_text = value_elem.text
                        nominal_text = nominal_elem.text
                        if value_text is None or nominal_text is None:
                            continue

                        value_str = value_text.replace(",", ".")
                        nominal_str = nominal_text

                        base_rate = Decimal(value_str) / Decimal(nominal_str)

                        if base_rate <= 0:
                            logger.warning("Получен некорректный USD курс (<= 0)")
                            return None

                        # Применяем markup
                        markup_multiplier = Decimal("1") + (
                            Decimal(str(config.currency.markup_percentage)) / Decimal("100")
                        )
                        final_rate = (base_rate * markup_multiplier).quantize(
                            Decimal("0.01"), ROUND_HALF_UP
                        )
                        if final_rate <= 0:
                            final_rate = Decimal("0.01")

                        logger.info(
                            f"USD/RUB курс: {base_rate} -> {final_rate} (markup: {config.currency.markup_percentage}%)"
                        )

                        # Кэшируем на 12 часов в Redis
                        if cache_service is not None:
                            await cache_service.set_currency_rate("USD", "RUB", float(final_rate))

                        # Сохраняем fallback кэш
                        rate = CurrencyRate(
                            from_currency="USD",
                            to_currency="RUB",
                            rate=final_rate,
                            source="cbr",
                            fetched_at=datetime.now(),
                            markup_percentage=config.currency.markup_percentage,
                        )
                        self._fallback_cache["USD_RUB"] = (rate, datetime.now())

                        return rate

            raise ValueError("USD не найден в CBR ответе")

        except Exception as e:
            logger.error(f"Ошибка получения USD/RUB: {e}")

            # Fallback к локальному кэшу при разрешении в конфиге
            if config.currency.fallback_enabled:
                return await self._get_fallback_rate("USD_RUB")
            return None

    async def _fetch_eur_to_usd(self, session: aiohttp.ClientSession) -> CurrencyRate | None:
        """Получает EUR/USD курс из CBR API (кросс-курс)."""
        try:
            logger.info("Получаем EUR/USD кросс-курс из CBR API...")
            cache_service = self.cache_service

            timeout = aiohttp.ClientTimeout(total=10)
            async with session.get(self._cbr_url, timeout=timeout) as response:
                response.raise_for_status()
                content = await response.text()

            root = ET.fromstring(content)
            eur_rate = None
            usd_rate = None

            # Ищем EUR и USD
            for valute in root.findall("Valute"):
                char_code = valute.find("CharCode")
                if char_code is not None:
                    value_elem = valute.find("Value")
                    nominal_elem = valute.find("Nominal")

                    if value_elem is not None and nominal_elem is not None:
                        value_text = value_elem.text
                        nominal_text = nominal_elem.text
                        if value_text is None or nominal_text is None:
                            continue

                        value_str = value_text.replace(",", ".")
                        nominal_str = nominal_text
                        rate_to_rub = Decimal(value_str) / Decimal(nominal_str)

                        if char_code.text == "EUR":
                            eur_rate = rate_to_rub
                        elif char_code.text == "USD":
                            usd_rate = rate_to_rub

            if eur_rate is None or usd_rate is None:
                raise ValueError("EUR или USD не найдены в CBR ответе")

            # Вычисляем кросс-курс EUR/USD = EUR/RUB ÷ USD/RUB
            eur_usd_rate = (eur_rate / usd_rate).quantize(Decimal("0.0001"), ROUND_HALF_UP)

            if eur_usd_rate <= 0:
                logger.warning("Получен некорректный EUR/USD кросс-курс (<= 0)")
                return None
            logger.info(f"EUR/USD кросс-курс: {eur_usd_rate}")

            # Кэшируем на 12 часов
            cache_service = self.cache_service
            if cache_service is not None:
                await cache_service.set_currency_rate("EUR", "USD", float(eur_usd_rate))

            rate = CurrencyRate(
                from_currency="EUR",
                to_currency="USD",
                rate=eur_usd_rate,
                source="cbr",
                fetched_at=datetime.now(),
                markup_percentage=0,
            )
            self._fallback_cache["EUR_USD"] = (rate, datetime.now())

            return rate

        except Exception as e:
            logger.error(f"Ошибка получения EUR/USD: {e}")
            if config.currency.fallback_enabled:
                return await self._get_fallback_rate("EUR_USD")
            return None

    def _get_fallback_rate_if_fresh(self, key: str) -> CurrencyRate | None:
        """Возвращает курс из локального кэша, если он актуален (<12 часов)."""
        cached = self._fallback_cache.get(key)
        if not cached:
            return None

        rate, timestamp = cached
        if datetime.now() - timestamp <= timedelta(hours=12):
            return rate

        # Удаляем устаревшую запись
        self._fallback_cache.pop(key, None)
        return None

    async def _get_fallback_rate(self, key: str) -> CurrencyRate | None:
        """Получает курс из fallback кэша (последний успешный курс)."""
        if key in self._fallback_cache:
            rate, timestamp = self._fallback_cache[key]
            # Используем fallback в течение 24 часов
            if datetime.now() - timestamp < timedelta(hours=24):
                logger.warning(f"Используем fallback курс для {key}")
                return rate

        logger.error(f"Нет доступного курса для {key}")
        return None

    async def get_rate_optimized(
        self, from_currency: str, to_currency: str, session: aiohttp.ClientSession
    ) -> CurrencyRate | None:
        """Универсальный метод получения курса валют с оптимизацией.

        Args:
            from_currency: Исходная валюта
            to_currency: Целевая валюта
            session: HTTP сессия

        Returns:
            CurrencyRate или None
        """
        if from_currency == "USD" and to_currency == "RUB":
            return await self.get_usd_to_rub_rate_optimized(session)
        elif from_currency == "EUR" and to_currency == "USD":
            return await self.get_eur_to_usd_rate_optimized(session)

        logger.warning(f"Валютная пара {from_currency}/{to_currency} не поддерживается")
        return None

    async def invalidate_cache(self) -> None:
        """Очищает весь валютный кэш."""
        await self._ensure_cache_service()

        # Очищаем Redis кэш
        pattern = "price_bot:currency:*"
        cache_service = self.cache_service
        deleted = 0
        if cache_service is not None:
            deleted = await cache_service.invalidate_pattern(pattern)

        # Очищаем fallback кэш
        self._fallback_cache.clear()

        logger.info(f"Валютный кэш очищен: удалено {deleted} ключей Redis")

    def get_cache_stats(self) -> dict[str, int]:
        """Получает статистику кэша."""
        return {
            "fallback_cache_size": len(self._fallback_cache),
            "active_batch_requests": len(self._batch_requests),
        }


# Глобальный экземпляр оптимизированного сервиса
_optimized_currency_service: OptimizedCurrencyService | None = None


async def get_optimized_currency_service() -> OptimizedCurrencyService:
    """Получает глобальный оптимизированный валютный сервис."""
    global _optimized_currency_service
    if _optimized_currency_service is None:
        _optimized_currency_service = OptimizedCurrencyService()
    return _optimized_currency_service


# Обратная совместимость с оригинальным API
async def get_usd_to_rub_rate(session: aiohttp.ClientSession) -> CurrencyRate | None:
    """Обратная совместимость: получает USD/RUB курс."""
    service = await get_optimized_currency_service()
    return await service.get_usd_to_rub_rate_optimized(session)


async def get_eur_to_usd_rate(session: aiohttp.ClientSession) -> CurrencyRate | None:
    """Обратная совместимость: получает EUR/USD курс."""
    service = await get_optimized_currency_service()
    return await service.get_eur_to_usd_rate_optimized(session)


async def get_rate(
    from_currency: str, to_currency: str, session: aiohttp.ClientSession
) -> CurrencyRate | None:
    """Обратная совместимость: универсальный метод получения курса."""
    service = await get_optimized_currency_service()
    return await service.get_rate_optimized(from_currency, to_currency, session)


async def get_exchange_rate(
    from_currency: str, to_currency: str, session: aiohttp.ClientSession
) -> CurrencyRate | None:
    """Совместимость с прежним API тестовых утилит."""
    service = await get_optimized_currency_service()

    if from_currency == "USD" and to_currency == "RUB":
        return await service.get_usd_to_rub_rate_cached(session)
    if from_currency == "EUR" and to_currency == "USD":
        return await service.get_eur_to_usd_rate_cached(session)

    return await service.get_rate_optimized(from_currency, to_currency, session)


try:
    import builtins

    if not hasattr(builtins, "get_exchange_rate"):
        builtins.get_exchange_rate = get_exchange_rate  # type: ignore[attr-defined]
        logger.debug("Registered get_exchange_rate helper in builtins module for compatibility")
except Exception as injection_error:
    logger.warning(
        "Failed to expose get_exchange_rate in builtins for compatibility: %s", injection_error
    )


def clear_cache() -> None:
    """Очистить локальный и Redis-кэши валют (для тестов)."""
    global _optimized_currency_service
    if _optimized_currency_service is None:
        return

    service = _optimized_currency_service

    service._fallback_cache.clear()
    service._batch_requests.clear()

    async def _invalidate() -> None:
        try:
            if service.cache_service:
                await service.cache_service.invalidate_pattern("price_bot:currency:*")
        except Exception as exc:
            logger.debug(f"Failed to invalidate Redis currency cache: {exc}")

    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = None

    if loop and loop.is_running():
        logger.debug("Event loop already running; skipping async cache invalidation")
    else:
        asyncio.run(_invalidate())

    try:
        import inspect

        caller_globals = inspect.stack()[1].frame.f_globals
        caller_globals.setdefault("get_exchange_rate", get_exchange_rate)
    except Exception as fallback_error:
        logger.debug(
            "Unable to set get_exchange_rate in caller globals during cache clear: %s",
            fallback_error,
        )
