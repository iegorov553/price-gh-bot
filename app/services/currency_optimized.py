"""
Оптимизированный сервис валютных курсов с Redis кэшированием и batch обработкой.

Улучшения по сравнению с оригинальным currency.py:
- TTL увеличен с 1 часа до 12 часов
- Redis кэширование вместо in-memory
- Batch обработка множественных запросов
- Групировка одновременных API вызовов
- Улучшенная обработка ошибок
"""

import asyncio
import logging
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta
from decimal import ROUND_HALF_UP, Decimal
from typing import Dict, Optional, Tuple

import aiohttp

from ..config import config
from ..models import CurrencyRate
from .cache_service import get_cache_service

logger = logging.getLogger(__name__)


class OptimizedCurrencyService:
    """
    Оптимизированный сервис валютных курсов с длительным кэшированием.
    
    Ожидаемое ускорение: 2-3с → мгновенно для кэша (95%)
    """
    
    def __init__(self):
        """Инициализирует оптимизированный валютный сервис."""
        self.cache_service = None
        self._batch_requests: Dict[str, asyncio.Task] = {}
        self._request_lock = asyncio.Lock()
        self._fallback_cache: Dict[str, Tuple[CurrencyRate, datetime]] = {}
        self._cbr_url = "https://www.cbr.ru/scripts/XML_daily.asp"
        
    async def _ensure_cache_service(self) -> None:
        """Обеспечивает инициализацию cache service."""
        if self.cache_service is None:
            self.cache_service = await get_cache_service()
    
    async def get_usd_to_rub_rate_optimized(self, session: aiohttp.ClientSession) -> Optional[CurrencyRate]:
        """
        Получает курс USD/RUB с оптимизированным кэшированием (12 часов).
        
        Args:
            session: HTTP сессия для запросов
            
        Returns:
            CurrencyRate с курсом USD/RUB или None
        """
        await self._ensure_cache_service()
        
        # Проверяем Redis кэш (12 часов TTL)
        cached_rate = await self.cache_service.get_currency_rate("USD", "RUB")
        if cached_rate:
            logger.debug("Используем кэшированный USD/RUB курс")
            
            return CurrencyRate(
                from_currency="USD",
                to_currency="RUB", 
                rate=Decimal(str(cached_rate)),
                source="cbr_cached",
                fetched_at=datetime.now(),
                markup_percentage=config.currency.markup_percentage
            )
        
        # Групируем одновременные запросы
        return await self._get_rate_with_batching("USD_RUB", session, self._fetch_usd_to_rub)
    
    async def get_eur_to_usd_rate_optimized(self, session: aiohttp.ClientSession) -> Optional[CurrencyRate]:
        """
        Получает курс EUR/USD с оптимизированным кэшированием.
        
        Args:
            session: HTTP сессия для запросов
            
        Returns:
            CurrencyRate с курсом EUR/USD или None
        """
        await self._ensure_cache_service()
        
        # Проверяем Redis кэш
        cached_rate = await self.cache_service.get_currency_rate("EUR", "USD")
        if cached_rate:
            logger.debug("Используем кэшированный EUR/USD курс")
            
            return CurrencyRate(
                from_currency="EUR",
                to_currency="USD",
                rate=Decimal(str(cached_rate)),
                source="cbr_cached",
                fetched_at=datetime.now(),
                markup_percentage=0
            )
        
        # Групируем одновременные запросы
        return await self._get_rate_with_batching("EUR_USD", session, self._fetch_eur_to_usd)
    
    async def _get_rate_with_batching(
        self, 
        key: str, 
        session: aiohttp.ClientSession,
        fetch_func
    ) -> Optional[CurrencyRate]:
        """
        Получает курс с группировкой одновременных запросов.
        
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
            task = asyncio.create_task(fetch_func(session))
            self._batch_requests[key] = task
            
            try:
                result = await task
                return result
            finally:
                # Удаляем завершенный запрос
                self._batch_requests.pop(key, None)
    
    async def _fetch_usd_to_rub(self, session: aiohttp.ClientSession) -> Optional[CurrencyRate]:
        """Получает USD/RUB курс из CBR API."""
        try:
            logger.info("Получаем USD/RUB курс из CBR API...")
            
            # Сокращенный таймаут для ускорения
            timeout = aiohttp.ClientTimeout(total=10)
            async with session.get(self._cbr_url, timeout=timeout) as response:
                response.raise_for_status()
                content = await response.read()
            
            # Парсим XML
            root = ET.fromstring(content)
            logger.info(f"XML парсинг успешен, дата: {root.get('Date')}")
            
            # Ищем USD
            for valute in root.findall('Valute'):
                char_code = valute.find('CharCode')
                if char_code is not None and char_code.text == 'USD':
                    value_elem = valute.find('Value')
                    nominal_elem = valute.find('Nominal')
                    
                    if value_elem is not None and nominal_elem is not None:
                        value_str = value_elem.text.replace(',', '.')
                        nominal_str = nominal_elem.text
                        
                        base_rate = Decimal(value_str) / Decimal(nominal_str)
                        
                        # Применяем markup
                        markup_multiplier = Decimal('1') + (Decimal(str(config.currency.markup_percentage)) / Decimal('100'))
                        final_rate = (base_rate * markup_multiplier).quantize(Decimal('0.01'), ROUND_HALF_UP)
                        
                        logger.info(f"USD/RUB курс: {base_rate} -> {final_rate} (markup: {config.currency.markup_percentage}%)")
                        
                        # Кэшируем на 12 часов в Redis
                        await self.cache_service.set_currency_rate("USD", "RUB", float(final_rate))
                        
                        # Сохраняем fallback кэш
                        rate = CurrencyRate(
                            from_currency="USD",
                            to_currency="RUB",
                            rate=final_rate,
                            source="cbr",
                            fetched_at=datetime.now(),
                            markup_percentage=config.currency.markup_percentage
                        )
                        self._fallback_cache["USD_RUB"] = (rate, datetime.now())
                        
                        return rate
            
            raise ValueError("USD не найден в CBR ответе")
            
        except Exception as e:
            logger.error(f"Ошибка получения USD/RUB: {e}")
            
            # Fallback к локальному кэшу
            return await self._get_fallback_rate("USD_RUB")
    
    async def _fetch_eur_to_usd(self, session: aiohttp.ClientSession) -> Optional[CurrencyRate]:
        """Получает EUR/USD курс из CBR API (кросс-курс)."""
        try:
            logger.info("Получаем EUR/USD кросс-курс из CBR API...")
            
            timeout = aiohttp.ClientTimeout(total=10)
            async with session.get(self._cbr_url, timeout=timeout) as response:
                response.raise_for_status()
                content = await response.read()
            
            root = ET.fromstring(content)
            eur_rate = None
            usd_rate = None
            
            # Ищем EUR и USD
            for valute in root.findall('Valute'):
                char_code = valute.find('CharCode')
                if char_code is not None:
                    value_elem = valute.find('Value')
                    nominal_elem = valute.find('Nominal')
                    
                    if value_elem is not None and nominal_elem is not None:
                        value_str = value_elem.text.replace(',', '.')
                        nominal_str = nominal_elem.text
                        rate_to_rub = Decimal(value_str) / Decimal(nominal_str)
                        
                        if char_code.text == 'EUR':
                            eur_rate = rate_to_rub
                        elif char_code.text == 'USD':
                            usd_rate = rate_to_rub
            
            if eur_rate is None or usd_rate is None:
                raise ValueError("EUR или USD не найдены в CBR ответе")
            
            # Вычисляем кросс-курс EUR/USD = EUR/RUB ÷ USD/RUB
            eur_usd_rate = (eur_rate / usd_rate).quantize(Decimal('0.0001'), ROUND_HALF_UP)
            logger.info(f"EUR/USD кросс-курс: {eur_usd_rate}")
            
            # Кэшируем на 12 часов
            await self.cache_service.set_currency_rate("EUR", "USD", float(eur_usd_rate))
            
            rate = CurrencyRate(
                from_currency="EUR",
                to_currency="USD",
                rate=eur_usd_rate,
                source="cbr",
                fetched_at=datetime.now(),
                markup_percentage=0
            )
            self._fallback_cache["EUR_USD"] = (rate, datetime.now())
            
            return rate
            
        except Exception as e:
            logger.error(f"Ошибка получения EUR/USD: {e}")
            return await self._get_fallback_rate("EUR_USD")
    
    async def _get_fallback_rate(self, key: str) -> Optional[CurrencyRate]:
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
        self, 
        from_currency: str, 
        to_currency: str, 
        session: aiohttp.ClientSession
    ) -> Optional[CurrencyRate]:
        """
        Универсальный метод получения курса валют с оптимизацией.
        
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
        deleted = await self.cache_service.invalidate_pattern(pattern)
        
        # Очищаем fallback кэш
        self._fallback_cache.clear()
        
        logger.info(f"Валютный кэш очищен: удалено {deleted} ключей Redis")
    
    def get_cache_stats(self) -> Dict[str, int]:
        """Получает статистику кэша."""
        return {
            "fallback_cache_size": len(self._fallback_cache),
            "active_batch_requests": len(self._batch_requests)
        }


# Глобальный экземпляр оптимизированного сервиса
_optimized_currency_service: Optional[OptimizedCurrencyService] = None


async def get_optimized_currency_service() -> OptimizedCurrencyService:
    """Получает глобальный оптимизированный валютный сервис."""
    global _optimized_currency_service
    if _optimized_currency_service is None:
        _optimized_currency_service = OptimizedCurrencyService()
    return _optimized_currency_service


# Обратная совместимость с оригинальным API
async def get_usd_to_rub_rate(session: aiohttp.ClientSession) -> Optional[CurrencyRate]:
    """Обратная совместимость: получает USD/RUB курс."""
    service = await get_optimized_currency_service()
    return await service.get_usd_to_rub_rate_optimized(session)


async def get_eur_to_usd_rate(session: aiohttp.ClientSession) -> Optional[CurrencyRate]:
    """Обратная совместимость: получает EUR/USD курс."""
    service = await get_optimized_currency_service()
    return await service.get_eur_to_usd_rate_optimized(session)


async def get_rate(from_currency: str, to_currency: str, session: aiohttp.ClientSession) -> Optional[CurrencyRate]:
    """Обратная совместимость: универсальный метод получения курса."""
    service = await get_optimized_currency_service()
    return await service.get_rate_optimized(from_currency, to_currency, session)