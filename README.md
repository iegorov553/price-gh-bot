# Price Comparison Telegram Bot

A Telegram bot that helps users calculate the total cost of buying items from eBay and Grailed, including shipping to Russia and marketplace fees. Features comprehensive seller reliability analysis for Grailed listings using headless browser technology.

## Features

- **Multi-marketplace support**: eBay and Grailed price scraping with dynamic content extraction
- **Complete cost calculation**: Item price + US shipping + Russia delivery + commission
- **Smart commission structure**: Fixed $15 for items <$150, 10% of item price (excluding shipping) for items ≥$150
- **Currency conversion**: USD to RUB with real-time exchange rates from Central Bank of Russia (5% markup)
- **Advanced seller analysis**: Comprehensive Grailed seller scoring using headless browser extraction
- **Activity tracking**: Real-time "X days ago" parsing from seller profiles for accurate activity scoring
- **Shipping estimation**: Smart categorization and weight-based Shopfans pricing
- **Buyability detection**: Identifies buy-now vs offer-only listings
- **Enhanced price display**: Structured multi-line format showing each cost component separately
- **Russian localization**: Clean, emoji-minimal user messages in Russian

## How It Works

1. **URL Detection**: Automatically detects eBay and Grailed URLs
2. **Dynamic Content Extraction**: Uses Playwright headless browser for React SPA data extraction
3. **Price Scraping**: Extracts item price and shipping costs from dynamic content
4. **Activity Analysis**: Parses "5 days ago" patterns from seller profiles for accurate last update tracking
5. **Shipping Calculation**: Estimates Russia delivery via Shopfans weight-based rates
6. **Smart Commission**: Fixed $15 for items <$150, 10% of item price only (excluding shipping) for items ≥$150
7. **Currency Conversion**: Converts final price to Russian Rubles with 5% markup
8. **Comprehensive Seller Analysis** (Grailed): 4-criteria reliability scoring with Diamond/Gold/Silver/Bronze categories

## Seller Reliability System

For Grailed listings, the bot provides comprehensive seller analysis using headless browser technology:

### Scoring System (100 Points Total)
- **Activity Score (0-30 points)**: Days since last listing update
  - Today/Yesterday: 30 points
  - 2-7 days: 24 points  
  - 8-30 days: 12 points
  - >30 days: 0 points (Ghost category)
- **Rating Score (0-35 points)**: Average seller rating
  - 4.8-5.0: 35 points
  - 4.5-4.7: 28 points
  - 4.0-4.4: 21 points
  - 3.5-3.9: 14 points
  - 3.0-3.4: 7 points
  - <3.0: 0 points
- **Review Volume (0-25 points)**: Number of completed transactions
  - 500+ reviews: 25 points
  - 100-499: 20 points
  - 50-99: 15 points
  - 20-49: 10 points
  - 10-19: 5 points
  - <10: 0 points
- **Trust Badge (0-10 points)**: Verified seller status
  - Trusted badge: 10 points
  - No badge: 0 points

### Categories
- **💎 Diamond (85-100)**: Top-tier seller
- **🥇 Gold (70-84)**: High reliability
- **🥈 Silver (55-69)**: Normal reliability
- **🥉 Bronze (40-54)**: Increased risk
- **👻 Ghost (<40 or >30 days inactive)**: Low reliability
- **ℹ️ No Data**: When seller information unavailable

### Technical Implementation
- **Optimized Headless Browser**: Playwright-based extraction with 2.3x performance improvement (8-10s vs 20s)
- **Human-like Behavior**: Stealth features and realistic browsing patterns to avoid bot detection
- **Activity Parsing**: Real-time "5 days ago" text extraction from profile listings
- **Dynamic Loading**: Smart scrolling and waiting for AJAX content to load
- **Browser Reuse**: Global browser instance for faster subsequent requests (3-5s)
- **Graceful Degradation**: Falls back to "No Data" when extraction fails

### User Experience
- **Instant Feedback**: Loading indicators show processing status
- **Clean Interface**: Temporary loading messages automatically deleted when results are ready
- **Performance Transparency**: Users see progress during 8-10 second analysis time

## Installation

### Requirements

- Python 3.11+
- Telegram Bot Token
- Playwright browser binaries
- Railway account (for deployment)

### Local Development

```bash
# Clone repository
git clone <repository-url>
cd price-gh-bot

# Create virtual environment
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt
pip install -r requirements-dev.txt  # For testing

# Install Playwright browsers
playwright install chromium

# Set environment variables
export BOT_TOKEN="your_telegram_bot_token"
export ENABLE_HEADLESS_BROWSER="true"  # Optional, defaults to true

# Run locally
python -m app.main
```

### Deployment

The bot is configured for Railway deployment with Docker:

1. Connect your GitHub repository to Railway
2. Set environment variables:
   - `BOT_TOKEN`: Your Telegram bot token
   - `ENABLE_HEADLESS_BROWSER`: "true" (optional, defaults to true)
3. Deploy using the provided `Dockerfile` and `railway.toml` configuration

The bot automatically:
- Installs Playwright and Chromium browser binaries during build
- Switches between webhook mode (production) and polling mode (local development)
- Uses headless browser for dynamic content extraction

### Docker Build

```bash
# Build Docker image
docker build -t price-gh-bot .

# Run container
docker run -e BOT_TOKEN="your_token" price-gh-bot
```

## Configuration

The bot uses YAML configuration files in `app/config/`:

- `fees.yml`: Commission rates, shipping costs, and currency settings
- `shipping_table.yml`: Weight estimation patterns for different item categories

### Environment Variables

- `BOT_TOKEN`: Required Telegram bot token
- `PORT`: Server port (defaults to 8000)
- `RAILWAY_PUBLIC_DOMAIN`: Public domain for webhook mode
- `ENABLE_HEADLESS_BROWSER`: Enable/disable headless browser (defaults to "true")

### Commission Configuration

```yaml
# fees.yml
commission:
  fixed:
    amount: 15.0      # Fixed commission for items <$150
    threshold: 150.0  # Threshold for commission type
  percentage:
    rate: 0.10        # 10% commission for items ≥$150 (applied to item price only)
```

## Development

### Code Quality

- **Linting**: `ruff check app/ tests/`
- **Type Checking**: `mypy app/`
- **Testing**: `pytest tests/`
- **Documentation**: `mkdocs serve`
- **Docstring Checking**: `pydocstyle app/`

### Testing Headless Browser

```bash
# Test specific seller profile
python test_headless.py

# Test commission calculation
python verify_commission.py

# Run full test suite
pytest tests/ -v
```

## Architecture

The bot follows a modular architecture with headless browser integration:

- **`app/main.py`**: Application entry point with module execution support
- **`app/bot/`**: Telegram bot handlers and clean message formatting
- **`app/scrapers/`**: Web scraping modules with Playwright headless browser
  - `grailed.py`: React SPA data extraction with activity parsing
  - `headless.py`: Playwright browser automation and content extraction
  - `ebay.py`: eBay listing scraping
- **`app/services/`**: Business logic for shipping, currency, and reliability scoring
- **`app/models.py`**: Pydantic data models with type safety
- **`app/config.py`**: Configuration management with YAML support

### Key Technical Features

- **React SPA Support**: Handles dynamic JavaScript-loaded content
- **Activity Extraction**: Parses human-readable time patterns ("5 days ago")
- **Browser Automation**: Chromium headless with proper resource management
- **Graceful Degradation**: Falls back when headless browser unavailable
- **Commission Optimization**: Smart calculation excluding shipping from percentage fees

## Examples

### Price Calculation Response
```
💰 Расчёт стоимости

Товар: $89.99
Доставка в США: $12.50
Доставка в РФ: $16.99
Итого: $119.48

Комиссия: $15 (фикс. сумма)
──────────────────
Итого к оплате: $134.48
В рублях: ₽11,254

Продавец: 💎 Diamond (92/100)
Продавец топ-уровня, можно брать без лишних вопросов
```

### Seller Analysis Response
```
Анализ продавца Grailed

Надёжность: 💎 Diamond (92/100)
Продавец топ-уровня, можно брать без лишних вопросов

Детали:
• Активность: 30/30 (обновления сегодня)
• Рейтинг: 35/35 (4.9/5.0)
• Отзывы: 25/25 (245 отзывов)
• Бейдж: 10/10 (Проверенный продавец)
```

## Contributing

1. Fork the repository
2. Create a feature branch
3. Make your changes with tests
4. Run code quality checks
5. Submit a pull request

---

*For detailed development guidance and internal architecture documentation, see [CLAUDE.md](CLAUDE.md)*