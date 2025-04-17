#!/usr/bin/env python3
"""Telegram Price+30 Bot

Listens for messages that contain a supported shopping‑site URL (eBay, Grailed for now) and replies
with the item’s listed price plus 30 %.

Dependencies:
    python-telegram-bot >= 21.0a0  (async API)
    requests
    beautifulsoup4
    lxml

Run:
    export BOT_TOKEN="123456:ABC..."
    python price_bot.py
"""

import asyncio
import logging
import os
import re
from decimal import Decimal, ROUND_HALF_UP
from typing import Optional

import requests
from bs4 import BeautifulSoup
from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    filters,
)

# Configure logging to show debug info
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.DEBUG,
)
logger = logging.getLogger(__name__)

PRICE_RE = re.compile(r"[\d,.]+")

SUPPORTED_DOMAINS = {
    "ebay.com": "ebay",
    "www.ebay.com": "ebay",
    "grailed.com": "grailed",
    "www.grailed.com": "grailed",
}


def _clean_price(raw: str) -> Optional[Decimal]:
    logger.debug(f"Cleaning raw price string: {raw}")
    match = PRICE_RE.search(raw)
    if not match:
        logger.warning(f"No numeric match found in raw price: {raw}")
        return None
    number = match.group(0).replace(",", "")
    try:
        price = Decimal(number)
        logger.debug(f"Parsed decimal price: {price}")
        return price
    except Exception as e:
        logger.error(f"Error parsing price '{number}': {e}")
        return None


def scrape_price_ebay(url: str) -> Optional[Decimal]:
    headers = {
        "User-Agent": "Mozilla/5.0 (compatible; PriceBot/1.0; +https://example.com/bot)"
    }
    logger.info(f"Scraping eBay price from URL: {url}")
    try:
        r = requests.get(url, headers=headers, timeout=10)
        logger.debug(f"Received status code {r.status_code} for URL: {url}")
    except Exception as e:
        logger.error(f"HTTP request failed for {url}: {e}")
        return None
    if r.status_code >= 400:
        logger.warning(f"Bad status code {r.status_code} for URL: {url}")
        return None
    soup = BeautifulSoup(r.text, "lxml")

    # eBay embeds price in several places; try common meta tags
    selectors = [
        ('meta[itemprop="price"]', "content"),
        ('span[itemprop="price"]', "content"),
        ('span[itemprop="price"]', "text"),
        ("span#prcIsum", "text"),
        ("span#mm-saleDscPrc", "text"),
    ]
    for css, attr in selectors:
        tag = soup.select_one(css)
        if not tag:
            logger.debug(f"Selector {css} not found for URL: {url}")
            continue
        value = tag.get(attr) if attr != "text" else tag.get_text(strip=True)
        price = _clean_price(value)
        if price:
            logger.info(f"Found price {price} using selector {css}")
            return price
    logger.warning(f"No price found for eBay URL: {url}")
    return None


def scrape_price_grailed(url: str) -> Optional[Decimal]:
    headers = {
        "User-Agent": "Mozilla/5.0 (compatible; PriceBot/1.0; +https://example.com/bot)"
    }
    logger.info(f"Scraping Grailed price from URL: {url}")
    try:
        r = requests.get(url, headers=headers, timeout=10)
        logger.debug(f"Received status code {r.status_code} for URL: {url}")
    except Exception as e:
        logger.error(f"HTTP request failed for {url}: {e}")
        return None
    if r.status_code >= 400:
        logger.warning(f"Bad status code {r.status_code} for URL: {url}")
        return None
    soup = BeautifulSoup(r.text, "lxml")
    # Grailed price usually in data-lazy attribute script json; fallback to span
    span = soup.find("span", attrs={"class": lambda c: c and "listing-price" in c})
    if span:
        value = span.get_text(strip=True)
        price = _clean_price(value)
        if price:
            logger.info(f"Found price {price} in span for URL: {url}")
            return price
    # Try meta
    meta = soup.find("meta", property="product:price:amount")
    if meta and meta.get("content"):
        value = meta["content"]
        price = _clean_price(value)
        if price:
            logger.info(f"Found price {price} in meta for URL: {url}")
            return price
    logger.warning(f"No price found for Grailed URL: {url}")
    return None


def get_price(url: str) -> Optional[Decimal]:
    from urllib.parse import urlparse

    logger.debug(f"Getting price for URL: {url}")
    domain = urlparse(url).netloc.lower()
    site = SUPPORTED_DOMAINS.get(domain)
    if site == "ebay":
        return scrape_price_ebay(url)
    if site == "grailed":
        return scrape_price_grailed(url)
    logger.error(f"Unsupported domain {domain} for URL: {url}")
    return None


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    logger.info(f"Received /start from user {update.effective_user.id}")
    await update.message.reply_text(
        "Yo, send me an eBay or Grailed link and I'll spit back the price +30 %. Easy."
    )


async def handle_link(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    message_text = update.message.text or ""
    logger.info(f"Received message: {message_text} from user {update.effective_user.id}")
    urls = re.findall(
        r"(https?://[\w\.-]+(?:/[^\s]*)?)", message_text, flags=re.IGNORECASE
    )
    logger.debug(f"Extracted URLs: {urls}")
    if not urls:
        logger.debug("No URLs found in message, skipping")
        return

    for url in urls:
        price = await asyncio.to_thread(get_price, url)
        if price is None:
            logger.warning(f"Failed to get price for URL: {url}")
            await update.message.reply_text(f"Couldn’t pull the price from {url} 🤷‍♀️")
            continue
        price_30 = (price * Decimal("1.30")).quantize(Decimal("0.01"), ROUND_HALF_UP)
        logger.info(f"Original price: {price}, Price+30%: {price_30} for URL: {url}")
        await update.message.reply_text(
            f"List price: {price} → with my 30 % magic: {price_30}"
        )


def main() -> None:
    token = os.getenv("BOT_TOKEN")
    logger.debug("Loading BOT_TOKEN from environment")
    if not token:
        logger.critical("BOT_TOKEN not set. Exiting.")
        raise RuntimeError("Set BOT_TOKEN env variable with your Telegram bot token.")
    app = Application.builder().token(token).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(
        MessageHandler(filters.TEXT & ~filters.COMMAND, handle_link)
    )

    logger.info("Bot starting…")
    app.run_polling(stop_signals=None)


if __name__ == "__main__":
    main()
