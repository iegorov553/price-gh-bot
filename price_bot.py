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

from messages import (
    START_MESSAGE, ERROR_PRICE_NOT_FOUND, ERROR_SELLER_DATA_NOT_FOUND, 
    ERROR_SELLER_ANALYSIS, OFFER_ONLY_MESSAGE, COMMISSION_FIXED, 
    COMMISSION_PERCENTAGE, SHIPPING_FREE, SHIPPING_PAID, PRICE_LINE,
    FINAL_PRICE_LINE, SELLER_RELIABILITY, GHOST_INACTIVE_DESCRIPTION,
    SELLER_PROFILE_HEADER, SELLER_RELIABILITY_LINE, SELLER_DETAILS_HEADER,
    SELLER_ACTIVITY_LINE, SELLER_RATING_LINE, SELLER_REVIEWS_LINE,
    SELLER_BADGE_LINE, TRUSTED_SELLER_BADGE, NO_BADGE, TIME_TODAY,
    TIME_YESTERDAY, TIME_DAYS_AGO, SELLER_INFO_LINE, SELLER_DESCRIPTION_LINE,
    ADMIN_NOTIFICATION, LOG_CBR_API_FAILED
)

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
            'description': GHOST_INACTIVE_DESCRIPTION
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
        description = SELLER_RELIABILITY['Diamond']['description']
    elif total_score >= 70:
        category = 'Gold'
        description = SELLER_RELIABILITY['Gold']['description']
    elif total_score >= 55:
        category = 'Silver'
        description = SELLER_RELIABILITY['Silver']['description']
    elif total_score >= 40:
        category = 'Bronze'
        description = SELLER_RELIABILITY['Bronze']['description']
    else:
        category = 'Ghost'
        description = SELLER_RELIABILITY['Ghost']['description']
    
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
            text=ADMIN_NOTIFICATION.format(message=message)
        )
        logger.info(f"Admin notification sent: {message}")
    except Exception as e:
        logger.error(f"Failed to send admin notification: {e}")

async def send_debug_to_admin(application, message: str) -> None:
    """Send debug message to admin only (not to users)"""
    try:
        await application.bot.send_message(
            chat_id=ADMIN_CHAT_ID,
            text=f"🔧 Debug: {message}"
        )
    except Exception as e:
        logger.debug(f"Failed to send debug message to admin: {e}")

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
        logger.debug("Extracting seller profile URL from listing page...")
        
        # Try to find seller link in JSON data first
        scripts_checked = 0
        for script in soup.find_all('script'):
            scripts_checked += 1
            if script.string and ('seller' in script.string or 'user' in script.string):
                logger.debug(f"Found script with seller/user data (script #{scripts_checked})")
                
                # Look for patterns like "seller":{"username":"someuser"} or "user":{"username":"someuser"}
                username_match = re.search(r'"(?:seller|user)"\s*:\s*\{[^}]*"username"\s*:\s*"([^"]+)"', script.string)
                if username_match:
                    username = username_match.group(1)
                    profile_url = f"https://www.grailed.com/{username}"
                    logger.debug(f"Found username in JSON: {username} -> {profile_url}")
                    return profile_url
                
                # Look for direct profile URL patterns
                profile_match = re.search(r'"(?:profileUrl|userUrl|sellerUrl)"\s*:\s*"([^"]+)"', script.string)
                if profile_match:
                    url = profile_match.group(1)
                    if url.startswith('/'):
                        full_url = f"https://www.grailed.com{url}"
                        logger.debug(f"Found relative profile URL: {url} -> {full_url}")
                        return full_url
                    logger.debug(f"Found absolute profile URL: {url}")
                    return url
        
        logger.debug(f"Checked {scripts_checked} scripts for seller profile URL")
        
        # Fallback: look for seller links in HTML
        links_checked = 0
        for link in soup.find_all('a', href=True):
            links_checked += 1
            href = link.get('href', '')
            
            # Check for various profile URL patterns
            if ('/users/' in href or '/sellers/' in href or 
                (href.startswith('/') and href.count('/') == 2 and 
                 not href.startswith('/listings') and not href.startswith('/search'))):
                
                if href.startswith('/'):
                    full_url = f"https://www.grailed.com{href}"
                    logger.debug(f"Found seller link in HTML: {href} -> {full_url}")
                    return full_url
                elif href.startswith('https://www.grailed.com/'):
                    logger.debug(f"Found full seller link in HTML: {href}")
                    return href
        
        logger.debug(f"Checked {links_checked} HTML links, no seller profile URL found")
        return None
        
    except Exception as e:
        logger.error(f"Error extracting seller profile URL: {e}")
        return None


def fetch_seller_last_update(profile_url: str) -> Optional[datetime]:
    """Fetch the last update date from seller's profile page."""
    try:
        logger.debug(f"Fetching seller last update from: {profile_url}")
        r = session.get(profile_url, timeout=TIMEOUT)
        r.raise_for_status()
        soup = BeautifulSoup(r.text, 'lxml')
        
        latest_date = None
        dates_found = []
        
        # Look for listing dates in JSON data with multiple patterns
        scripts_checked = 0
        for script in soup.find_all('script'):
            scripts_checked += 1
            if not script.string:
                continue
                
            script_content = script.string
            
            # Look for various date patterns
            if any(keyword in script_content for keyword in ['date', 'time', 'created', 'updated', 'listing']):
                logger.debug(f"Found script with date keywords (date script #{scripts_checked})")
                
                # Multiple date field patterns
                date_patterns = [
                    r'"(?:updatedAt|lastUpdated|dateUpdated)"\s*:\s*"([^"]+)"',
                    r'"(?:createdAt|dateCreated|created)"\s*:\s*"([^"]+)"',
                    r'"(?:publishedAt|datePublished)"\s*:\s*"([^"]+)"',
                    r'"(?:date|timestamp)"\s*:\s*"([^"]+)"',
                    r'"(?:listingDate|itemDate)"\s*:\s*"([^"]+)"',
                    # ISO datetime patterns
                    r'"(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:\d{2}))"',
                    # Epoch timestamps
                    r'"(?:time|date)"\s*:\s*(\d{10,13})',
                ]
                
                for pattern in date_patterns:
                    date_matches = re.findall(pattern, script_content, re.IGNORECASE)
                    for date_str in date_matches:
                        try:
                            # Handle different date formats
                            if date_str.isdigit():
                                # Epoch timestamp
                                timestamp = int(date_str)
                                if timestamp > 1000000000000:  # Milliseconds
                                    timestamp = timestamp / 1000
                                date_obj = datetime.fromtimestamp(timestamp, tz=timezone.utc)
                            elif 'T' in date_str:
                                # ISO format
                                date_obj = datetime.fromisoformat(date_str.replace('Z', '+00:00'))
                            else:
                                # Try parsing as ISO date
                                date_obj = datetime.fromisoformat(date_str)
                                if date_obj.tzinfo is None:
                                    date_obj = date_obj.replace(tzinfo=timezone.utc)
                            
                            dates_found.append(date_obj)
                            if latest_date is None or date_obj > latest_date:
                                latest_date = date_obj
                                logger.debug(f"Found newer date: {latest_date}")
                                
                        except Exception as e:
                            logger.debug(f"Error parsing date '{date_str}': {e}")
                            continue
        
        logger.debug(f"Checked {scripts_checked} scripts, found {len(dates_found)} dates")
        
        # Fallback: look for visible date elements in HTML
        if not latest_date:
            logger.debug("No dates found in scripts, checking HTML elements...")
            
            # Look for time elements, date spans, etc.
            date_selectors = [
                'time[datetime]', '[data-date]', '[data-timestamp]',
                '.date', '.timestamp', '.time', '[class*="date"]',
                '[class*="time"]', '.listing-date', '.updated'
            ]
            
            for selector in date_selectors:
                elements = soup.select(selector)
                for element in elements:
                    # Try datetime attribute first
                    date_str = element.get('datetime') or element.get('data-date') or element.get('data-timestamp')
                    if not date_str:
                        # Try element text
                        date_str = element.get_text(strip=True)
                        # Look for date-like patterns in text
                        date_match = re.search(r'(\d{4}-\d{2}-\d{2})', date_str)
                        if date_match:
                            date_str = date_match.group(1)
                    
                    if date_str:
                        try:
                            if date_str.isdigit():
                                timestamp = int(date_str)
                                if timestamp > 1000000000000:
                                    timestamp = timestamp / 1000
                                date_obj = datetime.fromtimestamp(timestamp, tz=timezone.utc)
                            else:
                                date_obj = datetime.fromisoformat(date_str.replace('Z', '+00:00'))
                                if date_obj.tzinfo is None:
                                    date_obj = date_obj.replace(tzinfo=timezone.utc)
                            
                            if latest_date is None or date_obj > latest_date:
                                latest_date = date_obj
                                logger.debug(f"Found date in HTML: {latest_date}")
                                
                        except Exception as e:
                            logger.debug(f"Error parsing HTML date '{date_str}': {e}")
                            continue
        
        if latest_date:
            logger.debug(f"Latest update date found: {latest_date}")
        else:
            logger.debug("No update date found on profile page")
            
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
        logger.debug("Extracting seller data from listing page...")
        
        # Extract basic seller info from listing page
        avg_rating = 0.0
        num_reviews = 0
        trusted_badge = False
        
        # Look for seller data in JSON within script tags
        scripts_checked = 0
        found_data = False
        
        for script in soup.find_all('script'):
            scripts_checked += 1
            if not script.string:
                continue
                
            script_content = script.string
            
            # Check multiple patterns for seller data
            if any(keyword in script_content for keyword in ['seller', 'user', 'rating', 'review']):
                logger.debug(f"Found script with seller keywords (script #{scripts_checked})")
                
                try:
                    # Pattern 1: Look for JSON-LD or structured data
                    json_ld_match = re.search(r'"@type"\s*:\s*"Person"[^}]*"name"\s*:\s*"([^"]+)"', script_content)
                    if json_ld_match:
                        logger.debug(f"Found structured person data: {json_ld_match.group(1)}")
                    
                    # Pattern 2: Modern React/GraphQL data patterns
                    # Look for user objects with rating and review data
                    user_patterns = [
                        r'"user"\s*:\s*\{[^}]*"rating"\s*:\s*([0-9.]+)[^}]*"reviewCount"\s*:\s*(\d+)',
                        r'"seller"\s*:\s*\{[^}]*"rating"\s*:\s*([0-9.]+)[^}]*"reviewCount"\s*:\s*(\d+)',
                        r'"averageRating"\s*:\s*([0-9.]+)[^,}]*"totalReviews"\s*:\s*(\d+)',
                        r'"rating"\s*:\s*([0-9.]+)[^,}]*"reviews"\s*:\s*(\d+)',
                        r'rating["\']?\s*:\s*([0-9.]+)[^,}]*review[sC]ount["\']?\s*:\s*(\d+)',
                    ]
                    
                    for pattern in user_patterns:
                        seller_match = re.search(pattern, script_content, re.IGNORECASE)
                        if seller_match:
                            avg_rating = float(seller_match.group(1))
                            num_reviews = int(seller_match.group(2))
                            logger.debug(f"Pattern matched - Rating: {avg_rating}, Reviews: {num_reviews}")
                            found_data = True
                            break
                    
                    if found_data:
                        # Look for trusted badge with various patterns
                        trusted_patterns = [
                            r'"trustedSeller"\s*:\s*true',
                            r'"trusted"\s*:\s*true',
                            r'"isTrusted"\s*:\s*true',
                            r'"verified"\s*:\s*true',
                            r'trustedSeller["\']?\s*:\s*true',
                        ]
                        
                        for pattern in trusted_patterns:
                            if re.search(pattern, script_content, re.IGNORECASE):
                                trusted_badge = True
                                logger.debug("Found trusted seller badge")
                                break
                        
                        break
                        
                except Exception as e:
                    logger.debug(f"Error parsing script #{scripts_checked}: {e}")
                    continue
        
        logger.debug(f"Checked {scripts_checked} scripts, found rating: {avg_rating}, reviews: {num_reviews}")
        
        # If no data found in scripts, try to extract from profile directly
        if not found_data:
            logger.debug("No seller data found in listing scripts, will extract from profile")
            profile_url = extract_seller_profile_url(soup)
            logger.debug(f"Extracted seller profile URL: {profile_url}")
            
            if profile_url:
                # Get data directly from seller profile
                profile_data = analyze_seller_profile(profile_url)
                if profile_data:
                    logger.info(f"Retrieved seller data from profile: rating={profile_data.get('avg_rating', 0)}, reviews={profile_data.get('num_reviews', 0)}")
                    return profile_data
        
        # Get seller profile URL and fetch last update date
        profile_url = extract_seller_profile_url(soup) if not 'profile_url' in locals() else profile_url
        last_updated = None
        
        if profile_url:
            last_updated = fetch_seller_last_update(profile_url)
            logger.debug(f"Fetched last update: {last_updated}")
        
        # If no last_updated found, use current time as fallback
        if not last_updated:
            logger.warning("Could not determine seller's last update date, using current time")
            last_updated = datetime.now(timezone.utc)
        
        # Only return data if we have basic seller info
        if avg_rating > 0 or num_reviews > 0 or found_data:
            logger.info(f"Successfully extracted seller data: rating={avg_rating}, reviews={num_reviews}, badge={trusted_badge}")
            return {
                'num_reviews': num_reviews,
                'avg_rating': avg_rating,
                'trusted_badge': trusted_badge,
                'last_updated': last_updated
            }
        
        logger.warning("No seller data found in listing page")
        return None
        
    except Exception as e:
        logger.error(f"Error extracting seller data: {e}")
        return None


def is_grailed_seller_profile(url: str) -> bool:
    """Check if URL is a Grailed seller profile."""
    try:
        parsed = urlparse(url)
        if 'grailed.com' not in parsed.netloc.lower():
            logger.debug(f"Not a Grailed domain: {parsed.netloc}")
            return False
        
        path = parsed.path.lower().strip('/')
        logger.debug(f"Checking path for seller profile: '{path}'")
        
        # Updated patterns based on actual Grailed URLs:
        # 1. /users/username (old pattern)
        # 2. /sellers/username (old pattern) 
        # 3. /username (new direct pattern)
        # 4. Exclude listing URLs like /listings/12345
        
        # Check for direct username pattern (most common now)
        if path and '/' not in path and not path.startswith('listings'):
            # Exclude common non-profile pages
            excluded_pages = {'sell', 'buy', 'search', 'help', 'about', 'terms', 
                             'privacy', 'brands', 'designers', 'categories', 'login', 
                             'signup', 'settings', 'notifications', 'feed'}
            if path not in excluded_pages:
                logger.info(f"Detected direct seller profile pattern: {url}")
                return True
        
        # Check for legacy patterns
        if path.startswith('users/') or path.startswith('sellers/') or path.startswith('user/'):
            logger.info(f"Detected legacy seller profile pattern: {url}")
            return True
            
        logger.debug(f"URL does not match seller profile patterns: {url}")
        return False
        
    except Exception as e:
        logger.error(f"Error checking seller profile URL: {e}")
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
        logger.debug(f"Profile page loaded successfully, status: {r.status_code}")
        soup = BeautifulSoup(r.text, 'lxml')
        
        # Extract seller data from profile page
        avg_rating = 0.0
        num_reviews = 0
        trusted_badge = False
        found_data = False
        
        # Look for seller data in JSON within script tags
        scripts_checked = 0
        for script in soup.find_all('script'):
            scripts_checked += 1
            if not script.string:
                continue
                
            script_content = script.string
            
            # Check for seller-related data
            if any(keyword in script_content for keyword in ['rating', 'review', 'user', 'seller', 'trusted']):
                logger.debug(f"Found script with seller keywords (profile script #{scripts_checked})")
                
                try:
                    # Multiple patterns for extracting rating and review data
                    patterns = [
                        # Standard patterns
                        (r'"rating"\s*:\s*([0-9.]+)', r'"reviewCount"\s*:\s*(\d+)'),
                        (r'"averageRating"\s*:\s*([0-9.]+)', r'"totalReviews"\s*:\s*(\d+)'),
                        (r'"userRating"\s*:\s*([0-9.]+)', r'"userReviews"\s*:\s*(\d+)'),
                        # Variations
                        (r'rating["\']?\s*:\s*([0-9.]+)', r'review[sC]ount["\']?\s*:\s*(\d+)'),
                        (r'"stars"\s*:\s*([0-9.]+)', r'"reviews"\s*:\s*(\d+)'),
                    ]
                    
                    for rating_pattern, review_pattern in patterns:
                        rating_match = re.search(rating_pattern, script_content, re.IGNORECASE)
                        review_match = re.search(review_pattern, script_content, re.IGNORECASE)
                        
                        if rating_match and review_match:
                            avg_rating = float(rating_match.group(1))
                            num_reviews = int(review_match.group(1))
                            logger.debug(f"Extracted from profile - Rating: {avg_rating}, Reviews: {num_reviews}")
                            found_data = True
                            break
                        elif rating_match:
                            avg_rating = float(rating_match.group(1))
                            logger.debug(f"Found rating: {avg_rating}")
                        elif review_match:
                            num_reviews = int(review_match.group(1))
                            logger.debug(f"Found reviews: {num_reviews}")
                    
                    # Look for trusted badge
                    trusted_patterns = [
                        r'"trustedSeller"\s*:\s*true',
                        r'"trusted"\s*:\s*true',
                        r'"isTrusted"\s*:\s*true',
                        r'"verified"\s*:\s*true',
                        r'"badge"\s*:\s*["\']?trusted["\']?',
                        r'trustedSeller["\']?\s*:\s*true',
                    ]
                    
                    for pattern in trusted_patterns:
                        if re.search(pattern, script_content, re.IGNORECASE):
                            trusted_badge = True
                            logger.debug("Found trusted seller badge in profile")
                            break
                            
                except Exception as e:
                    logger.debug(f"Error parsing profile script #{scripts_checked}: {e}")
                    continue
        
        logger.debug(f"Profile analysis: checked {scripts_checked} scripts, rating={avg_rating}, reviews={num_reviews}, trusted={trusted_badge}")
        
        # If still no data, try HTML parsing for visible elements
        if not found_data and avg_rating == 0 and num_reviews == 0:
            logger.debug("No data found in scripts, trying HTML parsing...")
            
            # Look for rating in HTML elements
            rating_selectors = [
                '[data-rating]', '.rating', '.stars', '[class*="rating"]',
                '[class*="star"]', '.review-score', '.seller-rating'
            ]
            
            for selector in rating_selectors:
                elements = soup.select(selector)
                for element in elements:
                    text = element.get_text(strip=True)
                    rating_match = re.search(r'([0-9.]+)', text)
                    if rating_match:
                        try:
                            potential_rating = float(rating_match.group(1))
                            if 0 <= potential_rating <= 5:
                                avg_rating = potential_rating
                                logger.debug(f"Found rating in HTML: {avg_rating}")
                                break
                        except ValueError:
                            continue
                
                if avg_rating > 0:
                    break
        
        # Get last updated date from profile listings
        last_updated = fetch_seller_last_update(profile_url)
        
        # If no last_updated found, use current time as fallback
        if not last_updated:
            logger.warning("Could not determine seller's last update date, using current time")
            last_updated = datetime.now(timezone.utc)
        
        # For profiles, we might not have rating data but still want to show analysis
        # Create minimal data even if no reviews/rating found
        logger.info(f"Profile analysis complete - Rating: {avg_rating}, Reviews: {num_reviews}, Trusted: {trusted_badge}")
        
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
        
    except Exception as e:
        logger.error(f"Error analyzing seller profile {profile_url}: {e}")
        return None


def format_seller_profile_response(seller_data: Dict[str, Any]) -> str:
    """Format seller profile analysis into a readable message."""
    reliability = seller_data['reliability']
    
    emoji = SELLER_RELIABILITY.get(reliability['category'], {}).get('emoji', '❓')
    
    # Calculate days since last update
    days_since_update = (datetime.now(timezone.utc) - seller_data['last_updated']).days
    
    # Format last update text
    if days_since_update == 0:
        last_update_text = TIME_TODAY
    elif days_since_update == 1:
        last_update_text = TIME_YESTERDAY
    else:
        last_update_text = TIME_DAYS_AGO.format(days=days_since_update)
    
    # Badge text
    badge_text = TRUSTED_SELLER_BADGE if seller_data['trusted_badge'] else NO_BADGE
    
    response_lines = [
        SELLER_PROFILE_HEADER.format(emoji=emoji),
        "",
        SELLER_RELIABILITY_LINE.format(
            category=reliability['category'],
            total_score=reliability['total_score']
        ),
        reliability['description'],
        "",
        SELLER_DETAILS_HEADER,
        SELLER_ACTIVITY_LINE.format(
            activity_score=reliability['activity_score'],
            last_update_text=last_update_text
        ),
        SELLER_RATING_LINE.format(
            rating_score=reliability['rating_score'],
            avg_rating=seller_data['avg_rating']
        ),
        SELLER_REVIEWS_LINE.format(
            review_volume_score=reliability['review_volume_score'],
            num_reviews=seller_data['num_reviews']
        ),
        SELLER_BADGE_LINE.format(
            badge_score=reliability['badge_score'],
            badge_text=badge_text
        ),
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
        logger.debug(f"Grailed extraction results: price={price}, shipping={shipping}, buyable={is_buyable}, seller_data={'yes' if seller_data else 'no'}")
        return price, shipping, is_buyable, seller_data
    
    return None, None, False, None

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(START_MESSAGE)

async def handle_link(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    text = update.message.text or ''
    urls = re.findall(r"(https?://[\w\.-]+(?:/[^\s]*)?)", text)
    if not urls:
        return
    
    # Check if any URLs are Grailed seller profiles
    for url in urls:
        logger.info(f"Checking URL: {url}")
        if is_grailed_seller_profile(url):
            logger.info(f"Processing seller profile: {url}")
            try:
                seller_data = await asyncio.to_thread(analyze_seller_profile, url)
                if seller_data:
                    response = format_seller_profile_response(seller_data)
                    await update.message.reply_text(response)
                else:
                    await update.message.reply_text(ERROR_SELLER_DATA_NOT_FOUND)
            except Exception as e:
                logger.error(f"Error processing seller profile {url}: {e}")
                await update.message.reply_text(ERROR_SELLER_ANALYSIS)
                # Send debug info to admin only
                await send_debug_to_admin(context.application, f"Seller profile error for {url}: {e}")
            return  # Exit after processing seller profile
        else:
            logger.debug(f"URL is not a seller profile: {url}")
    
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
            LOG_CBR_API_FAILED
        )
    
    for u, (price, shipping, is_buyable, seller_data) in zip(urls, results):
        if not price:
            await update.message.reply_text(ERROR_PRICE_NOT_FOUND)
        elif not is_buyable:
            # For items without buy-now option (only offer button)
            await update.message.reply_text(
                OFFER_ONLY_MESSAGE.format(price=price)
            )
        else:
            shipping = shipping or Decimal('0')
            total_cost = price + shipping
            
            # New pricing logic: fixed $15 commission if item price < $150, otherwise 10% markup
            if price < Decimal('150'):
                final_price = (total_cost + Decimal('15')).quantize(Decimal('0.01'), ROUND_HALF_UP)
                commission_text = COMMISSION_FIXED
            else:
                final_price = (total_cost * Decimal('1.10')).quantize(Decimal('0.01'), ROUND_HALF_UP)
                commission_text = COMMISSION_PERCENTAGE
            
            shipping_text = SHIPPING_PAID.format(shipping=shipping) if shipping > 0 else SHIPPING_FREE
            
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
                PRICE_LINE.format(
                    price=price,
                    shipping_text=shipping_text,
                    total_cost=total_cost
                ),
                FINAL_PRICE_LINE.format(
                    commission_text=commission_text,
                    final_price=final_price,
                    rub_text=rub_text
                )
            ]
            
            # Add seller reliability info for Grailed items with buyout price
            if seller_data and 'grailed' in u.lower():
                logger.info(f"Processing seller reliability for Grailed item. Seller data: reviews={seller_data.get('num_reviews', 0)}, rating={seller_data.get('avg_rating', 0)}")
                try:
                    reliability = evaluate_seller_reliability(
                        seller_data['num_reviews'],
                        seller_data['avg_rating'],
                        seller_data['trusted_badge'],
                        seller_data['last_updated']
                    )
                    
                    # Format seller reliability info
                    emoji = SELLER_RELIABILITY.get(reliability['category'], {}).get('emoji', '❓')
                    
                    response_lines.append("")  # Empty line for separation
                    response_lines.append(SELLER_INFO_LINE.format(
                        emoji=emoji,
                        category=reliability['category'],
                        total_score=reliability['total_score']
                    ))
                    response_lines.append(SELLER_DESCRIPTION_LINE.format(
                        description=reliability['description']
                    ))
                    
                    logger.info(f"Added seller reliability info: {reliability['category']} ({reliability['total_score']}/100)")
                    
                except Exception as e:
                    logger.error(f"Error evaluating seller reliability: {e}")
            elif 'grailed' in u.lower():
                logger.warning(f"No seller data found for Grailed item: {u}")
                # Notify admin about missing seller data for debugging
                await send_debug_to_admin(context.application, f"No seller data extracted for Grailed item: {u}")
            else:
                logger.debug(f"Not a Grailed item, skipping seller analysis: {u}")
            
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