"""eBay scraper implementation."""

import json
import re
from decimal import Decimal
from typing import Optional
from urllib.parse import urlparse

import aiohttp
from bs4 import BeautifulSoup

from ..models import ItemData


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
    """Clean and parse price string."""
    raw = raw.strip()
    if not PRICE_RE.match(raw):
        return None
    try:
        return Decimal(raw.replace(',', ''))
    except Exception:
        return None


def _parse_json_ld(soup: BeautifulSoup) -> Optional[Decimal]:
    """Parse JSON-LD structured data for price."""
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


def _scrape_shipping_ebay(soup: BeautifulSoup) -> Optional[Decimal]:
    """Extract eBay shipping cost."""
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


def _extract_title(soup: BeautifulSoup) -> Optional[str]:
    """Extract item title."""
    og = soup.find("meta", property="og:title")
    if og and og.get("content"):
        return og["content"]
    h1 = soup.find("h1")
    if h1:
        return h1.get_text(strip=True)
    return None


async def get_item_data(url: str, session: aiohttp.ClientSession) -> ItemData:
    """
    Scrape eBay item data.
    
    Args:
        url: eBay listing URL
        session: aiohttp session for requests
    
    Returns:
        ItemData with scraped information
    """
    try:
        async with session.get(url) as response:
            response.raise_for_status()
            html = await response.text()
    except Exception:
        return ItemData()
    
    soup = BeautifulSoup(html, 'lxml')
    
    # Extract price
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
    
    # Extract shipping
    shipping = _scrape_shipping_ebay(soup)
    
    # Extract title
    title = _extract_title(soup)
    
    return ItemData(
        price=price,
        shipping_us=shipping,
        is_buyable=True,  # eBay items are always buyable
        title=title
    )


def is_ebay_url(url: str) -> bool:
    """Check if URL is an eBay listing."""
    try:
        parsed = urlparse(url)
        domain = parsed.netloc.lower().split(':')[0]
        return 'ebay' in domain.split('.')
    except Exception:
        return False