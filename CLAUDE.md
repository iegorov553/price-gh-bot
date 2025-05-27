# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Development Commands

- **Install dependencies**: `pip install -r requirements.txt`
- **Run bot locally**: `python price_bot.py`
- **Deploy to Railway**: Automatically handled by `railway.json` config

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

This Telegram bot consists of two main files: `price_bot.py` (main logic) and `messages.py` (localized messages). It scrapes prices from eBay and Grailed listings, adds US shipping costs, applies tiered commission structure, converts to RUB, and provides comprehensive Grailed seller reliability analysis. The bot operates in two modes:
- **Webhook mode**: When deployed with a public domain (Railway), uses webhooks for production
- **Polling mode**: Falls back to long-polling when no public domain is available (local development)

### Core Components

- **Messages module**: Separate `messages.py` file containing all user-facing text in Russian for easy localization and editing
- **Price scrapers**: Combined function `get_price_and_shipping()` that extracts item price, US shipping cost, buyability status, and seller data from eBay and Grailed listings
- **Buyability detection**: Function `scrape_price_grailed()` analyzes JSON data to determine if Grailed items have fixed buy-now pricing or are offer-only
- **Seller analysis**: Comprehensive system for evaluating Grailed seller reliability with `evaluate_seller_reliability()`, `analyze_seller_profile()`, and `extract_seller_data_grailed()`
- **Profile processing**: Functions `extract_seller_profile_url()` and `fetch_seller_last_update()` get seller data from their profile pages
- **Shipping scrapers**: Separate functions for eBay (`scrape_shipping_ebay`) and Grailed (`scrape_shipping_grailed`) that parse shipping costs
- **Link resolution**: Handles Grailed app.link shorteners by following redirects
- **Concurrent processing**: Uses `asyncio.gather()` to scrape multiple URLs in parallel when multiple links are detected
- **HTTP session**: Configured with retries and proper user agent for reliable scraping
- **Currency conversion**: Function `get_usd_to_rub_rate()` fetches USD to RUB exchange rate from Central Bank of Russia XML API with 5% markup
- **Admin notifications**: Function `notify_admin()` sends Telegram alerts to admin (ID: 26917201) when CBR API fails
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
- **Profile fetching**: `extract_seller_profile_url()` gets seller profile URL from listing page using multiple JSON and HTML patterns
- **Last update tracking**: `fetch_seller_last_update()` fetches seller's profile page to find most recent listing update date with robust date parsing
- **Data extraction**: `extract_seller_data_grailed()` combines listing page data with profile data using multiple extraction strategies and fallback patterns
- **Evaluation**: `evaluate_seller_reliability()` applies business rules to calculate scores and categories
- **Response formatting**: `format_seller_profile_response()` creates user-friendly Russian messages
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
1. **Profile URLs**: `is_grailed_seller_profile()` detects Grailed seller profiles and processes with `analyze_seller_profile()`
2. **Listing URLs**: Regular price calculation with optional seller reliability for Grailed buyable items
3. **Buyability detection**: Grailed items analyzed for buy-now vs offer-only status using JSON parsing

#### Message Types
- **Buyable items**: Price calculation + seller reliability (for Grailed)
- **Offer-only items**: Message explaining need to contact seller + displayed price for reference
- **Profile analysis**: Detailed seller reliability breakdown
- **Errors**: Simple Russian error messages

### Deployment

The bot is designed for Railway deployment with automatic webhook configuration. The `railway.json` specifies build and start commands.