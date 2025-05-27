#!/usr/bin/env python3
"""Telegram Price+30 Bot

Scrapes prices from any eBay or Grailed listing and replies with the price + 30%.
"""
import asyncio
import logging
import os
import re
import json
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from decimal import Decimal, ROUND_HALF_UP
from typing import Optional, Dict, Any
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

# Admin notification settings
ADMIN_CHAT_ID = 26917201

def evaluate_seller_reliability(num_reviews: int, avg_rating: float, trusted_badge: bool, last_updated: datetime) -> Dict[str, Any]:
    """Evaluate Grailed seller reliability based on public profile metadata.
    
    Args:
        num_reviews: Number of reviews at time of evaluation
        avg_rating: Average rating (0.00 - 5.00)
        trusted_badge: True if profile has Trusted Seller badge
        last_updated: Date/time of last listing update
    
    Returns:
        Dict containing:
        - activity_score: Points for activity (0-30)
        - rating_score: Points for rating (0-35) 
        - review_volume_score: Points for review volume (0-25)
        - badge_score: Points for trusted badge (0-10)
        - total_score: Sum of all scores (0-100)
        - category: Reliability category string
        - description: Category description
    """
    now = datetime.now(timezone.utc)
    if last_updated.tzinfo is None:
        last_updated = last_updated.replace(tzinfo=timezone.utc)
    
    days_since_update = (now - last_updated).days
    
    # Hard filter: Ghost if inactive > 30 days
    if days_since_update > 30:
        return {
            'activity_score': 0,
            'rating_score': 0,
            'review_volume_score': 0,
            'badge_score': 0,
            'total_score': 0,
            'category': 'Ghost',
            'description': 'Неактивный продавец (>30 дней без обновлений)'
        }
    
    # Activity Score (0-30)
    if days_since_update <= 2:
        activity_score = 30
    elif days_since_update <= 7:
        activity_score = 24
    else:  # 8-30 days
        activity_score = 12
    
    # Rating Score (0-35)
    if avg_rating >= 4.90:
        rating_score = 35
    elif avg_rating >= 4.70:
        rating_score = 30
    elif avg_rating >= 4.50:
        rating_score = 24
    elif avg_rating >= 4.00:
        rating_score = 12
    else:
        rating_score = 0
    
    # Review Volume Score (0-25)
    if num_reviews == 0:
        review_volume_score = 0
    elif num_reviews <= 9:
        review_volume_score = 5
    elif num_reviews <= 49:
        review_volume_score = 15
    elif num_reviews <= 199:
        review_volume_score = 20
    else:  # >= 200
        review_volume_score = 25
    
    # Badge Score (0-10)
    badge_score = 10 if trusted_badge else 0
    
    # Total Score
    total_score = activity_score + rating_score + review_volume_score + badge_score
    
    # Determine category and description
    if total_score >= 85:
        category = 'Diamond'
        description = 'Продавец топ-уровня, можно брать без лишних вопросов'
    elif total_score >= 70:
        category = 'Gold'
        description = 'Высокая надёжность, смело оплачивать'
    elif total_score >= 55:
        category = 'Silver'
        description = 'Нормально, но проверь детали сделки'
    elif total_score >= 40:
        category = 'Bronze'
        description = 'Повышенный риск, используй безопасную оплату'
    else:
        category = 'Ghost'
        description = 'Низкая надёжность, высокий риск'
    
    return {
        'activity_score': activity_score,
        'rating_score': rating_score,
        'review_volume_score': review_volume_score,
        'badge_score': badge_score,
        'total_score': total_score,
        'category': category,
        'description': description
    }

async def notify_admin(application, message: str) -> None:
    """Send notification to admin about API failure"""
    try:
        await application.bot.send_message(
            chat_id=ADMIN_CHAT_ID,
            text=f"🚨 Price Bot Alert:\n{message}"
        )
        logger.info(f"Admin notification sent: {message}")
    except Exception as e:
        logger.error(f"Failed to send admin notification: {e}")

def get_usd_to_rub_rate() -> Optional[Decimal]:
    """Get USD to RUB exchange rate from Central Bank of Russia with 5% markup"""
    try:
        logger.info("Fetching USD to RUB exchange rate from Central Bank of Russia...")
        
        # CBR official XML API endpoint
        url = "https://www.cbr.ru/scripts/XML_daily.asp"
        response = requests.get(url, timeout=TIMEOUT)
        response.raise_for_status()
        logger.info(f"Got response from CBR, status: {response.status_code}")
        
        # Parse XML response
        root = ET.fromstring(response.content)
        logger.info(f"Successfully parsed CBR XML, date: {root.get('Date')}")
        
        # Find USD currency entry
        for valute in root.findall('Valute'):
            char_code = valute.find('CharCode')
            if char_code is not None and char_code.text == 'USD':
                value_elem = valute.find('Value')
                nominal_elem = valute.find('Nominal')
                
                if value_elem is not None and nominal_elem is not None:
                    # CBR uses comma as decimal separator
                    value_str = value_elem.text.replace(',', '.')
                    nominal_str = nominal_elem.text
                    
                    base_rate = Decimal(value_str) / Decimal(nominal_str)
                    logger.info(f"CBR USD rate: {base_rate} RUB per USD")
                    
                    # Add 5% markup
                    final_rate = (base_rate * Decimal('1.05')).quantize(Decimal('0.01'), ROUND_HALF_UP)
                    logger.info(f"Final USD to RUB rate: {base_rate} -> {final_rate} (with 5% markup)")
                    return final_rate
        
        raise ValueError("USD currency not found in CBR response")
        
    except Exception as e:
        error_msg = f"CBR API failed: {e}"
        logger.error(error_msg)
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
    shipping_text = soup.find(string=re.compile(r'shipping', re.I))
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


def scrape_price_grailed(url: str) -> tuple[Optional[Decimal], bool]:
    """Scrape Grailed price and determine if item has buy-now option.
    
    Returns:
        tuple: (price, is_buyable)
        - price: The item price if found
        - is_buyable: True if both Purchase/Buy and Offer buttons exist, False if only Offer
    """
    try:
        r = session.get(url, timeout=TIMEOUT)
        r.raise_for_status()
    except Exception as e:
        logger.error(f"Grailed request error: {e}")
        return None, False
    
    soup = BeautifulSoup(r.text, 'lxml')
    
    # Extract price
    price = None
    span = soup.find('span', attrs={'class': lambda c: c and 'price' in c.lower()})
    if span:
        price = _clean_price(span.get_text(strip=True))
    if not price:
        meta = soup.find('meta', property='product:price:amount')
        if meta and meta.get('content'):
            price = _clean_price(meta['content'])
    if not price:
        price = _parse_json_ld(soup)
    
    # Check buyability from JSON data (Grailed uses React SPA)
    is_buyable = False
    try:
        # Look for JSON data containing buyNow flag
        for script in soup.find_all('script'):
            if script.string and 'buyNow' in script.string:
                # Try to extract buyNow flag from JSON
                buy_now_match = re.search(r'"buyNow"\s*:\s*(true|false)', script.string)
                if buy_now_match:
                    is_buyable = buy_now_match.group(1) == 'true'
                    break
    except Exception:
        # Fallback: assume buyable if price is found
        is_buyable = price is not None
    
    return price, is_buyable


def extract_seller_profile_url(soup: BeautifulSoup) -> Optional[str]:
    """Extract seller profile URL from Grailed listing page."""
    try:
        # Look for seller profile link in various possible locations
        # Common patterns: /users/username, /sellers/username, profile links
        
        # Try to find seller link in JSON data first
        for script in soup.find_all('script'):
            if script.string and ('seller' in script.string or 'user' in script.string):
                # Look for patterns like "seller":{"username":"someuser"} or "user":{"username":"someuser"}
                username_match = re.search(r'"(?:seller|user)"\s*:\s*\{[^}]*"username"\s*:\s*"([^"]+)"', script.string)
                if username_match:
                    username = username_match.group(1)
                    return f"https://www.grailed.com/users/{username}"
                
                # Look for direct profile URL patterns
                profile_match = re.search(r'"(?:profileUrl|userUrl|sellerUrl)"\s*:\s*"([^"]+)"', script.string)
                if profile_match:
                    url = profile_match.group(1)
                    if url.startswith('/'):
                        return f"https://www.grailed.com{url}"
                    return url
        
        # Fallback: look for seller links in HTML
        for link in soup.find_all('a', href=True):
            href = link.get('href', '')
            if '/users/' in href or '/sellers/' in href:
                if href.startswith('/'):
                    return f"https://www.grailed.com{href}"
                elif href.startswith('https://www.grailed.com/'):
                    return href
        
        return None
        
    except Exception as e:
        logger.error(f"Error extracting seller profile URL: {e}")
        return None


def fetch_seller_last_update(profile_url: str) -> Optional[datetime]:
    """Fetch the last update date from seller's profile page."""
    try:
        logger.info(f"Fetching seller profile: {profile_url}")
        r = session.get(profile_url, timeout=TIMEOUT)
        r.raise_for_status()
        soup = BeautifulSoup(r.text, 'lxml')
        
        latest_date = None
        
        # Look for listing dates in JSON data
        for script in soup.find_all('script'):
            if script.string and ('listing' in script.string or 'item' in script.string):
                # Find all date patterns in the script
                date_matches = re.findall(r'"(?:updatedAt|createdAt|lastUpdated)"\s*:\s*"([^"]+)"', script.string)
                for date_str in date_matches:
                    try:
                        if 'T' in date_str:
                            date_obj = datetime.fromisoformat(date_str.replace('Z', '+00:00'))
                        else:
                            date_obj = datetime.fromisoformat(date_str)
                        
                        if latest_date is None or date_obj > latest_date:
                            latest_date = date_obj
                    except Exception:
                        continue
        
        # Fallback: look for visible date elements
        if not latest_date:
            # Look for time elements, date spans, etc.
            for time_elem in soup.find_all(['time', 'span'], attrs={'datetime': True}):
                try:
                    date_str = time_elem.get('datetime')
                    date_obj = datetime.fromisoformat(date_str.replace('Z', '+00:00'))
                    if latest_date is None or date_obj > latest_date:
                        latest_date = date_obj
                except Exception:
                    continue
        
        return latest_date
        
    except Exception as e:
        logger.error(f"Error fetching seller profile {profile_url}: {e}")
        return None


def extract_seller_data_grailed(soup: BeautifulSoup) -> Optional[Dict[str, Any]]:
    """Extract seller metadata from Grailed listing page.
    
    Returns:
        Dict with seller data or None if extraction fails:
        - num_reviews: Number of reviews
        - avg_rating: Average rating (0.00-5.00)
        - trusted_badge: Has Trusted Seller badge
        - last_updated: Date of last listing update from seller profile
    """
    try:
        # Extract basic seller info from listing page
        avg_rating = 0.0
        num_reviews = 0
        trusted_badge = False
        
        # Look for seller data in JSON within script tags
        for script in soup.find_all('script'):
            if script.string and 'seller' in script.string and 'rating' in script.string:
                # Try to extract seller info from JSON
                try:
                    # Look for patterns like "seller":{"rating":4.5,"reviewCount":23}
                    seller_match = re.search(r'"seller"\s*:\s*\{[^}]*"rating"\s*:\s*([0-9.]+)[^}]*"reviewCount"\s*:\s*(\d+)[^}]*\}', script.string)
                    if seller_match:
                        avg_rating = float(seller_match.group(1))
                        num_reviews = int(seller_match.group(2))
                        
                        # Look for trusted badge
                        trusted_badge = '"trustedSeller":true' in script.string or '"trusted":true' in script.string
                        break
                except Exception:
                    continue
        
        # Get seller profile URL and fetch last update date
        profile_url = extract_seller_profile_url(soup)
        last_updated = None
        
        if profile_url:
            last_updated = fetch_seller_last_update(profile_url)
        
        # If no last_updated found, use current time as fallback
        if not last_updated:
            logger.warning("Could not determine seller's last update date, using current time")
            last_updated = datetime.now(timezone.utc)
        
        # Only return data if we have basic seller info
        if avg_rating > 0 or num_reviews > 0:
            return {
                'num_reviews': num_reviews,
                'avg_rating': avg_rating,
                'trusted_badge': trusted_badge,
                'last_updated': last_updated
            }
        
        return None
        
    except Exception as e:
        logger.error(f"Error extracting seller data: {e}")
        return None


def is_grailed_seller_profile(url: str) -> bool:
    """Check if URL is a Grailed seller profile."""
    try:
        parsed = urlparse(url)
        if 'grailed.com' not in parsed.netloc.lower():
            return False
        
        path = parsed.path.lower()
        # Common seller profile patterns
        return '/users/' in path or '/sellers/' in path or '/user/' in path
    except Exception:
        return False


def analyze_seller_profile(profile_url: str) -> Optional[Dict[str, Any]]:
    """Analyze Grailed seller profile and return reliability data.
    
    Returns:
        Dict with seller analysis or None if extraction fails:
        - Basic seller info (reviews, rating, badge, last_updated)
        - Reliability evaluation (scores, category, description)
    """
    try:
        logger.info(f"Analyzing seller profile: {profile_url}")
        r = session.get(profile_url, timeout=TIMEOUT)
        r.raise_for_status()
        soup = BeautifulSoup(r.text, 'lxml')
        
        # Extract seller data from profile page
        avg_rating = 0.0
        num_reviews = 0
        trusted_badge = False
        
        # Look for seller data in JSON within script tags
        for script in soup.find_all('script'):
            if script.string and ('rating' in script.string or 'review' in script.string):
                try:
                    # Look for patterns like "rating":4.5,"reviewCount":23
                    rating_match = re.search(r'"rating"\s*:\s*([0-9.]+)', script.string)
                    if rating_match:
                        avg_rating = float(rating_match.group(1))
                    
                    review_match = re.search(r'"reviewCount"\s*:\s*(\d+)', script.string)
                    if review_match:
                        num_reviews = int(review_match.group(1))
                    
                    # Look for trusted badge
                    if '"trustedSeller":true' in script.string or '"trusted":true' in script.string:
                        trusted_badge = True
                        
                except Exception:
                    continue
        
        # Get last updated date from profile listings
        last_updated = fetch_seller_last_update(profile_url)
        
        # If no last_updated found, use current time as fallback
        if not last_updated:
            logger.warning("Could not determine seller's last update date, using current time")
            last_updated = datetime.now(timezone.utc)
        
        # Only proceed if we have basic seller info
        if avg_rating > 0 or num_reviews > 0:
            # Evaluate reliability
            reliability = evaluate_seller_reliability(
                num_reviews, avg_rating, trusted_badge, last_updated
            )
            
            return {
                'num_reviews': num_reviews,
                'avg_rating': avg_rating,
                'trusted_badge': trusted_badge,
                'last_updated': last_updated,
                'reliability': reliability
            }
        
        return None
        
    except Exception as e:
        logger.error(f"Error analyzing seller profile {profile_url}: {e}")
        return None


def format_seller_profile_response(seller_data: Dict[str, Any]) -> str:
    """Format seller profile analysis into a readable message."""
    reliability = seller_data['reliability']
    
    # Emoji mapping
    emoji_map = {
        'Diamond': '💎',
        'Gold': '🥇',
        'Silver': '🥈', 
        'Bronze': '🥉',
        'Ghost': '👻'
    }
    emoji = emoji_map.get(reliability['category'], '❓')
    
    # Calculate days since last update
    days_since_update = (datetime.now(timezone.utc) - seller_data['last_updated']).days
    
    # Format last update text
    if days_since_update == 0:
        last_update_text = "сегодня"
    elif days_since_update == 1:
        last_update_text = "вчера"
    elif days_since_update <= 7:
        last_update_text = f"{days_since_update} дн. назад"
    elif days_since_update <= 30:
        last_update_text = f"{days_since_update} дн. назад"
    else:
        last_update_text = f"{days_since_update} дн. назад"
    
    # Badge text
    badge_text = "✅ Проверенный продавец" if seller_data['trusted_badge'] else "❌ Нет бейджа"
    
    response_lines = [
        f"{emoji} Анализ продавца Grailed",
        "",
        f"Надёжность: {reliability['category']} ({reliability['total_score']}/100)",
        f"{reliability['description']}",
        "",
        "Детали:",
        f"• Активность: {reliability['activity_score']}/30 (обновления {last_update_text})",
        f"• Рейтинг: {reliability['rating_score']}/35 ({seller_data['avg_rating']:.1f}/5.0)",
        f"• Отзывы: {reliability['review_volume_score']}/25 ({seller_data['num_reviews']} отзывов)",
        f"• Бейдж: {reliability['badge_score']}/10 ({badge_text})",
    ]
    
    return "\n".join(response_lines)


def get_price_and_shipping(url: str) -> tuple[Optional[Decimal], Optional[Decimal], bool, Optional[Dict[str, Any]]]:
    """Get price, shipping cost, buyability status, and seller data for a URL.
    
    Returns:
        tuple: (price, shipping, is_buyable, seller_data)
        - For eBay: is_buyable is always True, seller_data is None
        - For Grailed: is_buyable depends on button presence, seller_data extracted
    """
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
            return None, None, False, None
    
    try:
        r = session.get(url, timeout=TIMEOUT)
        r.raise_for_status()
        soup = BeautifulSoup(r.text, 'lxml')
    except Exception as e:
        logger.error(f"Request error: {e}")
        return None, None, False, None
    
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
        return price, shipping, True, None  # eBay items are always buyable, no seller data
    
    if 'grailed' in labels:
        price, is_buyable = scrape_price_grailed(url)
        shipping = scrape_shipping_grailed(soup)
        seller_data = extract_seller_data_grailed(soup)
        return price, shipping, is_buyable, seller_data
    
    return None, None, False, None

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(
        "Пришлите ссылку на товар с eBay или Grailed. Бот рассчитает стоимость с доставкой и комиссией.\n\n"
        "Комиссия: $15 для товаров дешевле $150, или 10% для товаров от $150.\n"
        "Цены показываются в долларах и рублях по курсу ЦБ РФ + 5%."
    )

async def handle_link(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    text = update.message.text or ''
    urls = re.findall(r"(https?://[\w\.-]+(?:/[^\s]*)?)", text)
    if not urls:
        return
    
    # Check if any URLs are Grailed seller profiles
    for url in urls:
        if is_grailed_seller_profile(url):
            try:
                seller_data = await asyncio.to_thread(analyze_seller_profile, url)
                if seller_data:
                    response = format_seller_profile_response(seller_data)
                    await update.message.reply_text(response)
                else:
                    await update.message.reply_text(f"Не удалось получить данные о продавце")
            except Exception as e:
                logger.error(f"Error processing seller profile {url}: {e}")
                await update.message.reply_text("Ошибка при анализе продавца")
            return  # Exit after processing seller profile
    
    # Continue with regular listing processing if no seller profiles found
    # Fetch all URLs concurrently for performance
    tasks = [asyncio.to_thread(get_price_and_shipping, u) for u in urls]
    results = await asyncio.gather(*tasks)
    
    # Get USD to RUB rate once for all conversions
    logger.info("Getting USD to RUB exchange rate...")
    usd_to_rub_rate = await asyncio.to_thread(get_usd_to_rub_rate)
    if usd_to_rub_rate:
        logger.info(f"Successfully got exchange rate: {usd_to_rub_rate}")
    else:
        logger.error("CBR API failed - currency conversion unavailable")
        # Notify admin about CBR API failure
        await notify_admin(
            context.application,
            "CBR API is unavailable. Currency conversion disabled. Check logs for details."
        )
    
    for u, (price, shipping, is_buyable, seller_data) in zip(urls, results):
        if not price:
            await update.message.reply_text("Не удалось получить цену товара")
        elif not is_buyable:
            # For items without buy-now option (only offer button)
            await update.message.reply_text(
                f"У продавца не указана цена выкупа. Для расчёта полной стоимости товара необходимо связаться с продавцом.\n\n"
                f"Указанная цена: ${price} (только для переговоров)"
            )
        else:
            shipping = shipping or Decimal('0')
            total_cost = price + shipping
            
            # New pricing logic: fixed $15 commission if item price < $150, otherwise 10% markup
            if price < Decimal('150'):
                final_price = (total_cost + Decimal('15')).quantize(Decimal('0.01'), ROUND_HALF_UP)
                commission_text = "комиссия $15"
            else:
                final_price = (total_cost * Decimal('1.10')).quantize(Decimal('0.01'), ROUND_HALF_UP)
                commission_text = "наценка 10%"
            
            shipping_text = f" + ${shipping} доставка" if shipping > 0 else " (бесплатная доставка)"
            
            # Convert to RUB if rate is available
            rub_text = ""
            if usd_to_rub_rate:
                final_price_rub = (final_price * usd_to_rub_rate).quantize(Decimal('0.01'), ROUND_HALF_UP)
                rub_text = f" (₽{final_price_rub})"
                logger.info(f"Converted ${final_price} to ₽{final_price_rub} using rate {usd_to_rub_rate}")
            else:
                logger.warning("No exchange rate available, showing USD only")
            
            # Prepare base response message
            response_lines = [
                f"Цена: ${price}{shipping_text} = ${total_cost}",
                f"С учетом {commission_text}: ${final_price}{rub_text}"
            ]
            
            # Add seller reliability info for Grailed items with buyout price
            if seller_data and 'grailed' in u.lower():
                try:
                    reliability = evaluate_seller_reliability(
                        seller_data['num_reviews'],
                        seller_data['avg_rating'],
                        seller_data['trusted_badge'],
                        seller_data['last_updated']
                    )
                    
                    # Format seller reliability info
                    emoji_map = {
                        'Diamond': '💎',
                        'Gold': '🥇',
                        'Silver': '🥈',
                        'Bronze': '🥉',
                        'Ghost': '👻'
                    }
                    emoji = emoji_map.get(reliability['category'], '❓')
                    
                    response_lines.append("")  # Empty line for separation
                    response_lines.append(f"{emoji} Продавец: {reliability['category']} ({reliability['total_score']}/100)")
                    response_lines.append(f"📊 {reliability['description']}")
                    
                except Exception as e:
                    logger.error(f"Error evaluating seller reliability: {e}")
            
            await update.message.reply_text("\n".join(response_lines))


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