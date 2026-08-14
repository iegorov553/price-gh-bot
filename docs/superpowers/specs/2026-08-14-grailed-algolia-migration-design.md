# Дизайн миграции получения данных Grailed на поисковый индекс Algolia

**Дата:** 2026-08-14  
**Статус:** Утверждено  
**Область:** `app/config.py`, `app/services/grailed_algolia.py`, `app/scrapers/grailed_scraper.py`, `tests_new/`

---

## 1. Контекст и цели

### Проблема
Текущий способ получения данных листингов Grailed через статический HTTP и Playwright Chromium в Railway staging стабильно возвращает `HTTP 403` из-за блокировок датацентровых IP и фингерпринтов автоматизированного браузера Cloudflare/Grailed. Каждая попытка приводит к 20-секундной задержке перед падением с ошибкой `incomplete`.

### Решение
Замена HTML/Playwright скрапинга на прямое обращение к поисковому индексу Algolia (`Listing_production`), используемому официальным фронтендом Grailed. В ходе верификации подтверждено:
- 100% доступность из Railway staging (`200 OK`, 0 блокировок 403/429);
- Latency ~100–350 мс (в 50–100 раз быстрее Playwright);
- Полное наличие всех необходимых полей для `ItemData` (цена, название, доставка по США, buy-now) и `SellerData` (рейтинг, количество отзывов, trusted статус).

---

## 2. Архитектура решения

```
┌─────────────────────────────────────────────────────────────┐
│                   app/bot/handlers.py                       │
│                            │                                │
│                            ▼                                │
│             app/bot/scraping_orchestrator.py                │
│                            │                                │
│                            ▼                                │
│      app/scrapers/base.py (ScraperProtocol)                 │
│              ▲                              ▲               │
│              │                              │               │
│    app/scrapers/ebay_scraper.py   app/scrapers/grailed_scraper.py
│                                             │
│                                             ▼
│                             app/services/grailed_algolia.py │
│                             (GrailedAlgoliaClient)          │
│                                             │
│                                             ▼
│                              Algolia API (HTTPS / JSON)     │
└─────────────────────────────────────────────────────────────┘
```

### Принципы
1. **SOLID & Single Responsibility:** Вся логика протокола Algolia инкапсулирована в `GrailedAlgoliaClient`.
2. **Сохранение контракта `ScraperProtocol`:** `GrailedScraper` продолжает реализовывать единый интерфейс скрапера, оркестратор и хэндлеры бота не требуют изменений.
3. **Быстрый отказ (Fast-Fail):** При отсутствии листинга или ошибке сети не запускается Playwright, бот мгновенно возвращает ответ.
4. **Конфигурируемость:** Все параметры (App ID, API Key, Index Name, Timeout) управляются через Pydantic Settings и переменные окружения.

---

## 3. Компоненты системы

### 3.1. Конфигурация (`app/config.py`)
Новый класс настроек `GrailedAlgoliaConfig`:
- `app_id: str = Field(default="MNRWEFSS2Q", validation_alias="GRAILED_ALGOLIA_APP_ID")`
- `api_key: str = Field(default="c89dbaddf15fe70e1941a109bf7c2a3d", validation_alias="GRAILED_ALGOLIA_API_KEY")`
- `index_name: str = Field(default="Listing_production", validation_alias="GRAILED_ALGOLIA_INDEX_NAME")`
- `timeout_sec: float = Field(default=5.0, validation_alias="GRAILED_ALGOLIA_TIMEOUT_SEC")`

Интеграция в общую конфигурацию `config.algolia`.

### 3.2. Клиент Algolia (`app/services/grailed_algolia.py`)
Класс `GrailedAlgoliaClient`:
- **`get_listing_by_id(listing_id: int | str, session: aiohttp.ClientSession) -> tuple[ItemData | None, SellerData | None]`**:
  - Выполняет POST запрос к `https://{app_id}-dsn.algolia.net/1/indexes/*/queries`.
  - Формирует payload: `{"requests": [{"indexName": index_name, "params": "filters=id%3D<ID>&hitsPerPage=1"}]}`.
  - Извлекает и валидирует данные записи.
  - Возвращает пару `(ItemData, SellerData)` или `(None, None)` при отсутствии/ошибке.
- **`get_seller_by_username(username: str, session: aiohttp.ClientSession) -> SellerData | None`**:
  - Формирует payload с поиском по имени: `"query=<username>&hitsPerPage=1"`.
  - Сверяет имя продавца в найденной записи с запрошенным.
  - Возвращает `SellerData` или `None`.

### 3.3. Рефакторинг `GrailedScraper` (`app/scrapers/grailed_scraper.py`)
- Замена старого кода парсинга Next.js/HTML и Playwright-вызовов на делегирование в `GrailedAlgoliaClient`.
- Извлечение числового ID из URL листинга (`/listings/<id>-...` или короткие ссылки через `grailed_url_resolver`).
- Сохранение кэширования `_cached_seller_data` для поддержки стандартного протокола оркестратора.

---

## 4. Спецификация маппинга полей

### 4.1. `ItemData` (`app/models.py`)
| Поле | Источник в Algolia hit | Преобразование / Fallback |
|---|---|---|
| `title` | `hit["title"]` | `str(hit["title"]).strip()` |
| `price` | `hit["price"]` | `Decimal(str(hit["price"]))` |
| `shipping_us` | `hit["shipping"]["us"]` | `Decimal(str(us["amount"]))` если `us["enabled"] == True`, иначе `Decimal("0")` |
| `is_buyable` | `hit["buynow"]` | `bool(hit.get("buynow", False))` |
| `image_url` | `hit["cover_photo"]` | `cover.get("image_url") or cover.get("url")` |

### 4.2. `SellerData` (`app/models.py`)
| Поле | Источник в Algolia hit | Преобразование / Fallback |
|---|---|---|
| `num_reviews` | `hit["user"]["seller_score"]["rating_count"]` | `int(seller_score.get("rating_count") or 0)` |
| `avg_rating` | `hit["user"]["seller_score"]["rating_average"]` | `round(float(seller_score.get("rating_average") or 0.0), 2)` |
| `trusted_badge` | `hit["user"]["trusted_seller"]` | `bool(user.get("trusted_seller", False))` |
| `technical_issue`| N/A | `False` при успешном ответе |

---

## 5. Отказоустойчивость и обработка ошибок

1. **Листинг не найден (`nbHits: 0`):** Лог `INFO`, возврат `None` $\to$ пользователь получает стандартное сообщение о невозможности найти товар.
2. **HTTP 403 (ротация ключа / невалидные креденшелы):** Лог `ERROR: Algolia authentication failed`, возврат `None`.
3. **HTTP 429 (Rate limiting):** Лог `WARNING: Algolia rate limited`, возврат `None`.
4. **Сетевой таймаут (> 5 секунд):** Лог `WARNING: Algolia request timed out`, возврат `None`.
5. **Некорректная структура JSON / Schema Drift:** Безопасное чтение через `.get()` с дефолтами, логирование аномалий без краша сервиса.

---

## 6. План тестирования и верификации

1. **Unit-тесты:**
   - Тестирование `GrailedAlgoliaClient` с фикстурами реальных ответов Algolia (активный товар, offer-only, бесплатная доставка, продавец с 0 отзывов, продавец с низким рейтингом).
   - Тестирование обработки ошибок клиента (403, 429, timeout, network error, malformed JSON).
   - Тестирование `GrailedScraper` с моком клиента Algolia.
2. **Интеграционные тесты:**
   - Тестирование цепочки `ScrapingOrchestrator` $\to$ `GrailedScraper` $\to$ `GrailedAlgoliaClient` $\to$ расчет стоимости и seller advisory.
3. **Регрессионное тестирование:**
   - Запуск полного тестового набора `pytest tests_new/` для проверки целостности модулей eBay, расчетов доставки Shopfans и таможни.
