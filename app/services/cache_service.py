"""Сервис кэширования для результатов скрапинга с Redis.

Этот модуль предоставляет высокопроизводительное кэширование для:
- Данных товаров (TTL 24 часа)
- Данных продавцов (TTL 12 часов)
- Валютных курсов (TTL 12 часов)
- Результатов анализа сайтов
"""

import hashlib
import json
import logging
from datetime import datetime
from typing import TYPE_CHECKING, Any, cast

from pydantic import BaseModel, Field

from ..models import ItemData, SellerAdvisory, SellerData

logger = logging.getLogger(__name__)

try:
    import redis.asyncio as redis
except ImportError:
    redis = cast(Any, None)

if TYPE_CHECKING:
    from redis.asyncio import Redis as AsyncRedis
else:
    AsyncRedis = Any

REDIS_AVAILABLE = redis is not None


class CacheConfig(BaseModel):
    """Конфигурация Redis кэша."""

    redis_url: str = Field(default="redis://localhost:6379", description="URL Redis сервера")
    item_data_ttl: int = Field(default=86400, description="TTL для данных товаров (24 часа)")
    seller_data_ttl: int = Field(default=43200, description="TTL для данных продавцов (12 часов)")
    currency_ttl: int = Field(default=43200, description="TTL для валютных курсов (12 часов)")
    max_retries: int = Field(default=3, description="Максимальное количество повторных попыток")
    enabled: bool = Field(default=True, description="Включить/выключить кэширование")


class CacheService:
    """Высокопроизводительный сервис кэширования с Redis.

    Обеспечивает мгновенные ответы для повторных запросов,
    сокращая время обработки с 8-10 секунд до <1 секунды.
    """

    def __init__(self, config: CacheConfig):
        """Инициализирует сервис кэширования.

        Args:
            config: Конфигурация Redis соединения
        """
        self.config = config
        self._redis: AsyncRedis | None = None
        self._connected = False

        if not REDIS_AVAILABLE:
            logger.warning("Redis недоступен, кэширование отключено")
            self.config.enabled = False

    def _get_client(self) -> AsyncRedis | None:
        """Return active Redis client if connected."""
        if not self._connected or self._redis is None:
            return None
        return self._redis

    async def connect(self) -> bool:
        """Подключается к Redis серверу.

        Returns:
            True если подключение успешно, False иначе
        """
        if not self.config.enabled or not REDIS_AVAILABLE:
            return False

        try:
            client = redis.from_url(
                self.config.redis_url,
                decode_responses=True,
                retry_on_timeout=True,
                health_check_interval=30,
                socket_connect_timeout=5,
                socket_timeout=5,
            )

            # Проверяем соединение
            async_client = cast(AsyncRedis, client)
            await async_client.ping()
            self._redis = async_client
            self._connected = True
            logger.info("Подключение к Redis успешно")
            return True

        except Exception as e:
            logger.warning(f"Не удалось подключиться к Redis: {e}")
            self._connected = False
            return False

    def _generate_key(self, prefix: str, identifier: str) -> str:
        """Генерирует уникальный ключ кэша с хэшированием.

        Args:
            prefix: Префикс ключа (item, seller, currency)
            identifier: Уникальный идентификатор (URL, валютная пара)

        Returns:
            Хэшированный ключ кэша
        """
        # Нормализуем URL и создаем хэш
        normalized = identifier.lower().strip()
        hash_obj = hashlib.sha256(normalized.encode("utf-8"))
        return f"price_bot:{prefix}:{hash_obj.hexdigest()}"

    async def get_item_data(self, url: str) -> dict[str, Any] | None:
        """Получает кэшированные данные товара.

        Args:
            url: URL товара

        Returns:
            Словарь с данными товара или None
        """
        client = self._get_client()
        if client is None:
            return None

        try:
            key = self._generate_key("item", url)
            cached = await client.get(key)

            if cached:
                payload = cast(dict[str, Any], json.loads(cached))
                data = self._deserialize_scraping_result(payload)
                logger.debug(f"Кэш попадание для товара: {url}")
                return data
            else:
                logger.debug(f"Кэш промах для товара: {url}")
                return None

        except Exception as e:
            logger.warning(f"Ошибка получения кэша товара: {e}")
            return None

    async def set_item_data(self, url: str, data: dict[str, Any]) -> bool:
        """Кэширует данные товара на 24 часа.

        Args:
            url: URL товара
            data: Данные товара для кэширования

        Returns:
            True если кэширование успешно
        """
        client = self._get_client()
        if client is None:
            return False

        try:
            key = self._generate_key("item", url)

            # Добавляем метаданные кэша
            cache_data = self._serialize_scraping_result(data)
            cache_data["_cached_at"] = datetime.now().isoformat()
            cache_data["_cache_ttl"] = self.config.item_data_ttl

            await client.setex(
                key,
                self.config.item_data_ttl,
                json.dumps(cache_data, default=str, ensure_ascii=False),
            )

            logger.debug(f"Товар закэширован: {url}")
            return True

        except Exception as e:
            logger.warning(f"Ошибка кэширования товара: {e}")
            return False

    async def get_seller_data(self, seller_url: str) -> dict[str, Any] | None:
        """Получает кэшированные данные продавца.

        Args:
            seller_url: URL профиля продавца

        Returns:
            Словарь с данными продавца или None
        """
        client = self._get_client()
        if client is None:
            return None

        try:
            key = self._generate_key("seller", seller_url)
            cached = await client.get(key)

            if cached:
                payload = cast(dict[str, Any], json.loads(cached))
                data = self._deserialize_scraping_result(payload)
                logger.debug(f"Кэш попадание для продавца: {seller_url}")
                return data
            else:
                logger.debug(f"Кэш промах для продавца: {seller_url}")
                return None

        except Exception as e:
            logger.warning(f"Ошибка получения кэша продавца: {e}")
            return None

    async def set_seller_data(self, seller_url: str, data: dict[str, Any]) -> bool:
        """Кэширует данные продавца на 12 часов.

        Args:
            seller_url: URL профиля продавца
            data: Данные продавца для кэширования

        Returns:
            True если кэширование успешно
        """
        client = self._get_client()
        if client is None:
            return False

        try:
            key = self._generate_key("seller", seller_url)

            # Добавляем метаданные кэша
            cache_data = self._serialize_scraping_result(data)
            cache_data["_cached_at"] = datetime.now().isoformat()
            cache_data["_cache_ttl"] = self.config.seller_data_ttl

            await client.setex(
                key,
                self.config.seller_data_ttl,
                json.dumps(cache_data, default=str, ensure_ascii=False),
            )

            logger.debug(f"Продавец закэширован: {seller_url}")
            return True

        except Exception as e:
            logger.warning(f"Ошибка кэширования продавца: {e}")
            return False

    async def get_currency_rate(self, from_currency: str, to_currency: str) -> float | None:
        """Получает кэшированный курс валют.

        Args:
            from_currency: Исходная валюта
            to_currency: Целевая валюта

        Returns:
            Курс валют или None
        """
        client = self._get_client()
        if client is None:
            return None

        try:
            key = self._generate_key("currency", f"{from_currency}_{to_currency}")
            cached = await client.get(key)

            if cached:
                rate = float(cached)
                logger.debug(f"Кэш попадание для курса {from_currency}/{to_currency}: {rate}")
                return rate
            else:
                logger.debug(f"Кэш промах для курса {from_currency}/{to_currency}")
                return None

        except Exception as e:
            logger.warning(f"Ошибка получения кэша валют: {e}")
            return None

    async def set_currency_rate(self, from_currency: str, to_currency: str, rate: float) -> bool:
        """Кэширует курс валют на 12 часов.

        Args:
            from_currency: Исходная валюта
            to_currency: Целевая валюта
            rate: Курс валют

        Returns:
            True если кэширование успешно
        """
        client = self._get_client()
        if client is None:
            return False

        try:
            key = self._generate_key("currency", f"{from_currency}_{to_currency}")

            await client.setex(key, self.config.currency_ttl, str(rate))

            logger.debug(f"Курс валют закэширован {from_currency}/{to_currency}: {rate}")
            return True

        except Exception as e:
            logger.warning(f"Ошибка кэширования курса валют: {e}")
            return False

    async def invalidate_pattern(self, pattern: str) -> int:
        """Удаляет ключи по паттерну.

        Args:
            pattern: Паттерн для поиска ключей (например, "price_bot:item:*")

        Returns:
            Количество удаленных ключей
        """
        client = self._get_client()
        if client is None:
            return 0

        try:
            keys = cast(list[str], await client.keys(pattern))
            if keys:
                deleted_raw = await client.delete(*keys)
                deleted = int(deleted_raw)
                logger.info(f"Удалено {deleted} ключей по паттерну: {pattern}")
                return deleted
            return 0

        except Exception as e:
            logger.warning(f"Ошибка удаления по паттерну: {e}")
            return 0

    async def get_stats(self) -> dict[str, Any]:
        """Получает статистику кэша.

        Returns:
            Словарь со статистикой Redis
        """
        client = self._get_client()
        if client is None:
            return {"connected": False, "enabled": self.config.enabled}

        try:
            info = await client.info()
            return {
                "connected": True,
                "enabled": self.config.enabled,
                "used_memory": info.get("used_memory_human", "N/A"),
                "connected_clients": info.get("connected_clients", 0),
                "total_commands_processed": info.get("total_commands_processed", 0),
                "keyspace_hits": info.get("keyspace_hits", 0),
                "keyspace_misses": info.get("keyspace_misses", 0),
                "hit_rate": (
                    info.get("keyspace_hits", 0)
                    / max(1, info.get("keyspace_hits", 0) + info.get("keyspace_misses", 0))
                ),
            }

        except Exception as e:
            logger.warning(f"Ошибка получения статистики Redis: {e}")
            return {"connected": False, "enabled": self.config.enabled, "error": str(e)}

    async def close(self) -> None:
        """Закрывает соединение с Redis."""
        client = self._get_client()
        if client:
            try:
                await client.close()
                logger.info("Соединение с Redis закрыто")
            except Exception as e:
                logger.warning(f"Ошибка закрытия Redis: {e}")
            finally:
                self._connected = False
                self._redis = None

    @staticmethod
    def _serialize_scraping_result(data: dict[str, Any]) -> dict[str, Any]:
        """Подготавливает результат скрапинга к сериализации в JSON."""
        serialized: dict[str, Any] = {}
        for key, value in data.items():
            if hasattr(value, "model_dump"):
                serialized[key] = value.model_dump(mode="json")
            else:
                serialized[key] = value
        return serialized

    @staticmethod
    def _deserialize_scraping_result(data: dict[str, Any]) -> dict[str, Any]:
        """Восстанавливает Pydantic-модели из JSON данных кэша."""
        restored = dict(data)

        item_payload = restored.get("item_data")
        if isinstance(item_payload, dict):
            restored["item_data"] = ItemData(**item_payload)

        seller_payload = restored.get("seller_data")
        if isinstance(seller_payload, dict):
            restored["seller_data"] = SellerData(**seller_payload)

        advisory_payload = restored.get("seller_advisory")
        if isinstance(advisory_payload, dict):
            restored["seller_advisory"] = SellerAdvisory(**advisory_payload)

        # Обратная совместимость с кэшем старого формата
        reliability_payload = restored.get("reliability_score")
        if isinstance(reliability_payload, dict) and "message" in reliability_payload:
            restored["seller_advisory"] = SellerAdvisory(**reliability_payload)

        return restored


# Глобальный экземпляр сервиса кэширования
_cache_service: CacheService | None = None


async def get_cache_service() -> CacheService:
    """Получает глобальный сервис кэширования.

    Returns:
        Инициализированный CacheService
    """
    global _cache_service
    if _cache_service is None:
        config = CacheConfig()
        _cache_service = CacheService(config)
        await _cache_service.connect()
    return _cache_service


async def shutdown_cache_service() -> None:
    """Закрывает глобальный сервис кэширования."""
    global _cache_service
    if _cache_service:
        await _cache_service.close()
        _cache_service = None
