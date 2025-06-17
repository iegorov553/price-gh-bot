# Price Comparison Telegram Bot

A modern, scalable Telegram bot that calculates total costs for eBay and Grailed purchases including shipping to Russia and marketplace fees. Features advanced seller reliability analysis using headless browser technology and clean SOLID architecture.

## 🚀 Features

### Core Functionality
- **Multi-marketplace support**: eBay and Grailed price scraping with dynamic content extraction
- **Complete cost calculation**: Item price + US shipping + Russian customs duty + Russia delivery + commission
- **Smart commission structure**: Fixed $15 for orders <$150, 10% for orders ≥$150 (including US shipping)
- **Russian customs duty**: Automatic 15% duty calculation for imports exceeding 200 EUR threshold
- **Multi-currency support**: EUR/USD rates for customs, USD/RUB for final conversion (Central Bank of Russia API)
- **Enhanced price display**: Two-tier structured format with intermediate subtotal and additional costs breakdown

### Advanced Seller Analysis (Grailed)
- **Comprehensive scoring**: 4-criteria reliability evaluation (100-point scale)
- **Activity tracking**: Real-time "X days ago" parsing from seller profiles for accurate activity scoring
- **Headless browser extraction**: Optimized Playwright-based data extraction (8-10s processing time)
- **Smart categorization**: Diamond/Gold/Silver/Bronze/Ghost reliability tiers
- **Graceful degradation**: Falls back when seller data unavailable

### Technical Excellence
- **Clean Architecture**: SOLID principles with dependency injection
- **Error Boundary**: Centralized error handling with Russian user messages
- **Modular Design**: Specialized components with clear responsibilities  
- **Protocol-based**: Unified interfaces for marketplace scrapers
- **Comprehensive Testing**: 3-level testing system (unit/integration/e2e)
- **Performance Optimized**: Tiered shipping routes and browser pooling

## 🏗️ Modern Architecture

### SOLID Principles Implementation
The bot follows a clean, maintainable architecture built on SOLID principles:

- **Single Responsibility**: Each component has one clear purpose
- **Open/Closed**: Easy to extend with new marketplaces via ScraperProtocol
- **Liskov Substitution**: Interchangeable scraper implementations
- **Interface Segregation**: Focused protocols for specific functionality
- **Dependency Inversion**: Services depend on abstractions, not concrete implementations

### Core Components

```
app/
├── core/                   # Infrastructure layer
│   ├── container.py       # Dependency injection container
│   ├── service_locator.py # Global service access
│   └── interfaces.py      # Service contracts/protocols
├── bot/                   # Presentation layer
│   ├── handlers.py        # Clean Telegram handlers (150 lines vs 789)
│   ├── url_processor.py   # URL detection and validation
│   ├── scraping_orchestrator.py  # Concurrent scraping coordination
│   ├── response_formatter.py     # User message formatting
│   ├── analytics_tracker.py      # Usage analytics
│   └── error_boundary.py  # Centralized error handling
├── scrapers/              # Data access layer
│   ├── base.py           # ScraperProtocol interface
│   ├── ebay_scraper.py   # eBay implementation
│   ├── grailed_scraper.py # Grailed implementation
│   └── headless.py       # Playwright browser automation
├── services/             # Business logic layer
│   ├── currency.py       # Exchange rate management
│   ├── shipping.py       # Cost calculation
│   ├── reliability.py    # Seller scoring
│   ├── customs.py        # Duty calculation
│   └── analytics.py      # Data collection
└── models.py            # Data models and validation
```

### Key Architectural Improvements
- **God Object eliminated**: 789-line handlers.py refactored into 5 focused components
- **Dependency Injection**: Automatic resolution of service dependencies
- **Error Boundary**: Comprehensive error classification and user-friendly messaging
- **Protocol-based Design**: Easy extensibility for new marketplaces
- **Service Locator**: Centralized service management and lifecycle

## 📊 Seller Reliability System

### Scoring Algorithm (100 Points Total)

**Activity Score (0-30 points)**: Days since last listing update
- Today/Yesterday: 30 points - Maximum activity score
- 2-7 days: 24 points - Recent activity
- 8-30 days: 12 points - Moderate activity
- >30 days: 0 points - Triggers Ghost category

**Rating Score (0-35 points)**: Average seller rating (0.0-5.0)
- 4.8-5.0: 35 points - Excellent rating
- 4.5-4.7: 28 points - Very good rating
- 4.0-4.4: 21 points - Good rating
- 3.5-3.9: 14 points - Average rating
- 3.0-3.4: 7 points - Below average
- <3.0: 0 points - Poor rating

**Review Volume (0-25 points)**: Transaction history depth
- 500+ reviews: 25 points - Very established
- 100-499: 20 points - Well-established
- 50-99: 15 points - Moderately experienced
- 20-49: 10 points - Some experience
- 10-19: 5 points - Limited experience
- <10: 0 points - New/inactive seller

**Trust Badge (0-10 points)**: Grailed verification status
- Trusted Badge: 10 points - Platform-verified seller
- No Badge: 0 points - Standard account

### Reliability Categories
- **💎 Diamond (85-100)**: Top-tier seller - safe to purchase
- **🥇 Gold (70-84)**: High reliability - good track record
- **🥈 Silver (55-69)**: Normal reliability - standard marketplace risk
- **🥉 Bronze (40-54)**: Increased risk - exercise caution
- **👻 Ghost (<40 or >30 days inactive)**: Low reliability - significant concerns
- **ℹ️ No Data**: Information unavailable due to technical limitations

### Technical Implementation
- **Optimized Extraction**: 2.3x performance improvement (8-10s vs 20s)
- **Human-like Behavior**: Stealth browsing patterns to avoid detection
- **Dynamic Content Loading**: Smart scrolling and AJAX waiting
- **Browser Reuse**: Global instance for faster subsequent requests
- **Activity Parsing**: Real-time extraction of "5 days ago" patterns

## 💰 Pricing & Shipping

### Commission Structure
- **Orders < $150**: Fixed $15 commission
- **Orders ≥ $150**: 10% of (item price + US shipping)
- **Calculation Base**: Item price + US shipping costs

### Russian Customs Duty (December 2025)
- **Threshold**: 200 EUR for personal imports
- **Rate**: 15% of amount exceeding threshold
- **Currency**: Real-time EUR/USD conversion via CBR API
- **Example**: $270 order (~240€) → 15% × (240€ - 200€) = ~$6.75 duty

### Tiered Shipping System (Updated December 2025)
Dynamic routing based on order value (item price + US shipping):

**Route Selection:**
- **< $200**: Europe route (30.86$/kg) + $3 handling for light items
- **≥ $200**: Turkey route (35.27$/kg) + enhanced logistics
- **≥ $1000**: Kazakhstan route (41.89$/kg) + premium shipping

**Weight Threshold:**
- **≤ 1.36kg (3 lbs)**: $3 handling fee
- **> 1.36kg (3 lbs)**: $5 handling fee

**Example Calculations:**
```
$150 order, 0.6kg: max($13.99, 30.86 × 0.6) + $3 = $21.52
$250 order, 0.6kg: max($13.99, 35.27 × 0.6) + $3 = $24.16  
$1200 order, 0.6kg: max($13.99, 41.89 × 0.6) + $3 = $28.13
```

## 🛠️ Installation & Development

### Prerequisites
- Python 3.11+
- Telegram Bot Token
- Playwright browser binaries
- Railway account (for deployment)

### Local Development

```bash
# Clone and setup
git clone <repository-url>
cd price-gh-bot
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt
pip install -r requirements-dev.txt  # Development tools

# Install browser binaries
playwright install chromium

# Configure environment
export BOT_TOKEN="your_telegram_bot_token"
export ADMIN_CHAT_ID="your_telegram_user_id"
export ENABLE_HEADLESS_BROWSER="true"

# Run locally
python -m app.main
```

### Environment Variables
- `BOT_TOKEN`: Required Telegram bot token
- `ADMIN_CHAT_ID`: Required admin user ID for error notifications
- `PORT`: Server port (defaults to 8000)
- `RAILWAY_PUBLIC_DOMAIN`: Public domain for webhook mode
- `ENABLE_HEADLESS_BROWSER`: Enable/disable headless browser (defaults to "true")

### Development Commands (see CLAUDE.md)

```bash
# Code quality
ruff check app/ tests/          # Linting
mypy app/                      # Type checking
pydocstyle app/               # Docstring validation

# Testing (3-level system)
BOT_TOKEN=your_token pytest tests_new/unit/ -v     # Fast unit tests
BOT_TOKEN=your_token pytest tests_new/integration/ -v  # Integration tests
BOT_TOKEN=your_token pytest tests_new/e2e/ -v     # End-to-end tests
make test-all                 # Full test suite

# Documentation
mkdocs serve                  # Development server
mkdocs build                  # Build static docs

# Pre-commit quality checks
pre-commit run --all-files
```

## 🧪 Comprehensive Testing System

**📖 Complete Testing Documentation**: [docs/TESTING.md](docs/TESTING.md)

### Test Architecture
- **Unit Tests** (`tests_new/unit/`): Fast isolated business logic tests
- **Integration Tests** (`tests_new/integration/`): Component interaction with mocks
- **E2E Tests** (`tests_new/e2e/`): Full workflow with real external services

### Key Features
- **Contract Testing**: Validates business requirements
- **Auto-updating Test Data**: Syncs with external services
- **CI/CD Integration**: GitHub Actions pipeline
- **Docker Isolation**: Containerized testing environment
- **Performance Monitoring**: Benchmarks and coverage
- **Pre-commit Hooks**: Automated quality checks

### Quick Test Commands
```bash
# During development
make test-unit

# Full validation
make test-all

# Docker isolated
docker-compose -f docker-compose.test.yml up test-all

# Update test data
python tests_new/utils/data_updater.py
```

## 🚀 Deployment

### Railway Deployment (Recommended)
1. Connect GitHub repository to Railway
2. Set environment variables in Railway dashboard
3. Deploy using provided `Dockerfile` and `railway.toml`

The bot automatically:
- Installs Playwright and Chromium during build
- Switches between webhook (production) and polling (development) modes
- Initializes dependency injection container on startup

### Docker Deployment
```bash
# Build image
docker build -t price-gh-bot .

# Run container
docker run -e BOT_TOKEN="your_token" -e ADMIN_CHAT_ID="your_id" price-gh-bot

# Docker Compose
docker-compose up -d
```

## 📊 Analytics & Monitoring

### Built-in Analytics
- **Usage tracking**: Command usage, URL processing, success rates
- **Error monitoring**: Comprehensive error classification and admin notifications
- **Performance metrics**: Processing times, platform success rates
- **User analytics**: Activity patterns, platform preferences

### Admin Commands
- `/analytics_daily` - Daily usage statistics
- `/analytics_week` - Weekly analytics summary
- `/analytics_user <user_id>` - User-specific metrics
- `/analytics_errors [days]` - Error analysis
- `/analytics_export [days]` - CSV data export
- `/analytics_download_db` - SQLite database download

### Error Boundary System
- **Smart Classification**: 9 error categories with automatic detection
- **User-friendly Messages**: Russian error messages with actionable advice
- **Admin Notifications**: Rate-limited alerts for critical issues
- **Context Preservation**: Detailed error context for debugging

## 💡 Examples

### Price Calculation (Above Customs Threshold)
```
📦 Chrome Hearts Cemetery Cross Ring Size 7

💰 Расчёт стоимости

Товар: $250
Доставка в США: $20
Комиссия: $27.00 (10% от товара+доставка США)
──────────────────
Промежуточный итог: $297.00

Пошлина РФ: $6.23 (15% с превышения 200€)
Доставка в РФ: $25
──────────────────
Дополнительные расходы: $31.23

Итого к оплате: $328.23
В рублях: ₽27,088.82

Продавец: 💎 Diamond (95/100)
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

### Error Handling Example
```
⏱️ Превышено время ожидания соединения.

💡 Попробуйте повторить запрос через несколько минут.
```

## 🤝 Contributing

1. **Fork the repository**
2. **Create feature branch**: `git checkout -b feature/amazing-feature`
3. **Follow architecture**: Use dependency injection and SOLID principles
4. **Add tests**: Maintain comprehensive test coverage
5. **Update documentation**: Keep all docs current
6. **Run quality checks**: `pre-commit run --all-files`
7. **Submit pull request**: Include description of changes

### Development Guidelines
- Follow SOLID principles and clean architecture patterns
- Use dependency injection for all services
- Add comprehensive error handling with Error Boundary
- Write tests at appropriate levels (unit/integration/e2e)
- Document all public APIs with Google-style docstrings
- Keep Russian user messages simple and helpful

## 📚 Documentation

- **[CLAUDE.md](CLAUDE.md)**: Development commands and internal architecture
- **[docs/TESTING.md](docs/TESTING.md)**: Comprehensive testing guide
- **[docs/PROJECT_ANALYSIS.md](docs/PROJECT_ANALYSIS.md)**: Architecture analysis and improvements
- **[docs/ANALYTICS.md](docs/ANALYTICS.md)**: Analytics system documentation
- **API Reference**: Auto-generated from docstrings (run `mkdocs serve`)

## 🏆 Architecture Achievements

This project represents a complete transformation from monolithic code to modern, scalable architecture:

✅ **God Object Elimination**: 789-line handlers.py → 5 focused components (150 lines each)
✅ **SOLID Principles**: Complete adherence to clean architecture patterns
✅ **Dependency Injection**: Automatic service resolution and lifecycle management
✅ **Error Boundary**: Centralized error handling with user-friendly messaging
✅ **Protocol-based Design**: Easy extensibility for new marketplaces
✅ **Comprehensive Testing**: 3-level testing pyramid with CI/CD integration

The codebase now serves as an exemplar of modern Python application architecture with clean separation of concerns, testability, and maintainability.

---

*For detailed development guidance, deployment instructions, and internal architecture documentation, see [CLAUDE.md](CLAUDE.md)*