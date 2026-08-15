# Grailed Algolia Migration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Заменить текущий нестабильный механизм скрапинга листингов и продавцов Grailed (HTML/Playwright) на прямое получение структурированных данных через клиент поискового индекса Algolia.

**Architecture:** Выделенный сервис `GrailedAlgoliaClient` в `app/services/grailed_algolia.py`, настраиваемый через `GrailedAlgoliaConfig` в `app/config.py`. `GrailedScraper` в `app/scrapers/grailed_scraper.py` делегирует получение карточек товаров и профилей продавцов этому клиенту за единым интерфейсом `ScraperProtocol`, исключая медленные и блокируемые вызовы Playwright.

**Tech Stack:** Python 3.11, `aiohttp`, `pydantic` / `pydantic-settings`, `pytest`, `pytest-asyncio`.

## Global Constraints

- Сохранять совместимость с контрактом `ScraperProtocol` (`supports_url`, `scrape_item`, `scrape_seller`, `is_seller_profile`, `extract_seller_profile_url`).
- Не вносить изменений в логику расчетов комиссий, таможенных пошлин и скрапера eBay.
- Не сохранять секретные ключи в открытом коде без возможности переопределения через переменные окружения (`GRAILED_ALGOLIA_APP_ID`, `GRAILED_ALGOLIA_API_KEY`, `GRAILED_ALGOLIA_INDEX_NAME`).
- Применять TDD: сначала падающий тест, затем реализация, затем проверка и коммит.

---

### Task 1: Конфигурация Algolia в `app/config.py`

**Files:**
- Modify: `app/config.py`
- Modify: `.env.example`
- Test: `tests_new/unit/test_config.py`

**Interfaces:**
- Produces: `GrailedAlgoliaConfig` класс со свойствами `app_id: str`, `api_key: str`, `index_name: str`, `timeout_sec: float`, доступный через `config.algolia`.

- [ ] **Step 1: Написать падающий unit-тест для `GrailedAlgoliaConfig`**

Добавить в `tests_new/unit/test_config.py`:
```python
def test_grailed_algolia_config_defaults():
    from app.config import GrailedAlgoliaConfig
    
    cfg = GrailedAlgoliaConfig()
    assert cfg.app_id == "MNRWEFSS2Q"
    assert cfg.api_key == "c89dbaddf15fe70e1941a109bf7c2a3d"
    assert cfg.index_name == "Listing_production"
    assert cfg.timeout_sec == 5.0


def test_app_config_has_algolia_section():
    from app.config import config
    
    assert hasattr(config, "algolia")
    assert config.algolia.app_id == "MNRWEFSS2Q"
```

- [ ] **Step 2: Запустить тест и убедиться в падении**

Run: `pytest tests_new/unit/test_config.py -k "algolia" -v`  
Expected: FAIL (`ImportError` или `AttributeError`).

- [ ] **Step 3: Реализовать `GrailedAlgoliaConfig` в `app/config.py` и обновить `.env.example`**

В `app/config.py`:
```python
class GrailedAlgoliaConfig(BaseSettings):
    """Configuration for Grailed Algolia search client.

    Attributes:
        app_id: Algolia Application ID for Grailed.
        api_key: Algolia search-only API key.
        index_name: Name of the primary search index.
        timeout_sec: Network timeout for queries in seconds.
    """

    app_id: str = Field(default="MNRWEFSS2Q", validation_alias="GRAILED_ALGOLIA_APP_ID")
    api_key: str = Field(default="c89dbaddf15fe70e1941a109bf7c2a3d", validation_alias="GRAILED_ALGOLIA_API_KEY")
    index_name: str = Field(default="Listing_production", validation_alias="GRAILED_ALGOLIA_INDEX_NAME")
    timeout_sec: float = Field(default=5.0, validation_alias="GRAILED_ALGOLIA_TIMEOUT_SEC")
```
В `Config` класс добавить поле:
```python
algolia: GrailedAlgoliaConfig = Field(default_factory=GrailedAlgoliaConfig)
```

В `.env.example` добавить:
```env
# Grailed Algolia search configuration
GRAILED_ALGOLIA_APP_ID=MNRWEFSS2Q
GRAILED_ALGOLIA_API_KEY=c89dbaddf15fe70e1941a109bf7c2a3d
GRAILED_ALGOLIA_INDEX_NAME=Listing_production
GRAILED_ALGOLIA_TIMEOUT_SEC=5.0
```

- [ ] **Step 4: Запустить тесты и убедиться в прохождении**

Run: `pytest tests_new/unit/test_config.py -v`  
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add app/config.py .env.example tests_new/unit/test_config.py
git commit -m "feat(config): add GrailedAlgoliaConfig settings"
```

---

### Task 2: Реализация сервиса `GrailedAlgoliaClient`

**Files:**
- Create: `app/services/grailed_algolia.py`
- Test: `tests_new/unit/test_grailed_algolia_client.py`

**Interfaces:**
- Consumes: `app.config.config.algolia`, `app.models.ItemData`, `app.models.SellerData`.
- Produces:
  - `GrailedAlgoliaClient`:
    - `async def get_listing_by_id(self, listing_id: int | str, session: aiohttp.ClientSession) -> tuple[ItemData | None, SellerData | None]`
    - `async def get_seller_by_username(self, username: str, session: aiohttp.ClientSession) -> SellerData | None`
  - `grailed_algolia_client` (глобальный экземпляр).

- [ ] **Step 1: Написать модульные тесты для `GrailedAlgoliaClient`**

Создать `tests_new/unit/test_grailed_algolia_client.py`:
```python
import json
from decimal import Decimal
from unittest.mock import AsyncMock, patch

import pytest
import aiohttp

from app.models import ItemData, SellerData
from app.services.grailed_algolia import GrailedAlgoliaClient


SAMPLE_ACTIVE_HIT = {
    "id": 99406229,
    "title": "Vissla Board Shorts",
    "price": 34,
    "buynow": True,
    "makeoffer": True,
    "sold": False,
    "deleted": False,
    "shipping": {
        "us": {"amount": 9, "enabled": True}
    },
    "user": {
        "id": 13535449,
        "username": "EraLuxe",
        "seller_score": {"rating_average": 4.87, "rating_count": 118},
        "trusted_seller": True
    },
    "cover_photo": {
        "image_url": "https://media-assets.grailed.com/prd/listing/temp/sample.jpg"
    }
}

SAMPLE_OFFER_ONLY_HIT = {
    "id": 103179342,
    "title": "Nike Sweatpant",
    "price": 50,
    "buynow": False,
    "makeoffer": True,
    "sold": False,
    "deleted": False,
    "shipping": {
        "us": {"amount": 18.99, "enabled": True}
    },
    "user": {
        "id": 2204,
        "username": "secondlifeinc",
        "seller_score": {"rating_average": 4.85, "rating_count": 2204},
        "trusted_seller": False
    },
    "cover_photo": {
        "url": "https://media-assets.grailed.com/prd/listing/temp/sample2.jpg"
    }
}


@pytest.mark.asyncio
async def test_get_listing_by_id_success():
    client = GrailedAlgoliaClient()
    mock_resp_data = {"results": [{"hits": [SAMPLE_ACTIVE_HIT], "nbHits": 1}]}

    mock_session = AsyncMock(spec=aiohttp.ClientSession)
    mock_post_ctx = AsyncMock()
    mock_post_ctx.status = 200
    mock_post_ctx.json = AsyncMock(return_value=mock_resp_data)
    mock_session.post.return_value.__aenter__.return_value = mock_post_ctx

    item, seller = await client.get_listing_by_id(99406229, mock_session)

    assert item is not None
    assert item.title == "Vissla Board Shorts"
    assert item.price == Decimal("34")
    assert item.shipping_us == Decimal("9")
    assert item.is_buyable is True
    assert item.image_url == "https://media-assets.grailed.com/prd/listing/temp/sample.jpg"

    assert seller is not None
    assert seller.num_reviews == 118
    assert seller.avg_rating == 4.87
    assert seller.trusted_badge is True
    assert seller.technical_issue is False


@pytest.mark.asyncio
async def test_get_listing_by_id_offer_only():
    client = GrailedAlgoliaClient()
    mock_resp_data = {"results": [{"hits": [SAMPLE_OFFER_ONLY_HIT], "nbHits": 1}]}

    mock_session = AsyncMock(spec=aiohttp.ClientSession)
    mock_post_ctx = AsyncMock()
    mock_post_ctx.status = 200
    mock_post_ctx.json = AsyncMock(return_value=mock_resp_data)
    mock_session.post.return_value.__aenter__.return_value = mock_post_ctx

    item, seller = await client.get_listing_by_id("103179342", mock_session)

    assert item is not None
    assert item.is_buyable is False
    assert item.shipping_us == Decimal("18.99")
    assert item.image_url == "https://media-assets.grailed.com/prd/listing/temp/sample2.jpg"


@pytest.mark.asyncio
async def test_get_listing_by_id_not_found():
    client = GrailedAlgoliaClient()
    mock_resp_data = {"results": [{"hits": [], "nbHits": 0}]}

    mock_session = AsyncMock(spec=aiohttp.ClientSession)
    mock_post_ctx = AsyncMock()
    mock_post_ctx.status = 200
    mock_post_ctx.json = AsyncMock(return_value=mock_resp_data)
    mock_session.post.return_value.__aenter__.return_value = mock_post_ctx

    item, seller = await client.get_listing_by_id(99999999, mock_session)
    assert item is None
    assert seller is None


@pytest.mark.asyncio
async def test_get_listing_by_id_http_403_or_error():
    client = GrailedAlgoliaClient()
    mock_session = AsyncMock(spec=aiohttp.ClientSession)
    mock_post_ctx = AsyncMock()
    mock_post_ctx.status = 403
    mock_post_ctx.text = AsyncMock(return_value='{"message":"Invalid key"}')
    mock_session.post.return_value.__aenter__.return_value = mock_post_ctx

    item, seller = await client.get_listing_by_id(99406229, mock_session)
    assert item is None
    assert seller is None


@pytest.mark.asyncio
async def test_get_seller_by_username_success():
    client = GrailedAlgoliaClient()
    mock_resp_data = {"results": [{"hits": [SAMPLE_ACTIVE_HIT], "nbHits": 1}]}

    mock_session = AsyncMock(spec=aiohttp.ClientSession)
    mock_post_ctx = AsyncMock()
    mock_post_ctx.status = 200
    mock_post_ctx.json = AsyncMock(return_value=mock_resp_data)
    mock_session.post.return_value.__aenter__.return_value = mock_post_ctx

    seller = await client.get_seller_by_username("eraluxe", mock_session)
    assert seller is not None
    assert seller.num_reviews == 118
    assert seller.avg_rating == 4.87
    assert seller.trusted_badge is True
```

- [ ] **Step 2: Запустить тесты и убедиться в падении**

Run: `pytest tests_new/unit/test_grailed_algolia_client.py -v`  
Expected: FAIL (`ModuleNotFoundError: No module named 'app.services.grailed_algolia'`).

- [ ] **Step 3: Реализовать `GrailedAlgoliaClient` в `app/services/grailed_algolia.py`**

```python
"""Grailed Algolia search index client.

Extracts structured listing and seller profile data directly from Grailed's
Algolia backend, bypassing HTML scraping and browser-based anti-bot hurdles.
"""

from __future__ import annotations

import asyncio
import logging
from decimal import Decimal
from typing import Any

import aiohttp

from ..config import config
from ..models import ItemData, SellerData

logger = logging.getLogger(__name__)


class GrailedAlgoliaClient:
    """Client for querying Grailed listings and seller profiles via Algolia."""

    def __init__(self) -> None:
        self.cfg = config.algolia

    def _get_headers(self) -> dict[str, str]:
        return {
            "x-algolia-application-id": self.cfg.app_id,
            "x-algolia-api-key": self.cfg.api_key,
            "Content-Type": "application/json",
        }

    def _get_endpoint_url(self) -> str:
        return f"https://{self.cfg.app_id.lower()}-dsn.algolia.net/1/indexes/*/queries"

    def _map_hit_to_models(
        self, hit: dict[str, Any]
    ) -> tuple[ItemData | None, SellerData | None]:
        """Convert a raw Algolia hit into ItemData and SellerData."""
        try:
            title = hit.get("title")
            raw_price = hit.get("price")
            if raw_price is None:
                logger.warning("Algolia hit missing price for id: %s", hit.get("id"))
                return None, None

            price = Decimal(str(raw_price))

            # US shipping mapping
            shipping_data = hit.get("shipping") or {}
            shipping_us: Decimal | None = None
            if isinstance(shipping_data, dict):
                us_ship = shipping_data.get("us") or {}
                if isinstance(us_ship, dict):
                    enabled = us_ship.get("enabled", False)
                    amt = us_ship.get("amount")
                    if enabled and amt is not None:
                        shipping_us = Decimal(str(amt))
                    elif not enabled:
                        shipping_us = Decimal("0")

            is_buyable = bool(hit.get("buynow", False))

            # Cover image URL
            cover_photo = hit.get("cover_photo") or {}
            image_url: str | None = None
            if isinstance(cover_photo, dict):
                image_url = cover_photo.get("image_url") or cover_photo.get("url")

            item_data = ItemData(
                price=price,
                shipping_us=shipping_us,
                is_buyable=is_buyable,
                title=str(title).strip() if title else None,
                image_url=image_url,
            )

            # Seller mapping
            user_data = hit.get("user") or {}
            seller_score = user_data.get("seller_score") or {}
            num_reviews = int(seller_score.get("rating_count") or 0)
            avg_rating = round(float(seller_score.get("rating_average") or 0.0), 2)
            trusted_badge = bool(user_data.get("trusted_seller", False))

            seller_data = SellerData(
                num_reviews=num_reviews,
                avg_rating=avg_rating,
                trusted_badge=trusted_badge,
                technical_issue=False,
            )

            return item_data, seller_data

        except Exception as exc:
            logger.error("Failed to map Algolia hit to models: %s", exc, exc_info=True)
            return None, None

    async def get_listing_by_id(
        self, listing_id: int | str, session: aiohttp.ClientSession
    ) -> tuple[ItemData | None, SellerData | None]:
        """Fetch listing item data and seller data by listing ID."""
        cleaned_id = str(listing_id).strip()
        payload = {
            "requests": [
                {
                    "indexName": self.cfg.index_name,
                    "params": f"filters=id%3D{cleaned_id}&hitsPerPage=1",
                }
            ]
        }

        try:
            timeout = aiohttp.ClientTimeout(total=self.cfg.timeout_sec)
            async with session.post(
                self._get_endpoint_url(),
                headers=self._get_headers(),
                json=payload,
                timeout=timeout,
            ) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    results = data.get("results", [])
                    if results and results[0].get("hits"):
                        hit = results[0]["hits"][0]
                        return self._map_hit_to_models(hit)
                    logger.info("Listing ID %s not found in Algolia index", cleaned_id)
                    return None, None
                else:
                    err_body = await resp.text()
                    logger.error(
                        "Algolia query failed with HTTP %s for listing %s: %s",
                        resp.status,
                        cleaned_id,
                        err_body[:200],
                    )
                    return None, None

        except TimeoutError:
            logger.warning("Algolia query timed out for listing %s", cleaned_id)
            return None, None
        except Exception as exc:
            logger.error("Error querying Algolia for listing %s: %s", cleaned_id, exc)
            return None, None

    async def get_seller_by_username(
        self, username: str, session: aiohttp.ClientSession
    ) -> SellerData | None:
        """Fetch seller profile data by username via Algolia search."""
        cleaned_username = username.strip()
        payload = {
            "requests": [
                {
                    "indexName": self.cfg.index_name,
                    "params": f"query={cleaned_username}&hitsPerPage=1",
                }
            ]
        }

        try:
            timeout = aiohttp.ClientTimeout(total=self.cfg.timeout_sec)
            async with session.post(
                self._get_endpoint_url(),
                headers=self._get_headers(),
                json=payload,
                timeout=timeout,
            ) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    results = data.get("results", [])
                    if results and results[0].get("hits"):
                        hit = results[0]["hits"][0]
                        user_data = hit.get("user") or {}
                        hit_username = user_data.get("username", "")
                        if hit_username.lower() == cleaned_username.lower():
                            _, seller_data = self._map_hit_to_models(hit)
                            return seller_data

                    logger.info("Seller username %s not found in Algolia hits", cleaned_username)
                    return None
                else:
                    err_body = await resp.text()
                    logger.error(
                        "Algolia seller query failed with HTTP %s for %s: %s",
                        resp.status,
                        cleaned_username,
                        err_body[:200],
                    )
                    return None

        except TimeoutError:
            logger.warning("Algolia seller query timed out for %s", cleaned_username)
            return None
        except Exception as exc:
            logger.error("Error querying Algolia for seller %s: %s", cleaned_username, exc)
            return None


grailed_algolia_client = GrailedAlgoliaClient()
```

- [ ] **Step 4: Запустить тесты и убедиться в прохождении**

Run: `pytest tests_new/unit/test_grailed_algolia_client.py -v`  
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add app/services/grailed_algolia.py tests_new/unit/test_grailed_algolia_client.py
git commit -m "feat(services): implement GrailedAlgoliaClient"
```

---

### Task 3: Рефакторинг `GrailedScraper` на использование Algolia

**Files:**
- Modify: `app/scrapers/grailed_scraper.py`
- Modify: `tests_new/unit/test_grailed_scraper.py` (или создание обновленных тестов скрапера)

**Interfaces:**
- Consumes: `app.services.grailed_algolia.grailed_algolia_client`, `app.scrapers.grailed_url_resolver.async_normalize_grailed_url`.
- Produces: `GrailedScraper` (`ScraperProtocol`).

- [ ] **Step 1: Написать тесты для обновленного `GrailedScraper`**

Создать/обновить `tests_new/unit/test_grailed_scraper_algolia.py`:
```python
from decimal import Decimal
from unittest.mock import AsyncMock, patch

import pytest
import aiohttp

from app.models import ItemData, SellerData
from app.scrapers.grailed_scraper import GrailedScraper


@pytest.mark.asyncio
async def test_grailed_scraper_scrape_item_success():
    scraper = GrailedScraper()
    mock_session = AsyncMock(spec=aiohttp.ClientSession)

    mock_item = ItemData(
        price=Decimal("34"),
        shipping_us=Decimal("9"),
        is_buyable=True,
        title="Vissla Board Shorts",
        image_url="https://example.com/img.jpg"
    )
    mock_seller = SellerData(
        num_reviews=100,
        avg_rating=4.9,
        trusted_badge=True
    )

    with patch(
        "app.scrapers.grailed_scraper.grailed_algolia_client.get_listing_by_id",
        new_callable=AsyncMock,
        return_value=(mock_item, mock_seller)
    ) as mock_get:
        url = "https://www.grailed.com/listings/99406229-vissla-board-shorts"
        result = await scraper.scrape_item(url, mock_session)

        mock_get.assert_called_once_with("99406229", mock_session)
        assert result == mock_item
        assert scraper.extract_seller_profile_url(result) == "https://www.grailed.com/cached_seller"

        # Check cached seller retrieval
        cached_seller = await scraper.scrape_seller("https://www.grailed.com/cached_seller", mock_session)
        assert cached_seller == mock_seller


@pytest.mark.asyncio
async def test_grailed_scraper_scrape_seller_by_username():
    scraper = GrailedScraper()
    mock_session = AsyncMock(spec=aiohttp.ClientSession)

    mock_seller = SellerData(
        num_reviews=50,
        avg_rating=4.8,
        trusted_badge=False
    )

    with patch(
        "app.scrapers.grailed_scraper.grailed_algolia_client.get_seller_by_username",
        new_callable=AsyncMock,
        return_value=mock_seller
    ) as mock_get_user:
        url = "https://www.grailed.com/best_seller_shop"
        result = await scraper.scrape_seller(url, mock_session)

        mock_get_user.assert_called_once_with("best_seller_shop", mock_session)
        assert result == mock_seller
```

- [ ] **Step 2: Запустить тест и убедиться в падении**

Run: `pytest tests_new/unit/test_grailed_scraper_algolia.py -v`  
Expected: FAIL.

- [ ] **Step 3: Реализовать рефакторинг `GrailedScraper` в `app/scrapers/grailed_scraper.py`**

Обновить `app/scrapers/grailed_scraper.py`:
- Удалить импорты `BeautifulSoup`, `headless`.
- Добавить вспомогательную функцию `extract_grailed_listing_id(url: str) -> str | None`.
- В `scrape_item(url, session)`:
  1. Нормализовать URL через `async_normalize_grailed_url(url, session)`.
  2. Извлечь ID листинга. Если ID отсутствует $\to$ возврат `None`.
  3. Вызвать `grailed_algolia_client.get_listing_by_id(listing_id, session)`.
  4. Сохранить `seller_data` в `self._cached_seller_data`.
  5. Вернуть `item_data`.
- В `scrape_seller(url, session)`:
  1. Если URL — cached dummy URL (`https://www.grailed.com/cached_seller`), вернуть `self._cached_seller_data`.
  2. Если URL — профиль, извлечь username из path.
  3. Вызвать `grailed_algolia_client.get_seller_by_username(username, session)`.
  4. Если не найден, вернуть fallback `_fallback_seller_data("seller_not_found")`.

- [ ] **Step 4: Запустить unit-тесты скрапера**

Run: `pytest tests_new/unit/test_grailed_scraper_algolia.py -v`  
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add app/scrapers/grailed_scraper.py tests_new/unit/test_grailed_scraper_algolia.py
git commit -m "feat(scrapers): migrate GrailedScraper to Algolia backend"
```

---

### Task 4: Интеграционное и регрессионное тестирование

**Files:**
- Modify/Create: `tests_new/integration/test_grailed_orchestration.py`
- Check: All tests across `tests_new/`

**Interfaces:**
- Test orchestration with `scraping_orchestrator`, `seller_assessment`, and `response_formatter`.

- [ ] **Step 1: Написать сквозной интеграционный тест оркестрации Grailed**

Создать `tests_new/integration/test_grailed_orchestration.py`:
```python
from decimal import Decimal
from unittest.mock import AsyncMock, patch

import pytest
import aiohttp

from app.bot.scraping_orchestrator import scraping_orchestrator
from app.models import ItemData, SellerData
from app.services.seller_assessment import evaluate_seller_advisory


@pytest.mark.asyncio
async def test_orchestrator_grailed_item_and_advisory_flow():
    mock_item = ItemData(
        price=Decimal("45"),
        shipping_us=Decimal("10"),
        is_buyable=True,
        title="Vintage Hoodie",
        image_url="https://example.com/img.jpg",
    )
    mock_seller = SellerData(
        num_reviews=15,
        avg_rating=4.2,  # Low rating threshold <= 4.6
        trusted_badge=False,
    )

    with patch(
        "app.scrapers.grailed_scraper.grailed_algolia_client.get_listing_by_id",
        new_callable=AsyncMock,
        return_value=(mock_item, mock_seller),
    ):
        async with aiohttp.ClientSession() as session:
            result = await scraping_orchestrator.scrape_item_listing(
                "https://www.grailed.com/listings/99406229", session
            )

            assert result["success"] is True
            assert result["platform"] == "grailed"
            assert result["item_data"] == mock_item
            assert result["seller_data"] == mock_seller

            # Evaluate advisory
            advisory = evaluate_seller_advisory(
                seller_data=result["seller_data"], item_data=result["item_data"]
            )
            assert advisory.reason == "low_rating"
```

- [ ] **Step 2: Запустить интеграционный тест**

Run: `pytest tests_new/integration/test_grailed_orchestration.py -v`  
Expected: PASS.

- [ ] **Step 3: Запустить полный набор тестов проекта**

Run: `pytest tests_new/ -v`  
Expected: Все тесты проходят (за исключением изолированных headless тестов, которые можно пометить как устаревшие).

- [ ] **Step 4: Запустить probe скрипт для подтверждения**

Run: `python scripts/probe_grailed_algolia.py --incidents -v`  
Expected: 4/4 incident listings возвращают `[OK]` с точными данными.

- [ ] **Step 5: Commit**

```bash
git add tests_new/integration/test_grailed_orchestration.py
git commit -m "test(integration): add Grailed orchestration integration tests"
```
