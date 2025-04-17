#!/usr/bin/env python3
"""Telegram Price+30 Bot

Scrapes prices from any eBay or Grailed listing and replies with the price + 30%.
"""
import asyncio
import logging
import os
import re
import json
from decimal import Decimal, ROUND_HALF_UP
from typing import Optional
from urllib.parse import urlparse

import requests
from bs4 import BeautifulSoup
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, ContextTypes, filters

logging.basicConfig(format="%(asctime)s - %(levelname)s - %(message)s", level=logging.INFO)
logger = logging.getLogger(__name__)

# Reuse a session for connection pooling
session = requests.Session()
session.headers.update({"User-Agent": "Mozilla/5.0"})

PRICE_RE = re.compile(r"^\d[\d,.]*$")
EBAY_SELECTORS = [
    ("meta[itemprop='price']", 'content'),
    ("span#prcIsum", 'text'),
    ("span#mm-saleDscPrc", 'text'),
]


def _clean_price(raw: str) -> Optional[Decimal]:
    match = PRICE_RE.match(raw.strip())
    if not match:
        return None
    try:
        return Decimal(match.group(0).replace(',', ''))
    except Exception:
        return None


def _parse_json_ld(soup: BeautifulSoup) -> Optional[Decimal]:
    scripts = soup.find_all('script', type='application/ld+json')
    for script in scripts:
        text = script.string
        if not text:
            continue
        try:
            data = json.loads(text)
        except json.JSONDecodeError:
            continue
        offers = data.get('offers') or data.get('@graph', [])
        price_val = None
        if isinstance(offers, dict):
            price_val = offers.get('price')
        else:
            for item in offers if isinstance(offers, list) else []:
                if isinstance(item, dict) and 'price' in item:
                    price_val = item['price']
                    break
        if price_val:
            price = _clean_price(str(price_val))
            if price:
                return price
    return None


def scrape_price_ebay(url: str) -> Optional[Decimal]:
    try:
        r = session.get(url, timeout=10)
    except Exception as e:
        logger.error(f"eBay request error: {e}")
        return None
    if r.status_code >= 400:
        return None
    soup = BeautifulSoup(r.text, 'lxml')
    for css, attr in EBAY_SELECTORS:
        tag = soup.select_one(css)
        if tag:
            value = tag.get(attr) if attr != 'text' else tag.get_text(strip=True)
            price = _clean_price(value)
            if price:
                return price
    return _parse_json_ld(soup)


def scrape_price_grailed(url: str) -> Optional[Decimal]:
    try:
        r = session.get(url, timeout=10)
    except Exception as e:
        logger.error(f"Grailed request error: {e}")
        return None
    if r.status_code >= 400:
        return None
    soup = BeautifulSoup(r.text, 'lxml')
    span = soup.find('span', attrs={'class': lambda c: c and 'price' in c.lower()})
    if span:
        price = _clean_price(span.get_text(strip=True))
        if price:
            return price
    meta = soup.find('meta', property='product:price:amount')
    if meta and meta.get('content'):
        price = _clean_price(meta['content'])
        if price:
            return price
    return _parse_json_ld(soup)


def get_price(url: str) -> Optional[Decimal]:
    domain = urlparse(url).netloc.lower().split(':')[0]
    labels = domain.split('.')
    if 'ebay' in labels:
        return scrape_price_ebay(url)
    if 'grailed' in labels:
        return scrape_price_grailed(url)
    return None

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(
        "Yo, send me an eBay or Grailed link and I'll spit back the price +30%."
    )

async def handle_link(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    text = update.message.text or ''
    urls = re.findall(r"(https?://[\w\.-]+(?:/[^\s]*)?)", text)
    tasks = [asyncio.to_thread(get_price, url) for url in urls]
    prices = await asyncio.gather(*tasks)
    for url, price in zip(urls, prices):
        if not price:
            await update.message.reply_text(f"Couldn’t pull the price from {url} 🤷‍♀️")
        else:
            markup = (price * Decimal('1.30')).quantize(Decimal('0.01'), ROUND_HALF_UP)
            await update.message.reply_text(f"List price: {price} → with my 30% magic: {markup}")


def main() -> None:
    token = os.getenv('BOT_TOKEN')
    if not token:
        raise RuntimeError('Set BOT_TOKEN environment variable')
    app = Application.builder().token(token).build()
    app.add_handler(CommandHandler('start', start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_link))

    # Always use webhooks on Railway
    port = int(os.getenv('PORT', 8000))
    domain = os.getenv('RAILWAY_PUBLIC_DOMAIN')
    path = f"/{token}"
    webhook_url = f"https://{domain}{path}"
    app.run_webhook(
        listen='0.0.0.0',
        port=port,
        url_path=path,
        webhook_url=webhook_url
    )

if __name__ == '__main__':
    main()
