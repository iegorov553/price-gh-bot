# Price Bot for Telegram

Telegram бот для расчёта стоимости товаров с eBay и Grailed с учётом доставки, комиссии и курса валют. Включает анализ надёжности продавцов Grailed.

## Основные возможности

- **Поддержка платформ**: eBay и Grailed (включая app.link ссылки)
- **Умная система комиссий**: 
  - Фиксированная комиссия $15 для товаров дешевле $150
  - Наценка 10% для товаров от $150
- **Расчёт доставки**: Автоматическое определение стоимости доставки в США
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
Цена: $89.99 + $12.50 доставка = $102.49
С учетом комиссия $15: $117.49 (₽11,749.00)

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

- Single-file Python application (`price_bot.py`)
- HTTP session with retry logic and proper user agents
- Concurrent URL processing using `asyncio.gather()`
- BeautifulSoup for HTML parsing with multiple CSS selectors
- Decimal precision for accurate financial calculations

## Error Handling

- **Currency conversion**: CBR API failures trigger admin notifications via Telegram
- Multiple CSS selectors for robust price extraction
- Request timeouts and retry mechanisms
- Comprehensive logging for debugging
- No fallback rates - shows USD only if CBR API is unavailable

## Development

See `CLAUDE.md` for detailed development guidance and architecture information.