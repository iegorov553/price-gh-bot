# Price Bot for Telegram

Telegram бот для расчёта стоимости товаров с eBay и Grailed с учётом доставки, комиссии и курса валют. Включает анализ надёжности продавцов Grailed.

## Основные возможности

- **Поддержка платформ**: eBay и Grailed (включая app.link ссылки)
- **Умная система комиссий**: 
  - Фиксированная комиссия $15 для товаров дешевле $150
  - Наценка 10% для товаров от $150
- **Расчёт доставки**: Автоматическое определение стоимости доставки в США + оценка доставки в РФ (Shopfans Lite)
- **Конвертация валют**: Перевод в рубли по курсу ЦБ РФ (+5% наценка)
- **Анализ продавцов Grailed**: Система оценки надёжности по 4 критериям
- **Определение типа листинга**: Различает товары с фиксированной ценой и только для переговоров
- **Параллельная обработка**: Обработка нескольких URL в одном сообщении
- **Режимы развёртывания**: Webhook (продакшн) и polling (разработка)

## Система оценки продавцов Grailed

Бот анализирует надёжность продавца по 4 критериям:

### Критерии оценки (максимум 100 баллов)
- **Активность (0-30 баллов)**: Время с последнего обновления листингов
  - 0-2 дня: 30 баллов
  - 3-7 дней: 24 балла  
  - 8-30 дней: 12 баллов
  - >30 дней: категория "Ghost"
- **Рейтинг (0-35 баллов)**: Средняя оценка продавца
  - 4.90-5.00: 35 баллов
  - 4.70-4.89: 30 баллов
  - 4.50-4.69: 24 балла
  - 4.00-4.49: 12 баллов
- **Объём отзывов (0-25 баллов)**: Количество отзывов
  - 200+: 25 баллов
  - 50-199: 20 баллов
  - 10-49: 15 баллов
  - 1-9: 5 баллов
- **Бейдж Trusted Seller (0-10 баллов)**: Наличие официального бейджа

### Категории надёжности
- 💎 **Diamond (85-100)**: Продавец топ-уровня
- 🥇 **Gold (70-84)**: Высокая надёжность
- 🥈 **Silver (55-69)**: Нормальная надёжность
- 🥉 **Bronze (40-54)**: Повышенный риск
- 👻 **Ghost (<40 или >30 дней)**: Низкая надёжность

## Логика ценообразования

### Структура комиссий
- **Товары < $150**: Фиксированная комиссия $15
  - Пример: $89.99 + $12.50 доставка = $102.49 → **$117.49** (₽11,749)
- **Товары ≥ $150**: Наценка 10%
  - Пример: $250.00 + бесплатная доставка = $250.00 → **$275.00** (₽27,500)

### Оценка доставки РФ (Shopfans Lite)

Автоматическая оценка стоимости доставки в Россию по категориям товаров:

**Формула**: `max($13.99, $14 × вес) + (вес ≤ 0.45кг ? $3 : $5)`

| Категория | Вес (кг) | Стоимость |
|-----------|----------|-----------|
| Футболки | 0.20 | $16.99 |
| Худи/Свитшоты | 0.70 | $18.99 |
| Джинсы | 0.70 | $18.99 |
| Кроссовки | 1.40 | $23.60 |
| Ботинки | 1.80 | $30.20 |
| Чемоданы | 3.00 | $47.00 |
| По умолчанию | 0.60 | $18.99 |

### Конвертация валют
- Курс USD к RUB от **Центрального Банка России (ЦБ РФ)** 
- Официальные ежедневные курсы: `https://www.cbr.ru/scripts/XML_daily.asp`
- Дополнительная наценка 5% к официальному курсу ЦБ РФ
- Итоговая цена отображается в долларах и рублях
- Уведомления администратора при недоступности API ЦБ РФ

## Поддерживаемые платформы

- **eBay**: Полное определение цены и доставки
- **Grailed**: Извлечение цены с расчётом доставки и анализом продавца
- **Grailed app.link**: Автоматическое разрешение коротких ссылок

## Installation

```bash
# Install dependencies
pip install -r requirements.txt

# Set environment variables
export BOT_TOKEN="your_telegram_bot_token"
export PORT=8000  # Optional, defaults to 8000
```

## Usage

### Local Development
```bash
python price_bot.py
```
The bot will run in polling mode for local testing.

### Production Deployment (Railway)
The bot automatically detects Railway environment and switches to webhook mode.

```bash
# Railway deployment
railway up
```

## Environment Variables

| Variable | Required | Description |
|----------|----------|-------------|
| `BOT_TOKEN` | Yes | Telegram bot token from @BotFather |
| `PORT` | No | Server port (default: 8000) |
| `RAILWAY_PUBLIC_DOMAIN` | No | Railway domain for webhook mode |

## Команды бота

- `/start` - Показать приветственное сообщение и информацию о ценах
- **Ссылка на товар eBay/Grailed** - Расчёт стоимости с комиссией и конвертацией в рубли
- **Ссылка на профиль Grailed** - Анализ надёжности продавца

## Типы ответов

### Товар с фиксированной ценой
```
Цена: $89.99 + $12.50 доставка по США + $16.99 доставка РФ = $119.48
С учетом комиссия $15: $134.48 (₽13,448.00)

💎 Продавец: Diamond (92/100)
Продавец топ-уровня, можно брать без лишних вопросов
```

### Товар только для переговоров  
```
У продавца не указана цена выкупа. Для расчёта полной стоимости товара необходимо связаться с продавцом.

Указанная цена: $150 (только для переговоров)
```

### Анализ профиля продавца
```
💎 Анализ продавца Grailed

Надёжность: Diamond (92/100)
Продавец топ-уровня, можно брать без лишних вопросов

Детали:
• Активность: 30/30 (обновления сегодня)
• Рейтинг: 35/35 (4.9/5.0)
• Отзывы: 25/25 (245 отзывов)
• Бейдж: 10/10 (✅ Проверенный продавец)
```

## Architecture

### Core Files
- **`price_bot.py`**: Main application logic with all scraping and analysis functions
- **`messages.py`**: Centralized localized messages in Russian for easy editing and maintenance

### Technical Stack
- **HTTP session**: Retry logic and proper user agents for reliable scraping
- **Concurrent processing**: `asyncio.gather()` for parallel URL processing
- **Robust parsing**: Multiple extraction strategies for evolving website structures:
  - BeautifulSoup for HTML parsing with multiple CSS selectors
  - JSON parsing with various field name patterns and fallback strategies
  - Comprehensive error handling and detailed logging
- **Financial precision**: Decimal arithmetic for accurate price calculations
- **Date handling**: Multiple datetime formats (ISO, epoch, HTML attributes)

### Data Extraction Strategy
The bot uses a multi-layered approach for reliable data extraction from dynamic websites:

1. **JSON Parsing**: Primary method using multiple regex patterns for various field names
2. **HTML Fallback**: Secondary method parsing visible HTML elements when JSON fails  
3. **Profile Fetching**: Tertiary method fetching seller data directly from profile pages
4. **Comprehensive Logging**: Detailed debug information for troubleshooting extraction issues

## Error Handling

- **Currency conversion**: CBR API failures trigger admin notifications via Telegram
- **Robust extraction**: Multiple CSS selectors and JSON patterns for price extraction
- **Request resilience**: Timeouts and retry mechanisms for network reliability
- **Comprehensive logging**: Detailed debug information for troubleshooting scraping issues
- **Fallback strategies**: Multiple extraction methods when primary parsing fails
- **Conservative approach**: Shows USD only if CBR API is unavailable (no fallback rates)

## Recent Updates

### Enhanced Seller Data Extraction (Latest)
- **Multi-pattern parsing**: Added comprehensive regex patterns for various JSON field formats
- **Robust date handling**: Support for ISO dates, epoch timestamps, and HTML datetime attributes  
- **Fallback strategies**: HTML parsing when JSON data is unavailable
- **Profile URL detection**: Updated patterns for new Grailed URL structure (`/username` format)
- **Detailed logging**: Enhanced debug information for troubleshooting extraction issues
- **Messages module**: Centralized all user-facing text in `messages.py` for easy localization

### Previous Features
- Grailed seller reliability evaluation system with 4-criteria scoring
- Tiered commission structure ($15 fixed vs 10% markup)
- Central Bank of Russia currency conversion with admin notifications
- Concurrent URL processing for multiple links
- Buy-now vs offer-only detection for Grailed listings

## Development

See `CLAUDE.md` for detailed development guidance and architecture information.