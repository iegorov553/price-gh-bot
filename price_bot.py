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
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from bs4 import BeautifulSoup
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, ContextTypes, filters

# Logging
logging.basicConfig(format="%(asctime)s - %(levelname)s - %(message)s", level=logging.INFO)
logger = logging.getLogger(__name__)

# HTTP session with retries and pooling
session = requests.Session()
retries = Retry(total=3, backoff_factor=1, status_forcelist=[500, 502, 503, 504])
adapter = HTTPAdapter(max_retries=retries)
session.mount("http://", adapter)
session.mount("https://", adapter)
session.headers.update({"User-Agent": "Mozilla/5.0 (compatible; PriceBot/1.0)"})
TIMEOUT = 20

# Regex for full-string numeric price
PRICE_RE = re.compile(r"^\d[\d,.]*$")
EBAY_SELECTORS = [
    ("meta[itemprop='price']", 'content'),
    ("span#prcIsum", 'text'),
    ("span#mm-saleDscPrc", 'text'),
]

def _clean_price(raw: str) -> Optional[Decimal]:
    raw = raw.strip()
    if not PRICE_RE.match(raw):
        return None
    try:
        return Decimal(raw.replace(',', ''))
    except Exception:
        return None


def _parse_json_ld(soup: BeautifulSoup) -> Optional[Decimal]:
    for script in soup.find_all('script', type='application/ld+json'):
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
        elif isinstance(offers, list):
            for item in offers:
                if isinstance(item, dict) and item.get('price'):
                    price_val = item['price']
                    break
        if price_val is not None:
            price = _clean_price(str(price_val))
            if price:
                return price
    return None


def scrape_price_ebay(url: str) -> Optional[Decimal]:
    try:
        r = session.get(url, timeout=TIMEOUT)
        r.raise_for_status()
    except Exception as e:
        logger.error(f"eBay request error: {e}")
        return None
    soup = BeautifulSoup(r.text, 'lxml')
    for css, attr in EBAY_SELECTORS:
        tag = soup.select_one(css)
        if tag:
            raw = tag.get(attr) if attr != 'text' else tag.get_text(strip=True)
            price = _clean_price(raw)
            if price:
                return price
    return _parse_json_ld(soup)


def scrape_price_grailed(url: str) -> Optional[Decimal]:
    try:
        r = session.get(url, timeout=TIMEOUT)
        r.raise_for_status()
    except Exception as e:
        logger.error(f"Grailed request error: {e}")
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
    parsed = urlparse(url)
    # Resolve Grailed app.link shorteners
    if parsed.netloc.endswith('app.link'):
        try:
            resp = session.get(url, timeout=TIMEOUT)
            if resp.url and 'grailed.com' in resp.url:
                url = resp.url
            else:
                soup = BeautifulSoup(resp.text, 'lxml')
                meta = soup.find('meta', attrs={'http-equiv': lambda v: v and v.lower() == 'refresh'})
                if meta and 'url=' in meta.get('content', ''):
                    url = meta['content'].split('url=', 1)[1]
                else:
                    a = soup.find('a', href=re.compile(r'https?://(www\.)?grailed\.com/'))
                    if a:
                        url = a['href']
        except Exception:
            return None
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
    if not urls:
        return
    # Fetch all URLs concurrently for performance
    tasks = [asyncio.to_thread(get_price, u) for u in urls]
    results = await asyncio.gather(*tasks)
    for u, price in zip(urls, results):
        if not price:
            await update.message.reply_text(f"Couldn’t pull the price from {u} 🤷‍♀️")
        else:
            markup = (price * Decimal('1.30')).quantize(Decimal('0.01'), ROUND_HALF_UP)
            await update.message.reply_text(f"List price: {price} → with my 30% magic: {markup}")


def main() -> None:
    token = os.getenv('BOT_TOKEN') or ''
    if not token:
        raise RuntimeError('Set BOT_TOKEN environment variable')
    app = Application.builder().token(token).build()
    app.add_handler(CommandHandler('start', start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_link))
    port = int(os.getenv('PORT', 8000))
    domain = os.getenv('RAILWAY_PUBLIC_DOMAIN') or os.getenv('RAILWAY_URL')
    if domain:
        path = f"/{token}"
        webhook_url = f"https://{domain}{path}"
        logger.info(f"Starting webhook at {webhook_url}")
        app.run_webhook(
            listen='0.0.0.0',
            port=port,
            url_path=path,
            webhook_url=webhook_url,
        )
    else:
        logger.warning('No public domain found; falling back to long-polling')
        app.run_polling()

if __name__ == '__main__':
    main()