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

- **Messages module**: `app/bot/messages.py` containing all user-facing text in Russian for easy localization and editing
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
  - Items < $150: Fixed $15 commission (`total_cost + 15`)
  - Items ≥ $150: 10% markup (`total_cost * 1.10`)
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
- **Activity Score (0-30)**: Based on days since last listing update (fetched from seller profile)
- **Rating Score (0-35)**: Based on average seller rating (0.00-5.00)
- **Review Volume Score (0-25)**: Based on number of reviews
- **Badge Score (0-10)**: Trusted Seller badge status

#### Implementation Details
- **Profile fetching**: Functions in `app/scrapers/grailed.py` get seller profile URL from listing page using multiple JSON and HTML patterns
- **Last update tracking**: Fetches seller's profile page to find most recent listing update date with robust date parsing
- **Data extraction**: Combines listing page data with profile data using multiple extraction strategies and fallback patterns
- **Evaluation**: `app/services/reliability.py` applies business rules to calculate scores and categories
- **Response formatting**: Creates user-friendly Russian messages via `app/bot/messages.py`
- **Robust parsing**: All functions use multiple regex patterns, JSON field variations, and HTML fallbacks to handle Grailed's evolving page structure

#### Categories
- Diamond (85-100): Top-tier seller
- Gold (70-84): High reliability
- Silver (55-69): Normal reliability  
- Bronze (40-54): Increased risk
- Ghost (<40 or >30 days inactive): Low reliability

#### User Interface
- **Listing analysis**: Seller reliability shown for buyable Grailed items
- **Direct profile analysis**: Users can send Grailed profile URLs for detailed seller evaluation
- **Russian language**: All user messages in simple, neutral Russian

### Bot Behavior

#### URL Processing
1. **Profile URLs**: Functions in `app/bot/utils.py` detect Grailed seller profiles and process them accordingly
2. **Listing URLs**: Regular price calculation with optional seller reliability for Grailed buyable items
3. **Buyability detection**: Grailed items analyzed for buy-now vs offer-only status using JSON parsing

#### Message Types
- **Buyable items**: Price calculation + seller reliability (for Grailed)
- **Offer-only items**: Message explaining need to contact seller + displayed price for reference
- **Profile analysis**: Detailed seller reliability breakdown
- **Errors**: Simple Russian error messages

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

### Documentation Standards
- All modules, classes, and functions must have Google-style docstrings
- Include Args, Returns, Raises, and Examples sections where applicable
- Type hints required for all function parameters and return values
- Comprehensive README with architecture diagrams and setup instructions

### Deployment

The bot is designed for Railway deployment with automatic webhook configuration. The `railway.toml` specifies build and start commands.