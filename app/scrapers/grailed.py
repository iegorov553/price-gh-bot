"""Grailed scraper implementation."""

import json
import re
from datetime import datetime, timezone
from decimal import Decimal
from typing import Optional, Tuple, Dict, Any
from urllib.parse import urlparse

import aiohttp
from bs4 import BeautifulSoup

from ..models import ItemData, SellerData


PRICE_RE = re.compile(r"^\d[\d,.]*$")


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


def _scrape_shipping_grailed(soup: BeautifulSoup) -> Optional[Decimal]:
    """Extract Grailed shipping cost."""
    # Look for shipping text
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
    
    # Look for shipping div
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
    
    # Default Grailed shipping
    return Decimal('15')


def _extract_title(soup: BeautifulSoup) -> Optional[str]:
    """Extract item title."""
    og = soup.find("meta", property="og:title")
    if og and og.get("content"):
        return og["content"]
    h1 = soup.find("h1")
    if h1:
        return h1.get_text(strip=True)
    return None


def _extract_price_and_buyability(url: str, soup: BeautifulSoup) -> Tuple[Optional[Decimal], bool]:
    """Extract price and determine if item is buyable."""
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
    
    # Check buyability from JSON data
    is_buyable = False
    try:
        for script in soup.find_all('script'):
            if script.string and 'buyNow' in script.string:
                buy_now_match = re.search(r'"buyNow"\s*:\s*(true|false)', script.string)
                if buy_now_match:
                    is_buyable = buy_now_match.group(1) == 'true'
                    break
    except Exception:
        # Fallback: assume buyable if price is found
        is_buyable = price is not None
    
    return price, is_buyable


def _extract_seller_profile_url(soup: BeautifulSoup) -> Optional[str]:
    """Extract seller profile URL from listing page."""
    try:
        # Try JSON data first
        for script in soup.find_all('script'):
            if script.string and ('seller' in script.string or 'user' in script.string):
                # Look for username patterns
                username_match = re.search(
                    r'"(?:seller|user)"\s*:\s*\{[^}]*"username"\s*:\s*"([^"]+)"', 
                    script.string
                )
                if username_match:
                    username = username_match.group(1)
                    return f"https://www.grailed.com/{username}"
                
                # Look for direct profile URL patterns
                profile_match = re.search(
                    r'"(?:profileUrl|userUrl|sellerUrl)"\s*:\s*"([^"]+)"', 
                    script.string
                )
                if profile_match:
                    url = profile_match.group(1)
                    if url.startswith('/'):
                        return f"https://www.grailed.com{url}"
                    return url
        
        # Fallback: HTML links
        for link in soup.find_all('a', href=True):
            href = link.get('href', '')
            if ('/users/' in href or '/sellers/' in href or 
                (href.startswith('/') and href.count('/') == 2 and 
                 not href.startswith('/listings') and not href.startswith('/search'))):
                
                if href.startswith('/'):
                    return f"https://www.grailed.com{href}"
                elif href.startswith('https://www.grailed.com/'):
                    return href
        
        return None
    except Exception:
        return None


async def _fetch_seller_last_update(profile_url: str, session: aiohttp.ClientSession) -> Optional[datetime]:
    """Fetch seller's last update date from profile."""
    try:
        async with session.get(profile_url) as response:
            response.raise_for_status()
            html = await response.text()
        
        soup = BeautifulSoup(html, 'lxml')
        latest_date = None
        
        # Look for dates in JSON scripts
        for script in soup.find_all('script'):
            if not script.string:
                continue
                
            script_content = script.string
            if any(keyword in script_content for keyword in ['date', 'time', 'created', 'updated']):
                date_patterns = [
                    r'"(?:updatedAt|lastUpdated|dateUpdated)"\s*:\s*"([^"]+)"',
                    r'"(?:createdAt|dateCreated|created)"\s*:\s*"([^"]+)"',
                    r'"(?:publishedAt|datePublished)"\s*:\s*"([^"]+)"',
                    r'"(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:\d{2}))"',
                    r'"(?:time|date)"\s*:\s*(\d{10,13})',
                ]
                
                for pattern in date_patterns:
                    for date_str in re.findall(pattern, script_content, re.IGNORECASE):
                        try:
                            if date_str.isdigit():
                                timestamp = int(date_str)
                                if timestamp > 1000000000000:
                                    timestamp = timestamp / 1000
                                date_obj = datetime.fromtimestamp(timestamp, tz=timezone.utc)
                            elif 'T' in date_str:
                                date_obj = datetime.fromisoformat(date_str.replace('Z', '+00:00'))
                            else:
                                date_obj = datetime.fromisoformat(date_str)
                                if date_obj.tzinfo is None:
                                    date_obj = date_obj.replace(tzinfo=timezone.utc)
                            
                            if latest_date is None or date_obj > latest_date:
                                latest_date = date_obj
                        except Exception:
                            continue
        
        return latest_date
    except Exception:
        return None


async def _extract_seller_data(soup: BeautifulSoup, session: aiohttp.ClientSession) -> Optional[SellerData]:
    """Extract seller data from listing page."""
    try:
        avg_rating = 0.0
        num_reviews = 0
        trusted_badge = False
        
        # Look for seller data in JSON
        for script in soup.find_all('script'):
            if not script.string:
                continue
                
            script_content = script.string
            if any(keyword in script_content for keyword in ['seller', 'user', 'rating', 'review']):
                # Extract rating and review patterns
                user_patterns = [
                    r'"user"\s*:\s*\{[^}]*"rating"\s*:\s*([0-9.]+)[^}]*"reviewCount"\s*:\s*(\d+)',
                    r'"seller"\s*:\s*\{[^}]*"rating"\s*:\s*([0-9.]+)[^}]*"reviewCount"\s*:\s*(\d+)',
                    r'"averageRating"\s*:\s*([0-9.]+)[^,}]*"totalReviews"\s*:\s*(\d+)',
                    r'"rating"\s*:\s*([0-9.]+)[^,}]*"reviews"\s*:\s*(\d+)',
                ]
                
                for pattern in user_patterns:
                    match = re.search(pattern, script_content, re.IGNORECASE)
                    if match:
                        avg_rating = float(match.group(1))
                        num_reviews = int(match.group(2))
                        break
                
                # Look for trusted badge
                trusted_patterns = [
                    r'"trustedSeller"\s*:\s*true',
                    r'"trusted"\s*:\s*true',
                    r'"isTrusted"\s*:\s*true',
                ]
                
                for pattern in trusted_patterns:
                    if re.search(pattern, script_content, re.IGNORECASE):
                        trusted_badge = True
                        break
        
        # Get seller profile and last update
        profile_url = _extract_seller_profile_url(soup)
        last_updated = datetime.now(timezone.utc)
        
        if profile_url:
            profile_last_update = await _fetch_seller_last_update(profile_url, session)
            if profile_last_update:
                last_updated = profile_last_update
        
        if avg_rating > 0 or num_reviews > 0:
            return SellerData(
                num_reviews=num_reviews,
                avg_rating=avg_rating,
                trusted_badge=trusted_badge,
                last_updated=last_updated
            )
        
        return None
    except Exception:
        return None


async def get_item_data(url: str, session: aiohttp.ClientSession) -> Tuple[ItemData, Optional[SellerData]]:
    """
    Scrape Grailed item data and seller information.
    
    Args:
        url: Grailed listing URL
        session: aiohttp session for requests
    
    Returns:
        Tuple of (ItemData, Optional[SellerData])
    """
    try:
        async with session.get(url) as response:
            response.raise_for_status()
            html = await response.text()
    except Exception:
        return ItemData(), None
    
    soup = BeautifulSoup(html, 'lxml')
    
    # Extract price and buyability
    price, is_buyable = _extract_price_and_buyability(url, soup)
    
    # Extract shipping
    shipping = _scrape_shipping_grailed(soup)
    
    # Extract title
    title = _extract_title(soup)
    
    # Extract seller data
    seller_data = await _extract_seller_data(soup, session)
    
    item_data = ItemData(
        price=price,
        shipping_us=shipping,
        is_buyable=is_buyable,
        title=title
    )
    
    return item_data, seller_data


def is_grailed_url(url: str) -> bool:
    """Check if URL is a Grailed listing."""
    try:
        parsed = urlparse(url)
        domain = parsed.netloc.lower().split(':')[0]
        return 'grailed' in domain.split('.')
    except Exception:
        return False


def is_grailed_seller_profile(url: str) -> bool:
    """Check if URL is a Grailed seller profile."""
    try:
        parsed = urlparse(url)
        if 'grailed.com' not in parsed.netloc.lower():
            return False
        
        path = parsed.path.lower().strip('/')
        
        # Direct username pattern
        if path and '/' not in path and not path.startswith('listings'):
            excluded_pages = {
                'sell', 'buy', 'search', 'help', 'about', 'terms', 
                'privacy', 'brands', 'designers', 'categories', 'login', 
                'signup', 'settings', 'notifications', 'feed'
            }
            if path not in excluded_pages:
                return True
        
        # Legacy patterns
        if path.startswith('users/') or path.startswith('sellers/') or path.startswith('user/'):
            return True
            
        return False
    except Exception:
        return False


async def analyze_seller_profile(profile_url: str, session: aiohttp.ClientSession) -> Optional[Dict[str, Any]]:
    """
    Analyze Grailed seller profile.
    
    Args:
        profile_url: Seller profile URL
        session: aiohttp session for requests
    
    Returns:
        Dict with seller analysis data or None if failed
    """
    try:
        async with session.get(profile_url) as response:
            response.raise_for_status()
            html = await response.text()
    except Exception:
        return None
    
    soup = BeautifulSoup(html, 'lxml')
    
    avg_rating = 0.0
    num_reviews = 0
    trusted_badge = False
    
    # Extract seller data from profile
    for script in soup.find_all('script'):
        if not script.string:
            continue
            
        script_content = script.string
        if any(keyword in script_content for keyword in ['rating', 'review', 'user', 'seller']):
            patterns = [
                (r'"rating"\s*:\s*([0-9.]+)', r'"reviewCount"\s*:\s*(\d+)'),
                (r'"averageRating"\s*:\s*([0-9.]+)', r'"totalReviews"\s*:\s*(\d+)'),
            ]
            
            for rating_pattern, review_pattern in patterns:
                rating_match = re.search(rating_pattern, script_content, re.IGNORECASE)
                review_match = re.search(review_pattern, script_content, re.IGNORECASE)
                
                if rating_match and review_match:
                    avg_rating = float(rating_match.group(1))
                    num_reviews = int(review_match.group(1))
                    break
            
            # Check for trusted badge
            trusted_patterns = [
                r'"trustedSeller"\s*:\s*true',
                r'"trusted"\s*:\s*true',
                r'"isTrusted"\s*:\s*true',
            ]
            
            for pattern in trusted_patterns:
                if re.search(pattern, script_content, re.IGNORECASE):
                    trusted_badge = True
                    break
    
    # Get last update
    last_updated = await _fetch_seller_last_update(profile_url, session)
    if not last_updated:
        last_updated = datetime.now(timezone.utc)
    
    return {
        'num_reviews': num_reviews,
        'avg_rating': avg_rating,
        'trusted_badge': trusted_badge,
        'last_updated': last_updated
    }