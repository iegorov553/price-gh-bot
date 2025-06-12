"""eBay listing scraper for extracting item prices, shipping costs, and details.

This module provides functionality to scrape eBay listings for item information including
prices, US shipping costs, titles, and buyability status. It handles various eBay page
layouts and data formats using multiple extraction strategies with fallbacks.

The scraper supports both regular HTML parsing and JSON-LD structured data extraction
to ensure reliable data retrieval across different eBay page types.
"""

import json
import re
from decimal import Decimal
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


def _clean_price(raw: str) -> Decimal | None:
    """Clean and parse price string into Decimal."""
    raw = raw.strip()
    if not PRICE_RE.match(raw):
        return None
    try:
        return Decimal(raw.replace(',', ''))
    except Exception:
        return None


def _parse_json_ld(soup: BeautifulSoup) -> Decimal | None:
    """Parse JSON-LD structured data for price information."""
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


def _scrape_shipping_ebay(soup: BeautifulSoup) -> Decimal | None:
    """Extract US shipping cost from eBay listing page."""
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


def _extract_title(soup: BeautifulSoup) -> str | None:
    """Extract item title from eBay listing page."""
    og = soup.find("meta", property="og:title")
    if og and og.get("content"):
        return og["content"]
    h1 = soup.find("h1")
    if h1:
        return h1.get_text(strip=True)
    return None


async def get_item_data(url: str, session: aiohttp.ClientSession) -> ItemData:
    """Scrape comprehensive item data from an eBay listing.

    Extracts item price, US shipping cost, title, and buyability status from an eBay
    listing page. Uses multiple extraction strategies including HTML parsing and
    JSON-LD structured data to handle various eBay page layouts.

    Args:
        url (str): The eBay listing URL to scrape.
        session (aiohttp.ClientSession): HTTP session for making requests.

    Returns:
        ItemData: Object containing extracted item information including:
            - price: Item price in USD as Decimal, None if not found
            - shipping_us: US shipping cost as Decimal, None if not found
            - is_buyable: Always True for eBay items
            - title: Item title string, None if not found
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
    """Check if a URL belongs to eBay domain.

    Validates whether the provided URL is from an eBay domain by parsing
    the netloc and checking for 'ebay' in the domain components.

    Args:
        url (str): The URL to check.

    Returns:
        bool: True if the URL is from an eBay domain, False otherwise.
    """
    try:
        parsed = urlparse(url)
        domain = parsed.netloc.lower().split(':')[0]
        return 'ebay' in domain.split('.')
    except Exception:
        return False
