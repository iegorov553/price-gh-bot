# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Development Commands

- **Install dependencies**: `pip install -r requirements.txt`
- **Run bot locally**: `python app/main.py`
- **Run tests**: `pytest tests/`
- **Lint code**: `ruff check app/ tests/`
- **Type check**: `mypy app/`
- **Check docstrings**: `pydocstyle app/`
- **Build docs**: `mkdocs build`
- **Serve docs locally**: `mkdocs serve`
- **Pre-commit hooks**: `pre-commit run --all-files`
- **Deploy to Railway**: Automatically handled by `railway.toml` config

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

**IMPORTANT**: Grailed uses a React-based Single Page Application (SPA) architecture that heavily impacts scraping strategies:

#### Profile Pages Limitations
- **Profile pages** (e.g., `grailed.com/username`) use **client-side rendering**
- Seller data (rating, reviews, trusted badge) is **NOT available in static HTML**
- Data is loaded dynamically via API calls after page load requiring authentication
- Profile pages return ~200KB of HTML but contain minimal actual content
- The HTML contains React root elements (`<div id="app">`) but no seller metrics
- **DO NOT** expect to extract seller data from profile pages without headless browser

#### What Works vs What Doesn't
✅ **Available from listing pages**:
- Item price, shipping cost, buyability status
- Basic seller profile URL extraction
- Some seller data embedded in listing JSON (window.__PRELOADED_STATE__)

❌ **NOT available from profile pages**:
- Seller ratings, review counts, trusted badges
- Activity data, last update information
- Any meaningful seller metrics in static HTML

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

#### Technical Implementation Notes
- Enhanced headers improve success rate but don't solve fundamental SPA limitations
- JSON parsing patterns work on listing pages but not profile pages
- `window.__PRELOADED_STATE__` contains listing data, not profile data
- Multiple regex patterns help with listing page data but won't find profile data that isn't there

#### Debugging History & Lessons Learned (May 2025)
**Investigation conducted**: Exhaustive analysis of Grailed profile page structure including:
- WebFetch analysis of profile URLs
- Manual inspection of ~200KB HTML responses
- Script tag analysis for JSON data (found only category configuration data)
- API endpoint testing (discovered /api/users/{username} requires auth)
- Access token extraction and testing (tokens are for analytics, not user data)
- Multiple header combinations and user agent testing
- React root element inspection (confirmed SPA architecture)

**Key findings**:
- Profile pages return substantial HTML (~200KB) but it's mostly framework code
- No seller data exists in static HTML - all loaded post-render via authenticated APIs
- React app renders seller data client-side after page load
- `Thousandfacesstore` and `grailhunter` profiles confirmed to have zero extractable data in static content

**Attempted solutions that failed**:
- Enhanced regex patterns for seller data
- Deep JSON parsing of all script tags
- API endpoint discovery and token-based authentication
- Multiple user agent and header combinations

**Working solution implemented**:
- Enhanced `analyze_seller_profile()` with comprehensive search patterns
- Graceful degradation to "No Data" category when extraction fails
- Clear user communication about technical limitations
- Focus redirected to listing page data extraction where seller info is available

**Headless Browser Implementation (May 2025) - FINAL SOLUTION**:
- **Playwright integration** implemented as the ONLY working method for seller data extraction
- **Static HTML methods removed**: All JSON parsing, regex patterns, and script extraction methods removed as they don't work with React SPA
- **Dynamic content handling**: Headless browser waits for JavaScript execution and DOM manipulation to load seller data
- **Activity timestamp extraction**: Parses "X days/weeks/months ago" text patterns from seller profile pages after scrolling to load listings
- **Resource management**: Proper browser lifecycle with async context managers
- **Performance optimization**: Minimal overhead with chromium headless mode in production
- **Configuration**: Can be disabled via `ENABLE_HEADLESS_BROWSER=false` environment variable
- **Graceful degradation**: Falls back to "No Data" category when headless browser disabled or fails

**Technical Implementation**:
- **Single extraction method**: `app/scrapers/grailed.py` now uses only headless browser via `get_grailed_seller_data_headless()`
- **Selector strategy**: Multiple CSS selectors and text patterns to find rating, reviews, and trusted badge
- **Activity extraction**: Scrolls profile page to load listings, then extracts first "X time ago" pattern for accurate last activity timestamp
- **Time conversion**: Converts relative time expressions ("5 days ago") to absolute timestamps for reliability scoring
- **Error handling**: Comprehensive logging and fallback to "No Data" category
- **Dependencies**: Requires `playwright` and `playwright install chromium`

**Performance Notes**:
- Headless browser adds ~20 seconds per profile analysis
- Successfully extracts data that is impossible to get via static HTML
- Accurate activity timestamps enable proper reliability scoring
- Essential for accurate seller reliability analysis on Grailed

**Activity Extraction Breakthrough (May 2025)**:
- **Problem solved**: Replaced hardcoded "current time" with actual seller activity extraction
- **Method**: Parse listing update text ("5 days ago", "2 months ago") from seller profile pages
- **Implementation**: Scroll page to load dynamic listings, extract first time pattern with regex
- **Validation**: Tested with DP1211 seller - correctly shows 5 days since last activity
- **Impact**: Enables accurate activity scoring in reliability system (was previously giving all sellers maximum 30/30 activity points)

**Lessons Learned (May 2025)**:
- **React SPA architecture**: Makes static HTML parsing completely ineffective
- **Dynamic data loading**: Seller data loaded via authenticated APIs after page render
- **Listing activity**: Must scroll profile pages to trigger listing load, then parse human-readable time text
- **Multiple failed approaches**: JSON parsing, regex patterns, API attempts all failed for timestamps
- **Headless browser**: Only reliable method for extracting seller data and activity from Grailed profiles

## Architecture Overview

This Telegram bot uses a modular architecture with the following structure:
- **Entry point**: `app/main.py` - Application startup and configuration
- **Bot handlers**: `app/bot/handlers.py` - Message processing and URL handling  
- **Scrapers**: `app/scrapers/` - eBay and Grailed price/data extraction
- **Services**: `app/services/` - Currency, shipping, and reliability calculations
- **Models**: `app/models.py` - Pydantic data models for type safety
- **Configuration**: `app/config.py` - Settings and environment management
- **Messages**: `app/bot/messages.py` - Russian localized user messages

The bot scrapes prices from eBay and Grailed listings, adds US shipping costs, estimates Russia delivery costs via Shopfans Lite, applies tiered commission structure, converts to RUB, and provides comprehensive Grailed seller reliability analysis. It operates in two modes:
- **Webhook mode**: When deployed with a public domain (Railway), uses webhooks for production
- **Polling mode**: Falls back to long-polling when no public domain is available (local development)

### Core Components

- **Messages module**: `app/bot/messages.py` containing all user-facing text in Russian for easy localization and editing, with clean formatting and minimal emoji usage
- **Price scrapers**: Functions in `app/scrapers/` that extract item price, US shipping cost, buyability status, and seller data from eBay and Grailed listings
- **Buyability detection**: Grailed scraper analyzes JSON data to determine if items have fixed buy-now pricing or are offer-only
- **Seller analysis**: Comprehensive system in `app/services/reliability.py` for evaluating Grailed seller reliability 
- **Profile processing**: Functions to extract seller profile URLs and fetch seller data from their profile pages
- **Shipping estimation**: `app/services/shipping.py` calculates delivery costs to Russia based on item title categorization and Shopfans Lite pricing
- **Link resolution**: Handles Grailed app.link shorteners by following redirects
- **Concurrent processing**: Uses `asyncio.gather()` to scrape multiple URLs in parallel when multiple links are detected
- **HTTP session**: Configured with retries and proper user agent for reliable scraping
- **Currency conversion**: `app/services/currency.py` fetches USD to RUB exchange rate from Central Bank of Russia XML API with 5% markup
- **Admin notifications**: Sends Telegram alerts to admin when CBR API fails
- **Tiered pricing logic**: 
  - Items < $150: Fixed $15 commission (`item_price + shipping + 15`)
  - Items ≥ $150: 10% markup on item price only (`item_price * 0.10 + shipping + item_price`)
  - **Commission calculation**: Based on item price only, excluding shipping costs
- **Seller reliability scoring**: 4-criteria evaluation system (activity, rating, review volume, trusted badge) with Diamond/Gold/Silver/Bronze/Ghost categories

### Environment Variables

- `BOT_TOKEN`: Required Telegram bot token
- `PORT`: Server port (defaults to 8000)
- `RAILWAY_PUBLIC_DOMAIN` or `RAILWAY_URL`: Used to determine webhook mode vs polling mode

### Currency Exchange Rate Source

The bot uses the Central Bank of Russia (CBR) official XML API as the **only** source for USD to RUB exchange rates:

- **Endpoint**: `https://www.cbr.ru/scripts/XML_daily.asp`
- **Format**: XML with daily official rates
- **Processing**: Parses XML using `xml.etree.ElementTree`, finds USD entry, applies 5% markup
- **Error handling**: No fallback sources - if CBR API is unavailable, currency conversion is disabled and admin is notified
- **Admin notifications**: Telegram message sent to admin (ID: 26917201) when CBR API fails

### Grailed Seller Reliability System

The bot implements a comprehensive seller evaluation system for Grailed:

#### Scoring Criteria (Total: 100 points)
- **Activity Score (0-30)**: Based on days since last listing update
- **Rating Score (0-35)**: Based on average seller rating (0.00-5.00)
- **Review Volume Score (0-25)**: Based on number of reviews
- **Badge Score (0-10)**: Trusted Seller badge status

#### Implementation Details
- **Profile fetching**: Functions in `app/scrapers/grailed.py` get seller profile URL from listing page
- **Data extraction**: **Headless browser only** - static HTML parsing doesn't work due to React SPA architecture
- **Playwright integration**: Uses headless Chromium to execute JavaScript and access dynamically loaded content
- **Evaluation**: `app/services/reliability.py` applies business rules to calculate scores and categories
- **Response formatting**: Creates user-friendly Russian messages via `app/bot/messages.py`
- **Configuration**: Can be enabled/disabled via `ENABLE_HEADLESS_BROWSER` environment variable

#### Categories
- Diamond (85-100): Top-tier seller
- Gold (70-84): High reliability
- Silver (55-69): Normal reliability  
- Bronze (40-54): Increased risk
- Ghost (<40 or >30 days inactive): Low reliability
- **No Data**: When seller information is unavailable due to Grailed's technical limitations

#### User Interface
- **Listing analysis**: Seller reliability shown for buyable Grailed items (when data available)
- **Direct profile analysis**: **Limited functionality** - Users informed about technical limitations and encouraged to share listing URLs instead
- **Russian language**: All user messages in simple, neutral Russian with honest explanations of constraints

### Bot Behavior

#### URL Processing
1. **Profile URLs**: Functions in `app/bot/utils.py` detect Grailed seller profiles and process them accordingly
2. **Listing URLs**: Regular price calculation with optional seller reliability for Grailed buyable items
3. **Buyability detection**: Grailed items analyzed for buy-now vs offer-only status using JSON parsing

#### Message Types
- **Buyable items**: Price calculation + seller reliability (for Grailed, when data available)
- **Offer-only items**: Message explaining need to contact seller + displayed price for reference
- **Profile analysis**: Full seller reliability analysis using headless browser extraction
- **Errors**: Simple Russian error messages with context about technical limitations

#### Message Formatting (Updated May 2025)
- **Clean design**: Removed excessive emoji usage for better readability
- **Emoji positioning**: Moved emoji from headers to inline with category names
- **Seller info format**: "Продавец: 💎 Diamond (95/100)" instead of "💎 Продавец: Diamond (95/100)"
- **Badge display**: Simplified to "Проверенный продавец" / "Нет бейджа" without checkmark/cross emoji
- **Header cleanup**: "Анализ продавца Grailed" without leading emoji

### Shopfans Shipping Estimation

⚠️ **IMPORTANT**: Shipping weight estimates in `app/services/shipping.py` should be reviewed and updated quarterly based on actual shipment tracking data to maintain accuracy.

The shipping estimation system:
- Uses regex pattern matching on item titles to determine product categories
- Maps categories to estimated weights in kilograms
- Applies Shopfans Lite pricing formula: `max($13.99, $14 × weight) + handling_fee`
- Handling fee: $3 for items ≤ 0.45kg, $5 for heavier items
- Default weight: 0.60kg for unmatched items

## Code Quality and Documentation

### Development Tools
- **Code quality**: Enforced via `ruff` linter and `mypy` type checker
- **Documentation**: Google-style docstrings with `pydocstyle` validation
- **Pre-commit hooks**: Automatic code formatting and quality checks
- **API documentation**: Auto-generated with `mkdocs` and `mkdocstrings`
- **Testing**: Unit tests with `pytest` framework
- **Browser automation**: Playwright for headless browser testing and scraping
- **Development dependencies**: Managed via `requirements-dev.txt` for testing environment

### Documentation Standards
- All modules, classes, and functions must have Google-style docstrings
- Include Args, Returns, Raises, and Examples sections where applicable
- Type hints required for all function parameters and return values
- Comprehensive README with architecture diagrams and setup instructions

### Deployment

The bot is designed for Railway deployment with automatic webhook configuration. The `railway.toml` specifies build and start commands.