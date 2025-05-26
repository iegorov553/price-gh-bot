# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Development Commands

- **Install dependencies**: `pip install -r requirements.txt`
- **Run bot locally**: `python price_bot.py`
- **Deploy to Railway**: Automatically handled by `railway.json` config

## Architecture Overview

This is a single-file Telegram bot (`price_bot.py`) that scrapes prices from eBay and Grailed listings and calculates a 30% markup. The bot operates in two modes:
- **Webhook mode**: When deployed with a public domain (Railway), uses webhooks for production
- **Polling mode**: Falls back to long-polling when no public domain is available (local development)

### Core Components

- **Price scrapers**: Separate functions for eBay (`scrape_price_ebay`) and Grailed (`scrape_price_grailed`) that use different CSS selectors and fallback strategies
- **Link resolution**: Handles Grailed app.link shorteners by following redirects
- **Concurrent processing**: Uses `asyncio.gather()` to scrape multiple URLs in parallel when multiple links are detected
- **HTTP session**: Configured with retries and proper user agent for reliable scraping

### Environment Variables

- `BOT_TOKEN`: Required Telegram bot token
- `PORT`: Server port (defaults to 8000)
- `RAILWAY_PUBLIC_DOMAIN` or `RAILWAY_URL`: Used to determine webhook mode vs polling mode

### Deployment

The bot is designed for Railway deployment with automatic webhook configuration. The `railway.json` specifies build and start commands.