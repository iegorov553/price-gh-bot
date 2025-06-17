# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## ⚠️ CRITICAL ARCHITECTURE NOTES

This project has undergone **complete architectural modernization** implementing SOLID principles, dependency injection, and clean architecture patterns. Always maintain these standards:

### 🏗️ Architecture Principles
- **SOLID Compliance**: Single Responsibility, Open/Closed, Liskov Substitution, Interface Segregation, Dependency Inversion
- **Dependency Injection**: All services must use DI container (`app/core/container.py`)
- **Error Boundary**: Centralized error handling (`app/bot/error_boundary.py`)
- **Protocol-based Design**: Use interfaces from `app/core/interfaces.py`
- **Clean Separation**: Presentation → Business Logic → Data Access layers

### 🚫 Architectural Violations to Avoid
- **God Objects**: Keep components focused (150 lines max for handlers)
- **Direct Instantiation**: Use service locator or DI container
- **Tight Coupling**: Depend on abstractions, not concrete implementations
- **Mixed Concerns**: Separate presentation, business logic, and data access
- **Global State**: Use dependency injection instead

### ✅ Current Architecture (Post-Refactoring)
```
app/
├── core/                   # Infrastructure (DI, interfaces)
├── bot/                   # Presentation (handlers, formatters) 
├── scrapers/              # Data Access (marketplace APIs)
├── services/              # Business Logic (pricing, reliability)
└── models.py             # Domain Models
```

## Development Commands

### Core Commands
- **Install dependencies**: `pip install -r requirements.txt`
- **Install dev dependencies**: `pip install -r requirements-dev.txt`
- **Run bot locally**: `python -m app.main` (uses dependency injection initialization)
- **Lint code**: `ruff check app/ tests/`
- **Type check**: `mypy app/`
- **Check docstrings**: `pydocstyle app/`
- **Build docs**: `mkdocs build`
- **Serve docs locally**: `mkdocs serve`
- **Pre-commit hooks**: `pre-commit run --all-files`
- **Deploy to Railway**: Automatically handled by `railway.toml` config with DI container setup

### Modern Testing System

**📖 Complete Testing Documentation**: [docs/TESTING.md](docs/TESTING.md)

#### Quick Test Commands
- **Unit tests (fast)**: `BOT_TOKEN=your_token pytest tests_new/unit/ -v`
- **Integration tests**: `BOT_TOKEN=your_token pytest tests_new/integration/ -v`
- **E2E tests (slow)**: `BOT_TOKEN=your_token pytest tests_new/e2e/ -v` (with real APIs)
- **All tests**: `make test-all` (requires Makefile.test setup)
- **Docker tests**: `docker-compose -f docker-compose.test.yml up test-all`
- **Legacy tests**: `pytest tests/ -v` (deprecated, use tests_new/ instead)

#### Test Architecture
- **Unit Tests** (`tests_new/unit/`): Fast isolated business logic tests
- **Integration Tests** (`tests_new/integration/`): Component interaction with mocks
- **E2E Tests** (`tests_new/e2e/`): Full workflow with real external services

#### Key Features
- **Contract Testing**: Validates business requirements against defined interfaces
- **Auto-updating Test Data**: Synchronizes with real external services
- **CI/CD Integration**: GitHub Actions pipeline with comprehensive quality checks
- **Docker Isolation**: Containerized testing environment for consistency
- **Performance Monitoring**: Benchmarks and coverage reporting
- **Pre-commit Hooks**: Automated quality checks before commits

#### Test Data Management
- **Automated Updates**: `python tests_new/utils/data_updater.py`
- **URL Verification**: `make test-verify`
- **Custom Fixtures**: Located in `tests_new/fixtures/`

## Modern Architecture Overview (Post-SOLID Refactoring)

This Telegram bot implements **clean architecture** with **SOLID principles** and **dependency injection**:

### 🏗️ Layered Architecture
- **Infrastructure Layer** (`app/core/`): DI container, service locator, interfaces
- **Presentation Layer** (`app/bot/`): Telegram handlers, formatters, error boundary
- **Business Logic Layer** (`app/services/`): Domain services (currency, shipping, reliability)
- **Data Access Layer** (`app/scrapers/`): Marketplace integrations with unified protocols
- **Domain Models** (`app/models.py`): Pydantic models with validation

### 🔄 Dependency Flow
```
Telegram Update → Handlers → Services → Scrapers → External APIs
                     ↓
              DI Container resolves all dependencies
                     ↓
            Error Boundary handles all exceptions
```

### 🎯 Key Components
- **Service Locator** (`app/core/service_locator.py`): Central service registry
- **DI Container** (`app/core/container.py`): Automatic dependency resolution
- **Error Boundary** (`app/bot/error_boundary.py`): Centralized error handling
- **ScraperProtocol** (`app/scrapers/base.py`): Unified marketplace interface
- **Clean Handlers** (`app/bot/handlers.py`): 150 lines vs original 789

### 🚀 Operational Modes
- **Webhook mode**: Production deployment with Railway webhooks
- **Polling mode**: Local development with long-polling
- **Service initialization**: Automatic DI container configuration on startup
- **Graceful shutdown**: Proper resource cleanup and service disposal

### Modern Component Architecture (Post-Refactoring)

#### 🏗️ Infrastructure Layer (`app/core/`)
- **Dependency Injection Container** (`container.py`): Automatic service resolution with lifecycle management
- **Service Locator** (`service_locator.py`): Global service registry with validation
- **Interface Protocols** (`interfaces.py`): Service contracts for loose coupling

#### 🎯 Presentation Layer (`app/bot/`) 
- **Clean Handlers** (`handlers.py`): Focused Telegram message handling (150 lines)
- **URL Processor** (`url_processor.py`): URL detection, validation, and categorization
- **Scraping Orchestrator** (`scraping_orchestrator.py`): Concurrent marketplace coordination
- **Response Formatter** (`response_formatter.py`): Russian user message formatting
- **Analytics Tracker** (`analytics_tracker.py`): Usage and performance tracking
- **Error Boundary** (`error_boundary.py`): Centralized error handling with classification
- **Messages** (`messages.py`): Localized Russian text with minimal emoji usage

#### 🔧 Business Logic Layer (`app/services/`)
- **Currency Service** (`currency.py`): Exchange rate management with CBR API integration
- **Shipping Service** (`shipping.py`): Tiered Shopfans cost calculation (Europe/Turkey/Kazakhstan routes)
- **Reliability Service** (`reliability.py`): Grailed seller scoring (100-point Diamond/Gold/Silver/Bronze system)
- **Customs Service** (`customs.py`): Russian duty calculation (15% over 200 EUR threshold)
- **Analytics Service** (`analytics.py`): SQLite data collection and reporting

#### 📡 Data Access Layer (`app/scrapers/`)
- **ScraperProtocol** (`base.py`): Unified marketplace interface
- **eBay Scraper** (`ebay_scraper.py`): eBay listing implementation
- **Grailed Scraper** (`grailed_scraper.py`): Grailed listing + seller analysis
- **Headless Browser** (`headless.py`): Playwright automation for React SPA extraction
- **Scraper Registry**: Automatic marketplace detection and routing

#### 🔄 Key Integration Points
- **Next.js Support**: Prioritizes `__NEXT_DATA__` extraction with HTML fallback
- **Dual Strategy**: HTTP for listings (fast), headless browser for profiles (comprehensive)
- **Concurrent Processing**: `asyncio.gather()` for parallel URL processing
- **Error Recovery**: Graceful degradation with user-friendly Russian messages
- **Commission Logic**: $15 fixed (<$150) or 10% (≥$150) including US shipping
- **Russian Customs**: Automatic 15% duty on imports exceeding 200 EUR

### Environment Variables

#### Required Variables
- `BOT_TOKEN`: Telegram bot token (required)
- `ADMIN_CHAT_ID`: Admin user ID for error notifications (required)

#### Optional Variables  
- `PORT`: Server port (defaults to 8000)
- `RAILWAY_PUBLIC_DOMAIN` or `RAILWAY_URL`: Webhook mode detection
- `ENABLE_HEADLESS_BROWSER`: Enable Playwright browser (defaults to "true")

#### Production Configuration
- All services automatically registered via Service Locator
- Dependency injection container initialized on startup
- Error boundary configured for admin notifications
- Analytics database created if not exists

### Currency Exchange Rate Sources

The bot uses the Central Bank of Russia (CBR) official XML API for all currency conversions:

**USD to RUB (for final price conversion):**
- **Endpoint**: `https://www.cbr.ru/scripts/XML_daily.asp`
- **Format**: XML with daily official rates
- **Processing**: Parses XML using `xml.etree.ElementTree`, finds USD entry, applies 5% markup
- **Markup justification**: 5% covers currency exchange fees and market volatility

**EUR to USD (for customs duty threshold):**
- **Endpoint**: Same CBR XML API
- **Calculation**: Cross-rate EUR/USD = EUR/RUB ÷ USD/RUB
- **Purpose**: Convert 200 EUR customs threshold to USD for duty calculation
- **No markup**: Cross-rate used as-is for threshold conversion

**Common features:**
- **Error handling**: No fallback sources - if CBR API is unavailable, affected features are disabled and admin is notified
- **Admin notifications**: Telegram message sent to admin (ID: 26917201) when CBR API fails
- **Caching**: Exchange rates cached for 1 hour for performance optimization

### Grailed Seller Reliability System

The bot implements a comprehensive seller evaluation system for Grailed with sophisticated scoring algorithms:

#### Scoring Criteria (Total: 100 points)

**Activity Score (0-30 points)**: Based on days since last listing update
- **Today (0 days)**: 30 points - Maximum activity score
- **Yesterday (1 day)**: 30 points - Still considered very active
- **2-7 days ago**: 24 points - Recent activity, good score
- **8-30 days ago**: 12 points - Moderate activity, some concern
- **>30 days ago**: 0 points - Inactive seller, triggers Ghost category

**Rating Score (0-35 points)**: Based on average seller rating (0.00-5.00)
- **4.8-5.0 stars**: 35 points - Excellent rating, maximum score
- **4.5-4.7 stars**: 28 points - Very good rating
- **4.0-4.4 stars**: 21 points - Good rating, acceptable
- **3.5-3.9 stars**: 14 points - Average rating, some risk
- **3.0-3.4 stars**: 7 points - Below average, higher risk
- **<3.0 stars**: 0 points - Poor rating, significant risk

**Review Volume Score (0-25 points)**: Based on number of completed transactions
- **500+ reviews**: 25 points - Very established seller
- **100-499 reviews**: 20 points - Well-established seller
- **50-99 reviews**: 15 points - Moderately experienced
- **20-49 reviews**: 10 points - Some experience
- **10-19 reviews**: 5 points - Limited experience
- **<10 reviews**: 0 points - New or inactive seller

**Badge Score (0-10 points)**: Trusted Seller badge status
- **Trusted Badge Present**: 10 points - Grailed-verified seller
- **No Badge**: 0 points - Standard seller account

#### Implementation Details
- **Profile fetching**: Functions in `app/scrapers/grailed.py` get seller profile URL from listing page
- **Data extraction**: **Headless browser only** - static HTML parsing doesn't work due to React SPA architecture
- **Playwright integration**: Uses headless Chromium to execute JavaScript and access dynamically loaded content
- **Evaluation**: `app/services/reliability.py` applies business rules to calculate scores and categories
- **Response formatting**: Creates user-friendly Russian messages via `app/bot/messages.py`
- **Configuration**: Can be enabled/disabled via `ENABLE_HEADLESS_BROWSER` environment variable

#### Categories and Thresholds

**💎 Diamond (85-100 points)**: Top-tier seller
- Characteristics: Excellent rating (4.8+), high transaction volume (100+), recent activity, trusted badge
- Risk Level: Minimal - Safe to purchase from
- Typical Profile: Established seller with consistent positive feedback

**🥇 Gold (70-84 points)**: High reliability
- Characteristics: Good rating (4.5+), moderate transaction volume (50+), regular activity
- Risk Level: Low - Reliable seller with good track record
- Typical Profile: Active seller with solid reputation

**🥈 Silver (55-69 points)**: Normal reliability
- Characteristics: Acceptable rating (4.0+), some transaction history (20+), occasional activity
- Risk Level: Moderate - Standard marketplace risk
- Typical Profile: Average seller, proceed with normal caution

**🥉 Bronze (40-54 points)**: Increased risk
- Characteristics: Below-average metrics, limited history, infrequent activity
- Risk Level: Higher - Exercise additional caution
- Typical Profile: Newer or less active seller, verify details carefully

**👻 Ghost (<40 points OR >30 days inactive)**: Low reliability
- Characteristics: Poor metrics OR inactive for over 30 days
- Risk Level: High - Significant concerns about seller
- Typical Profile: Inactive or problematic seller, consider alternatives
- Special Rule: Any seller inactive >30 days automatically becomes Ghost regardless of other scores

**ℹ️ No Data**: When seller information is unavailable
- Cause: Grailed's React SPA architecture or headless browser disabled
- Risk Level: Unknown - Unable to assess seller reliability
- Recommendation: Use listing URLs instead of profile URLs for better data extraction

#### User Interface
- **Listing analysis**: Seller reliability shown for buyable Grailed items (when data available)
- **Direct profile analysis**: **Limited functionality** - Users informed about technical limitations and encouraged to share listing URLs instead
- **Russian language**: All user messages in simple, neutral Russian with honest explanations of constraints

### Modern Bot Behavior (Clean Architecture)

#### URL Processing Pipeline
1. **URL Processor**: Extracts, validates, and categorizes URLs with security filtering
2. **Scraping Orchestrator**: Coordinates marketplace scraping with concurrent processing
3. **Response Formatter**: Creates structured Russian messages with proper formatting
4. **Error Boundary**: Handles all exceptions with user-friendly error messages

#### Processing Flow
```
User Message → URL Processor → Scraping Orchestrator → Response Formatter → User
                    ↓                ↓                      ↓
              Security Filter   ScraperProtocol      Error Boundary
```

#### Message Types & Formatting
- **Buyable Items**: Product title + structured price breakdown + seller analysis
- **Offer-only Items**: Contact seller message with reference price
- **Seller Profiles**: Comprehensive Diamond/Gold/Silver/Bronze analysis
- **Errors**: Classified error messages with actionable user guidance

#### Enhanced UX (December 2025)
- **Structured Pricing**: Two-tier format (subtotal → additional costs → final total)
- **Item Title Links**: Clickable product names linking to original listings
- **Clean Design**: Minimal emoji usage, clear visual hierarchy
- **Loading States**: Progress indicators for 8-10 second processing times
- **Customs Integration**: Automatic duty display when applicable
- **Performance Transparency**: Users see processing status during analysis

### Enhanced Price Display Format (Updated December 2025)
**Implemented structured multi-line format with Russian customs duty integration and item title display:**

**Current format with item title and customs duty:**
```
📦 [Chrome Hearts Cemetery Cross Ring Size 7](https://www.grailed.com/listings/59397754-chrome-hearts-chrome-hearts-cemetery-cross-ring-sz-7)

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
```

**Format for items below customs threshold:**
```
💰 Расчёт стоимости

Товар: $100
Доставка в США: $15
Комиссия: $15.0 (фикс. сумма)
──────────────────
Промежуточный итог: $130.00

Доставка в РФ: $20
──────────────────
Дополнительные расходы: $20.00

Итого к оплате: $150.00
В рублях: ₽12,379.50
```

**Implementation details:**
- **Item title display**: Shows product name with clickable hyperlink to original listing (when available)
- **Two-tier structure**: Intermediate subtotal → Additional costs → Final total
- **Customs duty calculation**: Automatically applied when item + US shipping > 200€
- **Commission clarity**: Shows calculation base ("10% от товара+доставка США")
- **Visual separation**: Clear separators between calculation stages
- **Smart display**: Customs duty line only appears when applicable
- **Multi-scenario support**: Handles all combinations of US/RU shipping and customs duty
- **Backward compatibility**: Title display is optional - falls back gracefully when title unavailable

### Shopfans Shipping Estimation (Updated December 2025)

⚠️ **IMPORTANT**: Shipping weight estimates in `app/services/shipping.py` should be reviewed and updated quarterly based on actual shipment tracking data to maintain accuracy.

**Tiered Shipping System Based on Order Value:**

The shipping estimation system now uses dynamic pricing based on total order value (item price + US shipping):

**Route Selection:**
- **< $200**: Europe route (30.86$/kg) - Standard shipping via European logistics
- **≥ $200**: Turkey route (35.27$/kg) - Enhanced routing via Turkey for medium-value orders  
- **≥ $1000**: Kazakhstan route (41.89$/kg) - Premium logistics via Kazakhstan for high-value orders

**Handling Fee Structure:**
- **≤ 1.36kg (3 pounds)**: $3 handling fee - Light items warehouse processing
- **> 1.36kg (3 pounds)**: $5 handling fee - Heavy items additional handling

**Calculation Formula:**
```
shipping_cost = max($13.99, route_rate × weight_kg) + handling_fee
```

**Implementation Details:**
- Uses regex pattern matching on item titles to determine product categories
- Maps categories to estimated weights in kilograms from `app/config/shipping_table.yml`
- Route selection automatically determined by total order value (item + US shipping)
- Weight threshold updated from 0.45kg to 1.36kg (3 pounds) for more accurate handling fees
- Default weight: 0.60kg for unmatched items

**Example Calculations:**
- $150 order, 0.6kg: max($13.99, 30.86 × 0.6) + $3 = $21.52
- $250 order, 0.6kg: max($13.99, 35.27 × 0.6) + $3 = $24.16  
- $1200 order, 0.6kg: max($13.99, 41.89 × 0.6) + $3 = $28.13

## Web Scraping Guidelines

**CRITICAL**: Always analyze target website structure before implementing scraping logic:

1. **Page Structure Analysis**: Before writing any scraping code, use WebFetch tool to analyze the actual HTML/JSON structure of target pages
2. **Multiple Pattern Support**: Implement multiple regex patterns and fallback strategies since websites frequently change their data formats
3. **Dynamic Content**: Modern sites (like Grailed) use React SPA with dynamic JSON loading - account for various data formats and field names
4. **Robust Extraction**: Use multiple extraction strategies:
   - JSON parsing with various field name patterns
   - HTML element parsing as fallback
   - Comprehensive error handling and logging
5. **Pattern Evolution**: Websites evolve - implement flexible patterns that can handle format changes without breaking

### Grailed.com Specific Knowledge (Critical)

**UPDATED June 2025**: Grailed now uses Next.js architecture with dual parsing strategies for listings and profiles.

#### Modern Grailed Architecture (Next.js)

**Listing Pages**: Now use Next.js with data embedded in `__NEXT_DATA__` script tags
- **Primary extraction method**: Parse JSON from `<script id="__NEXT_DATA__">` 
- **Data location**: `props.pageProps.listing` contains all listing information
- **Available data**: price, title, shipping costs, seller info, buyability status
- **Fallback strategy**: Legacy HTML parsing for older listings

**Seller Profile Pages**: Still use React SPA requiring headless browser
- **Dynamic loading**: Seller data loaded via authenticated APIs after page render
- **Headless browser required**: Only method to extract rating, reviews, trusted badge
- **Static HTML limitation**: Profile data not available in initial HTML response

#### Profile Pages Limitations
- **Profile pages** (e.g., `grailed.com/username`) use **client-side rendering**
- Seller data (rating, reviews, trusted badge) is **NOT available in static HTML**
- Data is loaded dynamically via API calls after page load requiring authentication
- Profile pages return ~200KB of HTML but contain minimal actual content
- The HTML contains React root elements (`<div id="app">`) but no seller metrics
- **DO NOT** expect to extract seller data from profile pages without headless browser

#### What Works vs What Doesn't (Updated June 2025)

✅ **Listing Pages (Next.js + HTTP requests)**:
- **Complete item data**: price, title, shipping costs, buyability status
- **Accurate extraction**: Real-time data from `__NEXT_DATA__` JSON
- **Seller profile URLs**: Extracted for further analysis
- **Performance**: Fast HTTP-only parsing (~2-3 seconds)
- **Compatibility**: Works with both modern Next.js and legacy HTML listings

❌ **Profile Pages (Require headless browser)**:
- **Seller ratings**: Only available via headless browser JavaScript execution
- **Review counts**: Dynamic loading after page render
- **Trusted badges**: Client-side verification
- **Activity timestamps**: Requires scrolling and dynamic content loading
- **Performance cost**: ~8-10 seconds per profile analysis

#### API Endpoints Discovery (May 2025)
- `grailed.com/api/users/{username}` exists but requires authentication (401)
- Access tokens found in HTML are for analytics/tracking, not user data access
- GraphQL endpoint `/graphql` returns 404
- No public API for seller profile data

#### Recommended Approach
1. **For seller analysis**: Focus on data extraction from **listing pages**, not profile pages
2. **Profile URLs**: Use for navigation/identification only, not data extraction  
3. **Fallback handling**: Always implement graceful degradation when seller data unavailable
4. **User communication**: Clearly explain limitations to users when profile analysis fails
5. **Alternative strategy**: Suggest users share specific listing URLs for seller analysis

#### Technical Implementation Notes (Updated June 2025)

**Listing Parsing (HTTP-based)**:
- **Next.js priority**: `_parse_next_data()` extracts from `<script id="__NEXT_DATA__">`
- **Data structure**: `props.pageProps.listing` contains complete item information
- **Enhanced headers**: Browser-like headers prevent bot detection and JSON config responses
- **Legacy fallback**: Maintains compatibility with older listing formats
- **Error handling**: Content-Type validation prevents parsing JSON config as HTML

**Profile Parsing (Headless browser)**:
- **JavaScript execution**: Required for dynamic content loading
- **Scrolling mechanism**: Loads activity data by scrolling to listings
- **Stealth features**: Anti-detection measures for stable extraction
- **Resource optimization**: Selective content loading for performance

#### Headless Browser Implementation (June 2025) - OPTIMIZED SOLUTION

- **Playwright integration** implemented as the ONLY working method for seller data extraction
- **Static HTML methods removed**: All JSON parsing, regex patterns, and script extraction methods removed as they don't work with React SPA
- **Dynamic content handling**: Headless browser waits for JavaScript execution and DOM manipulation to load seller data
- **Activity timestamp extraction**: Parses "X days/weeks/months ago" text patterns from seller profile pages after scrolling to load listings
- **Resource management**: Proper browser lifecycle with async context managers
- **Performance optimization**: Optimized for speed while maintaining human-like behavior to avoid bot detection
- **Configuration**: Can be disabled via `ENABLE_HEADLESS_BROWSER=false` environment variable
- **Graceful degradation**: Falls back to "No Data" category when headless browser disabled or fails

**Performance Optimizations (June 2025)**:
- **Speed improvements**: Reduced execution time from ~20 seconds to ~8-10 seconds (2.3x faster)
- **Human-like behavior**: Balanced speed with bot detection avoidance
- **Resource blocking**: Intelligent blocking of heavy media while keeping essential CSS/JS
- **Browser reuse**: Global browser instance for repeated requests (3-5 seconds for subsequent calls)
- **Stealth features**: Hidden automation markers and realistic browser behavior
- **Random delays**: Human-like timing patterns to avoid detection

**Technical Implementation**:
- **Single extraction method**: `app/scrapers/grailed.py` now uses only headless browser via `get_grailed_seller_data_headless()`
- **Selector strategy**: Multiple CSS selectors and text patterns to find rating, reviews, and trusted badge
- **Activity extraction**: Scrolls profile page to load listings, then extracts first "X time ago" pattern for accurate last activity timestamp
- **Time conversion**: Converts relative time expressions ("5 days ago") to absolute timestamps for reliability scoring
- **Error handling**: Comprehensive logging and fallback to "No Data" category
- **Dependencies**: Requires `playwright` and `playwright install chromium`

**Performance Notes**:
- Headless browser adds ~8-10 seconds per profile analysis
- Successfully extracts data that is impossible to get via static HTML
- Accurate activity timestamps enable proper reliability scoring (was giving all sellers 30/30 points)
- Essential for accurate seller reliability analysis on Grailed
- Scrolling mechanism ensures dynamic listing content loads before extraction
- Resource-efficient with proper browser lifecycle management

**Activity Extraction Breakthrough (May 2025)**:
- **Problem solved**: Replaced hardcoded "current time" with actual seller activity extraction
- **Method**: Parse listing update text ("5 days ago", "2 months ago") from seller profile pages
- **Implementation**: Scroll page to load dynamic listings, extract first time pattern with regex
- **Validation**: Tested with DP1211 seller - correctly shows 5 days since last activity
- **Impact**: Enables accurate activity scoring in reliability system (was previously giving all sellers maximum 30/30 activity points)

#### User Interface and Experience
- **Listing analysis**: Seller reliability shown for buyable Grailed items when data available
- **Direct profile analysis**: Full seller reliability analysis using headless browser extraction
- **Loading indicators**: Immediate feedback with "⏳ Загружаем данные и производим расчёт..." messages
- **Clean UX**: Loading messages automatically deleted when results are ready
- **Performance transparency**: Users see processing status during 8-10 second analysis time
- **Clean formatting**: Minimal emoji usage for better readability
- **Russian language**: All user messages in simple, neutral Russian with honest explanations of constraints
- **Enhanced error diagnostics**: Intelligent error handling with site availability checking
  - Automatic Grailed availability check when listing scraping fails
  - Context-aware error messages distinguishing between site downtime and listing issues
  - Response time monitoring for performance diagnostics
  - Three-tier error classification: site down, site slow, or listing-specific issues
- **Error handling**: Graceful fallback to "No Data" category with clear explanations
- **Real-time updates**: Activity timestamps reflect actual seller behavior, not system time
- **Enhanced price display**: Structured multi-line format showing each cost component separately for better readability

**Lessons Learned (Updated June 2025)**:
- **Next.js architecture shift**: Grailed migrated listings to Next.js requiring new parsing strategies
- **Dual approach necessity**: Listings (HTTP + Next.js) vs Profiles (headless browser)
- **Data availability split**: Complete listing data in `__NEXT_DATA__`, seller data requires JS execution
- **Legacy compatibility**: Must maintain fallback parsing for older listing formats
- **Performance optimization**: HTTP parsing for listings (2-3s) vs headless for profiles (8-10s)
- **Bot detection evolved**: Enhanced headers prevent JSON config responses
- **Extraction accuracy**: Next.js parsing provides exact prices/shipping vs estimated defaults
- **Architecture adaptation**: Parser evolved from HTML-only to JSON-first with HTML fallback

## Code Quality and Documentation Standards

### Modern Development Tools
- **Code Quality**: `ruff` linting + `mypy` type checking + `pydocstyle` docstring validation
- **Architecture Validation**: DI container service validation on startup
- **Testing Framework**: 3-level testing pyramid (unit/integration/e2e)
- **Documentation**: Auto-generated API docs with `mkdocs` + `mkdocstrings`
- **Pre-commit Hooks**: Automated quality checks and formatting
- **Browser Automation**: Playwright for React SPA testing and scraping
- **Dependency Management**: Separate dev dependencies for testing environment

### Architecture Documentation Standards
- **Service Interfaces**: All services must implement protocols from `app/core/interfaces.py`
- **Dependency Injection**: Document all constructor dependencies with type hints
- **Error Handling**: Use Error Boundary decorators and document exception types
- **Testing Strategy**: Write tests at appropriate level (unit for business logic, integration for components, e2e for workflows)
- **API Documentation**: Google-style docstrings with Args, Returns, Raises, Examples
- **Architecture Diagrams**: Keep README and CLAUDE.md current with structural changes

### Quality Gates
1. **Type Safety**: All functions must have complete type hints
2. **Documentation**: Public APIs require comprehensive docstrings
3. **Testing**: Minimum 80% coverage for business logic
4. **Architecture**: Services must use dependency injection
5. **Error Handling**: All exceptions must go through Error Boundary
6. **Code Organization**: Follow layered architecture with clear separation

### Deployment with Modern Architecture

#### Railway Deployment (Recommended)
The bot is optimized for Railway with automatic:
- **Service Initialization**: DI container configuration on startup
- **Webhook Configuration**: Automatic mode detection (webhook vs polling)
- **Dependency Resolution**: All services validated during initialization
- **Error Monitoring**: Admin notifications for critical issues
- **Browser Setup**: Playwright Chromium installation during build

#### Configuration Files
- `railway.toml`: Build and start commands with service initialization
- `Dockerfile`: Multi-stage build with Playwright browser binaries
- `requirements.txt`: Production dependencies with DI container
- `requirements-dev.txt`: Development tools for testing and quality

#### Startup Sequence
1. **Environment Validation**: Check required variables (BOT_TOKEN, ADMIN_CHAT_ID)
2. **Service Locator Configuration**: Register all application services
3. **Container Validation**: Verify all dependencies can be resolved
4. **Error Boundary Setup**: Configure admin notifications
5. **Bot Initialization**: Register handlers with Error Boundary decorators
6. **Mode Detection**: Webhook (production) vs polling (development)
7. **Health Monitoring**: Service validation and error tracking

# important-instruction-reminders

## 🏗️ ARCHITECTURE COMPLIANCE (CRITICAL)
This project follows **SOLID principles** and **clean architecture**. ALWAYS maintain:

### ✅ Required Patterns
- **Dependency Injection**: Use `app/core/service_locator.py` for service resolution
- **Error Boundary**: Wrap all handlers with `@error_boundary.telegram_handler`
- **Protocol Interfaces**: Implement services using protocols from `app/core/interfaces.py`
- **Separation of Concerns**: Keep presentation, business logic, and data access separate
- **Single Responsibility**: Components should have one clear purpose (max 150 lines)

### ❌ Architectural Violations
- **Direct Instantiation**: Never use `ClassName()` - use dependency injection
- **God Objects**: Never create large classes with multiple responsibilities  
- **Tight Coupling**: Never import concrete implementations - use interfaces
- **Mixed Concerns**: Never put business logic in handlers or data access in services
- **Global State**: Never use module-level variables - use DI container

### 📋 Standard Instructions
Do what has been asked; nothing more, nothing less.
NEVER create files unless they're absolutely necessary for achieving your goal.
ALWAYS prefer editing an existing file to creating a new one.
NEVER proactively create documentation files (*.md) or README files. Only create documentation files if explicitly requested by the User.

### 🔧 When Modifying Code
1. Check if component uses dependency injection correctly
2. Ensure Error Boundary decorators are present
3. Verify protocol compliance for services
4. Maintain clean architecture layers
5. Add/update type hints and docstrings
6. Update tests at appropriate level