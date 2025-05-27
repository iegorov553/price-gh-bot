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

def get_usd_to_rub_rate() -> Optional[Decimal]:
    """Get USD to RUB exchange rate from Google with 5% markup"""
    try:
        logger.info("Fetching USD to RUB exchange rate from Google...")
        
        # Using Google's currency conversion via search
        url = "https://www.google.com/search?q=1+usd+to+rub"
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
        }
        response = requests.get(url, headers=headers, timeout=TIMEOUT)
        response.raise_for_status()
        logger.info(f"Got response from Google, status: {response.status_code}")
        
        # Try BeautifulSoup first, fall back to regex if not available
        try:
            soup = BeautifulSoup(response.text, 'lxml')
            
            # Try multiple selectors for the exchange rate
            selectors = [
                "span.DFlfde.SwHCTb",  # Main rate display
                "div.BNeawe.iBp4i.AP7Wnd",  # Alternative selector
                "span.pclqee",  # Another possible selector
                "div.a61j6",  # Additional selector
                "span.SwHCTb",  # Simplified selector
            ]
            
            logger.info(f"Trying {len(selectors)} CSS selectors...")
            for i, selector in enumerate(selectors):
                rate_element = soup.select_one(selector)
                if rate_element:
                    rate_text = rate_element.get_text(strip=True)
                    logger.info(f"Selector {i+1} found text: '{rate_text}'")
                    
                    # Extract numeric value, handle both comma and dot as decimal separator
                    rate_match = re.search(r'(\d+[,.]?\d*)', rate_text)
                    if rate_match:
                        rate_str = rate_match.group(1).replace(',', '.')
                        logger.info(f"Extracted rate string: '{rate_str}'")
                        
                        # Ensure we have a valid decimal number
                        if re.match(r'^\d+(\.\d+)?$', rate_str):
                            base_rate = Decimal(rate_str)
                            # Check if rate is in reasonable range (70-120)
                            if 70 <= base_rate <= 120:
                                # Add 5% markup
                                final_rate = (base_rate * Decimal('1.05')).quantize(Decimal('0.01'), ROUND_HALF_UP)
                                logger.info(f"USD to RUB rate: {base_rate} -> {final_rate} (with 5% markup)")
                                return final_rate
                            else:
                                logger.warning(f"Rate out of expected range: {base_rate}")
                        else:
                            logger.warning(f"Invalid rate format: '{rate_str}'")
                    else:
                        logger.warning(f"No numeric value found in: '{rate_text}'")
                else:
                    logger.debug(f"Selector {i+1} not found: {selector}")
        
        except ImportError:
            logger.warning("BeautifulSoup not available, using regex fallback")
        
        # Fallback: search for patterns in HTML text
        logger.info("Using pattern-based search...")
        html_text = response.text
        
        # Look for patterns that might contain exchange rates
        rate_patterns = [
            r'(\d{2,3}[.,]\d{2,4})\s*(?:RUB|рубл|rubles?)',
            r'(\d{2,3}[.,]\d{2,4})\s*Russian',
            r'1\s*USD\s*=\s*(\d{2,3}[.,]\d{2,4})',
            r'(\d{2,3}[.,]\d{2,4})\s*₽',
        ]
        
        for pattern in rate_patterns:
            matches = re.findall(pattern, html_text, re.IGNORECASE)
            if matches:
                logger.info(f"Pattern match found: {matches[:3]}")
                try:
                    rate_str = matches[0].replace(',', '.')
                    if re.match(r'^\d+(\.\d+)?$', rate_str):
                        base_rate = Decimal(rate_str)
                        # Check if rate is in reasonable range
                        if 70 <= base_rate <= 120:
                            final_rate = (base_rate * Decimal('1.05')).quantize(Decimal('0.01'), ROUND_HALF_UP)
                            logger.info(f"Pattern-based USD to RUB rate: {base_rate} -> {final_rate} (with 5% markup)")
                            return final_rate
                except Exception as e:
                    logger.warning(f"Error processing pattern rate: {e}")
        
        logger.warning("Could not find exchange rate in Google response")
        return None
        
    except Exception as e:
        logger.error(f"Error getting USD to RUB rate: {e}")
        return None

# Regex for full-string numeric price
PRICE_RE = re.compile(r"^\d[\d,.]*$")
EBAY_SELECTORS = [
    ("meta[itemprop='price']", 'content'),
    ("span#prcIsum", 'text'),
    ("span#mm-saleDscPrc", 'text'),
]

EBAY_SHIPPING_SELECTORS = [
    ("span#fshippingCost", 'text'),
    ("span.vi-price .notranslate", 'text'),
    ("span.u-flL.condText", 'text'),
    ("#shipCostId", 'text'),
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


def scrape_shipping_ebay(soup: BeautifulSoup) -> Optional[Decimal]:
    for css, attr in EBAY_SHIPPING_SELECTORS:
        tag = soup.select_one(css)
        if tag:
            raw = tag.get(attr) if attr != 'text' else tag.get_text(strip=True)
            if 'free' in raw.lower() or 'бесплатно' in raw.lower():
                return Decimal('0')
            raw = re.sub(r'[^\d.,]', '', raw)
            shipping = _clean_price(raw)
            if shipping:
                return shipping
    if soup.find(text=re.compile(r'free shipping', re.I)):
        return Decimal('0')
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


def scrape_shipping_grailed(soup: BeautifulSoup) -> Optional[Decimal]:
    shipping_text = soup.find(text=re.compile(r'shipping', re.I))
    if shipping_text:
        parent = shipping_text.parent
        if parent:
            text = parent.get_text()
            if 'free' in text.lower():
                return Decimal('0')
            shipping_match = re.search(r'\$(\d+(?:\.\d{2})?)', text)
            if shipping_match:
                return Decimal(shipping_match.group(1))
    
    shipping_elem = soup.find('div', string=re.compile(r'shipping', re.I))
    if shipping_elem:
        next_elem = shipping_elem.find_next_sibling()
        if next_elem:
            text = next_elem.get_text(strip=True)
            if 'free' in text.lower():
                return Decimal('0')
            shipping_match = re.search(r'\$(\d+(?:\.\d{2})?)', text)
            if shipping_match:
                return Decimal(shipping_match.group(1))
    
    return Decimal('15')


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


def get_price_and_shipping(url: str) -> tuple[Optional[Decimal], Optional[Decimal]]:
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
            return None, None
    
    try:
        r = session.get(url, timeout=TIMEOUT)
        r.raise_for_status()
        soup = BeautifulSoup(r.text, 'lxml')
    except Exception as e:
        logger.error(f"Request error: {e}")
        return None, None
    
    domain = urlparse(url).netloc.lower().split(':')[0]
    labels = domain.split('.')
    
    if 'ebay' in labels:
        price = None
        for css, attr in EBAY_SELECTORS:
            tag = soup.select_one(css)
            if tag:
                raw = tag.get(attr) if attr != 'text' else tag.get_text(strip=True)
                price = _clean_price(raw)
                if price:
                    break
        if not price:
            price = _parse_json_ld(soup)
        shipping = scrape_shipping_ebay(soup)
        return price, shipping
    
    if 'grailed' in labels:
        span = soup.find('span', attrs={'class': lambda c: c and 'price' in c.lower()})
        price = None
        if span:
            price = _clean_price(span.get_text(strip=True))
        if not price:
            meta = soup.find('meta', property='product:price:amount')
            if meta and meta.get('content'):
                price = _clean_price(meta['content'])
        if not price:
            price = _parse_json_ld(soup)
        shipping = scrape_shipping_grailed(soup)
        return price, shipping
    
    return None, None

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(
        "Yo, send me an eBay or Grailed link and I'll calculate the price + shipping + commission (fixed $15 for items <$150, or 10% for items ≥$150). Final price shown in USD and RUB."
    )

async def handle_link(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    text = update.message.text or ''
    urls = re.findall(r"(https?://[\w\.-]+(?:/[^\s]*)?)", text)
    if not urls:
        return
    # Fetch all URLs concurrently for performance
    tasks = [asyncio.to_thread(get_price_and_shipping, u) for u in urls]
    results = await asyncio.gather(*tasks)
    
    # Get USD to RUB rate once for all conversions
    logger.info("Getting USD to RUB exchange rate...")
    usd_to_rub_rate = await asyncio.to_thread(get_usd_to_rub_rate)
    if usd_to_rub_rate:
        logger.info(f"Successfully got exchange rate: {usd_to_rub_rate}")
    else:
        logger.warning("Failed to get exchange rate - will show USD only")
    
    for u, (price, shipping) in zip(urls, results):
        if not price:
            await update.message.reply_text(f"Couldn’t pull the price from {u} 🤷‍♀️")
        else:
            shipping = shipping or Decimal('0')
            total_cost = price + shipping
            
            # New pricing logic: fixed $15 commission if item price < $150, otherwise 10% markup
            if price < Decimal('150'):
                final_price = (total_cost + Decimal('15')).quantize(Decimal('0.01'), ROUND_HALF_UP)
                commission_text = "$15 commission"
            else:
                final_price = (total_cost * Decimal('1.10')).quantize(Decimal('0.01'), ROUND_HALF_UP)
                commission_text = "10% markup"
            
            shipping_text = f" + ${shipping} shipping" if shipping > 0 else " (free shipping)"
            
            # Convert to RUB if rate is available
            rub_text = ""
            if usd_to_rub_rate:
                final_price_rub = (final_price * usd_to_rub_rate).quantize(Decimal('0.01'), ROUND_HALF_UP)
                rub_text = f" (₽{final_price_rub})"
                logger.info(f"Converted ${final_price} to ₽{final_price_rub} using rate {usd_to_rub_rate}")
            else:
                logger.warning("No exchange rate available, showing USD only")
            
            await update.message.reply_text(
                f"Price: ${price}{shipping_text} = ${total_cost}\n"
                f"With {commission_text}: ${final_price}{rub_text}"
            )


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