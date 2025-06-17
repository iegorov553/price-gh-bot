# Система аналитики бота

Бот включает в себя комплексную систему аналитики для сбора данных о поисковых запросах пользователей и использовании бота.

## Архитектура

### Модель данных (`SearchAnalytics`)

Каждый запрос пользователя сохраняется в SQLite базе данных со следующими полями:

```python
class SearchAnalytics(BaseModel):
    url: str                              # Исходный URL запроса
    user_id: int                          # Telegram ID пользователя  
    username: str | None                  # Telegram username
    timestamp: datetime                   # Время обработки запроса
    platform: str                        # Платформа (ebay/grailed/profile)
    success: bool                         # Успешность обработки
    item_price: Decimal | None            # Цена товара в USD
    shipping_us: Decimal | None           # Доставка по США
    item_title: str | None               # Название товара
    error_message: str | None            # Сообщение об ошибке
    processing_time_ms: int | None       # Время обработки в мс
    seller_score: int | None             # Оценка продавца (0-100)
    seller_category: str | None          # Категория продавца (Diamond/Gold/etc)
    final_price_usd: Decimal | None      # Итоговая цена в USD
    commission: Decimal | None           # Размер комиссии
    is_buyable: bool | None             # Доступность для покупки
```

### База данных

- **SQLite** база с автоматической инициализацией
- **Индексы** для оптимизации запросов по `user_id`, `timestamp`, `platform`, `success`
- **Путь**: `data/analytics.db` (настраивается через `ANALYTICS_DB_PATH`)

### Сервис аналитики (`AnalyticsService`)

Основной класс для работы с аналитическими данными:

```python
from app.services.analytics import analytics_service

# Логирование запроса
analytics_service.log_search(SearchAnalytics(...))

# Получение статистики
stats = analytics_service.get_daily_stats(days=7)
user_stats = analytics_service.get_user_stats(user_id=12345)
popular = analytics_service.get_popular_searches(limit=10)
errors = analytics_service.get_error_analysis(days=7)

# Экспорт данных
success = analytics_service.export_to_csv("export.csv", days=30)
```

## Конфигурация

Настройки аналитики в `app/config.py`:

```python
class AnalyticsConfig(BaseSettings):
    enabled: bool = True                  # Включить/выключить сбор данных
    db_path: str = "data/analytics.db"    # Путь к базе данных
    export_enabled: bool = True           # Разрешить экспорт данных
    retention_days: int = 365            # Срок хранения данных (дней)
```

### Переменные окружения

- `ANALYTICS_ENABLED` - включить аналитику (по умолчанию: `true`)
- `ANALYTICS_DB_PATH` - путь к БД (по умолчанию: `data/analytics.db`)
- `ANALYTICS_EXPORT_ENABLED` - разрешить экспорт (по умолчанию: `true`)
- `ANALYTICS_RETENTION_DAYS` - срок хранения данных (по умолчанию: `365`)

## Команды для админа

Бот предоставляет следующие команды для анализа данных (только для админа):

### `/analytics_daily`
Статистика за последний день:
- Общее количество поисков
- Процент успешных запросов
- Количество уникальных пользователей
- Среднее время обработки
- Разбивка по платформам

### `/analytics_week`
Аналогичная статистика за неделю.

### `/analytics_user <user_id>`
Детальная статистика конкретного пользователя:
- История поисков по платформам
- Средние цены товаров
- Последние запросы

### `/analytics_errors [days]`
Анализ ошибок за указанный период:
- Частые ошибки по платформам
- Наиболее распространенные сообщения об ошибках

### `/analytics_export [days]`
Экспорт данных в CSV файл:
- Все данные или за указанный период
- Отправляется в виде документа в чат

## Интеграция в код

### Автоматическое логирование

Аналитика автоматически собирается в обработчиках `app/bot/handlers.py`:

1. **Профили продавцов** (`_handle_seller_profile`)
2. **Листинги товаров** (`_handle_listings`)

### Логирование успешных запросов

```python
# Успешная обработка листинга
analytics_data = SearchAnalytics(
    url=url,
    user_id=user_id,
    username=username,
    platform=detect_platform(url),
    success=True,
    item_price=item_data.price,
    shipping_us=item_data.shipping_us,
    item_title=item_data.title,
    seller_score=reliability_score.total_score if reliability_score else None,
    seller_category=reliability_score.category if reliability_score else None,
    final_price_usd=calculation.final_price_usd,
    commission=calculation.commission,
    is_buyable=item_data.is_buyable,
    processing_time_ms=processing_time
)
analytics_service.log_search(analytics_data)
```

### Логирование ошибок

```python
# Обработка с ошибкой
analytics_data = SearchAnalytics(
    url=url,
    user_id=user_id,
    username=username,
    platform=detect_platform(url),
    success=False,
    error_message=str(error),
    processing_time_ms=processing_time
)
analytics_service.log_search(analytics_data)
```

## Статистики и отчеты

### Базовая статистика
- Общее количество поисков
- Процент успешных запросов  
- Уникальные пользователи
- Среднее время обработки
- Средняя цена товаров

### Разбивка по платформам
- eBay vs Grailed vs профили продавцов
- Успешность для каждой платформы
- Популярность платформ

### Анализ пользователей
- Активность отдельных пользователей
- Предпочтения по платформам
- История поисков

### Анализ ошибок
- Самые частые ошибки
- Проблемные платформы
- Временные паттерны сбоев

## Производительность

- **Индексы** для быстрого поиска по ключевым полям
- **Асинхронное логирование** не блокирует основную работу бота
- **Пакетная обработка** для операций с большими объемами данных
- **Ротация данных** - автоматическое удаление старых записей (настраивается)

## Приватность и безопасность

- Сохраняются только **публичные данные** (URL, цены, время)
- **Username** сохраняется опционально (может быть NULL)
- **Нет персональных данных** сверх базовой идентификации Telegram
- **Админский доступ** - команды аналитики доступны только админу
- **Настраиваемость** - аналитику можно полностью отключить

## Использование данных

Собранные данные помогают:

1. **Понять предпочтения пользователей** - какие товары ищут чаще
2. **Оптимизировать производительность** - выявить узкие места
3. **Улучшить надежность** - анализировать частые ошибки
4. **Планировать развитие** - видеть тренды использования
5. **Мониторить качество** - отслеживать успешность обработки

## Будущие улучшения

- **Дашборд** для визуализации статистики
- **Алерты** при критических ошибках
- **A/B тестирование** различных подходов
- **Машинное обучение** для предсказания предпочтений
- **API** для внешнего доступа к аналитике