# Price Bot for Telegram

A Telegram bot that scrapes prices from eBay and Grailed listings, calculates shipping costs, applies commission, and converts to RUB.

## Features

- **Multi-platform scraping**: Supports eBay and Grailed listings
- **Intelligent pricing**: 
  - Fixed $15 commission for items under $150
  - 10% markup for items $150 and above
- **Shipping calculation**: Automatically detects and includes US shipping costs
- **Currency conversion**: Converts final price to RUB using **Central Bank of Russia** official rates (+5% markup)
- **Concurrent processing**: Handles multiple URLs in a single message
- **Dual deployment modes**: Webhook (production) and polling (development)

## Pricing Logic

### Commission Structure
- **Items < $150**: Fixed $15 commission
  - Example: $89.99 + $12.50 shipping = $102.49 → **$117.49** (₽11,749)
- **Items ≥ $150**: 10% markup  
  - Example: $250.00 + free shipping = $250.00 → **$275.00** (₽27,500)

### Currency Conversion
- USD to RUB exchange rate from **Central Bank of Russia (CBR)** official API
- Uses daily official rates: `https://www.cbr.ru/scripts/XML_daily.asp`
- Additional 5% markup applied to the official CBR rate
- Final price displayed in both USD and RUB
- Admin notifications if CBR API is unavailable

## Supported Platforms

- **eBay**: Full price and shipping detection
- **Grailed**: Price extraction with shipping calculation
- **Grailed app.link**: Automatic shortener resolution

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

## Bot Commands

- `/start` - Display welcome message and pricing information
- Send any eBay or Grailed URL - Get price calculation with commission and RUB conversion

## Example Output

```
Price: $89.99 + $12.50 shipping = $102.49
With $15 commission: $117.49 (₽11,749.00)
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