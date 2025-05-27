# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Development Commands

- **Install dependencies**: `pip install -r requirements.txt`
- **Run bot locally**: `python price_bot.py`
- **Deploy to Railway**: Automatically handled by `railway.json` config

## Architecture Overview

This is a single-file Telegram bot (`price_bot.py`) that scrapes prices from eBay and Grailed listings, adds US shipping costs, and calculates a 10% markup. The bot operates in two modes:
- **Webhook mode**: When deployed with a public domain (Railway), uses webhooks for production
- **Polling mode**: Falls back to long-polling when no public domain is available (local development)

### Core Components

- **Price scrapers**: Combined function `get_price_and_shipping()` that extracts both item price and US shipping cost from eBay and Grailed listings
- **Shipping scrapers**: Separate functions for eBay (`scrape_shipping_ebay`) and Grailed (`scrape_shipping_grailed`) that parse shipping costs
- **Link resolution**: Handles Grailed app.link shorteners by following redirects
- **Concurrent processing**: Uses `asyncio.gather()` to scrape multiple URLs in parallel when multiple links are detected
- **HTTP session**: Configured with retries and proper user agent for reliable scraping
- **Price calculation**: Formula: `(item_price + shipping_cost) * 1.10` instead of simple 30% markup

### Environment Variables

- `BOT_TOKEN`: Required Telegram bot token
- `PORT`: Server port (defaults to 8000)
- `RAILWAY_PUBLIC_DOMAIN` or `RAILWAY_URL`: Used to determine webhook mode vs polling mode

### Deployment

The bot is designed for Railway deployment with automatic webhook configuration. The `railway.json` specifies build and start commands.