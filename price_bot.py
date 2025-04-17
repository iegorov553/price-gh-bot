#!/usr/bin/env python3
"""Telegram Price+30 Bot

Listens for messages that contain a supported shopping‑site URL (eBay, Grailed for now) and replies
with the item’s listed price plus 30 %.

Dependencies:
    python-telegram-bot >= 22.0
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
import json
from decimal import Decimal, ROUND_HALF_UP
from typing import Optional

import requests
from bs4 import BeautifulSoup
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, ContextTypes, filters

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
    match = PRICE_RE.search(raw)
    if not match:
        return None
    number = match.group(0).replace(",", "")
    try:
        return Decimal(number)
    except Exception:
        return None


def scrape_price_ebay(url: str) -> Optional[Decimal]:
    headers = {"User-Agent": "Mozilla/5.0"}
    logger.info(f"Scraping eBay price from: {url}")
    try:
        r = requests.get(url, headers=headers, timeout=10)
    except Exception as e:
        logger.error(f"Request failed: {e}")
        return None
    if r.status_code >= 400:
        return None
    soup = BeautifulSoup(r.text, "lxml")
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
            continue
        value = tag.get(attr) if attr != "text" else tag.get_text(strip=True)
        price = _clean_price(value)
        if price:
            return price
    return None


def scrape_price_grailed(url: str) -> Optional[Decimal]:
    headers = {"User-Agent": "Mozilla/5.0"}
    logger.info(f"Scraping Grailed price from: {url}")
    try:
        r = requests.get(url, headers=headers, timeout=10)
    except Exception as e:
        logger.error(f"Request failed: {e}")
        return None
    if r.status_code >= 400:
        return None
    soup = BeautifulSoup(r.text, "lxml")
    span = soup.find("span", attrs={"class": lambda c: c and "price" in c.lower()})
    if span:
        price = _clean_price(span.get_text(strip=True))
        if price:
            return price
    meta = soup.find("meta", property="product:price:amount")
    if meta and meta.get("content"):
        price = _clean_price(meta["content"])
        if price:
            return price
    script = soup.find("script", type="application/ld+json")
    if script and script.string:
        try:
            data = json.loads(script.string)
            offers = data.get("offers") or data.get("@graph", [])
            if isinstance(offers, dict):
                price_val = offers.get("price")
            elif isinstance(offers, list) and offers:
                price_val = offers[0].get("price")
            else:
                price_val = None
            if price_val:
                price = _clean_price(str(price_val))
                if price:
                    return price
        except Exception:
            pass
    return None


def get_price(url: str) -> Optional[Decimal]:
    from urllib.parse import urlparse
    domain = urlparse(url).netloc.lower()
    site = SUPPORTED_DOMAINS.get(domain)
    if site == "ebay":
        return scrape_price_ebay(url)
    if site == "grailed":
        return scrape_price_grailed(url)
    return None


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(
        "Yo, send me an eBay or Grailed link and I'll spit back the price +30 %. Easy."
    )


async def handle_link(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    message_text = update.message.text or ""
    urls = re.findall(r"(https?://[\w\.-]+(?:/[^\s]*)?)", message_text)
    if not urls:
        return
    for url in urls:
        price = await asyncio.to_thread(get_price, url)
        if price is None:
            await update.message.reply_text(f"Couldn’t pull the price from {url} 🤷‍♀️")
            continue
        price_30 = (price * Decimal("1.30")).quantize(Decimal("0.01"), ROUND_HALF_UP)
        await update.message.reply_text(
            f"List price: {price} → with my 30 % magic: {price_30}"
        )


def main() -> None:
    token = os.getenv("BOT_TOKEN")
    if not token:
        raise RuntimeError("Set BOT_TOKEN env variable with your Telegram bot token.")
    app = Application.builder().token(token).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_link))
    app.run_polling()


if __name__ == "__main__":
    main()
